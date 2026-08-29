"""Item 7: exactly one writer, and a restart that resumes rather than forgets."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from options_alpha_lab.config import load_settings
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.worker import (
    LEASE_TTL,
    LeaseManager,
    LeaseUnavailable,
    WorkerHealth,
)

NOW = datetime(2026, 8, 29, 13, 30, tzinfo=UTC)


class LeaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "w.db"
        self.settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{db}",
        })
        self.engine = build_engine(self.settings)
        create_schema(self.engine)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class SingleWriterTests(LeaseCase):
    def test_the_first_worker_acquires_the_lease(self) -> None:
        info = LeaseManager(self.engine).acquire(now=NOW)
        self.assertEqual(info.expires_at, NOW + LEASE_TTL)

    def test_a_second_worker_is_refused_while_the_lease_is_live(self) -> None:
        # Two workers reconciling the same position would fight, and both
        # could submit.
        LeaseManager(self.engine).acquire(now=NOW)
        with self.assertRaises(LeaseUnavailable) as ctx:
            LeaseManager(self.engine).acquire(now=NOW + timedelta(seconds=10))
        self.assertIn("held by", str(ctx.exception))

    def test_an_expired_lease_is_taken_over(self) -> None:
        # A worker that died without releasing must not block its replacement.
        LeaseManager(self.engine).acquire(now=NOW)
        second = LeaseManager(self.engine)
        info = second.acquire(now=NOW + LEASE_TTL + timedelta(seconds=1))
        self.assertEqual(info.owner, second.owner)

    def test_a_released_lease_is_immediately_available(self) -> None:
        first = LeaseManager(self.engine)
        first.acquire(now=NOW)
        first.release(now=NOW + timedelta(seconds=5))
        LeaseManager(self.engine).acquire(now=NOW + timedelta(seconds=6))

    def test_the_same_worker_may_reacquire_its_own_lease(self) -> None:
        manager = LeaseManager(self.engine)
        manager.acquire(now=NOW)
        manager.acquire(now=NOW + timedelta(seconds=5))


class HeartbeatTests(LeaseCase):
    def test_a_heartbeat_extends_the_lease(self) -> None:
        manager = LeaseManager(self.engine)
        manager.acquire(now=NOW)
        later = NOW + timedelta(seconds=30)
        self.assertTrue(manager.heartbeat(now=later))
        current = manager.current()
        assert current is not None
        self.assertEqual(current.expires_at, later + LEASE_TTL)

    def test_a_lost_lease_reports_false_so_work_can_stop(self) -> None:
        first = LeaseManager(self.engine)
        first.acquire(now=NOW)
        # A second worker takes over after the TTL lapses.
        LeaseManager(self.engine).acquire(now=NOW + LEASE_TTL + timedelta(seconds=1))
        self.assertFalse(first.heartbeat(now=NOW + LEASE_TTL + timedelta(seconds=2)))

    def test_releasing_a_lease_we_no_longer_own_is_a_no_op(self) -> None:
        first = LeaseManager(self.engine)
        first.acquire(now=NOW)
        second = LeaseManager(self.engine)
        second.acquire(now=NOW + LEASE_TTL + timedelta(seconds=1))
        first.release(now=NOW + LEASE_TTL + timedelta(seconds=2))
        # The second worker still holds it.
        current = second.current()
        assert current is not None
        self.assertEqual(current.owner, second.owner)


class HealthTests(unittest.TestCase):
    def test_health_is_written_as_readable_json(self) -> None:
        health = WorkerHealth(started_at=NOW, ticks=3, last_action="POSITION_HELD")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "health.json"
            health.write(str(path))
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["ticks"], 3)
        self.assertTrue(payload["healthy"])

    def test_a_lost_lease_is_reported_unhealthy(self) -> None:
        health = WorkerHealth(started_at=NOW, lease_lost=True)
        self.assertFalse(health.as_dict()["healthy"])

    def test_an_error_is_reported_unhealthy(self) -> None:
        health = WorkerHealth(started_at=NOW, last_error="boom")
        self.assertFalse(health.as_dict()["healthy"])


class RestartRecoveryTests(LeaseCase):
    def test_a_restart_resumes_the_same_position(self) -> None:
        # EXIT-AC-04: nothing lives in process memory, so a new process finds the
        # position the previous one was managing.
        from decimal import Decimal

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from options_alpha_lab.architecture.contracts import Direction, SpreadStrategy
        from options_alpha_lab.execution.intent import IntentLeg, OrderIntent
        from options_alpha_lab.execution.lifecycle import (
            LifecycleStore,
            OrderState,
            PositionState,
            TypedInvalidation,
        )
        from options_alpha_lab.execution.request import prepare_mleg_request
        from options_alpha_lab.persistence.models import Decision
        from options_alpha_lab.replay import replay_paths

        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")],
                     self.settings, create=False)
        with Session(self.engine) as session:
            decision_id = session.scalars(select(Decision)).first().id

        store = LifecycleStore(self.engine)
        intent = OrderIntent(
            decision_hash="sha256:x", strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
            legs=(IntentLeg("SPY260918C00640000", 1, "buy", "buy_to_open"),
                  IntentLeg("SPY260918C00645000", 1, "sell", "sell_to_open")),
            strategy_quantity=1, limit_price=Decimal("3.39"),
            approval_reference="risk", created_at=NOW,
            expires_at=NOW + timedelta(seconds=90),
        )
        order_id, position_id = store.prepare_entry(
            decision_id=decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW), direction=Direction.BULLISH,
            long_symbol="SPY260918C00640000", short_symbol="SPY260918C00645000",
            expiration=NOW + timedelta(days=22), width=Decimal("5.00"),
            max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("631.63"), Direction.BULLISH, "close"),
            now=NOW,
        )
        store.record_submission(order_id, broker_order_id="brk-1",
                                broker_status="accepted", now=NOW)
        store.apply_order_reconciliation(order_id, broker_status="filled",
                                         filled_quantity=1,
                                         filled_avg_price=Decimal("3.13"), now=NOW)
        store.apply_entry_outcome(position_id, state=OrderState.FILLED,
                                  filled_quantity=1, avg_debit=Decimal("3.13"), now=NOW)

        # A completely new process: fresh engine, fresh store, no shared memory.
        restarted = LifecycleStore(build_engine(self.settings))
        recovered = restarted.active_positions()
        self.assertEqual(len(recovered), 1)
        self.assertIs(recovered[0].state, PositionState.OPEN)
        self.assertEqual(recovered[0].avg_entry_debit, Decimal("3.13"))
        self.assertEqual(recovered[0].position_id, position_id)


if __name__ == "__main__":
    unittest.main()
