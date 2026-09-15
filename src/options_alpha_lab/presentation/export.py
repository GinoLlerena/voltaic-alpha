"""A deterministic, redacted proof manifest for one decision.

`CIIP-007`. The manifest answers a reviewer's real question — *show me that this
order came from that observation* — as a file they can keep, diff, and check
without the application or the database.

Two properties do the work.

**Determinism.** The same records must produce byte-identical bytes, so a
reviewer can diff two exports and conclude that a difference means the records
differ, not that the exporter is noisy. There is therefore no `generated_at`,
no wall clock, no set iteration, and no dict whose order depends on insertion:
keys are sorted and every collection is ordered by a stable field.

**Redaction by construction.** Nothing is copied wholesale and scrubbed
afterwards. Every value in the output is named by `_snapshot`, `_intent` and
friends, so a new column on a model cannot leak into an export by default — it
has to be added deliberately. Post-hoc masking has the opposite failure mode:
it protects only the patterns someone remembered, and silently ships the rest.
That is why `serialized_request` is represented by its hash rather than its
bytes, and why the account identifier never appears at all.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from .decision import DecisionView

#: Bumped when the shape changes, so an old manifest stays interpretable.
#: Bumped for `RUI-VAL-010`: the disclosures no longer assert a sample size that
#: nothing counted, which changes the bytes and therefore every digest.
MANIFEST_VERSION = "proof-manifest-2"

#: Reproduced verbatim from README.md. See `HK-018`.
DISCLOSURES = (
    "Alpaca Paper only. No live endpoint exists in this build.",
    "Option quotes come from the indicative feed; the account has no OPRA "
    "agreement, so quotes are not trading-quality.",
    "No alpha is claimed. The null hypothesis is not rejected, and the sample is "
    "far too small to test it. The completed round trips are counted on the "
    "dashboard's proof tiles rather than asserted here.",
    "Nothing here is investment advice.",
)


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _num(value: Any) -> str | None:
    """Numbers travel as strings so a float repr cannot vary between runs."""
    return None if value is None else str(Decimal(str(value)))


def _snapshot(view: DecisionView) -> dict[str, Any] | None:
    snapshot = view.snapshot
    if snapshot is None:
        return None
    return {
        "snapshot_id": snapshot.snapshot_id,
        "symbol": snapshot.symbol,
        "provider": snapshot.provider,
        "feed": snapshot.feed,
        "source_time": _stamp(snapshot.source_time),
        "received_time": _stamp(snapshot.received_time),
        "underlying_price": _num(snapshot.underlying_price),
        "payload_hash": snapshot.payload_hash,
        # The payload itself is excluded: it is large, and its account block is
        # exactly the sort of thing an allowlist exists to keep out. The hash
        # above is what makes it checkable.
    }


def _evidence(view: DecisionView) -> list[dict[str, Any]]:
    return [
        {
            "setup_id": pack.setup_id,
            "setup_family": pack.setup_family,
            "direction": pack.direction,
            "classifier_name": pack.classifier_name,
            "evidence_ids": sorted(pack.evidence_ids or []),
            "invalidation_conditions": list(pack.invalidation_conditions or []),
            "payload_hash": pack.payload_hash,
        }
        for pack in sorted(view.packs, key=lambda p: p.setup_id)
    ]


def _memo(view: DecisionView) -> dict[str, Any] | str:
    """`NOT_CALLED` is a first-class result, not an empty section."""
    if not view.theses:
        return "NOT_CALLED"
    thesis = view.theses[0]
    return {
        "synthesizer_name": thesis.synthesizer_name,
        "direction": thesis.direction,
        "confidence": _num(thesis.confidence),
        "evidence_ids": sorted(thesis.evidence_ids or []),
        "counter_evidence_ids": sorted(thesis.counter_evidence_ids or []),
        # `reasoning_summary` is the model's own prose and is deliberately
        # omitted: it is the one field whose content nobody controls.
    }


def _risk(view: DecisionView) -> list[dict[str, Any]]:
    return [
        {
            "governor_name": risk.governor_name,
            "approved": bool(risk.approved),
            "reason_codes": sorted(risk.reason_codes or []),
            "risk_budget": _num(risk.risk_budget),
            "calculated_max_loss": _num(risk.calculated_max_loss),
            "policy_version": risk.policy_version,
        }
        for risk in sorted(view.risks, key=lambda r: r.id)
    ]


def _intents(view: DecisionView) -> list[dict[str, Any]]:
    return [
        {
            "intent_hash": intent.intent_hash,
            "client_order_id": intent.client_order_id,
            "desired_limit_price": _num(intent.desired_limit_price),
            "approval_reference": intent.approval_reference,
            "expires_at": _stamp(intent.expires_at),
        }
        for intent in sorted(view.intents, key=lambda i: i.intent_hash)
    ]


def _requests(view: DecisionView) -> list[dict[str, Any]]:
    return [
        {
            "request_hash": request.request_hash,
            "adapter_version": request.adapter_version,
            "request_schema_version": request.request_schema_version,
            "intent_hash_match": bool(request.intent_hash_match),
            # `serialized_request` holds the exact bytes sent to the broker,
            # including headers. The hash proves it without shipping it.
        }
        for request in sorted(view.requests, key=lambda r: r.request_hash)
    ]


def _orders(view: DecisionView) -> list[dict[str, Any]]:
    out = []
    for order in sorted(view.orders, key=lambda o: (o.role, o.client_order_id)):
        out.append(
            {
                "role": order.role,
                "client_order_id": order.client_order_id,
                "status": order.status,
                "local_state": order.local_state,
                "terminal": bool(order.terminal),
                "strategy_quantity": order.strategy_quantity,
                "filled_quantity": order.filled_quantity,
                "filled_avg_price": _num(order.filled_avg_price),
                "prepared_at": _stamp(order.prepared_at),
                "submitted_at": _stamp(order.submitted_at),
                "reconciled_at": _stamp(order.reconciled_at),
                "fills": [
                    {
                        "leg_symbol": fill.leg_symbol,
                        "quantity": fill.quantity,
                        "price": _num(fill.price),
                        "filled_at": _stamp(fill.filled_at),
                    }
                    for fill in sorted(
                        view.fills_for(order.id),
                        key=lambda f: (f.leg_symbol, str(f.price)),
                    )
                ],
            }
        )
    return out


def _positions(view: DecisionView) -> list[dict[str, Any]]:
    return [
        {
            "strategy": position.strategy,
            "direction": position.direction,
            "lifecycle_status": position.lifecycle_status,
            "long_symbol": position.long_symbol,
            "short_symbol": position.short_symbol,
            "expiration": _stamp(position.expiration),
            "width": _num(position.width),
            "requested_quantity": position.requested_quantity,
            "filled_quantity": position.filled_quantity,
            "avg_entry_debit": _num(position.avg_entry_debit),
            "open_risk": _num(position.open_risk),
        }
        for position in sorted(view.positions, key=lambda p: p.id)
    ]


def manifest(view: DecisionView) -> dict[str, Any]:
    """The proof chain for one decision, as plain data."""
    decision = view.decision
    return {
        "manifest_version": MANIFEST_VERSION,
        "decision": {
            "snapshot_id": decision.snapshot_id,
            "action": decision.action,
            "direction": decision.direction,
            "reason_codes": sorted(decision.reason_codes or []),
            "input_hash": decision.input_hash,
            "decision_hash": decision.decision_hash,
            "policy_version": decision.policy_version,
            "decided_at": _stamp(decision.decided_at),
        },
        "observation": _snapshot(view),
        "evidence": _evidence(view),
        "model_memo": _memo(view),
        "risk": _risk(view),
        "intents": _intents(view),
        "prepared_requests": _requests(view),
        "broker_orders": _orders(view),
        "positions": _positions(view),
        "reached_the_broker": view.reached_the_broker,
        "model_was_called": view.model_was_called,
        "disclosures": list(DISCLOSURES),
    }


def render(view: DecisionView) -> bytes:
    """The manifest as stable bytes. Identical records give identical output."""
    return json.dumps(
        manifest(view),
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
        ensure_ascii=False,
    ).encode("utf-8") + b"\n"


def digest(view: DecisionView) -> str:
    return "sha256:" + hashlib.sha256(render(view)).hexdigest()
