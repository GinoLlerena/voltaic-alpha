"""The scheduled stop's decision, with no cloud calls in it.

Design: docs/improvements/options_alpha_scheduled_stop_design_v0_1.md. The
Function Compute handler that will run this every 15 minutes only gathers the
inputs (instance status and tags, the calendar, stop readiness) and carries out
the returned action; every rule the owner asked to see lives here, where it is
tested.

The order of checks is the point. A session lock is read before anything else,
and stop readiness is asked for last and only when a stop is otherwise due, so
no path reaches `StopInstance` past an active lock (owner, 27 September 2026:
"a scheduled stop must not interrupt an active manual session").
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum

from .calendar import MARKET_TZ, TradingCalendar

#: Before the open: worker start-up, lease, startup reconciliation, first tick.
START_LEAD = timedelta(minutes=60)
#: After the close: SPY options to 16:15 ET, the 17:00 ET backup, its upload.
STOP_LAG = timedelta(minutes=90)
#: No lock may reach further ahead than this; forgetting costs at most a day.
MAX_LOCK = timedelta(hours=24)
#: After a lock ends or expires, one more tick before a stop may happen.
LOCK_GRACE = timedelta(minutes=15)
#: One warning this long before a lock expires.
EXPIRY_WARNING = timedelta(minutes=30)

LOCK_UNTIL_TAG = "oa-session-until"
LOCK_REASON_TAG = "oa-session-reason"


class LockState(str, Enum):  # noqa: UP042 - matches the str-Enum style used project-wide
    NONE = "none"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass(frozen=True)
class Lock:
    state: LockState
    until: datetime | None = None
    reason: str = ""
    problem: str = ""


def read_lock(tags: Mapping[str, str], now: datetime) -> Lock:
    """The owner's session lock, from the instance tags.

    Every lock carries an absolute expiry, so there is no "on until I say off"
    state to forget. One that cannot be read, or reaches more than 24 hours
    ahead, is invalid: ignored and alerted on, never honoured.
    """
    raw = tags.get(LOCK_UNTIL_TAG)
    if raw is None:
        return Lock(LockState.NONE)
    reason = tags.get(LOCK_REASON_TAG, "unspecified")
    try:
        until = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return Lock(LockState.INVALID, reason=reason, problem=f"unparseable expiry {raw!r}")
    if until.tzinfo is None:
        return Lock(LockState.INVALID, reason=reason, problem=f"expiry {raw!r} has no timezone")
    if until <= now:
        return Lock(LockState.EXPIRED, until=until, reason=reason)
    if until - now > MAX_LOCK:
        return Lock(
            LockState.INVALID, until=until, reason=reason,
            problem=f"expiry {raw} is more than {MAX_LOCK} ahead",
        )
    return Lock(LockState.ACTIVE, until=until, reason=reason)


def in_run_window(calendar: TradingCalendar, now: datetime, covered_until: date) -> bool:
    """Whether the schedule wants the server running at `now`.

    A date past the calendar's coverage counts as a trading day: an unknown
    day fails toward the server being available, never toward it being off.
    """
    day = now.astimezone(MARKET_TZ).date()
    if day > covered_until:
        return True
    session = calendar.session_for(now)
    if session is None:
        return False
    return session.open_at - START_LEAD <= now < session.close_at + STOP_LAG


@dataclass(frozen=True)
class Readiness:
    ok: bool
    reasons: tuple[str, ...] = ()


class Action(str, Enum):  # noqa: UP042 - matches the str-Enum style used project-wide
    START = "start"
    STOP = "stop"
    NONE = "none"


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    alerts: tuple[str, ...] = field(default=())


def decide(
    *,
    now: datetime,
    status: str,
    tags: Mapping[str, str],
    calendar: TradingCalendar | None,
    covered_until: date,
    readiness: Callable[[], Readiness],
) -> Decision:
    """One tick: start, stop, or leave the instance as it is.

    `readiness` is called only when a stop is otherwise due, so a lock, the
    schedule or a missing calendar each keep the server running without the
    server even being asked.
    """
    lock = read_lock(tags, now)
    alerts: list[str] = []
    if lock.state is LockState.INVALID:
        alerts.append(f"session lock ignored: {lock.problem}")

    # (1) An active session is never stopped, and a stopped server is started for it.
    if lock.state is LockState.ACTIVE and lock.until is not None:
        if lock.until - now <= EXPIRY_WARNING:
            alerts.append(
                f"{lock.reason} session ends at {lock.until.isoformat()}; "
                "`session.py extend` to keep it"
            )
        if status == "Stopped":
            return Decision(Action.START, f"{lock.reason} session lock", tuple(alerts))
        return Decision(Action.NONE, f"{lock.reason} session lock active", tuple(alerts))

    # (2) Without a calendar the schedule is unknown: never stop on a guess.
    if calendar is None:
        alerts.append("trading calendar unavailable; no stop until it loads")
        return Decision(Action.NONE, "calendar unavailable", tuple(alerts))

    # (3) Inside the schedule, the server runs.
    if in_run_window(calendar, now, covered_until):
        if status == "Stopped":
            return Decision(Action.START, "inside the run window", tuple(alerts))
        return Decision(Action.NONE, "inside the run window", tuple(alerts))

    if status != "Running":
        # Already stopped, or mid-transition: nothing to do this tick.
        return Decision(Action.NONE, f"outside the run window; instance {status}", tuple(alerts))

    # (3b) One grace tick after a lock ends, so a session being wrapped up is not cut off.
    if lock.state is LockState.EXPIRED and lock.until is not None and now < lock.until + LOCK_GRACE:
        return Decision(Action.NONE, "grace after the session lock ended", tuple(alerts))

    # (4) Asked last: the server's own view of whether stopping is safe.
    ready = readiness()
    if not ready.ok:
        alerts.append(f"stop skipped: {'; '.join(ready.reasons) or 'not ready'}")
        return Decision(Action.NONE, "not ready to stop", tuple(alerts))

    # (5) Only now.
    return Decision(Action.STOP, "outside the run window, no lock, ready", tuple(alerts))
