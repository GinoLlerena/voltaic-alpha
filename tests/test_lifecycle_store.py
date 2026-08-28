"""Item 1: state is durable before and after every broker mutation (EXIT-001, EXIT-002)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import Direction, SpreadStrategy
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent, build_close_intent
from options_alpha_lab.execution.lifecycle import (
    LifecycleStore,
    OrderState,
    PositionState,
    TypedInvalidation,
    map_broker_status,
)
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import BrokerOrder, Fill, Incident, Position
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.replay import replay_paths

NOW = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)
LONG, SHORT = "SPY260918C00640000", "SPY260918C00645000"


def entry_intent() -> OrderIntent:
    return OrderIntent(
        decision_hash="sha256:x",
        strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        legs=(IntentLeg(LONG, 1, "buy", "buy_to_open"),
              IntentLeg(SHORT, 1, "sell", "sell_to_open")),
        strategy_quantity=1,
        limit_price=Decimal("3.39"),
        approval_reference="risk:h0",
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )


class StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "lifecycle.db"
        self.settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{db}",
        })
        self.engine = build_engine(self.settings)
        create_schema(self.engine)
        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")],
                     self.settings, create=False)
        from options_alpha_lab.persistence.models import Decision

        with Session(self.engine) as session:
            decision = session.scalars(select(Decision)).first()
            assert decision is not None
            self.decision_id = decision.id
        self.store = LifecycleStore(self.engine)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def prepare(self, intent: OrderIntent | None = None) -> tuple[str, str]:
        intent = intent or entry_intent()
        return self.store.prepare_entry(
            decision_id=self.decision_id,
            intent=intent,
            request=prepare_mleg_request(intent, now=NOW),
            direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT,
            expiration=NOW + timedelta(days=22),
            width=Decimal("5.00"), max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("631.63"), Direction.BULLISH, "daily_close"),
            now=NOW,
        )


class PersistBeforeMutationTests(StoreCase):
    def test_intent_request_order_and_position_exist_before_sending(self) -> None:
        # A crash between send and response must leave a durable record that
        # something may be in flight.
        order_id, position_id = self.prepare()
        with Session(self.engine) as session:
            order = session.get(BrokerOrder, order_id)
            position = session.get(Position, position_id)
            assert order is not None and position is not None
            self.assertEqual(order.local_state, OrderState.PREPARED.value)
            self.assertIsNone(order.submitted_at)
            self.assertIsNone(order.broker_order_id)
            self.assertEqual(position.lifecycle_status, PositionState.PENDING.value)

    def test_a_pending_position_asserts_no_exposure(self) -> None:
        _, position_id = self.prepare()
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertEqual(managed.filled_quantity, 0)
        self.assertIsNone(managed.avg_entry_debit)
        self.assertFalse(managed.has_confirmed_exposure)


class AcceptanceIsNotFillTests(StoreCase):
    def test_a_broker_claiming_filled_at_submit_is_recorded_as_submitted(self) -> None:
        # EXIT-001. The submission response never establishes a fill.
        order_id, position_id = self.prepare()
        state = self.store.record_submission(
            order_id, broker_order_id="brk-1", broker_status="filled", now=NOW
        )
        self.assertIs(state, OrderState.SUBMITTED)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.PENDING)

    def test_only_reconciled_fills_open_a_position_and_set_the_basis(self) -> None:
        order_id, position_id = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("3.13"),
            legs=[{"symbol": LONG, "quantity": 1, "price": "6.90"},
                  {"symbol": SHORT, "quantity": 1, "price": "3.77"}],
            now=NOW,
        )
        state = self.store.apply_entry_outcome(
            position_id, state=OrderState.FILLED, filled_quantity=1,
            avg_debit=Decimal("3.13"), now=NOW,
        )
        self.assertIs(state, PositionState.OPEN)
        managed = self.store.get_position(position_id)
        assert managed is not None
        # The exit basis is the actual fill, not the 3.39 limit.
        self.assertEqual(managed.avg_entry_debit, Decimal("3.13"))
        self.assertNotEqual(managed.avg_entry_debit, entry_intent().limit_price)
        self.assertTrue(managed.has_confirmed_exposure)

    def test_an_unknown_broker_status_is_ambiguous_rather_than_guessed(self) -> None:
        self.assertIs(map_broker_status("some_new_status"), OrderState.AMBIGUOUS)
        self.assertIs(map_broker_status(None), OrderState.AMBIGUOUS)
        self.assertIs(map_broker_status("OrderStatus.FILLED"), OrderState.FILLED)

    def test_fill_reconciliation_is_idempotent(self) -> None:
        order_id, _ = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        legs = [{"symbol": LONG, "quantity": 1, "price": "6.90"}]
        for _ in range(3):
            self.store.apply_order_reconciliation(
                order_id, broker_status="filled", filled_quantity=1,
                filled_avg_price=Decimal("3.13"), legs=legs, now=NOW,
            )
        with Session(self.engine) as session:
            fills = session.scalars(
                select(Fill).where(Fill.broker_order_id == order_id)
            ).all()
        self.assertEqual(len(fills), 1, "repeated reconciliation must not duplicate fills")


class TerminalEntryTests(StoreCase):
    def test_a_canceled_entry_creates_no_exposure(self) -> None:
        order_id, position_id = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="canceled", filled_quantity=0,
            filled_avg_price=None, now=NOW,
        )
        state = self.store.apply_entry_outcome(
            position_id, state=OrderState.CANCELED, filled_quantity=0,
            avg_debit=None, now=NOW,
        )
        self.assertIs(state, PositionState.ABANDONED)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertFalse(managed.has_confirmed_exposure)

    def test_a_rejected_entry_creates_no_exposure(self) -> None:
        order_id, position_id = self.prepare()
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status="rejected", now=NOW)
        state = self.store.apply_entry_outcome(
            position_id, state=OrderState.REJECTED, filled_quantity=0,
            avg_debit=None, now=NOW,
        )
        self.assertIs(state, PositionState.ABANDONED)

    def test_an_unfilled_but_still_open_entry_stays_pending(self) -> None:
        order_id, position_id = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="new", now=NOW)
        state = self.store.apply_entry_outcome(
            position_id, state=OrderState.SUBMITTED, filled_quantity=0,
            avg_debit=None, now=NOW,
        )
        self.assertIs(state, PositionState.PENDING)

    def test_a_partial_fill_manages_only_the_filled_quantity(self) -> None:
        intent = OrderIntent(
            decision_hash="sha256:x", strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
            legs=entry_intent().legs, strategy_quantity=3,
            limit_price=Decimal("3.39"), approval_reference="risk:h0",
            created_at=NOW, expires_at=NOW + timedelta(seconds=90),
        )
        order_id, position_id = self.prepare(intent)
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="partially_filled", filled_quantity=1,
            filled_avg_price=Decimal("3.20"), now=NOW,
        )
        self.store.apply_entry_outcome(
            position_id, state=OrderState.PARTIALLY_FILLED, filled_quantity=1,
            avg_debit=Decimal("3.20"), now=NOW,
        )
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertEqual(managed.requested_quantity, 3)
        self.assertEqual(managed.filled_quantity, 1, "only filled exposure is managed")


class CloseResponsibilityTests(StoreCase):
    def opened(self) -> tuple[str, str]:
        order_id, position_id = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("3.13"), now=NOW,
        )
        self.store.apply_entry_outcome(position_id, state=OrderState.FILLED,
                                       filled_quantity=1, avg_debit=Decimal("3.13"), now=NOW)
        return order_id, position_id

    def test_a_submitted_close_does_not_release_responsibility(self) -> None:
        # EXIT-001: never report flat before the broker confirms it.
        _, position_id = self.opened()
        closing = build_close_intent(entry_intent(), approval_reference="exit:stop",
                                     limit_price=Decimal("2.80"), now=NOW)
        self.store.prepare_close(
            position_id=position_id, decision_id=self.decision_id, intent=closing,
            request=prepare_mleg_request(closing, now=NOW), reason="stop_loss", now=NOW,
        )
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.CLOSING)
        self.assertTrue(managed.has_confirmed_exposure, "exposure is still owned")

    def test_only_a_confirmed_flat_broker_position_closes_it(self) -> None:
        _, position_id = self.opened()
        closing = build_close_intent(entry_intent(), approval_reference="exit:stop",
                                     limit_price=Decimal("2.80"), now=NOW)
        self.store.prepare_close(position_id=position_id, decision_id=self.decision_id,
                                 intent=closing, request=prepare_mleg_request(closing, now=NOW),
                                 reason="stop_loss", now=NOW)
        still = self.store.apply_close_outcome(position_id, broker_flat=False,
                                               remaining_quantity=1, now=NOW)
        self.assertIs(still, PositionState.CLOSING)
        done = self.store.apply_close_outcome(position_id, broker_flat=True,
                                              remaining_quantity=0, now=NOW)
        self.assertIs(done, PositionState.CLOSED)

    def test_a_partial_close_keeps_the_remainder_owned(self) -> None:
        _, position_id = self.opened()
        state = self.store.apply_close_outcome(position_id, broker_flat=False,
                                               remaining_quantity=1, now=NOW)
        self.assertIs(state, PositionState.CLOSING)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertEqual(managed.filled_quantity, 1)


class DurabilityTests(StoreCase):
    def test_a_new_store_on_the_same_database_sees_the_position(self) -> None:
        # EXIT-002: state survives the process that created it.
        _, position_id = self.prepare()
        rebuilt = LifecycleStore(build_engine(self.settings))
        active = rebuilt.active_positions()
        self.assertEqual([p.position_id for p in active], [position_id])

    def test_closed_and_abandoned_positions_leave_the_active_set(self) -> None:
        order_id, position_id = self.prepare()
        self.store.record_submission(order_id, broker_order_id="b",
                                     broker_status="canceled", now=NOW)
        self.store.apply_entry_outcome(position_id, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        self.assertEqual(self.store.active_positions(), [])

    def test_typed_invalidation_survives_a_round_trip(self) -> None:
        # EXIT-005: stored, not parsed back out of prose.
        _, position_id = self.prepare()
        managed = self.store.get_position(position_id)
        assert managed is not None and managed.invalidation is not None
        self.assertEqual(managed.invalidation.level, Decimal("631.63"))
        self.assertIs(managed.invalidation.direction, Direction.BULLISH)
        self.assertEqual(managed.invalidation.source, "daily_close")
        self.assertTrue(managed.invalidation.breached(Decimal("631.00")))
        self.assertFalse(managed.invalidation.breached(Decimal("632.00")))


class IncidentTests(StoreCase):
    def test_an_incident_is_durable_and_marks_the_position(self) -> None:
        # EXIT-004/EXIT-010: a console line is not an incident.
        _, position_id = self.prepare()
        self.store.open_incident(
            kind="broker_local_mismatch", detail="broker reports exposure we do not own",
            position_id=position_id, now=NOW,
        )
        with Session(self.engine) as session:
            incidents = session.scalars(select(Incident)).all()
            position = session.get(Position, position_id)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].execution_state, "NO_NEW_RISK")
        assert position is not None
        self.assertEqual(position.lifecycle_status, PositionState.INCIDENT.value)
        self.assertEqual(len(self.store.open_incidents()), 1)

    def test_an_incident_never_reopens_a_closed_position(self) -> None:
        order_id, position_id = self.prepare()
        self.store.record_submission(order_id, broker_order_id="b",
                                     broker_status="canceled", now=NOW)
        self.store.apply_entry_outcome(position_id, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        self.store.open_incident(kind="late_fill", detail="fill after cancel",
                                 position_id=position_id, now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.ABANDONED)


if __name__ == "__main__":
    unittest.main()
