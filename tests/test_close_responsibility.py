"""Item 5: responsibility is retained until the broker confirms flat (EXIT-001, EXIT-006)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import Direction, PriceSource, SpreadStrategy
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
from options_alpha_lab.persistence.models import Decision
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.replay import replay_paths

NOW = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)
LONG, SHORT = "SPY260918C00640000", "SPY260918C00645000"


def entry_intent() -> OrderIntent:
    return OrderIntent(
        decision_hash="sha256:x", strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        legs=(IntentLeg(LONG, 1, "buy", "buy_to_open"),
              IntentLeg(SHORT, 1, "sell", "sell_to_open")),
        strategy_quantity=1, limit_price=Decimal("3.39"),
        approval_reference="risk", created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )


class Broker(BrokerPort):
    def __init__(self, *, positions: list[dict[str, Any]] | None = None,
                 by_client_id: dict[str, dict[str, Any]] | None = None) -> None:
        self._positions = positions or []
        self._by_client_id = by_client_id or {}

    def resolved_endpoint(self) -> str:
        return "https://paper-api.alpaca.markets"

    def open_strategy_count(self) -> int:
        return len(self._positions)

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("reconciliation must never submit")

    def get_by_client_order_id(self, cid: str) -> dict[str, Any] | None:
        return self._by_client_id.get(cid)

    def list_open_orders(self) -> list[dict[str, Any]]:
        return []

    def list_positions(self) -> list[dict[str, Any]]:
        return self._positions

    def cancel_order(self, broker_order_id: str) -> None:
        return None


class CloseCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "c.db"
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
        self.position_id, self.close_intent = self.closing()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def closing(self) -> tuple[str, OrderIntent]:
        intent = entry_intent()
        order_id, position_id = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=22),
            width=Decimal("5.00"), max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("631.63"), Direction.BULLISH,
                                        PriceSource.COMPLETED_DAILY_CLOSE),
            now=NOW,
        )
        self.store.record_submission(order_id, broker_order_id="brk-entry",
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

    def state(self) -> PositionState:
        managed = self.store.get_position(self.position_id)
        assert managed is not None
        return managed.state

    def kinds(self) -> list[str]:
        return [i.kind for i in self.store.open_incidents()]


class RetainedResponsibilityTests(CloseCase):
    def test_a_working_close_keeps_the_position_owned(self) -> None:
        broker = Broker(positions=[{"symbol": LONG, "qty": "1"}],
                        by_client_id={self.close_intent.client_order_id: {
                            "client_order_id": self.close_intent.client_order_id,
                            "status": "new", "filled_qty": "0", "filled_avg_price": None}})
        Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertIs(self.state(), PositionState.CLOSING)
        self.assertIn(self.position_id,
                      [p.position_id for p in self.store.active_positions()])

    def test_only_a_flat_broker_closes_the_position(self) -> None:
        broker = Broker(positions=[], by_client_id={
            self.close_intent.client_order_id: {
                "client_order_id": self.close_intent.client_order_id,
                "status": "filled", "filled_qty": "1", "filled_avg_price": "3.06"}})
        Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertIs(self.state(), PositionState.CLOSED)
        self.assertEqual(self.store.active_positions(), [])

    def test_a_partially_filled_close_keeps_the_remainder_owned(self) -> None:
        broker = Broker(positions=[{"symbol": LONG, "qty": "1"}],
                        by_client_id={self.close_intent.client_order_id: {
                            "client_order_id": self.close_intent.client_order_id,
                            "status": "partially_filled", "filled_qty": "1",
                            "filled_avg_price": "3.06"}})
        Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertIs(self.state(), PositionState.CLOSING)


class FailedCloseTests(CloseCase):
    def test_a_canceled_close_returns_the_position_to_open_for_another_attempt(self) -> None:
        # Leaving it CLOSING forever would make it permanently unclosable, which
        # is trapped exposure wearing a different label.
        broker = Broker(positions=[{"symbol": LONG, "qty": "1"}],
                        by_client_id={self.close_intent.client_order_id: {
                            "client_order_id": self.close_intent.client_order_id,
                            "status": "canceled", "filled_qty": "0",
                            "filled_avg_price": None}})
        Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertIs(self.state(), PositionState.OPEN)
        self.assertIn("close_did_not_flatten", self.kinds())

    def test_a_rejected_close_also_returns_the_position_to_open(self) -> None:
        broker = Broker(positions=[{"symbol": SHORT, "qty": "-1"}],
                        by_client_id={self.close_intent.client_order_id: {
                            "client_order_id": self.close_intent.client_order_id,
                            "status": "rejected", "filled_qty": "0",
                            "filled_avg_price": None}})
        Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertIs(self.state(), PositionState.OPEN)

    def test_a_released_close_clears_the_close_order_link(self) -> None:
        broker = Broker(positions=[{"symbol": LONG, "qty": "1"}],
                        by_client_id={self.close_intent.client_order_id: {
                            "client_order_id": self.close_intent.client_order_id,
                            "status": "expired", "filled_qty": "0",
                            "filled_avg_price": None}})
        Reconciler(broker, self.store).reconcile(now=NOW)
        managed = self.store.get_position(self.position_id)
        assert managed is not None
        self.assertIsNone(managed.close_order_id, "a fresh close may be prepared")

    def test_release_is_a_no_op_on_a_position_that_is_not_closing(self) -> None:
        self.store.release_close(self.position_id, reason="canceled", now=NOW)
        again = self.store.release_close(self.position_id, reason="canceled", now=NOW)
        self.assertIs(again, PositionState.OPEN)


if __name__ == "__main__":
    unittest.main()
