"""Step 5 of the veto backtest: exits decided by the shipped policy, on time.

A small calendar and hand-written leg bars pin each rule: when an observation
exists, how stale a leg may be, when the session stop and the invalidation may
act (never at the close itself), which bar fills an exit, and that each cost
case runs on its own debit.
"""

import unittest
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from options_alpha_lab import veto_entries as ve
from options_alpha_lab import veto_exits as vx
from options_alpha_lab.calendar import MARKET_TZ, TradingCalendar
from options_alpha_lab.veto_replay import PERMITTED

# Thursday 8 Feb to Wednesday 14 Feb 2024; 12 Feb is given an early close.
DAYS = ["2024-02-08", "2024-02-09", "2024-02-12", "2024-02-13", "2024-02-14"]
CALENDAR = TradingCalendar.from_payload({"sessions": [
    {"date": d, "open": "09:30", "close": "13:00" if d == "2024-02-12" else "16:00"}
    for d in DAYS]})
CLOSES = {date(2024, 2, 7): Decimal("500"), **{date.fromisoformat(d): Decimal("500")
                                               for d in DAYS}}
LONG, SHORT = "SPY240301C00495000", "SPY240301C00501000"


def entry(debit: str = "3.00", level: str = "492.50") -> ve.Entry:
    return ve.Entry(session="2024-02-08", group=PERMITTED, status=ve.ENTERED, chain_calls=2,
                    dropped=0, long_symbol=LONG, short_symbol=SHORT, expiration="2024-03-01",
                    dte=22, long_strike="495", short_strike="501", width="6",
                    fill_reference=debit, invalidation=level, reference_close="500")


def path(bars: dict[str, list[tuple[str, str, float]]]) -> dict[str, Any]:
    """`bars` maps a leg to (date, bar opening time, price); volume is 1."""
    return {"last": DAYS[-1], "legs": {LONG: [[d, t, p, 1] for d, t, p in bars.get(LONG, [])],
                                       SHORT: [[d, t, p, 1] for d, t, p in bars.get(SHORT, [])]}}


def both(d: str, t: str, long: float, short: float) -> dict[str, list[tuple[str, str, float]]]:
    return {LONG: [(d, t, long)], SHORT: [(d, t, short)]}


Legs = dict[str, list[tuple[str, str, float]]]


def merge(*parts: Legs) -> Legs:
    out: Legs = {LONG: [], SHORT: []}
    for p in parts:
        for leg, rows in p.items():
            out[leg] += rows
    return out


def run(bars: dict[str, Any], case: str = "optimistic", **kw: str) -> vx.Trade:
    return vx.simulate(entry(**kw), case, path(bars), CALENDAR, CLOSES)


def ny(d: str, hhmm: str) -> str:
    return datetime.combine(date.fromisoformat(d), time.fromisoformat(hhmm),
                            tzinfo=MARKET_TZ).isoformat()


class Observations(unittest.TestCase):
    def test_entry_day_starts_after_the_fill_and_stops_at_the_close(self) -> None:
        moments = vx.observations(CALENDAR, date(2024, 2, 8), date(2024, 2, 8))
        self.assertEqual(moments[0].astimezone(MARKET_TZ).strftime("%H:%M"), "10:10")
        self.assertEqual(moments[-1].astimezone(MARKET_TZ).strftime("%H:%M"), "16:00")
        self.assertEqual(len(moments), 71)

    def test_an_early_close_ends_at_13_00(self) -> None:
        moments = [m for m in vx.observations(CALENDAR, date(2024, 2, 9), date(2024, 2, 12))
                   if m.astimezone(MARKET_TZ).date() == date(2024, 2, 12)]
        self.assertEqual(moments[0].astimezone(MARKET_TZ).strftime("%H:%M"), "09:35")
        self.assertEqual(moments[-1].astimezone(MARKET_TZ).strftime("%H:%M"), "13:00")


class Values(unittest.TestCase):
    def test_a_leg_older_than_15_minutes_is_not_a_value(self) -> None:
        bars = {k: vx.leg_bars([[d, t, p, 1] for d, t, p in rows])
                for k, rows in merge(both("2024-02-08", "10:05", 5.0, 2.0)).items()}
        at = datetime.fromisoformat(ny("2024-02-08", "10:25"))
        self.assertEqual(vx.value_at(bars[LONG], bars[SHORT], at), Decimal("3.0"))
        later = datetime.fromisoformat(ny("2024-02-08", "10:30"))
        self.assertIsNone(vx.value_at(bars[LONG], bars[SHORT], later))

    def test_legs_more_than_10_minutes_apart_are_not_a_value(self) -> None:
        rows = {LONG: [["2024-02-08", "10:05", 5.0, 1]], SHORT: [["2024-02-08", "10:20", 2.0, 1]]}
        long, short = vx.leg_bars(rows[LONG]), vx.leg_bars(rows[SHORT])
        at = datetime.fromisoformat(ny("2024-02-08", "10:25"))
        self.assertIsNone(vx.value_at(long, short, at))


class Rules(unittest.TestCase):
    def test_stop_loss_fills_at_the_next_bar_with_both_legs(self) -> None:
        # Debit 3.00, stop 1.50. 10:10 bar reads 1.40; 10:15 has one leg only;
        # 10:20 has both, at 1.30.
        t = run(merge(both("2024-02-08", "10:10", 3.40, 2.00),
                      {LONG: [("2024-02-08", "10:15", 3.30)]},
                      both("2024-02-08", "10:20", 3.30, 2.00)))
        self.assertEqual((t.status, t.trigger), (vx.CLOSED, "stop_loss"))
        self.assertEqual(t.triggered_at, ny("2024-02-08", "10:15"))
        self.assertEqual(t.exited_at, ny("2024-02-08", "10:25"))
        self.assertEqual(t.result_usd, -170.0)

    def test_session_stop_acts_at_the_open_after_the_third_close(self) -> None:
        # Value 3.10 throughout: neither stop nor target. Closes: 8, 9 and 12 Feb.
        quiet = merge(*(both(d, t, 5.10, 2.00) for d in DAYS[:4]
                        for t in ("09:30", "09:35", "12:55", "15:55")))
        t = run(quiet)
        self.assertEqual(t.trigger, "session_stop")
        # Not at 12 Feb's 13:00 close, but at 13 Feb's first observation.
        self.assertEqual(t.triggered_at, ny("2024-02-13", "09:35"))
        self.assertEqual(t.exited_at, ny("2024-02-13", "09:40"))
        self.assertEqual(t.sessions_held, 3)

    def test_invalidation_is_read_from_the_last_completed_close(self) -> None:
        closes = {**CLOSES, date(2024, 2, 8): Decimal("490")}
        quiet = merge(*(both(d, t, 5.10, 2.00) for d in DAYS[:2]
                        for t in ("09:30", "09:35", "15:55")))
        t = vx.simulate(entry(), "optimistic", path(quiet), CALENDAR, closes)
        self.assertEqual(t.trigger, "invalidation_breached")
        self.assertEqual(t.triggered_at, ny("2024-02-09", "09:35"))

    def test_each_case_runs_on_its_own_debit(self) -> None:
        # Value 6.80 - 2.00 = 4.80. Optimistic: debit 3.00, target
        # 3.00 + 0.6 x 3.00 = 4.80, reached. Pessimistic: debit 3.10, target
        # 3.10 + 0.6 x 2.90 = 4.84 against a value of 4.70, not reached; the
        # session stop, which needs no premium, comes later and finds no fill.
        bars = merge(both("2024-02-08", "10:05", 6.80, 2.00),
                     both("2024-02-08", "10:10", 6.80, 2.00))
        self.assertEqual(run(bars).trigger, "profit_capture")
        pessimistic = run(bars, "pessimistic")
        self.assertEqual((pessimistic.status, pessimistic.trigger),
                         (vx.NO_EXIT_FILL, "session_stop"))

    def test_a_trigger_with_no_later_fill_is_unresolved(self) -> None:
        # No trade at all: the session stop still fires, and nothing fills it.
        t = run({})
        self.assertEqual((t.status, t.trigger), (vx.NO_EXIT_FILL, "session_stop"))
        self.assertIsNone(t.result_usd)

    def test_no_path_is_unresolved_not_dropped(self) -> None:
        t = vx.simulate(entry(), "central", None, CALENDAR, CLOSES)
        self.assertEqual(t.status, vx.NO_PATH)
        self.assertEqual(t.entry_debit, "3.05")


if __name__ == "__main__":
    unittest.main()
