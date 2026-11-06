"""Setup follow-through study: the mechanics, on synthetic data."""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal

from options_alpha_lab import study_follow_through as ft
from options_alpha_lab import veto_replay as vr
from options_alpha_lab.evidence import Bar


def bars(closes: list[float]) -> list[Bar]:
    start = date(2026, 1, 1)
    return [Bar(start + timedelta(days=i), Decimal(1), Decimal(1), Decimal(1),
                Decimal(repr(c)), Decimal(1)) for i, c in enumerate(closes)]


def val(x: float | None) -> float:
    assert x is not None
    return x


def row(index: int, completed: Bar | None, bucket: str,
        signals: tuple[tuple[str, str, str], ...] = ()) -> vr.Row:
    return vr.Row(f"s{index}", None if completed is None else str(completed.session), index,
                  None, None, signals, None, None, bucket, "", None)


STRUCT = ("sig-structure-trend-retest", "bullish", "0.70")


class Moves(unittest.TestCase):
    def test_h_is_the_hth_close_after_the_one_read(self) -> None:
        spy = bars([100, 101, 102, 110, 99])
        rows = [row(0, spy[0], vr.NO_SETUP), row(1, spy[2], vr.PERMITTED),
                row(2, None, vr.UNMEASURABLE)]
        m = ft.moves(rows, spy)
        self.assertAlmostEqual(val(m[3][0]), 10.0)  # C[-1]=100 to the third close after, 110
        self.assertAlmostEqual(val(m[1][1]), (110 - 102) / 102 * 100)
        self.assertIsNone(m[3][1])  # censored: only two closes after 102
        self.assertIsNone(m[1][2])

    def test_prior_moves(self) -> None:
        spy = bars([100, 105, 84])
        rows = [row(0, spy[2], vr.PERMITTED), row(1, spy[0], vr.PERMITTED)]
        self.assertAlmostEqual(val(ft.prior_move(rows, spy, 1)[0]), -20.0)
        self.assertAlmostEqual(val(ft.prior_move(rows, spy, 2)[0]), -16.0)
        self.assertIsNone(ft.prior_move(rows, spy, 1)[1])


class Signals(unittest.TestCase):
    def test_confirmation_is_the_strongest_bullish_non_structure(self) -> None:
        r = row(0, None, vr.PERMITTED, (
            ("sig-structure-trend-retest", "bullish", "0.90"),
            ("sig-momentum-divergence", "bullish", "0.55"),
            ("sig-volatility-regime", "bullish", "0.60"),
            ("sig-participation-breadth", "bearish", "0.95")))
        self.assertEqual(ft.confirming_family(r), "volatility")
        self.assertEqual(ft.structure_strength(r), 0.9)

    def test_ties_go_to_the_higher_signal_id_like_the_classifier(self) -> None:
        r = row(0, None, vr.PERMITTED, (
            ("sig-momentum-divergence", "bullish", "0.60"),
            ("sig-participation-breadth", "bullish", "0.60")))
        self.assertEqual(ft.confirming_family(r), "participation")

    def test_below_the_minimum_is_not_a_confirmation(self) -> None:
        r = row(0, None, vr.PERMITTED, (("sig-momentum-divergence", "bullish", "0.49"),))
        self.assertIsNone(ft.confirming_family(r))

    def test_an_unknown_signal_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            ft.confirming_family(row(0, None, vr.PERMITTED, (("sig-new", "bullish", "1"),)))


class Thirds(unittest.TestCase):
    def test_cut_ranks_and_ties_go_low(self) -> None:
        self.assertEqual(ft.cuts([5, 1, 2, 3, 4, 6, 7]), (3, 5))  # ranks 3 and 5 of 7
        cut = ft.cuts([1, 1, 1, 2, 3, 4])
        self.assertEqual(cut, (1, 2))
        self.assertEqual([ft.third(v, cut) for v in (1, 2, 3)], ["lower", "middle", "upper"])

    def test_too_few_values(self) -> None:
        with self.assertRaises(ValueError):
            ft.cuts([1.0, 2.0])


class Report(unittest.TestCase):
    def test_groups_and_unmeasurable_left_out(self) -> None:
        closes = [100 + (i % 7) - (i % 3) for i in range(80)]
        spy = bars([float(c) for c in closes])
        conf = ("sig-momentum-divergence", "bullish", "0.60")
        rows: list[vr.Row] = []
        for i in range(25, 70):
            bucket = (vr.PERMITTED if i % 3 == 0 else vr.BREADTH_VETOED if i % 3 == 1
                      else vr.NO_SETUP if i % 2 else vr.UNMEASURABLE)
            rows.append(row(i - 25, spy[i], bucket, (STRUCT, conf)))
        rep = ft.report(rows, spy, repetitions=50)
        counts = rep["counts"]
        self.assertEqual(counts["qualifying"], 30)
        self.assertEqual(counts["unmeasurable"] + counts["non_qualifying"], 15)
        a = rep["part_a"]["h3_block10"]
        self.assertEqual(a["qualifying_n"] + a["qualifying_censored"], 30)
        self.assertAlmostEqual(a["difference"], a["qualifying_mean"] - a["non_qualifying_mean"])
        self.assertEqual(set(rep["part_a"]), {"h1_block10", "h2_block10", "h3_block10",
                                              "h3_block5", "h3_block20"})
        self.assertEqual(list(rep["part_b"]["D1"]), ["momentum"])
        self.assertNotIn("non_qualifying", rep["part_b"]["D2"])
        self.assertEqual(sum(m["n"] for m in rep["part_b"]["D3"]["qualifying"].values()), 30)


if __name__ == "__main__":
    unittest.main()
