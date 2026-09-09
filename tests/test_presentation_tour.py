"""Regression tests for `CIIP-004`: no tour step may point at nothing.

The failure this guards against is quiet. A scene naming a snapshot the evidence
set does not contain would not raise — the dashboard would simply render
whatever case happened to be selected, under a confident heading describing a
different one. That is worse than an error, because it looks like it worked.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab.presentation.tour import SCENES, missing_scenes, resolve, scene

DB = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"


class TourTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(f"sqlite+pysqlite:///{DB}", future=True)
        self.session = Session(engine)

    def tearDown(self) -> None:
        self.session.close()

    def test_every_scene_resolves_to_committed_evidence(self) -> None:
        absent = missing_scenes(self.session)
        self.assertEqual(
            [s.snapshot_id for s in absent],
            [],
            "a tour step would render a different case under its own heading",
        )

    def test_there_are_six_scenes_numbered_in_order(self) -> None:
        self.assertEqual(len(SCENES), 6)
        self.assertEqual([s.number for s in SCENES], list(range(1, 7)))

    def test_out_of_range_steps_clamp_rather_than_raise(self) -> None:
        """A hand-edited or stale URL must not break the page."""
        self.assertEqual(scene(0).number, 1)
        self.assertEqual(scene(-4).number, 1)
        self.assertEqual(scene(99).number, 6)

    def test_the_tour_ends_on_a_refusal(self) -> None:
        """A tour ending on a winning trade says the system works.

        One ending on a refusal the model was never consulted for says why.
        """
        last = SCENES[-1]
        self.assertIn("refusal", last.snapshot_id)
        decision = resolve(self.session, last)
        assert decision is not None
        self.assertEqual(decision.action, "NO_TRADE")

    def test_the_model_scene_comes_after_the_deterministic_one(self) -> None:
        titles = [s.title for s in SCENES]
        self.assertLess(
            titles.index("What the code decided before the model ran"),
            titles.index("What the model contributed"),
        )

    def test_every_scene_names_a_tab_that_exists(self) -> None:
        for item in SCENES:
            self.assertIn(item.tab, range(5), f"scene {item.number} has no valid tab")

    def test_every_scene_carries_narration(self) -> None:
        for item in SCENES:
            self.assertTrue(item.narration.strip(), f"scene {item.number} is silent")
            self.assertTrue(item.title.strip())

    def test_the_losing_trade_is_not_hidden(self) -> None:
        outcome = next(s for s in SCENES if "Alpaca actually did" in s.title)
        self.assertIn("lost money", outcome.narration)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
