"""Shared builders for suites that exercise reconciliation.

`CSA-010`: these lived in `test_reconcile.py` and were imported from it by the
agent and acceptance suites. Nothing here is a test.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import (
    Direction,
    PriceSource,
    SpreadStrategy,
)
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.gateway import BrokerPort
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent
from options_alpha_lab.execution.lifecycle import (
    LifecycleStore,
    OrderState,
    TypedInvalidation,
)
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import Decision, Incident
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.replay import replay_paths
from pgsupport import database_url

NOW = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)
LONG, SHORT = "SPY260918C00640000", "SPY260918C00645000"


def entry_intent(qty: int = 1, decision_hash: str = "sha256:x") -> OrderIntent:
    return OrderIntent(
        decision_hash=decision_hash, strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
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
            "DATABASE_URL": database_url(db),
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
            invalidation=TypedInvalidation(Decimal("631.63"), Direction.BULLISH,
                                        PriceSource.COMPLETED_DAILY_CLOSE),
            now=NOW,
        )
        return order_id, position_id, intent

    def open_position(
        self, intent: OrderIntent | None = None, broker_order_id: str = "brk-1"
    ) -> tuple[str, OrderIntent]:
        order_id, position_id, intent = self.prepare(intent)
        self.store.record_submission(order_id, broker_order_id=broker_order_id,
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("3.13"), now=NOW,
        )
        self.store.apply_entry_outcome(position_id, state=OrderState.FILLED,
                                       filled_quantity=1, avg_debit=Decimal("3.13"), now=NOW)
        return position_id, intent

    def incidents(self) -> list[Incident]:
        with Session(self.engine) as session:
            return list(session.scalars(select(Incident)).all())
