"""The watchdog has to fail closed, because a monitor that lies is worse than none.

Every check here is written from the direction of failure: what does the
watchdog say when it cannot read the thing it is supposed to be checking? A
monitor that reports "no incidents found" when the database is unreachable
would have reported the worker healthy through the entire 30 August crash loop.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import insert

from options_alpha_lab.calendar import committed_calendar
from options_alpha_lab.config import load_settings
from options_alpha_lab.offsite import (
    MAX_OFFSITE_AGE_SECONDS,
    MAX_STATUS_AGE_SECONDS,
    OffsiteError,
    StoredObject,
)
from options_alpha_lab.persistence.models import Incident, WorkerLease
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.watchdog import (
    DEFAULT_BACKUP_FILE,
    DEFAULT_HEALTH_FILE,
    MAX_BACKUP_AGE_SECONDS,
    MAX_TICK_AGE_SECONDS,
    WATCHDOG_INCIDENT_KIND,
    OffsiteProbe,
    WatchdogResult,
    _notify,
    _record,
    evaluate,
)
from options_alpha_lab.worker import DEFAULT_LEASE

NOW = datetime(2026, 8, 31, 16, 0, tzinfo=UTC)


def ago(seconds: float) -> str:
    return (NOW - timedelta(seconds=seconds)).isoformat()


class WatchdogCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{self.dir / 'w.db'}",
        })
        self.engine = build_engine(self.settings)
        create_schema(self.engine)
        self.healthy_lease()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def healthy_lease(self, *, released: bool = False, expires_in: float = 60) -> None:
        with self.engine.begin() as c:
            c.execute(insert(WorkerLease).values(
                name=DEFAULT_LEASE, owner="o", host="h",
                acquired_at=NOW - timedelta(minutes=5), heartbeat_at=NOW,
                expires_at=NOW + timedelta(seconds=expires_in),
                released_at=NOW if released else None,
            ))

    def health(self, **overrides: object) -> str:
        body = {
            "started_at": ago(3600), "ticks": 12, "last_tick_at": ago(60),
            "last_action": "POSITION_HELD", "last_error": None, "lease_lost": False,
        }
        body.update(overrides)
        path = self.dir / "health.json"
        path.write_text(json.dumps(body))
        return str(path)

    def backup(self, **overrides: object) -> str:
        body = {"at": ago(1800), "verified": True, "path": "/var/backups/x.dump"}
        body.update(overrides)
        path = self.dir / "backup.json"
        path.write_text(json.dumps(body))
        return str(path)

    def run_checks(self, *, health: str | None = None, backup: str | None = None,
                   engine: object = ...) -> object:
        return evaluate(
            self.engine if engine is ... else engine,  # type: ignore[arg-type]
            health_file=health or self.health(),
            backup_file=backup or self.backup(),
            now=NOW,
        )

    def failed(self, result: object) -> set[str]:
        return {c.name for c in result.failures}  # type: ignore[attr-defined]


class HealthyTests(WatchdogCase):
    def test_a_working_system_passes_every_check(self) -> None:
        result = self.run_checks()
        self.assertTrue(result.ok, result.summary)  # type: ignore[attr-defined]
        self.assertIn("checks passed", result.summary)  # type: ignore[attr-defined]


class FailsClosedTests(WatchdogCase):
    def test_a_missing_health_file_is_a_failure_not_a_pass(self) -> None:
        result = self.run_checks(health=str(self.dir / "gone.json"))
        self.assertIn("health_file", self.failed(result))

    def test_unparseable_health_is_a_failure(self) -> None:
        path = self.dir / "bad.json"
        path.write_text("{not json")
        self.assertIn("health_file", self.failed(self.run_checks(health=str(path))))

    def test_an_unreachable_database_is_reported_rather_than_assumed_clean(self) -> None:
        """The 30 August failure mode: the process was dead and nothing said so."""
        self.engine.dispose()
        broken = build_engine(load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/none",
        }))
        result = evaluate(broken, health_file=self.health(),
                          backup_file=self.backup(), now=NOW)
        self.assertIn("database", self.failed(result))
        self.assertNotIn(
            "no_unresolved_incidents",
            {c.name for c in result.checks},
            "an unreadable database must not also report on incidents",
        )

    def test_no_database_configured_is_a_failure(self) -> None:
        self.assertIn("database", self.failed(self.run_checks(engine=None)))


class WorkerStateTests(WatchdogCase):
    def test_a_stale_tick_fails(self) -> None:
        result = self.run_checks(health=self.health(last_tick_at=ago(MAX_TICK_AGE_SECONDS + 1)))
        self.assertIn("tick_recent", self.failed(result))

    def test_a_tick_just_inside_the_limit_passes(self) -> None:
        result = self.run_checks(health=self.health(last_tick_at=ago(MAX_TICK_AGE_SECONDS - 1)))
        self.assertNotIn("tick_recent", self.failed(result))

    def test_a_recorded_worker_error_fails(self) -> None:
        result = self.run_checks(health=self.health(last_error="ProviderError: boom"))
        self.assertIn("worker_error_free", self.failed(result))
        self.assertIn("boom", result.summary)  # type: ignore[attr-defined]

    def test_a_lost_lease_fails(self) -> None:
        self.assertIn("lease_not_lost", self.failed(
            self.run_checks(health=self.health(lease_lost=True))))

    def test_a_released_lease_fails(self) -> None:
        with self.engine.begin() as c:
            c.execute(WorkerLease.__table__.delete())
        self.healthy_lease(released=True)
        self.assertIn("lease_present", self.failed(self.run_checks()))

    def test_an_expired_lease_fails(self) -> None:
        with self.engine.begin() as c:
            c.execute(WorkerLease.__table__.delete())
        self.healthy_lease(expires_in=-30)
        self.assertIn("lease_present", self.failed(self.run_checks()))

    def test_a_missing_lease_row_fails(self) -> None:
        with self.engine.begin() as c:
            c.execute(WorkerLease.__table__.delete())
        self.assertIn("lease_present", self.failed(self.run_checks()))

    def test_an_unresolved_incident_fails(self) -> None:
        with self.engine.begin() as c:
            c.execute(insert(Incident).values(
                id="i1", kind="leg_imbalance", severity="high", detail="d",
                execution_state="NO_NEW_RISK", opened_at=NOW,
            ))
        self.assertIn("no_unresolved_incidents", self.failed(self.run_checks()))

    def test_a_resolved_incident_does_not_fail(self) -> None:
        with self.engine.begin() as c:
            c.execute(insert(Incident).values(
                id="i1", kind="leg_imbalance", severity="high", detail="d",
                execution_state="NO_NEW_RISK", opened_at=NOW, resolved_at=NOW,
            ))
        self.assertNotIn("no_unresolved_incidents", self.failed(self.run_checks()))


class BackupIsPartOfHealthTests(WatchdogCase):
    """A dump job that quietly stopped is the failure nobody notices in time."""

    def test_a_missing_backup_status_fails(self) -> None:
        self.assertIn("backup_status", self.failed(
            self.run_checks(backup=str(self.dir / "gone.json"))))

    def test_a_stale_backup_fails(self) -> None:
        self.assertIn("backup_status", self.failed(
            self.run_checks(backup=self.backup(at=ago(MAX_BACKUP_AGE_SECONDS + 1)))))

    def test_a_dump_that_failed_verification_fails(self) -> None:
        result = self.run_checks(backup=self.backup(verified=False, detail="pg_restore failed"))
        self.assertIn("backup_status", self.failed(result))
        self.assertIn("pg_restore failed", result.summary)  # type: ignore[attr-defined]

    def test_an_unverified_dump_is_not_a_backup_even_when_recent(self) -> None:
        self.assertIn("backup_status", self.failed(
            self.run_checks(backup=self.backup(at=ago(1), verified=False))))


class ReportingTests(WatchdogCase):
    def test_the_summary_names_every_failure_not_just_the_first(self) -> None:
        result = self.run_checks(
            health=self.health(last_error="boom", lease_lost=True),
            backup=self.backup(verified=False),
        )
        for expected in ("worker_error_free", "lease_not_lost", "backup_status"):
            self.assertIn(expected, result.summary)  # type: ignore[attr-defined]

    def test_the_dict_round_trips_as_json_for_the_status_file(self) -> None:
        payload = json.loads(json.dumps(self.run_checks().as_dict()))  # type: ignore[attr-defined]
        self.assertIn("checks", payload)
        self.assertTrue(all({"name", "ok", "detail"} <= set(c) for c in payload["checks"]))


class OwnsItsAlarmTests(WatchdogCase):
    """The watchdog must not be able to trip itself, or latch on permanently."""

    def open_incidents(self, kind: str | None = None) -> int:
        from sqlalchemy import func, select

        with self.engine.connect() as c:
            stmt = select(func.count()).select_from(Incident).where(
                Incident.resolved_at.is_(None))
            if kind is not None:
                stmt = stmt.where(Incident.kind == kind)
            return c.execute(stmt).scalar_one()

    def test_its_own_incident_does_not_make_it_unhealthy(self) -> None:
        """Otherwise one transient failure latches it into failing forever."""
        unhealthy = self.run_checks(health=self.health(last_error="boom"))
        _record(self.engine, unhealthy)  # type: ignore[arg-type]
        self.assertEqual(self.open_incidents(WATCHDOG_INCIDENT_KIND), 1)

        recovered = self.run_checks()
        self.assertTrue(recovered.ok, recovered.summary)  # type: ignore[attr-defined]

    def test_an_incident_raised_by_anything_else_still_counts(self) -> None:
        from sqlalchemy import insert

        with self.engine.begin() as c:
            c.execute(insert(Incident).values(
                id="i9", kind="leg_imbalance", severity="high", detail="d",
                execution_state="NO_NEW_RISK", opened_at=NOW,
            ))
        self.assertIn("no_unresolved_incidents", self.failed(self.run_checks()))

    def test_recovery_resolves_the_alarm_it_opened(self) -> None:
        _record(self.engine, self.run_checks(health=self.health(last_error="boom")))  # type: ignore[arg-type]
        self.assertEqual(self.open_incidents(WATCHDOG_INCIDENT_KIND), 1)

        _record(self.engine, self.run_checks())  # type: ignore[arg-type]
        self.assertEqual(self.open_incidents(WATCHDOG_INCIDENT_KIND), 0)

    def test_recovery_does_not_resolve_anybody_else_s_incident(self) -> None:
        from sqlalchemy import insert

        with self.engine.begin() as c:
            c.execute(insert(Incident).values(
                id="i9", kind="leg_imbalance", severity="high", detail="d",
                execution_state="NO_NEW_RISK", opened_at=NOW,
            ))
        _record(self.engine, WatchdogResult(NOW, ()))  # an all-passed result
        self.assertEqual(self.open_incidents("leg_imbalance"), 1)


class LeaseNameTests(WatchdogCase):
    def test_it_looks_for_the_lease_the_worker_actually_takes(self) -> None:
        """Regression: this module had its own copy of the name and it was wrong.

        A monitor that looks for a lease nobody writes reports every healthy
        worker as leaseless, which is indistinguishable from a real outage.
        """
        self.assertNotIn("lease_present", self.failed(self.run_checks()))
        self.assertEqual(DEFAULT_LEASE, "options-alpha-worker")


class StatusFileLocationTests(unittest.TestCase):
    """Regression: the backup status lived inside the worker's RuntimeDirectory.

    `options-alpha-worker.service` declares `RuntimeDirectory=options-alpha`, so
    systemd deletes `/run/options-alpha` every time that unit stops - taking any
    file another unit wrote there with it. The hourly backup's status file was
    one, so every worker restart, including the host's own unattended-upgrade
    one, produced a "backup is missing" alarm about a backup that was fine.

    State written by one unit must not live inside another unit's lifecycle.
    """

    def test_the_backup_status_is_not_in_the_workers_runtime_directory(self) -> None:
        self.assertFalse(
            DEFAULT_BACKUP_FILE.startswith("/var/run/options-alpha"),
            "systemd deletes this directory whenever the worker stops",
        )
        self.assertFalse(DEFAULT_BACKUP_FILE.startswith("/run/options-alpha"))

    def test_the_health_file_may_stay_there_because_the_worker_owns_it(self) -> None:
        """The distinction that matters: health *is* the worker's runtime state."""
        self.assertTrue(DEFAULT_HEALTH_FILE.startswith("/var/run/options-alpha"))


class WebhookTests(WatchdogCase):
    """The webhook URL comes from the environment, so it is not trusted."""

    def result(self) -> WatchdogResult:
        return self.run_checks(health=self.health(last_error="boom"))  # type: ignore[return-value]

    def test_a_non_http_scheme_is_refused_rather_than_opened(self) -> None:
        for url in ("file:///etc/options-alpha.env", "gopher://x/", "ftp://x/"):
            with self.subTest(url):
                check = _notify(url, self.result())
                self.assertFalse(check.ok)
                self.assertIn("refusing webhook scheme", check.detail)

    def test_a_failing_webhook_is_reported_and_never_raises(self) -> None:
        """A broken notifier must not swallow the failure it was sent to report."""
        check = _notify("http://127.0.0.1:1/hook", self.result())
        self.assertFalse(check.ok)
        self.assertIn("webhook failed", check.detail)


class OffsiteTests(WatchdogCase):
    """Plan §7: a stopped upload must become an incident within 30 hours."""

    def offsite_status(self, **overrides: object) -> str:
        body: dict[str, object] = {"checked_at": ago(3600), "ok": True, "detail": "uploaded"}
        body.update(overrides)
        path = self.dir / "offsite.json"
        path.write_text(json.dumps(body))
        return str(path)

    def listing(self, *hours_old: float) -> list[StoredObject]:
        return [StoredObject(f"daily/{i}", 10, NOW - timedelta(hours=h))
                for i, h in enumerate(hours_old)]

    def run_offsite_checks(self, status: str, lister: object) -> object:
        return evaluate(
            self.engine, health_file=self.health(), backup_file=self.backup(),
            offsite=OffsiteProbe(status, lister),  # type: ignore[arg-type]
            now=NOW,
        )

    def test_a_fresh_copy_and_a_clean_run_pass(self) -> None:
        result = self.run_offsite_checks(self.offsite_status(), lambda: self.listing(3, 27))
        self.assertTrue(result.ok, result.summary)  # type: ignore[attr-defined]

    def test_no_offsite_probe_means_no_offsite_checks(self) -> None:
        names = {c.name for c in self.run_checks().checks}  # type: ignore[attr-defined]
        self.assertFalse(names & {"offsite_run", "offsite_fresh"})

    def test_a_copy_older_than_thirty_hours_fails(self) -> None:
        result = self.run_offsite_checks(self.offsite_status(), lambda: self.listing(31))
        self.assertIn("offsite_fresh", self.failed(result))

    def test_the_newest_copy_decides_not_the_oldest(self) -> None:
        result = self.run_offsite_checks(self.offsite_status(), lambda: self.listing(160, 2))
        self.assertNotIn("offsite_fresh", self.failed(result))

    def test_an_empty_daily_prefix_fails(self) -> None:
        result = self.run_offsite_checks(self.offsite_status(), lambda: [])
        self.assertIn("offsite_fresh", self.failed(result))

    def test_being_unable_to_list_is_a_failure_not_a_pass(self) -> None:
        def unreachable() -> list[StoredObject]:
            raise OffsiteError("listing daily/ failed: Http Status Code: 403")
        result = self.run_offsite_checks(self.offsite_status(), unreachable)
        self.assertIn("offsite_fresh", self.failed(result))

    def test_a_failed_upload_run_fails_even_while_the_copy_is_fresh(self) -> None:
        """The run's own record catches a failure before the 30-hour alarm could."""
        status = self.offsite_status(ok=False, detail="upload of daily/x failed: 403")
        result = self.run_offsite_checks(status, lambda: self.listing(3))
        self.assertIn("offsite_run", self.failed(result))
        self.assertIn("403", result.summary)  # type: ignore[attr-defined]

    def test_a_job_that_stopped_running_fails(self) -> None:
        stale = self.offsite_status(checked_at=ago(MAX_STATUS_AGE_SECONDS + 60))
        result = self.run_offsite_checks(stale, lambda: self.listing(3))
        self.assertIn("offsite_run", self.failed(result))

    def test_a_missing_status_file_fails(self) -> None:
        result = self.run_offsite_checks(str(self.dir / "never-ran.json"), lambda: self.listing(3))
        self.assertIn("offsite_run", self.failed(result))

    def test_the_thirty_hour_limit_is_the_planned_one(self) -> None:
        self.assertEqual(MAX_OFFSITE_AGE_SECONDS, 30 * 3600)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ScheduledStopTests(WatchdogCase):
    """Scheduled-stop design §6: a stopped weekend must not look like a failure."""

    CAL = committed_calendar()
    # Monday 5 Oct 2026, 08:40 ET: ten minutes after a scheduled start.
    MONDAY_START = datetime(2026, 10, 5, 12, 40, tzinfo=UTC)

    def status_file(self, at: datetime) -> str:
        path = self.dir / "offsite.json"
        path.write_text(json.dumps({"checked_at": at.isoformat(), "ok": True, "detail": "x"}))
        return str(path)

    def copies(self, *days: str) -> list[StoredObject]:
        return [StoredObject(f"daily/{d}.dump.age", 10, NOW) for d in days]

    def evaluate_at(self, now: datetime, days: tuple[str, ...], uptime: timedelta | None,
                    status_at: datetime) -> object:
        return evaluate(
            self.engine, health_file=self.health(), backup_file=self.backup(),
            offsite=OffsiteProbe(self.status_file(status_at), lambda: self.copies(*days)),
            now=now, calendar=self.CAL, uptime=uptime,
        )

    def test_friday_s_copy_is_the_right_one_on_monday_morning(self) -> None:
        result = self.evaluate_at(self.MONDAY_START, ("2026-10-01", "2026-10-02"),
                                  None, self.MONDAY_START)
        self.assertNotIn("offsite_fresh", self.failed(result))

    def test_a_missing_session_copy_fails_however_recent_the_newest_is(self) -> None:
        result = self.evaluate_at(self.MONDAY_START, ("2026-10-01",), None, self.MONDAY_START)
        self.assertIn("offsite_fresh", self.failed(result))
        self.assertIn("2026-10-02", result.summary)  # type: ignore[attr-defined]

    def test_the_session_copy_is_not_due_until_three_hours_after_the_close(self) -> None:
        # Friday 2 Oct, 18:30 ET: the copy for that day is not due yet.
        friday_evening = datetime(2026, 10, 2, 22, 30, tzinfo=UTC)
        result = self.evaluate_at(friday_evening, ("2026-10-01",), None, friday_evening)
        self.assertNotIn("offsite_fresh", self.failed(result))

    def test_after_a_start_old_backup_and_upload_records_are_excused(self) -> None:
        friday = datetime(2026, 10, 2, 21, 10, tzinfo=UTC)
        path = self.dir / "backup.json"
        path.write_text(json.dumps({"at": friday.isoformat(), "verified": True, "path": "/x"}))
        result = evaluate(
            self.engine, health_file=self.health(), backup_file=str(path),
            offsite=OffsiteProbe(self.status_file(friday), lambda: self.copies("2026-10-02")),
            now=self.MONDAY_START, calendar=self.CAL, uptime=timedelta(minutes=10),
        )
        failed = self.failed(result)
        self.assertFalse(failed & {"backup_status", "offsite_run"})
        excused = [c for c in result.checks if "boot grace" in c.detail]  # type: ignore[attr-defined]
        # Ten minutes after start the old tick is excused too (its grace is 15 min).
        self.assertEqual({c.name for c in excused}, {"backup_status", "offsite_run", "tick_recent"})
        at_twenty = evaluate(
            self.engine, health_file=self.health(), backup_file=str(path),
            now=self.MONDAY_START, calendar=self.CAL, uptime=timedelta(minutes=20),
        )
        self.assertIn("tick_recent", self.failed(at_twenty))
        self.assertNotIn("backup_status", self.failed(at_twenty))

    def test_the_grace_ends_and_never_excuses_other_checks(self) -> None:
        friday = datetime(2026, 10, 2, 21, 10, tzinfo=UTC)
        path = self.dir / "backup.json"
        path.write_text(json.dumps({"at": friday.isoformat(), "verified": True, "path": "/x"}))
        late = evaluate(
            self.engine, health_file=self.health(), backup_file=str(path),
            now=self.MONDAY_START, calendar=self.CAL, uptime=timedelta(minutes=95),
        )
        self.assertIn("backup_status", self.failed(late))
        broken = evaluate(None, health_file=self.health(), backup_file=self.backup(),
                          now=NOW, uptime=timedelta(minutes=1))
        self.assertIn("database", self.failed(broken))

