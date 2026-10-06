"""What can be learned from recorded outcomes: the read model behind Review.

`PUI4` step 2, approved 6 October 2026 (`docs/improvements/
options_alpha_pui_phase4_read_models_v0_1.md`, §4). Two things that must never
be read as one:

- **Execution outcomes** are closed positions: what was paid, what it was
  closed for, and the result computed from reconciled fills.
- **Research horizons** are what the underlying did after a decision, traded
  or not. They say nothing about trading.

The research journal has one row per market session, not per decision. The
worker decides every few minutes against the last completed daily close, which
does not move intraday, so a day is one evaluation recorded dozens of times;
listing the decisions would present one fact that many times over.

Counts only (owner decision D3). There is no rate, average or score here, and
adding one needs a definition agreed separately.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..calendar import MARKET_TZ, TradingCalendar
from ..outcomes import COMPLETE, HORIZONS, PENDING, UNRESOLVABLE, aware
from ..persistence.models import (
    BrokerOrder,
    Decision,
    DecisionOutcomeRecord,
    ExitDecisionRecord,
    MarketSnapshot,
    OrderIntent,
    Position,
    ReviewJob,
)
from . import positions
from .decision import POSITION_ACTION

ExecutionKind = Literal["closed", "abandoned"]
HORIZON_LABELS = tuple(h.label for h in HORIZONS)


# -- A. execution outcomes ---------------------------------------------------------


@dataclass(frozen=True)
class Execution:
    """One position that is no longer held, and how it ended."""

    view: positions.PositionView
    #: The close order's reconciled average price, per share. None if never closed.
    close_price: Decimal | None
    #: The exit evaluation that produced the close order, when one is recorded.
    exit: ExitDecisionRecord | None
    held: timedelta | None
    sessions_held: int | None


def execution_count(session: Session, kind: ExecutionKind) -> int:
    state = "CLOSED" if kind == "closed" else "ABANDONED"
    return int(session.scalar(
        select(func.count()).select_from(Position).where(Position.lifecycle_status == state)
    ) or 0)


def executions(
    session: Session,
    *,
    kind: ExecutionKind,
    now: datetime,
    calendar: TradingCalendar,
    limit: int = 50,
    before: positions.PositionCursor | None = None,
) -> tuple[list[Execution], positions.PositionCursor | None]:
    """Closed round trips, or entries that never filled, newest first."""
    state = "CLOSED" if kind == "closed" else "ABANDONED"
    stmt = (
        select(Position)
        .where(Position.lifecycle_status == state)
        .order_by(Position.recorded_at.desc(), Position.id.desc())
    )
    if before is not None:
        at, key = before
        stmt = stmt.where(
            (Position.recorded_at < at) | ((Position.recorded_at == at) & (Position.id < key))
        )
    rows = list(session.scalars(stmt.limit(limit + 1)).all())
    shown = rows[:limit]
    after = (shown[-1].recorded_at, shown[-1].id) if len(rows) > limit else None

    # The close order is the position's own when it recorded one. A position
    # closed outside the exit path (the committed lifecycle was closed by hand)
    # names none, so its decision's filled close order is used instead: the
    # same order `realized_from_fills` reads.
    close_ids = {p.id: p.close_order_id for p in shown if p.close_order_id}
    unnamed = {p.decision_id: p.id for p in shown if not p.close_order_id}
    if unnamed:
        for decision_id, order_id in session.execute(
            select(OrderIntent.decision_id, BrokerOrder.id)
            .join(BrokerOrder, BrokerOrder.order_intent_id == OrderIntent.id)
            .where(
                OrderIntent.decision_id.in_(unnamed), BrokerOrder.role == "close",
                BrokerOrder.status == "filled",
            )
        ).all():
            close_ids.setdefault(unnamed[decision_id], order_id)
    order_ids = set(close_ids.values())
    prices: dict[str, Decimal | None] = {
        order_id: None if price is None else Decimal(str(price))
        for order_id, price in session.execute(
            select(BrokerOrder.id, BrokerOrder.filled_avg_price).where(
                BrokerOrder.id.in_(order_ids)
            )
        ).all()
    } if order_ids else {}
    governing: dict[str, ExitDecisionRecord] = {
        e.close_order_id: e
        for e in session.scalars(
            select(ExitDecisionRecord).where(ExitDecisionRecord.close_order_id.in_(order_ids))
        ).all()
        if e.close_order_id
    } if order_ids else {}

    out = []
    for view in positions.views(session, shown, now=now, calendar=calendar):
        p = view.position
        opened, closed = p.opened_at, p.closed_at
        held = aware(closed) - aware(opened) if opened and closed else None
        out.append(Execution(
            view=view,
            close_price=prices.get(close_ids.get(p.id, "")),
            exit=governing.get(close_ids.get(p.id, "")),
            held=held,
            sessions_held=(
                calendar.completed_sessions_between(aware(opened), aware(closed))
                if opened and closed else None
            ),
        ))
    return out, after


# -- B. research horizons, by market session ----------------------------------------


@dataclass(frozen=True)
class Verdict:
    """One distinct outcome reached during a session, and how many times."""

    outcome: Literal["position", "refusal"]
    direction: str
    reason_codes: tuple[str, ...]
    count: int


@dataclass(frozen=True)
class SessionHorizon:
    """What the chosen horizon recorded for a session's decisions. Counts only."""

    label: str
    sessions: int
    resolved: int = 0
    pending: int = 0
    unresolvable: int = 0
    #: Decisions for which no review job exists at this horizon.
    unscheduled: int = 0
    agreed: int = 0
    disagreed: int = 0
    unanswerable: int = 0
    #: Distinct underlying prices at the horizon, and the moves they imply.
    at_horizon: tuple[Decimal, ...] = ()
    smallest_move: Decimal | None = None
    largest_move: Decimal | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class ReviewSession:
    day: date
    open_at: datetime
    close_at: datetime
    decisions: int
    #: Distinct completed closes the session's decisions read. Usually one.
    closes_read: tuple[Decimal, ...] = ()
    verdicts: tuple[Verdict, ...] = ()
    horizon: SessionHorizon | None = None
    first_decided_at: datetime | None = None
    last_decided_at: datetime | None = None
    #: The newest decision of the session, to open as its representative.
    latest_decision_hash: str | None = None


@dataclass(frozen=True)
class SessionPage:
    items: list[ReviewSession] = field(default_factory=list)
    #: The day to continue before, or None when the journal ends.
    next_before: date | None = None
    #: Market sessions from the first recorded decision to now.
    total: int = 0


@dataclass(frozen=True)
class _Decided:
    """The columns of a decision the journal reads; never the whole row."""

    id: str
    decided_at: datetime
    action: str
    direction: str
    reason_codes: list[str] | None
    market_snapshot_id: str
    decision_hash: str


def market_day(moment: datetime) -> date:
    return aware(moment).astimezone(MARKET_TZ).date()


def day_bounds(first: date, last: date) -> tuple[datetime, datetime]:
    """UTC instants bounding the New York days `first`..`last`, inclusive."""
    start = datetime.combine(first, time.min, MARKET_TZ).astimezone(UTC)
    end = datetime.combine(last + timedelta(days=1), time.min, MARKET_TZ).astimezone(UTC)
    return start, end


def _session_days(
    calendar: TradingCalendar, first: date, last: date
) -> list[date]:
    """Trading days from `first` to `last`, newest first."""
    days = []
    day = last
    while day >= first:
        if calendar.is_trading_day(day):
            days.append(day)
        day -= timedelta(days=1)
    return days


def sessions(
    session: Session,
    *,
    calendar: TradingCalendar,
    horizon: str,
    now: datetime,
    limit: int = 20,
    before: date | None = None,
) -> SessionPage:
    """The research journal: one row per market session, newest first.

    Bounded to sessions between the first recorded decision and now, so the
    journal neither invents history before the system existed nor hides a
    session inside that range on which nothing was recorded.
    """
    first_at = session.scalar(select(func.min(Decision.decided_at)))
    if first_at is None:
        return SessionPage()
    every = _session_days(calendar, market_day(first_at), market_day(now))
    days = [d for d in every if before is None or d < before]
    shown = days[:limit]
    if not shown:
        return SessionPage(total=len(every))
    more = len(days) > limit

    start, end = day_bounds(shown[-1], shown[0])
    decisions = [
        _Decided(*row)
        for row in session.execute(
            select(
                Decision.id, Decision.decided_at, Decision.action, Decision.direction,
                Decision.reason_codes, Decision.market_snapshot_id, Decision.decision_hash,
            ).where(Decision.decided_at >= start, Decision.decided_at < end)
        ).all()
    ]
    by_day: dict[date, list[_Decided]] = {}
    for row in decisions:
        by_day.setdefault(market_day(row.decided_at), []).append(row)

    snapshot_ids = {row.market_snapshot_id for row in decisions}
    closes: dict[str, Decimal] = {
        snapshot_id: Decimal(str(price))
        for snapshot_id, price in session.execute(
            select(MarketSnapshot.id, MarketSnapshot.underlying_price).where(
                MarketSnapshot.id.in_(snapshot_ids)
            )
        ).all()
    } if snapshot_ids else {}

    decision_ids = [row.id for row in decisions]
    job_state: dict[str, str] = {
        decision_id: state
        for decision_id, state in session.execute(
            select(ReviewJob.decision_id, ReviewJob.state).where(
                ReviewJob.horizon == horizon, ReviewJob.decision_id.in_(decision_ids)
            )
        ).all()
    } if decision_ids else {}
    outcome_of: dict[str, DecisionOutcomeRecord] = {
        o.decision_id: o
        for o in session.scalars(
            select(DecisionOutcomeRecord).where(
                DecisionOutcomeRecord.horizon == horizon,
                DecisionOutcomeRecord.decision_id.in_(decision_ids),
            )
        ).all()
    } if decision_ids else {}
    horizon_sessions = next((h.sessions for h in HORIZONS if h.label == horizon), 0)

    items = []
    for day in shown:
        market = calendar.session_for(datetime.combine(day, time(12), MARKET_TZ))
        assert market is not None  # noqa: S101 - `day` came from the calendar
        rows = sorted(by_day.get(day, []), key=lambda r: (r.decided_at, r.decision_hash))
        verdicts = Counter(
            (r.action == POSITION_ACTION, r.direction, tuple(sorted(r.reason_codes or [])))
            for r in rows
        )
        outcomes = [outcome_of[r.id] for r in rows if r.id in outcome_of]
        states = Counter(job_state.get(r.id, "UNSCHEDULED") for r in rows)
        moves = [Decimal(str(o.underlying_change)) for o in outcomes]
        items.append(ReviewSession(
            day=day, open_at=market.open_at, close_at=market.close_at,
            decisions=len(rows),
            closes_read=tuple(sorted({
                closes[r.market_snapshot_id] for r in rows
                if r.market_snapshot_id in closes
            })),
            verdicts=tuple(
                Verdict("position" if traded else "refusal", direction, codes, n)
                for (traded, direction, codes), n in sorted(
                    verdicts.items(), key=lambda kv: (-kv[1], kv[0])
                )
            ),
            horizon=SessionHorizon(
                label=horizon, sessions=horizon_sessions,
                resolved=states.get(COMPLETE, 0), pending=states.get(PENDING, 0),
                unresolvable=states.get(UNRESOLVABLE, 0),
                unscheduled=states.get("UNSCHEDULED", 0),
                agreed=sum(1 for o in outcomes if o.direction_agreed is True),
                disagreed=sum(1 for o in outcomes if o.direction_agreed is False),
                unanswerable=sum(1 for o in outcomes if o.direction_agreed is None),
                at_horizon=tuple(sorted({Decimal(str(o.underlying_at_horizon)) for o in outcomes})),
                smallest_move=min(moves) if moves else None,
                largest_move=max(moves) if moves else None,
                observed_at=max((aware(o.observed_source_time) for o in outcomes), default=None),
            ) if rows else None,
            first_decided_at=aware(rows[0].decided_at) if rows else None,
            last_decided_at=aware(rows[-1].decided_at) if rows else None,
            latest_decision_hash=rows[-1].decision_hash if rows else None,
        ))
    return SessionPage(
        items=items, next_before=shown[-1] if more else None, total=len(every)
    )
