"""Latency, memory and worker statistics for one UTC window, from the capacity samples.

Runs ON THE INSTANCE: argv = start end (UTC ISO). Sent by scripts/resize_trial.py.
"""

import json
import pathlib
import subprocess
import sys
from datetime import datetime

start, end = sys.argv[1], sys.argv[2]
rows = []
for p in sorted(pathlib.Path("/var/lib/options-alpha/capacity").glob("*.jsonl")):
    for line in p.read_text().splitlines():
        r = json.loads(line)
        if "sample_error" not in r and start <= r["at"] <= end:
            rows.append(r)


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))] if v else None


lat = {
    n: [r["latency"][n]["ms"] for r in rows if r["latency"][n].get("ok")]
    for n in ("api_status", "api_decisions", "dashboard")
}
fails = {n: sum(1 for r in rows if not r["latency"][n].get("ok")) for n in lat}
psi = [r["psi"]["memory"].get("some", 0.0) for r in rows]

# Longest stretch, in seconds, with MemAvailable under the floor. Measured from
# sample timestamps, not a count, so a gap in sampling cannot shorten it.
LOW_MIB = 256
longest, run_start = 0.0, None
for r in rows:
    low = r["mem_available_kb"] / 1024 < LOW_MIB
    if low and run_start is None:
        run_start = r["at"]
    if not low and run_start is not None:
        run_start = None
    if run_start is not None:
        span = (datetime.fromisoformat(r["at"]) - datetime.fromisoformat(run_start)).total_seconds()
        longest = max(longest, span)
j = subprocess.run(  # noqa: S603 - fixed argv, no shell
    [
        "/usr/bin/journalctl",
        "-u",
        "options-alpha-worker",
        "--since",
        start.replace("T", " ")[:16] + " UTC",
        "--until",
        end.replace("T", " ")[:16] + " UTC",
        "-o",
        "cat",
        "--no-pager",
    ],
    capture_output=True,
    text=True,
).stdout


def unit_failures(unit):
    """systemd's own record: each failed run logs 'Failed with result'."""
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            "/usr/bin/journalctl",
            "-u",
            unit,
            "--since",
            start.replace("T", " ")[:16] + " UTC",
            "--until",
            end.replace("T", " ")[:16] + " UTC",
            "--no-pager",
        ],
        capture_output=True,
        text=True,
    ).stdout
    return sum(1 for line in out.splitlines() if "Failed with result" in line)


ticks = [
    json.loads(line)
    for line in j.splitlines()
    if line.startswith("{") and '"event": "tick"' in line
]
print(
    json.dumps(
        {
            "samples": len(rows),
            "first": rows[0]["at"] if rows else None,
            "last": rows[-1]["at"] if rows else None,
            "p95_ms": {n: pct(v, 0.95) for n, v in lat.items()},
            "probe_failures": fails,
            "oom_kills": (rows[-1]["oom_kill"] - rows[0]["oom_kill"]) if rows else None,
            "psi_memory_max": max(psi) if psi else None,
            "psi_memory_nonzero": sum(1 for x in psi if x > 0),
            "low_memory_longest_s": longest,
            "mem_available_min_mib": min(r["mem_available_kb"] for r in rows) / 1024
            if rows
            else None,
            "tick_age_max_s": max((r["worker"].get("tick_age_s") or 0) for r in rows)
            if rows
            else None,
            "lease_age_max_s": max((r.get("lease_age_s") or 0) for r in rows) if rows else None,
            "ticks": len(ticks),
            # The hourly backup restores every dump into a scratch database, so a
            # failed backup run also covers a failed restore.
            "backup_failures": unit_failures("options-alpha-backup.service"),
            "offsite_failures": unit_failures("options-alpha-backup-offsite.service"),
            "failed_ticks": [
                t.get("detail", "")[:80] for t in ticks if t.get("action") == "OBSERVE_FAILED"
            ],
        }
    )
)
