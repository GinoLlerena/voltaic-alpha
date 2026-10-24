"""Host side of `veto_export.py paths`: a chosen spread's two legs after entry.

Read-only: one GET for 5-minute trade bars. For one entry it prints each leg's
bars from the 10:05 New York bar of the entry session to the close of the last
session asked for, as [New York date, bar opening time, volume-weighted price,
volume]. Nothing is written on the host and no credential is printed.

Requests are spaced `PAUSE` seconds apart so the worker, which shares the
account's request allowance, is never crowded out.
"""

import base64
import gzip
import json
import sys
import time
from datetime import UTC, date, datetime
from datetime import time as clock
from zoneinfo import ZoneInfo

from options_alpha_lab.config import resolved_env
from options_alpha_lab.providers.alpaca_readonly import MARKET_DATA_HOST, ReadOnlyAlpacaClient

PAUSE = 0.5
NEW_YORK = ZoneInfo("America/New_York")
FIRST_BAR = clock(10, 5)
CLOSE = clock(16, 0)

entry = date.fromisoformat(sys.argv[1])
last = date.fromisoformat(sys.argv[2])
symbols = sorted(sys.argv[3].split(","))
if len(symbols) != 2:
    raise SystemExit("a spread has two legs")

env = resolved_env()
client = ReadOnlyAlpacaClient(env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", ""))
start = datetime.combine(entry, FIRST_BAR, tzinfo=NEW_YORK)
end = datetime.combine(last, CLOSE, tzinfo=NEW_YORK)
time.sleep(PAUSE)
bars, pages = client._paged(
    f"{MARKET_DATA_HOST}/v1beta1/options/bars",
    {
        "symbols": ",".join(symbols),
        "timeframe": "5Min",
        "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "end": end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "limit": 10000,
    },
    "bars",
)
client.close()
if pages != 1:
    # A symbol's bars split over two pages would be merged wrongly.
    raise SystemExit(f"leg bars for {entry} came back in {pages} pages")

legs = {}
for symbol in symbols:
    rows = []
    for bar in bars.get(symbol, []):
        opened = datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).astimezone(NEW_YORK)
        rows.append([opened.date().isoformat(), opened.strftime("%H:%M"), bar["vw"], bar["v"]])
    legs[symbol] = rows

out = {
    "entry": entry.isoformat(),
    "last": last.isoformat(),
    "requests": pages,
    "columns": ["new_york_date", "bar_open_new_york", "volume_weighted_price", "volume"],
    "legs": legs,
}
packed = base64.b64encode(gzip.compress(json.dumps(out, separators=(",", ":")).encode())).decode()
print(json.dumps({"gz": packed}))
