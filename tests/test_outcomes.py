"""`CIIP-008`: review jobs and decision outcomes.

The properties under test are the ones that make a later claim about the policy
worth anything: a refusal is reviewed on the same clock as a trade, a horizon is
resolved only from a completed close at or after it, enrichment never edits the
decision, and asking twice yields one answer rather than two.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from options_alpha_lab import outcomes
from options_alpha_lab.calendar import TradingCalendar
from options_alpha_lab.persistence.models import (
    Base,
    BrokerOrder,
    Decision,
    DecisionOutcomeRecord,
    MarketSnapshot,
    OrderIntent,
    ReviewJob,
    Run,
)

ET = ZoneInfo("America/New_York")
SESSIONS = [
    {"date": "2026-08-27", "open": "09:30", "close": "16:00"},
    {"date": "2026-08-28", "open": "09:30", "close": "16:00"},
    {"date": "2026-08-31", "open": "09:30", "close": "16:00"},
    {"date": "2026-09-01", "open": "09:30", "close": "16:00"},
    {"date": "2026-09-02", "open": "09:30", "close": "16:00"},
]


def et(day: str, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(
        datetime.fromisoformat(day).date(), time(hour, minute), tzinfo=ET
    ).astimezone(UTC)


class OutcomeCase(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.calendar = TradingCalendar.from_payload({"sessions": SESSIONS})
        self.session.add(
            Run(
                id="run",
                runtime_version="t",
                policy_version="h0",
                bot_mode="observe",
                trading_enabled=False,
                started_at=et("2026-08-27", 9),
            )
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def snapshot(self, snapshot_id: str, source_time: datetime, price: str) -> MarketSnapshot:
        row = MarketSnapshot(
            id=uuid.uuid4().hex,
            run_id="run",
            snapshot_id=snapshot_id,
            symbol="SPY",
            provider="test",
            feed="fixture",
            source_time=source_time,
            received_time=source_time,
            underlying_price=Decimal(price),
            payload_hash="sha256:snap",
            payload={},
            data_quality={},
        )
        self.session.add(row)
        self.session.commit()
        return row

    def decision(
        self,
        snapshot: MarketSnapshot,
        *,
        action: str = "NO_TRADE",
        direction: str = "neutral",
        decided_at: datetime | None = None,
    ) -> Decision:
        row = Decision(
            id=uuid.uuid4().hex,
            run_id="run",
            market_snapshot_id=snapshot.id,
            snapshot_id=snapshot.snapshot_id,
            action=action,
            direction=direction,
            reason_codes=[],
            transitions=[],
            input_hash="sha256:in",
            decision_hash=f"sha256:{uuid.uuid4().hex}",
            policy_version="h0",
            decided_at=decided_at or snapshot.source_time,
        )
        self.session.add(row)
        self.session.commit()
        return row


class HorizonParityTests(OutcomeCase):
    def test_a_refusal_gets_the_same_horizons_as_a_trade(self) -> None:
        """Reviewing only what traded measures the policy on the half it liked."""
        snap = self.snapshot("s1", et("2026-08-27", 16), "600")
        refusal = self.decision(snap)
        trade = self.decision(snap, action="OPTIONS_POSITION", direction="bullish")
        for row in (refusal, trade):
            outcomes.ensure_jobs(self.session, row)
        self.session.commit()
        for row in (refusal, trade):
            horizons = sorted(
                j.horizon
                for j in self.session.scalars(
                    select(ReviewJob).where(ReviewJob.decision_id == row.id)
                ).all()
            )
            self.assertEqual(horizons, [h.label for h in outcomes.HORIZONS])

    def test_jobs_are_created_once(self) -> None:
        snap = self.snapshot("s1", et("2026-08-27", 16), "600")
        decision = self.decision(snap)
        self.assertEqual(len(outcomes.ensure_jobs(self.session, decision)), len(outcomes.HORIZONS))
        self.session.commit()
        self.assertEqual(outcomes.ensure_jobs(self.session, decision), [])
        self.session.commit()
        jobs = self.session.scalars(select(ReviewJob)).all()
        self.assertEqual(len(jobs), len(outcomes.HORIZONS))

    def test_a_duplicate_horizon_is_refused_by_the_database(self) -> None:
        snap = self.snapshot("s1", et("2026-08-27", 16), "600")
        decision = self.decision(snap)
        outcomes.ensure_jobs(self.session, decision)
        self.session.commit()
        self.session.add(
            ReviewJob(
                id=uuid.uuid4().hex, decision_id=decision.id, horizon="T+1",
                horizon_sessions=1, state=outcomes.PENDING, policy_version="h0",
                decided_at=snap.source_time,
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()


class ResolutionTests(OutcomeCase):
    def _decision_with_jobs(self, price: str = "600") -> Decision:
        snap = self.snapshot("s1", et("2026-08-27", 16), price)
        decision = self.decision(snap, action="OPTIONS_POSITION", direction="bullish")
        outcomes.ensure_jobs(self.session, decision)
        self.session.commit()
        return decision

    def test_a_horizon_that_has_not_elapsed_stays_pending(self) -> None:
        self._decision_with_jobs()
        summary = outcomes.review(self.session, self.calendar, now=et("2026-08-27", 17))
        self.assertEqual(summary.completed, 0)
        self.assertEqual(summary.still_pending, len(outcomes.HORIZONS))
        self.assertEqual(self.session.scalars(select(DecisionOutcomeRecord)).all(), [])

    def test_an_elapsed_horizon_without_an_observation_stays_pending(self) -> None:
        """The evidence has not arrived. That is not an outcome of zero."""
        self._decision_with_jobs()
        summary = outcomes.review(self.session, self.calendar, now=et("2026-09-02", 17))
        self.assertEqual(summary.completed, 0)
        self.assertEqual(self.session.scalars(select(DecisionOutcomeRecord)).all(), [])

    def test_an_elapsed_horizon_with_a_completed_close_resolves(self) -> None:
        self._decision_with_jobs("600")
        self.snapshot("s2", et("2026-08-28", 16), "606")
        outcomes.review(self.session, self.calendar, now=et("2026-08-28", 17))
        row = self.session.scalars(
            select(DecisionOutcomeRecord).where(DecisionOutcomeRecord.horizon == "T+1")
        ).one()
        self.assertEqual(row.outcome_kind, outcomes.TRADE)
        self.assertEqual(Decimal(str(row.underlying_at_decision)), Decimal("600"))
        self.assertEqual(Decimal(str(row.underlying_at_horizon)), Decimal("606"))
        self.assertEqual(Decimal(str(row.underlying_change)), Decimal("6"))
        self.assertTrue(row.direction_agreed)
        self.assertEqual(row.observed_snapshot_id, "s2")
        job = self.session.scalars(
            select(ReviewJob).where(ReviewJob.horizon == "T+1")
        ).one()
        self.assertEqual(job.state, outcomes.COMPLETE)
        self.assertIsNotNone(job.resolved_at)

    def test_the_first_qualifying_close_is_used_not_the_latest(self) -> None:
        """Taking the most recent close would lengthen the horizon as time passed."""
        self._decision_with_jobs("600")
        self.snapshot("s2", et("2026-08-28", 16), "606")
        self.snapshot("s3", et("2026-08-31", 16), "650")
        outcomes.review(self.session, self.calendar, now=et("2026-08-31", 17))
        row = self.session.scalars(
            select(DecisionOutcomeRecord).where(DecisionOutcomeRecord.horizon == "T+1")
        ).one()
        self.assertEqual(row.observed_snapshot_id, "s2")
        self.assertEqual(Decimal(str(row.underlying_at_horizon)), Decimal("606"))

    def test_a_close_before_the_horizon_is_never_used(self) -> None:
        """The look-ahead protection, from the other side: too early is not eligible."""
        self._decision_with_jobs("600")
        self.snapshot("s2", et("2026-08-28", 16), "606")   # one session: T+1 only
        outcomes.review(self.session, self.calendar, now=et("2026-09-02", 17))
        horizons = {
            r.horizon for r in self.session.scalars(select(DecisionOutcomeRecord)).all()
        }
        self.assertEqual(horizons, {"T+1"}, "T+3 has no close three sessions out")

    def test_reviewing_twice_yields_one_outcome(self) -> None:
        self._decision_with_jobs()
        self.snapshot("s2", et("2026-08-28", 16), "606")
        first = outcomes.review(self.session, self.calendar, now=et("2026-08-28", 17))
        second = outcomes.review(self.session, self.calendar, now=et("2026-08-28", 18))
        self.assertEqual(first.completed, 1)
        self.assertEqual(second.completed, 0, "a resolved horizon is not asked again")
        self.assertEqual(len(self.session.scalars(select(DecisionOutcomeRecord)).all()), 1)

    def test_enrichment_never_edits_the_decision(self) -> None:
        decision = self._decision_with_jobs()
        before = (decision.decision_hash, decision.action, decision.direction, decision.decided_at)
        self.snapshot("s2", et("2026-08-28", 16), "606")
        outcomes.review(self.session, self.calendar, now=et("2026-08-28", 17))
        self.session.refresh(decision)
        after = (decision.decision_hash, decision.action, decision.direction, decision.decided_at)
        self.assertEqual(before, after)


class ReplayedDecisionsTests(OutcomeCase):
    """A replayed decision has no future inside its own database.

    The committed evidence is a set of independent scenarios, not a price series:
    its decisions are dated by replay wall-clock, after the observations they
    used, and its snapshots belong to unrelated cases (641.25 and 771.10 are not
    two points on one instrument's path). Anchoring the horizon on `decided_at`
    is what keeps that shape inert. Anchoring on the observation instead would
    have manufactured a +129.85 one-session move between unrelated fixtures.
    """

    def test_a_decision_dated_after_its_observations_never_resolves(self) -> None:
        early = self.snapshot("observed", et("2026-08-27", 16), "641.25")
        later = self.decision(early, decided_at=et("2026-09-02", 16))
        self.snapshot("unrelated", et("2026-08-28", 16), "771.10")
        outcomes.ensure_jobs(self.session, later)
        self.session.commit()
        summary = outcomes.review(self.session, self.calendar, now=et("2026-09-02", 17))
        self.assertEqual(summary.completed, 0)
        self.assertEqual(self.session.scalars(select(DecisionOutcomeRecord)).all(), [])


class DirectionTests(unittest.TestCase):
    def test_a_stated_direction_is_compared_not_scored(self) -> None:
        self.assertTrue(outcomes.direction_agreed("bullish", Decimal("1")))
        self.assertFalse(outcomes.direction_agreed("bullish", Decimal("-1")))
        self.assertTrue(outcomes.direction_agreed("bearish", Decimal("-1")))
        self.assertFalse(outcomes.direction_agreed("bearish", Decimal("1")))

    def test_unanswerable_cases_are_none_not_false(self) -> None:
        """A refusal has no direction, and a flat move answers neither way.
        False would be averaged later as if it meant something."""
        self.assertIsNone(outcomes.direction_agreed("neutral", Decimal("5")))
        self.assertIsNone(outcomes.direction_agreed("bullish", Decimal("0")))


class RealizedTests(OutcomeCase):
    def _order(self, decision_id: str, role: str, price: str, status: str = "filled") -> None:
        intent_id = uuid.uuid4().hex
        self.session.add(
            OrderIntent(
                id=intent_id, decision_id=decision_id, intent_hash=f"sha256:{role}",
                client_order_id=f"oa-{role}", legs=[], desired_limit_price=Decimal(price),
                approval_reference="ref", expires_at=et("2026-08-27", 17),
            )
        )
        self.session.add(
            BrokerOrder(
                id=uuid.uuid4().hex, order_intent_id=intent_id, broker_order_id=None,
                client_order_id=f"oa-{role}", role=role, status=status, local_state="TERMINAL",
                terminal=True, strategy_quantity=1, filled_quantity=1,
                filled_avg_price=Decimal(price), prepared_at=et("2026-08-27", 15),
                submitted_at=et("2026-08-27", 15), deadline_at=et("2026-08-27", 16),
                reconciled_at=et("2026-08-27", 16),
            )
        )
        self.session.commit()

    def test_a_round_trip_is_computed_from_recorded_fills(self) -> None:
        snap = self.snapshot("s1", et("2026-08-27", 16), "600")
        decision = self.decision(snap, action="OPTIONS_POSITION", direction="bullish")
        self._order(decision.id, "entry", "3.13")
        self._order(decision.id, "close", "3.06")
        self.assertEqual(
            outcomes.realized_from_fills(self.session, decision.id), Decimal("-7.00")
        )

    def test_an_unclosed_trade_has_no_result_yet(self) -> None:
        """None, not zero: zero would read as break-even."""
        snap = self.snapshot("s1", et("2026-08-27", 16), "600")
        decision = self.decision(snap, action="OPTIONS_POSITION", direction="bullish")
        self._order(decision.id, "entry", "3.13")
        self.assertIsNone(outcomes.realized_from_fills(self.session, decision.id))

    def test_a_refusal_records_no_realized_figure(self) -> None:
        snap = self.snapshot("s1", et("2026-08-27", 16), "600")
        refusal = self.decision(snap)
        outcomes.ensure_jobs(self.session, refusal)
        self.session.commit()
        self.snapshot("s2", et("2026-08-28", 16), "606")
        outcomes.review(self.session, self.calendar, now=et("2026-08-28", 17))
        row = self.session.scalars(
            select(DecisionOutcomeRecord).where(DecisionOutcomeRecord.horizon == "T+1")
        ).one()
        self.assertEqual(row.outcome_kind, outcomes.NO_TRADE)
        self.assertIsNone(row.realized)


class RecordedDecisionsCarryTheirJobsTests(unittest.TestCase):
    """`CIIP-008`. A decision cannot exist without the questions asked of it:
    the jobs are written in the decision's own transaction."""

    def _recorder(self):  # type: ignore[no-untyped-def]
        import tempfile
        from pathlib import Path

        from options_alpha_lab.config import load_settings
        from options_alpha_lab.persistence.repository import (
            DecisionRecorder,
            build_engine,
            create_schema,
        )

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings = load_settings({
            "BOT_MODE": "observe",
            "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{Path(tmp.name) / 'w.db'}",
        })
        engine = build_engine(settings)
        create_schema(engine)
        return DecisionRecorder(engine, settings), engine

    def test_recording_a_decision_creates_its_review_jobs(self) -> None:
        from options_alpha_lab.replay import replay_paths

        recorder, engine = self._recorder()
        settings = recorder._settings  # noqa: SLF001 - test introspection
        results = replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")], settings)
        self.assertTrue(results)
        with Session(engine) as session:
            decisions = session.scalars(select(Decision)).all()
            self.assertTrue(decisions)
            for decision in decisions:
                horizons = sorted(
                    j.horizon
                    for j in session.scalars(
                        select(ReviewJob).where(ReviewJob.decision_id == decision.id)
                    ).all()
                )
                self.assertEqual(horizons, [h.label for h in outcomes.HORIZONS])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
