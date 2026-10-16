"""Step 2 of the veto backtest: the replay must decide as the worker decides.

Attribution is checked on hand-built signal sets, one per bucket, and against
the shipped classifier. The replay itself is checked on the committed bar
fixture for what would make it quietly wrong: reading a bar from the decision
session or later, bridging a missing input, or giving a different answer on a
second run.
"""

import unittest
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import combinations
from unittest import mock

from options_alpha_lab import veto_replay as vr
from options_alpha_lab.architecture.contracts import Direction, Signal, SignalFamily
from options_alpha_lab.veto_study import load_bars

AS_OF = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
CLOSE = Decimal("700.00")
SESSION = date(2026, 10, 8)


def sig(name: str, family: SignalFamily, direction: Direction, strength: str) -> Signal:
    return Signal(f"sig-{name}", family, direction, Decimal(strength), AS_OF, "test", "test")


STRUCTURE = sig("structure-trend-retest", SignalFamily.STRUCTURE, Direction.BULLISH, "0.61")
CALM = sig("volatility-regime", SignalFamily.VOLATILITY_OPTIONS, Direction.BULLISH, "0.75")
NARROW = sig("participation-breadth", SignalFamily.PARTICIPATION, Direction.BEARISH, "0.89")
NARROW_QUIET = replace(NARROW, strength=Decimal("0.69"))
DIVERGENT = sig("momentum-divergence", SignalFamily.MOMENTUM, Direction.BEARISH, "0.75")


def attribute(*signals: Signal) -> vr.Attribution:
    return vr.attribute(tuple(signals), CLOSE, SESSION, AS_OF)


class AttributionTests(unittest.TestCase):
    def test_a_qualified_setup_is_permitted_with_its_invalidation(self) -> None:
        result = attribute(STRUCTURE, CALM)
        self.assertEqual(result.bucket, vr.PERMITTED)
        self.assertEqual(result.invalidation, "689.50")

    def test_breadth_below_the_line_does_not_veto(self) -> None:
        self.assertEqual(attribute(STRUCTURE, CALM, NARROW_QUIET).bucket, vr.PERMITTED)

    def test_breadth_alone_vetoing_is_attributed_to_breadth(self) -> None:
        result = attribute(STRUCTURE, CALM, NARROW)
        self.assertEqual(result.bucket, vr.BREADTH_VETOED)
        # Taken from the counterfactual that qualifies.
        self.assertEqual(result.invalidation, "689.50")

    def test_another_family_vetoing_is_not_a_breadth_veto(self) -> None:
        result = attribute(STRUCTURE, CALM, DIVERGENT)
        self.assertEqual(result.bucket, vr.OTHER_VETOES)
        self.assertIn("momentum", result.reason)

    def test_breadth_and_another_family_together_are_multiple_vetoes(self) -> None:
        result = attribute(STRUCTURE, CALM, NARROW, DIVERGENT)
        self.assertEqual(result.bucket, vr.OTHER_VETOES)
        self.assertIn("participation", result.reason)

    def test_a_missing_confirmation_is_not_reported_as_a_veto(self) -> None:
        result = attribute(STRUCTURE, NARROW)
        self.assertEqual(result.bucket, vr.NO_SETUP)

    def test_aligned_breadth_still_confirms(self) -> None:
        broad = replace(NARROW, direction=Direction.BULLISH)
        self.assertEqual(attribute(STRUCTURE, broad).bucket, vr.PERMITTED)

    def test_structure_below_the_line_is_no_setup(self) -> None:
        weak = replace(STRUCTURE, strength=Decimal("0.59"))
        result = attribute(weak, CALM, NARROW)
        self.assertEqual(result.bucket, vr.NO_SETUP)
        self.assertIn("below", result.reason)

    def test_bearish_structure_is_out_of_scope(self) -> None:
        bearish = replace(STRUCTURE, direction=Direction.BEARISH)
        self.assertEqual(attribute(bearish, NARROW).bucket, vr.OUT_OF_SCOPE)

    def test_no_signals_is_no_setup(self) -> None:
        self.assertEqual(attribute().bucket, vr.NO_SETUP)

    def test_permitted_exactly_when_the_shipped_classifier_qualifies(self) -> None:
        pool = (STRUCTURE, CALM, NARROW, NARROW_QUIET, DIVERGENT,
                replace(NARROW, direction=Direction.BULLISH))
        for size in range(len(pool) + 1):
            for combo in combinations(pool, size):
                ids = [s.signal_id for s in combo]
                if len(ids) != len(set(ids)):
                    continue
                snapshot = vr._snapshot(combo, CLOSE, SESSION, AS_OF)
                qualified = vr._CLASSIFIER.classify(snapshot) is not None
                with self.subTest(signals=ids):
                    self.assertEqual(attribute(*combo).bucket == vr.PERMITTED, qualified)

    def test_the_input_signals_are_not_altered(self) -> None:
        signals = (STRUCTURE, CALM, NARROW)
        before = tuple(replace(s) for s in signals)
        vr.attribute(signals, CLOSE, SESSION, AS_OF)
        self.assertEqual(signals, before)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spy, cls.rsp = load_bars()
        # Sessions late enough in the fixture for a full window.
        cls.days = [str(bar.session) for bar in cls.spy[-60:]]
        cls.readings = {day: 0.12 for day in cls.days}

    def replay(self, **changes):
        args = {"spy": self.spy, "rsp": self.rsp, "readings": self.readings, **changes}
        with mock.patch.object(vr, "COVERED_FROM", self.spy[0].session):
            return vr.replay(args["spy"], args["rsp"], args["readings"])

    def test_every_session_is_measured_and_bucketed(self) -> None:
        rows = self.replay()
        self.assertEqual(len(rows), len(self.days))
        self.assertTrue(all(row.bucket in vr.BUCKETS for row in rows))
        self.assertFalse([row for row in rows if row.bucket == vr.UNMEASURABLE])

    def test_no_bar_from_the_session_or_later_is_read(self) -> None:
        day = self.days[30]
        session = date.fromisoformat(day)
        later = [replace(bar, close=bar.close * 2, low=bar.low * 2, high=bar.high * 2)
                 if bar.session >= session else bar for bar in self.spy]
        original = {row.session: row for row in self.replay()}[day]
        altered = {row.session: row for row in self.replay(spy=later)}[day]
        self.assertEqual(original, altered)
        self.assertLess(original.completed, day)

    def test_a_session_without_a_reading_is_unmeasurable_not_no_setup(self) -> None:
        readings = dict(self.readings, **{self.days[5]: None})
        row = {r.session: r for r in self.replay(readings=readings)}[self.days[5]]
        self.assertEqual((row.bucket, row.reason), (vr.UNMEASURABLE, "no at-the-money reading"))

    def test_a_missing_rsp_bar_is_unmeasurable(self) -> None:
        completed = {r.session: r for r in self.replay()}[self.days[5]].completed
        rsp = [bar for bar in self.rsp if str(bar.session) != completed]
        row = {r.session: r for r in self.replay(rsp=rsp)}[self.days[5]]
        self.assertEqual(row.bucket, vr.UNMEASURABLE)
        self.assertIn("RSP", row.reason)

    def test_a_window_reaching_before_the_cached_bars_is_unmeasurable(self) -> None:
        with mock.patch.object(vr, "COVERED_FROM", date(2100, 1, 1)):
            rows = vr.replay(self.spy, self.rsp, self.readings)
        self.assertTrue(all(row.bucket == vr.UNMEASURABLE for row in rows))

    def test_two_runs_give_the_same_rows(self) -> None:
        self.assertEqual(vr.digest(self.replay()), vr.digest(self.replay()))

    def test_a_stressed_reading_vetoes_what_a_calm_one_permits(self) -> None:
        calm = self.replay()
        permitted = [row.session for row in calm if row.bucket == vr.PERMITTED]
        self.assertTrue(permitted, "the fixture should hold at least one permitted session")
        stressed = self.replay(readings={day: 0.40 for day in self.days})
        by_day = {row.session: row for row in stressed}
        for day in permitted:
            self.assertNotEqual(by_day[day].bucket, vr.PERMITTED)


class ParityTests(unittest.TestCase):
    def setUp(self) -> None:
        spy, rsp = load_bars()
        self.closes = {str(bar.session): bar.close for bar in spy}
        day = str(spy[-1].session)
        with mock.patch.object(vr, "COVERED_FROM", spy[0].session):
            self.row = vr.replay(spy, rsp, {day: 0.12})[0]
        self.day = day

    def signals_of(self, row: vr.Row) -> tuple[Signal, ...]:
        as_of = vr.decision_moment(date.fromisoformat(row.session))
        return tuple(
            vr.stored_signal({"signal_id": sid, "family": self.family(sid),
                              "direction": d, "strength": st}, as_of)
            for sid, d, st in row.signals
        )

    @staticmethod
    def family(signal_id: str) -> str:
        return {
            "sig-structure-trend-retest": "structure",
            "sig-volatility-regime": "volatility_options",
            "sig-participation-breadth": "participation",
            "sig-momentum-divergence": "momentum",
        }[signal_id]

    def test_the_replay_agrees_with_an_identical_record(self) -> None:
        check = vr.parity([self.row], {self.day: self.signals_of(self.row)}, self.closes)
        self.assertTrue(check["passes"])
        self.assertTrue(check["sessions"][0]["other_signals_identical"])

    def test_a_different_bucket_fails(self) -> None:
        live = (replace(STRUCTURE, as_of=vr.decision_moment(date.fromisoformat(self.day))),)
        row = replace(self.row, bucket=vr.PERMITTED)
        check = vr.parity([row], {self.day: live}, self.closes)
        self.assertFalse(check["passes"])

    def test_a_session_not_replayed_fails(self) -> None:
        check = vr.parity([], {self.day: ()}, self.closes)
        self.assertFalse(check["passes"])


if __name__ == "__main__":
    unittest.main()
