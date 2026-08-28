"""Durable recording of decision traces.

One decision becomes one atomic transaction covering the observation, its
signals, the qualified setup, the thesis, the spread candidate, the risk
decision, and the ordered audit trail. Either the whole trace is reconstructable
or none of it was written.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..architecture.contracts import DecisionOutcome, DecisionSnapshot
from ..config import Settings
from ..hashing import payload_hash
from ..snapshot_io import outcome_to_dict, snapshot_to_dict
from .models import (
    AuditEvent,
    Base,
    Decision,
    EvidencePack,
    MarketSnapshot,
    ModelCall,
    RiskDecisionRecord,
    Run,
    SignalRecord,
    SpreadCandidateRecord,
    ThesisRecord,
)


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class RecordedDecision:
    """Identifiers a caller needs to find the trace it just wrote."""

    decision_id: str
    input_hash: str
    decision_hash: str
    action: str


def build_engine(settings: Settings, *, echo: bool = False) -> Engine:
    return create_engine(settings.database_url, echo=echo, future=True)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


class DecisionRecorder:
    """Writes decision traces. Has no broker access and no write path to one."""

    def __init__(self, engine: Engine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings
        self._session_factory = sessionmaker(bind=engine, future=True)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def start_run(self) -> str:
        run_id = _new_id()
        with self._session() as session:
            session.add(
                Run(
                    id=run_id,
                    runtime_version=self._settings.runtime_version,
                    policy_version=self._settings.policy_version,
                    bot_mode=self._settings.bot_mode.value,
                    trading_enabled=self._settings.alpaca_trading_enabled,
                    started_at=datetime.now(UTC),
                )
            )
        return run_id

    def end_run(self, run_id: str, health_result: str) -> None:
        with self._session() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise LookupError(f"run {run_id} not found")
            run.ended_at = datetime.now(UTC)
            run.health_result = health_result

    def record_decision(
        self,
        *,
        run_id: str,
        snapshot: DecisionSnapshot,
        outcome: DecisionOutcome,
        provider: str = "fixture",
        feed: str = "fixture",
        risk_checks: Sequence[dict[str, Any]] = (),
        classifier_name: str = "unknown",
        synthesizer_name: str = "unknown",
        model_call: Any = None,
    ) -> RecordedDecision:
        snapshot_payload = snapshot_to_dict(snapshot)
        input_hash = payload_hash(snapshot_payload)
        outcome_payload = outcome_to_dict(outcome)
        # The decision hash binds the outcome to the exact observation it came
        # from: replaying different inputs cannot produce the same decision hash.
        decision_hash = payload_hash(
            {"input_hash": input_hash, "outcome": outcome_payload}
        )

        now = datetime.now(UTC)
        market_snapshot_id = _new_id()
        decision_id = _new_id()

        with self._session() as session:
            session.add(
                MarketSnapshot(
                    id=market_snapshot_id,
                    run_id=run_id,
                    snapshot_id=snapshot.snapshot_id,
                    symbol=snapshot.symbol,
                    provider=provider,
                    feed=feed,
                    source_time=snapshot.as_of,
                    received_time=now,
                    underlying_price=snapshot.underlying_price,
                    payload_hash=input_hash,
                    payload=_jsonable(snapshot_payload),
                    data_quality=snapshot_payload["data_quality"],
                )
            )
            for signal in snapshot.signals:
                session.add(
                    SignalRecord(
                        id=_new_id(),
                        market_snapshot_id=market_snapshot_id,
                        signal_id=signal.signal_id,
                        family=signal.family.value,
                        direction=signal.direction.value,
                        strength=signal.strength,
                        as_of=signal.as_of,
                        source=signal.source,
                        summary=signal.summary,
                    )
                )

            if outcome.setup is not None:
                setup_payload = outcome_payload["setup"]
                session.add(
                    EvidencePack(
                        id=_new_id(),
                        market_snapshot_id=market_snapshot_id,
                        setup_id=outcome.setup.setup_id,
                        setup_family=outcome.setup.family.value,
                        direction=outcome.setup.direction.value,
                        evidence_ids=list(outcome.setup.evidence_ids),
                        invalidation_conditions=list(outcome.setup.invalidation_conditions),
                        classifier_name=classifier_name,
                        payload_hash=payload_hash(setup_payload),
                    )
                )

            session.add(
                Decision(
                    id=decision_id,
                    run_id=run_id,
                    market_snapshot_id=market_snapshot_id,
                    snapshot_id=snapshot.snapshot_id,
                    action=outcome.action.value,
                    direction=outcome.direction.value,
                    reason_codes=list(outcome.reason_codes),
                    transitions=_jsonable(outcome_payload["transitions"]),
                    input_hash=input_hash,
                    decision_hash=decision_hash,
                    policy_version=self._settings.policy_version,
                    decided_at=now,
                )
            )

            model_call_id: str | None = None
            if model_call is not None:
                model_call_id = _new_id()
                session.add(
                    ModelCall(
                        id=model_call_id,
                        run_id=run_id,
                        provider=model_call.provider,
                        model=model_call.model,
                        prompt_version=model_call.prompt_version,
                        output_schema_version=model_call.output_schema_version,
                        status=model_call.status,
                        latency_ms=model_call.latency_ms,
                        input_tokens=model_call.input_tokens,
                        output_tokens=model_call.output_tokens,
                        input_hash=model_call.input_hash,
                    )
                )

            if outcome.thesis is not None:
                session.add(
                    ThesisRecord(
                        id=_new_id(),
                        decision_id=decision_id,
                        model_call_id=model_call_id,
                        synthesizer_name=synthesizer_name,
                        direction=outcome.thesis.direction.value,
                        confidence=outcome.thesis.confidence,
                        evidence_ids=list(outcome.thesis.evidence_ids),
                        counter_evidence_ids=list(outcome.thesis.counter_evidence_ids),
                        invalidation_conditions=list(outcome.thesis.invalidation_conditions),
                        reasoning_summary=outcome.thesis.reasoning_summary,
                    )
                )

            if outcome.spread is not None:
                legs = [
                    _jsonable(quote)
                    for quote in snapshot_payload["option_chain"]
                    if quote["contract_symbol"]
                    in {
                        outcome.spread.long_contract_symbol,
                        outcome.spread.short_contract_symbol,
                    }
                ]
                session.add(
                    SpreadCandidateRecord(
                        id=_new_id(),
                        decision_id=decision_id,
                        candidate_id=outcome.spread.candidate_id,
                        strategy=outcome.spread.strategy.value,
                        long_contract_symbol=outcome.spread.long_contract_symbol,
                        short_contract_symbol=outcome.spread.short_contract_symbol,
                        quantity=outcome.spread.quantity,
                        estimated_debit=outcome.spread.estimated_debit,
                        calculated_max_loss=outcome.spread.calculated_max_loss,
                        leg_quotes=legs,
                        rejection_reasons=[],
                        selected=outcome.risk is not None and outcome.risk.approved,
                    )
                )

            if outcome.risk is not None:
                session.add(
                    RiskDecisionRecord(
                        id=_new_id(),
                        decision_id=decision_id,
                        governor_name="deterministic_risk_governor_v0",
                        approved=outcome.risk.approved,
                        reason_codes=list(outcome.risk.reason_codes),
                        checks=list(risk_checks),
                        risk_budget=outcome.risk.risk_budget,
                        calculated_max_loss=outcome.risk.calculated_max_loss,
                        policy_version=outcome.risk.policy_version,
                        intent_ttl_seconds=None,
                    )
                )

            for sequence, transition in enumerate(outcome.transitions):
                session.add(
                    AuditEvent(
                        id=_new_id(),
                        run_id=run_id,
                        correlation_id=snapshot.snapshot_id,
                        sequence=sequence,
                        component=transition.component,
                        stage=transition.stage.value,
                        outcome=transition.outcome,
                        reason_codes=list(transition.reason_codes),
                        occurred_at=now,
                    )
                )

        return RecordedDecision(
            decision_id=decision_id,
            input_hash=input_hash,
            decision_hash=decision_hash,
            action=outcome.action.value,
        )


def _jsonable(value: Any) -> Any:
    """Convert Decimals, datetimes, dates, and enums to JSON-storable values."""
    from datetime import date as _date
    from datetime import datetime as _datetime
    from decimal import Decimal as _Decimal
    from enum import Enum as _Enum

    if isinstance(value, _Enum):
        return _jsonable(value.value)
    if isinstance(value, _Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, _datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, _date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
