"""Positions in every lifecycle state, built with the lifecycle store itself.

Shared by the positions and review API suites (`PUI4`). Each state is reached
through the calls the worker makes - prepare, submit, reconcile, close,
abandon - never by writing a row that says so. Nothing here is a test.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.api.server import create_app
from options_alpha_lab.execution.intent import build_close_intent
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import Decision
from options_alpha_lab.presentation.source import Source
from options_alpha_lab.replay import replay_paths
from reconcile_support import NOW, ReconcileCase, entry_intent

#: `NOW` is Friday 28 August 2026, 11:30 in New York: the session is open.
AFTER_CLOSE = NOW + timedelta(hours=6)
MONDAY_OPEN = NOW + timedelta(days=3)


class PositionsCase(ReconcileCase):
    def setUp(self) -> None:
        super().setUp()
        # A second decision, so the closed round trip has fills of its own.
        replay_paths([Path("fixtures/h0/spy_bearish_qualified.snapshot.json")],
                     self.settings, create=False)
        with Session(self.engine) as session:
            ids = [d.id for d in session.scalars(select(Decision)).all()]
        self.other_decision = next(i for i in ids if i != self.decision_id)
        self._n = 0

    def client(self, now: datetime = NOW) -> TestClient:
        return TestClient(create_app(
            Source(self.engine, "LIVE", "test", "live"), clock=lambda: now
        ))

    def intent(self) -> Any:
        self._n += 1
        return entry_intent(decision_hash=f"sha256:{self._n:064d}")

    def pending(self) -> str:
        _, position_id, _ = self.prepare(self.intent())
        return position_id

    def opened(self) -> tuple[str, Any]:
        self._n += 1
        return self.open_position(self.intent(), broker_order_id=f"brk-{self._n}")

    def mark(self, position_id: str, at: datetime, value: str | None = "3.40") -> str:
        return self.store.record_observation(
            position_id=position_id, observed_at=at, source_time=at - timedelta(seconds=2),
            underlying_price=Decimal("640.10"), underlying_source="completed_daily_close",
            dte=21, sessions_elapsed=1, quantity=1, policy_version="h0-provisional-1",
            long_bid=None if value is None else Decimal("7.10"),
            short_ask=None if value is None else Decimal("3.70"),
            spread_value=None if value is None else Decimal(value),
            data_quality=[] if value is not None else ["long_leg_no_bid"],
        )

    def hold(self, position_id: str, observation_id: str, unrealized: str | None) -> None:
        self.store.record_exit_decision(
            position_id=position_id, observation_id=observation_id, trigger="none",
            should_close=False, reason="no trigger met",
            evaluated=[{"trigger": "stop_loss", "met": False}], precedence=["stop_loss"],
            disposition="held", policy_version="h0-provisional-1", decided_at=NOW,
            unrealized=None if unrealized is None else Decimal(unrealized),
            value_unmeasurable=unrealized is None,
        )

    def closing(self, position_id: str, intent: Any, decision_id: str | None = None) -> str:
        close = build_close_intent(intent, approval_reference="exit:stop",
                                   limit_price=Decimal("2.80"), now=NOW)
        return self.store.prepare_close(
            position_id=position_id, decision_id=decision_id or self.decision_id, intent=close,
            request=prepare_mleg_request(close, now=NOW), reason="stop_loss", now=NOW,
        )

    def closed(self) -> str:
        """A whole round trip on its own decision: entry 3.13, close 2.80."""
        first, self.decision_id = self.decision_id, self.other_decision
        try:
            position_id, intent = self.opened()
            order_id = self.closing(position_id, intent, self.other_decision)
        finally:
            self.decision_id = first
        self.store.record_submission(order_id, broker_order_id="brk-close",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("2.80"), now=NOW,
        )
        self.store.apply_close_outcome(position_id, broker_flat=True, remaining_quantity=0,
                                       now=NOW)
        return position_id

    def get(self, position_id: str, now: datetime = NOW) -> dict[str, Any]:
        body = self.client(now).get(f"/api/v1/positions/{position_id}").json()
        data: dict[str, Any] = body["data"]
        return data

    def summary(self, position_id: str, now: datetime = NOW) -> dict[str, Any]:
        position: dict[str, Any] = self.get(position_id, now)["position"]
        return position
