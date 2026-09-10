"""Durable activity, read from records rather than narrated by the browser.

`CIIP-006`, completing the read-model set. Two things the plan asks for meet
here: activity must be "server/durable-record derived, never synthesized", and
`app.py` must stop owning cross-table interpretation.

The property worth more than either is the one the records make checkable.
`audit_events.sequence` is contiguous by construction, so a gap is not a display
quirk — it means an event that was supposed to be written was not. A trail
rendered without checking looks complete whether or not it is, which is the
same defect as a status strip that cannot be wrong.

So `Trail` carries `gaps`, and a trail with gaps says so. The dashboard should
never be the last place to learn that its evidence is incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..persistence.models import AuditEvent, Decision


@dataclass(frozen=True)
class ActivityEvent:
    """One recorded transition."""

    sequence: int
    stage: str
    outcome: str
    component: str
    reason_codes: tuple[str, ...]
    occurred_at: datetime
    correlation_id: str

    @property
    def refused(self) -> bool:
        """Outcomes that stopped the pipeline, which a reader should find fast."""
        return self.outcome in {"refused", "rejected", "abandoned", "failed"}


@dataclass(frozen=True)
class Trail:
    """An ordered trail, and whether it is complete."""

    events: tuple[ActivityEvent, ...]
    #: Sequence numbers expected but absent. Empty means the trail is whole.
    gaps: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return not self.gaps

    @property
    def stages(self) -> tuple[str, ...]:
        return tuple(event.stage for event in self.events)

    @property
    def final_outcome(self) -> str | None:
        return self.events[-1].outcome if self.events else None


def _event(row: AuditEvent) -> ActivityEvent:
    return ActivityEvent(
        sequence=int(row.sequence),
        stage=str(row.stage),
        outcome=str(row.outcome),
        component=str(row.component),
        reason_codes=tuple(row.reason_codes or []),
        occurred_at=row.occurred_at,
        correlation_id=str(row.correlation_id),
    )


def _gaps(events: tuple[ActivityEvent, ...]) -> tuple[int, ...]:
    """Sequence numbers missing between the first and last recorded event.

    Deliberately bounded by what was observed rather than assuming a trail
    starts at zero: a decision whose earliest event is 3 may have been recorded
    that way, and inventing 0, 1, 2 as "missing" would be a false alarm about
    a trail we have no evidence was ever longer.
    """
    if len(events) < 2:
        return ()
    seen = {event.sequence for event in events}
    lo, hi = min(seen), max(seen)
    return tuple(n for n in range(lo, hi + 1) if n not in seen)


def for_decision(session: Session, decision: Decision) -> Trail:
    """The trail for one decision, scoped by its correlation id."""
    rows = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.correlation_id == decision.snapshot_id)
        .order_by(AuditEvent.sequence)
    ).all()
    events = tuple(_event(row) for row in rows)
    return Trail(events=events, gaps=_gaps(events))


def recent(session: Session, *, limit: int = 40) -> tuple[ActivityEvent, ...]:
    """The system-wide feed, newest first.

    This is the "visible running-agent state" the competitor reviews found
    persuasive, with the difference that every row here is a durable record. A
    feed assembled in the browser can show whatever the browser was told; this
    one can only show what happened.
    """
    rows = session.scalars(
        select(AuditEvent)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.sequence.desc())
        .limit(limit)
    ).all()
    return tuple(_event(row) for row in rows)
