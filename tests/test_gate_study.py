"""The study's gate must be the shipped gate, or the study measures nothing.

`gate_study` re-implements the structure gate so that variations can be applied
to it. That is the whole risk of the module: a re-implementation that has
drifted from `evidence.structure_reading` produces a report about a system
nobody is running, and it would look exactly as convincing.

So the baseline is held to the real function on every session in the fixture,
not on a sample.
"""

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from options_alpha_lab import gate_study
from options_alpha_lab.evidence import MIN_EMA_SEPARATION, structure_reading


class BaselineMatchesTheShippedGate(unittest.TestCase):
    def setUp(self) -> None:
        self.views = gate_study.windows(gate_study.load_spy())

    def test_there_is_enough_history_to_be_worth_reporting(self) -> None:
        self.assertGreater(len(self.views), 400)

    def test_every_session_agrees_with_evidence_structure_reading(self) -> None:
        for window in self.views:
            session = window[-1].session
            with self.subTest(session=str(session)):
                as_of = datetime.combine(
                    session + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                )
                shipped = structure_reading(window, as_of)
                studied = gate_study.verdict(window)
                self.assertEqual(shipped.gate, studied.gate)
                self.assertEqual(shipped.separation, studied.separation)
                self.assertEqual(shipped.close_side, studied.close_side)
                self.assertEqual(shipped.retest_touched, studied.retest_touched)

    def test_the_window_is_the_one_the_worker_receives(self) -> None:
        """400 calendar days, which is what the provider is asked for."""
        self.assertEqual(gate_study.LOOKBACK_DAYS, 400)
        # The live readings recorded 275 bars considered; the fixture's windows
        # should land in the same neighbourhood rather than the full series.
        sizes = {len(window) for window in self.views}
        self.assertLess(max(sizes), 300, f"window too long: {max(sizes)}")
        self.assertGreater(max(sizes), 250, f"window too short: {max(sizes)}")


class VariationsDoWhatTheyClaim(unittest.TestCase):
    def setUp(self) -> None:
        self.views = gate_study.windows(gate_study.load_spy())

    def test_dropping_the_side_test_can_only_admit_more(self) -> None:
        """A loosened gate that refused *more* would mean the knob is inverted."""
        baseline = gate_study.census(self.views)
        loosened = gate_study.census(self.views, require_side=False)
        self.assertGreaterEqual(
            loosened.get("passed", 0) + loosened.get("no_retest", 0),
            baseline.get("passed", 0) + baseline.get("no_retest", 0),
        )
        self.assertLessEqual(
            loosened.get("separation_or_side", 0), baseline.get("separation_or_side", 0)
        )

    def test_a_tolerance_is_monotonic(self) -> None:
        refusals = [
            gate_study.census(self.views, side_tolerance=t).get("separation_or_side", 0)
            for t in (Decimal(0), *gate_study.TOLERANCES)
        ]
        self.assertEqual(refusals, sorted(refusals, reverse=True), refusals)

    def test_zero_tolerance_is_the_shipped_rule(self) -> None:
        self.assertEqual(
            gate_study.census(self.views),
            gate_study.census(self.views, side_tolerance=Decimal(0)),
        )

    def test_a_refusal_with_separation_failed_on_side_alone(self) -> None:
        """The report's central number, checked rather than asserted in prose."""
        report = gate_study.run()
        refused_with_separation = [
            v for v in (gate_study.verdict(w) for w in self.views)
            if v.gate == "separation_or_side"
            and v.separation is not None
            and abs(v.separation) >= MIN_EMA_SEPARATION
        ]
        self.assertEqual(report["refused_with_separation"], len(refused_with_separation))
        # Each of them really did have separation and really did fail: the only
        # remaining reason is the side of EMA20 the close landed on.
        for v in refused_with_separation:
            self.assertIsNotNone(v.close_gap)


class TheReportSaysWhatItCannot(unittest.TestCase):
    def test_render_carries_the_no_edge_warning(self) -> None:
        """A count of qualifying sessions is not a hit rate, and must not read
        as one if the table is pasted somewhere without its module docstring."""
        text = gate_study.render(gate_study.run()).lower()
        self.assertIn("does not say", text)
        self.assertIn("section 9", text)
        # The words may appear in the disclaimer — that is where they belong.
        # What must not happen is the body of the report making such a claim.
        body, _, disclaimer = text.partition("what this does not say")
        self.assertTrue(disclaimer, "the report lost its disclaimer")
        for forbidden in ("win rate", "hit rate", "profit", "edge", "return"):
            self.assertNotIn(forbidden, body, f"the report body claims {forbidden!r}")
