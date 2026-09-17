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

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

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


@dataclass(frozen=True)
class DecisionView:
    """Everything one decision produced, and nothing another decision produced."""

    decision: Decision
    snapshot: MarketSnapshot | None
    signals: list[SignalRecord] = field(default_factory=list)
    packs: list[EvidencePack] = field(default_factory=list)
    theses: list[ThesisRecord] = field(default_factory=list)
    spreads: list[SpreadCandidateRecord] = field(default_factory=list)
    risks: list[RiskDecisionRecord] = field(default_factory=list)
    intents: list[OrderIntent] = field(default_factory=list)
    requests: list[PreparedOrderRequest] = field(default_factory=list)
    orders: list[BrokerOrder] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    exits: list[ExitDecisionRecord] = field(default_factory=list)
    model_calls: list[ModelCall] = field(default_factory=list)
    #: `CIIP-VAL-012`. Absent for a decision recorded before the reading
    #: existed, or replayed from a fixture that carries no bars.
    structure: StructureReadingRecord | None = None

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


def load(session: Session, decision: Decision) -> DecisionView:
    """Resolve one decision's lineage. The only constructor for a view."""
    snapshot = session.get(MarketSnapshot, decision.market_snapshot_id)

    intents = list(
        session.scalars(
            select(OrderIntent).where(OrderIntent.decision_id == decision.id)
        ).all()
    )
    intent_ids = [i.id for i in intents]

    orders = (
        list(
            session.scalars(
                select(BrokerOrder).where(BrokerOrder.order_intent_id.in_(intent_ids))
            ).all()
        )
        if intent_ids
        else []
    )
    order_ids = [o.id for o in orders]
    fills = (
        list(
            session.scalars(
                select(Fill).where(Fill.broker_order_id.in_(order_ids))
            ).all()
        )
        if order_ids
        else []
    )
    requests = (
        list(
            session.scalars(
                select(PreparedOrderRequest).where(
                    PreparedOrderRequest.order_intent_id.in_(intent_ids)
                )
            ).all()
        )
        if intent_ids
        else []
    )
    positions = list(
        session.scalars(
            select(Position).where(Position.decision_id == decision.id)
        ).all()
    )
    position_ids = [p.id for p in positions]
    exits = (
        list(
            session.scalars(
                select(ExitDecisionRecord).where(
                    ExitDecisionRecord.position_id.in_(position_ids)
                )
            ).all()
        )
        if position_ids
        else []
    )

    theses = list(
        session.scalars(select(ThesisRecord).where(ThesisRecord.decision_id == decision.id)).all()
    )
    call_ids = [t.model_call_id for t in theses if t.model_call_id]
    model_calls = (
        list(session.scalars(select(ModelCall).where(ModelCall.id.in_(call_ids))).all())
        if call_ids
        else []
    )

    structure = session.scalars(
        select(StructureReadingRecord).where(
            StructureReadingRecord.decision_id == decision.id
        )
    ).one_or_none()

    snapshot_id = decision.market_snapshot_id
    return DecisionView(
        decision=decision,
        snapshot=snapshot,
        signals=list(
            session.scalars(
                select(SignalRecord).where(
                    SignalRecord.market_snapshot_id == snapshot_id
                )
            ).all()
        ),
        packs=list(
            session.scalars(
                select(EvidencePack).where(
                    EvidencePack.market_snapshot_id == snapshot_id
                )
            ).all()
        ),
        theses=theses,
        spreads=list(
            session.scalars(
                select(SpreadCandidateRecord).where(
                    SpreadCandidateRecord.decision_id == decision.id
                )
            ).all()
        ),
        risks=list(
            session.scalars(
                select(RiskDecisionRecord).where(RiskDecisionRecord.decision_id == decision.id)
            ).all()
        ),
        intents=intents,
        requests=requests,
        orders=orders,
        fills=fills,
        positions=positions,
        exits=exits,
        model_calls=model_calls,
        structure=structure,
    )


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


def count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(Decision)) or 0)


def listing(
    session: Session,
    *,
    action: str | None = None,
    limit: int = 50,
    before: DecisionCursor | None = None,
) -> tuple[list[Decision], DecisionCursor | None]:
    """Decisions newest first, one page at a time, keyed on a total order."""
    stmt = select(Decision).order_by(Decision.decided_at.desc(), Decision.decision_hash.desc())
    if action:
        stmt = stmt.where(Decision.action == action)
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
