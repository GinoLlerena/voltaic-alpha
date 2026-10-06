"""Positions across decisions: the read model behind the Positions screen.

`PUI4`, approved 6 October 2026 (`docs/improvements/
options_alpha_pui_phase4_read_models_v0_1.md`). Positions were served only per
decision, inside its lifecycle; there was no way to ask "what exposure exists?"
without knowing which decision to open.

Everything here is selected from a stored row. Nothing is valued: `unrealized`
is the figure the exit logic recorded on its own mark, `realized` is the round
trip computed from reconciled fills, and each is absent rather than zero when
the records cannot support it. A mark is a recorded observation, never a live
price, and `mark_state` says which kind of old it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..calendar import TradingCalendar
from ..outcomes import realized_from_fills
from ..persistence.models import (
    Decision,
    ExitDecisionRecord,
    Incident,
    MarketSnapshot,
    Position,
    PositionObservation,
)
from .status import OPEN_STATES

#: Every state in which exposure exists or is unconfirmed, and its complement.
CLOSED_STATES = ("CLOSED", "ABANDONED")

StateFilter = Literal["open", "closed", "all"]

#: What each lifecycle state means, served so every surface says the same thing.
STATE_MEANING = {
    "PENDING": "Entry submitted; no confirmed fill. Exposure is unknown, not zero.",
    "OPEN": "Reconciled fills establish this exposure.",
    "CLOSING": "A close was submitted; the broker has not confirmed flat.",
    "CLOSED": "The broker confirms flat.",
    "ABANDONED": "The entry ended without a fill. There was never exposure.",
    "INCIDENT": "Local records and the broker disagree. Treat exposure as unknown.",
}

MarkState = Literal["never_observed", "unreadable", "current", "last_session", "stale", "final"]

#: A mark older than this, while the session is open, is stale: five missed
#: cycles of the worker's 60-second position clock (owner decision D4).
STALE_AFTER = timedelta(minutes=5)

PositionCursor = tuple[datetime, str]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def mark_state(
    position: Position,
    observation: PositionObservation | None,
    now: datetime,
    calendar: TradingCalendar,
) -> MarkState:
    """Which kind of observation the newest mark is. See the proposal, §3.5.

    `final` is the one state the proposal's table did not list: a position that
    is closed or abandoned is no longer marked, so its last mark is not stale,
    it is simply the last one.
    """
    if observation is None:
        return "never_observed"
    if position.lifecycle_status in CLOSED_STATES:
        return "final"
    if observation.spread_value is None:
        return "unreadable"
    seen = _aware(observation.observed_at)
    session = calendar.session_for(now)
    if session is not None and session.open_at <= now < session.close_at:
        return "current" if now - seen <= STALE_AFTER else "stale"
    last = calendar.last_closed(now)
    if last is not None and seen >= last.open_at:
        return "last_session"
    return "stale"


@dataclass(frozen=True)
class PositionView:
    """One position with what the records say around it."""

    position: Position
    decision_hash: str | None
    instrument: str | None
    observation: PositionObservation | None
    mark_state: MarkState
    exit: ExitDecisionRecord | None
    #: USD for the round trip, from reconciled fills; None unless both sides filled.
    realized: Decimal | None
    open_incidents: int

    @property
    def state_meaning(self) -> str:
        return STATE_MEANING.get(
            self.position.lifecycle_status, "A state this version does not describe."
        )

    @property
    def is_open(self) -> bool:
        return self.position.lifecycle_status in OPEN_STATES


def _filtered(stmt: Any, state: StateFilter) -> Any:
    if state == "open":
        return stmt.where(Position.lifecycle_status.in_(OPEN_STATES))
    if state == "closed":
        return stmt.where(Position.lifecycle_status.in_(CLOSED_STATES))
    return stmt


def count(session: Session, state: StateFilter = "all") -> int:
    return int(session.scalar(_filtered(select(func.count()).select_from(Position), state)) or 0)


def by_id(session: Session, position_id: str) -> Position | None:
    return session.get(Position, position_id)


_Row = TypeVar("_Row", PositionObservation, ExitDecisionRecord)


def _latest(
    session: Session, model: type[_Row], stamp: Any, ids: Sequence[str]
) -> dict[str, _Row]:
    """The newest row of `model` per position, in one statement however many positions."""
    if not ids:
        return {}
    newest = (
        select(model.position_id, func.max(stamp).label("at"))
        .where(model.position_id.in_(ids))
        .group_by(model.position_id)
        .subquery()
    )
    rows = session.scalars(
        select(model).join(
            newest, (model.position_id == newest.c.position_id) & (stamp == newest.c.at)
        )
    ).all()
    # Two rows can share a timestamp; keep one, deterministically.
    return {row.position_id: row for row in sorted(rows, key=lambda r: r.id)}


def views(
    session: Session, rows: Sequence[Position], *, now: datetime, calendar: TradingCalendar
) -> list[PositionView]:
    """Dress positions with their decision, newest mark, newest exit and incidents."""
    ids = [p.id for p in rows]
    decisions = {
        d.id: d
        for d in session.scalars(
            select(Decision).where(Decision.id.in_({p.decision_id for p in rows}))
        ).all()
    } if rows else {}
    symbols: dict[str, str] = {
        snapshot_id: symbol
        for snapshot_id, symbol in session.execute(
            select(MarketSnapshot.id, MarketSnapshot.symbol).where(
                MarketSnapshot.id.in_({d.market_snapshot_id for d in decisions.values()})
            )
        ).all()
    } if decisions else {}
    marks = _latest(session, PositionObservation, PositionObservation.observed_at, ids)
    exits = _latest(session, ExitDecisionRecord, ExitDecisionRecord.decided_at, ids)
    incidents: dict[str | None, int] = {
        position_id: n
        for position_id, n in session.execute(
            select(Incident.position_id, func.count())
            .where(Incident.position_id.in_(ids), Incident.resolved_at.is_(None))
            .group_by(Incident.position_id)
        ).all()
    } if ids else {}

    out = []
    for p in rows:
        decision = decisions.get(p.decision_id)
        mark = marks.get(p.id)
        exit_row = exits.get(p.id)
        out.append(PositionView(
            position=p,
            decision_hash=decision.decision_hash if decision else None,
            instrument=symbols.get(decision.market_snapshot_id) if decision else None,
            observation=mark,
            mark_state=mark_state(p, mark, now, calendar),
            exit=exit_row,
            # A result exists only for a confirmed round trip; never for a state
            # in which the close is unconfirmed.
            realized=(
                realized_from_fills(session, p.decision_id)
                if p.lifecycle_status == "CLOSED" else None
            ),
            open_incidents=int(incidents.get(p.id, 0)),
        ))
    return out


def page(
    session: Session,
    *,
    state: StateFilter = "all",
    limit: int = 50,
    before: PositionCursor | None = None,
) -> tuple[list[Position], PositionCursor | None]:
    """Positions newest first by when they were recorded, on a total order."""
    stmt = _filtered(
        select(Position).order_by(Position.recorded_at.desc(), Position.id.desc()), state
    )
    if before is not None:
        at, key = before
        stmt = stmt.where(
            (Position.recorded_at < at) | ((Position.recorded_at == at) & (Position.id < key))
        )
    rows = list(session.scalars(stmt.limit(limit + 1)).all())
    shown = rows[:limit]
    after = (shown[-1].recorded_at, shown[-1].id) if len(rows) > limit else None
    return shown, after


def exits_for(session: Session, position_id: str, limit: int = 50) -> list[ExitDecisionRecord]:
    return list(session.scalars(
        select(ExitDecisionRecord)
        .where(ExitDecisionRecord.position_id == position_id)
        .order_by(ExitDecisionRecord.decided_at.desc(), ExitDecisionRecord.id.desc())
        .limit(limit)
    ).all())


def incidents_for(session: Session, position_id: str) -> list[Incident]:
    return list(session.scalars(
        select(Incident)
        .where(Incident.position_id == position_id)
        .order_by(Incident.opened_at.desc())
    ).all())


def observations(
    session: Session,
    position_id: str,
    *,
    limit: int = 50,
    before: PositionCursor | None = None,
) -> tuple[list[PositionObservation], PositionCursor | None]:
    """A position's recorded marks, newest first."""
    stmt = (
        select(PositionObservation)
        .where(PositionObservation.position_id == position_id)
        .order_by(PositionObservation.observed_at.desc(), PositionObservation.id.desc())
    )
    if before is not None:
        at, key = before
        stmt = stmt.where(
            (PositionObservation.observed_at < at)
            | ((PositionObservation.observed_at == at) & (PositionObservation.id < key))
        )
    rows = list(session.scalars(stmt.limit(limit + 1)).all())
    shown = rows[:limit]
    after = (shown[-1].observed_at, shown[-1].id) if len(rows) > limit else None
    return shown, after


def observation_count(session: Session, position_id: str) -> int:
    return int(session.scalar(
        select(func.count()).select_from(PositionObservation)
        .where(PositionObservation.position_id == position_id)
    ) or 0)
