"""Item 2: reconciliation at startup and periodically; mismatches halt new risk."""

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
from options_alpha_lab.execution.gateway import BrokerPort
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent, build_close_intent
from options_alpha_lab.execution.lifecycle import (
    LifecycleStore,
    OrderState,
    PositionState,
    TypedInvalidation,
)
from options_alpha_lab.execution.reconcile import Reconciler
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import Decision, Incident
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.replay import replay_paths

NOW = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)
LONG, SHORT = "SPY260918C00640000", "SPY260918C00645000"


def entry_intent(qty: int = 1) -> OrderIntent:
    return OrderIntent(
        decision_hash="sha256:x", strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        legs=(IntentLeg(LONG, 1, "buy", "buy_to_open"),
              IntentLeg(SHORT, 1, "sell", "sell_to_open")),
        strategy_quantity=qty, limit_price=Decimal("3.39"),
        approval_reference="risk:h0", created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )


class FakeBroker(BrokerPort):
    def __init__(self, *, positions: list[dict[str, Any]] | None = None,
                 open_orders: list[dict[str, Any]] | None = None,
                 by_client_id: dict[str, dict[str, Any]] | None = None,
                 raises: Exception | None = None) -> None:
        self._positions = positions or []
        self._open_orders = open_orders or []
        self._by_client_id = by_client_id or {}
        self._raises = raises

    def resolved_endpoint(self) -> str:
        return "https://paper-api.alpaca.markets"

    def open_strategy_count(self) -> int:
        return len(self._positions) + len(self._open_orders)

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("reconciliation must never submit")

    def list_positions(self) -> list[dict[str, Any]]:
        if self._raises:
            raise self._raises
        return self._positions

    def list_open_orders(self) -> list[dict[str, Any]]:
        if self._raises:
            raise self._raises
        return self._open_orders

    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        return self._by_client_id.get(client_order_id)


def filled_order(client_order_id: str, qty: int = 1, avg: str = "3.13",
                 status: str = "filled") -> dict[str, Any]:
    return {
        "client_order_id": client_order_id, "id": "brk-1", "status": status,
        "filled_qty": str(qty), "filled_avg_price": avg,
        "legs": [
            {"symbol": LONG, "filled_qty": str(qty), "filled_avg_price": "6.90"},
            {"symbol": SHORT, "filled_qty": str(qty), "filled_avg_price": "3.77"},
        ],
    }


class ReconcileCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "r.db"
        self.settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{db}",
        })
        self.engine = build_engine(self.settings)
        create_schema(self.engine)
        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")],
                     self.settings, create=False)
        with Session(self.engine) as session:
            self.decision_id = session.scalars(select(Decision)).first().id
        self.store = LifecycleStore(self.engine)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def prepare(self, intent: OrderIntent | None = None) -> tuple[str, str, OrderIntent]:
        intent = intent or entry_intent()
        order_id, position_id = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=22),
            width=Decimal("5.00"), max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("631.63"), Direction.BULLISH, "daily_close"),
            now=NOW,
        )
        return order_id, position_id, intent

    def incidents(self) -> list[Incident]:
        with Session(self.engine) as session:
            return list(session.scalars(select(Incident)).all())


class StartupRecoveryTests(ReconcileCase):
    def test_a_pending_entry_that_filled_while_we_were_down_becomes_open(self) -> None:
        # EXIT-002: the crash-during-submit case.
        _, position_id, intent = self.prepare()
        broker = FakeBroker(
            positions=[{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}],
            by_client_id={intent.client_order_id: filled_order(intent.client_order_id)},
        )
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.OPEN)
        self.assertEqual(managed.avg_entry_debit, Decimal("3.13"))
        self.assertTrue(report.clean, report.mismatches)
        self.assertIs(report.execution_state, ExecutionState.NORMAL)

    def test_a_pending_entry_that_was_canceled_becomes_abandoned(self) -> None:
        _, position_id, intent = self.prepare()
        broker = FakeBroker(by_client_id={
            intent.client_order_id: {
                "client_order_id": intent.client_order_id, "id": "brk-1",
                "status": "canceled", "filled_qty": "0", "filled_avg_price": None,
            }
        })
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.ABANDONED)
        self.assertTrue(report.clean)

    def test_a_submitted_entry_the_broker_cannot_find_raises_an_incident(self) -> None:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status=None, ambiguous=True, now=NOW)
        report = Reconciler(FakeBroker(), self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertEqual([i.kind for i in self.incidents()], ["ambiguous_entry"])


class MismatchTests(ReconcileCase):
    def open_position(self) -> tuple[str, OrderIntent]:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("3.13"), now=NOW,
        )
        self.store.apply_entry_outcome(position_id, state=OrderState.FILLED,
                                       filled_quantity=1, avg_debit=Decimal("3.13"), now=NOW)
        return position_id, intent

    def test_an_open_position_the_broker_does_not_hold_halts_new_risk(self) -> None:
        position_id, _ = self.open_position()
        report = Reconciler(FakeBroker(positions=[]), self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertIn("position_vanished", [i.kind for i in self.incidents()])
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.INCIDENT)

    def test_broker_exposure_nobody_owns_halts_new_risk(self) -> None:
        broker = FakeBroker(positions=[{"symbol": "SPY260918P00600000", "qty": "-1"}])
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertEqual(report.unexpected_symbols, ["SPY260918P00600000"])
        self.assertIn("unexpected_exposure", [i.kind for i in self.incidents()])

    def test_an_unreachable_broker_halts_new_risk_rather_than_assuming_flat(self) -> None:
        broker = FakeBroker(raises=ConnectionError("network down"))
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertTrue(report.broker_unreachable)
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertIn("broker_unreachable", [i.kind for i in self.incidents()])

    def test_an_unresolved_incident_keeps_new_risk_halted_on_later_passes(self) -> None:
        self.open_position()
        store, broker = self.store, FakeBroker(positions=[])
        Reconciler(broker, store).reconcile(now=NOW)
        second = Reconciler(broker, store).reconcile(now=NOW)
        self.assertIs(second.execution_state, ExecutionState.NO_NEW_RISK)


class CloseReconciliationTests(ReconcileCase):
    def closing(self) -> tuple[str, OrderIntent]:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(order_id, broker_status="filled",
                                              filled_quantity=1,
                                              filled_avg_price=Decimal("3.13"), now=NOW)
        self.store.apply_entry_outcome(position_id, state=OrderState.FILLED,
                                       filled_quantity=1, avg_debit=Decimal("3.13"), now=NOW)
        closing = build_close_intent(intent, approval_reference="exit:stop",
                                     limit_price=Decimal("2.80"), now=NOW)
        self.store.prepare_close(position_id=position_id, decision_id=self.decision_id,
                                 intent=closing,
                                 request=prepare_mleg_request(closing, now=NOW),
                                 reason="stop_loss", now=NOW)
        return position_id, closing

    def test_a_close_only_completes_when_the_broker_is_flat(self) -> None:
        position_id, closing = self.closing()
        still_held = FakeBroker(
            positions=[{"symbol": LONG, "qty": "1"}],
            by_client_id={closing.client_order_id: filled_order(
                closing.client_order_id, status="new")},
        )
        Reconciler(still_held, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.CLOSING, "must not report flat early")

        flat = FakeBroker(positions=[], by_client_id={
            closing.client_order_id: filled_order(closing.client_order_id)})
        Reconciler(flat, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.CLOSED)

    def test_a_closed_position_leaves_the_active_set(self) -> None:
        position_id, closing = self.closing()
        flat = FakeBroker(positions=[], by_client_id={
            closing.client_order_id: filled_order(closing.client_order_id)})
        Reconciler(flat, self.store).reconcile(now=NOW)
        self.assertEqual(self.store.active_positions(), [])
        self.assertIsNotNone(self.store.get_position(position_id))


class NoWorkTests(ReconcileCase):
    def test_nothing_to_reconcile_is_clean_and_permits_new_risk(self) -> None:
        report = Reconciler(FakeBroker(), self.store).reconcile(now=NOW)
        self.assertTrue(report.clean)
        self.assertIs(report.execution_state, ExecutionState.NORMAL)
        self.assertEqual(report.summary(), "nothing to reconcile")

    def test_reconciliation_never_submits(self) -> None:
        self.prepare()
        # FakeBroker.submit raises if called.
        Reconciler(FakeBroker(), self.store).reconcile(now=NOW)




class IncidentHealingTests(ReconcileCase):
    """Reconciliation exists to heal an incident once the facts are known."""

    def test_an_ambiguous_entry_resolves_once_the_order_is_found(self) -> None:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status=None, ambiguous=True, now=NOW)
        self.store.open_incident(kind="ambiguous_entry_submission",
                                 detail="outcome unknown", position_id=position_id, now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.INCIDENT)

        # The order turns out to have filled after all.
        broker = FakeBroker(
            positions=[{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}],
            by_client_id={intent.client_order_id: filled_order(intent.client_order_id)},
        )
        Reconciler(broker, self.store).reconcile(now=NOW)
        healed = self.store.get_position(position_id)
        assert healed is not None
        self.assertIs(healed.state, PositionState.OPEN)
        self.assertEqual(healed.avg_entry_debit, Decimal("3.13"))

    def test_an_ambiguous_entry_that_never_existed_resolves_to_abandoned(self) -> None:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status=None, ambiguous=True, now=NOW)
        self.store.open_incident(kind="ambiguous_entry_submission",
                                 detail="outcome unknown", position_id=position_id, now=NOW)
        broker = FakeBroker(by_client_id={
            intent.client_order_id: {
                "client_order_id": intent.client_order_id, "id": "brk-1",
                "status": "rejected", "filled_qty": "0", "filled_avg_price": None,
            }
        })
        Reconciler(broker, self.store).reconcile(now=NOW)
        healed = self.store.get_position(position_id)
        assert healed is not None
        self.assertIs(healed.state, PositionState.ABANDONED)


if __name__ == "__main__":
    unittest.main()
