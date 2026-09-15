"""Turn one resolved `DecisionView` into the public workspace payloads.

`RUI-1`. Pure functions of records already loaded, plus the committed artifact
files. Nothing here queries by itself except the audit trail, which is the read
model's own function. Every value that could carry money crosses as a decimal
string, and every free-form mapping passes an explicit allowlist that names what
it withheld.
"""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from ..persistence.models import Incident
from ..presentation import activity
from ..presentation.artifacts import ArtifactLink, correlate_ablation, correlate_receipt
from ..presentation.decision import DecisionView, signal_role
from . import dto


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing artifact is reported as UNKNOWN, not raised
        return {}
    # A committed artifact that is valid JSON but not an object is treated as absent.
    return data if isinstance(data, dict) else {}


def market(view: DecisionView) -> dto.MarketOut:
    snap = view.snapshot
    pack = view.packs[0] if view.packs else None
    cited = set(pack.evidence_ids) if pack else set()
    setup_direction = pack.direction if pack else ""
    kind: Literal["fixture", "provider", "unavailable"]
    if snap is None:
        kind = "unavailable"
    else:
        kind = "fixture" if snap.feed in {"fixture", ""} else "provider"
    return dto.MarketOut(
        observation=None if snap is None else dto.Observation(
            symbol=snap.symbol, provider=snap.provider, feed=snap.feed,
            source_time=dto.utc(snap.source_time), received_time=dto.utc(snap.received_time),
            underlying_price=dto.decimal(snap.underlying_price), payload_hash=snap.payload_hash,
        ),
        observation_kind=kind,
        signals=[
            dto.SignalOut(
                signal_id=s.signal_id, family=s.family, direction=s.direction,
                strength=dto.decimal(s.strength), as_of=dto.utc(s.as_of), source=s.source,
                summary=s.summary,
                role=signal_role(s.signal_id, s.direction, cited, setup_direction),
            )
            # Strongest first, the order the dashboard renders in.
            for s in sorted(view.signals, key=lambda s: -Decimal(str(s.strength)))
        ],
        qualification=None if pack is None else dto.QualificationOut(
            setup_id=pack.setup_id, setup_family=pack.setup_family, direction=pack.direction,
            classifier_name=pack.classifier_name, evidence_ids=list(pack.evidence_ids),
            invalidation_conditions=list(pack.invalidation_conditions),
            payload_hash=pack.payload_hash,
        ),
    )


def memo(view: DecisionView) -> dto.MemoOut:
    if not view.theses:
        return dto.MemoOut(produced=False, thesis=None, model_call=None)
    thesis = view.theses[0]
    call = view.call_for(thesis)
    return dto.MemoOut(
        produced=True,
        thesis=dto.ThesisOut(
            synthesizer_name=thesis.synthesizer_name, direction=thesis.direction,
            confidence=dto.decimal(thesis.confidence), evidence_ids=list(thesis.evidence_ids),
            counter_evidence_ids=list(thesis.counter_evidence_ids),
            invalidation_conditions=list(thesis.invalidation_conditions),
            reasoning_summary=thesis.reasoning_summary,
        ),
        model_call=None if call is None else dto.ModelCallOut(
            provider=call.provider, model=call.model, prompt_version=call.prompt_version,
            output_schema_version=call.output_schema_version, status=call.status,
            latency_ms=call.latency_ms, input_tokens=call.input_tokens,
            output_tokens=call.output_tokens, input_hash=call.input_hash,
            reasoning_effort=call.reasoning_effort,
        ),
    )


def _candidate(spread: Any) -> dto.SpreadCandidateOut:
    quotes = [dto.allow(q, dto.LEG_QUOTE_KEYS)[0] for q in (spread.leg_quotes or [])]
    return dto.SpreadCandidateOut(
        candidate_id=spread.candidate_id, strategy=spread.strategy,
        long_contract_symbol=spread.long_contract_symbol,
        short_contract_symbol=spread.short_contract_symbol, quantity=spread.quantity,
        estimated_debit=dto.decimal(spread.estimated_debit),
        calculated_max_loss=dto.decimal(spread.calculated_max_loss),
        selected=bool(spread.selected), rejection_reasons=list(spread.rejection_reasons or []),
        leg_quotes=quotes,
    )


def structure(view: DecisionView) -> dto.StructureOut:
    candidates = [_candidate(s) for s in view.spreads]
    # The dashboard shows the first candidate as the selected structure.
    selected = next((c for c in candidates if c.selected), candidates[0] if candidates else None)
    return dto.StructureOut(selected=selected, candidates=candidates)


def _equity(view: DecisionView) -> str | None:
    """The one account fact the risk view needs, lifted out of a payload that
    must not cross. Everything else in `payload.account` stays behind."""
    payload = (view.snapshot.payload if view.snapshot else None) or {}
    value = (payload.get("account") or {}).get("equity")
    try:
        return None if value is None else str(Decimal(str(value)))
    except InvalidOperation:
        return None


def risk(view: DecisionView) -> dto.RiskOut:
    decisions = [
        dto.RiskDecisionOut(
            governor_name=r.governor_name, approved=bool(r.approved),
            reason_codes=list(r.reason_codes or []),
            checks=[{k: dto.scalar(v) for k, v in c.items()} for c in (r.checks or [])],
            risk_budget=dto.decimal(r.risk_budget),
            calculated_max_loss=dto.decimal(r.calculated_max_loss),
            policy_version=r.policy_version, intent_ttl_seconds=r.intent_ttl_seconds,
        )
        for r in view.risks
    ]
    accounting = None
    if view.risks and view.spreads:
        first = view.risks[0]
        budget = Decimal(str(first.risk_budget)) if first.risk_budget is not None else None
        loss = first.calculated_max_loss
        used = Decimal(str(loss)) if loss is not None else None
        percent = (
            str((used / budget * 100).quantize(Decimal("0.01")))
            if budget and used is not None
            else None
        )
        accounting = dto.AccountingOut(
            account_equity=_equity(view), risk_budget=dto.decimal(budget),
            maximum_loss=dto.decimal(used), budget_used_percent=percent,
        )
    return dto.RiskOut(decisions=decisions, accounting=accounting)


def _request(request: Any) -> dto.RequestOut:
    body = dict(request.serialized_request or {})
    legs = body.pop("legs", None)
    kept, withheld = dto.allow(body, dto.REQUEST_KEYS)
    out: dict[str, Any] = dict(kept)
    if legs is not None:
        out["legs"] = []
        for leg in legs:
            leg_kept, leg_withheld = dto.allow(leg, dto.LEG_KEYS)
            out["legs"].append(leg_kept)
            withheld += [f"legs.{k}" for k in leg_withheld]
    return dto.RequestOut(
        request_hash=request.request_hash, intent_hash_match=bool(request.intent_hash_match),
        adapter_version=request.adapter_version,
        request_schema_version=request.request_schema_version,
        dry_run_result=request.dry_run_result, prepared_at=dto.utc(request.prepared_at),
        expires_at=dto.utc(request.expires_at), request=out, withheld=sorted(set(withheld)),
    )


def _artifact(link: ArtifactLink, facts: dict[str, Any]) -> dto.ArtifactOut:
    return dto.ArtifactOut(
        relation=link.relation, belongs=link.belongs, reason=link.reason,
        matched_on=link.matched_on, facts={k: dto.scalar(v) for k, v in facts.items()},
    )


def lifecycle(session: Session, view: DecisionView, *, root: Path) -> dto.LifecycleOut:
    receipt = _json(root / "artifacts" / "h0_paper_lifecycle.json")
    ablation = _json(root / "artifacts" / "ablation_h0.json")
    final = receipt.get("final_state") or {}
    trail = activity.for_decision(session, view.decision)
    return dto.LifecycleOut(
        reached_the_broker=view.reached_the_broker,
        intents=[
            dto.IntentOut(
                intent_hash=i.intent_hash, client_order_id=i.client_order_id,
                approval_reference=i.approval_reference,
                desired_limit_price=dto.decimal(i.desired_limit_price),
                expires_at=dto.utc(i.expires_at),
                legs=[dto.allow(leg, dto.LEG_KEYS)[0] for leg in (i.legs or [])],
                requests=[_request(r) for r in view.requests_for(i)],
            )
            for i in view.intents
        ],
        orders=[
            dto.OrderOut(
                role=o.role, status=o.status, local_state=o.local_state,
                terminal=bool(o.terminal), client_order_id=o.client_order_id,
                strategy_quantity=o.strategy_quantity, filled_quantity=o.filled_quantity,
                filled_avg_price=dto.decimal(o.filled_avg_price),
                prepared_at=dto.utc(o.prepared_at), submitted_at=dto.utc(o.submitted_at),
                deadline_at=dto.utc(o.deadline_at), reconciled_at=dto.utc(o.reconciled_at),
                fills=[
                    dto.FillOut(leg_symbol=f.leg_symbol, quantity=f.quantity,
                                price=dto.decimal(f.price), filled_at=dto.utc(f.filled_at))
                    for f in view.fills_for(o.id)
                ],
                # The broker's own id and free-text errors stay behind.
                withheld=[k for k in ("broker_order_id", "last_error") if getattr(o, k)],
            )
            for o in view.orders
        ],
        positions=[
            dto.PositionOut(
                lifecycle_status=p.lifecycle_status, strategy=p.strategy, direction=p.direction,
                long_symbol=p.long_symbol, short_symbol=p.short_symbol,
                width=dto.decimal(p.width), expiration=dto.utc(p.expiration),
                requested_quantity=p.requested_quantity, filled_quantity=p.filled_quantity,
                avg_entry_debit=dto.decimal(p.avg_entry_debit), open_risk=dto.decimal(p.open_risk),
                opened_at=dto.utc(p.opened_at), entry_filled_at=dto.utc(p.entry_filled_at),
                closed_at=dto.utc(p.closed_at), close_reason=p.close_reason,
                invalidation_level=dto.decimal(p.invalidation_level),
                invalidation_direction=p.invalidation_direction,
                invalidation_source=p.invalidation_source,
            )
            for p in view.positions
        ],
        exits=[
            dto.ExitOut(
                trigger=e.trigger, should_close=bool(e.should_close), disposition=e.disposition,
                reason=e.reason, unrealized=dto.decimal(e.unrealized),
                suggested_limit=dto.decimal(e.suggested_limit),
                value_unmeasurable=bool(e.value_unmeasurable),
                invalidation_unverifiable=bool(e.invalidation_unverifiable),
                policy_version=e.policy_version, decided_at=dto.utc(e.decided_at),
            )
            for e in view.exits
        ],
        trail=dto.TrailOut(
            complete=trail.complete, gaps=list(trail.gaps),
            events=[
                dto.ActivityEventOut(
                    correlation_id=e.correlation_id, sequence=e.sequence, stage=e.stage,
                    outcome=e.outcome, component=e.component,
                    reason_codes=list(e.reason_codes), occurred_at=dto.utc(e.occurred_at),
                    refused=e.refused,
                )
                for e in trail.events
            ],
        ),
        receipt=_artifact(correlate_receipt(view, receipt), {
            "open_positions": final.get("open_positions"),
            "equity_before": final.get("equity_before"),
            "equity_after": final.get("equity_after"),
            "realized": final.get("realized"),
            "entry_filled_avg_price": (receipt.get("open") or {}).get("filled_avg_price"),
            "exit_filled_avg_price": (receipt.get("close") or {}).get("filled_avg_price"),
        } if final else {}),
        ablation=_artifact(correlate_ablation(view, ablation), {
            "decisions_changed_by_model":
                (ablation.get("metrics") or {}).get("decisions_changed_by_model"),
            "cases_compared": (ablation.get("metrics") or {}).get("cases_compared"),
        } if ablation.get("metrics") else {}),
    )


def incident(row: Incident) -> dto.IncidentOut:
    return dto.IncidentOut(
        kind=row.kind, severity=row.severity, execution_state=row.execution_state,
        opened_at=dto.utc(row.opened_at), resolved_at=dto.utc(row.resolved_at),
        open=row.resolved_at is None, withheld=["detail"] if row.detail else [],
    )
