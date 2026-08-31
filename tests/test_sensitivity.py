"""The sweep must not be able to report a threshold as robust when it is untested.

That is the failure this module exists to avoid, and it is one the first draft
committed: summarising only the structure direction made the participation and
momentum thresholds unreachable, and they came back as "no flip found" - which
reads as reassuring and meant nothing had been tried. These tests hold the
distinction between fragile, stable and inert, because collapsing it is how a
sensitivity report becomes worse than no report.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from options_alpha_lab import components, evidence
from options_alpha_lab.sensitivity import (
    HISTORY_SESSIONS,
    Result,
    Threshold,
    decision_thresholds,
    load_bars,
    signals_over_history,
    structure_thresholds,
    sweep,
)


class FixtureTests(unittest.TestCase):
    def test_the_committed_bars_cover_the_window_the_sweep_walks(self) -> None:
        spy, rsp = load_bars()
        self.assertGreater(len(spy), HISTORY_SESSIONS + evidence.MIN_BARS_REQUIRED)
        self.assertEqual(len(spy), len(rsp))

    def test_bars_are_ordered_and_dated(self) -> None:
        spy, _ = load_bars()
        self.assertEqual([b.session for b in spy], sorted(b.session for b in spy))
        self.assertTrue(all(b.close > 0 for b in spy))


class SummaryReachesEverySignalTests(unittest.TestCase):
    """The regression that made four thresholds untestable."""

    def setUp(self) -> None:
        self.spy, self.rsp = load_bars()
        self.answers = signals_over_history(self.spy, self.rsp)

    def test_the_summary_has_one_entry_per_session(self) -> None:
        self.assertEqual(len(self.answers), HISTORY_SESSIONS)

    def test_confirmers_and_opposers_appear_not_only_the_direction(self) -> None:
        families = {
            part.split(":")[0]
            for answer in self.answers
            if answer != "-"
            for section in answer.split("|")[1:]
            for part in section.split(",")
            if part
        }
        self.assertIn("participation", families)
        self.assertIn("momentum", families)

    def test_a_participation_threshold_actually_moves_the_answer(self) -> None:
        """Directly pins the bug: this returned an identical tuple before."""
        original = evidence.PARTICIPATION_SESSIONS
        try:
            evidence.PARTICIPATION_SESSIONS = 45
            widened = signals_over_history(self.spy, self.rsp)
        finally:
            evidence.PARTICIPATION_SESSIONS = original
        self.assertNotEqual(widened, self.answers)


class ThresholdRestorationTests(unittest.TestCase):
    def test_every_swept_constant_is_put_back(self) -> None:
        """A sweep that leaked state would silently corrupt every later test."""
        for threshold in structure_thresholds() + decision_thresholds():
            with self.subTest(threshold.name):
                before = threshold.snapshot_state()
                sweep(threshold, lambda: ("x",))
                self.assertEqual(threshold.snapshot_state(), before)

    def test_a_derived_constant_is_recomputed_with_its_source(self) -> None:
        """SLOW_EMA and MIN_BARS_REQUIRED are not independent."""
        threshold = next(
            t for t in structure_thresholds() if t.attribute == "SLOW_EMA"
        )
        seen: list[int] = []
        sweep(threshold, lambda: (str(evidence.MIN_BARS_REQUIRED),) if not seen
              else ("x",))
        threshold.install(90)
        try:
            self.assertEqual(
                evidence.MIN_BARS_REQUIRED, 90 + evidence.MOMENTUM_LONG_SESSIONS
            )
        finally:
            evidence.SLOW_EMA = 50
            evidence.MIN_BARS_REQUIRED = (
                evidence.SLOW_EMA + evidence.MOMENTUM_LONG_SESSIONS
            )

    def test_a_tuple_band_element_is_set_without_disturbing_the_other(self) -> None:
        threshold = next(
            t for t in decision_thresholds() if t.name == "components.LONG_DELTA_BAND[low]"
        )
        state = threshold.snapshot_state()
        try:
            threshold.install(Decimal("0.40"))
            self.assertEqual(components.LONG_DELTA_BAND[0], Decimal("0.40"))
            self.assertEqual(components.LONG_DELTA_BAND[1], Decimal("0.70"))
        finally:
            threshold.restore(state)


class ClassificationTests(unittest.TestCase):
    """Fragile, stable and inert must stay three answers, not two."""

    def result(self, answers: dict[str, tuple[str, ...]]) -> Result:
        threshold = Threshold(
            "t", components, "MAX_DEBIT_TO_WIDTH",
            tuple(Decimal(v) for v in answers), Decimal("1.0"),
        )
        baseline = answers["1.0"]
        return Result(
            threshold=threshold, baseline=baseline,
            observations=[(Decimal(k), v) for k, v in answers.items()],
        )

    def test_a_threshold_nothing_depends_on_is_inert_not_stable(self) -> None:
        r = self.result({"0.9": ("a", "a"), "1.0": ("a", "a"), "1.1": ("a", "a")})
        self.assertTrue(r.inert)
        self.assertFalse(r.fragile)

    def test_a_threshold_that_moves_many_outcomes_nearby_is_fragile(self) -> None:
        r = self.result({"0.9": ("b", "b"), "1.0": ("a", "a"), "1.1": ("a", "a")})
        self.assertTrue(r.fragile)
        self.assertFalse(r.inert)
        self.assertEqual(r.worst_flip_within_10pct, Decimal("1"))

    def test_a_distant_flip_is_neither_fragile_nor_inert(self) -> None:
        r = self.result({
            "0.5": ("b", "b"), "0.9": ("a", "a"), "1.0": ("a", "a"),
            "1.1": ("a", "a"), "2.0": ("b", "b"),
        })
        self.assertFalse(r.fragile)
        self.assertFalse(r.inert)

    def test_one_outcome_in_twenty_moving_is_below_the_fragile_line(self) -> None:
        steady = tuple(["a"] * 20)
        r = self.result({
            "0.9": steady, "1.0": steady, "1.1": tuple(["a"] * 19 + ["b"]),
        })
        self.assertEqual(r.worst_flip_within_10pct, Decimal("0.05"))
        self.assertFalse(r.fragile)
        self.assertFalse(r.inert)

    def test_a_length_mismatch_raises_rather_than_scoring_a_partial_compare(self) -> None:
        """Two evaluations of different length is a bug, not a 0% flip."""
        r = self.result({"1.0": ("a", "a"), "1.1": ("a",)})
        with self.assertRaises(ValueError):
            _ = r.worst_flip_within_10pct


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
