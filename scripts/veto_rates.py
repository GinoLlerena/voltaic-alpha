"""Fetch the veto backtest's risk-free series: a public download, no credential.

Protocol: docs/improvements/options_alpha_veto_backtest_protocol_v0_1.md,
section 2. The series is FRED's DGS3MO, the 3-month Treasury yield, one value a
business day. It lands in `.cache/veto_backtest/`, which git ignores, and the
committed manifest names it by its digest.

Run it with the project's interpreter: `uv run python scripts/veto_rates.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

SERIES = "DGS3MO"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={first}"
CACHE = Path(".cache/veto_backtest")
MANIFEST = Path("docs/analysis/options_alpha_veto_backtest_manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", default="2024-01-01")
    args = parser.parse_args()

    url = URL.format(series=SERIES, first=args.first)
    reply = httpx.get(url, timeout=60, follow_redirects=True)
    reply.raise_for_status()
    body = reply.content
    lines = body.decode().strip().splitlines()
    if not lines[0].endswith(SERIES):
        raise SystemExit(f"unexpected header: {lines[0][:80]}")
    published = [line.split(",") for line in lines[1:] if line.split(",")[1] not in ("", ".")]
    if len(published) < 200:
        raise SystemExit(f"only {len(published)} published values; not written")

    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{SERIES}.csv"
    path.write_bytes(body)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}}
    manifest["files"][path.name] = {
        "digest": "sha256:" + hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "FRED, series DGS3MO, percent a year",
        "url": url,
        "coverage": {"values": len(published), "first": published[0][0],
                     "last": published[-1][0]},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}: {len(published)} values, {published[0][0]} to {published[-1][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
