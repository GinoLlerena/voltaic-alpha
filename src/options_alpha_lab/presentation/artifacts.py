"""Whether a committed artifact belongs to the decision on screen.

`CIIP-CV-002`. The Outcome tab renders a decision that may come from a live
worker database, next to a realized Paper receipt and an ablation result that
always come from committed JSON files. Placed together with no qualifier, the
receipt reads as *this* decision's outcome. It usually was not.

The rule the plan asks for is that artifacts may be combined only when their
durable correlation identifiers explicitly match. So this module answers one
question — does this artifact belong to this decision? — and answers `NO` when
it cannot tell. Adjacency is not evidence, and a receipt that happens to be the
only one available is still not the outcome of a decision it never described.

The ablation is a deliberate second case. It is a corpus-level result over five
frozen cases and belongs to **no** decision, so it can never correlate. It is
not a failure to match; it is a category difference, and the display says so
rather than leaving a reader to infer it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .decision import DecisionView

Relation = Literal["THIS_DECISION", "OTHER_DECISION", "NOT_DECISION_SCOPED", "UNKNOWN"]


@dataclass(frozen=True)
class ArtifactLink:
    """How an artifact relates to the decision currently selected."""

    relation: Relation
    #: Plain-language reason, rendered next to the artifact.
    reason: str
    #: The identifier that settled it, when one did.
    matched_on: str | None = None

    @property
    def belongs(self) -> bool:
        return self.relation == "THIS_DECISION"


def correlate_receipt(view: DecisionView, receipt: dict[str, Any]) -> ArtifactLink:
    """Does this Paper receipt describe the selected decision?

    `decision_hash` is preferred over `snapshot_id` because a snapshot can be
    replayed into more than one decision, while the decision hash is unique by
    construction.
    """
    if not receipt:
        return ArtifactLink("UNKNOWN", "no realized receipt is committed")

    recorded = str(receipt.get("decision_hash") or "")
    if recorded:
        if recorded == view.decision.decision_hash:
            return ArtifactLink(
                "THIS_DECISION",
                "the receipt records this decision's hash",
                "decision_hash",
            )
        same_snapshot = str(receipt.get("snapshot_id") or "") == view.decision.snapshot_id
        if same_snapshot:
            # The informative case, and the one actually present in the committed
            # evidence: same observation, different evaluation of it. The receipt
            # describes a decision that no longer exists in this database, so it
            # is not provably the outcome of the one on screen.
            return ArtifactLink(
                "OTHER_DECISION",
                "this receipt records a different evaluation of the same "
                "snapshot; the decision it describes is not the one selected",
                "decision_hash",
            )
        return ArtifactLink(
            "OTHER_DECISION",
            "this receipt records a different decision and is not the outcome "
            "of the selected case",
            "decision_hash",
        )

    recorded_snapshot = str(receipt.get("snapshot_id") or "")
    if recorded_snapshot:
        if recorded_snapshot == view.decision.snapshot_id:
            return ArtifactLink(
                "THIS_DECISION",
                "the receipt records this snapshot",
                "snapshot_id",
            )
        return ArtifactLink(
            "OTHER_DECISION",
            "this receipt records a different snapshot",
            "snapshot_id",
        )

    return ArtifactLink(
        "UNKNOWN",
        "the receipt carries no correlation identifier, so it cannot be tied "
        "to any decision",
    )


def correlate_ablation(_: DecisionView, ablation: dict[str, Any]) -> ArtifactLink:
    """The ablation is corpus-level and belongs to no single decision."""
    if not ablation:
        return ArtifactLink("UNKNOWN", "no ablation artifact is committed")
    cases = (ablation.get("metrics") or {}).get("cases_compared")
    detail = f" over {cases} frozen cases" if cases else ""
    return ArtifactLink(
        "NOT_DECISION_SCOPED",
        f"a corpus-level result{detail}, not an outcome of the selected decision",
    )
