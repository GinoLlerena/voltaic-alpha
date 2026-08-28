"""Append-oriented audit schema for the H0 decision path.

Implements the H0 subset of implementation plan section 12. Every table carries
a UTC timestamp and a schema version, and no table stores credentials,
authorization headers, or model hidden reasoning.

Execution tables (``order_intents`` through ``positions``) are created here
because the reconstruction story needs them to exist as a shape, but Phase 1
writes nothing to them: there is no broker write path in this commit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA_VERSION = "h0.1"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[str]:
    return mapped_column(String(64), primary_key=True)


def _recorded_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def _schema_version() -> Mapped[str]:
    return mapped_column(String(32), default=SCHEMA_VERSION, nullable=False)


class Run(Base):
    """One execution of the decision cycle, successful or not."""

    __tablename__ = "runs"

    id: Mapped[str] = _pk()
    runtime_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    bot_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()

    snapshots: Mapped[list[MarketSnapshot]] = relationship(back_populates="run")
    decisions: Mapped[list[Decision]] = relationship(back_populates="run")


class MarketSnapshot(Base):
    """The exact observation a decision was made from, with its input hash."""

    __tablename__ = "market_snapshots"

    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    feed: Mapped[str] = mapped_column(String(32), nullable=False)
    source_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    underlying_price: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    data_quality: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()

    run: Mapped[Run] = relationship(back_populates="snapshots")


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[str] = _pk()
    market_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("market_snapshots.id"), nullable=False
    )
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    family: Mapped[str] = mapped_column(String(48), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    strength: Mapped[Any] = mapped_column(Numeric(6, 4), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class EvidencePack(Base):
    """The qualified setup: aligned evidence, contradictions, and invalidation."""

    __tablename__ = "evidence_packs"

    id: Mapped[str] = _pk()
    market_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("market_snapshots.id"), nullable=False
    )
    setup_id: Mapped[str] = mapped_column(String(128), nullable=False)
    setup_family: Mapped[str] = mapped_column(String(48), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    invalidation_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    classifier_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class ModelCall(Base):
    """Provider call metadata. Never stores prompts' secrets or hidden reasoning."""

    __tablename__ = "model_calls"

    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class ThesisRecord(Base):
    __tablename__ = "theses"

    id: Mapped[str] = _pk()
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), nullable=False)
    model_call_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_calls.id"), nullable=True
    )
    synthesizer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Any] = mapped_column(Numeric(6, 4), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    counter_evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    invalidation_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reasoning_summary: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class SpreadCandidateRecord(Base):
    __tablename__ = "spread_candidates"

    id: Mapped[str] = _pk()
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy: Mapped[str] = mapped_column(String(48), nullable=False)
    long_contract_symbol: Mapped[str] = mapped_column(String(48), nullable=False)
    short_contract_symbol: Mapped[str] = mapped_column(String(48), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_debit: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    calculated_max_loss: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    leg_quotes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    rejection_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class RiskDecisionRecord(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[str] = _pk()
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), nullable=False)
    governor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    risk_budget: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    calculated_max_loss: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class Decision(Base):
    """The immutable outcome, linked by hash to the observation it came from."""

    __tablename__ = "decisions"

    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    market_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("market_snapshots.id"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    transitions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()

    run: Mapped[Run] = relationship(back_populates="decisions")


class OrderIntent(Base):
    """Immutable approved intent. No row is written until Phase 4."""

    __tablename__ = "order_intents"

    id: Mapped[str] = _pk()
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    legs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    desired_limit_price: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class PreparedOrderRequest(Base):
    """The exact serialized request. Never stores authorization headers."""

    __tablename__ = "prepared_order_requests"

    id: Mapped[str] = _pk()
    order_intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.id"), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    request_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    serialized_request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    intent_hash_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dry_run_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class BrokerOrder(Base):
    __tablename__ = "broker_orders"

    id: Mapped[str] = _pk()
    order_intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.id"), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[str] = _pk()
    broker_order_id: Mapped[str] = mapped_column(ForeignKey("broker_orders.id"), nullable=False)
    leg_symbol: Mapped[str] = mapped_column(String(48), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[str] = _pk()
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), nullable=False)
    strategy: Mapped[str] = mapped_column(String(48), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False)
    open_risk: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


class AuditEvent(Base):
    """Every workflow transition, in order, with its correlation IDs."""

    __tablename__ = "audit_events"

    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = _recorded_at()
    schema_version: Mapped[str] = _schema_version()


#: Tables that Phase 1 must never write to. Enforced by test, not by convention.
EXECUTION_TABLES: frozenset[str] = frozenset(
    {
        OrderIntent.__tablename__,
        PreparedOrderRequest.__tablename__,
        BrokerOrder.__tablename__,
        Fill.__tablename__,
        Position.__tablename__,
    }
)
