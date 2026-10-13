"""Fetch the veto backtest's inputs from the host, read-only.

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, decisions 4(a)
and 11, approved by the owner on 12 October 2026 for this export.

  veto_export.py bars     SPY and RSP daily bars, with the worker's own settings
  veto_export.py signals  the signals the worker stored, for the reference check
  veto_export.py snapshots  one stored decision snapshot a session, for calibration

The host-side programs are the files in `veto_export_remote/`, sent as they are,
so what was reviewed is what runs. Each is one read: a market-data GET or a
SELECT. Nothing is written on the host, no service is touched, and no credential
leaves it. The data lands in `.cache/veto_backtest/`, which git ignores; what is
committed is the manifest, naming each file by its digest.

Cloud Assistant returns about 24 kB per command, so bars are fetched a year at
a time and a snapshot's contracts a page at a time.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import resize_trial as rt  # noqa: E402 - the Cloud Assistant helpers live there

REMOTE = Path(__file__).with_name("veto_export_remote")
CACHE = Path(".cache/veto_backtest")
MANIFEST = Path("docs/analysis/options_alpha_veto_backtest_manifest.json")
ENV_FILE = "/etc/options-alpha.env"


def on_host(name: str, *argv: str) -> dict[str, Any]:
    """Run one reviewed host-side program and return its JSON line."""
    code = (REMOTE / name).read_text(encoding="utf-8")
    args = " ".join(f"'{a}'" for a in argv)
    script = "\n".join([
        "set -euo pipefail",
        "cd /opt/options-alpha",
        f"set -a; . {ENV_FILE}; set +a",
        f"{rt.VENV_PYTHON} - {args} <<'PY'\n{code}\nPY",
    ])
    return dict(json.loads(rt.remote(script, timeout=180).strip().splitlines()[-1]))


def unpack(packed: str) -> Any:
    return json.loads(gzip.decompress(base64.b64decode(packed)))


def record(path: Path, **facts: Any) -> None:
    """Add one file to the committed manifest, by digest."""
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}}
    manifest["files"][path.name] = {
        "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **facts,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def bars(first_year: int) -> int:
    symbols: dict[str, list[dict[str, Any]]] = {}
    feeds: set[str] = set()
    params: dict[str, Any] = {}
    today = datetime.now(UTC).date()
    for year in range(first_year, today.year + 1):
        end = "" if year == today.year else date(year, 12, 31).isoformat()
        reply = on_host("bars.py", f"{year}-01-01", end)
        feeds.add(reply["feed"])
        params = {k: v for k, v in reply["params"].items() if k not in ("start", "end")}
        for symbol, rows in unpack(reply["gz"]).items():
            symbols.setdefault(symbol, []).extend(rows)
        print(f"{year}: " + ", ".join(f"{s} {len(r)}" for s, r in unpack(reply["gz"]).items()))
    if len(feeds) != 1:
        raise SystemExit(f"the feed changed between calls: {sorted(feeds)}")
    for symbol, rows in symbols.items():
        stamps = [row["t"] for row in rows]
        if stamps != sorted(set(stamps)):
            raise SystemExit(f"{symbol}: bars are not unique and ordered")
    feed = feeds.pop()
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "daily_bars.json"
    path.write_text(json.dumps({
        "fixture_version": "sensitivity_bars.v1",
        "provider": "alpaca",
        "endpoint": "/v2/stocks/{symbol}/bars",
        "feed": feed,
        "symbols": {symbol: {"bars": rows} for symbol, rows in symbols.items()},
    }, separators=(",", ":")))
    record(
        path, feed=feed, endpoint="/v2/stocks/{symbol}/bars", params=params,
        coverage={s: {"bars": len(r), "first": r[0]["t"][:10], "last": r[-1]["t"][:10]}
                  for s, r in symbols.items()},
    )
    print(f"wrote {path}")
    return 0


def signals(first: str, last: str) -> int:
    data = unpack(on_host("signals.py", first, last)["gz"])
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "stored_signals.json"
    path.write_text(json.dumps(data, indent=1))
    record(path, source="live worker database: signals joined to market_snapshots",
           first=first, last=last, sessions=len(data["snapshots"]),
           snapshots=sum(data["snapshots"].values()))
    print(f"wrote {path}: {len(data['snapshots'])} sessions, {len(data['signals'])} distinct")
    return 0


#: Contracts per call, sized to stay under Cloud Assistant's output limit.
PAGE = 400


def snapshots(first: str, last: str) -> int:
    sessions: dict[str, Any] = {}
    day = date.fromisoformat(first)
    while day <= date.fromisoformat(last):
        if day.weekday() < 5:
            reply = unpack(on_host("snapshots.py", day.isoformat(), "0", str(PAGE))["gz"])
            if reply["snapshot"] is None:
                print(f"{day}: no snapshot at or after the decision time "
                      f"({reply['stored']} stored)")
            else:
                rows = list(reply["rows"])
                while len(rows) < reply["snapshot"]["kept_contracts"]:
                    more = unpack(
                        on_host("snapshots.py", day.isoformat(), str(len(rows)), str(PAGE))["gz"]
                    )
                    if more["snapshot"]["snapshot_id"] != reply["snapshot"]["snapshot_id"]:
                        raise SystemExit(f"{day}: the snapshot changed between pages")
                    if not more["rows"]:
                        raise SystemExit(f"{day}: a page came back empty")
                    rows.extend(more["rows"])
                symbols = [row[0] for row in rows]
                if symbols != sorted(set(symbols)):
                    raise SystemExit(f"{day}: contracts are not unique and ordered")
                sessions[day.isoformat()] = {
                    **reply["snapshot"], "columns": reply["columns"], "rows": rows,
                }
                print(f"{day}: {reply['snapshot']['snapshot_id']}, {len(rows)} of "
                      f"{reply['snapshot']['chain_contracts']} contracts kept")
        day += timedelta(days=1)
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "decision_snapshots.json"
    path.write_text(json.dumps({"sessions": sessions}, separators=(",", ":")))
    record(path, source="live worker database: market_snapshots.payload, reduced on the host",
           rule="first snapshot at or after 10:00 New York; calls with stored delta 0.20 to "
                "0.75, and either type struck within 1% of the underlying price",
           first=first, last=last, sessions=len(sessions),
           contracts=sum(len(s["rows"]) for s in sessions.values()))
    print(f"wrote {path}: {len(sessions)} sessions")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bars")
    b.add_argument("--first-year", type=int, default=2023)
    s = sub.add_parser("signals")
    s.add_argument("--first", default="2026-09-22")
    s.add_argument("--last", default="2026-10-09")
    n = sub.add_parser("snapshots")
    n.add_argument("--first", default="2026-09-22")
    n.add_argument("--last", default="2026-10-12")
    args = parser.parse_args()
    try:
        if args.command == "bars":
            return bars(args.first_year)
        if args.command == "snapshots":
            return snapshots(args.first, args.last)
        return signals(args.first, args.last)
    except rt.Stop as stop:
        print(f"stopped: {stop}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
