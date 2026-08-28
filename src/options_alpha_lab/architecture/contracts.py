from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class DecisionAction(str, Enum):
    OPTIONS_POSITION = "OPTIONS_POSITION"
    NO_TRADE = "NO_TRADE"
    HOLD = "HOLD"
    REDUCE_EXPOSURE = "REDUCE_EXPOSURE"
    EXIT = "EXIT"


class BotMode(str, Enum):
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    PAPER_EXECUTE = "paper_execute"


class ExecutionState(str, Enum):
    NORMAL = "NORMAL"
    NO_NEW_RISK = "NO_NEW_RISK"
    FREEZE_ALL_WRITES = "FREEZE_ALL_WRITES"


class SignalFamily(str, Enum):
    STRUCTURE = "structure"
    MOMENTUM = "momentum"
    PARTICIPATION = "participation"
    RELATIVE_STRENGTH = "relative_strength"
    VOLATILITY_OPTIONS = "volatility_options"
    MACRO_LIQUIDITY = "macro_liquidity"
    EVENT = "event"
    SENTIMENT_POSITIONING = "sentiment_positioning"
    EXECUTION_QUALITY = "execution_quality"
    PORTFOLIO_RISK = "portfolio_risk"


class SetupFamily(str, Enum):
    TREND_CONTINUATION_RETEST = "trend_continuation_retest"
    BREAKOUT_BREAKDOWN = "breakout_breakdown"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class SpreadStrategy(str, Enum):
    BULL_CALL_DEBIT_SPREAD = "bull_call_debit_spread"
    BEAR_PUT_DEBIT_SPREAD = "bear_put_debit_spread"


class WorkflowStage(str, Enum):
    OBSERVED = "OBSERVED"
    QUALIFIED = "QUALIFIED"
    THESIS_READY = "THESIS_READY"
    STRUCTURE_READY = "STRUCTURE_READY"
    RISK_REVIEWED = "RISK_REVIEWED"
    DECIDED = "DECIDED"


def _require_nonblank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_range(
    value: Decimal,
    minimum: Decimal,
    maximum: Decimal,
    field_name: str,
) -> None:
    if not minimum <= value <= maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")


@dataclass(frozen=True)
class DataQuality:
    missing_fields: tuple[str, ...] = ()
    stale_fields: tuple[str, ...] = ()
    provider_errors: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        return not (self.missing_fields or self.stale_fields or self.provider_errors)

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return (
            *(f"missing:{field_name}" for field_name in self.missing_fields),
            *(f"stale:{field_name}" for field_name in self.stale_fields),
            *(f"provider:{error}" for error in self.provider_errors),
        )


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    as_of: datetime
    equity: Decimal
    options_buying_power: Decimal
    is_paper: bool

    def __post_init__(self) -> None:
        _require_nonblank(self.account_id, "account_id")
        _require_aware(self.as_of, "account.as_of")
        if self.equity <= 0:
            raise ValueError("account equity must be positive")
        if self.options_buying_power < 0:
            raise ValueError("options buying power must not be negative")


@dataclass(frozen=True)
class Signal:
    signal_id: str
    family: SignalFamily
    direction: Direction
    strength: Decimal
    as_of: datetime
    source: str
    summary: str

    def __post_init__(self) -> None:
        _require_nonblank(self.signal_id, "signal_id")
        _require_nonblank(self.source, "signal.source")
        _require_nonblank(self.summary, "signal.summary")
        _require_aware(self.as_of, "signal.as_of")
        _require_range(self.strength, Decimal("0"), Decimal("1"), "signal.strength")


@dataclass(frozen=True)
class OptionQuoteSnapshot:
    contract_symbol: str
    option_type: OptionType
    expiration: date
    dte: int
    strike: Decimal
    bid: Decimal
    ask: Decimal
    quote_as_of: datetime
    feed: str
    delta: Decimal | None = None
    implied_volatility: Decimal | None = None
    open_interest: int | None = None
    open_interest_date: date | None = None
    recent_volume: int | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.contract_symbol, "contract_symbol")
        _require_nonblank(self.feed, "option.feed")
        _require_aware(self.quote_as_of, "option.quote_as_of")
        if self.dte < 0:
            raise ValueError("option dte must not be negative")
        if self.strike <= 0:
            raise ValueError("option strike must be positive")
        if self.bid < 0 or self.ask < 0:
            raise ValueError("option bid and ask must not be negative")
        if self.delta is not None:
            _require_range(self.delta, Decimal("-1"), Decimal("1"), "option.delta")
        if self.implied_volatility is not None and self.implied_volatility < 0:
            raise ValueError("option implied volatility must not be negative")
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("option open interest must not be negative")
        if self.recent_volume is not None and self.recent_volume < 0:
            raise ValueError("option recent volume must not be negative")


@dataclass(frozen=True)
class DecisionSnapshot:
    snapshot_id: str
    as_of: datetime
    symbol: str
    underlying_price: Decimal
    account: AccountSnapshot
    signals: tuple[Signal, ...]
    option_chain: tuple[OptionQuoteSnapshot, ...] = ()
    data_quality: DataQuality = field(default_factory=DataQuality)
    schema_version: str = "decision_snapshot.v1"

    def __post_init__(self) -> None:
        _require_nonblank(self.snapshot_id, "snapshot_id")
        _require_nonblank(self.schema_version, "schema_version")
        _require_aware(self.as_of, "snapshot.as_of")
        normalized_symbol = self.symbol.strip().upper()
        _require_nonblank(normalized_symbol, "symbol")
        object.__setattr__(self, "symbol", normalized_symbol)
        if self.underlying_price <= 0:
            raise ValueError("underlying price must be positive")
        if self.account.as_of > self.as_of:
            raise ValueError("account snapshot cannot be newer than decision snapshot")

        signal_ids = [signal.signal_id for signal in self.signals]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("signal IDs must be unique")
        if any(signal.as_of > self.as_of for signal in self.signals):
            raise ValueError("signals cannot be newer than decision snapshot")
        if any(quote.quote_as_of > self.as_of for quote in self.option_chain):
            raise ValueError("option quotes cannot be newer than decision snapshot")


@dataclass(frozen=True)
class SetupCandidate:
    setup_id: str
    family: SetupFamily
    direction: Direction
    evidence_ids: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank(self.setup_id, "setup_id")
        if self.direction is Direction.NEUTRAL:
            raise ValueError("a qualified setup must be directional")
        if not self.evidence_ids:
            raise ValueError("a qualified setup must reference evidence")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("setup evidence IDs must be unique")
        if not any(item.strip() for item in self.invalidation_conditions):
            raise ValueError("a qualified setup must define invalidation")


@dataclass(frozen=True)
class Thesis:
    direction: Direction
    confidence: Decimal
    evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    reasoning_summary: str

    def __post_init__(self) -> None:
        _require_range(self.confidence, Decimal("0"), Decimal("1"), "confidence")
        _require_nonblank(self.reasoning_summary, "reasoning_summary")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("thesis evidence IDs must be unique")
        if len(self.counter_evidence_ids) != len(set(self.counter_evidence_ids)):
            raise ValueError("counter-evidence IDs must be unique")
        if self.direction is not Direction.NEUTRAL:
            if not self.evidence_ids:
                raise ValueError("a directional thesis must reference evidence")
            if not any(item.strip() for item in self.invalidation_conditions):
                raise ValueError("a directional thesis must define invalidation")


@dataclass(frozen=True)
class SpreadCandidate:
    candidate_id: str
    strategy: SpreadStrategy
    long_contract_symbol: str
    short_contract_symbol: str
    quantity: int
    estimated_debit: Decimal
    calculated_max_loss: Decimal

    def __post_init__(self) -> None:
        _require_nonblank(self.candidate_id, "candidate_id")
        _require_nonblank(self.long_contract_symbol, "long_contract_symbol")
        _require_nonblank(self.short_contract_symbol, "short_contract_symbol")
        if self.long_contract_symbol == self.short_contract_symbol:
            raise ValueError("spread legs must use different contracts")
        if self.quantity < 1:
            raise ValueError("spread quantity must be positive")
        if self.estimated_debit <= 0:
            raise ValueError("estimated debit must be positive")
        if self.calculated_max_loss <= 0:
            raise ValueError("calculated max loss must be positive")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason_codes: tuple[str, ...]
    risk_budget: Decimal
    calculated_max_loss: Decimal
    policy_version: str

    def __post_init__(self) -> None:
        _require_nonblank(self.policy_version, "policy_version")
        if self.risk_budget < 0 or self.calculated_max_loss < 0:
            raise ValueError("risk values must not be negative")
        if self.approved and self.calculated_max_loss > self.risk_budget:
            raise ValueError("approved maximum loss must not exceed the risk budget")


@dataclass(frozen=True)
class WorkflowTransition:
    stage: WorkflowStage
    component: str
    outcome: str
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionOutcome:
    snapshot_id: str
    action: DecisionAction
    direction: Direction
    reason_codes: tuple[str, ...]
    transitions: tuple[WorkflowTransition, ...]
    setup: SetupCandidate | None = None
    thesis: Thesis | None = None
    spread: SpreadCandidate | None = None
    risk: RiskDecision | None = None

    def __post_init__(self) -> None:
        if self.action is DecisionAction.OPTIONS_POSITION:
            if self.spread is None or self.risk is None or not self.risk.approved:
                raise ValueError("an options position requires an approved spread")
