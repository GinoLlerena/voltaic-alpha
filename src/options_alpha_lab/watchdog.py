"""Notice when the worker stops being a worker.

A health file nobody reads is not monitoring, and a backup nobody verifies is
not a backup. This module is the thing that reads them, on a timer, and turns
"the process is gone" or "the last dump was eleven hours ago" into the same
durable incident record that every other integrity failure lands in.

It deliberately checks the *backup* as well as the worker. A dump job that
silently stopped is precisely the failure nobody notices until they need the
dump, so it is treated as a fault in its own right rather than as an operational
detail outside the health story.

Every check fails closed: anything it cannot read is a failure, never a pass.
An unreachable database is reported as unhealthy rather than as "no incidents
found", because a monitor that reports success when it cannot see is worse than
no monitor at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from .persistence.models import Incident, WorkerLease

# Imported rather than restated. The first version of this module carried its
# own copy of the lease name, guessed it wrong, and reported a healthy worker
# as having no lease at all - a monitor disagreeing with reality because it
# had its own private idea of what to look for.
from .worker import DEFAULT_LEASE

#: A tick is due every 300 seconds even with the market closed, so three missed
#: ticks is a wedged process rather than a quiet one. Generous on purpose: an
#: alert that cries wolf gets muted, and a muted alert is not an alert.
MAX_TICK_AGE_SECONDS = 900
#: Backups run hourly; two missed runs is a broken job.
MAX_BACKUP_AGE_SECONDS = 7800

DEFAULT_HEALTH_FILE = "/var/run/options-alpha/health.json"
DEFAULT_BACKUP_FILE = "/var/run/options-alpha/backup.json"
#: The kind this module raises. Excluded from its own incident check: counting
#: it would mean one transient failure latches the watchdog into permanent
#: failure, since its own alarm would keep tripping the alarm.
WATCHDOG_INCIDENT_KIND = "worker_unhealthy"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class WatchdogResult:
    at: datetime
    checks: tuple[Check, ...]

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if not check.ok)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def summary(self) -> str:
        if self.ok:
            return f"{len(self.checks)} checks passed"
        return "; ".join(f"{check.name}: {check.detail}" for check in self.failures)

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "ok": self.ok,
            "summary": self.summary,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail} for c in self.checks
            ],
        }


def _age_seconds(stamp: datetime, now: datetime) -> float:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return (now - stamp).total_seconds()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _check_health_file(path: Path, now: datetime) -> list[Check]:
    health = _read_json(path)
    if health is None:
        return [Check("health_file", False, f"{path} is missing or unreadable")]

    checks = [Check("health_file", True, f"{path} readable")]

    raw_tick = health.get("last_tick_at")
    if not isinstance(raw_tick, str):
        checks.append(Check("tick_recent", False, "health file records no last_tick_at"))
    else:
        try:
            age = _age_seconds(datetime.fromisoformat(raw_tick), now)
        except ValueError:
            checks.append(Check("tick_recent", False, f"unparseable last_tick_at {raw_tick!r}"))
        else:
            fresh = age <= MAX_TICK_AGE_SECONDS
            checks.append(Check(
                "tick_recent", fresh,
                f"last tick {age:.0f}s ago (limit {MAX_TICK_AGE_SECONDS}s)",
            ))

    error = health.get("last_error")
    checks.append(Check(
        "worker_error_free", error is None, "clean" if error is None else str(error),
    ))
    lease_lost = bool(health.get("lease_lost"))
    checks.append(Check(
        "lease_not_lost", not lease_lost,
        "held" if not lease_lost else "the worker reports it lost its lease",
    ))
    return checks


def _check_backup(path: Path, now: datetime) -> list[Check]:
    status = _read_json(path)
    if status is None:
        return [Check("backup_status", False, f"{path} is missing or unreadable")]
    if not status.get("verified"):
        return [Check(
            "backup_status", False,
            f"last backup was not verified: {status.get('detail') or 'no detail'}",
        )]
    raw = status.get("at")
    if not isinstance(raw, str):
        return [Check("backup_status", False, "backup status records no timestamp")]
    try:
        age = _age_seconds(datetime.fromisoformat(raw), now)
    except ValueError:
        return [Check("backup_status", False, f"unparseable backup timestamp {raw!r}")]
    return [Check(
        "backup_status", age <= MAX_BACKUP_AGE_SECONDS,
        f"verified backup {age / 3600:.1f}h ago (limit {MAX_BACKUP_AGE_SECONDS / 3600:.1f}h)",
    )]


def _check_database(engine: Engine, now: datetime) -> list[Check]:
    try:
        with engine.connect() as connection:
            lease = connection.execute(
                select(WorkerLease).where(WorkerLease.name == DEFAULT_LEASE)
            ).mappings().first()
            unresolved = connection.execute(
                select(func.count()).select_from(Incident).where(
                    Incident.resolved_at.is_(None),
                    Incident.kind != WATCHDOG_INCIDENT_KIND,
                )
            ).scalar_one()
    except Exception as exc:  # noqa: BLE001 - any read failure is a failure to see
        return [Check("database", False, f"unreadable: {type(exc).__name__}: {exc}")]

    checks = [Check("database", True, "readable")]
    if lease is None:
        checks.append(Check("lease_present", False, "no worker lease row exists"))
    elif lease["released_at"] is not None:
        checks.append(Check("lease_present", False, "the lease has been released"))
    else:
        age = _age_seconds(lease["heartbeat_at"], now)
        expires = _age_seconds(lease["expires_at"], now)
        checks.append(Check(
            "lease_present", expires <= 0,
            f"heartbeat {age:.0f}s ago, "
            + ("live" if expires <= 0 else f"expired {expires:.0f}s ago"),
        ))
    checks.append(Check(
        "no_unresolved_incidents", unresolved == 0,
        "none" if unresolved == 0 else f"{unresolved} unresolved incident(s)",
    ))
    return checks


def evaluate(
    engine: Engine | None,
    *,
    health_file: str = DEFAULT_HEALTH_FILE,
    backup_file: str = DEFAULT_BACKUP_FILE,
    now: datetime | None = None,
) -> WatchdogResult:
    """Run every check. Nothing here raises; a failure to look is a failed check."""
    stamp = now or datetime.now(UTC)
    checks: list[Check] = []
    checks += _check_health_file(Path(health_file), stamp)
    checks += _check_backup(Path(backup_file), stamp)
    if engine is None:
        checks.append(Check("database", False, "no database configured"))
    else:
        checks += _check_database(engine, stamp)
    return WatchdogResult(at=stamp, checks=tuple(checks))


def _notify(url: str, result: WatchdogResult) -> Check:
    """Post the failure to an operator-configured endpoint, if there is one.

    Off unless `WATCHDOG_WEBHOOK_URL` is set. Without it this module is
    monitoring rather than alerting: it detects and records, but nothing reaches
    anyone who is not already looking at the dashboard. That distinction is
    stated here rather than glossed, because "we have alerting" is exactly the
    kind of claim that is discovered to be false at the worst moment.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    # Only ever speak HTTP. The URL arrives from the environment, and a `file:`
    # or `gopher:` scheme handed to urlopen turns an alerting hook into an
    # arbitrary-read primitive on the one host that holds the broker credentials.
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        return Check("notified", False, f"refusing webhook scheme {scheme!r}")

    payload = json.dumps(result.as_dict()).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - scheme checked above
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - scheme checked above
            return Check("notified", True, f"webhook returned {response.status}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # A failed notification must not mask the failure it was reporting.
        return Check("notified", False, f"webhook failed: {type(exc).__name__}: {exc}")


def main(argv: list[str] | None = None) -> int:
    """Exit 0 when healthy, 1 when not. Intended for a systemd timer."""
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description="Check that the worker is still working.")
    parser.add_argument("--health-file", default=DEFAULT_HEALTH_FILE)
    parser.add_argument("--backup-file", default=DEFAULT_BACKUP_FILE)
    parser.add_argument("--status-file", default="/var/run/options-alpha/watchdog.json")
    parser.add_argument(
        "--record", action="store_true",
        help="open a durable incident when unhealthy (deduplicated while it stays open)",
    )
    args = parser.parse_args(argv)

    engine = None
    url = os.environ.get("DATABASE_URL")
    if url:
        from sqlalchemy import create_engine

        try:
            engine = create_engine(url)
        except Exception:  # noqa: BLE001 - reported as an unreadable database below
            engine = None

    result = evaluate(
        engine, health_file=args.health_file, backup_file=args.backup_file
    )

    webhook = os.environ.get("WATCHDOG_WEBHOOK_URL")
    if webhook and not result.ok:
        result = WatchdogResult(result.at, (*result.checks, _notify(webhook, result)))

    if args.status_file:
        target = Path(args.status_file)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"could not write {target}: {exc}", file=sys.stderr)

    print(json.dumps(result.as_dict(), indent=2))

    if args.record and engine is not None:
        try:
            _record(engine, result)
        except Exception as exc:  # noqa: BLE001 - the exit code still carries the alarm
            print(f"could not record: {exc}", file=sys.stderr)

    return 0 if result.ok else 1


def _record(engine: Engine, result: WatchdogResult) -> None:
    """Open the alarm while it is failing, and close it once it is not.

    A monitor that only ever opens incidents leaves its own history as a list of
    things that were wrong once, with no way to tell which are still wrong. It
    owns this alarm, so it is responsible for both ends of it.
    """
    from sqlalchemy import update

    from .execution.lifecycle import LifecycleStore

    if not result.ok:
        LifecycleStore(engine).open_incident(
            kind=WATCHDOG_INCIDENT_KIND, detail=result.summary, severity="high",
        )
        return

    with engine.begin() as connection:
        connection.execute(
            update(Incident)
            .where(
                Incident.kind == WATCHDOG_INCIDENT_KIND,
                Incident.resolved_at.is_(None),
            )
            .values(resolved_at=result.at)
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
