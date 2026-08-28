"""JSON loading and serialization for the production ``DecisionSnapshot``.

Two rules shape this module:

* Production input carries **no expected answers**. Oracles live in separate
  files (``*.oracle.json``) that the workflow never receives, so a fixture cannot
  leak the answer into the system under test (`CLR-005`).
* Every numeric value is parsed as ``Decimal`` from its string form. Parsing
  through ``float`` would make input hashes depend on binary rounding.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .architecture.contracts import (
    AccountSnapshot,
    DataQuality,
    DecisionOutcome,
    DecisionSnapshot,
    Direction,
    OptionQuoteSnapshot,
    OptionType,
    Signal,
    SignalFamily,
)


class SnapshotFormatError(ValueError):
    """Raised when a snapshot document cannot be read as the v1 contract."""


_ORACLE_KEYS = frozenset(
    {
        "expected_action",
        "expected_direction",
        "expected",
        "oracle",
        "answer",
        "expected_reason_codes",
        "outcome",
    }
)


def _require(payload: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in payload:
        raise SnapshotFormatError(f"{context}: missing required field {key!r}")
    return payload[key]


def _decimal(value: Any, context: str) -> Decimal:
    if isinstance(value, float):
        raise SnapshotFormatError(
            f"{context}: numbers must be JSON strings so the value is exact, got a float"
        )
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SnapshotFormatError(f"{context}: {value!r} is not a decimal") from exc


def _datetime(value: Any, context: str) -> datetime:
    if not isinstance(value, str):
        raise SnapshotFormatError(f"{context}: expected an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SnapshotFormatError(f"{context}: {value!r} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise SnapshotFormatError(f"{context}: {value!r} has no timezone offset")
    return parsed


def _date(value: Any, context: str) -> date:
    if not isinstance(value, str):
        raise SnapshotFormatError(f"{context}: expected a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SnapshotFormatError(f"{context}: {value!r} is not a date") from exc


def snapshot_from_dict(payload: Mapping[str, Any]) -> DecisionSnapshot:
    """Build a snapshot, refusing any document that carries an expected answer."""
    leaked = sorted(_ORACLE_KEYS & set(payload))
    if leaked:
        raise SnapshotFormatError(
            "snapshot contains oracle fields "
            f"{leaked}; expected answers belong in a separate .oracle.json file"
        )

    schema_version = payload.get("schema_version", "decision_snapshot.v1")
    if schema_version != "decision_snapshot.v1":
        raise SnapshotFormatError(f"unsupported schema_version {schema_version!r}")

    account_payload = _require(payload, "account", "snapshot")
    account = AccountSnapshot(
        account_id=str(_require(account_payload, "account_id", "account")),
        as_of=_datetime(_require(account_payload, "as_of", "account"), "account.as_of"),
        equity=_decimal(_require(account_payload, "equity", "account"), "account.equity"),
        options_buying_power=_decimal(
            _require(account_payload, "options_buying_power", "account"),
            "account.options_buying_power",
        ),
        is_paper=bool(_require(account_payload, "is_paper", "account")),
    )

    signals: list[Signal] = []
    raw_signals: Sequence[Mapping[str, Any]] = payload.get("signals", ())
    for index, raw in enumerate(raw_signals):
        context = f"signals[{index}]"
        signals.append(
            Signal(
                signal_id=str(_require(raw, "signal_id", context)),
                family=SignalFamily(_require(raw, "family", context)),
                direction=Direction(_require(raw, "direction", context)),
                strength=_decimal(_require(raw, "strength", context), f"{context}.strength"),
                as_of=_datetime(_require(raw, "as_of", context), f"{context}.as_of"),
                source=str(_require(raw, "source", context)),
                summary=str(_require(raw, "summary", context)),
            )
        )

    chain: list[OptionQuoteSnapshot] = []
    raw_chain: Sequence[Mapping[str, Any]] = payload.get("option_chain", ())
    for index, raw in enumerate(raw_chain):
        context = f"option_chain[{index}]"
        chain.append(
            OptionQuoteSnapshot(
                contract_symbol=str(_require(raw, "contract_symbol", context)),
                option_type=OptionType(_require(raw, "option_type", context)),
                expiration=_date(_require(raw, "expiration", context), f"{context}.expiration"),
                dte=int(_require(raw, "dte", context)),
                strike=_decimal(_require(raw, "strike", context), f"{context}.strike"),
                bid=_decimal(_require(raw, "bid", context), f"{context}.bid"),
                ask=_decimal(_require(raw, "ask", context), f"{context}.ask"),
                quote_as_of=_datetime(
                    _require(raw, "quote_as_of", context), f"{context}.quote_as_of"
                ),
                feed=str(_require(raw, "feed", context)),
                delta=(
                    _decimal(raw["delta"], f"{context}.delta") if raw.get("delta") is not None
                    else None
                ),
                implied_volatility=(
                    _decimal(raw["implied_volatility"], f"{context}.implied_volatility")
                    if raw.get("implied_volatility") is not None
                    else None
                ),
                open_interest=(
                    int(raw["open_interest"]) if raw.get("open_interest") is not None else None
                ),
                open_interest_date=(
                    _date(raw["open_interest_date"], f"{context}.open_interest_date")
                    if raw.get("open_interest_date") is not None
                    else None
                ),
                recent_volume=(
                    int(raw["recent_volume"]) if raw.get("recent_volume") is not None else None
                ),
            )
        )

    raw_quality: Mapping[str, Any] = payload.get("data_quality", {})
    data_quality = DataQuality(
        missing_fields=tuple(raw_quality.get("missing_fields", ())),
        stale_fields=tuple(raw_quality.get("stale_fields", ())),
        provider_errors=tuple(raw_quality.get("provider_errors", ())),
    )

    return DecisionSnapshot(
        snapshot_id=str(_require(payload, "snapshot_id", "snapshot")),
        as_of=_datetime(_require(payload, "as_of", "snapshot"), "snapshot.as_of"),
        symbol=str(_require(payload, "symbol", "snapshot")),
        underlying_price=_decimal(
            _require(payload, "underlying_price", "snapshot"), "snapshot.underlying_price"
        ),
        account=account,
        signals=tuple(signals),
        option_chain=tuple(chain),
        data_quality=data_quality,
    )


def snapshot_to_dict(snapshot: DecisionSnapshot) -> dict[str, Any]:
    """Serialize a snapshot for hashing and persistence."""
    return {
        "schema_version": snapshot.schema_version,
        "snapshot_id": snapshot.snapshot_id,
        "as_of": snapshot.as_of,
        "symbol": snapshot.symbol,
        "underlying_price": snapshot.underlying_price,
        "account": {
            "account_id": snapshot.account.account_id,
            "as_of": snapshot.account.as_of,
            "equity": snapshot.account.equity,
            "options_buying_power": snapshot.account.options_buying_power,
            "is_paper": snapshot.account.is_paper,
        },
        "signals": [
            {
                "signal_id": signal.signal_id,
                "family": signal.family,
                "direction": signal.direction,
                "strength": signal.strength,
                "as_of": signal.as_of,
                "source": signal.source,
                "summary": signal.summary,
            }
            for signal in snapshot.signals
        ],
        "option_chain": [
            {
                "contract_symbol": quote.contract_symbol,
                "option_type": quote.option_type,
                "expiration": quote.expiration,
                "dte": quote.dte,
                "strike": quote.strike,
                "bid": quote.bid,
                "ask": quote.ask,
                "quote_as_of": quote.quote_as_of,
                "feed": quote.feed,
                "delta": quote.delta,
                "implied_volatility": quote.implied_volatility,
                "open_interest": quote.open_interest,
                "open_interest_date": quote.open_interest_date,
                "recent_volume": quote.recent_volume,
            }
            for quote in snapshot.option_chain
        ],
        "data_quality": {
            "missing_fields": list(snapshot.data_quality.missing_fields),
            "stale_fields": list(snapshot.data_quality.stale_fields),
            "provider_errors": list(snapshot.data_quality.provider_errors),
        },
    }


def outcome_to_dict(outcome: DecisionOutcome) -> dict[str, Any]:
    """Serialize a decision for hashing, persistence, and oracle comparison."""
    return {
        "snapshot_id": outcome.snapshot_id,
        "action": outcome.action,
        "direction": outcome.direction,
        "reason_codes": list(outcome.reason_codes),
        "transitions": [
            {
                "stage": transition.stage,
                "component": transition.component,
                "outcome": transition.outcome,
                "reason_codes": list(transition.reason_codes),
            }
            for transition in outcome.transitions
        ],
        "setup": (
            None
            if outcome.setup is None
            else {
                "setup_id": outcome.setup.setup_id,
                "family": outcome.setup.family,
                "direction": outcome.setup.direction,
                "evidence_ids": list(outcome.setup.evidence_ids),
                "invalidation_conditions": list(outcome.setup.invalidation_conditions),
            }
        ),
        "thesis": (
            None
            if outcome.thesis is None
            else {
                "direction": outcome.thesis.direction,
                "confidence": outcome.thesis.confidence,
                "evidence_ids": list(outcome.thesis.evidence_ids),
                "counter_evidence_ids": list(outcome.thesis.counter_evidence_ids),
                "invalidation_conditions": list(outcome.thesis.invalidation_conditions),
                "reasoning_summary": outcome.thesis.reasoning_summary,
            }
        ),
        "spread": (
            None
            if outcome.spread is None
            else {
                "candidate_id": outcome.spread.candidate_id,
                "strategy": outcome.spread.strategy,
                "long_contract_symbol": outcome.spread.long_contract_symbol,
                "short_contract_symbol": outcome.spread.short_contract_symbol,
                "quantity": outcome.spread.quantity,
                "estimated_debit": outcome.spread.estimated_debit,
                "calculated_max_loss": outcome.spread.calculated_max_loss,
            }
        ),
        "risk": (
            None
            if outcome.risk is None
            else {
                "approved": outcome.risk.approved,
                "reason_codes": list(outcome.risk.reason_codes),
                "risk_budget": outcome.risk.risk_budget,
                "calculated_max_loss": outcome.risk.calculated_max_loss,
                "policy_version": outcome.risk.policy_version,
            }
        ),
    }


def load_snapshot(path: str | Path) -> DecisionSnapshot:
    """Load a production snapshot document from disk."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SnapshotFormatError(f"{path}: expected a JSON object")
    return snapshot_from_dict(document)


def load_oracle(path: str | Path) -> dict[str, Any]:
    """Load an oracle document. Never passed to the workflow."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SnapshotFormatError(f"{path}: expected a JSON object")
    return document
