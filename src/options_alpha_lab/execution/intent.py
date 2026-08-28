"""Immutable approved order intents.

An intent is the only thing the gateway will act on. It is created from an
approved decision, hashed, and never mutated. The client order id is derived
from the intent hash rather than generated, which is what makes a retry after an
ambiguous response idempotent: the same approved intent can only ever produce the
same client order id, so a duplicate submit collides instead of opening a second
strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..architecture.contracts import DecisionOutcome, SpreadStrategy
from ..hashing import payload_hash

INTENT_TTL = timedelta(seconds=90)
CLIENT_ID_PREFIX = "oa"


class IntentError(ValueError):
    """The decision cannot produce an approved intent."""


@dataclass(frozen=True)
class IntentLeg:
    symbol: str
    ratio_qty: int
    side: str
    position_intent: str


@dataclass(frozen=True)
class OrderIntent:
    """Immutable. Every field contributes to the hash and the client order id."""

    decision_hash: str
    strategy: SpreadStrategy
    legs: tuple[IntentLeg, ...]
    strategy_quantity: int
    limit_price: Decimal
    approval_reference: str
    created_at: datetime
    expires_at: datetime

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "decision_hash": self.decision_hash,
            "strategy": self.strategy.value,
            "strategy_quantity": self.strategy_quantity,
            "limit_price": self.limit_price,
            "approval_reference": self.approval_reference,
            "legs": [
                {
                    "symbol": leg.symbol,
                    "ratio_qty": leg.ratio_qty,
                    "side": leg.side,
                    "position_intent": leg.position_intent,
                }
                for leg in self.legs
            ],
        }

    @property
    def intent_hash(self) -> str:
        return payload_hash(self.payload)

    @property
    def client_order_id(self) -> str:
        # Derived, never random: the same approved intent must always produce the
        # same id so a retry collides rather than duplicating.
        digest = self.intent_hash.split(":", 1)[1]
        return f"{CLIENT_ID_PREFIX}-{digest[:28]}"

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) > self.expires_at


def build_open_intent(
    outcome: DecisionOutcome,
    decision_hash: str,
    *,
    approval_reference: str,
    now: datetime | None = None,
) -> OrderIntent:
    """Create the opening intent for an approved decision. Refuses anything else."""
    if outcome.spread is None or outcome.risk is None or not outcome.risk.approved:
        raise IntentError("only an approved spread may produce an order intent")
    spread = outcome.spread
    created = now or datetime.now(UTC)

    # A debit vertical: buy the long leg to open, sell the short leg to open.
    legs = (
        IntentLeg(spread.long_contract_symbol, 1, "buy", "buy_to_open"),
        IntentLeg(spread.short_contract_symbol, 1, "sell", "sell_to_open"),
    )
    return OrderIntent(
        decision_hash=decision_hash,
        strategy=spread.strategy,
        legs=legs,
        strategy_quantity=spread.quantity,
        limit_price=spread.estimated_debit.quantize(Decimal("0.01")),
        approval_reference=approval_reference,
        created_at=created,
        expires_at=created + INTENT_TTL,
    )


def build_close_intent(
    opening: OrderIntent, *, approval_reference: str, limit_price: Decimal,
    now: datetime | None = None,
) -> OrderIntent:
    """Mirror an opening intent to close it. Never widens size or adds legs."""
    created = now or datetime.now(UTC)
    legs = tuple(
        IntentLeg(
            leg.symbol,
            leg.ratio_qty,
            "sell" if leg.side == "buy" else "buy",
            "sell_to_close" if leg.position_intent == "buy_to_open" else "buy_to_close",
        )
        for leg in opening.legs
    )
    return OrderIntent(
        decision_hash=opening.decision_hash,
        strategy=opening.strategy,
        legs=legs,
        strategy_quantity=opening.strategy_quantity,
        limit_price=limit_price.quantize(Decimal("0.01")),
        approval_reference=approval_reference,
        created_at=created,
        expires_at=created + INTENT_TTL,
    )
