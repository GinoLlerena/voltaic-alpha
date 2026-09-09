"""The three claims the first viewport makes, each derived rather than typed.

`CIIP-003`. A landing tile that reads `1 Paper lifecycle` is worth nothing if a
person wrote `1` into the template — that is the same defect as the hardcoded
safety strip, moved somewhere more prominent. Each tile here is computed from
correlated records or a versioned artifact, and carries the query or file it
came from so a reader can check it.

The three claims are chosen to be the ones a sceptical reviewer would test
first, in the order they would test them:

1. did this thing ever actually trade;
2. did the model change any of its decisions; and
3. can the model reach the broker at all.

The third is the load-bearing one and the only one that is a code property
rather than an observation, so it is labelled `DERIVED` rather than `OBSERVED`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..persistence.models import BrokerOrder, Fill, OrderIntent, Position

#: How a value was arrived at. Displayed verbatim; never inferred at render time.
Mode = Literal["OBSERVED PAPER", "LIVE READ", "FROZEN REPLAY", "DERIVED", "UNAVAILABLE"]


@dataclass(frozen=True)
class ProofTile:
    """One headline claim, with the evidence that supports it."""

    value: str
    label: str
    mode: Mode
    #: The query, artifact, or gate the value came from.
    source: str
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.mode != "UNAVAILABLE"


def paper_lifecycles(session: Session) -> ProofTile:
    """Completed Paper round trips, counted by correlation rather than by hand.

    Correlation runs through the decision, not through `positions.close_order_id`:
    that column is populated by `prepare_close` at runtime but is absent from the
    committed fixture, so a count keyed on it silently reports zero over exactly
    the evidence a reader is most likely to be looking at. Decision lineage is
    the same traversal the Outcome tab uses after `CIIP-CV-003`.

    A round trip is complete when a position reached `CLOSED` and its decision
    produced both a reconciled entry and a reconciled close order. Counting
    `CLOSED` positions alone would also count one abandoned into that state,
    which is a different claim.
    """
    closed = session.scalars(
        select(Position).where(Position.lifecycle_status == "CLOSED")
    ).all()
    complete = 0
    for position in closed:
        roles = set(
            session.scalars(
                select(BrokerOrder.role)
                .join(OrderIntent, OrderIntent.id == BrokerOrder.order_intent_id)
                .where(OrderIntent.decision_id == position.decision_id)
            ).all()
        )
        if {"entry", "close"} <= roles:
            complete += 1

    if not complete:
        return ProofTile(
            "0", "reconciled Paper lifecycles", "UNAVAILABLE",
            "positions joined through decisions to broker_orders",
            "no position has both a reconciled entry and close",
        )

    fills = int(session.scalar(select(func.count()).select_from(Fill)) or 0)
    return ProofTile(
        str(complete),
        "reconciled Paper lifecycle" + ("s" if complete != 1 else ""),
        "OBSERVED PAPER",
        "positions joined through decisions to broker_orders and fills",
        f"{fills} recorded fill{'s' if fills != 1 else ''}, entry and close reconciled",
    )


def model_effect(artifact: Path) -> ProofTile:
    """What the ablation measured, read from the artifact rather than recalled.

    This is the tile we would most like to overstate and must not. The honest
    reading is that the model changed nothing across a sample far too small to
    conclude anything, and the tile says both halves.
    """
    try:
        data: dict[str, Any] = json.loads(artifact.read_text(encoding="utf-8"))
        metrics = data["metrics"]
        changed = int(metrics["decisions_changed_by_model"])
        cases = int(metrics["cases_compared"])
    except Exception as exc:  # noqa: BLE001 - a missing artifact is a display state
        return ProofTile(
            "—", "model effect on decisions", "UNAVAILABLE",
            str(artifact),
            f"ablation artifact unreadable: {type(exc).__name__}",
        )
    return ProofTile(
        str(changed),
        f"decisions changed by the model, over {cases} cases",
        "DERIVED",
        f"{artifact.name} · metrics.decisions_changed_by_model",
        "a mechanism check on a tiny sample, not evidence about returns",
    )


def write_boundary(gate: Path) -> ProofTile:
    """How many files may express a broker write, proven by the static gate.

    Deliberately not a count of anything at render time: the claim is that a
    build fails if a second file acquires a write path, and the evidence for it
    is that the gate exists and runs in the release sequence.
    """
    if not gate.exists():
        return ProofTile(
            "—", "authorized broker-write paths", "UNAVAILABLE",
            str(gate), "the static execution-boundary gate is missing",
        )
    return ProofTile(
        "1",
        "authorized broker-write path",
        "DERIVED",
        f"{gate.name} · fails the build if a second appears",
        "the dashboard has none; the model has none",
    )


def proof_tiles(session: Session, *, root: Path) -> list[ProofTile]:
    return [
        paper_lifecycles(session),
        model_effect(root / "artifacts" / "ablation_h0.json"),
        write_boundary(root / "scripts" / "check_no_write_path.py"),
    ]
