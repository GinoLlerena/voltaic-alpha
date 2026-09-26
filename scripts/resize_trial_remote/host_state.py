"""Read-only snapshot of host state before a resize: schema, counts, backups, watchdog, units.

Runs ON THE INSTANCE, sent by scripts/resize_trial.py over Cloud Assistant.
"""

import json
import pathlib
import subprocess


def q(sql):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["/usr/bin/sudo", "-u", "postgres", "psql", "-d", "options_alpha", "-tAc", sql],
        capture_output=True,
        text=True,
    ).stdout.strip()


def active(u):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["/usr/bin/systemctl", "is-active", u], capture_output=True, text=True
    ).stdout.strip()


b = json.loads(pathlib.Path("/var/lib/options-alpha/backup.json").read_text())
o = json.loads(pathlib.Path("/var/lib/options-alpha/offsite.json").read_text())
w = json.loads(pathlib.Path("/var/run/options-alpha/watchdog.json").read_text())
h = json.loads(pathlib.Path("/var/run/options-alpha/health.json").read_text())
mem = dict(line.split(":")[0:2] for line in open("/proc/meminfo") if ":" in line)
print(
    json.dumps(
        {
            "mem_total_kb": int(mem["MemTotal"].split()[0]),
            "alembic": q("select version_num from alembic_version"),
            "tables": int(
                q("select count(*) from information_schema.tables where table_schema='public'")
            ),
            "decisions": int(q("select count(*) from decisions")),
            "market_snapshots": int(q("select count(*) from market_snapshots")),
            "decision_outcomes": int(q("select count(*) from decision_outcomes")),
            "open_incidents": int(q("select count(*) from incidents where resolved_at is null")),
            "lease_heartbeat_age_s": int(
                float(
                    q(
                        "select extract(epoch from now()-heartbeat_at) from worker_leases"
                        " where released_at is null order by heartbeat_at desc limit 1"
                    )
                    or -1
                )
            ),
            "backup": {
                k: b.get(k)
                for k in (
                    "at",
                    "verified",
                    "path",
                    "bytes",
                    "tables",
                    "rows_restored",
                    "alembic_revision",
                )
            },
            "offsite": {k: o.get(k) for k in ("checked_at", "ok", "newest_daily_at", "detail")},
            "watchdog_ok": w.get("ok"),
            "watchdog_failures": [c["name"] for c in w["checks"] if not c["ok"]],
            "worker": {
                "mode_flag": "observe"
                if "--mode observe"
                in open("/etc/systemd/system/options-alpha-worker.service").read()
                else "CHECK",
                "last_tick_at": h.get("last_tick_at"),
                "last_action": h.get("last_action"),
                "healthy": h.get("healthy"),
            },
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
                    "options-alpha-port80",
                )
            },
            "not_enabled": [
                u
                for u in (
                    "postgresql",
                    "options-alpha-worker",
                    "options-alpha",
                    "options-alpha-api",
                    "options-alpha-backup.timer",
                    "options-alpha-backup-offsite.timer",
                    "options-alpha-watchdog.timer",
                    "options-alpha-capacity",
                    "options-alpha-port80",
                )
                if subprocess.run(  # noqa: S603 - fixed argv, no shell
                    ["/usr/bin/systemctl", "is-enabled", u], capture_output=True, text=True
                ).stdout.strip()
                != "enabled"
            ],
        }
    )
)
