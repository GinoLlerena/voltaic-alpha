"""Item 6: entry is bounded by the trading calendar, not by "the market is open"."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from options_alpha_lab.calendar import (
    ENTRY_ABSOLUTE_CUTOFF,
    MARKET_TZ,
    TradingCalendar,
    WindowState,
)

ET = ZoneInfo("America/New_York")

# Real sessions from the Alpaca calendar, including two genuine early closes.
SESSIONS = [
    {"date": "2026-08-27", "open": "09:30", "close": "16:00"},
    {"date": "2026-08-28", "open": "09:30", "close": "16:00"},
    {"date": "2026-11-26", "open": "09:30", "close": "16:00"},
    {"date": "2026-11-27", "open": "09:30", "close": "13:00"},  # day after Thanksgiving
    {"date": "2026-12-24", "open": "09:30", "close": "13:00"},  # Christmas Eve
]


def et(day: str, hour: int, minute: int) -> datetime:
    return datetime.combine(
        date.fromisoformat(day), time(hour, minute), tzinfo=ET
    ).astimezone(UTC)


def calendar() -> TradingCalendar:
    return TradingCalendar.from_payload({"sessions": SESSIONS})


class NormalSessionTests(unittest.TestCase):
    def test_entry_is_refused_before_the_opening_buffer(self) -> None:
        decision = calendar().evaluate_entry(et("2026-08-28", 9, 40))
        self.assertIs(decision.state, WindowState.BEFORE_WINDOW)
        self.assertFalse(decision.entry_permitted)

    def test_entry_opens_after_the_buffer(self) -> None:
        self.assertTrue(calendar().evaluate_entry(et("2026-08-28", 9, 45)).entry_permitted)

    def test_entry_is_permitted_mid_session(self) -> None:
        self.assertTrue(calendar().evaluate_entry(et("2026-08-28", 12, 0)).entry_permitted)

    def test_entry_is_refused_at_the_absolute_cutoff(self) -> None:
        cal = calendar()
        self.assertTrue(cal.evaluate_entry(et("2026-08-28", 15, 15)).entry_permitted)
        decision = cal.evaluate_entry(et("2026-08-28", 15, 16))
        self.assertIs(decision.state, WindowState.AFTER_CUTOFF)

    def test_the_final_minute_is_refused(self) -> None:
        # The behaviour that motivated this: an open market is not an eligible
        # entry window at 15:59.
        decision = calendar().evaluate_entry(et("2026-08-28", 15, 59))
        self.assertIs(decision.state, WindowState.AFTER_CUTOFF)
        self.assertIn("monitoring and risk reduction remain available", decision.reason)


class EarlyCloseTests(unittest.TestCase):
    def test_an_early_close_tightens_the_cutoff(self) -> None:
        # 13:00 close minus the 45-minute buffer is 12:15, well before the
        # 15:15 absolute cutoff. A fixed clock time cannot express this.
        cal = calendar()
        self.assertTrue(cal.evaluate_entry(et("2026-11-27", 12, 15)).entry_permitted)
        self.assertIs(
            cal.evaluate_entry(et("2026-11-27", 12, 16)).state, WindowState.AFTER_CUTOFF
        )

    def test_the_absolute_cutoff_would_have_permitted_that_entry(self) -> None:
        # Proves the session-relative rule is doing the work, not the clock time.
        self.assertLess(
            calendar().session_for(et("2026-11-27", 12, 0)).entry_window()[1].astimezone(
                MARKET_TZ
            ).time(),
            ENTRY_ABSOLUTE_CUTOFF,
        )

    def test_an_early_close_is_labelled_in_the_reason(self) -> None:
        decision = calendar().evaluate_entry(et("2026-12-24", 12, 30))
        self.assertIn("early close", decision.reason)

    def test_a_regular_session_is_not_flagged_early(self) -> None:
        session = calendar().session_for(et("2026-08-28", 12, 0))
        assert session is not None
        self.assertFalse(session.is_early_close)


class NonTradingDayTests(unittest.TestCase):
    def test_a_day_absent_from_the_calendar_is_not_a_trading_day(self) -> None:
        # 2026-08-29 is a Saturday and simply is not in the calendar.
        decision = calendar().evaluate_entry(et("2026-08-29", 12, 0))
        self.assertIs(decision.state, WindowState.NOT_A_TRADING_DAY)
        self.assertFalse(decision.entry_permitted)

    def test_a_holiday_is_not_a_trading_day(self) -> None:
        # Thanksgiving 2026-11-26 is present; 2026-11-25 is deliberately absent.
        cal = calendar()
        self.assertTrue(cal.is_trading_day(date(2026, 11, 26)))
        self.assertFalse(cal.is_trading_day(date(2026, 11, 25)))

    def test_an_empty_calendar_refuses_rather_than_assuming_open(self) -> None:
        decision = TradingCalendar.from_payload({"sessions": []}).evaluate_entry(
            et("2026-08-28", 12, 0)
        )
        self.assertIs(decision.state, WindowState.UNKNOWN_SESSION)
        self.assertFalse(decision.entry_permitted)


class SessionCountingTests(unittest.TestCase):
    def test_completed_sessions_skip_weekends_and_holidays(self) -> None:
        cal = calendar()
        # From the 2026-08-27 close to the 2026-11-27 close: 27 Aug is not
        # counted (not strictly after), leaving 28 Aug, 26 Nov, and 27 Nov.
        count = cal.completed_sessions_between(
            et("2026-08-27", 16, 0), et("2026-11-27", 13, 0)
        )
        self.assertEqual(count, 3)

    def test_a_session_still_open_is_not_counted(self) -> None:
        cal = calendar()
        self.assertEqual(
            cal.completed_sessions_between(et("2026-08-28", 9, 45), et("2026-08-28", 15, 0)),
            0,
        )

    def test_a_closed_session_is_counted(self) -> None:
        cal = calendar()
        self.assertEqual(
            cal.completed_sessions_between(et("2026-08-28", 9, 45), et("2026-08-28", 16, 1)),
            1,
        )


class ParsingTests(unittest.TestCase):
    def test_malformed_sessions_are_skipped_rather_than_guessed(self) -> None:
        cal = TradingCalendar.from_payload({"sessions": [
            {"date": "not-a-date", "open": "09:30", "close": "16:00"},
            {"date": "2026-08-28", "open": "bad", "close": "16:00"},
            {"date": "2026-08-28", "open": "09:30", "close": "16:00"},
        ]})
        self.assertEqual(len(cal), 1)

    def test_times_are_interpreted_as_eastern_wall_clock(self) -> None:
        session = calendar().session_for(et("2026-08-28", 12, 0))
        assert session is not None
        self.assertEqual(session.open_at.astimezone(MARKET_TZ).strftime("%H:%M"), "09:30")
        self.assertEqual(session.close_at.astimezone(MARKET_TZ).strftime("%H:%M"), "16:00")


if __name__ == "__main__":
    unittest.main()
