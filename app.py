"""Options Alpha - judge-facing dashboard.

Five read-only views over committed evidence. There are no control actions: the
dashboard cannot start a run, approve an intent, or reach a broker, so there is
nothing here to protect with a permission check. That is the intended design, not
a simplification - the surface a judge browses is not the surface that trades.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import ExecutionState
from options_alpha_lab.persistence.models import (
    AuditEvent,
    BrokerOrder,
    Decision,
    EvidencePack,
    Fill,
    MarketSnapshot,
    ModelCall,
    OrderIntent,
    PreparedOrderRequest,
    RiskDecisionRecord,
    SignalRecord,
    SpreadCandidateRecord,
    ThesisRecord,
)

DB = Path("demo/h0_demo.db")
RECEIPT = Path("artifacts/h0_paper_lifecycle.json")

st.set_page_config(page_title="Options Alpha", page_icon="🔒", layout="wide")


@st.cache_resource
def engine():  # type: ignore[no-untyped-def]
    return create_engine(f"sqlite+pysqlite:///{DB}", future=True)


def rows(stmt: Any) -> list[Any]:
    with Session(engine()) as session:
        return list(session.scalars(stmt).all())


def hash_chip(label: str, value: str | None) -> None:
    if not value:
        return
    st.markdown(f"**{label}**")
    st.code(value, language=None)


st.title("Options Alpha")
st.caption(
    "An auditable AI execution firewall. A language model may write a memo; it cannot "
    "pick a direction, change an invalidation level, size risk, or reach a broker tool."
)

decisions = rows(select(Decision).order_by(Decision.recorded_at))
if not decisions:
    st.error("No evidence database found. Run `python scripts/build_demo_db.py`.")
    st.stop()

labels = {d.id: f"{d.snapshot_id} — {d.action}" for d in decisions}
chosen_id = st.sidebar.radio(
    "Decision", list(labels), format_func=lambda k: labels[k], index=0
)
decision = next(d for d in decisions if d.id == chosen_id)

st.sidebar.divider()
st.sidebar.markdown(
    "**Disclosures**\n\n"
    "- Alpaca **Paper** only. No live endpoint exists in this build.\n"
    "- Option quotes come from the **indicative** feed. The account has no OPRA "
    "agreement, so quotes are not trading-quality.\n"
    "- **No alpha is claimed.** A `NO_TRADE` refusal and a deterministic baseline "
    "beating the model are both valid results.\n"
    "- Nothing here is investment advice."
)

tabs = st.tabs(
    [
        "1 · Mode & health",
        "2 · Evidence & baseline",
        "3 · Model memo",
        "4 · Approval lineage",
        "5 · Outcome or refusal",
    ]
)

# --- 1. Mode and health -----------------------------------------------------
with tabs[0]:
    st.subheader("Mode and health")
    snapshot = rows(
        select(MarketSnapshot).where(MarketSnapshot.id == decision.market_snapshot_id)
    )[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Environment", "Paper")
    c2.metric("Order writes", "disabled")
    c3.metric("Option feed", snapshot.feed)
    c4.metric("Policy", decision.policy_version)

    st.markdown("#### What blocks a write")
    st.markdown(
        "Six guards run immediately before every order, not at startup, because the "
        "interesting failures develop between the two."
    )
    st.table(
        [
            {"guard": "configuration permits writes", "blocks": "any mode but paper_execute"},
            {"guard": "resolved endpoint is Paper", "blocks": "a client pointing anywhere else"},
            {
                "guard": "execution state allows new risk",
                "blocks": "NO_NEW_RISK, FREEZE_ALL_WRITES",
            },
            {"guard": "no strategy already open", "blocks": "a second concurrent position"},
            {"guard": "intent not expired", "blocks": "a stale approval (90 s TTL)"},
            {"guard": "request matches intent hash", "blocks": "bytes that drifted after approval"},
        ]
    )

    st.markdown("#### `NO_NEW_RISK` demonstration")
    state = st.selectbox(
        "Durable execution state", [s.value for s in ExecutionState], index=0
    )
    if state == ExecutionState.NORMAL.value:
        st.success("New risk permitted. Closes and cancels also permitted.")
    elif state == ExecutionState.NO_NEW_RISK.value:
        st.warning(
            "New or increased risk **blocked**. Cancels and risk-reducing closes stay "
            "permitted, because blocking a close during a loss would trap exposure."
        )
    else:
        st.error(
            "**All writes blocked**, including closes. Reserved for adapter, credential, "
            "or endpoint integrity incidents, and raises an incident because it can "
            "temporarily prevent risk reduction."
        )

# --- 2. Evidence and deterministic baseline ---------------------------------
with tabs[1]:
    st.subheader("Evidence")
    snapshot = rows(
        select(MarketSnapshot).where(MarketSnapshot.id == decision.market_snapshot_id)
    )[0]
    st.markdown(
        f"**{snapshot.symbol}** at `{snapshot.underlying_price}` · "
        f"observed `{snapshot.source_time}` · provider `{snapshot.provider}` · "
        f"feed `{snapshot.feed}`"
    )
    hash_chip("Input hash", snapshot.payload_hash)

    signals = rows(
        select(SignalRecord).where(SignalRecord.market_snapshot_id == snapshot.id)
    )
    st.markdown("#### Signals")
    st.dataframe(
        [
            {
                "id": s.signal_id,
                "family": s.family,
                "direction": s.direction,
                "strength": str(s.strength),
                "source": s.source,
                "summary": s.summary,
            }
            for s in signals
        ],
        use_container_width=True,
        hide_index=True,
    )

    packs = rows(select(EvidencePack).where(EvidencePack.market_snapshot_id == snapshot.id))
    st.markdown("#### Deterministic qualification")
    if packs:
        pack = packs[0]
        st.success(
            f"Qualified **{pack.direction}** · {pack.setup_family} · "
            f"classifier `{pack.classifier_name}`"
        )
        st.markdown("**Invalidation, set by code and not negotiable:**")
        for condition in pack.invalidation_conditions:
            st.markdown(f"- {condition}")
    else:
        st.warning(
            "No setup qualified. The deterministic classifier declined before any "
            "model was consulted."
        )

# --- 3. Bounded model memo --------------------------------------------------
with tabs[2]:
    st.subheader("Bounded model memo")
    theses = rows(select(ThesisRecord).where(ThesisRecord.decision_id == decision.id))
    if not theses:
        st.info(
            "No memo exists for this decision. The setup did not qualify, so the model "
            "was never asked. The model is never invited to adjudicate contradictory "
            "evidence, because it has no authority to resolve it."
        )
    else:
        thesis = theses[0]
        st.markdown(f"Synthesizer `{thesis.synthesizer_name}`")
        c1, c2 = st.columns(2)
        c1.metric("Direction", thesis.direction)
        c2.metric("Confidence", str(thesis.confidence))
        st.markdown("**Memo**")
        st.info(thesis.reasoning_summary)
        c1, c2 = st.columns(2)
        c1.markdown("**Cited evidence**")
        c1.write(thesis.evidence_ids or "none")
        c2.markdown("**Counter-evidence**")
        c2.write(thesis.counter_evidence_ids or "none")

        calls = rows(select(ModelCall).where(ModelCall.id == thesis.model_call_id))
        if calls:
            call = calls[0]
            st.markdown("#### Model call")
            st.table(
                [
                    {
                        "provider": call.provider,
                        "model": call.model,
                        "status": call.status,
                        "latency_ms": call.latency_ms,
                        "input_tokens": call.input_tokens,
                        "output_tokens": call.output_tokens,
                    }
                ]
            )
            hash_chip("Model input hash", call.input_hash)

    st.markdown("#### What the model cannot do")
    st.table(
        [
            {
                "bound": "Direction",
                "how": "may agree or abstain; a reversal is coerced to abstention",
            },
            {"bound": "Invalidation", "how": "never sent to the model and absent from its schema"},
            {"bound": "Position size", "how": "not in the prompt; computed after the memo"},
            {"bound": "Option eligibility", "how": "deterministic, from the chain"},
            {"bound": "Execution", "how": "no broker tool is reachable from the model path"},
        ]
    )

# --- 4. Approval and request lineage ----------------------------------------
with tabs[3]:
    st.subheader("Approval and request lineage")
    hash_chip("Input hash (observation)", decision.input_hash)
    hash_chip("Decision hash (binds outcome to observation)", decision.decision_hash)

    risks = rows(select(RiskDecisionRecord).where(RiskDecisionRecord.decision_id == decision.id))
    if risks:
        risk = risks[0]
        st.markdown("#### Deterministic risk decision")
        c1, c2, c3 = st.columns(3)
        c1.metric("Approved", "yes" if risk.approved else "no")
        c2.metric("Max loss", str(risk.calculated_max_loss))
        c3.metric("Budget", str(risk.risk_budget))
        if risk.checks:
            st.dataframe(risk.checks, use_container_width=True, hide_index=True)
        if risk.reason_codes:
            st.error("Rejected: " + ", ".join(risk.reason_codes))

    intents = rows(select(OrderIntent).where(OrderIntent.decision_id == decision.id))
    if not intents:
        st.info("No order intent exists for this decision.")
    for intent in intents:
        st.markdown(f"#### Intent `{intent.approval_reference}`")
        hash_chip("Intent hash", intent.intent_hash)
        st.markdown(
            f"Client order id `{intent.client_order_id}` — the first 28 hex characters "
            "of the intent hash. Derived, never generated, so a duplicate submit "
            "collides instead of opening a second strategy."
        )
        prepared = rows(
            select(PreparedOrderRequest).where(
                PreparedOrderRequest.order_intent_id == intent.id
            )
        )
        for request in prepared:
            st.markdown("**Exact request sent to the broker**")
            st.json(request.serialized_request)
            hash_chip("Request hash", request.request_hash)
            if request.intent_hash_match:
                st.success("Request hash matches the approved intent.")
            else:
                st.error("Request does not match the approved intent. A write would be refused.")

# --- 5. Reconciled outcome or refusal ---------------------------------------
with tabs[4]:
    st.subheader("Outcome")
    if decision.action != "OPTIONS_POSITION":
        st.warning(f"**{decision.action}** — {', '.join(decision.reason_codes) or 'refused'}")
        st.markdown(
            "A refusal is a first-class result. It is reproducible from the recorded "
            "evidence and required no model call."
        )
    else:
        spreads = rows(
            select(SpreadCandidateRecord).where(SpreadCandidateRecord.decision_id == decision.id)
        )
        if spreads:
            spread = spreads[0]
            st.success(
                f"**{spread.strategy}** — {spread.long_contract_symbol} / "
                f"{spread.short_contract_symbol} × {spread.quantity}, "
                f"debit {spread.estimated_debit}, max loss {spread.calculated_max_loss}"
            )

    orders = rows(select(BrokerOrder))
    if orders:
        st.markdown("#### Reconciled broker state")
        for order in orders:
            fills = rows(select(Fill).where(Fill.broker_order_id == order.id))
            st.markdown(
                f"`{order.client_order_id}` — **{order.status}**, "
                f"{order.filled_quantity}/{order.strategy_quantity} filled"
            )
            if fills:
                st.dataframe(
                    [
                        {"leg": f.leg_symbol, "qty": f.quantity, "price": str(f.price)}
                        for f in fills
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

    if RECEIPT.exists():
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        final = receipt["final_state"]
        st.markdown("#### Paper result")
        c1, c2, c3 = st.columns(3)
        c1.metric("Open positions", final["open_positions"])
        c2.metric("Equity", final["equity_after"], delta=final["realized"])
        c3.metric("Realized", final["realized"])
        st.caption(final["note"])

    st.markdown("#### Audit trail")
    events = rows(
        select(AuditEvent)
        .where(AuditEvent.correlation_id == decision.snapshot_id)
        .order_by(AuditEvent.sequence)
    )
    st.dataframe(
        [
            {
                "#": e.sequence,
                "stage": e.stage,
                "component": e.component,
                "outcome": e.outcome,
                "reasons": ", ".join(e.reason_codes),
            }
            for e in events
        ],
        use_container_width=True,
        hide_index=True,
    )
