"""What became of a decision, asked once its horizon had actually elapsed.

`CIIP-008`. A decision's quality is not knowable when it is made. The
architecture had an in-memory `DecisionOutcome` describing what the workflow
decided; nothing recorded what was observable afterwards, so every later claim
about the policy -- promotion, ranking, an edge score -- would have rested on
nothing. `CIIP-009` onward depend on this.

Three properties carry the design.

**The same horizons for refusals as for trades.** A `NO_TRADE` gets reviewed on
the same clock as a position. Reviewing only the decisions that traded measures
a policy on the half of its behaviour it already liked, and a refusal-heavy
policy would look better the more it refused.

**No look-ahead, by construction.** The horizon price is a later snapshot's
`underlying_price`, which is the last *completed* daily close -- the same
protection the decision itself used. Enrichment therefore needs no provider
call, and cannot see inside the session it is measuring.

**Append-only.** Enrichment writes a new row and never edits the decision. A
horizon is asked once: re-running the reviewer is a no-op, not a second opinion.

What this deliberately does not do is score. `direction_agreed` is a plain
comparison between a stated direction and a realised move, not a claim that a
decision was right; at this sample size no such claim is available.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calendar import TradingCalendar
from .components import CONTRACT_MULTIPLIER
from .persistence.models import (
    BrokerOrder,
    Decision,
    DecisionOutcomeRecord,
    MarketSnapshot,
    OrderIntent,
    ReviewJob,
)

PENDING = "PENDING"
COMPLETE = "COMPLETE"
UNRESOLVABLE = "UNRESOLVABLE"

TRADE = "TRADE"
NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class Horizon:
    label: str
    sessions: int


#: `T+3` is the strategy's own `exits.SESSION_STOP`, so a decision is reviewed on
#: the clock its exit policy already runs on; `T+1` is the short look. Declared
#: here once and applied to every decision, whatever it decided.
HORIZONS: tuple[Horizon, ...] = (Horizon("T+1", 1), Horizon("T+3", 3))


def aware(moment: datetime) -> datetime:
    """Stored times as UTC-aware.

    PostgreSQL returns timezone-aware datetimes; SQLite -- the committed evidence
    and every test fixture -- returns naive ones for the same column. Comparing
    the two raises, so every stored time passes through here before it is used.
    Values are written UTC, so attaching UTC is a restoration, not a guess.
    """
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def sessions_elapsed(calendar: TradingCalendar, decided_at: datetime, moment: datetime) -> int:
    """Completed trading sessions between a decision and a later moment."""
    start, end = aware(decided_at), aware(moment)
    if end <= start:
        return 0
    return calendar.completed_sessions_between(start, end)


def direction_agreed(direction: str, change: Decimal) -> bool | None:
    """Whether a stated direction matched the move. `None` when unanswerable.

    A decision with no direction has nothing to agree with, and an exactly flat
    move answers neither way. Both are recorded as unknown rather than forced
    into a boolean that would later be averaged.
    """
    if change == 0:
        return None
    if direction == "bullish":
        return change > 0
    if direction == "bearish":
        return change < 0
    return None


def realized_from_fills(session: Session, decision_id: str) -> Decimal | None:
    """The round trip's result, computed from recorded fills.

    Both legs of the economics come from `broker_orders.filled_avg_price`, which
    is what the broker reconciled. Returns `None` unless the decision produced
    both a filled entry and a filled close: a half-round-trip has no result yet,
    and a zero would read as break-even.

    Deliberately not taken from the committed receipt's `realized`. That number
    is an account-equity delta and differs from the fills by 0.10 on the one
    lifecycle recorded (`CIIP-VAL-011`); a figure this file writes into a
    database must be reproducible from the records it cites.
    """
    orders = session.scalars(
        select(BrokerOrder)
        .join(OrderIntent, OrderIntent.id == BrokerOrder.order_intent_id)
        .where(OrderIntent.decision_id == decision_id)
    ).all()
    by_role = {
        order.role: order
        for order in orders
        if order.status == "filled" and order.filled_avg_price is not None
    }
    entry, close = by_role.get("entry"), by_role.get("close")
    if entry is None or close is None:
        return None
    quantity = Decimal(str(entry.filled_quantity or entry.strategy_quantity or 0))
    if quantity == 0:
        return None
    entry_price = Decimal(str(entry.filled_avg_price))
    close_price = Decimal(str(close.filled_avg_price))
    return ((close_price - entry_price) * CONTRACT_MULTIPLIER * quantity).quantize(
        Decimal("0.01")
    )


def ensure_jobs(session: Session, decision: Decision) -> list[ReviewJob]:
    """One review job per horizon for this decision, created once.

    Idempotent: a decision already carrying its jobs gets none added, so a
    reconciling worker can call this on every tick without multiplying questions.
    """
    existing = {
        job.horizon
        for job in session.scalars(
            select(ReviewJob).where(ReviewJob.decision_id == decision.id)
        ).all()
    }
    created: list[ReviewJob] = []
    for horizon in HORIZONS:
        if horizon.label in existing:
            continue
        job = ReviewJob(
            id=uuid.uuid4().hex,
            decision_id=decision.id,
            horizon=horizon.label,
            horizon_sessions=horizon.sessions,
            state=PENDING,
            policy_version=decision.policy_version,
            decided_at=decision.decided_at,
        )
        session.add(job)
        created.append(job)
    return created


def _observation(
    session: Session, calendar: TradingCalendar, job: ReviewJob
) -> tuple[MarketSnapshot, int] | None:
    """The earliest completed close at or after the horizon, or `None`.

    Ordered by `source_time`, so the observation is the first close that
    satisfies the horizon rather than the most recent one available -- taking the
    latest would silently lengthen the horizon as time passed.
    """
    candidates = session.scalars(
        select(MarketSnapshot)
        .where(MarketSnapshot.source_time > job.decided_at)
        .order_by(MarketSnapshot.source_time)
    ).all()
    for snapshot in candidates:
        elapsed = sessions_elapsed(calendar, job.decided_at, aware(snapshot.source_time))
        if elapsed >= job.horizon_sessions:
            return snapshot, elapsed
    return None


@dataclass(frozen=True)
class ReviewSummary:
    completed: int
    still_pending: int

    @property
    def total(self) -> int:
        return self.completed + self.still_pending


def review(
    session: Session, calendar: TradingCalendar, *, now: datetime | None = None
) -> ReviewSummary:
    """Resolve every pending job whose horizon has produced a completed close.

    A job with no qualifying observation stays `PENDING`: the evidence has not
    arrived yet, which is not the same as an outcome and must not be recorded as
    one.
    """
    moment = now or datetime.now(UTC)
    completed = pending = 0
    for job in session.scalars(select(ReviewJob).where(ReviewJob.state == PENDING)).all():
        decision = session.get(Decision, job.decision_id)
        if decision is None:  # pragma: no cover - a foreign key makes this unreachable
            continue
        if sessions_elapsed(calendar, job.decided_at, moment) < job.horizon_sessions:
            pending += 1
            continue
        found = _observation(session, calendar, job)
        if found is None:
            pending += 1
            continue
        snapshot, elapsed = found
        decided_snapshot = session.get(MarketSnapshot, decision.market_snapshot_id)
        if decided_snapshot is None:  # pragma: no cover - a foreign key makes this unreachable
            pending += 1
            continue

        # Idempotent: the unique constraint is the guarantee, this is the courtesy.
        already = session.scalars(
            select(DecisionOutcomeRecord).where(
                DecisionOutcomeRecord.decision_id == decision.id,
                DecisionOutcomeRecord.horizon == job.horizon,
            )
        ).one_or_none()
        if already is None:
            at_decision = Decimal(str(decided_snapshot.underlying_price))
            at_horizon = Decimal(str(snapshot.underlying_price))
            change = at_horizon - at_decision
            traded = decision.action == "OPTIONS_POSITION"
            session.add(
                DecisionOutcomeRecord(
                    id=uuid.uuid4().hex,
                    decision_id=decision.id,
                    review_job_id=job.id,
                    horizon=job.horizon,
                    horizon_sessions=job.horizon_sessions,
                    outcome_kind=TRADE if traded else NO_TRADE,
                    observed_snapshot_id=snapshot.snapshot_id,
                    observed_source_time=aware(snapshot.source_time),
                    sessions_elapsed=elapsed,
                    underlying_at_decision=at_decision,
                    underlying_at_horizon=at_horizon,
                    underlying_change=change,
                    direction_agreed=direction_agreed(decision.direction, change),
                    realized=realized_from_fills(session, decision.id) if traded else None,
                    policy_version=job.policy_version,
                )
            )
        job.state = COMPLETE
        job.resolved_at = moment
        completed += 1
    session.flush()
    return ReviewSummary(completed=completed, still_pending=pending)


def open_positions_unreviewed(session: Session) -> int:
    """Jobs still waiting, for a surface that wants to say so."""
    return len(session.scalars(select(ReviewJob).where(ReviewJob.state == PENDING)).all())
