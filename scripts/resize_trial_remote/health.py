"""Post-start health: units, one lease, API payload, dashboard, reconcile, watchdog.

Runs ON THE INSTANCE, sent by scripts/resize_trial.py over Cloud Assistant.
"""

import json
import pathlib
import subprocess
import urllib.request


def active(u):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["/usr/bin/systemctl", "is-active", u], capture_output=True, text=True
    ).stdout.strip()


def q(sql):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["/usr/bin/sudo", "-u", "postgres", "psql", "-d", "options_alpha", "-tAc", sql],
        capture_output=True,
        text=True,
    ).stdout.strip()


out = {
    "units": {
        u: active(u)
        for u in (
            "postgresql",
            "options-alpha-worker",
            "options-alpha",
            "options-alpha-api",
            "options-alpha-backup.timer",
            "options-alpha-backup-offsite.timer",
            "options-alpha-watchdog.timer",
            "options-alpha-capacity",
        )
    }
}
out["alembic"] = q("select version_num from alembic_version")
out["lease_holders"] = int(
    q("select count(*) from worker_leases where released_at is null and expires_at > now()") or 0
)
try:
    with urllib.request.urlopen("http://127.0.0.1:8600/api/v1/system/status", timeout=15) as r:
        body = json.loads(r.read())
        out["api_status_items"] = len(body.get("data") or [])
except Exception as e:
    out["api_status_items"] = f"ERROR {type(e).__name__}"
try:
    with urllib.request.urlopen("http://127.0.0.1:8501/", timeout=15) as r:
        out["dashboard_http"] = r.status
except Exception as e:
    out["dashboard_http"] = f"ERROR {type(e).__name__}"
j = subprocess.run(
    ["/usr/bin/journalctl", "-u", "options-alpha-worker", "-b", "-o", "cat", "--no-pager"],
    capture_output=True,
    text=True,
).stdout
ev = [json.loads(line) for line in j.splitlines() if line.startswith("{")]
rec = [e for e in ev if e.get("event") == "startup_reconcile"]
out["startup_reconcile_clean"] = bool(rec and rec[-1].get("clean"))
ticks = [e for e in ev if e.get("event") == "tick"]
out["first_tick_at"] = ticks[0]["at"] if ticks else None
out["mem_total_kb"] = int(
    [line for line in open("/proc/meminfo") if line.startswith("MemTotal")][0].split()[1]
)
subprocess.run(
    ["/usr/bin/systemctl", "start", "options-alpha-watchdog.service"], capture_output=True
)
w = json.loads(pathlib.Path("/var/run/options-alpha/watchdog.json").read_text())
out["watchdog_ok"] = w["ok"]
out["watchdog_failures"] = [c["name"] + ": " + c["detail"] for c in w["checks"] if not c["ok"]]
print(json.dumps(out))
