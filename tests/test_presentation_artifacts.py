"""Regression tests for `CIIP-CV-002`: adjacency is not correlation.

The defect was that a committed Paper receipt rendered directly beneath whatever
decision happened to be selected, with nothing saying whether the two were
related. With one receipt and one lifecycle in the evidence set they usually
were, which is what made it invisible.

These tests assert the uncomfortable direction: for four of the five committed
decisions the receipt must be labelled as belonging to a *different* decision,
and the ablation must never be attributed to any decision at all.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from options_alpha_lab.persistence.models import Decision
from options_alpha_lab.presentation.artifacts import (
    correlate_ablation,
    correlate_receipt,
)
from options_alpha_lab.presentation.decision import load

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "demo" / "h0_demo.db"
RECEIPT = json.loads((ROOT / "artifacts" / "h0_paper_lifecycle.json").read_text())
ABLATION = json.loads((ROOT / "artifacts" / "ablation_h0.json").read_text())

#: The snapshot the receipt names. Note that this is *not* the same thing as the
#: decision it describes: the receipt's decision_hash matches no decision in the
#: committed database, including the one built from this snapshot. See
#: `test_the_receipt_matches_no_committed_decision`.
SAME_SNAPSHOT = "spy-lifecycle-20260828T154747Z"


class ReceiptCorrelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(create_engine(f"sqlite+pysqlite:///{DB}", future=True))

    def tearDown(self) -> None:
        self.session.close()

    def _view(self, snapshot_id: str):  # type: ignore[no-untyped-def]
        decision = self.session.scalars(
            select(Decision).where(Decision.snapshot_id == snapshot_id)
        ).one()
        return load(self.session, decision)

    def test_the_receipt_matches_no_committed_decision(self) -> None:
        """The finding that justified this module.

        The receipt names `spy-lifecycle-20260828T154747Z` and the database
        holds a decision built from that snapshot, but their decision hashes
        differ — the demo database was rebuilt and the decision re-derived,
        while the receipt is from the original live run. The dashboard rendered
        the two together for the whole judging period, so a reader would
        reasonably have read the receipt as that decision's outcome.
        """
        owners = [
            d.snapshot_id
            for d in self.session.scalars(select(Decision)).all()
            if correlate_receipt(load(self.session, d), RECEIPT).belongs
        ]
        self.assertEqual(owners, [], "correlation must not be inferred from adjacency")

    def test_the_same_snapshot_case_says_what_actually_differs(self) -> None:
        link = correlate_receipt(self._view(SAME_SNAPSHOT), RECEIPT)
        self.assertFalse(link.belongs)
        self.assertEqual(link.matched_on, "decision_hash")
        self.assertIn("different evaluation of the same snapshot", link.reason)

    def test_a_matching_hash_does_correlate(self) -> None:
        """The positive path, proved by constructing the match."""
        view = self._view(SAME_SNAPSHOT)
        receipt = dict(RECEIPT)
        receipt["decision_hash"] = view.decision.decision_hash
        link = correlate_receipt(view, receipt)
        self.assertTrue(link.belongs)
        self.assertEqual(link.matched_on, "decision_hash")

    def test_another_decision_is_labelled_as_another_decision(self) -> None:
        link = correlate_receipt(self._view("spy-refusal-2026-08-27"), RECEIPT)
        self.assertFalse(link.belongs)
        self.assertEqual(link.relation, "OTHER_DECISION")
        self.assertIn("not the outcome of the selected case", link.reason)

    def test_a_receipt_with_no_identifier_is_unknown_not_matched(self) -> None:
        link = correlate_receipt(self._view(SAME_SNAPSHOT), {"final_state": {"realized": "-7.10"}})
        self.assertFalse(link.belongs)
        self.assertEqual(link.relation, "UNKNOWN")

    def test_a_missing_receipt_is_unknown(self) -> None:
        self.assertEqual(correlate_receipt(self._view(SAME_SNAPSHOT), {}).relation, "UNKNOWN")

    def test_snapshot_id_is_a_fallback_not_the_primary_key(self) -> None:
        """A snapshot can replay into several decisions; a decision hash cannot."""
        receipt = {k: v for k, v in RECEIPT.items() if k != "decision_hash"}
        link = correlate_receipt(self._view(SAME_SNAPSHOT), receipt)
        self.assertTrue(link.belongs)
        self.assertEqual(link.matched_on, "snapshot_id")

    def test_a_mismatched_hash_wins_over_a_matching_snapshot(self) -> None:
        """If the hashes disagree, the artifact is not this decision's."""
        receipt = dict(RECEIPT)
        receipt["decision_hash"] = "sha256:deadbeef"
        link = correlate_receipt(self._view(SAME_SNAPSHOT), receipt)
        self.assertFalse(link.belongs)
        self.assertEqual(link.matched_on, "decision_hash")


class AblationCorrelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(create_engine(f"sqlite+pysqlite:///{DB}", future=True))

    def tearDown(self) -> None:
        self.session.close()

    def test_the_ablation_never_belongs_to_a_decision(self) -> None:
        for decision in self.session.scalars(select(Decision)).all():
            link = correlate_ablation(load(self.session, decision), ABLATION)
            self.assertFalse(link.belongs, decision.snapshot_id)
            self.assertEqual(link.relation, "NOT_DECISION_SCOPED")

    def test_it_says_how_many_cases_it_covers(self) -> None:
        decision = self.session.scalars(select(Decision)).first()
        assert decision is not None
        link = correlate_ablation(load(self.session, decision), ABLATION)
        self.assertIn("5 frozen cases", link.reason)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
