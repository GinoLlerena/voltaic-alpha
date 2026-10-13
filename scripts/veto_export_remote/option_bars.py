"""Host side of `veto_export.py options`: traded option prices around one decision.

Read-only: GET requests for the contract record and for 5-minute trade bars.
For one session it lists the SPY contracts expiring 10 to 60 days later inside
the given strike windows, and prints each one's bars for the four 5-minute
slots from 09:45 to 10:05 New York: the three that end by the 10:00 decision
and the one a fill would use. Nothing is written on the host and no credential
is printed.

Requests are spaced `PAUSE` seconds apart so the worker, which shares the
account's request allowance, is never crowded out.
"""

import base64
import gzip
import json
import sys
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock
from decimal import Decimal
from zoneinfo import ZoneInfo

from options_alpha_lab.config import resolved_env
from options_alpha_lab.providers.alpaca_readonly import (
    MARKET_DATA_HOST,
    PAPER_TRADING_HOST,
    ReadOnlyAlpacaClient,
)

DTE_LOW, DTE_HIGH = 10, 60
SLOTS = (clock(9, 45), clock(9, 50), clock(9, 55), clock(10, 0))
SYMBOLS_PER_REQUEST = 100
PAUSE = 0.5
NEW_YORK = ZoneInfo("America/New_York")

session = date.fromisoformat(sys.argv[1])
call_low, call_high = Decimal(sys.argv[2]), Decimal(sys.argv[3])
put_low, put_high = Decimal(sys.argv[4]), Decimal(sys.argv[5])
offset, limit = int(sys.argv[6]), int(sys.argv[7])

env = resolved_env()
client = ReadOnlyAlpacaClient(env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", ""))
requests = 0


def paged(url, params, collection):
    global requests
    time.sleep(PAUSE)
    items, pages = client._paged(url, params, collection)
    requests += pages
    return items, pages


wanted = {}
for status in ("active", "inactive"):
    listed, _ = paged(
        f"{PAPER_TRADING_HOST}/v2/options/contracts",
        {
            "underlying_symbols": "SPY",
            "status": status,
            "expiration_date_gte": (session + timedelta(days=DTE_LOW)).isoformat(),
            "expiration_date_lte": (session + timedelta(days=DTE_HIGH)).isoformat(),
            "strike_price_gte": str(min(call_low, put_low) if put_high else call_low),
            "strike_price_lte": str(max(call_high, put_high)),
            "limit": 10000,
        },
        "option_contracts",
    )
    for contract in listed:
        strike = Decimal(str(contract["strike_price"]))
        low, high = (call_low, call_high) if contract["type"] == "call" else (put_low, put_high)
        if low <= strike <= high:
            wanted[contract["symbol"]] = status

symbols = sorted(wanted)
start = datetime.combine(session, SLOTS[0], tzinfo=NEW_YORK)
end = datetime.combine(session, SLOTS[-1], tzinfo=NEW_YORK) + timedelta(minutes=4, seconds=59)
rows = []
for index in range(0, len(symbols), SYMBOLS_PER_REQUEST):
    batch = symbols[index:index + SYMBOLS_PER_REQUEST]
    bars, pages = paged(
        f"{MARKET_DATA_HOST}/v1beta1/options/bars",
        {
            "symbols": ",".join(batch),
            "timeframe": "5Min",
            "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "end": end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "limit": 10000,
        },
        "bars",
    )
    if pages != 1:
        # A symbol's bars split over two pages would be merged wrongly.
        raise SystemExit(f"option bars for {session} came back in {pages} pages")
    for symbol in batch:
        slots = [0, 0, 0, 0]
        for bar in bars.get(symbol, []):
            opened = datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).astimezone(NEW_YORK)
            if opened.date() == session and opened.time() in SLOTS:
                slots[SLOTS.index(opened.time())] = [bar["vw"], bar["v"]]
        if any(slots):
            rows.append([symbol, *slots])
client.close()

out = {
    "session": session.isoformat(),
    "listed": len(symbols),
    "listed_inactive": sum(1 for status in wanted.values() if status == "inactive"),
    "traded": len(rows),
    "requests": requests,
    "slots": [slot.strftime("%H:%M") for slot in SLOTS],
    "columns": ["contract_symbol", "then one [volume-weighted price, volume] or 0 per slot"],
    "rows": rows[offset:offset + limit],
}
packed = base64.b64encode(gzip.compress(json.dumps(out, separators=(",", ":")).encode())).decode()
print(json.dumps({"gz": packed}))
