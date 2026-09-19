"""What the review horizons have produced so far, as plain counts.

`CIIP-008` records outcomes; nothing displayed them. This is the read model that
does, and its whole design is about what it refuses to compute.

There is no win rate here, and no field that could be mistaken for one. Over the
recorded evidence a rate would be arithmetic on an empty set: every decision so
far is a refusal, so `direction_agreed` is `NULL` on every row, and a "0%
agreement" or a "100% correct" derived from that would be a sentence about
nothing. Counts can be read honestly at any sample size; a rate cannot.

The summary states what the records show, including the absence: if no position
was ever opened, it says so, and says it from a count rather than from prose
somebody typed once and forgot to update.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..outcomes import COMPLETE, HORIZONS, PENDING
from ..persistence.models import (
    Decision,
    DecisionOutcomeRecord,
    MarketSnapshot,
    Position,
    ReviewJob,
)


@dataclass(frozen=True)
class HorizonCounts:
    """One horizon's tally. Counts only, deliberately."""

    horizon: str
    sessions: int
    resolved: int
    pending: int
    trades: int
    refusals: int
    #: A stated direction that matched, that did not, and the rows where the
    #: question does not arise -- no direction, or an exactly flat move.
    agreed: int
    disagreed: int
    unanswerable: int
    with_realized: int
    smallest_move: Decimal | None
    largest_move: Decimal | None

    @property
    def answerable(self) -> int:
        return self.agreed + self.disagreed


@dataclass(frozen=True)
class ReviewOverview:
    horizons: tuple[HorizonCounts, ...]
    decisions: int
    decisions_reviewed: int
    positions_ever: int
    #: Distinct completed daily closes the decisions were taken from.
    #:
    #: The worker ticks every five minutes, but `underlying_price` is the last
    #: *completed* daily close and does not move intraday, so every decision in
    #: a trading day reads the same input and necessarily reaches the same
    #: verdict. A decision count therefore says how often the system was asked,
    #: not how many times the market was evaluated. This is the second number.
    #:
    #: Counted as distinct close prices, which merges two sessions that closed
    #: at exactly the same price to six decimal places. That direction is the
    #: safe one: it claims less evidence than exists, never more.
    closes_observed: int = 0

    @property
    def resolved(self) -> int:
        return sum(h.resolved for h in self.horizons)

    @property
    def pending(self) -> int:
        return sum(h.pending for h in self.horizons)

    @property
    def caveat(self) -> str:
        """What the numbers do not support, derived from the numbers.

        Written here rather than in a template so it cannot drift from the
        records: the day a position exists, this sentence changes by itself.
        """
        if self.resolved == 0:
            return "No horizon has elapsed yet, so nothing has been reviewed."
        if self.positions_ever == 0:
            return (
                f"All {self.decisions_reviewed} reviewed decisions are refusals: no position "
                "has ever been opened, so there is no realised result and nothing here "
                "measures trading. What is recorded is what the underlying did afterwards."
                f"{self.sampling}"
            )
        answerable = sum(h.answerable for h in self.horizons)
        if answerable == 0:
            return (
                "No reviewed decision stated a direction, so agreement is unanswerable "
                "rather than zero."
            )
        return (
            f"{answerable} of {self.resolved} resolved horizons state a direction that can "
            f"be compared. That is a sample, not a result.{self.sampling}"
        )

    @property
    def sampling(self) -> str:
        """How much less independent the decision count is than it looks.

        The worker asks the same question every five minutes against a daily
        close that does not move until the session ends, so a day contributes
        one evaluation and sixty-odd records of it. Stating the decision count
        without this invites the reading that sixty-five refusals are sixty-five
        pieces of evidence. Empty when the records do not have that shape, so a
        future system that observes intraday says nothing it has not earned.
        """
        if self.closes_observed <= 0 or self.decisions <= self.closes_observed:
            return ""
        per_close = self.decisions / self.closes_observed
        if per_close < 2:
            return ""
        return (
            f" The {self.decisions} decisions rest on {self.closes_observed} distinct "
            f"completed closes — about {per_close:.0f} decisions per close, because the "
            "input is the last completed daily close and does not move intraday."
        )


@dataclass(frozen=True)
class DecisionHorizon:
    """One decision's horizon, resolved or still waiting."""

    horizon: str
    sessions: int
    state: str
    underlying_at_decision: Decimal | None = None
    underlying_at_horizon: Decimal | None = None
    change: Decimal | None = None
    direction_agreed: bool | None = None
    realized: Decimal | None = None
    observed_snapshot_id: str | None = None

    @property
    def resolved(self) -> bool:
        return self.state == COMPLETE


def _count(session: Session, stmt) -> int:  # type: ignore[no-untyped-def]
    return int(session.scalar(stmt) or 0)


def overview(session: Session) -> ReviewOverview:
    counts: list[HorizonCounts] = []
    for horizon in HORIZONS:
        rows = session.scalars(
            select(DecisionOutcomeRecord).where(DecisionOutcomeRecord.horizon == horizon.label)
        ).all()
        moves = [Decimal(str(r.underlying_change)) for r in rows]
        counts.append(
            HorizonCounts(
                horizon=horizon.label,
                sessions=horizon.sessions,
                resolved=len(rows),
                pending=_count(
                    session,
                    select(func.count())
                    .select_from(ReviewJob)
                    .where(ReviewJob.horizon == horizon.label, ReviewJob.state == PENDING),
                ),
                trades=sum(1 for r in rows if r.outcome_kind == "TRADE"),
                refusals=sum(1 for r in rows if r.outcome_kind != "TRADE"),
                agreed=sum(1 for r in rows if r.direction_agreed is True),
                disagreed=sum(1 for r in rows if r.direction_agreed is False),
                unanswerable=sum(1 for r in rows if r.direction_agreed is None),
                with_realized=sum(1 for r in rows if r.realized is not None),
                smallest_move=min(moves) if moves else None,
                largest_move=max(moves) if moves else None,
            )
        )
    reviewed = _count(
        session,
        select(func.count(func.distinct(DecisionOutcomeRecord.decision_id))),
    )
    return ReviewOverview(
        horizons=tuple(counts),
        decisions=_count(session, select(func.count()).select_from(Decision)),
        decisions_reviewed=reviewed,
        positions_ever=_count(session, select(func.count()).select_from(Position)),
        closes_observed=_count(
            session, select(func.count(func.distinct(MarketSnapshot.underlying_price)))
        ),
    )


def for_decision(session: Session, decision: Decision) -> tuple[DecisionHorizon, ...]:
    """Every horizon for one decision, including the ones still waiting.

    A horizon that has not elapsed is shown as waiting rather than omitted: a
    reader who sees only resolved rows cannot tell a decision that was reviewed
    from one whose review has not come due.
    """
    jobs = {
        job.horizon: job
        for job in session.scalars(
            select(ReviewJob).where(ReviewJob.decision_id == decision.id)
        ).all()
    }
    outcomes = {
        row.horizon: row
        for row in session.scalars(
            select(DecisionOutcomeRecord).where(
                DecisionOutcomeRecord.decision_id == decision.id
            )
        ).all()
    }
    out: list[DecisionHorizon] = []
    for horizon in HORIZONS:
        job = jobs.get(horizon.label)
        if job is None:
            continue
        row = outcomes.get(horizon.label)
        if row is None:
            out.append(DecisionHorizon(horizon.label, horizon.sessions, job.state))
            continue
        out.append(
            DecisionHorizon(
                horizon=horizon.label,
                sessions=horizon.sessions,
                state=job.state,
                underlying_at_decision=Decimal(str(row.underlying_at_decision)),
                underlying_at_horizon=Decimal(str(row.underlying_at_horizon)),
                change=Decimal(str(row.underlying_change)),
                direction_agreed=row.direction_agreed,
                realized=None if row.realized is None else Decimal(str(row.realized)),
                observed_snapshot_id=row.observed_snapshot_id,
            )
        )
    return tuple(out)
