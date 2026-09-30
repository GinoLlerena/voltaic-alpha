"""Whether the server may be stopped now (scheduled-stop design §7).

Asked by the scheduler only when a stop is otherwise due, and last: after the
session lock, the calendar and the run window. It is the server's own account,
read-only, and public-safe: counts and timestamps, no identifiers or broker
detail.

`ok` requires every one of:

* no open position, and no broker order that is not terminal;
* no unresolved incident, which covers unreconciled state;
* a verified backup taken after the last completed session's close;
* that session's copy stored off-host, by the uploader's own record.

Anything unreadable counts against a stop. Stopping is the change that needs
justifying; staying up never does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..calendar import MARKET_TZ, TradingCalendar
from ..offsite import POST_CLOSE_LAG
from ..persistence.models import BrokerOrder, Incident, Position
from .status import _OPEN_STATES


@dataclass(frozen=True)
class StopReadiness:
    ok: bool
    open_positions: int
    working_orders: int
    unresolved_incidents: int
    backup_at: str | None
    backup_verified: bool
    session_due: str | None
    session_copy_off_host: bool
    reasons: tuple[str, ...]


def _read(path: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _at(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def stop_readiness(
    db: Session,
    *,
    now: datetime,
    live: bool,
    backup_file: str,
    offsite_file: str,
    calendar: tuple[TradingCalendar, date],
) -> StopReadiness:
    reasons: list[str] = []
    if not live:
        reasons.append("the API is not reading the live database")

    open_position = Position.lifecycle_status.in_(_OPEN_STATES)
    positions = int(db.scalar(select(func.count()).select_from(Position).where(open_position)) or 0)
    orders = int(db.scalar(
        select(func.count()).select_from(BrokerOrder).where(BrokerOrder.terminal.is_(False))
    ) or 0)
    incidents = int(db.scalar(
        select(func.count()).select_from(Incident).where(Incident.resolved_at.is_(None))
    ) or 0)
    if positions:
        reasons.append(f"{positions} open position(s)")
    if orders:
        reasons.append(f"{orders} working order(s)")
    if incidents:
        reasons.append(f"{incidents} unresolved incident(s)")

    sessions, covered_through = calendar
    covered = now.astimezone(MARKET_TZ).date() <= covered_through
    due = sessions.last_closed(now, POST_CLOSE_LAG) if covered else None
    if due is None:
        reasons.append("no completed session is known for now; the calendar cannot place it")

    backup = _read(backup_file)
    backup_at = _at(backup.get("at")) if backup else None
    verified = bool(backup and backup.get("verified") is True)
    if backup is None:
        reasons.append("the backup record is missing or unreadable")
    elif not verified:
        reasons.append("the latest backup is not verified")
    elif due is not None and (backup_at is None or backup_at < due.close_at + POST_CLOSE_LAG):
        reasons.append(f"no verified backup since the {due.day.isoformat()} close")

    offsite = _read(offsite_file)
    key = f"daily/{due.day.isoformat()}.dump.age" if due else None
    recorded = (offsite.get("keys") or []) if offsite and offsite.get("ok") is True else []
    off_host = key is not None and key in recorded
    if key is not None and not off_host:
        reasons.append(f"{key} is not recorded as off-host")

    return StopReadiness(
        ok=not reasons,
        open_positions=positions,
        working_orders=orders,
        unresolved_incidents=incidents,
        backup_at=backup_at.isoformat() if backup_at else None,
        backup_verified=verified,
        session_due=due.day.isoformat() if due else None,
        session_copy_off_host=off_host,
        reasons=tuple(reasons),
    )
