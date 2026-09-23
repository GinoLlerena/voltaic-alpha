#!/usr/bin/env python3
"""Measure what the host actually uses, before anyone decides it can use less.

The 2c4g -> 2c2g resize (cost analysis §7.3) is gated on a baseline taken
across at least one full trading session, including a backup/restore overlap.
This samples every signal that section names, every 30 seconds, into one JSON
line per sample under /var/lib/options-alpha/capacity/. It changes nothing, holds
no credential, and runs at low priority so it does not distort what it measures.

Cumulative kernel counters (swap-ins, CPU jiffies, OOM kills) are stored raw;
the summary turns them into rates. `--summarize` reads the files back and prints
peaks and percentiles, optionally restricted to a UTC window such as a session.

Standard library only: this has to run with nothing installed, on the box it
is measuring.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OUT_DIR = Path("/var/lib/options-alpha/capacity")
INTERVAL_SECONDS = 30
HEALTH_FILE = Path("/var/run/options-alpha/health.json")
CGROUP_ROOT = Path("/sys/fs/cgroup/system.slice")
#: unit -> cgroup directory, relative to system.slice
SERVICES = {
    "worker": "options-alpha-worker.service",
    "dashboard": "options-alpha.service",
    "api": "options-alpha-api.service",
    "postgres": "system-postgresql.slice/postgresql@16-main.service",
    "backup": "options-alpha-backup.service",
    "offsite": "options-alpha-backup-offsite.service",
}
PROBES = {
    "api_status": "http://127.0.0.1:8600/api/v1/system/status",
    "api_decisions": "http://127.0.0.1:8600/api/v1/decisions",
    "dashboard": "http://127.0.0.1:8501/_stcore/health",
}


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _kv(path: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in (_read(Path(path)) or "").splitlines():
        parts = line.replace(":", " ").split()
        if len(parts) >= 2 and parts[1].isdigit():
            values[parts[0]] = int(parts[1])
    return values


def _psi(resource: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in (_read(Path(f"/proc/pressure/{resource}")) or "").splitlines():
        kind, *fields = line.split()
        for field in fields:
            name, _, value = field.partition("=")
            if name == "avg10":
                out[kind] = float(value)
    return out


def _probe(url: str) -> dict[str, Any]:
    start = time.monotonic()

    def elapsed() -> float:
        return round((time.monotonic() - start) * 1000, 1)

    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - loopback only
            response.read()
            status = response.status
    except Exception as exc:  # noqa: BLE001 - a failed probe is data, not a crash
        return {"ok": False, "error": type(exc).__name__, "ms": elapsed()}
    return {"ok": status == 200, "status": status, "ms": elapsed()}


def _psql(query: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, local peer auth, no credential
            ["/usr/bin/sudo", "-u", "postgres", "/usr/bin/psql",
             "-d", "options_alpha", "-tAqc", query],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def sample() -> dict[str, Any]:
    mem = _kv("/proc/meminfo")
    vm = _kv("/proc/vmstat")
    cpu_line = (_read(Path("/proc/stat")) or "").splitlines()[0].split()[1:]
    services: dict[str, Any] = {}
    for name, rel in SERVICES.items():
        base = CGROUP_ROOT / rel
        current = _read(base / "memory.current")
        if current is not None:
            peak = _read(base / "memory.peak")
            services[name] = {"current": int(current), "peak": int(peak) if peak else None}

    health: dict[str, Any] = {}
    try:
        raw = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
        tick = raw.get("last_tick_at")
        health = {
            "tick_age_s": round(
                (datetime.now(UTC) - datetime.fromisoformat(tick)).total_seconds(), 1
            ) if isinstance(tick, str) else None,
            "management_batch_ms": raw.get("management_batch_ms"),
            "ticks": raw.get("ticks"),
            "healthy": raw.get("healthy"),
        }
    except (OSError, ValueError):
        health = {"error": "health file unreadable"}

    lease_age = _psql(
        "select round(extract(epoch from now() - heartbeat_at))::int "
        "from worker_leases where released_at is null order by heartbeat_at desc limit 1"
    )
    connections = _psql("select count(*) from pg_stat_activity where datname = 'options_alpha'")

    return {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mem_total_kb": mem.get("MemTotal"),
        "mem_available_kb": mem.get("MemAvailable"),
        "cached_kb": mem.get("Cached"),
        "swap_total_kb": mem.get("SwapTotal"),
        "swap_free_kb": mem.get("SwapFree"),
        "pswpin": vm.get("pswpin"), "pswpout": vm.get("pswpout"), "oom_kill": vm.get("oom_kill"),
        # user nice system idle iowait irq softirq steal
        "cpu_jiffies": [int(v) for v in cpu_line[:8]],
        "load1": float((_read(Path("/proc/loadavg")) or "0").split()[0]),
        "psi": {r: _psi(r) for r in ("memory", "cpu", "io")},
        "services": services,
        "db_connections": int(connections) if connections and connections.isdigit() else None,
        "lease_age_s": int(lease_age) if lease_age and lease_age.lstrip("-").isdigit() else None,
        "worker": health,
        "latency": {name: _probe(url) for name, url in PROBES.items()},
    }


def collect() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        started = time.monotonic()
        try:
            record = sample()
        except Exception as exc:  # noqa: BLE001 - one bad sample must not end the baseline
            record = {"at": datetime.now(UTC).isoformat(timespec="seconds"),
                      "sample_error": type(exc).__name__}
        path = OUT_DIR / f"{record['at'][:10]}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        time.sleep(max(1.0, INTERVAL_SECONDS - (time.monotonic() - started)))


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]


def _series(rows: list[dict[str, Any]], getter: Any) -> list[Any]:
    out = []
    for row in rows:
        try:
            value = getter(row)
        except (KeyError, TypeError):
            continue
        if value is not None:
            out.append(value)
    return out


def summarize(start: str | None, end: str | None) -> None:
    rows = []
    for path in sorted(OUT_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            outside = (start and row["at"] < start) or (end and row["at"] > end)
            if "sample_error" not in row and not outside:
                rows.append(row)
    if len(rows) < 2:
        print("not enough samples")
        return
    first, last = rows[0], rows[-1]
    span = datetime.fromisoformat(last["at"]) - datetime.fromisoformat(first["at"])
    print(f"window {first['at']} -> {last['at']}  "
          f"({span.total_seconds() / 3600:.1f} h, {len(rows)} samples)")
    print(f"MemTotal {first['mem_total_kb'] / 1024:.0f} MiB")

    avail = _series(rows, lambda r: r["mem_available_kb"] / 1024)
    used = _series(rows, lambda r: (r["mem_total_kb"] - r["mem_available_kb"]) / 1024)
    print(f"used MiB   p50 {_pct(used, .5):.0f}  p95 {_pct(used, .95):.0f}  max {max(used):.0f}")
    print(f"avail MiB  min {min(avail):.0f}  p5 {_pct(avail, .05):.0f}")

    swapped_in = last["pswpin"] - first["pswpin"]
    swapped_out = last["pswpout"] - first["pswpout"]
    ooms = last["oom_kill"] - first["oom_kill"]
    print(f"swap-ins {swapped_in}  swap-outs {swapped_out}  OOM kills {ooms}")

    j0, j1 = first["cpu_jiffies"], last["cpu_jiffies"]
    total = sum(j1) - sum(j0)
    busy = 100 * (1 - (j1[3] - j0[3]) / total)
    iowait = 100 * (j1[4] - j0[4]) / total
    print(f"cpu busy {busy:.1f}%  iowait {iowait:.2f}%")

    for res in ("memory", "cpu", "io"):
        some = _series(rows, lambda r, res=res: r["psi"][res].get("some", 0.0))
        print(f"psi {res:6} some avg10  max {max(some):.2f}  p95 {_pct(some, .95):.2f}")

    for name in SERVICES:
        current = _series(rows, lambda r, n=name: r["services"][n]["current"])
        peaks = _series(rows, lambda r, n=name: r["services"][n]["peak"])
        if current:
            peak = max(peaks) / 2**20 if peaks else 0.0
            print(f"cgroup {name:9} current max {max(current) / 2**20:.0f} MiB  "
                  f"peak {peak:.0f} MiB")

    for name in PROBES:
        ms = _series(
            rows, lambda r, n=name: r["latency"][n]["ms"] if r["latency"][n]["ok"] else None
        )
        failures = sum(1 for r in rows if not r["latency"][name].get("ok"))
        if ms:
            print(f"latency {name:13} p50 {_pct(ms, .5):.0f} ms  p95 {_pct(ms, .95):.0f} ms  "
                  f"max {max(ms):.0f}  failures {failures}")

    ticks = _series(rows, lambda r: r["worker"]["tick_age_s"])
    batch = _series(rows, lambda r: r["worker"]["management_batch_ms"])
    lease = _series(rows, lambda r: r["lease_age_s"])
    conns = _series(rows, lambda r: r["db_connections"])
    if ticks:
        print(f"worker tick age  max {max(ticks):.0f} s   "
              f"batch ms max {max(batch) if batch else 'n/a'}")
    if lease:
        print(f"lease heartbeat age  max {max(lease)} s")
    if conns:
        print(f"db connections  max {max(conns)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--start", help="UTC ISO lower bound for --summarize")
    parser.add_argument("--end", help="UTC ISO upper bound for --summarize")
    args = parser.parse_args()
    if args.summarize:
        summarize(args.start, args.end)
    else:
        # Priority is set by the unit (Nice=10); setting it here as well would
        # compound to 19.
        collect()


if __name__ == "__main__":
    main()
