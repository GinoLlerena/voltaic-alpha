"""Regression tests for `CIIP-005`: the summary must not outrun the records.

Two failure modes matter here and they pull in opposite directions. The summary
could assert a stage that has no record — the hardcoded-status defect again, in
prose. Or it could quietly omit a missing stage, which reads as though the stage
happened and was unremarkable. The refusal case is the one that catches both:
its correct rendering is three explicit absences, not a shorter list.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from options_alpha_lab.persistence.models import Decision
from options_alpha_lab.presentation.explain import why_decision

DB = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"


def _decision(session: Session, snapshot_id: str) -> Decision:
    return session.scalars(
        select(Decision).where(Decision.snapshot_id == snapshot_id)
    ).one()


class ExplanationTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(f"sqlite+pysqlite:///{DB}", future=True)
        self.session = Session(engine)

    def tearDown(self) -> None:
        self.session.close()

    def test_every_line_names_its_source(self) -> None:
        for snapshot in ("spy-qualified-2026-08-27", "spy-refusal-2026-08-27"):
            for line in why_decision(self.session, _decision(self.session, snapshot)):
                self.assertTrue(line.source, f"{snapshot}/{line.stage} has no source")
                self.assertTrue(line.text.strip())

    def test_refusal_renders_absences_rather_than_omitting_them(self) -> None:
        lines = why_decision(
            self.session, _decision(self.session, "spy-refusal-2026-08-27")
        )
        missing = [line for line in lines if not line.present]
        self.assertGreaterEqual(
            len(missing), 3, "the refusal must show its absences, not hide them"
        )
        stages = {line.stage for line in missing}
        self.assertIn("Model memo", stages)
        self.assertIn("Authorized intent", stages)

    def test_refusal_says_the_model_was_never_called(self) -> None:
        lines = why_decision(
            self.session, _decision(self.session, "spy-refusal-2026-08-27")
        )
        memo = next(line for line in lines if line.stage == "Model memo")
        self.assertFalse(memo.present)
        self.assertIn("never called", memo.text)

    def test_refusal_claims_no_broker_contact(self) -> None:
        lines = why_decision(
            self.session, _decision(self.session, "spy-refusal-2026-08-27")
        )
        self.assertNotIn("Broker", {line.stage for line in lines})

    def test_qualified_case_has_a_memo_but_never_reached_a_broker(self) -> None:
        """Deciding to trade and actually trading are different claims.

        `spy-qualified-2026-08-27` produced a memo and an approved risk decision
        but no order intent. The tabs blur that distinction; the summary must
        not, because "the system decided to buy" and "the system bought" are the
        two things a reviewer is most likely to conflate.
        """
        lines = why_decision(
            self.session, _decision(self.session, "spy-qualified-2026-08-27")
        )
        stages = {line.stage: line for line in lines}
        self.assertTrue(stages["Model memo"].present)
        self.assertFalse(stages["Authorized intent"].present)
        self.assertNotIn("Broker", stages)

    def test_executed_case_reports_a_derived_client_order_id(self) -> None:
        lines = why_decision(
            self.session, _decision(self.session, "spy-lifecycle-20260828T154747Z")
        )
        intent = next(line for line in lines if line.stage == "Authorized intent")
        self.assertTrue(intent.present)
        self.assertIn("derived from its own hash", intent.text)

    def test_invalidation_line_states_the_model_never_saw_it(self) -> None:
        lines = why_decision(
            self.session, _decision(self.session, "spy-qualified-2026-08-27")
        )
        line = next(line for line in lines if line.stage == "Invalidation")
        self.assertIn("never received these", line.text)

    def test_lifecycle_case_reaches_the_broker_stage(self) -> None:
        lines = why_decision(
            self.session, _decision(self.session, "spy-lifecycle-20260828T154747Z")
        )
        broker = next(line for line in lines if line.stage == "Broker")
        self.assertIn("SUBMITTED", broker.text)
        self.assertIn("reconciled", broker.text)

    def test_stages_are_in_authority_order(self) -> None:
        """Reading the summary should teach the boundary without explaining it."""
        lines = why_decision(
            self.session, _decision(self.session, "spy-lifecycle-20260828T154747Z")
        )
        order = [line.stage for line in lines]
        self.assertLess(order.index("Observed"), order.index("Model memo"))
        self.assertLess(order.index("Model memo"), order.index("Authorized intent"))
        self.assertLess(order.index("Authorized intent"), order.index("Broker"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
