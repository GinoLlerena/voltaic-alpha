"""Trading-calendar-derived entry window.

Addresses `EXIT-012`. Previously an open market was treated as an eligible entry
window, so the agent would enter at 15:59 on a normal session or at 12:59 on a
13:00 early close, leaving no time for the thesis to work or for an exit to fill.

Two rules, and the **earlier** of them governs:

* an absolute cutoff, and
* a session-relative buffer before that day's actual close.

On a normal 16:00 session those coincide at 15:15. On a 13:00 early close the
session-relative rule binds at 12:15, which is the point: a fixed clock time
cannot express "leave enough of the session to get out".

Only trading days appear in the calendar, so a date's absence answers weekends
and holidays without a second source. A date the calendar does not cover is
treated as closed rather than assumed open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")

# --- PROVISIONAL policy values ----------------------------------------------
#: Skip the opening auction and the first prints.
ENTRY_OPEN_BUFFER = timedelta(minutes=15)
#: Absolute latest entry on a full session.
ENTRY_ABSOLUTE_CUTOFF = time(15, 15)
#: Never enter inside this much of the session's actual close.
ENTRY_CLOSE_BUFFER = timedelta(minutes=45)
#: A session closing this much earlier than usual is an early close.
REGULAR_CLOSE = time(16, 0)


class WindowState(str, Enum):  # noqa: UP042 - matches the str-Enum style used project-wide
    OPEN = "open"
    BEFORE_WINDOW = "before_window"
    AFTER_CUTOFF = "after_cutoff"
    NOT_A_TRADING_DAY = "not_a_trading_day"
    UNKNOWN_SESSION = "unknown_session"


@dataclass(frozen=True)
class Session:
    day: date
    open_at: datetime
    close_at: datetime

    @property
    def is_early_close(self) -> bool:
        return self.close_at.astimezone(MARKET_TZ).time() < REGULAR_CLOSE

    def entry_window(self) -> tuple[datetime, datetime]:
        """The interval during which a new entry may be opened."""
        starts = self.open_at + ENTRY_OPEN_BUFFER
        absolute = datetime.combine(
            self.close_at.astimezone(MARKET_TZ).date(),
            ENTRY_ABSOLUTE_CUTOFF,
            tzinfo=MARKET_TZ,
        ).astimezone(UTC)
        relative = self.close_at - ENTRY_CLOSE_BUFFER
        # The earlier of the two, so an early close tightens the window rather
        # than the fixed clock time silently permitting a late entry.
        return starts, min(absolute, relative)


@dataclass(frozen=True)
class WindowDecision:
    state: WindowState
    reason: str
    session: Session | None = None

    @property
    def entry_permitted(self) -> bool:
        return self.state is WindowState.OPEN


def _parse_session(entry: dict[str, Any]) -> Session | None:
    try:
        day = date.fromisoformat(str(entry["date"]))
        open_h, open_m = (int(part) for part in str(entry["open"]).split(":"))
        close_h, close_m = (int(part) for part in str(entry["close"]).split(":"))
    except (KeyError, ValueError):
        return None
    return Session(
        day=day,
        open_at=datetime.combine(day, time(open_h, open_m), tzinfo=MARKET_TZ).astimezone(UTC),
        close_at=datetime.combine(day, time(close_h, close_m), tzinfo=MARKET_TZ).astimezone(UTC),
    )


class TradingCalendar:
    """Sessions keyed by Eastern trading date."""

    def __init__(self, sessions: dict[date, Session]) -> None:
        self._sessions = sessions

    @classmethod
    def from_payload(cls, payload: Any) -> TradingCalendar:
        raw = payload.get("sessions") if isinstance(payload, dict) else payload
        sessions: dict[date, Session] = {}
        for entry in raw or []:
            if not isinstance(entry, dict):
                continue
            session = _parse_session(entry)
            if session is not None:
                sessions[session.day] = session
        return cls(sessions)

    def __len__(self) -> int:
        return len(self._sessions)

    def session_for(self, moment: datetime) -> Session | None:
        return self._sessions.get(moment.astimezone(MARKET_TZ).date())

    def is_trading_day(self, day: date) -> bool:
        return day in self._sessions

    def completed_sessions_between(self, start: datetime, end: datetime) -> int:
        """Trading sessions that closed strictly between two moments."""
        return sum(
            1 for session in self._sessions.values() if start < session.close_at <= end
        )

    def evaluate_entry(self, moment: datetime) -> WindowDecision:
        """Whether a new entry may be opened at this instant."""
        if not self._sessions:
            return WindowDecision(
                WindowState.UNKNOWN_SESSION,
                "no trading calendar is loaded; entry is refused rather than assumed",
            )

        session = self.session_for(moment)
        if session is None:
            local = moment.astimezone(MARKET_TZ).date()
            return WindowDecision(
                WindowState.NOT_A_TRADING_DAY,
                f"{local.isoformat()} is not a trading session",
            )

        starts, cutoff = session.entry_window()
        local_cutoff = cutoff.astimezone(MARKET_TZ).strftime("%H:%M")
        early = " (early close)" if session.is_early_close else ""

        if moment < starts:
            return WindowDecision(
                WindowState.BEFORE_WINDOW,
                f"entry opens at {starts.astimezone(MARKET_TZ).strftime('%H:%M')} ET",
                session,
            )
        if moment > cutoff:
            return WindowDecision(
                WindowState.AFTER_CUTOFF,
                f"entry closed at {local_cutoff} ET{early}; monitoring and risk "
                "reduction remain available",
                session,
            )
        return WindowDecision(
            WindowState.OPEN, f"entry permitted until {local_cutoff} ET{early}", session
        )
