"""The only component in this project that can write to a broker.

Every guard here is checked immediately before the write, not at startup, because
the interesting failures are the ones that develop between the two. In order:

1. Configuration permits writes at all.
2. The resolved endpoint is the Paper endpoint, verified from the client that is
   about to be used rather than from the environment variable that configured it.
3. Durable execution state allows the write.
4. An operator has approved, when approval is required.
5. No strategy is already open or pending.
6. The intent has not expired.
7. The prepared request still matches the intent hash.

A failure at any step raises. There is no path that degrades to "submit anyway".

**Risk-reducing closes are treated differently on purpose.** Guards 3, 4, and 5
exist to stop new risk being taken. Applying them to a close would trap exposure
at exactly the moment it needs to be reduced: an operator who is asleep, a halt
state raised by stale data, or the position itself occupying the single strategy
slot would each prevent an exit. A close still requires Paper authority, an
unexpired intent, and a matching hash, and `FREEZE_ALL_WRITES` still blocks it,
because that state exists for integrity incidents where writing at all is unsafe.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..architecture.contracts import ExecutionState
from ..config import Settings
from .intent import OrderIntent
from .request import PreparedRequest

PAPER_HOST = "paper-api.alpaca.markets"


class ExecutionRefused(RuntimeError):
    """A guard refused the write **before** anything was sent.

    Nothing reached the broker, so no exposure can exist. This is safe to treat
    as "no position was created".
    """


class AmbiguousSubmission(ExecutionRefused):
    """The request was sent and its outcome is unknown.

    Distinct from `ExecutionRefused` on purpose. A caller that treats these the
    same will mark a position abandoned that the broker may actually hold, which
    loses responsibility for real exposure. The correct response is to retain
    responsibility, halt new risk, and keep reconciling.
    """


@dataclass(frozen=True)
class SubmissionResult:
    client_order_id: str
    broker_order_id: str | None
    status: str
    submitted_at: datetime
    reconciled: bool
    ambiguous: bool = False


class BrokerPort:
    """The narrow surface the gateway and reconciler need."""

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def resolved_endpoint(self) -> str:
        raise NotImplementedError

    def open_strategy_count(self) -> int:
        raise NotImplementedError

    # -- reconciliation reads ---------------------------------------------
    def list_open_orders(self) -> list[dict[str, Any]]:
        """Every order still working at the broker."""
        raise NotImplementedError

    def list_positions(self) -> list[dict[str, Any]]:
        """Every position the broker believes we hold."""
        raise NotImplementedError

    # -- risk-reducing mutation -------------------------------------------
    def cancel_order(self, broker_order_id: str) -> None:
        """Cancel a working order. Never creates exposure."""
        raise NotImplementedError


class ExecutionGateway:
    def __init__(
        self,
        broker: BrokerPort,
        settings: Settings,
        *,
        execution_state: ExecutionState = ExecutionState.NORMAL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._broker = broker
        self._settings = settings
        self.execution_state = execution_state
        self._clock = clock or (lambda: datetime.now(UTC))

    # -- guards ------------------------------------------------------------
    def preflight(
        self,
        intent: OrderIntent,
        request: PreparedRequest,
        *,
        reduces_risk: bool = False,
        operator_approval: str | None = None,
    ) -> None:
        if not self._settings.may_write_orders:
            raise ExecutionRefused(
                "configuration does not permit order writes "
                f"(mode={self._settings.bot_mode.value}, "
                f"trading_enabled={self._settings.alpaca_trading_enabled})"
            )

        endpoint = self._broker.resolved_endpoint()
        if PAPER_HOST not in endpoint:
            # Checked against the client that is about to be used, not the flag
            # that configured it. Those can disagree.
            raise ExecutionRefused(f"resolved endpoint {endpoint!r} is not the Paper endpoint")

        if self.execution_state is ExecutionState.FREEZE_ALL_WRITES:
            # The one state that blocks a close too. It raises an incident
            # precisely because it can prevent risk reduction.
            raise ExecutionRefused("execution state FREEZE_ALL_WRITES blocks every write")

        if not reduces_risk:
            if self.execution_state is not ExecutionState.NORMAL:
                raise ExecutionRefused(
                    f"execution state {self.execution_state.value} blocks new risk"
                )

            if self._settings.require_operator_approval and not operator_approval:
                raise ExecutionRefused(
                    "REQUIRE_OPERATOR_APPROVAL is set and no operator approval was supplied; "
                    "an autonomous open is not permitted in this configuration"
                )

            if self._broker.open_strategy_count() > 0:
                raise ExecutionRefused("H0 permits one open or pending strategy at a time")

        if intent.is_expired(self._clock()):
            raise ExecutionRefused(f"intent expired at {intent.expires_at.isoformat()}")

        if not request.matches(intent):
            raise ExecutionRefused("prepared request does not match the approved intent hash")

    # -- write -------------------------------------------------------------
    def submit(
        self,
        intent: OrderIntent,
        request: PreparedRequest,
        *,
        reduces_risk: bool = False,
        operator_approval: str | None = None,
    ) -> SubmissionResult:
        """Submit once. An ambiguous response is resolved by lookup, never by retry."""
        self.preflight(
            intent, request, reduces_risk=reduces_risk, operator_approval=operator_approval
        )
        submitted_at = self._clock()

        try:
            response = self._broker.submit(request.body)
        except Exception as exc:  # noqa: BLE001 - any failure becomes an ambiguous state
            # We do not know whether the broker accepted it. Resolving by
            # re-submitting is how duplicates are created; resolve by lookup.
            try:
                found = self._broker.get_by_client_order_id(request.client_order_id)
            except Exception:  # noqa: BLE001 - the lookup is as unreliable as the submit
                found = None
            if found is None:
                # We could not confirm the order is absent; we only failed to
                # find it. Those are different, and only one of them is safe.
                raise AmbiguousSubmission(
                    f"submit failed and no order could be located for "
                    f"{request.client_order_id}: {exc}"
                ) from exc
            return SubmissionResult(
                client_order_id=request.client_order_id,
                broker_order_id=str(found.get("id")) if found.get("id") else None,
                status=str(found.get("status", "unknown")),
                submitted_at=submitted_at,
                reconciled=True,
                ambiguous=True,
            )

        return SubmissionResult(
            client_order_id=request.client_order_id,
            broker_order_id=str(response.get("id")) if response.get("id") else None,
            status=str(response.get("status", "unknown")),
            submitted_at=submitted_at,
            reconciled=False,
        )

    def cancel(self, broker_order_id: str, *, reason: str = "deadline") -> None:
        """Cancel a working order.

        A cancel removes exposure rather than creating it, so it is not subject
        to the approval, halt, or one-strategy guards. `FREEZE_ALL_WRITES` still
        blocks it: that state exists for incidents where writing at all is
        unsafe.
        """
        if not self._settings.may_write_orders:
            raise ExecutionRefused("configuration does not permit order writes")
        endpoint = self._broker.resolved_endpoint()
        if PAPER_HOST not in endpoint:
            raise ExecutionRefused(f"resolved endpoint {endpoint!r} is not the Paper endpoint")
        if self.execution_state is ExecutionState.FREEZE_ALL_WRITES:
            raise ExecutionRefused("execution state FREEZE_ALL_WRITES blocks every write")
        self._broker.cancel_order(broker_order_id)

    def reconcile(self, client_order_id: str) -> dict[str, Any] | None:
        """Authoritative local view of one order, by the id we chose."""
        return self._broker.get_by_client_order_id(client_order_id)


class AlpacaBroker(BrokerPort):
    """alpaca-py implementation. The only place order submission exists."""

    def __init__(self, api_key: str, secret_key: str) -> None:
        from alpaca.trading.client import TradingClient

        # paper=True is not a preference here; a live client is never constructed.
        self._client = TradingClient(api_key, secret_key, paper=True)

    def resolved_endpoint(self) -> str:
        base = getattr(self._client, "_base_url", "") or getattr(self._client, "base_url", "")
        # alpaca-py stores this as a BaseURL enum whose str() is the member name,
        # not the URL. Resolving the member name would make the Paper check pass
        # or fail on the wrong string, so read .value when it is present.
        return str(getattr(base, "value", base))

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

        legs = [
            OptionLegRequest(
                symbol=leg["symbol"],
                ratio_qty=int(leg["ratio_qty"]),
                side=OrderSide(leg["side"]),
                position_intent=PositionIntent(leg["position_intent"]),
            )
            for leg in body["legs"]
        ]
        request = LimitOrderRequest(
            qty=int(body["qty"]),
            limit_price=float(Decimal(body["limit_price"])),
            order_class=OrderClass.MLEG,
            time_in_force=TimeInForce(body["time_in_force"]),
            client_order_id=body["client_order_id"],
            legs=legs,
        )
        order = self._client.submit_order(request)
        return _as_dict(order)

    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        try:
            order = self._client.get_order_by_client_id(client_order_id)
        except Exception:  # noqa: BLE001 - a missing order is a normal answer
            return None
        return _as_dict(order) if order is not None else None

    def open_strategy_count(self) -> int:
        return len(self.list_open_orders()) + len(self.list_positions())

    def list_open_orders(self) -> list[dict[str, Any]]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        orders = self._client.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True)
        )
        return [_as_dict(order) for order in orders]

    def list_positions(self) -> list[dict[str, Any]]:
        return [_as_dict(position) for position in self._client.get_all_positions()]

    def cancel_order(self, broker_order_id: str) -> None:
        self._client.cancel_order_by_id(broker_order_id)


def _normalize(value: Any) -> Any:
    """Coerce scalars to strings **without flattening structure**.

    Every scalar becomes a string so the reconciler can compare provider values
    that arrive as `Decimal`, `UUID`, enum, or `datetime` on different reads of
    the same order. Containers are walked instead of stringified: an MLeg order
    carries its per-leg fills in a nested `legs` list, and `str()` on that list
    turns the only record of which leg filled into prose. `_leg_fills` would
    then iterate the string character by character and raise `AttributeError`,
    taking reconciliation down at exactly the moment a real fill arrives.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return str(value)


def _as_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        dumped: dict[str, Any] = obj.model_dump()
        return {str(key): _normalize(value) for key, value in dumped.items()}
    return dict(obj)
