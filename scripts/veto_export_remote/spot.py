"""Host side of `veto_export.py spot`: SPY 5-minute bars around the decision.

Read-only: one paged GET with the worker's own stock feed. It prints the bars
that open from 09:30 to 10:00 New York for each session in the range, unadjusted,
so an option price can be set against the underlying price of the same bar.
Nothing is written on the host and no credential is printed.
"""

import base64
import gzip
import json
import sys
from datetime import datetime
from datetime import time as clock
from zoneinfo import ZoneInfo

from options_alpha_lab.config import resolved_env
from options_alpha_lab.providers.alpaca_readonly import MARKET_DATA_HOST, ReadOnlyAlpacaClient

NEW_YORK = ZoneInfo("America/New_York")
FIRST, LAST = clock(9, 30), clock(10, 0)

start, end = sys.argv[1], sys.argv[2]
env = resolved_env()
client = ReadOnlyAlpacaClient(env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", ""))
feed = client.detect_stock_feed("SPY")
params = {"timeframe": "5Min", "limit": 10000, "feed": feed, "adjustment": "raw", "start": start}
# The subscription refuses an `end` inside the last fifteen minutes, so the
# range that reaches today is left open.
if end:
    params["end"] = end
bars, pages = client._paged(f"{MARKET_DATA_HOST}/v2/stocks/SPY/bars", params, "bars")
client.close()
rows = []
for bar in bars:
    opened = datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).astimezone(NEW_YORK)
    if FIRST <= opened.time() <= LAST:
        rows.append([opened.date().isoformat(), opened.strftime("%H:%M"), bar["vw"], bar["c"],
                     bar["v"]])
out = {"feed": feed, "pages": pages, "params": {k: v for k, v in params.items()
                                               if k not in ("start", "end")},
       "columns": ["session", "bar_open_new_york", "volume_weighted_price", "close", "volume"],
       "rows": rows}
packed = base64.b64encode(gzip.compress(json.dumps(out, separators=(",", ":")).encode())).decode()
print(json.dumps({"gz": packed}))
