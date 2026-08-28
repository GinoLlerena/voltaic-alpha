"""Item 4: post-submission deadline, cancel, partial fill, late fill (EXIT-011, EXIT-014)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import Direction, ExecutionState, SpreadStrategy
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.deadline import (
    ENTRY_DEADLINE,
    DeadlineEnforcer,
    deadline_for,
)
from options_alpha_lab.execution.gateway import BrokerPort, ExecutionGateway
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent
from options_alpha_lab.execution.lifecycle import (
    LifecycleStore,
    OrderState,
    PositionState,
    TypedInvalidation,
)
from options_alpha_lab.execution.reconcile import Reconciler
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import Decision
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.replay import replay_paths

NOW = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)
PAST_DEADLINE = NOW + ENTRY_DEADLINE + timedelta(seconds=1)
LONG, SHORT = "SPY260918C00640000", "SPY260918C00645000"

WRITE_ENV = {
    "BOT_MODE": "paper_execute", "ALPACA_PAPER_TRADE": "true",
    "ALPACA_TRADING_ENABLED": "true", "REQUIRE_OPERATOR_APPROVAL": "false",
}


class CancelBroker(BrokerPort):
    def __init__(self, *, fail: Exception | None = None,
                 positions: list[dict[str, Any]] | None = None) -> None:
        self.cancels: list[str] = []
        self.fail = fail
        self._positions = positions or []

    def resolved_endpoint(self) -> str:
        return "https://paper-api.alpaca.markets"

    def open_strategy_count(self) -> int:
        return 0

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("the deadline enforcer must never submit")

    def get_by_client_order_id(self, cid: str) -> dict[str, Any] | None:
        return None

    def list_open_orders(self) -> list[dict[str, Any]]:
        return []

    def list_positions(self) -> list[dict[str, Any]]:
        return self._positions

    def cancel_order(self, broker_order_id: str) -> None:
        if self.fail:
            raise self.fail
        self.cancels.append(broker_order_id)


def intent(qty: int = 1) -> OrderIntent:
    return OrderIntent(
        decision_hash="sha256:x", strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        legs=(IntentLeg(LONG, 1, "buy", "buy_to_open"),
              IntentLeg(SHORT, 1, "sell", "sell_to_open")),
        strategy_quantity=qty, limit_price=Decimal("3.39"),
        approval_reference="risk", created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )


class DeadlineCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "d.db"
        self.settings = load_settings(dict(WRITE_ENV, DATABASE_URL=f"sqlite+pysqlite:///{db}"))
        self.engine = build_engine(self.settings)
        create_schema(self.engine)
        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")],
                     self.settings, create=False)
        with Session(self.engine) as session:
            self.decision_id = session.scalars(select(Decision)).first().id
        self.store = LifecycleStore(self.engine)
        self.broker = CancelBroker()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def enforcer(self, broker: CancelBroker | None = None,
                 state: ExecutionState = ExecutionState.NORMAL) -> DeadlineEnforcer:
        self.broker = broker or self.broker
        gateway = ExecutionGateway(self.broker, self.settings, execution_state=state,
                                   clock=lambda: NOW)
        return DeadlineEnforcer(gateway, self.store)

    def submitted(self, qty: int = 1) -> tuple[str, str]:
        i = intent(qty)
        order_id, position_id = self.store.prepare_entry(
            decision_id=self.decision_id, intent=i,
            request=prepare_mleg_request(i, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=22),
            width=Decimal("5.00"), max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("631.63"), Direction.BULLISH, "close"),
            now=NOW,
        )
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        return order_id, position_id

    def kinds(self) -> list[str]:
        return [i.kind for i in self.store.open_incidents()]


class DeadlineTests(DeadlineCase):
    def test_an_order_inside_its_deadline_is_left_alone(self) -> None:
        self.submitted()
        outcome = self.enforcer().enforce(now=NOW + timedelta(seconds=30))
        self.assertFalse(outcome.acted)
        self.assertEqual(self.broker.cancels, [])

    def test_an_unfilled_order_past_its_deadline_is_canceled(self) -> None:
        order_id, _ = self.submitted()
        outcome = self.enforcer().enforce(now=PAST_DEADLINE)
        self.assertEqual(outcome.canceled, [order_id])
        self.assertEqual(self.broker.cancels, ["brk-1"])

    def test_a_cancel_request_does_not_mark_the_order_terminal(self) -> None:
        # A cancel can lose a race with a fill; only reconciliation decides.
        order_id, position_id = self.submitted()
        self.enforcer().enforce(now=PAST_DEADLINE)
        state, _, _ = self.store.order_state(order_id)
        self.assertFalse(state.is_terminal)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.PENDING)

    def test_a_terminal_order_is_not_canceled_again(self) -> None:
        order_id, _ = self.submitted()
        self.store.apply_order_reconciliation(order_id, broker_status="canceled",
                                              filled_quantity=0, filled_avg_price=None,
                                              now=NOW)
        outcome = self.enforcer().enforce(now=PAST_DEADLINE)
        self.assertEqual(self.broker.cancels, [])
        self.assertFalse(outcome.acted)

    def test_deadline_differs_by_role(self) -> None:
        entry = deadline_for("entry", NOW)
        close = deadline_for("close", NOW)
        self.assertLess(entry, close, "a close is given longer than an entry")


class PartialFillTests(DeadlineCase):
    def test_a_partial_fill_keeps_the_filled_exposure_and_cancels_the_rest(self) -> None:
        order_id, position_id = self.submitted(qty=3)
        self.store.apply_order_reconciliation(
            order_id, broker_status="partially_filled", filled_quantity=1,
            filled_avg_price=Decimal("3.20"), now=NOW,
        )
        self.store.apply_entry_outcome(position_id, state=OrderState.PARTIALLY_FILLED,
                                       filled_quantity=1, avg_debit=Decimal("3.20"), now=NOW)
        outcome = self.enforcer().enforce(now=PAST_DEADLINE)
        self.assertEqual(outcome.partial_fills, [position_id])
        self.assertEqual(self.broker.cancels, ["brk-1"], "the remainder is canceled")
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertEqual(managed.filled_quantity, 1, "filled exposure is still managed")
        self.assertIn("partial_fill_at_deadline", self.kinds())


class LateFillTests(DeadlineCase):
    def test_a_fill_reported_after_abandonment_reinstates_the_position(self) -> None:
        # EXIT-014: a cancel and a fill can cross.
        order_id, position_id = self.submitted()
        self.store.apply_order_reconciliation(order_id, broker_status="canceled",
                                              filled_quantity=0, filled_avg_price=None,
                                              now=NOW)
        self.store.apply_entry_outcome(position_id, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        self.assertIs(self.store.get_position(position_id).state, PositionState.ABANDONED)

        # The broker now reports it filled after all.
        self.store.apply_order_reconciliation(order_id, broker_status="filled",
                                              filled_quantity=1,
                                              filled_avg_price=Decimal("3.13"), now=NOW)
        outcome = self.enforcer().enforce(now=PAST_DEADLINE)
        self.assertEqual(outcome.late_fills, [position_id])
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.OPEN)
        self.assertEqual(managed.avg_entry_debit, Decimal("3.13"))
        self.assertIn("late_fill_after_terminal", self.kinds())

    def test_reconciliation_also_detects_broker_exposure_on_an_abandoned_entry(self) -> None:
        order_id, position_id = self.submitted()
        self.store.apply_entry_outcome(position_id, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        broker = CancelBroker(positions=[{"symbol": LONG, "qty": "1"}])
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertIn("late_fill_after_terminal", self.kinds())


class CancelFailureTests(DeadlineCase):
    def test_a_refused_cancel_raises_an_incident(self) -> None:
        self.submitted()
        enforcer = self.enforcer(state=ExecutionState.FREEZE_ALL_WRITES)
        outcome = enforcer.enforce(now=PAST_DEADLINE)
        self.assertTrue(outcome.failures)
        self.assertIn("cancel_refused", self.kinds())

    def test_an_ambiguous_cancel_raises_an_incident(self) -> None:
        self.submitted()
        outcome = self.enforcer(CancelBroker(fail=ConnectionError("timeout"))).enforce(
            now=PAST_DEADLINE
        )
        self.assertTrue(outcome.failures)
        self.assertIn("cancel_ambiguous", self.kinds())

    def test_an_order_with_no_broker_id_cannot_be_canceled_and_is_flagged(self) -> None:
        i = intent()
        order_id, _ = self.store.prepare_entry(
            decision_id=self.decision_id, intent=i,
            request=prepare_mleg_request(i, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=22),
            width=Decimal("5.00"), max_loss=Decimal("339.00"), invalidation=None, now=NOW,
        )
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status=None, ambiguous=True, now=NOW)
        outcome = self.enforcer().enforce(now=PAST_DEADLINE)
        self.assertTrue(outcome.failures)
        self.assertIn("uncancellable_order", self.kinds())


class GatewayCancelGuardTests(DeadlineCase):
    def test_cancel_requires_paper_authority(self) -> None:
        from options_alpha_lab.execution.gateway import ExecutionRefused

        class LiveBroker(CancelBroker):
            def resolved_endpoint(self) -> str:
                return "https://api.alpaca.markets"

        gateway = ExecutionGateway(LiveBroker(), self.settings, clock=lambda: NOW)
        with self.assertRaises(ExecutionRefused):
            gateway.cancel("brk-1")

    def test_cancel_is_permitted_under_no_new_risk(self) -> None:
        # A cancel reduces exposure; blocking it would trap the order.
        gateway = ExecutionGateway(self.broker, self.settings,
                                   execution_state=ExecutionState.NO_NEW_RISK,
                                   clock=lambda: NOW)
        gateway.cancel("brk-1")
        self.assertEqual(self.broker.cancels, ["brk-1"])


if __name__ == "__main__":
    unittest.main()
