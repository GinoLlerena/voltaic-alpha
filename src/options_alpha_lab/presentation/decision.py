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

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..persistence.models import (
    BrokerOrder,
    Decision,
    EvidencePack,
    ExitDecisionRecord,
    Fill,
    MarketSnapshot,
    OrderIntent,
    Position,
    PreparedOrderRequest,
    RiskDecisionRecord,
    SignalRecord,
    SpreadCandidateRecord,
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
        theses=list(
            session.scalars(
                select(ThesisRecord).where(ThesisRecord.decision_id == decision.id)
            ).all()
        ),
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
    )
