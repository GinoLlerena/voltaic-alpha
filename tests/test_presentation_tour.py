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


class TourRendersItsOwnDecisionTests(unittest.TestCase):
    """`RUI-VAL-009`. The tests above proved each scene's decision *exists*; none
    proved the page *shows* it. Five of six scenes narrated one decision over
    another, because a scene selected its case only if the default view listed
    it and otherwise fell back to the first entry."""

    APP = Path(__file__).resolve().parents[1] / "app.py"

    def _run(self, number: int, live_url: str | None = None):  # type: ignore[no-untyped-def]
        import os

        from streamlit.testing.v1 import AppTest

        saved = os.environ.get("DASHBOARD_DATABASE_URL")
        if live_url:
            os.environ["DASHBOARD_DATABASE_URL"] = live_url
        else:
            os.environ.pop("DASHBOARD_DATABASE_URL", None)
        try:
            run = AppTest.from_file(str(self.APP), default_timeout=120)
            run.query_params["tour"] = str(number)
            return run.run()
        finally:
            if saved is None:
                os.environ.pop("DASHBOARD_DATABASE_URL", None)
            else:
                os.environ["DASHBOARD_DATABASE_URL"] = saved

    def test_every_scene_selects_its_own_decision_in_the_default_view(self) -> None:
        import sqlite3

        ids = dict(sqlite3.connect(DB).execute("select id, snapshot_id from decisions"))
        for item in SCENES:
            with self.subTest(scene=item.number):
                run = self._run(item.number)
                self.assertFalse(run.exception)
                self.assertEqual(ids[run.radio[1].value], item.snapshot_id)
                self.assertTrue(
                    any(item.narration[:40] in m.value for m in run.markdown),
                    "the scene's narration must be shown with its own decision",
                )

    def test_a_filter_that_excludes_the_scenes_decision_still_shows_it(self) -> None:
        """Where the pin is load-bearing: a position scene viewed under "Refusals".

        With every position now listed in the default view, the default-view test
        above passes with or without pinning. This one does not."""
        import os
        import sqlite3

        from streamlit.testing.v1 import AppTest

        ids = dict(sqlite3.connect(DB).execute("select id, snapshot_id from decisions"))
        saved = os.environ.pop("DASHBOARD_DATABASE_URL", None)
        try:
            for item in SCENES:
                if not item.snapshot_id.startswith(("spy-qualified", "spy-lifecycle")):
                    continue
                with self.subTest(scene=item.number):
                    run = AppTest.from_file(str(self.APP), default_timeout=120)
                    run.query_params["tour"] = str(item.number)
                    run.run()
                    run.radio[0].set_value("Refusals").run()
                    self.assertFalse(run.exception)
                    self.assertEqual(ids[run.radio[1].value], item.snapshot_id)
        finally:
            if saved is not None:
                os.environ["DASHBOARD_DATABASE_URL"] = saved

    def test_a_scene_whose_decision_is_absent_says_so(self) -> None:
        """On a source without the scene's case, admit it; never narrate over another."""
        import shutil
        import sqlite3
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.db"
            shutil.copy(DB, live)
            with sqlite3.connect(live) as conn:
                conn.execute("delete from decisions where snapshot_id=?", (SCENES[0].snapshot_id,))
            run = self._run(1, f"sqlite+pysqlite:///{live}")
        self.assertFalse(run.exception)
        rendered = " ".join(m.value for m in run.markdown)
        self.assertIn("is not in", rendered)
        self.assertIn("not the one this step describes", rendered)
        self.assertNotIn(SCENES[0].narration[:40], rendered)
