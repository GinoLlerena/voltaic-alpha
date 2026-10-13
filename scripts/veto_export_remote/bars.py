"""Host side of `veto_export.py bars`: SPY and RSP daily bars for one date range.

Read-only. It asks the market-data endpoint the worker uses, with the worker's
own feed and adjustment, and prints one JSON line. Nothing is written on the
host and no credential is printed.
"""

import base64
import gzip
import json
import sys

from options_alpha_lab.config import resolved_env
from options_alpha_lab.evidence import PARTICIPATION_SYMBOL
from options_alpha_lab.providers.alpaca_readonly import MARKET_DATA_HOST, ReadOnlyAlpacaClient

start, end = sys.argv[1], sys.argv[2]
env = resolved_env()
client = ReadOnlyAlpacaClient(env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", ""))
client.stock_feed = client.detect_stock_feed("SPY")
params = {
    "timeframe": "1Day",
    "limit": 1000,
    "feed": client.stock_feed,
    "adjustment": "split",
    "start": start,
}
# The worker sends no `end`, and the subscription refuses one that reaches the
# last fifteen minutes. An open range is the worker's own request.
if end:
    params["end"] = end
out = {}
pages = {}
for symbol in ("SPY", PARTICIPATION_SYMBOL):
    url = f"{MARKET_DATA_HOST}/v2/stocks/{symbol}/bars"
    bars, pages[symbol] = client._paged(url, params, "bars")
    out[symbol] = [{k: bar[k] for k in ("t", "o", "h", "l", "c", "v")} for bar in bars]
client.close()
packed = base64.b64encode(gzip.compress(json.dumps(out, separators=(",", ":")).encode())).decode()
print(json.dumps({"feed": client.stock_feed, "pages": pages, "params": params, "gz": packed}))
