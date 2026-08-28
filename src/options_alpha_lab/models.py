from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class Decision(str, Enum):
    TRADE_CANDIDATE = "TRADE_CANDIDATE"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class OptionQuote:
    symbol: str
    option_type: str
    expiration: str
    dte: int
    strike: Decimal
    bid: Decimal
    ask: Decimal
    delta: Decimal
    implied_volatility: Decimal

    @property
    def midpoint(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def has_two_sided_market(self) -> bool:
        return self.bid > 0 and self.ask > 0

    @property
    def is_crossed(self) -> bool:
        return self.bid > self.ask

    @property
    def spread_ratio(self) -> Decimal:
        if not self.has_two_sided_market or self.is_crossed or self.midpoint <= 0:
            return Decimal("999")
        return (self.ask - self.bid) / self.midpoint


@dataclass(frozen=True)
class Policy:
    max_risk_pct: Decimal
    min_confidence: Decimal
    min_evidence_items: int
    min_dte: int
    max_dte: int
    max_bid_ask_ratio: Decimal
    max_contracts: int


@dataclass(frozen=True)
class ExperimentCase:
    case_id: str
    symbol: str
    event_type: str
    event_date: str
    days_until_event: int
    underlying_price: Decimal
    account_equity: Decimal
    expected_direction: Direction
    confidence: Decimal
    evidence: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    option_chain: tuple[OptionQuote, ...]
    policy: Policy


@dataclass(frozen=True)
class Thesis:
    symbol: str
    event_type: str
    direction: Direction
    confidence: Decimal
    evidence: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]


@dataclass(frozen=True)
class SpreadProposal:
    strategy: str
    long_leg: OptionQuote
    short_leg: OptionQuote
    quantity: int
    estimated_debit: Decimal
    rationale: str

    @property
    def max_loss(self) -> Decimal:
        return self.estimated_debit * Decimal("100") * self.quantity


@dataclass(frozen=True)
class RiskResult:
    approved: bool
    reasons: tuple[str, ...]
    risk_budget: Decimal
    calculated_max_loss: Decimal
    suggested_quantity: int | None = None


@dataclass(frozen=True)
class TraceMessage:
    sender: str
    recipient: str
    kind: str
    payload: dict[str, Any]


@dataclass
class ExperimentResult:
    case_id: str
    decision: Decision
    thesis: Thesis
    proposal: SpreadProposal | None
    risk: RiskResult
    trace: list[TraceMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def quote_from_dict(raw: dict[str, Any]) -> OptionQuote:
    return OptionQuote(
        symbol=raw["symbol"],
        option_type=raw["option_type"],
        expiration=raw["expiration"],
        dte=int(raw["dte"]),
        strike=Decimal(str(raw["strike"])),
        bid=Decimal(str(raw["bid"])),
        ask=Decimal(str(raw["ask"])),
        delta=Decimal(str(raw["delta"])),
        implied_volatility=Decimal(str(raw["implied_volatility"])),
    )


def case_from_dict(raw: dict[str, Any]) -> ExperimentCase:
    policy_raw = raw["policy"]
    return ExperimentCase(
        case_id=raw["case_id"],
        symbol=raw["symbol"],
        event_type=raw["event_type"],
        event_date=raw["event_date"],
        days_until_event=int(raw["days_until_event"]),
        underlying_price=Decimal(str(raw["underlying_price"])),
        account_equity=Decimal(str(raw["account_equity"])),
        expected_direction=Direction(raw["expected_direction"]),
        confidence=Decimal(str(raw["confidence"])),
        evidence=tuple(raw["evidence"]),
        invalidation_conditions=tuple(raw["invalidation_conditions"]),
        option_chain=tuple(quote_from_dict(item) for item in raw["option_chain"]),
        policy=Policy(
            max_risk_pct=Decimal(str(policy_raw["max_risk_pct"])),
            min_confidence=Decimal(str(policy_raw["min_confidence"])),
            min_evidence_items=int(policy_raw["min_evidence_items"]),
            min_dte=int(policy_raw["min_dte"]),
            max_dte=int(policy_raw["max_dte"]),
            max_bid_ask_ratio=Decimal(str(policy_raw["max_bid_ask_ratio"])),
            max_contracts=int(policy_raw["max_contracts"]),
        ),
    )
