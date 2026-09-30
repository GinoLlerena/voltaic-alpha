#!/usr/bin/env python3
"""Refresh src/options_alpha_lab/data/nyse_sessions.json from Alpaca's calendar.

Runs on the operator machine. The request itself is made on the host, with the
worker's read-only client and credentials, over Cloud Assistant: the operator
holds no broker keys. Only dates and open/close times come back.

    python3 scripts/refresh_calendar.py 2026 2027
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import resize_trial as rt

OUT = Path(__file__).resolve().parents[1] / "src/options_alpha_lab/data/nyse_sessions.json"

# Compact on purpose: Cloud Assistant truncates command output near 6 KB.
REMOTE = r'''set -euo pipefail
cd /opt/options-alpha
set -a; . /etc/options-alpha.env; set +a
./.venv/bin/python - <<'PY' 2>/dev/null
import json, os
from options_alpha_lab.providers.alpaca_readonly import ReadOnlyAlpacaClient
env = os.environ.get
c = ReadOnlyAlpacaClient(env("ALPACA_API_KEY", ""), env("ALPACA_SECRET_KEY", ""))
rows = c.calendar("YEAR-01-01", "YEAR-12-31").payload["sessions"]
dates = [r["date"].replace("-", "") for r in rows]
std = ("09:30", "16:00")
odd = {r["date"]: [r["open"], r["close"]] for r in rows if (r["open"], r["close"]) != std}
print(json.dumps({"d": " ".join(dates), "odd": odd}, separators=(",", ":")))
PY'''


def fetch(year: str) -> list[dict[str, str]]:
    out = json.loads(rt.remote(REMOTE.replace("YEAR", year), timeout=180).strip().splitlines()[-1])
    rows = []
    for d in out["d"].split():
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        opens, closes = out["odd"].get(iso, ["09:30", "16:00"])
        rows.append({"date": iso, "open": opens, "close": closes})
    return rows


def main() -> int:
    years = sorted(sys.argv[1:]) or [str(datetime.now(UTC).year), str(datetime.now(UTC).year + 1)]
    sessions = [row for year in years for row in fetch(year)]
    head = {
        "source": "Alpaca /v2/calendar (US equity sessions, Eastern wall clock), fetched on the "
        "host with the worker's read-only client by scripts/refresh_calendar.py on "
        f"{datetime.now(UTC).date().isoformat()}",
        "covered_from": f"{years[0]}-01-01",
        "covered_through": f"{years[-1]}-12-31",
    }
    lines = ["{", *[f"  {json.dumps(k)}: {json.dumps(v)}," for k, v in head.items()]]
    lines.append('  "sessions": [')
    lines += [
        "    " + json.dumps(s, separators=(", ", ": ")) + ("," if i < len(sessions) - 1 else "")
        for i, s in enumerate(sessions)
    ]
    OUT.write_text("\n".join([*lines, "  ]", "}"]) + "\n", encoding="utf-8")
    print(f"{len(sessions)} sessions, {head['covered_from']} to {head['covered_through']} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
