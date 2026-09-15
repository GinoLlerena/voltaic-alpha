"""System-wide book state: positions and incidents, not scoped to a decision.

`RUI-1`. These were ad hoc queries in `app.py`. One definition of "open" now
serves both surfaces. The dashboard had computed its own list using only `OPEN`
and `CLOSING` while `status.open_positions` counts `PENDING` and `INCIDENT` too;
the narrower list was never rendered, so no screen ever disagreed, but the next
person to render it would have inherited a second definition. `OPEN_STATES` is
the status module's, so that cannot happen.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..persistence.models import Incident, Position
from .status import OPEN_STATES


def positions(session: Session) -> list[Position]:
    return list(session.scalars(select(Position).order_by(Position.opened_at.desc())).all())


def open_positions(session: Session) -> list[Position]:
    return [p for p in positions(session) if p.lifecycle_status in OPEN_STATES]


def incidents(session: Session, *, open_only: bool = True) -> list[Incident]:
    stmt = select(Incident).order_by(Incident.opened_at.desc())
    if open_only:
        stmt = stmt.where(Incident.resolved_at.is_(None))
    return list(session.scalars(stmt).all())
