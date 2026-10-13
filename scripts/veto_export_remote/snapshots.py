"""Host side of `veto_export.py snapshots`: one stored decision snapshot a session.

Read-only: two SELECTs. It takes the first snapshot the worker stored at or
after the study's decision time (10:00 New York) on the given day and prints
the part of its option chain the calibration needs, a page at a time: calls
whose stored delta is between `DELTA_LOW` and `DELTA_HIGH`, and contracts of
either type struck within `NEAR_MONEY` of the underlying price. The account
block of the snapshot is never read out.
"""

import base64
import gzip
import json
import os
import sys
from datetime import time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

DELTA_LOW, DELTA_HIGH = Decimal("0.20"), Decimal("0.75")
NEAR_MONEY = Decimal("0.01")
DECISION_TIME = time(10, 0)
NEW_YORK = ZoneInfo("America/New_York")

day, offset, limit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
stamp = day.replace("-", "")


def emit(out: dict[str, object]) -> None:
    packed = gzip.compress(json.dumps(out, separators=(",", ":"), default=str).encode())
    print(json.dumps({"gz": base64.b64encode(packed).decode()}))


def wanted(quote: dict[str, object], price: Decimal) -> bool:
    if abs(Decimal(str(quote["strike"])) - price) <= NEAR_MONEY * price:
        return True
    delta = quote.get("delta")
    return (
        quote["option_type"] == "call"
        and delta is not None
        and DELTA_LOW <= Decimal(str(delta)) <= DELTA_HIGH
    )


engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    stored = connection.execute(
        text(
            "select id, source_time from market_snapshots "
            "where snapshot_id >= :low and snapshot_id < :high order by source_time"
        ),
        {"low": f"spy-agent-{stamp}", "high": f"spy-agent-{stamp}U"},
    ).all()
    chosen = next(
        (
            row for row in stored
            if row[1].astimezone(NEW_YORK).date().isoformat() == day
            and row[1].astimezone(NEW_YORK).time() >= DECISION_TIME
        ),
        None,
    )
    if chosen is None:
        emit({"day": day, "stored": len(stored), "snapshot": None})
        raise SystemExit(0)
    payload = connection.execute(
        text("select payload from market_snapshots where id = :id"), {"id": chosen[0]}
    ).scalar_one()

if isinstance(payload, str):
    payload = json.loads(payload)
price = Decimal(str(payload["underlying_price"]))
chain = payload["option_chain"]
kept = sorted((q for q in chain if wanted(q, price)), key=lambda q: q["contract_symbol"])
emit({
    "day": day,
    "stored": len(stored),
    "snapshot": {
        "snapshot_id": payload["snapshot_id"],
        "as_of": payload["as_of"],
        "underlying_price": payload["underlying_price"],
        "underlying_source": payload.get("underlying_source"),
        "underlying_session": payload.get("underlying_session"),
        "signals": payload["signals"],
        "data_quality": payload.get("data_quality"),
        "chain_contracts": len(chain),
        "kept_contracts": len(kept),
    },
    "columns": ["contract_symbol", "bid", "ask", "quote_as_of", "delta", "implied_volatility"],
    "rows": [
        [q["contract_symbol"], q["bid"], q["ask"], q["quote_as_of"], q.get("delta"),
         q.get("implied_volatility")]
        for q in kept[offset:offset + limit]
    ],
})
