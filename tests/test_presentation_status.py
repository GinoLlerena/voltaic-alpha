"""Regression tests for `CIIP-CV-001`: the safety strip must not lie.

The defect these lock down is subtle. The old strip rendered `Order writes:
Disabled` and `Live endpoint: None` as string constants, so it displayed the
same reassuring green cells over a live worker database, a committed fixture,
and an empty schema alike. Nothing could ever falsify it, which is precisely
what disqualifies it as evidence.

So the tests here are mostly about the *absence* of a comfortable default: an
empty database must say `UNKNOWN`, and a worker whose lease expired must not be
indistinguishable from one that is alive.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab.persistence.models import Base, Incident, Position, Run, WorkerLease
from options_alpha_lab.presentation.status import UNKNOWN, StatusItem, system_status

NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _by_label(items: list[StatusItem], label: str) -> StatusItem:
    return next(i for i in items if i.label == label)


class EmptyDatabaseTests(unittest.TestCase):
    """Nothing recorded means nothing known. It must not mean 'safe'."""

    def setUp(self) -> None:
        self.session = _session()
        self.items = system_status(self.session, now=NOW)

    def tearDown(self) -> None:
        self.session.close()

    def test_order_writes_is_unknown_not_disabled(self) -> None:
        item = _by_label(self.items, "Order writes")
        self.assertEqual(item.value, UNKNOWN)
        self.assertFalse(item.known)
        self.assertEqual(item.tone, "unknown")

    def test_worker_is_unknown_not_absent(self) -> None:
        self.assertEqual(_by_label(self.items, "Worker").value, UNKNOWN)

    def test_every_unknown_states_a_reason(self) -> None:
        for item in self.items:
            if not item.known:
                self.assertTrue(item.reason, f"{item.label} is UNKNOWN without a reason")

    def test_no_cell_claims_a_safe_default(self) -> None:
        # The exact strings the old hardcoded strip used.
        for item in self.items:
            if item.label in {"Order writes", "Worker mode", "Worker"}:
                self.assertNotIn(item.value, {"Disabled", "Required", "None"})

    def test_every_item_declares_provenance(self) -> None:
        for item in self.items:
            self.assertTrue(item.source, f"{item.label} has no source")


class RecordedRuntimeTests(unittest.TestCase):
    """With records present, the strip must report what they actually say."""

    def setUp(self) -> None:
        self.session = _session()

    def tearDown(self) -> None:
        self.session.close()

    def _run(self, *, enabled: bool, mode: str) -> None:
        self.session.add(
            Run(
                id="run-1",
                runtime_version="test",
                policy_version="test",
                bot_mode=mode,
                trading_enabled=enabled,
                started_at=NOW - timedelta(minutes=5),
            )
        )
        self.session.commit()

    def _lease(self, *, expires: datetime, released: datetime | None = None) -> None:
        self.session.add(
            WorkerLease(
                name="worker",
                owner="owner-1",
                host="host-1",
                acquired_at=NOW - timedelta(minutes=10),
                heartbeat_at=NOW - timedelta(seconds=30),
                expires_at=expires,
                released_at=released,
            )
        )
        self.session.commit()

    def test_trading_enabled_reads_enabled_and_warns(self) -> None:
        self._run(enabled=True, mode="paper_execute")
        item = _by_label(system_status(self.session, now=NOW), "Order writes")
        self.assertEqual(item.value, "Enabled")
        self.assertEqual(item.tone, "warn")
        self.assertEqual(item.source, "runs.trading_enabled")
        self.assertIsNotNone(item.observed_at)

    def test_trading_disabled_reads_disabled(self) -> None:
        self._run(enabled=False, mode="recommend")
        self.assertEqual(
            _by_label(system_status(self.session, now=NOW), "Order writes").value,
            "Disabled",
        )

    def test_live_lease_is_distinguishable_from_stale(self) -> None:
        self._lease(expires=NOW + timedelta(minutes=1))
        live = _by_label(system_status(self.session, now=NOW), "Worker")
        self.assertTrue(live.value.startswith("Live"))
        self.assertEqual(live.tone, "ok")

    def test_expired_lease_is_reported_bad_not_live(self) -> None:
        self._lease(expires=NOW - timedelta(minutes=1))
        stale = _by_label(system_status(self.session, now=NOW), "Worker")
        self.assertTrue(stale.value.startswith("Stale"))
        self.assertEqual(stale.tone, "bad")

    def test_released_lease_reads_released(self) -> None:
        self._lease(expires=NOW + timedelta(minutes=1), released=NOW)
        self.assertEqual(
            _by_label(system_status(self.session, now=NOW), "Worker").value, "Released"
        )

    def test_open_position_and_incident_counts_are_derived(self) -> None:
        self.session.add(
            Position(
                id="pos-1",
                decision_id="dec-1",
                entry_order_id="ord-1",
                strategy="bull_call_debit_spread",
                direction="bullish",
                lifecycle_status="OPEN",
                long_symbol="SPY260911C00772000",
                short_symbol="SPY260911C00778000",
                expiration=NOW + timedelta(days=12),
                width=6,
                requested_quantity=1,
                open_risk=339,
            )
        )
        self.session.add(
            Incident(
                id="inc-1",
                kind="test",
                severity="warning",
                detail="open",
                execution_state="NORMAL",
                opened_at=NOW,
            )
        )
        self.session.commit()
        items = system_status(self.session, now=NOW)
        self.assertEqual(_by_label(items, "Open positions").value, "1")
        self.assertEqual(_by_label(items, "Open incidents").value, "1")
        self.assertEqual(_by_label(items, "Open incidents").tone, "bad")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
