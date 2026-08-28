"""Exact request preparation.

The distinctive claim is that the bytes sent to the broker are the bytes that
were approved. That requires the request to be built once, hashed, reviewed, and
then submitted unchanged - not rebuilt at submit time from the same inputs and
assumed to be identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..hashing import payload_hash
from .intent import OrderIntent

ADAPTER_VERSION = "alpaca-py-0.44-mleg"
REQUEST_SCHEMA_VERSION = "mleg_limit.v1"


class RequestError(ValueError):
    """The intent cannot be turned into a valid broker request."""


@dataclass(frozen=True)
class PreparedRequest:
    intent_hash: str
    client_order_id: str
    body: dict[str, Any]
    request_hash: str
    adapter_version: str
    request_schema_version: str
    prepared_at: datetime
    expires_at: datetime

    def matches(self, intent: OrderIntent) -> bool:
        return self.intent_hash == intent.intent_hash


def prepare_mleg_request(intent: OrderIntent, *, now: datetime | None = None) -> PreparedRequest:
    """Map an approved intent to the exact native MLeg limit order body."""
    if len(intent.legs) < 2:
        raise RequestError("a vertical requires two legs")
    if intent.strategy_quantity < 1:
        raise RequestError("strategy quantity must be positive")
    if intent.limit_price <= 0:
        raise RequestError("limit price must be positive")

    body: dict[str, Any] = {
        "order_class": "mleg",
        "qty": str(intent.strategy_quantity),
        "type": "limit",
        # Options are day-only at Alpaca; an unsupported TIF is a silent reject.
        "time_in_force": "day",
        "limit_price": format(intent.limit_price.quantize(Decimal("0.01")), "f"),
        "client_order_id": intent.client_order_id,
        "legs": [
            {
                "symbol": leg.symbol,
                "ratio_qty": str(leg.ratio_qty),
                "side": leg.side,
                "position_intent": leg.position_intent,
            }
            for leg in intent.legs
        ],
    }
    prepared_at = now or datetime.now(UTC)
    return PreparedRequest(
        intent_hash=intent.intent_hash,
        client_order_id=intent.client_order_id,
        body=body,
        request_hash=payload_hash(body),
        adapter_version=ADAPTER_VERSION,
        request_schema_version=REQUEST_SCHEMA_VERSION,
        prepared_at=prepared_at,
        expires_at=intent.expires_at,
    )
