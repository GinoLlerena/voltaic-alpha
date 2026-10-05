"""One decision's complete lineage, resolved once and isolated by construction.

`CIIP-006`. The dashboard used to assemble a decision from a dozen ad hoc
queries scattered across five tab bodies. That is how `CIIP-CV-003` happened:
one of those queries forgot its filter, and the mistake was invisible while the
evidence set held a single lifecycle.

The defence here is structural rather than careful. Every collection on
`DecisionView` is reached from one decision id, and `load` is the only way to
build one, so a view cannot contain another decision's records — there is no
code path that would let it. The isolation tests exercise two complete
lifecycles precisely because one lifecycle cannot fail this way.

`snapshot` is intentionally nullable. A decision whose snapshot is absent should
render as a decision with a missing snapshot, not raise on a page a reviewer is
reading.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from functools import cached_property
from typing import Any, Literal, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..persistence.models import (
    BrokerOrder,
    Decision,
    EvidencePack,
    ExitDecisionRecord,
    Fill,
    MarketSnapshot,
    ModelCall,
    OrderIntent,
    Position,
    PreparedOrderRequest,
    RiskDecisionRecord,
    SignalRecord,
    SpreadCandidateRecord,
    StructureReadingRecord,
    ThesisRecord,
)

_Row = TypeVar("_Row")


class DecisionView:
    """Everything one decision produced, and nothing another decision produced.

    `CSA-005`: each part is read from the database the first time it is asked
    for, and kept. The decision page asks eight endpoints about one decision,
    and each used to load all thirteen record sets to map two or three of
    them: 78 statements a page view on a plain decision, 107 on one with a
    lifecycle, repeated every refresh on a host that also runs the worker. A
    part nobody reads is now never queried.

    `load` still returns a fully read view, for callers that keep it after
    their session ends; `lazy` is for a caller that maps a view inside one.
    """

    def __init__(self, session: Session, decision: Decision) -> None:
        self._session = session
        self.decision = decision

    def _all(self, model: type[_Row], *where: Any) -> list[_Row]:
        return list(self._session.scalars(select(model).where(*where)).all())

    @cached_property
    def snapshot(self) -> MarketSnapshot | None:
        return self._session.get(MarketSnapshot, self.decision.market_snapshot_id)

    @cached_property
    def signals(self) -> list[SignalRecord]:
        return self._all(
            SignalRecord, SignalRecord.market_snapshot_id == self.decision.market_snapshot_id
        )

    @cached_property
    def packs(self) -> list[EvidencePack]:
        return self._all(
            EvidencePack, EvidencePack.market_snapshot_id == self.decision.market_snapshot_id
        )

    @cached_property
    def theses(self) -> list[ThesisRecord]:
        return self._all(ThesisRecord, ThesisRecord.decision_id == self.decision.id)

    @cached_property
    def spreads(self) -> list[SpreadCandidateRecord]:
        return self._all(
            SpreadCandidateRecord, SpreadCandidateRecord.decision_id == self.decision.id
        )

    @cached_property
    def risks(self) -> list[RiskDecisionRecord]:
        return self._all(RiskDecisionRecord, RiskDecisionRecord.decision_id == self.decision.id)

    @cached_property
    def intents(self) -> list[OrderIntent]:
        return self._all(OrderIntent, OrderIntent.decision_id == self.decision.id)

    @cached_property
    def requests(self) -> list[PreparedOrderRequest]:
        ids = [i.id for i in self.intents]
        if not ids:
            return []
        return self._all(PreparedOrderRequest, PreparedOrderRequest.order_intent_id.in_(ids))

    @cached_property
    def orders(self) -> list[BrokerOrder]:
        ids = [i.id for i in self.intents]
        return self._all(BrokerOrder, BrokerOrder.order_intent_id.in_(ids)) if ids else []

    @cached_property
    def fills(self) -> list[Fill]:
        ids = [o.id for o in self.orders]
        return self._all(Fill, Fill.broker_order_id.in_(ids)) if ids else []

    @cached_property
    def positions(self) -> list[Position]:
        return self._all(Position, Position.decision_id == self.decision.id)

    @cached_property
    def exits(self) -> list[ExitDecisionRecord]:
        ids = [p.id for p in self.positions]
        return self._all(ExitDecisionRecord, ExitDecisionRecord.position_id.in_(ids)) if ids else []

    @cached_property
    def model_calls(self) -> list[ModelCall]:
        ids = [t.model_call_id for t in self.theses if t.model_call_id]
        return self._all(ModelCall, ModelCall.id.in_(ids)) if ids else []

    @cached_property
    def structure(self) -> StructureReadingRecord | None:
        """`CIIP-VAL-012`. Absent for a decision recorded before the reading
        existed, or replayed from a fixture that carries no bars."""
        return self._session.scalars(
            select(StructureReadingRecord).where(
                StructureReadingRecord.decision_id == self.decision.id
            )
        ).one_or_none()

    # -- questions the tabs ask, answered here rather than re-derived ----------

    @property
    def reached_the_broker(self) -> bool:
        return bool(self.orders)

    @property
    def model_was_called(self) -> bool:
        return bool(self.theses)

    @property
    def order_ids(self) -> set[str]:
        return {order.id for order in self.orders}

    def fills_for(self, order_id: str) -> list[Fill]:
        return [f for f in self.fills if f.broker_order_id == order_id]

    def call_for(self, thesis: ThesisRecord) -> ModelCall | None:
        return next((c for c in self.model_calls if c.id == thesis.model_call_id), None)

    def requests_for(self, intent: OrderIntent) -> list[PreparedOrderRequest]:
        return [r for r in self.requests if r.order_intent_id == intent.id]


#: Every part of a view, in dependency order.
PARTS = (
    "snapshot", "signals", "packs", "theses", "spreads", "risks", "intents", "requests",
    "orders", "fills", "positions", "exits", "model_calls", "structure",
)


def lazy(session: Session, decision: Decision) -> DecisionView:
    """A view that reads each part on first use. Map it before `session` closes."""
    return DecisionView(session, decision)


def load(session: Session, decision: Decision) -> DecisionView:
    """Resolve one decision's whole lineage now; safe to keep after the session."""
    view = DecisionView(session, decision)
    for part in PARTS:
        getattr(view, part)
    return view


SignalRole = Literal["cited", "counter-evidence", "observed, unused"]


def signal_role(
    signal_id: str, direction: str, cited: set[str], setup_direction: str
) -> SignalRole:
    """How one observed signal relates to the qualifying setup.

    `RUI-1`. This lived in the dashboard's render function, which made it an
    interpretation only one surface could perform. Cited evidence supports the
    setup; an uncited signal pointing the other way argues against it; anything
    else was observed and not used.
    """
    if signal_id in cited:
        return "cited"
    if direction != setup_direction:
        return "counter-evidence"
    return "observed, unused"


#: A position in the decision list: `(decided_at, decision_hash)`.
DecisionCursor = tuple[datetime, str]


def by_hash(session: Session, decision_hash: str) -> Decision | None:
    """Look a decision up by the only identifier the schema guarantees unique.

    `RUI-1`. `snapshot_id` is indexed but not unique -- one snapshot can replay
    into several decisions -- so it cannot address a decision in a public
    contract. `decision_hash` carries a unique constraint and is already public.
    """
    return session.scalars(
        select(Decision).where(Decision.decision_hash == decision_hash)
    ).one_or_none()


#: The action that opens a position; every other action is a refusal.
POSITION_ACTION = "OPTIONS_POSITION"

ListOutcome = Literal["position", "refusal"]


def _filtered(stmt: Any, action: str | None, outcome: ListOutcome | None) -> Any:
    if action:
        stmt = stmt.where(Decision.action == action)
    if outcome == "position":
        stmt = stmt.where(Decision.action == POSITION_ACTION)
    elif outcome == "refusal":
        stmt = stmt.where(Decision.action != POSITION_ACTION)
    return stmt


def count(
    session: Session, *, action: str | None = None, outcome: ListOutcome | None = None
) -> int:
    stmt = _filtered(select(func.count()).select_from(Decision), action, outcome)
    return int(session.scalar(stmt) or 0)


def outcome_of(decision: Decision) -> ListOutcome:
    return "position" if decision.action == POSITION_ACTION else "refusal"


def instruments(session: Session, decisions: Sequence[Decision]) -> dict[str, str]:
    """Each decision's observed underlying, in one query rather than one per row."""
    ids = {d.market_snapshot_id for d in decisions}
    if not ids:
        return {}
    rows = session.execute(
        select(MarketSnapshot.id, MarketSnapshot.symbol).where(MarketSnapshot.id.in_(ids))
    ).all()
    symbols = {snapshot_id: symbol for snapshot_id, symbol in rows}
    return {
        d.id: symbols[d.market_snapshot_id] for d in decisions if d.market_snapshot_id in symbols
    }


def listing(
    session: Session,
    *,
    action: str | None = None,
    outcome: ListOutcome | None = None,
    limit: int = 50,
    before: DecisionCursor | None = None,
) -> tuple[list[Decision], DecisionCursor | None]:
    """Decisions newest first, one page at a time, keyed on a total order."""
    stmt = select(Decision).order_by(Decision.decided_at.desc(), Decision.decision_hash.desc())
    stmt = _filtered(stmt, action, outcome)
    if before is not None:
        at, key = before
        stmt = stmt.where(
            (Decision.decided_at < at)
            | ((Decision.decided_at == at) & (Decision.decision_hash < key))
        )
    rows = list(session.scalars(stmt.limit(limit + 1)).all())
    shown = rows[:limit]
    after = (shown[-1].decided_at, shown[-1].decision_hash) if len(rows) > limit else None
    return shown, after
