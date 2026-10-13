"""The reconstruction is only as good as its pricing arithmetic.

Every implied volatility and delta in the veto backtest comes from
`veto_pricing`. These hold it to textbook values and to its own inverse, and
check that an unusable price is refused instead of being forced into the
bounds.
"""

import math
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from options_alpha_lab import veto_pricing as vp
from options_alpha_lab.architecture.contracts import OptionType

CALL, PUT = OptionType.CALL, OptionType.PUT


class PriceTests(unittest.TestCase):
    def test_a_textbook_value(self) -> None:
        # Hull: S 42, K 40, r 10%, sigma 20%, six months.
        self.assertAlmostEqual(vp.price(CALL, 42, 40, 0.5, 0.10, 0.0, 0.20), 4.76, places=2)
        self.assertAlmostEqual(vp.price(PUT, 42, 40, 0.5, 0.10, 0.0, 0.20), 0.81, places=2)

    def test_put_call_parity_with_a_dividend_yield(self) -> None:
        for strike in (600.0, 680.0, 760.0):
            call = vp.price(CALL, 680, strike, 0.08, 0.045, 0.012, 0.16)
            put = vp.price(PUT, 680, strike, 0.08, 0.045, 0.012, 0.16)
            forward = 680 * math.exp(-0.012 * 0.08) - strike * math.exp(-0.045 * 0.08)
            self.assertAlmostEqual(call - put, forward, places=9)

    def test_delta_matches_a_finite_difference(self) -> None:
        for kind in (CALL, PUT):
            up = vp.price(kind, 680.5, 690, 0.08, 0.045, 0.012, 0.16)
            down = vp.price(kind, 679.5, 690, 0.08, 0.045, 0.012, 0.16)
            self.assertAlmostEqual(
                vp.delta(kind, 680, 690, 0.08, 0.045, 0.012, 0.16), up - down, places=4
            )

    def test_call_and_put_delta_differ_by_the_carry(self) -> None:
        call = vp.delta(CALL, 680, 690, 0.08, 0.045, 0.012, 0.16)
        put = vp.delta(PUT, 680, 690, 0.08, 0.045, 0.012, 0.16)
        self.assertAlmostEqual(call - put, math.exp(-0.012 * 0.08), places=12)


class ImpliedVolatilityTests(unittest.TestCase):
    def test_it_inverts_the_price_across_the_range_the_study_uses(self) -> None:
        for kind in (CALL, PUT):
            for strike in (640.0, 680.0, 700.0, 720.0):
                for years in (10 / 365, 30 / 365, 60 / 365):
                    for volatility in (0.08, 0.16, 0.35, 0.90):
                        observed = vp.price(kind, 680, strike, years, 0.045, 0.012, volatility)
                        if observed < 0.05:
                            continue  # a price this small does not identify a volatility
                        intrinsic = max(680 - strike, 0) if kind is CALL else max(strike - 680, 0)
                        if observed <= intrinsic - vp.INTRINSIC_SLACK:
                            # A European put deep in the money is worth less than
                            # intrinsic value. A traded American one is not, so
                            # the study refuses such a price; see the next test.
                            continue
                        with self.subTest(kind=kind, strike=strike, years=years, v=volatility):
                            solved = vp.implied_volatility(
                                kind, observed, 680, strike, years, 0.045
                            )
                            assert solved is not None
                            again = vp.price(kind, 680, strike, years, 0.045, 0.012, solved)
                            self.assertAlmostEqual(again, observed, delta=vp.PRICE_TOLERANCE)

    def test_a_price_under_intrinsic_value_is_refused(self) -> None:
        self.assertIsNone(vp.implied_volatility(CALL, 19.98, 700, 680, 0.05, 0.045))

    def test_a_model_price_under_intrinsic_value_is_refused_too(self) -> None:
        european = vp.price(PUT, 680, 720, 30 / 365, 0.045, 0.012, 0.08)
        self.assertLess(european, 40 - vp.INTRINSIC_SLACK)
        self.assertIsNone(vp.implied_volatility(PUT, european, 680, 720, 30 / 365, 0.045))

    def test_a_price_no_volatility_in_the_bounds_reaches_is_refused(self) -> None:
        ceiling = vp.price(CALL, 680, 680, 0.05, 0.045, 0.012, vp.MAX_VOLATILITY)
        floor = vp.price(CALL, 680, 680, 0.05, 0.045, 0.012, vp.MIN_VOLATILITY)
        self.assertIsNone(vp.implied_volatility(CALL, ceiling + 1.0, 680, 680, 0.05, 0.045))
        self.assertIsNone(vp.implied_volatility(CALL, floor - 0.01, 680, 680, 0.05, 0.045))

    def test_an_expired_or_empty_input_is_refused(self) -> None:
        self.assertIsNone(vp.implied_volatility(CALL, 5.0, 680, 680, 0.0, 0.045))
        self.assertIsNone(vp.implied_volatility(CALL, 0.0, 680, 680, 0.05, 0.045))

    def test_the_bounds_themselves_are_reachable(self) -> None:
        low = vp.price(CALL, 680, 680, 0.1, 0.045, 0.012, vp.MIN_VOLATILITY)
        self.assertEqual(vp.implied_volatility(CALL, low, 680, 680, 0.1, 0.045), vp.MIN_VOLATILITY)


class BrentTests(unittest.TestCase):
    def test_it_finds_a_root_of_a_curved_function(self) -> None:
        root = vp.brent(lambda x: x**3 - 2 * x - 5, 2.0, 3.0, 1e-10)
        assert root is not None
        self.assertAlmostEqual(root, 2.0945514815, places=7)

    def test_no_sign_change_is_no_root(self) -> None:
        self.assertIsNone(vp.brent(lambda x: x * x + 1, -1.0, 1.0, 1e-9))


class TimeTests(unittest.TestCase):
    def test_time_runs_to_the_new_york_close_on_expiry(self) -> None:
        # 10:00 New York in daylight time is 14:00 UTC: six hours to the close.
        at = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
        self.assertAlmostEqual(vp.years_to_expiry(at, date(2026, 10, 9)), 6 / 24 / 365)
        self.assertAlmostEqual(vp.years_to_expiry(at, date(2026, 10, 23)), (14 + 6 / 24) / 365)

    def test_standard_time_is_an_hour_later_in_utc(self) -> None:
        at = datetime(2026, 12, 1, 15, 0, tzinfo=UTC)  # 10:00 New York
        self.assertAlmostEqual(vp.years_to_expiry(at, date(2026, 12, 1)), 6 / 24 / 365)

    def test_after_expiry_it_is_negative(self) -> None:
        at = datetime(2026, 10, 9, 21, 0, tzinfo=UTC)
        self.assertLess(vp.years_to_expiry(at, date(2026, 10, 9)), 0)


class RatesTests(unittest.TestCase):
    def _rates(self) -> vp.Rates:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "DGS3MO.csv"
            path.write_text(
                "observation_date,DGS3MO\n2026-10-08,4.10\n2026-10-09,4.20\n"
                "2026-10-12,.\n2026-10-13,4.30\n"
            )
            return vp.Rates.load(path)

    def test_a_session_never_uses_its_own_days_rate(self) -> None:
        self.assertAlmostEqual(self._rates().before(date(2026, 10, 9)), 0.0410)

    def test_an_unpublished_day_falls_back_to_the_one_before(self) -> None:
        # 12 October is a bond-market holiday: no value, so the 9th stands.
        self.assertAlmostEqual(self._rates().before(date(2026, 10, 13)), 0.0420)

    def test_no_earlier_rate_is_an_error_not_a_guess(self) -> None:
        with self.assertRaises(LookupError):
            self._rates().before(date(2026, 10, 8))


if __name__ == "__main__":
    unittest.main()
