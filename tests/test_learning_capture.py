"""Phase 1: every managed position is reconstructable without console logs.

The property under test is not "a row was written". It is that the mark an exit
decision was made on survives independently of the decision, that decisions
which did nothing are kept on the same footing as the ones that acted, and that
neither can be produced without the other having been recorded first.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import PriceSource
from options_alpha_lab.execution.lifecycle import PositionState
from options_alpha_lab.persistence.models import ExitDecisionRecord, PositionObservation
from options_alpha_lab.persistence.repository import (
    build_engine,
    create_schema,
    upgrade_schema,
)
from test_agent import LONG, NOW, SHORT, WRITE_ENV, DurableAgentCase, FakeClient

STOP_QUOTES = {LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}


class ObservationCaptureTests(DurableAgentCase):
    def observations(self, position_id: str) -> list[PositionObservation]:
        return self.store.observations_for(position_id)

    def decisions(self, position_id: str) -> list[ExitDecisionRecord]:
        return self.store.exit_decisions_for(position_id)

    def test_a_hold_is_recorded_with_the_mark_it_was_decided_on(self) -> None:
        # A store that keeps only the decisions that acted cannot say how often
        # a threshold nearly fired, which is the question tuning it depends on.
        agent = self.build(WRITE_ENV)
        position_id = self.open_position()
        self.assertEqual(agent.tick().action, "POSITION_HELD")

        observed = self.observations(position_id)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0].spread_value, Decimal("2.600000"))
        self.assertEqual(observed[0].long_bid, Decimal("12.400000"))
        self.assertEqual(observed[0].short_ask, Decimal("9.800000"))
        self.assertEqual(observed[0].underlying_source, PriceSource.COMPLETED_DAILY_CLOSE.value)
        self.assertEqual(observed[0].quantity, 1)

        decided = self.decisions(position_id)
        self.assertEqual(len(decided), 1)
        self.assertEqual(decided[0].trigger, "hold")
        self.assertFalse(decided[0].should_close)
        self.assertEqual(decided[0].disposition, "held")
        self.assertEqual(decided[0].observation_id, observed[0].id)

    def test_every_trigger_is_recorded_not_only_the_governing_one(self) -> None:
        agent = self.build(WRITE_ENV)
        position_id = self.open_position()
        agent.tick()

        evaluated = self.decisions(position_id)[0].evaluated
        self.assertEqual(
            [row["trigger"] for row in evaluated],
            ["expiry_guard", "invalidation_breached", "stop_loss",
             "session_stop", "profit_capture"],
        )
        # Each carries what it saw and what it needed to see, so a threshold can
        # be replayed against the observations that actually occurred.
        for row in evaluated:
            self.assertIn("observed", row)
            self.assertIn("threshold", row)
            self.assertFalse(row["fired"], row)

    def test_a_rule_that_could_not_be_evaluated_is_not_recorded_as_not_fired(self) -> None:
        # None and False are different facts. Collapsing them is how a missing
        # value becomes indistinguishable from a healthy one.
        agent = self.build(WRITE_ENV, client=FakeClient(quotes={}))
        position_id = self.open_position()
        agent.tick()

        rows = {r["trigger"]: r for r in self.decisions(position_id)[0].evaluated}
        self.assertIsNone(rows["stop_loss"]["fired"])
        self.assertEqual(rows["stop_loss"]["skipped"], "no readable premium")
        self.assertIsNone(rows["profit_capture"]["fired"])
        # Premium-independent rules were still genuinely evaluated.
        self.assertIs(rows["expiry_guard"]["fired"], False)
        self.assertIs(rows["session_stop"]["fired"], False)

    def test_a_close_records_its_decision_before_it_is_submitted(self) -> None:
        agent = self.build(WRITE_ENV, client=FakeClient(quotes=STOP_QUOTES))
        position_id = self.open_position()
        self.assertEqual(agent.tick().action, "CLOSE_SUBMITTED")

        decided = self.decisions(position_id)
        self.assertEqual(len(decided), 1)
        self.assertEqual(decided[0].trigger, "stop_loss")
        self.assertTrue(decided[0].should_close)
        self.assertEqual(decided[0].disposition, "close_submitting")
        # Linked to the order it authorised, so a crash mid-submit still leaves
        # the reason the close was attempted.
        self.assertIsNotNone(decided[0].close_order_id)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertEqual(decided[0].close_order_id, managed.close_order_id)

    def test_a_signalled_exit_without_authority_is_still_recorded(self) -> None:
        agent = self.build(WRITE_ENV, client=FakeClient(quotes=STOP_QUOTES))
        agent.gateway = None  # recommend-mode shape: it decides, it cannot write
        position_id = self.open_position()
        self.assertEqual(agent.tick().action, "EXIT_SIGNALLED")

        decided = self.decisions(position_id)[0]
        self.assertTrue(decided.should_close)
        self.assertEqual(decided.disposition, "signalled_without_authority")
        self.assertIsNone(decided.close_order_id)

    def test_marks_continue_while_a_close_is_working(self) -> None:
        # MFE and MAE need an unbroken series. A position under a working close
        # is still moving, and CLOSE_WORKING used to return before observing.
        agent = self.build(WRITE_ENV, client=FakeClient(quotes=STOP_QUOTES))
        position_id = self.open_position()
        agent.tick()
        self.assertIs(self.store.get_position(position_id).state, PositionState.CLOSING)

        self.assertEqual(agent.tick().action, "CLOSE_WORKING")
        self.assertEqual(len(self.observations(position_id)), 2, "still marked")
        # But no second exit decision: none was evaluated, and inventing one
        # would imply the policy ran when it deliberately did not.
        self.assertEqual(len(self.decisions(position_id)), 1)

    def test_observations_accumulate_across_ticks_and_are_ordered(self) -> None:
        agent = self.build(WRITE_ENV)
        position_id = self.open_position()
        # Inside the 60-second clock freshness window: past it the clock read
        # is stale, the price source degrades to UNKNOWN, and the tick becomes a
        # POSITION_REVIEW rather than the plain hold this test is about.
        for offset in range(3):
            agent._clock = lambda o=offset: NOW + timedelta(seconds=20 * o)
            agent.tick()

        observed = self.observations(position_id)
        self.assertEqual(len(observed), 3)
        self.assertEqual(observed, sorted(observed, key=lambda row: row.observed_at))
        self.assertEqual(len(self.decisions(position_id)), 3)

    def test_the_original_decision_is_never_amended_by_a_later_one(self) -> None:
        agent = self.build(WRITE_ENV)
        position_id = self.open_position()
        agent.tick()
        first = self.decisions(position_id)[0]
        original = (first.id, first.trigger, first.reason, first.decided_at)

        agent._clock = lambda: NOW + timedelta(seconds=20)
        agent.tick()

        rows = self.decisions(position_id)
        self.assertEqual(len(rows), 2, "appended, not updated")
        self.assertEqual((rows[0].id, rows[0].trigger, rows[0].reason, rows[0].decided_at),
                         original)


class MigrationTests(unittest.TestCase):
    """Finding 8: a versioned path exists, and it goes both ways."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "m.db"
        from options_alpha_lab.config import load_settings

        self.settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{db}",
        })
        self.engine = build_engine(self.settings)

    def tearDown(self) -> None:
        self.engine.dispose()
        self._tmp.cleanup()

    def test_a_created_schema_is_stamped_so_the_next_upgrade_is_a_no_op(self) -> None:
        # Without stamping, a fresh database has no alembic_version row and the
        # next `upgrade head` tries to create tables that already exist.
        create_schema(self.engine)
        self.assertIn("alembic_version", inspect(self.engine).get_table_names())
        with Session(self.engine) as session:
            stamped = session.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
        self.assertEqual(stamped, "0002_learning_capture")

        upgrade_schema(self.engine)  # must not raise on an already-current database
        self.assertIn("exit_decisions", inspect(self.engine).get_table_names())

    def test_the_capture_tables_can_be_rolled_back_and_reapplied(self) -> None:
        from alembic import command

        from options_alpha_lab.persistence.repository import alembic_config

        create_schema(self.engine)
        config = alembic_config(self.engine)

        command.downgrade(config, "0001_h0_baseline")
        names = inspect(self.engine).get_table_names()
        self.assertNotIn("exit_decisions", names)
        self.assertNotIn("position_observations", names)
        self.assertIn("positions", names, "the rollback must not touch the baseline")

        command.upgrade(config, "head")
        names = inspect(self.engine).get_table_names()
        self.assertIn("exit_decisions", names)
        self.assertIn("position_observations", names)
