"""Step 4 of the veto backtest: the bot's own selector on a rebuilt chain.

The chain is priced with the pricing model at a known volatility, so the
reconstruction recovers real deltas and the shipped selector, thesis and risk
governor decide as they would live. Each gate after the selector is pinned on
its own: the leg-time limit, the risk budget and the fill bar.
"""

import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest import mock

from options_alpha_lab import veto_entries as ve
from options_alpha_lab import veto_pricing as vp
from options_alpha_lab import veto_reconstruction as recon
from options_alpha_lab import veto_replay as vr
from options_alpha_lab.architecture.contracts import (
    Direction,
    OptionType,
    Signal,
    SignalFamily,
)
from options_alpha_lab.components import LONG_DELTA_BAND, SHORT_DELTA_BAND

SESSION = date(2026, 10, 8)
COMPLETED = date(2026, 10, 7)
SLOTS = ["09:45", "09:50", "09:55", "10:00"]
SPOT = 777.0
CLOSE = Decimal("777.00")
RATE = 0.042
DAYS = 20
VOL = 0.12
SPOT_BARS = {(SESSION.isoformat(), slot): SPOT for slot in SLOTS}
AS_OF = vr.decision_moment(SESSION)


def sig(name: str, family: SignalFamily, strength: str) -> Signal:
    return Signal(f"sig-{name}", family, Direction.BULLISH, Decimal(strength), AS_OF, "t", "t")


SIGNALS = (
    sig("structure-trend-retest", SignalFamily.STRUCTURE, "0.61"),
    sig("volatility-regime", SignalFamily.VOLATILITY_OPTIONS, "0.75"),
)
SETUP = vr.attribute(SIGNALS, CLOSE, COMPLETED, AS_OF).setup


def price(strike: int, slot: str) -> float:
    opened = datetime.combine(SESSION, datetime.strptime(slot, "%H:%M").time(), vp.NEW_YORK)
    years = vp.years_to_expiry(opened + recon.BAR, SESSION + timedelta(days=DAYS))
    return vp.price(OptionType.CALL, SPOT, strike, years, RATE, vp.DIVIDEND_YIELD, VOL)


def chain(decision_slot: str = "09:55", fill: bool = True,
          slot_for: dict[int, str] | None = None) -> dict[str, Any]:
    rows = []
    for strike in range(750, 806):
        slot = (slot_for or {}).get(strike, decision_slot)
        bars: list[Any] = [0, 0, 0, 0]
        bars[SLOTS.index(slot)] = [price(strike, slot), 3]
        if fill:
            bars[3] = [price(strike, "10:00"), 2]
        rows.append([f"SPY{SESSION + timedelta(days=DAYS):%y%m%d}C{strike * 1000:08d}", *bars])
    return {"session": SESSION.isoformat(), "slots": SLOTS, "rows": rows}


def select(data: dict[str, Any] | None) -> ve.Entry:
    assert SETUP is not None
    return ve.select(SESSION.isoformat(), vr.PERMITTED, SETUP, SIGNALS, CLOSE, COMPLETED,
                     data, SPOT_BARS, RATE)


class Quotes(unittest.TestCase):
    def test_half_width_has_a_one_cent_floor(self) -> None:
        self.assertEqual(ve.half_width(Decimal("0.50")), Decimal("0.01"))
        self.assertEqual(ve.half_width(Decimal("10")), Decimal("0.062240"))

    def test_quote_is_symmetric_and_counts_days_as_the_worker(self) -> None:
        reading = recon.Reading("SPY261028C00777000", OptionType.CALL, date(2026, 10, 28),
                                777.0, AS_OF, 10.0, SPOT, VOL, 0.52)
        q = ve.quote(reading, SESSION)
        self.assertEqual((q.bid, q.ask), (Decimal("9.937760"), Decimal("10.062240")))
        self.assertEqual(q.dte, 20)


class Selection(unittest.TestCase):
    def test_enters_with_the_shipped_selector(self) -> None:
        e = select(chain())
        self.assertEqual(e.status, ve.ENTERED)
        assert e.long_delta is not None and e.short_delta is not None
        self.assertTrue(float(LONG_DELTA_BAND[0]) <= e.long_delta <= float(LONG_DELTA_BAND[1]))
        self.assertTrue(float(SHORT_DELTA_BAND[0]) <= e.short_delta <= float(SHORT_DELTA_BAND[1]))
        assert e.width is not None and e.long_strike is not None and e.short_strike is not None
        self.assertGreaterEqual(Decimal(e.width), CLOSE * Decimal("0.005"))
        expected = (Decimal(repr(price(int(float(e.long_strike)), "10:00")))
                    - Decimal(repr(price(int(float(e.short_strike)), "10:00"))))
        self.assertEqual(Decimal(e.fill_reference or "0"), expected)
        self.assertEqual(e.dte, DAYS)

    def test_no_chain(self) -> None:
        self.assertEqual(select(None).status, ve.NO_CHAIN)

    def test_a_leg_missing_from_the_fill_bar_is_unfilled(self) -> None:
        e = select(chain(fill=False))
        self.assertEqual(e.status, ve.UNFILLED)
        self.assertIsNone(e.fill_reference)
        self.assertIsNotNone(e.long_symbol)

    def test_bars_ten_minutes_apart_are_synchronized(self) -> None:
        # With the 15-minute age limit, 10 minutes is the widest gap possible.
        chosen = select(chain())
        assert chosen.long_strike is not None
        long_strike = int(float(chosen.long_strike))
        e = select(chain(slot_for={long_strike: "09:45"}))
        self.assertEqual(e.leg_gap_minutes, 10.0)
        self.assertEqual(e.status, ve.ENTERED)

    def test_the_risk_budget_is_the_shipped_governor(self) -> None:
        with mock.patch.object(ve, "EQUITY", Decimal("10000")):
            e = select(chain())
        self.assertEqual(e.status, ve.RISK_REFUSED)
        self.assertIn("max_loss_exceeds_risk_budget", e.risk_reasons)

    def test_too_few_contracts_find_no_pair(self) -> None:
        data = chain()
        data["rows"] = data["rows"][:3]
        self.assertEqual(select(data).status, ve.NO_PAIR)


if __name__ == "__main__":
    unittest.main()
