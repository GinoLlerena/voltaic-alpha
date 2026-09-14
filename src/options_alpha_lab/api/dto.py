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

SCHEMA_VERSION = "public.v1"

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
