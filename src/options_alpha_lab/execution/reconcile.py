"""Reconcile local lifecycle records against the broker.

Addresses `EXIT-002`, `EXIT-011`, and part of `EXIT-010`. Reconciliation runs at
startup, before any new-risk write, after every mutation or ambiguous response,
and periodically while any order or exposure exists.

The governing rule: **the broker is authoritative about exposure, and the
database is authoritative about responsibility.** Where they disagree the system
does not pick a winner. It halts new risk, records a durable incident, and keeps
managing whatever it might still own — because the dangerous mistake is not
"stopped trading unnecessarily", it is "stopped managing a real position".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..architecture.contracts import ExecutionState
from .gateway import BrokerPort
from .lifecycle import LifecycleStore, ManagedPosition, OrderState, PositionState


@dataclass
class ReconciliationReport:
    at: datetime
    positions_checked: int = 0
    positions_resolved: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    incidents: list[str] = field(default_factory=list)
    unexpected_symbols: list[str] = field(default_factory=list)
    execution_state: ExecutionState = ExecutionState.NORMAL
    broker_unreachable: bool = False

    @property
    def clean(self) -> bool:
        return not self.mismatches and not self.broker_unreachable

    def summary(self) -> str:
        if self.broker_unreachable:
            return "broker unreachable; new risk halted until reconciliation succeeds"
        if not self.positions_checked and not self.unexpected_symbols:
            return "nothing to reconcile"
        if self.clean:
            return f"{self.positions_checked} position(s) reconciled, no mismatch"
        return f"{len(self.mismatches)} mismatch(es): " + "; ".join(self.mismatches[:3])


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _leg_fills(order: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-leg fills from a nested MLeg order, when the broker supplies them."""
    fills: list[dict[str, Any]] = []
    for leg in order.get("legs") or []:
        quantity = leg.get("filled_qty")
        price = leg.get("filled_avg_price")
        if not quantity or price in (None, "", "None"):
            continue
        try:
            if int(float(quantity)) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        fills.append(
            {
                "symbol": leg.get("symbol"),
                "quantity": int(float(quantity)),
                "price": str(price),
                "filled_at": None,
            }
        )
    return fills


class Reconciler:
    """Compares durable lifecycle records with authoritative broker state."""

    def __init__(self, broker: BrokerPort, store: LifecycleStore) -> None:
        self._broker = broker
        self._store = store

    def reconcile(self, *, run_id: str | None = None, now: datetime | None = None
                  ) -> ReconciliationReport:
        stamp = now or datetime.now(UTC)
        report = ReconciliationReport(at=stamp)

        try:
            broker_positions = self._broker.list_positions()
            open_orders = self._broker.list_open_orders()
        except Exception as exc:  # noqa: BLE001 - any read failure halts new risk
            report.broker_unreachable = True
            report.execution_state = ExecutionState.NO_NEW_RISK
            report.mismatches.append(f"broker read failed: {type(exc).__name__}: {exc}")
            report.incidents.append(
                self._store.open_incident(
                    kind="broker_unreachable",
                    detail=f"reconciliation could not read broker state: {exc}",
                    run_id=run_id, now=stamp,
                )
            )
            return report

        held_symbols = {
            str(p.get("symbol")) for p in broker_positions if p.get("symbol")
        }
        working_by_client_id = {
            str(o.get("client_order_id")): o for o in open_orders if o.get("client_order_id")
        }

        managed = self._store.active_positions()
        report.positions_checked = len(managed)
        claimed_symbols: set[str] = set()

        for position in managed:
            claimed_symbols.update({position.long_symbol, position.short_symbol})
            self._reconcile_one(
                position, held_symbols, working_by_client_id, report, run_id, stamp
            )

        # Exposure the broker reports that no local record claims.
        unexpected = sorted(held_symbols - claimed_symbols)
        if unexpected:
            report.unexpected_symbols = unexpected
            report.mismatches.append(f"unclaimed broker exposure: {', '.join(unexpected)}")
            report.incidents.append(
                self._store.open_incident(
                    kind="unexpected_exposure",
                    detail=(
                        "broker reports positions no local record owns: "
                        + ", ".join(unexpected)
                    ),
                    run_id=run_id, now=stamp,
                )
            )

        if report.mismatches:
            report.execution_state = ExecutionState.NO_NEW_RISK
        return report

    def _reconcile_one(
        self,
        position: ManagedPosition,
        held_symbols: set[str],
        working_by_client_id: dict[str, dict[str, Any]],
        report: ReconciliationReport,
        run_id: str | None,
        stamp: datetime,
    ) -> None:
        broker_holds = bool({position.long_symbol, position.short_symbol} & held_symbols)

        entry_state, _, _ = self._store.order_state(position.entry_order_id)
        entry_order = self._fetch_order(position.entry_order_id, working_by_client_id)

        # 1. Resolve the entry order against authoritative state.
        if entry_order is not None:
            filled = self._filled_quantity(entry_order)
            resolved = self._store.apply_order_reconciliation(
                position.entry_order_id,
                broker_status=str(entry_order.get("status")),
                filled_quantity=filled,
                filled_avg_price=_dec(entry_order.get("filled_avg_price")),
                legs=_leg_fills(entry_order),
                now=stamp,
            )
            # INCIDENT is included deliberately: reconciliation exists to heal
            # an incident once the facts are known, not only to raise one.
            if position.state in {PositionState.PENDING, PositionState.INCIDENT}:
                new_state = self._store.apply_entry_outcome(
                    position.position_id,
                    state=resolved,
                    filled_quantity=filled,
                    avg_debit=_dec(entry_order.get("filled_avg_price")),
                    now=stamp,
                )
                report.positions_resolved.append(f"{position.position_id}:{new_state.value}")
                return
        elif (
            position.state in {PositionState.PENDING, PositionState.INCIDENT}
            and entry_state is OrderState.AMBIGUOUS
        ):
            report.mismatches.append(
                f"{position.position_id}: entry order state is ambiguous and the broker "
                "returned no matching order"
            )
            report.incidents.append(
                self._store.open_incident(
                    kind="ambiguous_entry",
                    detail="submitted entry cannot be located at the broker",
                    position_id=position.position_id, run_id=run_id, now=stamp,
                )
            )
            return

        # 2. A position we believe is open must be visible at the broker.
        if position.state is PositionState.OPEN and not broker_holds:
            report.mismatches.append(
                f"{position.position_id}: locally OPEN but the broker holds neither leg"
            )
            report.incidents.append(
                self._store.open_incident(
                    kind="position_vanished",
                    detail=(
                        f"local OPEN position {position.position_id} has no broker exposure "
                        f"in {position.long_symbol} or {position.short_symbol}"
                    ),
                    position_id=position.position_id, run_id=run_id, now=stamp,
                )
            )
            return

        # 3. A close is only complete when the broker confirms flat.
        if position.state is PositionState.CLOSING:
            if position.close_order_id is not None:
                close_order = self._fetch_order(position.close_order_id, working_by_client_id)
                if close_order is not None:
                    self._store.apply_order_reconciliation(
                        position.close_order_id,
                        broker_status=str(close_order.get("status")),
                        filled_quantity=self._filled_quantity(close_order),
                        filled_avg_price=_dec(close_order.get("filled_avg_price")),
                        legs=_leg_fills(close_order),
                        now=stamp,
                    )
            state = self._store.apply_close_outcome(
                position.position_id,
                broker_flat=not broker_holds,
                remaining_quantity=0 if not broker_holds else position.filled_quantity,
                now=stamp,
            )
            report.positions_resolved.append(f"{position.position_id}:{state.value}")
            return

        if position.state is PositionState.INCIDENT:
            report.mismatches.append(
                f"{position.position_id}: unresolved incident; new risk stays halted"
            )

    def _fetch_order(
        self, order_id: str, working_by_client_id: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Find an order by our deterministic client id, working set first."""
        client_order_id = self._store.client_order_id_for(order_id)
        if client_order_id is None:
            return None
        if client_order_id in working_by_client_id:
            return working_by_client_id[client_order_id]
        try:
            return self._broker.get_by_client_order_id(client_order_id)
        except Exception:  # noqa: BLE001 - absence is a normal answer
            return None

    @staticmethod
    def _filled_quantity(order: dict[str, Any]) -> int:
        raw = order.get("filled_qty")
        try:
            return int(float(raw)) if raw not in (None, "", "None") else 0
        except (TypeError, ValueError):
            return 0
