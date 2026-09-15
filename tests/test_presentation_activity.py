"""Regression tests for the durable activity trail.

The interesting assertion is the gap check. `audit_events.sequence` is
contiguous by construction, so a missing number means an event that should have
been recorded was not — and a trail rendered without checking looks equally
complete either way. That is the same defect as a status strip that cannot be
wrong, applied to the audit trail, which is the one place it would matter most.

The committed evidence has no gaps, so the failure is constructed here. A test
that only ever sees a healthy trail proves nothing about the unhealthy one.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from options_alpha_lab.persistence.models import (
    AuditEvent,
    Base,
    Decision,
    Run,
    WorkerEvent,
)
from options_alpha_lab.presentation import activity

DB = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"
NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)


class CommittedEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(create_engine(f"sqlite+pysqlite:///{DB}", future=True))

    def tearDown(self) -> None:
        self.session.close()

    def _decision(self, snapshot_id: str) -> Decision:
        return self.session.scalars(
            select(Decision).where(Decision.snapshot_id == snapshot_id)
        ).one()

    def test_every_committed_trail_is_complete(self) -> None:
        for decision in self.session.scalars(select(Decision)).all():
            trail = activity.for_decision(self.session, decision)
            self.assertTrue(
                trail.complete,
                f"{decision.snapshot_id} is missing sequence {trail.gaps}",
            )

    def test_a_trail_is_scoped_to_its_own_decision(self) -> None:
        """26 events exist; a decision must see only its own."""
        trail = activity.for_decision(
            self.session, self._decision("spy-refusal-2026-08-27")
        )
        self.assertTrue(trail.events)
        self.assertEqual(
            {event.correlation_id for event in trail.events},
            {"spy-refusal-2026-08-27"},
            "an event from another decision leaked into the trail",
        )
        self.assertLess(len(trail.events), len(activity.recent(self.session)))

    def test_events_are_ordered_by_sequence(self) -> None:
        trail = activity.for_decision(
            self.session, self._decision("spy-qualified-2026-08-27")
        )
        sequences = [event.sequence for event in trail.events]
        self.assertEqual(sequences, sorted(sequences))

    def test_the_refusal_stops_early(self) -> None:
        """A refusal's trail is short because the pipeline stopped, not truncated."""
        refusal = activity.for_decision(
            self.session, self._decision("spy-refusal-2026-08-27")
        )
        qualified = activity.for_decision(
            self.session, self._decision("spy-qualified-2026-08-27")
        )
        self.assertLess(len(refusal.events), len(qualified.events))
        self.assertTrue(refusal.complete, "short is not the same as incomplete")
        self.assertEqual(refusal.final_outcome, "NO_TRADE")

    def test_the_system_feed_returns_events(self) -> None:
        self.assertTrue(activity.recent(self.session))

    def test_the_system_feed_respects_its_limit(self) -> None:
        self.assertEqual(len(activity.recent(self.session, limit=3)), 3)


class GapDetectionTests(unittest.TestCase):
    """The committed evidence has no gaps, so build one."""

    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.session.add(
            Run(
                id="r",
                runtime_version="t",
                policy_version="t",
                bot_mode="recommend",
                trading_enabled=False,
                started_at=NOW,
            )
        )
        self.decision = Decision(
            id="d",
            run_id="r",
            market_snapshot_id="s",
            snapshot_id="spy-gap",
            action="OPTIONS_POSITION",
            direction="bullish",
            reason_codes=[],
            transitions=[],
            input_hash="ih",
            decision_hash="dh",
            policy_version="t",
            decided_at=NOW,
        )
        self.session.add(self.decision)

    def tearDown(self) -> None:
        self.session.close()

    def _events(self, sequences: list[int]) -> None:
        for n in sequences:
            self.session.add(
                AuditEvent(
                    id=f"e{n}",
                    run_id="r",
                    correlation_id="spy-gap",
                    sequence=n,
                    component="c",
                    stage=f"S{n}",
                    outcome="accepted",
                    reason_codes=[],
                    occurred_at=NOW + timedelta(seconds=n),
                )
            )
        self.session.commit()

    def test_a_missing_sequence_is_reported(self) -> None:
        self._events([0, 1, 3, 4])
        trail = activity.for_decision(self.session, self.decision)
        self.assertFalse(trail.complete)
        self.assertEqual(trail.gaps, (2,))

    def test_several_missing_sequences_are_all_reported(self) -> None:
        self._events([0, 4])
        trail = activity.for_decision(self.session, self.decision)
        self.assertEqual(trail.gaps, (1, 2, 3))

    def test_a_contiguous_trail_has_no_gaps(self) -> None:
        self._events([0, 1, 2, 3])
        self.assertTrue(activity.for_decision(self.session, self.decision).complete)

    def test_a_trail_not_starting_at_zero_is_not_a_false_alarm(self) -> None:
        """We have no evidence such a trail was ever longer, so do not claim it."""
        self._events([3, 4, 5])
        trail = activity.for_decision(self.session, self.decision)
        self.assertTrue(trail.complete)
        self.assertEqual(trail.gaps, ())

    def test_a_single_event_is_not_a_gap(self) -> None:
        self._events([7])
        self.assertTrue(activity.for_decision(self.session, self.decision).complete)

    def test_an_empty_trail_is_not_a_gap(self) -> None:
        trail = activity.for_decision(self.session, self.decision)
        self.assertEqual(trail.events, ())
        self.assertTrue(trail.complete)
        self.assertIsNone(trail.final_outcome)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class WorkerEventTests(unittest.TestCase):
    """`CIIP-I-008`: worker lifecycle must be durable, not only in the journal."""

    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.session.add(
            Run(
                id="r",
                runtime_version="t",
                policy_version="t",
                bot_mode="observe",
                trading_enabled=False,
                started_at=NOW,
            )
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def _event(self, event: str, kind: str, offset: int, **detail: object) -> None:
        self.session.add(
            WorkerEvent(
                id=f"w{offset}",
                run_id="r",
                kind=kind,
                event=event,
                detail=detail,
                occurred_at=NOW + timedelta(seconds=offset),
            )
        )
        self.session.commit()

    def test_an_empty_table_is_not_an_error(self) -> None:
        self.assertEqual(activity.worker_events(self.session), ())

    def test_events_come_back_newest_first(self) -> None:
        self._event("worker_started", "state", 0)
        self._event("startup_reconcile", "state", 1)
        self._event("worker_stopped", "state", 2)
        names = [e.event for e in activity.worker_events(self.session)]
        self.assertEqual(names, ["worker_stopped", "startup_reconcile", "worker_started"])

    def test_detail_survives_the_round_trip(self) -> None:
        self._event("worker_started", "state", 0, mode="observe", writes="disabled")
        (event,) = activity.worker_events(self.session)
        self.assertEqual(event.detail["mode"], "observe")
        self.assertEqual(event.detail["writes"], "disabled")

    def test_faults_are_selectable_without_parsing_prose(self) -> None:
        """The reason `kind` is a column rather than something inferred."""
        self._event("worker_started", "state", 0)
        self._event("tick_failed", "fault", 1, error="ProviderError: boom")
        self._event("worker_stopped", "state", 2)
        faults = activity.worker_faults(self.session)
        self.assertEqual([f.event for f in faults], ["tick_failed"])
        self.assertTrue(faults[0].is_fault)

    def test_a_state_event_is_not_a_fault(self) -> None:
        self._event("worker_started", "state", 0)
        (event,) = activity.worker_events(self.session)
        self.assertFalse(event.is_fault)

    def test_the_limit_is_respected(self) -> None:
        for n in range(6):
            self._event("tick_failed", "fault", n, error=str(n))
        self.assertEqual(len(activity.worker_events(self.session, limit=2)), 2)
        self.assertEqual(len(activity.worker_faults(self.session, limit=3)), 3)


class RecorderDurabilityTests(unittest.TestCase):
    """Recording must never be able to kill the single writer."""

    def test_a_failed_write_is_reported_not_raised(self) -> None:
        """A telemetry failure taking down a worker holding a position would be
        far worse than a missing row — but it must still be visible."""
        import io
        from contextlib import redirect_stderr

        from options_alpha_lab.persistence.repository import DecisionRecorder

        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)

        class _Settings:
            schema_version = "h0.1"

        recorder = DecisionRecorder.__new__(DecisionRecorder)
        recorder._engine = engine  # type: ignore[attr-defined]
        recorder._settings = _Settings()  # type: ignore[attr-defined]
        recorder._sessions = None  # type: ignore[attr-defined]

        err = io.StringIO()
        with redirect_stderr(err):
            # The session factory is absent, so the write raises inside the
            # recorder. The specific failure does not matter; what matters is
            # that no failure reaches the caller, and that it is still visible.
            recorder.record_worker_event("absent-run", event="worker_started")
        reported = err.getvalue()
        self.assertIn("worker_event_not_recorded", reported)
        self.assertIn("worker_started", reported, "the dropped event must be named")
        self.assertIn('"kind": "fault"', reported)
