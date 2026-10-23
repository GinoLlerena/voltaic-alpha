"""Step 3 of the veto backtest: outcomes must be indexed as plan section 4.3 says.

The closes are checked by hand on a small bar series, including the censored
end of the cache and a missing session. The bootstrap is checked where its
answer is known: equal groups, a block covering the whole sequence, and the
same seed giving the same interval.
"""

import math
import unittest
from datetime import date, timedelta
from decimal import Decimal

from options_alpha_lab import veto_outcomes as vo
from options_alpha_lab.evidence import Bar
from options_alpha_lab.veto_replay import BREADTH_VETOED, NO_SETUP, PERMITTED, Row

START = date(2026, 1, 5)


def bars(*closes: str) -> list[Bar]:
    out = []
    for i, c in enumerate(closes):
        price = Decimal(c)
        out.append(Bar(START + timedelta(days=i), price, price, price, price, Decimal("1")))
    return out


def row(index: int, spy: list[Bar], bucket: str = PERMITTED, level: str = "98.50",
        breadth: str | None = None) -> Row:
    """The row deciding on `spy[index]`, which read `spy[index - 1]`."""
    return Row(str(spy[index].session), str(spy[index - 1].session), index, 0.12, "calm",
               (), breadth, None, bucket, "test", level if bucket != NO_SETUP else None)


class Indexing(unittest.TestCase):
    SPY = bars("99.00", "100.00", "101.00", "98.00", "103.00", "104.00")

    def test_hand_worked_example(self) -> None:
        # Decision on day 2: C[-1] = 100 (day 1), C[0] = 101, C[1] = 98, C[2] = 103.
        (o,) = vo.outcomes([row(2, self.SPY)], self.SPY)
        self.assertEqual(o.reference_close, "100.00")
        self.assertEqual(o.closes, ("101.00", "98.00", "103.00"))
        self.assertEqual(o.move_usd, (1.0, -2.0, 3.0))
        self.assertEqual(o.move_pct, (1.0, -2.0, 3.0))
        # 98.00 is below 98.50: breached; the worst close is 98, -2%.
        self.assertTrue(o.breached)
        self.assertEqual(o.worst_pct, -2.0)

    def test_a_close_at_the_level_is_not_a_breach(self) -> None:
        (o,) = vo.outcomes([row(2, self.SPY, level="98.00")], self.SPY)
        self.assertFalse(o.breached)

    def test_censored_horizons_are_none_never_zero(self) -> None:
        (o,) = vo.outcomes([row(5, self.SPY)], self.SPY)
        self.assertEqual(o.closes, ("104.00", None, None))
        self.assertEqual(o.move_pct[1:], (None, None))
        self.assertIsNone(o.breached)
        self.assertIsNone(o.worst_pct)

    def test_other_buckets_are_not_measured(self) -> None:
        self.assertEqual(vo.outcomes([row(2, self.SPY, NO_SETUP)], self.SPY), [])

    def test_a_missing_session_is_refused(self) -> None:
        gapped = self.SPY[:3] + self.SPY[4:]
        bad = Row(str(self.SPY[4].session), str(self.SPY[1].session), 2, 0.1, "calm",
                  (), None, None, PERMITTED, "test", "98.50")
        with self.assertRaises(ValueError):
            vo.outcomes([bad], gapped)


class RealizedVol(unittest.TestCase):
    def test_constant_growth_has_no_volatility(self) -> None:
        closes = [Decimal(100) * Decimal("1.01") ** i for i in range(vo.VOL_WINDOW + 1)]
        self.assertAlmostEqual(vo.realized_vol(closes) or 0.0, 0.0, places=12)

    def test_too_short_a_history_is_none(self) -> None:
        self.assertIsNone(vo.realized_vol([Decimal(100)] * vo.VOL_WINDOW))

    def test_alternating_returns(self) -> None:
        closes = [Decimal(100)]
        for i in range(vo.VOL_WINDOW):
            closes.append(closes[-1] * (Decimal("1.02") if i % 2 == 0 else Decimal("0.98")))
        up, down = math.log(1.02), math.log(0.98)
        rs = [up if i % 2 == 0 else down for i in range(vo.VOL_WINDOW)]
        mean = sum(rs) / len(rs)
        expected = math.sqrt(sum((r - mean) ** 2 for r in rs) / (len(rs) - 1))
        self.assertAlmostEqual(vo.realized_vol(closes) or 0.0, expected, places=12)


def series(n: int, permitted: float, vetoed: float) -> list[vo.Outcome]:
    """Alternating groups over a sequence of n, with a fixed 3-session move each."""
    out = []
    for i in range(n):
        group = PERMITTED if i % 2 == 0 else BREADTH_VETOED
        move = permitted if group == PERMITTED else vetoed
        out.append(vo.Outcome(f"s{i}", i, group, None, "1", "1", ("1", "1", "1"),
                              (move,) * 3, (move,) * 3, False, move, None))
    return out


class Bootstrap(unittest.TestCase):
    def test_equal_groups_give_a_zero_interval(self) -> None:
        c = vo.contrast(40, series(40, 1.0, 1.0), vo.PRIMARY, repetitions=200)
        self.assertEqual((c.difference, c.low, c.high), (0.0, 0.0, 0.0))

    def test_one_block_covering_everything_reproduces_the_estimate(self) -> None:
        found = series(30, 2.0, 0.5)
        c = vo.contrast(30, found, vo.PRIMARY, block=30, repetitions=50)
        self.assertEqual(c.difference, 1.5)
        self.assertAlmostEqual(c.low or 0.0, 1.5)
        self.assertAlmostEqual(c.high or 0.0, 1.5)

    def test_same_seed_same_interval(self) -> None:
        found = [o if o.index % 3 else
                 vo.Outcome(o.session, o.index, o.group, None, "1", "1", ("1",) * 3,
                            (o.index / 10,) * 3, (o.index / 10,) * 3, False, 0.0, None)
                 for o in series(60, 1.0, -1.0)]
        a = vo.contrast(60, found, vo.PRIMARY, block=5, repetitions=300)
        b = vo.contrast(60, found, vo.PRIMARY, block=5, repetitions=300)
        self.assertEqual(a, b)
        self.assertLess(a.low or 0.0, a.high or 0.0)

    def test_gaps_and_censored_values_are_counted_not_filled(self) -> None:
        found = series(20, 1.0, 0.0)
        censored = vo.Outcome("x", 0, PERMITTED, None, "1", "1", ("1", None, None),
                              (1.0, None, None), (1.0, None, None), None, None, None)
        found[0] = censored
        # A sequence of 30: positions 20 to 29 are other buckets, kept as gaps.
        c = vo.contrast(30, found, vo.PRIMARY, repetitions=100)
        self.assertEqual((c.permitted_n, c.permitted_excluded), (9, 1))
        self.assertEqual((c.vetoed_n, c.vetoed_excluded), (10, 0))
        self.assertEqual(c.difference, 1.0)

    def test_percentile_interpolates(self) -> None:
        self.assertEqual(vo._percentile([0.0, 10.0], 0.25), 2.5)
        self.assertEqual(vo._percentile([1.0, 2.0, 3.0], 0.5), 2.0)


class Lines(unittest.TestCase):
    def test_regrouping_uses_the_stored_breadth_strength(self) -> None:
        o = vo.Outcome("s", 0, PERMITTED, "0.65", "1", "1", ("1",) * 3, (0.0,) * 3,
                       (0.0,) * 3, False, 0.0, None)
        self.assertEqual(vo.at_line(Decimal("0.60"))(o), BREADTH_VETOED)
        self.assertEqual(vo.at_line(Decimal("0.70"))(o), PERMITTED)
        none = vo.Outcome("s", 0, PERMITTED, None, "1", "1", ("1",) * 3, (0.0,) * 3,
                          (0.0,) * 3, False, 0.0, None)
        self.assertEqual(vo.at_line(Decimal("0.60"))(none), PERMITTED)

    def test_the_rule_line_matches_the_replay_buckets(self) -> None:
        # At 0.70, regrouping must give back the Step 2 bucket.
        vetoed = vo.Outcome("s", 0, BREADTH_VETOED, "0.70", "1", "1", ("1",) * 3,
                            (0.0,) * 3, (0.0,) * 3, False, 0.0, None)
        self.assertEqual(vo.at_line(Decimal("0.70"))(vetoed), BREADTH_VETOED)


if __name__ == "__main__":
    unittest.main()
