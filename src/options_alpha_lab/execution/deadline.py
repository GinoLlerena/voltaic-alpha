"""Post-submission order deadline.

Addresses `EXIT-011`. The intent TTL expires *authority* before a request is
sent; it says nothing about an order that has already reached the broker. An
accepted limit that never fills previously sat there indefinitely, occupying the
single strategy slot, while the agent believed it held a position.

H0 policy is **cancel-only** at the deadline. The plan's bounded
replace-and-chase proposal stays provisional: chasing a spread has real economic
consequences and no replay evidence yet, so the safe rule is to stop trying, not
to try harder at a worse price.

Two races are handled explicitly rather than hoped away:

* **Partial fill at the deadline.** The filled quantity is real exposure and is
  managed; only the remainder is canceled.
* **Late fill after a cancel.** A cancel and a fill can cross. If the broker
  later reports a fill on an order we abandoned, that is exposure we own, and it
  is reinstated under an incident rather than ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..architecture.contracts import ExecutionState
from .gateway import ExecutionGateway, ExecutionRefused
from .lifecycle import LifecycleStore, OrderState, PositionState

#: PROVISIONAL. Owner approval required before this governs a live entry.
ENTRY_DEADLINE = timedelta(seconds=90)
CLOSE_DEADLINE = timedelta(seconds=120)


@dataclass
class DeadlineOutcome:
    at: datetime
    canceled: list[str] = field(default_factory=list)
    partial_fills: list[str] = field(default_factory=list)
    late_fills: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def acted(self) -> bool:
        return bool(self.canceled or self.partial_fills or self.late_fills or self.failures)

    def summary(self) -> str:
        parts = []
        if self.canceled:
            parts.append(f"canceled {len(self.canceled)}")
        if self.partial_fills:
            parts.append(f"partial {len(self.partial_fills)}")
        if self.late_fills:
            parts.append(f"late fill {len(self.late_fills)}")
        if self.failures:
            parts.append(f"failed {len(self.failures)}")
        return ", ".join(parts) or "no order past its deadline"


def deadline_for(role: str, submitted_at: datetime) -> datetime:
    return submitted_at + (ENTRY_DEADLINE if role == "entry" else CLOSE_DEADLINE)


class DeadlineEnforcer:
    """Cancels working orders that have outlived their post-submission deadline."""

    def __init__(self, gateway: ExecutionGateway, store: LifecycleStore) -> None:
        self._gateway = gateway
        self._store = store

    def enforce(self, *, run_id: str | None = None, now: datetime | None = None
                ) -> DeadlineOutcome:
        stamp = now or datetime.now(UTC)
        outcome = DeadlineOutcome(at=stamp)

        for position in self._store.active_positions(include_abandoned=True):
            order_id = (
                position.close_order_id
                if position.state is PositionState.CLOSING and position.close_order_id
                else position.entry_order_id
            )
            record = self._store.order_record(order_id)
            if record is None:
                continue

            state, filled, _ = self._store.order_state(order_id)

            # Late fill: an order we treated as terminal turns out to have filled.
            if position.state is PositionState.ABANDONED and filled > 0:
                self._handle_late_fill(position.position_id, order_id, filled, outcome,
                                       run_id, stamp)
                continue

            if state.is_terminal or state is OrderState.PREPARED:
                continue
            if record["submitted_at"] is None:
                continue
            if stamp < deadline_for(record["role"], record["submitted_at"]):
                continue

            if filled > 0:
                # Real exposure exists. Cancel only the unfilled remainder.
                outcome.partial_fills.append(position.position_id)
                self._store.open_incident(
                    kind="partial_fill_at_deadline", severity="medium",
                    detail=(
                        f"order {order_id} filled {filled} of "
                        f"{record['strategy_quantity']} by its deadline; "
                        "cancelling the remainder and managing what filled"
                    ),
                    execution_state=ExecutionState.NORMAL,
                    position_id=position.position_id, run_id=run_id, now=stamp,
                )

            self._cancel(position.position_id, order_id, record, outcome, run_id, stamp)

        return outcome

    def _cancel(
        self, position_id: str, order_id: str, record: dict[str, Any],
        outcome: DeadlineOutcome, run_id: str | None, stamp: datetime,
    ) -> None:
        broker_order_id = record["broker_order_id"]
        if not broker_order_id:
            outcome.failures.append(f"{order_id}: no broker order id to cancel")
            self._store.open_incident(
                kind="uncancellable_order",
                detail=f"order {order_id} passed its deadline with no broker id",
                position_id=position_id, run_id=run_id, now=stamp,
            )
            return
        try:
            self._gateway.cancel(broker_order_id, reason="post_submission_deadline")
        except ExecutionRefused as exc:
            outcome.failures.append(f"{order_id}: {exc}")
            self._store.open_incident(
                kind="cancel_refused",
                detail=f"cancel refused for order {order_id}: {exc}",
                position_id=position_id, run_id=run_id, now=stamp,
            )
            return
        except Exception as exc:  # noqa: BLE001 - the order may or may not be canceled
            outcome.failures.append(f"{order_id}: {type(exc).__name__}")
            self._store.open_incident(
                kind="cancel_ambiguous",
                detail=f"cancel outcome unknown for order {order_id}: {exc}",
                position_id=position_id, run_id=run_id, now=stamp,
            )
            return
        outcome.canceled.append(order_id)
        # The cancel is requested, not confirmed. Reconciliation decides the
        # terminal state; a cancel can still lose a race with a fill.
        self._store.record_cancel_requested(order_id, now=stamp)

    def _handle_late_fill(
        self, position_id: str, order_id: str, filled: int,
        outcome: DeadlineOutcome, run_id: str | None, stamp: datetime,
    ) -> None:
        _, _, avg = self._store.order_state(order_id)
        self._store.open_incident(
            kind="late_fill_after_terminal",
            detail=(
                f"order {order_id} reported {filled} filled after being treated as "
                "terminal; exposure is reinstated and new risk is halted"
            ),
            position_id=position_id, run_id=run_id, now=stamp,
        )
        self._store.apply_entry_outcome(
            position_id, state=OrderState.FILLED, filled_quantity=filled,
            avg_debit=avg or Decimal("0"), now=stamp,
        )
        outcome.late_fills.append(position_id)
