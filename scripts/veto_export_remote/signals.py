"""Host side of `veto_export.py signals`: the signals the worker stored.

Read-only: one SELECT. For each session it prints each distinct signal the
worker recorded and how many snapshots carried it, so a replay can be held to
what the worker actually saw.
"""

import base64
import gzip
import json
import os
import sys
from collections import Counter

from sqlalchemy import create_engine, text

first, last = sys.argv[1].replace("-", ""), sys.argv[2].replace("-", "")
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    snapshots = connection.execute(
        text(
            "select snapshot_id from market_snapshots "
            "where snapshot_id >= :low and snapshot_id < :high"
        ),
        {"low": f"spy-agent-{first}", "high": f"spy-agent-{last}U"},
    ).all()
    found = connection.execute(
        text(
            "select m.snapshot_id, s.signal_id, s.family, s.direction, s.strength, s.summary "
            "from signals s join market_snapshots m on m.id = s.market_snapshot_id "
            "where m.snapshot_id >= :low and m.snapshot_id < :high"
        ),
        {"low": f"spy-agent-{first}", "high": f"spy-agent-{last}U"},
    ).all()


def day(snapshot_id: str) -> str:
    stamp = snapshot_id.removeprefix("spy-agent-")[:8]
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"


per_day = Counter(day(row[0]) for row in snapshots)
seen = Counter((day(r[0]), r[1], r[2], r[3], str(r[4]), r[5]) for r in found)
out = {
    "snapshots": dict(sorted(per_day.items())),
    "signals": [
        {"day": k[0], "signal_id": k[1], "family": k[2], "direction": k[3],
         "strength": k[4], "summary": k[5], "snapshots": n}
        for k, n in sorted(seen.items())
    ],
}
packed = base64.b64encode(gzip.compress(json.dumps(out, separators=(",", ":")).encode())).decode()
print(json.dumps({"gz": packed}))
