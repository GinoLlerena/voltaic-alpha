"""Fetch the veto backtest's inputs from the host, read-only.

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, decisions 4(a)
and 11, approved by the owner on 12 October 2026 for this export.

  veto_export.py bars     SPY and RSP daily bars, with the worker's own settings
  veto_export.py signals  the signals the worker stored, for the reference check
  veto_export.py snapshots  one stored decision snapshot a session, for calibration
  veto_export.py spot     SPY 5-minute bars from 09:30 to 10:05 New York
  veto_export.py options  traded option prices around the 10:00 decision
  veto_export.py chains   Part 2: wide call chains for the qualifying sessions

`options` is the long one: a call to the host per session. It keeps one file per
session and skips the sessions it already has, so it can be stopped and run
again.

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
import math
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


def spot(first_year: int) -> int:
    rows: list[list[Any]] = []
    feeds: set[str] = set()
    params: dict[str, Any] = {}
    today = datetime.now(UTC).date()
    for year in range(first_year, today.year + 1):
        for month in (1, 4, 7, 10):
            start = date(year, month, 1)
            if start > today:
                break
            last = date(year + (month == 10), (month + 3) % 12 or 12, 1) - timedelta(days=1)
            reply = unpack(on_host(
                "spot.py", start.isoformat(), "" if last >= today else last.isoformat()
            )["gz"])
            feeds.add(reply["feed"])
            params = reply["params"]
            found = reply["rows"]
            rows.extend(found)
            print(f"{start}: {len(found)} bars in {len({row[0] for row in found})} sessions")
    if len(feeds) != 1:
        raise SystemExit(f"the feed changed between calls: {sorted(feeds)}")
    keys = [(row[0], row[1]) for row in rows]
    if keys != sorted(set(keys)):
        raise SystemExit("bars are not unique and ordered")
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "spy_5min_open.json"
    path.write_text(json.dumps({
        "columns": ["session", "bar_open_new_york", "volume_weighted_price", "close", "volume"],
        "rows": rows,
    }, separators=(",", ":")))
    record(path, feed=feeds.pop(), endpoint="/v2/stocks/SPY/bars", params=params,
           window="bars opening 09:30 to 10:00 New York",
           coverage={"bars": len(rows), "sessions": len({row[0] for row in rows}),
                     "first": rows[0][0], "last": rows[-1][0]})
    print(f"wrote {path}")
    return 0


#: Strikes within this of the previous close, calls and puts: the candidates
#: for the at-the-money reading.
NEAR_MONEY = 0.01
#: Calls over this range of the previous close cover both delta bands at every
#: expiry the worker reads. Used for the sessions that have a stored snapshot
#: to compare with.
WIDE_CALLS = (0.94, 1.07)
OPTION_PAGE = 600


def _session_file(session: str, previous: float, bounds: list[str]) -> dict[str, Any]:
    """One session's traded option prices, every page, checked for agreement."""
    reply = unpack(on_host("option_bars.py", session, *bounds, "0", str(OPTION_PAGE))["gz"])
    rows = list(reply["rows"])
    requests = reply["requests"]
    while len(rows) < reply["traded"]:
        more = unpack(
            on_host("option_bars.py", session, *bounds, str(len(rows)), str(OPTION_PAGE))["gz"]
        )
        if more["traded"] != reply["traded"] or not more["rows"]:
            raise SystemExit(f"{session}: the pages do not agree; nothing kept, run again")
        rows.extend(more["rows"])
        requests += more["requests"]
    symbols = [row[0] for row in rows]
    if symbols != sorted(set(symbols)):
        raise SystemExit(f"{session}: contracts are not unique and ordered")
    call_low, call_high, put_low, put_high = (int(b) for b in bounds)
    return {
        **{k: reply[k] for k in ("session", "listed", "listed_inactive", "traded", "slots")},
        "previous_close": previous,
        "strikes": {"calls": [call_low, call_high], "puts": [put_low, put_high]},
        "requests": requests,
        "rows": rows,
    }


def _folder_digest(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode() + b" " + hashlib.sha256(file.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _previous_closes() -> list[tuple[str, float]]:
    """(session, previous completed close) for every cached SPY session."""
    spy = json.loads((CACHE / "daily_bars.json").read_text())["symbols"]["SPY"]["bars"]
    closes = [(bar["t"][:10], float(bar["c"])) for bar in spy]
    return [(session, previous)
            for (_, previous), (session, _) in zip(closes, closes[1:], strict=False)]


def options(first: str, last: str, wide_first: str, wide_last: str) -> int:
    folder = CACHE / "options"
    folder.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for session, previous in _previous_closes():
        if not first <= session <= last:
            continue
        path = folder / f"{session}.json"
        if path.exists():
            continue
        put_low = math.floor(previous * (1 - NEAR_MONEY))
        put_high = math.ceil(previous * (1 + NEAR_MONEY))
        wide = wide_first <= session <= wide_last
        call_low = math.floor(previous * WIDE_CALLS[0]) if wide else put_low
        call_high = math.ceil(previous * WIDE_CALLS[1]) if wide else put_high
        bounds = [str(call_low), str(call_high), str(put_low), str(put_high)]
        data = _session_file(session, previous, bounds)
        path.write_text(json.dumps(data, separators=(",", ":")))
        fetched += 1
        print(f"{session}: {data['traded']} of {data['listed']} listed contracts traded"
              f"{' (wide)' if wide else ''}", flush=True)
    files = sorted(folder.glob("*.json"))
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}}
    manifest["files"]["options/"] = {
        "digest": _folder_digest(files),
        "digest_of": "each file's name and SHA-256, in name order",
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "endpoints": ["/v2/options/contracts", "/v1beta1/options/bars"],
        "params": {"timeframe": "5Min", "window": "09:45 to 10:05 New York",
                   "expiry": "10 to 60 days after the session",
                   "strikes": f"calls and puts within {NEAR_MONEY:.0%} of the previous close; "
                              f"calls {WIDE_CALLS[0]} to {WIDE_CALLS[1]} of it from "
                              f"{wide_first} to {wide_last}"},
        "coverage": {"sessions": len(files), "first": files[0].stem, "last": files[-1].stem,
                     "bytes": sum(file.stat().st_size for file in files)},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"fetched {fetched} sessions; {len(files)} held in {folder}")
    return 0


def qualifying_sessions() -> list[str]:
    """Permitted and Breadth-vetoed sessions, from the Step 2 replay of the cache."""
    from options_alpha_lab import veto_replay

    rows, check = veto_replay.load(CACHE)
    if not check["passes"]:
        raise SystemExit("Step 2 parity fails; the qualifying sessions are not trusted")
    return [row.session for row in rows
            if row.bucket in (veto_replay.PERMITTED, veto_replay.BREADTH_VETOED)]


def chains(limit: int | None) -> int:
    """Part 2 entry chains: calls 0.94 to 1.07 of the previous close, no puts.

    Its own folder, so the Step 1 to 3 inputs and their digests never change.
    Approved by the owner on 23 October 2026 (plan section 9).
    """
    wanted = set(qualifying_sessions())
    folder = CACHE / "chains"
    folder.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for session, previous in _previous_closes():
        if session not in wanted or (folder / f"{session}.json").exists():
            continue
        if limit is not None and fetched >= limit:
            break
        bounds = [str(math.floor(previous * WIDE_CALLS[0])),
                  str(math.ceil(previous * WIDE_CALLS[1])), "0", "0"]
        data = _session_file(session, previous, bounds)
        (folder / f"{session}.json").write_text(json.dumps(data, separators=(",", ":")))
        fetched += 1
        print(f"{session}: {data['traded']} of {data['listed']} listed calls traded, "
              f"{data['requests']} requests", flush=True)
    files = sorted(folder.glob("*.json"))
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}}
    manifest["files"]["chains/"] = {
        "digest": _folder_digest(files),
        "digest_of": "each file's name and SHA-256, in name order",
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "endpoints": ["/v2/options/contracts", "/v1beta1/options/bars"],
        "params": {"timeframe": "5Min", "window": "09:45 to 10:05 New York",
                   "expiry": "10 to 60 days after the session",
                   "strikes": f"calls {WIDE_CALLS[0]} to {WIDE_CALLS[1]} of the previous "
                              "close; no puts",
                   "sessions": "Permitted and Breadth-vetoed sessions of the Step 2 replay"},
        "coverage": {"sessions": len(files), "wanted": len(wanted),
                     "first": files[0].stem if files else None,
                     "last": files[-1].stem if files else None,
                     "bytes": sum(file.stat().st_size for file in files)},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"fetched {fetched} sessions; {len(files)} of {len(wanted)} held in {folder}")
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
    sub.add_parser("spot").add_argument("--first-year", type=int, default=2024)
    o = sub.add_parser("options")
    o.add_argument("--first", default="2024-02-01")
    o.add_argument("--last", default="2026-10-12")
    o.add_argument("--wide-first", default="2026-09-22")
    o.add_argument("--wide-last", default="2026-10-08")
    c = sub.add_parser("chains")
    c.add_argument("--limit", type=int, help="fetch at most this many sessions (a trial)")
    args = parser.parse_args()
    try:
        if args.command == "spot":
            return spot(args.first_year)
        if args.command == "chains":
            return chains(args.limit)
        if args.command == "options":
            return options(args.first, args.last, args.wide_first, args.wide_last)
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
