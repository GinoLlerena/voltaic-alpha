"""Public shapes: what may cross from the records to a browser.

Every field here is a decision to publish it. Anything not named is withheld,
which is the point of an allowlist: a column added to a model later does not
become public by default.

Two conventions hold everywhere. Money and prices cross as decimal strings, so a
binary float can never alter a value in transit. Timestamps cross as UTC with an
explicit offset -- SQLite hands back naive datetimes, and a naive time in a
public contract is a time a reader will misplace by their own offset.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION: Literal["public.v1"] = "public.v1"

T = TypeVar("T")


def utc(value: datetime | None) -> str | None:
    """A timezone-aware UTC ISO-8601 string. Naive values are stored UTC."""
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def decimal(value: Any) -> str | None:
    return None if value is None else str(Decimal(str(value)))


class Public(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Envelope(Public, Generic[T]):
    schema_version: Literal["public.v1"] = SCHEMA_VERSION
    source_mode: Literal["LIVE", "FROZEN_REPLAY"]
    source_label: str
    observed_at: str
    #: The decision a response is scoped to, when it is scoped to one.
    correlation_id: str | None = None
    data: T


class StatusItemOut(Public):
    label: str
    value: str
    tone: Literal["ok", "warn", "bad", "off", "unknown"]
    known: bool
    source: str
    observed_at: str | None
    reason: str | None


class ProofTileOut(Public):
    value: str
    label: str
    mode: str
    available: bool
    source: str
    detail: str


class DecisionListItem(Public):
    decision_id: str
    snapshot_id: str
    action: str
    direction: str
    reason_codes: list[str]
    policy_version: str
    decided_at: str | None


class DecisionPage(Public):
    items: list[DecisionListItem]
    next_cursor: str | None


class Observation(Public):
    symbol: str
    provider: str
    feed: str
    source_time: str | None
    received_time: str | None
    underlying_price: str | None
    payload_hash: str


class ExplainLineOut(Public):
    stage: str
    text: str
    source: str
    present: bool


class DecisionSummary(Public):
    decision_id: str
    snapshot_id: str
    action: str
    direction: str
    reason_codes: list[str]
    input_hash: str
    decision_hash: str
    policy_version: str
    decided_at: str | None
    observation: Observation | None
    reached_the_broker: bool
    model_was_called: bool
    why: list[ExplainLineOut]


class ProofOut(Public):
    manifest_digest: str
    manifest: dict[str, Any]


class ActivityEventOut(Public):
    correlation_id: str
    sequence: int
    stage: str
    outcome: str
    component: str
    reason_codes: list[str]
    occurred_at: str | None
    refused: bool


class ActivityPage(Public):
    items: list[ActivityEventOut]
    next_cursor: str | None


#: Worker detail keys safe to publish. `host` names a private machine; `error`
#: and `summary` are free text that can carry anything an exception carried.
WORKER_DETAIL_ALLOWLIST = frozenset({"mode", "writes", "approval", "clean", "action", "ticks"})


class WorkerEventOut(Public):
    event: str
    kind: Literal["state", "cadence", "fault"] | str
    occurred_at: str | None
    detail: dict[str, str | int | bool | None]
    #: Names of detail keys held back, so a withheld field is visible as withheld
    #: rather than silently absent. Values are never included.
    withheld: list[str]


class WorkerEventsOut(Public):
    #: False when the source cannot hold worker events, which is not the same
    #: claim as "the worker recorded nothing".
    available: bool
    reason: str | None
    items: list[WorkerEventOut]


# --------------------------------------------------------------------------
# Decision workspaces (RUI-1). Each mirrors one area of the existing dashboard.
# --------------------------------------------------------------------------

Scalar = str | int | bool | None


def scalar(value: Any) -> Scalar:
    """Coerce a JSON value to a public scalar: numbers other than ints and bools
    become decimal strings, so no float crosses the boundary."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float | Decimal):
        return str(Decimal(str(value)))
    return str(value)


def allow(
    source: dict[str, Any] | None, keys: frozenset[str]
) -> tuple[dict[str, Scalar], list[str]]:
    """Keep allowlisted keys, and name -- never show -- the rest."""
    source = source or {}
    kept = {k: scalar(v) for k, v in source.items() if k in keys}
    return kept, sorted(k for k in source if k not in keys)


class SignalOut(Public):
    signal_id: str
    family: str
    direction: str
    strength: str | None
    as_of: str | None
    source: str
    summary: str
    #: Computed by `presentation.decision.signal_role`, the rule the dashboard
    #: renders with -- never re-derived by a client.
    role: Literal["cited", "counter-evidence", "observed, unused"]


class QualificationOut(Public):
    setup_id: str
    setup_family: str
    direction: str
    classifier_name: str
    evidence_ids: list[str]
    invalidation_conditions: list[str]
    payload_hash: str


class MarketOut(Public):
    observation: Observation | None
    #: `fixture` for a recorded replay, `provider` for an observed quote,
    #: `unavailable` when the snapshot row is missing.
    observation_kind: Literal["fixture", "provider", "unavailable"]
    signals: list[SignalOut]
    #: None when no setup qualified: the deterministic classifier declined
    #: before any model was consulted.
    qualification: QualificationOut | None
    #: None for a decision recorded before `CIIP-VAL-012`, or replayed from a
    #: fixture that carries no bars.
    structure: StructureReadingOut | None = None


class ThesisOut(Public):
    synthesizer_name: str
    direction: str
    confidence: str | None
    evidence_ids: list[str]
    counter_evidence_ids: list[str]
    invalidation_conditions: list[str]
    reasoning_summary: str


class ModelCallOut(Public):
    provider: str
    model: str
    prompt_version: str
    output_schema_version: str
    status: str
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    input_hash: str
    reasoning_effort: str | None


class MemoOut(Public):
    """Separate from structure on purpose: the memo is the model's, advisory,
    and sizes nothing; structure is deterministic. One payload holding both
    would blur the authority line the product is built to draw."""

    produced: bool
    thesis: ThesisOut | None
    model_call: ModelCallOut | None


LEG_QUOTE_KEYS = frozenset({
    "contract_symbol", "option_type", "expiration", "dte", "strike", "bid", "ask",
    "quote_as_of", "feed", "delta", "implied_volatility", "open_interest",
    "open_interest_date", "recent_volume",
})


class SpreadCandidateOut(Public):
    candidate_id: str
    strategy: str
    long_contract_symbol: str
    short_contract_symbol: str
    quantity: int
    estimated_debit: str | None
    calculated_max_loss: str | None
    selected: bool
    rejection_reasons: list[str]
    leg_quotes: list[dict[str, Scalar]]


class StructureOut(Public):
    selected: SpreadCandidateOut | None
    candidates: list[SpreadCandidateOut]


class RiskDecisionOut(Public):
    governor_name: str
    approved: bool
    reason_codes: list[str]
    checks: list[dict[str, Scalar]]
    risk_budget: str | None
    calculated_max_loss: str | None
    policy_version: str
    intent_ttl_seconds: int | None


class AccountingOut(Public):
    account_equity: str | None
    risk_budget: str | None
    maximum_loss: str | None
    #: Of the per-trade budget, not of the portfolio.
    budget_used_percent: str | None


class RiskOut(Public):
    decisions: list[RiskDecisionOut]
    accounting: AccountingOut | None


LEG_KEYS = frozenset({"symbol", "side", "position_intent", "ratio_qty"})
REQUEST_KEYS = frozenset({
    "client_order_id", "legs", "limit_price", "order_class", "qty", "time_in_force", "type",
})


class RequestOut(Public):
    request_hash: str
    intent_hash_match: bool
    adapter_version: str
    request_schema_version: str
    dry_run_result: str | None
    prepared_at: str | None
    expires_at: str | None
    #: The approved order fields, allowlisted. Any other key -- a header, a
    #: credential-bearing field a future adapter adds -- is named, not shown.
    request: dict[str, Any]
    withheld: list[str]


class IntentOut(Public):
    intent_hash: str
    client_order_id: str
    approval_reference: str | None
    desired_limit_price: str | None
    expires_at: str | None
    legs: list[dict[str, Scalar]]
    requests: list[RequestOut]


class FillOut(Public):
    leg_symbol: str
    quantity: int
    price: str | None
    filled_at: str | None


class OrderOut(Public):
    role: str
    status: str
    local_state: str | None
    terminal: bool
    client_order_id: str
    strategy_quantity: int | None
    filled_quantity: int | None
    filled_avg_price: str | None
    prepared_at: str | None
    submitted_at: str | None
    deadline_at: str | None
    reconciled_at: str | None
    fills: list[FillOut]
    withheld: list[str]


class PositionOut(Public):
    lifecycle_status: str
    strategy: str
    direction: str
    long_symbol: str
    short_symbol: str
    width: str | None
    expiration: str | None
    requested_quantity: int | None
    filled_quantity: int | None
    avg_entry_debit: str | None
    open_risk: str | None
    opened_at: str | None
    entry_filled_at: str | None
    closed_at: str | None
    close_reason: str | None
    invalidation_level: str | None
    invalidation_direction: str | None
    invalidation_source: str | None


class ExitOut(Public):
    trigger: str
    should_close: bool
    disposition: str | None
    reason: str
    unrealized: str | None
    suggested_limit: str | None
    value_unmeasurable: bool
    invalidation_unverifiable: bool
    policy_version: str
    decided_at: str | None


class TrailOut(Public):
    complete: bool
    gaps: list[int]
    events: list[ActivityEventOut]


class ArtifactOut(Public):
    """A committed artifact and whether it belongs to this decision."""

    relation: Literal["THIS_DECISION", "OTHER_DECISION", "NOT_DECISION_SCOPED", "UNKNOWN"]
    belongs: bool
    reason: str
    matched_on: str | None
    facts: dict[str, Scalar]


class LifecycleOut(Public):
    reached_the_broker: bool
    intents: list[IntentOut]
    orders: list[OrderOut]
    positions: list[PositionOut]
    exits: list[ExitOut]
    trail: TrailOut
    receipt: ArtifactOut
    ablation: ArtifactOut


class IncidentOut(Public):
    kind: str
    severity: str
    execution_state: str | None
    opened_at: str | None
    resolved_at: str | None
    open: bool
    #: `detail` is built from exception text at several call sites, so it is
    #: free text a broker error chose. Named here when present, never shown.
    withheld: list[str]


class SceneOut(Public):
    number: int
    title: str
    narration: str
    tab: int
    snapshot_id: str
    #: None when the scene's decision is absent from the current source.
    decision_id: str | None


class ListEntryOut(Public):
    decision_id: str
    snapshot_id: str
    action: str
    direction: str
    label: str
    #: Consecutive identical outcomes this entry stands for.
    count: int
    member_ids: list[str]


class DecisionListOut(Public):
    view: Literal["Notable", "Positions", "Refusals", "Everything"]
    entries: list[ListEntryOut]
    shown: int
    total: int
    grouped: bool
    #: A `pin` was requested and this source holds no such decision.
    pin_missing: bool


class RuleOut(Public):
    name: str
    effect: str


class HaltStateOut(Public):
    state: str
    tone: Literal["ok", "warn", "bad"]
    explanation: str


class CopyOut(Public):
    """Copy that makes a checkable claim about the system, served rather than
    typed into each client (presentation/copy.py)."""

    what_this_is: str
    disclosures: list[str]
    write_guards: list[RuleOut]
    write_guards_note: str
    model_limits: list[RuleOut]
    halt_states: list[HaltStateOut]


class HorizonCountsOut(Public):
    """Counts only. There is no rate field, and that is deliberate: over a corpus
    where every row is unanswerable, a rate would be a sentence about nothing."""

    horizon: str
    sessions: int
    resolved: int
    pending: int
    trades: int
    refusals: int
    agreed: int
    disagreed: int
    unanswerable: int
    with_realized: int
    smallest_move: str | None
    largest_move: str | None


class ReviewOverviewOut(Public):
    horizons: list[HorizonCountsOut]
    decisions: int
    decisions_reviewed: int
    positions_ever: int
    resolved: int
    pending: int
    #: Derived from the counts, so it cannot drift from them.
    caveat: str


class DecisionHorizonOut(Public):
    horizon: str
    sessions: int
    state: str
    resolved: bool
    underlying_at_decision: str | None
    underlying_at_horizon: str | None
    change: str | None
    direction_agreed: bool | None
    realized: str | None
    observed_snapshot_id: str | None


class StructureReadingOut(Public):
    """What the structure gate computed, whether or not it produced a signal.

    `CIIP-VAL-012`. Without it a refusal is a reason code with no arithmetic
    behind it, and 201 of them cannot be told apart.
    """

    gate: str
    bars_considered: int
    bars_required: int
    fast_ema: str | None
    slow_ema: str | None
    separation: str | None
    last_close: str | None
    close_side: str | None
    retest_touched: bool | None
    #: Negative is a shortfall; positive cleared the threshold.
    separation_shortfall: str | None
