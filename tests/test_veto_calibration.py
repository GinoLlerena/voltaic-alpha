"""`k` sets every synthetic quote in the backtest, so what it counts is pinned."""

import unittest
from decimal import Decimal
from typing import Any

from options_alpha_lab import veto_calibration as vc

COLUMNS = ["contract_symbol", "bid", "ask", "quote_as_of", "delta", "implied_volatility"]
AT = "2026-10-08T14:00:00+00:00"


def _session(*rows: list[Any]) -> dict[str, Any]:
    return {"columns": COLUMNS, "rows": [list(row) for row in rows]}


def _call(strike: int, bid: str, ask: str, delta: str | None) -> list[Any]:
    return [f"SPY261023C{strike * 1000:08d}", bid, ask, AT, delta, "0.15"]


class HalfSpreadTests(unittest.TestCase):
    def test_it_is_half_the_spread_over_the_midpoint(self) -> None:
        self.assertEqual(
            vc.relative_half_spread(Decimal("3.96"), Decimal("4.04")), Decimal("0.01")
        )

    def test_a_missing_bid_or_a_crossed_quote_is_not_a_spread(self) -> None:
        self.assertIsNone(vc.relative_half_spread(Decimal("0"), Decimal("0.05")))
        self.assertIsNone(vc.relative_half_spread(Decimal("4.10"), Decimal("4.00")))


class MeasureTests(unittest.TestCase):
    def test_only_calls_inside_the_two_delta_bands_count(self) -> None:
        put = ["SPY261023P00680000", "1.00", "3.00", AT, "-0.60", "0.15"]
        data = {"sessions": {"2026-10-08": _session(
            _call(670, "3.96", "4.04", "0.60"),   # long band, 1%
            _call(690, "1.94", "2.06", "0.30"),   # short band, 3%
            _call(680, "1.00", "3.00", "0.48"),   # between the bands
            _call(720, "1.00", "3.00", "0.10"),   # below both
            _call(700, "1.00", "3.00", None),     # no delta: fails closed
            put,
        )}}
        report = vc.measure(data)
        self.assertEqual(report["quotes"], 2)
        self.assertEqual(report["k"], Decimal("0.02"))
        self.assertEqual(report["by_band"], {"long": Decimal("0.01"), "short": Decimal("0.03")})

    def test_the_band_edges_are_inside(self) -> None:
        for edge in ("0.55", "0.70", "0.25", "0.40"):
            self.assertIsNotNone(vc.band_of(Decimal(edge)))
        self.assertIsNone(vc.band_of(Decimal("0.41")))

    def test_an_unusable_quote_is_counted_apart_not_dropped_silently(self) -> None:
        data = {"sessions": {"2026-10-08": _session(
            _call(670, "3.96", "4.04", "0.60"), _call(690, "0", "0.05", "0.30"),
        )}}
        report = vc.measure(data)
        self.assertEqual((report["quotes"], report["unusable_quotes"]), (1, 1))

    def test_the_median_is_pooled_over_quotes_not_over_sessions(self) -> None:
        data = {"sessions": {
            "2026-10-07": _session(_call(670, "3.96", "4.04", "0.60")),
            "2026-10-08": _session(
                _call(671, "1.94", "2.06", "0.60"), _call(672, "1.94", "2.06", "0.60"),
            ),
        }}
        report = vc.measure(data)
        self.assertEqual(report["k"], Decimal("0.03"))
        self.assertEqual(report["sessions"], 2)

    def test_no_usable_quote_reports_no_k(self) -> None:
        report = vc.measure({"sessions": {"2026-10-08": _session()}})
        self.assertIsNone(report["k"])
        self.assertIn(str(vc.FALLBACK_K), vc.render(report))


if __name__ == "__main__":
    unittest.main()
