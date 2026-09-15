"""A plain-language answer to "why this decision?", assembled from lineage.

`CIIP-005`. The five tabs already hold everything needed to reconstruct a
decision, but they require the reader to do the reconstruction. This module does
it once, in order, and refuses to say anything the records do not support: every
line it returns names the table it came from, and a stage with no record says so
rather than being skipped silently.

The ordering is deliberate. It answers *what was observed*, then *what the
deterministic setup concluded*, then *what the model contributed*, then *what
risk decided*, then *what reached the broker* — which is the authority sequence,
so reading the summary teaches the boundary without explaining it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..persistence.models import (
    BrokerOrder,
    Decision,
    EvidencePack,
    OrderIntent,
    RiskDecisionRecord,
    ThesisRecord,
)


@dataclass(frozen=True)
class ExplainLine:
    """One step of the answer, with the record that supports it."""

    stage: str
    text: str
    source: str
    #: False when no record exists for this stage — rendered, not omitted.
    present: bool = True


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal | float | int):
        return f"{Decimal(str(value)):.2f}".rstrip("0").rstrip(".")
    return str(value)


def why_decision(session: Session, decision: Decision) -> list[ExplainLine]:
    """Reconstruct one decision as an ordered, sourced explanation."""
    lines: list[ExplainLine] = []

    packs = session.scalars(
        select(EvidencePack).where(
            EvidencePack.market_snapshot_id == decision.market_snapshot_id
        )
    ).all()
    if packs:
        pack = packs[0]
        cited = len(pack.evidence_ids or [])
        lines.append(
            ExplainLine(
                "Observed",
                f"A deterministic classifier ({pack.classifier_name}) identified a "
                f"{pack.direction} {pack.setup_family.replace('_', ' ')} setup, "
                f"citing {cited} signal{'s' if cited != 1 else ''}.",
                "evidence_packs",
            )
        )
        conditions = pack.invalidation_conditions or []
        if conditions:
            lines.append(
                ExplainLine(
                    "Invalidation",
                    f"It set {len(conditions)} invalidation condition"
                    f"{'s' if len(conditions) != 1 else ''}: "
                    + "; ".join(str(c) for c in conditions)
                    + ". The model never received these and has no schema field "
                    "for them.",
                    "evidence_packs.invalidation_conditions",
                )
            )
    else:
        lines.append(
            ExplainLine(
                "Observed",
                "No evidence pack exists: the setup did not qualify, so nothing "
                "downstream was asked to run.",
                "evidence_packs",
                present=False,
            )
        )

    theses = session.scalars(
        select(ThesisRecord).where(ThesisRecord.decision_id == decision.id)
    ).all()
    if theses:
        thesis = theses[0]
        lines.append(
            ExplainLine(
                "Model memo",
                f"The model returned {thesis.direction} at confidence "
                f"{_fmt(thesis.confidence)}. Its entire contribution is this memo; "
                "a direction disagreeing with the setup is coerced to neutral and "
                "recorded as an attempt.",
                "theses",
            )
        )
    else:
        lines.append(
            ExplainLine(
                "Model memo",
                "No memo exists. The model was never called, which is the cheapest "
                "possible refusal: one classifier and no tokens.",
                "theses",
                present=False,
            )
        )

    risks = session.scalars(
        select(RiskDecisionRecord).where(RiskDecisionRecord.decision_id == decision.id)
    ).all()
    if risks:
        risk = risks[0]
        lines.append(
            ExplainLine(
                "Deterministic risk",
                f"Risk arithmetic {'approved' if risk.approved else 'refused'} the "
                f"structure at a maximum loss of {_fmt(risk.calculated_max_loss)} "
                f"against a budget of {_fmt(risk.risk_budget)}.",
                "risk_decisions",
            )
        )

    intents = session.scalars(
        select(OrderIntent).where(OrderIntent.decision_id == decision.id)
    ).all()
    if intents:
        intent = intents[0]
        lines.append(
            ExplainLine(
                "Authorized intent",
                f"An immutable intent was recorded at limit "
                f"{_fmt(intent.desired_limit_price)}, with client order id "
                f"{intent.client_order_id} derived from its own hash so a duplicate "
                "submit collides at the broker.",
                "order_intents",
            )
        )
        roles = session.scalars(
            select(BrokerOrder.role)
            .join(OrderIntent, OrderIntent.id == BrokerOrder.order_intent_id)
            .where(OrderIntent.decision_id == decision.id)
        ).all()
        if roles:
            lines.append(
                ExplainLine(
                    "Broker",
                    "Alpaca Paper acknowledged "
                    + " and ".join(sorted(set(roles)))
                    + " order(s). Acknowledgement is recorded as SUBMITTED; a fill is "
                    "only written from a reconciled broker record.",
                    "broker_orders",
                )
            )
    else:
        lines.append(
            ExplainLine(
                "Authorized intent",
                f"No intent was created. The decision resolved to {decision.action}"
                + (
                    f" ({', '.join(decision.reason_codes)})"
                    if decision.reason_codes
                    else ""
                )
                + ", so nothing was ever prepared for the broker.",
                "order_intents",
                present=False,
            )
        )

    return lines
