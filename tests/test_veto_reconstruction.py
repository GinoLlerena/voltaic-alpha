"""The reconstruction decides which contract speaks for a session's volatility.

Prices here are made with the pricing model at a known volatility, so the test
knows the answer the reconstruction has to find, and each rule for dropping a
contract or choosing between two is pinned on its own.
"""

import unittest
from datetime import date, datetime, timedelta
from typing import Any

from options_alpha_lab import veto_pricing as vp
from options_alpha_lab import veto_reconstruction as vr
from options_alpha_lab.architecture.contracts import OptionType

SESSION = date(2026, 10, 8)
SLOTS = ["09:45", "09:50", "09:55", "10:00"]
SPOT = 777.0
RATE = 0.042
RATES = vp.Rates({date(2026, 10, 7): RATE})
SPOT_BARS = {(SESSION.isoformat(), slot): SPOT for slot in SLOTS}
COLUMNS = ["contract_symbol", "bid", "ask", "quote_as_of", "delta", "implied_volatility"]


def _symbol(kind: str, strike: int, days: int = 11) -> str:
    return f"SPY{SESSION + timedelta(days=days):%y%m%d}{kind}{strike * 1000:08d}"


def _price(kind: str, strike: int, volatility: float, slot: str = "09:55", days: int = 11) -> float:
    opened = datetime.combine(SESSION, datetime.strptime(slot, "%H:%M").time(), vp.NEW_YORK)
    years = vp.years_to_expiry(opened + vr.BAR, SESSION + timedelta(days=days))
    option = OptionType.CALL if kind == "C" else OptionType.PUT
    return vp.price(option, SPOT, strike, years, RATE, vp.DIVIDEND_YIELD, volatility)


def _row(kind: str, strike: int, volatility: float, slot: str = "09:55", days: int = 11,
         volume: int = 5) -> list[Any]:
    bars: list[Any] = [0, 0, 0, 0]
    bars[SLOTS.index(slot)] = [_price(kind, strike, volatility, slot, days), volume]
    return [_symbol(kind, strike, days), *bars]


def _options(*rows: list[Any]) -> dict[str, Any]:
    return {"session": SESSION.isoformat(), "slots": SLOTS, "rows": list(rows)}


class ReconstructTests(unittest.TestCase):
    def test_it_recovers_the_volatility_the_price_was_made_with(self) -> None:
        readings, dropped = vr.reconstruct(_options(_row("C", 777, 0.11)), SPOT_BARS, RATE)
        self.assertEqual(sum(dropped.values()), 0)
        self.assertAlmostEqual(readings[0].implied_volatility, 0.11, places=4)
        self.assertGreater(readings[0].delta, 0.45)

    def test_the_latest_traded_bar_before_the_decision_is_the_price(self) -> None:
        row = _row("C", 777, 0.11, slot="09:45")
        row[1 + SLOTS.index("09:55")] = [_price("C", 777, 0.20, "09:55"), 3]
        readings, _ = vr.reconstruct(_options(row), SPOT_BARS, RATE)
        self.assertAlmostEqual(readings[0].implied_volatility, 0.20, places=4)
        self.assertEqual(readings[0].bar_end.strftime("%H:%M"), "10:00")

    def test_the_fill_bar_is_never_read_for_the_decision(self) -> None:
        readings, dropped = vr.reconstruct(
            _options(_row("C", 777, 0.11, slot="10:00")), SPOT_BARS, RATE
        )
        self.assertEqual(readings, [])
        self.assertEqual(dropped["no trade in the 15 minutes before the decision"], 1)

    def test_a_bar_with_no_volume_is_not_a_price(self) -> None:
        readings, dropped = vr.reconstruct(
            _options(_row("C", 777, 0.11, volume=0)), SPOT_BARS, RATE
        )
        self.assertEqual((readings, sum(dropped.values())), ([], 1))

    def test_each_reason_for_dropping_a_contract_is_counted(self) -> None:
        under = _row("C", 700, 0.11)
        under[1 + SLOTS.index("09:55")] = [70.0, 1]  # seven dollars under intrinsic value
        _, dropped = vr.reconstruct(
            _options(_row("C", 777, 0.11, days=5), _row("C", 777, 0.11, days=61), under),
            SPOT_BARS, RATE,
        )
        self.assertEqual(dropped["outside 10 to 60 days to expiry"], 2)
        self.assertEqual(dropped["price below intrinsic value or no volatility in the bounds"], 1)

    def test_no_underlying_bar_drops_the_contract(self) -> None:
        _, dropped = vr.reconstruct(_options(_row("C", 777, 0.11)), {}, RATE)
        self.assertEqual(dropped["no SPY bar for the same five minutes"], 1)


class AtTheMoneyTests(unittest.TestCase):
    def _readings(self, *rows: list[Any]) -> list[vr.Reading]:
        return vr.reconstruct(_options(*rows), SPOT_BARS, RATE)[0]

    def test_the_nearest_strike_wins(self) -> None:
        readings = self._readings(_row("C", 775, 0.12), _row("C", 777, 0.11))
        chosen = vr.at_the_money(readings, 777.22)
        assert chosen is not None
        self.assertEqual(chosen.strike, 777.0)

    def test_a_tie_goes_to_the_nearest_expiry_then_the_call(self) -> None:
        readings = self._readings(
            _row("P", 777, 0.13), _row("C", 777, 0.12, days=12), _row("C", 777, 0.11),
        )
        chosen = vr.at_the_money(readings, 777.22)
        assert chosen is not None
        self.assertEqual(chosen.symbol, _symbol("C", 777))

    def test_two_strikes_equally_far_give_the_lower_one(self) -> None:
        readings = self._readings(_row("C", 778, 0.11), _row("C", 777, 0.12))
        chosen = vr.at_the_money(readings, 777.5)
        assert chosen is not None
        self.assertEqual(chosen.strike, 777.0)

    def test_nothing_priced_is_no_reading(self) -> None:
        self.assertIsNone(vr.at_the_money([], 777.0))


class RegimeTests(unittest.TestCase):
    def test_the_thresholds_belong_to_the_calm_and_stressed_sides(self) -> None:
        self.assertEqual(vr.regime(0.22), "calm")
        self.assertEqual(vr.regime(0.2201), "neither")
        self.assertEqual(vr.regime(0.32), "stressed")


class ParityTests(unittest.TestCase):
    def _snapshot(self, implied: str, delta: str = "0.60") -> dict[str, Any]:
        return {"underlying_price": "777.22", "columns": COLUMNS, "rows": [
            [_symbol("C", 777), "9.9", "10.1", "t", delta, implied],
            [_symbol("P", 777), "9.9", "10.1", "t", "-0.48", "0.5"],
            [_symbol("C", 790), "2.9", "3.1", "t", "0.05", "0.3"],
        ]}

    def _parity(self, snapshot: dict[str, Any], *rows: list[Any]) -> dict[str, Any]:
        day = SESSION.isoformat()
        return vr.parity({"sessions": {day: snapshot}}, {day: _options(*rows)}, SPOT_BARS, RATES)

    def test_the_stored_reading_is_the_first_symbol_at_the_nearest_strike(self) -> None:
        self.assertEqual(
            vr.stored_at_the_money(self._snapshot("0.11")), (_symbol("C", 777), 0.11)
        )

    def test_a_close_reconstruction_passes_all_three_gates(self) -> None:
        report = self._parity(self._snapshot("0.112"), _row("C", 777, 0.11))
        self.assertTrue(report["atm_iv"]["passes"])
        self.assertTrue(report["regime"]["passes"])
        self.assertEqual(report["delta"]["band_contracts"], 1)

    def test_an_error_over_one_volatility_point_fails(self) -> None:
        report = self._parity(self._snapshot("0.13"), _row("C", 777, 0.11))
        self.assertFalse(report["atm_iv"]["passes"])

    def test_a_reading_on_the_other_side_of_a_threshold_fails_the_regime_gate(self) -> None:
        report = self._parity(self._snapshot("0.225"), _row("C", 777, 0.218))
        self.assertTrue(report["atm_iv"]["passes"])
        self.assertFalse(report["regime"]["passes"])

    def test_a_delta_error_over_the_tolerance_fails(self) -> None:
        report = self._parity(self._snapshot("0.11", delta="0.60"), _row("C", 777, 0.11))
        self.assertEqual((report["delta"]["priced"], report["delta"]["within"]), (1, 0))
        self.assertFalse(report["delta"]["passes"])

    def test_a_session_with_no_prices_is_a_failure_not_a_skip(self) -> None:
        day = SESSION.isoformat()
        report = vr.parity({"sessions": {day: self._snapshot("0.11")}}, {}, SPOT_BARS, RATES)
        self.assertFalse(report["atm_iv"]["passes"])
        self.assertFalse(report["regime"]["passes"])
        self.assertIn("no option prices", vr.render(report))


if __name__ == "__main__":
    unittest.main()
