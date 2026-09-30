"""The scheduled stop's decision (design §4, §8.1).

Two questions from the owner are answered here as tests: a scheduled stop must
check for an active demo or development session before calling StopInstance,
and a forgotten override must expire on its own.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, timedelta

from options_alpha_lab.calendar import TradingCalendar
from options_alpha_lab.scheduler import (
    LOCK_REASON_TAG,
    LOCK_UNTIL_TAG,
    Action,
    LockState,
    Readiness,
    decide,
    in_run_window,
    read_lock,
)

CAL = TradingCalendar.from_payload({"sessions": [
    {"date": "2026-03-06", "open": "09:30", "close": "16:00"},   # Friday before DST starts
    {"date": "2026-03-09", "open": "09:30", "close": "16:00"},   # Monday, EDT
    {"date": "2026-09-29", "open": "09:30", "close": "16:00"},
    {"date": "2026-10-30", "open": "09:30", "close": "16:00"},
    {"date": "2026-11-02", "open": "09:30", "close": "16:00"},   # Monday after DST ends, EST
    {"date": "2026-11-25", "open": "09:30", "close": "16:00"},
    # 2026-11-26 Thanksgiving: absent, a holiday
    {"date": "2026-11-27", "open": "09:30", "close": "13:00"},   # early close
]})
COVERED = date(2026, 12, 31)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class Readiness_:
    """A readiness probe that records whether it was asked."""

    def __init__(self, ok: bool = True, *reasons: str) -> None:
        self.calls = 0
        self.result = Readiness(ok, reasons)

    def __call__(self) -> Readiness:
        self.calls += 1
        return self.result


def tick(now: str, status: str = "Running", tags: dict[str, str] | None = None,
         ready: Readiness_ | None = None, calendar: TradingCalendar | None = CAL):
    probe = ready or Readiness_()
    decision = decide(now=utc(now), status=status, tags=tags or {}, calendar=calendar,
                      covered_until=COVERED, readiness=probe)
    return decision, probe


def lock(until: str, reason: str = "dev") -> dict[str, str]:
    return {LOCK_UNTIL_TAG: until, LOCK_REASON_TAG: reason}


class RunWindowTests(unittest.TestCase):
    def test_edt_session_runs_0830_to_1730_eastern(self) -> None:
        # 29 Sep 2026 is EDT (UTC-4): 08:30 ET = 12:30 UTC, 17:30 ET = 21:30 UTC.
        self.assertFalse(in_run_window(CAL, utc("2026-09-29T12:29"), COVERED))
        self.assertTrue(in_run_window(CAL, utc("2026-09-29T12:30"), COVERED))
        self.assertTrue(in_run_window(CAL, utc("2026-09-29T21:29"), COVERED))
        self.assertFalse(in_run_window(CAL, utc("2026-09-29T21:30"), COVERED))

    def test_the_window_follows_daylight_saving_without_a_second_schedule(self) -> None:
        # After DST ends (EST, UTC-5) the same 08:30 ET is an hour later in UTC.
        self.assertFalse(in_run_window(CAL, utc("2026-11-02T12:45"), COVERED))
        self.assertTrue(in_run_window(CAL, utc("2026-11-02T13:30"), COVERED))
        # After DST starts (EDT) it is an hour earlier.
        self.assertTrue(in_run_window(CAL, utc("2026-03-09T12:30"), COVERED))
        self.assertFalse(in_run_window(CAL, utc("2026-03-06T12:30"), COVERED))

    def test_an_early_close_ends_the_window_early(self) -> None:
        # 13:00 ET close (EST) = 18:00 UTC; +90 min = 19:30 UTC.
        self.assertTrue(in_run_window(CAL, utc("2026-11-27T19:29"), COVERED))
        self.assertFalse(in_run_window(CAL, utc("2026-11-27T19:30"), COVERED))

    def test_holidays_and_weekends_are_off(self) -> None:
        self.assertFalse(in_run_window(CAL, utc("2026-11-26T15:00"), COVERED))  # Thanksgiving
        self.assertFalse(in_run_window(CAL, utc("2026-10-03T15:00"), COVERED))  # Saturday

    def test_a_date_past_the_calendar_fails_toward_running(self) -> None:
        self.assertTrue(in_run_window(CAL, utc("2027-01-02T03:00"), COVERED))


class ReadLockTests(unittest.TestCase):
    NOW = utc("2026-10-03T15:00")

    def test_no_tag_is_no_lock(self) -> None:
        self.assertIs(read_lock({}, self.NOW).state, LockState.NONE)

    def test_a_future_expiry_within_the_cap_is_active(self) -> None:
        got = read_lock(lock("2026-10-03T19:00Z", "demo"), self.NOW)
        self.assertEqual((got.state, got.reason), (LockState.ACTIVE, "demo"))

    def test_a_past_expiry_is_expired_and_honoured_as_no_lock(self) -> None:
        self.assertIs(read_lock(lock("2026-10-03T14:59Z"), self.NOW).state, LockState.EXPIRED)

    def test_a_lock_can_never_reach_beyond_24_hours(self) -> None:
        # A typo'd year must not pin the server on: ignored, not honoured.
        for until in ("2026-10-04T15:01Z", "2027-10-03T19:00Z"):
            with self.subTest(until):
                self.assertIs(read_lock(lock(until), self.NOW).state, LockState.INVALID)
        self.assertIs(read_lock(lock("2026-10-04T15:00Z"), self.NOW).state, LockState.ACTIVE)

    def test_unreadable_or_naive_expiries_are_invalid(self) -> None:
        for until in ("tomorrow", "2026-10-03T19:00", ""):
            with self.subTest(until):
                self.assertIs(read_lock(lock(until), self.NOW).state, LockState.INVALID)


class TheCheckBeforeStopInstance(unittest.TestCase):
    """Design §4.1, in order. Every "no" leaves the server running."""

    SATURDAY = "2026-10-03T15:00"  # outside any run window

    def test_an_active_session_is_never_stopped_and_readiness_is_not_even_asked(self) -> None:
        decision, probe = tick(self.SATURDAY, tags=lock("2026-10-03T19:00Z"))
        self.assertIs(decision.action, Action.NONE)
        self.assertEqual(probe.calls, 0)

    def test_a_session_lock_starts_a_stopped_server_outside_hours(self) -> None:
        decision, _ = tick(self.SATURDAY, status="Stopped", tags=lock("2026-10-03T19:00Z"))
        self.assertIs(decision.action, Action.START)

    def test_a_lock_never_shortens_the_schedule(self) -> None:
        # An expired lock inside market hours: the schedule still runs the server.
        decision, _ = tick("2026-09-29T15:00", status="Stopped", tags=lock("2026-09-29T14:00Z"))
        self.assertIs(decision.action, Action.START)

    def test_the_owner_is_warned_before_a_session_expires(self) -> None:
        decision, _ = tick(self.SATURDAY, tags=lock("2026-10-03T15:20Z"))
        self.assertIs(decision.action, Action.NONE)
        self.assertTrue(any("session ends at" in a for a in decision.alerts))

    def test_a_forgotten_session_expires_then_stops_after_one_grace_tick(self) -> None:
        tags = lock("2026-10-03T14:50Z")
        within_grace, probe = tick(self.SATURDAY, tags=tags)          # 10 min after expiry
        self.assertIs(within_grace.action, Action.NONE)
        self.assertEqual(probe.calls, 0)
        after_grace, probe = tick("2026-10-03T15:06", tags=tags)       # 16 min after expiry
        self.assertIs(after_grace.action, Action.STOP)
        self.assertEqual(probe.calls, 1)

    def test_an_invalid_lock_never_permits_a_stop(self) -> None:
        # Owner, 29 Sep 2026: an invalid or unreadable lock must not silently
        # allow a stop during an active session. Each is held, alerted, and
        # rewritten to the 24-hour cap; readiness is never even asked.
        cases = {
            "over the cap": lock("2027-10-03T19:00Z"),
            "unreadable": lock("tomorrow evening"),
            "no timezone": lock("2026-10-03T19:00"),
            "empty": lock(""),
            "reason only": {LOCK_REASON_TAG: "demo"},
            "misspelt key": {"oa-session-untill": "2026-10-03T19:00Z"},
            "wrong case": {"OA-Session-Until": "2026-10-03T19:00Z"},
        }
        for name, tags in cases.items():
            with self.subTest(name):
                decision, probe = tick(self.SATURDAY, tags=tags)
                self.assertIs(decision.action, Action.NONE)
                self.assertEqual(probe.calls, 0)
                self.assertEqual(decision.retag_until, utc(self.SATURDAY) + timedelta(hours=24))
                self.assertTrue(any("invalid" in a for a in decision.alerts))

    def test_an_invalid_lock_on_a_stopped_server_starts_it(self) -> None:
        decision, _ = tick(self.SATURDAY, status="Stopped", tags=lock("tomorrow"))
        self.assertIs(decision.action, Action.START)

    def test_a_rewritten_lock_is_honoured_then_expires_like_any_other(self) -> None:
        rewritten = lock("2026-10-04T15:00Z", "unspecified")      # what the handler writes
        held, _ = tick("2026-10-04T14:00", tags=rewritten)
        self.assertIs(held.action, Action.NONE)
        self.assertIsNone(held.retag_until)                       # valid now: not rewritten again
        stopped, _ = tick("2026-10-04T15:16", tags=rewritten)     # expired, past the grace
        self.assertIs(stopped.action, Action.STOP)

    def test_no_calendar_means_no_stop(self) -> None:
        decision, probe = tick(self.SATURDAY, calendar=None)
        self.assertIs(decision.action, Action.NONE)
        self.assertEqual(probe.calls, 0)

    def test_inside_the_run_window_the_server_is_not_stopped(self) -> None:
        decision, probe = tick("2026-09-29T15:00")
        self.assertIs(decision.action, Action.NONE)
        self.assertEqual(probe.calls, 0)

    def test_exposure_or_a_missing_off_host_copy_blocks_the_stop_and_alerts(self) -> None:
        probe = Readiness_(False, "1 open position", "today's backup not off-host")
        decision, _ = tick(self.SATURDAY, ready=probe)
        self.assertIs(decision.action, Action.NONE)
        self.assertIn("1 open position", decision.alerts[-1])

    def test_only_with_no_lock_outside_hours_and_ready_does_it_stop(self) -> None:
        decision, probe = tick(self.SATURDAY)
        self.assertIs(decision.action, Action.STOP)
        self.assertEqual(probe.calls, 1)

    def test_a_server_mid_transition_is_left_alone(self) -> None:
        for status in ("Starting", "Stopping", "Stopped"):
            with self.subTest(status):
                decision, probe = tick(self.SATURDAY, status=status)
                self.assertIs(decision.action, Action.NONE)
                self.assertEqual(probe.calls, 0)

    def test_the_schedule_starts_the_server_for_a_session(self) -> None:
        decision, _ = tick("2026-09-29T12:45", status="Stopped")
        self.assertIs(decision.action, Action.START)


class ExhaustiveNoStopPastAnInvalidLock(unittest.TestCase):
    def test_no_tick_of_a_weekend_with_an_unreadable_lock_ends_in_a_stop(self) -> None:
        # Even if every rewrite failed and the bad tag stayed, no tick stops.
        tags = lock("next Tuesday")
        now = utc("2026-10-03T04:00")
        while now < utc("2026-10-05T04:00"):
            decision = decide(now=now, status="Running", tags=tags, calendar=CAL,
                              covered_until=COVERED, readiness=lambda: Readiness(True))
            self.assertIsNot(decision.action, Action.STOP, now.isoformat())
            now += timedelta(minutes=15)


class ExhaustiveNoStopPastALock(unittest.TestCase):
    def test_no_minute_of_a_locked_weekend_ends_in_a_stop(self) -> None:
        # Every 15-minute tick of a Saturday under a lock that lasts all day.
        tags = lock("2026-10-04T03:59Z")
        now = utc("2026-10-03T04:00")
        while now < utc("2026-10-04T03:45"):
            decision = decide(now=now, status="Running", tags=tags, calendar=CAL,
                              covered_until=COVERED, readiness=lambda: Readiness(True))
            self.assertIsNot(decision.action, Action.STOP, now.isoformat())
            now += timedelta(minutes=15)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
