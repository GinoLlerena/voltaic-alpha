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
#: Any tag whose key starts with this is read as an attempt at a session lock.
LOCK_TAG_PREFIX = "oa-session"


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
    state to forget. A lock that cannot be read, has no timezone, reaches more
    than 24 hours ahead, or is only partly there (a reason with no expiry, a
    misspelt `oa-session…` key) is INVALID. `decide` never lets an invalid lock
    permit a stop: it asks for the lock to be rewritten to a valid 24-hour one.
    """
    raw = tags.get(LOCK_UNTIL_TAG)
    stray = sorted(
        k for k in tags
        if k.lower().startswith(LOCK_TAG_PREFIX) and k not in (LOCK_UNTIL_TAG, LOCK_REASON_TAG)
    )
    reason = tags.get(LOCK_REASON_TAG, "unspecified")
    if stray:
        return Lock(LockState.INVALID, reason=reason, problem=f"unrecognised lock tag(s) {stray}")
    if raw is None:
        if LOCK_REASON_TAG in tags:
            return Lock(LockState.INVALID, reason=reason, problem="a reason with no expiry")
        return Lock(LockState.NONE)
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
    #: Exposure the worker still owns. While any exists the server stays up,
    #: and that is the system working, not a fault.
    open_positions: int = 0
    working_orders: int = 0
    unresolved_incidents: int = 0

    @property
    def holding(self) -> bool:
        return self.open_positions > 0 or self.working_orders > 0


class Action(str, Enum):  # noqa: UP042 - matches the str-Enum style used project-wide
    START = "start"
    STOP = "stop"
    NONE = "none"


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    alerts: tuple[str, ...] = field(default=())
    #: When set, the handler rewrites the lock to expire here. Only ever for an
    #: invalid lock: it becomes a valid one, honoured and then expiring normally.
    retag_until: datetime | None = None


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

    # (0) An invalid lock is somebody's session, badly written. It never permits
    # a stop, and it is not left to pin the server on for ever either: it is
    # rewritten to the cap, so it is honoured for at most 24 hours and then
    # expires like any other. If the rewrite fails, the server simply stays up.
    if lock.state is LockState.INVALID:
        alerts.append(
            f"session lock was invalid ({lock.problem}); rewritten to expire in "
            f"{MAX_LOCK} — correct it with `session.py`"
        )
        return Decision(
            Action.START if status == "Stopped" else Action.NONE,
            "invalid session lock: held, and rewritten to the cap",
            tuple(alerts),
            retag_until=now + MAX_LOCK,
        )

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
        # (4a) Holding exposure is a reason to stay up, not an alert. A position
        # is held for up to three sessions, and this runs every 15 minutes: an
        # alert per tick would be about sixty a night saying the system is doing
        # what it should, on the channel that also carries "the server did not
        # start" (readiness review PER-R-1, 7 October 2026). An unresolved
        # incident is different and still alerts, held position or not.
        if ready.holding and ready.unresolved_incidents == 0:
            held = []
            if ready.open_positions:
                held.append(f"{ready.open_positions} open position(s)")
            if ready.working_orders:
                held.append(f"{ready.working_orders} working order(s)")
            return Decision(
                Action.NONE, f"holding {' and '.join(held)}; the server stays up", tuple(alerts)
            )
        alerts.append(f"stop skipped: {'; '.join(ready.reasons) or 'not ready'}")
        return Decision(Action.NONE, "not ready to stop", tuple(alerts))

    # (5) Only now.
    return Decision(Action.STOP, "outside the run window, no lock, ready", tuple(alerts))
