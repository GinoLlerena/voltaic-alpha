"""Runtime status derived from durable records, never from literals.

`CIIP-CV-001`. The dashboard used to render `Order writes: Disabled`,
`Operator approval: Required`, and `Live endpoint: None` as string constants,
which meant the safety strip said the same reassuring thing whether it was
reading a live worker database, a committed fixture, or nothing at all. A status
line that cannot be wrong is not evidence.

The rule here is that an unavailable value renders `UNKNOWN` with a reason.
`UNKNOWN` is louder than a green tile, and that is the point: not knowing
whether writes are enabled is a worse position than knowing they are, and the
display should say so rather than defaulting to the comfortable answer.

Two things are genuinely invariant and are labelled as such rather than being
re-derived per request: the build is Paper-only because the gateway refuses any
resolved endpoint that is not the Paper host, and the dashboard holds no write
path because a static gate fails the build otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..persistence.models import Incident, Position, Run, WorkerLease

Tone = Literal["ok", "warn", "bad", "off", "unknown"]

#: Rendered in place of any value that cannot be sourced from a durable record.
UNKNOWN = "UNKNOWN"

#: States that still owe management, mirroring `lifecycle.active_positions`.
OPEN_STATES = ("PENDING", "OPEN", "CLOSING", "INCIDENT")
_OPEN_STATES = OPEN_STATES


@dataclass(frozen=True)
class StatusItem:
    """One cell of the safety strip, carrying where its value came from."""

    label: str
    value: str
    tone: Tone
    #: Human-readable provenance: a table name, `code invariant`, or `derived`.
    source: str
    #: When the underlying record was written. `None` for invariants.
    observed_at: datetime | None = None
    #: Why the value is unavailable. Set only when `value` is `UNKNOWN`.
    reason: str | None = None

    @property
    def known(self) -> bool:
        return self.value != UNKNOWN


def _age(now: datetime, then: datetime) -> str:
    """Compact age, because a bare timestamp makes a reader do arithmetic."""
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 90:
        return f"{seconds}s ago"
    if seconds < 5400:
        return f"{seconds // 60}m ago"
    if seconds < 172800:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _latest_run(session: Session) -> Run | None:
    return session.scalars(select(Run).order_by(Run.started_at.desc()).limit(1)).first()


def _lease(session: Session) -> WorkerLease | None:
    return session.scalars(
        select(WorkerLease).order_by(WorkerLease.heartbeat_at.desc()).limit(1)
    ).first()


def _unknown(label: str, source: str, reason: str) -> StatusItem:
    return StatusItem(label, UNKNOWN, "unknown", source, None, reason)


def order_writes(session: Session) -> StatusItem:
    """Whether the *worker* may write orders, per the last run it recorded."""
    run = _latest_run(session)
    if run is None:
        return _unknown("Order writes", "runs", "no run has been recorded")
    return StatusItem(
        label="Order writes",
        value="Enabled" if run.trading_enabled else "Disabled",
        tone="warn" if run.trading_enabled else "ok",
        source="runs.trading_enabled",
        observed_at=run.started_at,
    )


def worker_mode(session: Session) -> StatusItem:
    run = _latest_run(session)
    if run is None:
        return _unknown("Worker mode", "runs", "no run has been recorded")
    return StatusItem(
        label="Worker mode",
        value=str(run.bot_mode),
        tone="warn" if run.bot_mode == "paper_execute" else "ok",
        source="runs.bot_mode",
        observed_at=run.started_at,
    )


def worker_liveness(session: Session, *, now: datetime) -> StatusItem:
    """Is a worker actually holding the single-writer lease right now?

    This is the cell the old hardcoded strip could not express at all, and the
    one a reader most wants: a dashboard rendering happily over a database no
    worker has touched for a week should not look identical to a live system.
    """
    lease = _lease(session)
    if lease is None:
        return _unknown("Worker", "worker_leases", "no worker has ever held the lease")
    if lease.released_at is not None:
        return StatusItem(
            "Worker", "Released", "off", "worker_leases.released_at", lease.released_at
        )
    expires = lease.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < now:
        return StatusItem(
            "Worker",
            f"Stale · {_age(now, lease.heartbeat_at)}",
            "bad",
            "worker_leases.expires_at",
            lease.heartbeat_at,
        )
    return StatusItem(
        "Worker",
        f"Live · {_age(now, lease.heartbeat_at)}",
        "ok",
        "worker_leases.heartbeat_at",
        lease.heartbeat_at,
    )


def _count(session: Session, stmt: Select[tuple[int]]) -> int:
    return int(session.scalar(stmt) or 0)


def open_positions(session: Session) -> StatusItem:
    n = _count(
        session,
        select(func.count())
        .select_from(Position)
        .where(Position.lifecycle_status.in_(_OPEN_STATES)),
    )
    return StatusItem(
        "Open positions", str(n), "ok" if n == 0 else "warn", "derived from positions"
    )


def open_incidents(session: Session) -> StatusItem:
    n = _count(
        session,
        select(func.count()).select_from(Incident).where(Incident.resolved_at.is_(None)),
    )
    return StatusItem(
        "Open incidents", str(n), "ok" if n == 0 else "bad", "derived from incidents"
    )


def system_status(session: Session, *, now: datetime | None = None) -> list[StatusItem]:
    """The safety strip, every cell carrying its provenance.

    `Environment` stays a constant because it is one: the gateway refuses any
    resolved endpoint that is not the Paper host, checked against the client
    about to be used rather than the flag that configured it. That is a
    code-level guarantee, not an observation, and it is labelled that way.
    """
    stamp = now or datetime.now(UTC)
    return [
        StatusItem(
            "Environment",
            "Paper",
            "ok",
            "code invariant: gateway refuses a non-Paper endpoint",
        ),
        order_writes(session),
        worker_mode(session),
        worker_liveness(session, now=stamp),
        open_positions(session),
        open_incidents(session),
    ]
