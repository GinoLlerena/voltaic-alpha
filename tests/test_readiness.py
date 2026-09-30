"""Stop readiness (scheduled-stop design §7): anything unknown counts against a stop."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.orm import Session

from options_alpha_lab.api.server import create_app
from options_alpha_lab.calendar import committed_calendar
from options_alpha_lab.config import load_settings
from options_alpha_lab.persistence.models import Incident
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.presentation.readiness import stop_readiness
from options_alpha_lab.presentation.source import resolve

CAL = committed_calendar()
# Friday 2 Oct 2026, 17:35 ET: after the close and the post-close backup.
NOW = datetime(2026, 10, 2, 21, 35, tzinfo=UTC)
POST_CLOSE = datetime(2026, 10, 2, 21, 1, tzinfo=UTC)


class ReadinessCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{self.dir / 'r.db'}",
        })
        self.engine = build_engine(settings)
        create_schema(self.engine)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def files(self, *, backup_at: datetime = POST_CLOSE, verified: bool = True,
              keys: list[str] | None = None, offsite_ok: bool = True) -> tuple[str, str]:
        backup = self.dir / "backup.json"
        backup.write_text(json.dumps({"at": backup_at.isoformat(), "verified": verified}))
        offsite = self.dir / "offsite.json"
        friday = ["daily/2026-10-02.dump.age", "weekly/2026-10-02.dump.age"]
        offsite.write_text(json.dumps({"ok": offsite_ok, "keys": friday if keys is None else keys}))
        return str(backup), str(offsite)

    def check(self, *, live: bool = True, **files: object):
        backup, offsite = self.files(**files)  # type: ignore[arg-type]
        with Session(self.engine) as db:
            return stop_readiness(db, now=NOW, live=live, backup_file=backup,
                                  offsite_file=offsite, calendar=CAL)


class Readiness(ReadinessCase):
    def test_a_quiet_evening_with_friday_off_host_is_ready(self) -> None:
        r = self.check()
        self.assertTrue(r.ok, r.reasons)
        self.assertEqual(r.session_due, "2026-10-02")

    def test_an_unresolved_incident_blocks_a_stop(self) -> None:
        with self.engine.begin() as c:
            c.execute(insert(Incident).values(
                id="i1", kind="broker_unreachable", severity="critical", detail="x",
                execution_state="RECONCILING", opened_at=NOW - timedelta(hours=1),
            ))
        r = self.check()
        self.assertFalse(r.ok)
        self.assertIn("1 unresolved incident(s)", r.reasons)

    def test_a_backup_from_before_the_close_blocks_a_stop(self) -> None:
        r = self.check(backup_at=POST_CLOSE - timedelta(hours=2))
        self.assertFalse(r.ok)
        self.assertTrue(any("since the 2026-10-02 close" in x for x in r.reasons))

    def test_an_unverified_backup_blocks_a_stop(self) -> None:
        self.assertFalse(self.check(verified=False).ok)

    def test_the_session_copy_must_be_recorded_off_host(self) -> None:
        for kwargs in ({"keys": ["daily/2026-10-01.dump.age"]}, {"offsite_ok": False}):
            with self.subTest(kwargs):
                r = self.check(**kwargs)  # type: ignore[arg-type]
                self.assertFalse(r.ok)
                self.assertFalse(r.session_copy_off_host)

    def test_missing_records_count_against_a_stop(self) -> None:
        with Session(self.engine) as db:
            r = stop_readiness(db, now=NOW, live=True, backup_file=str(self.dir / "none"),
                               offsite_file=str(self.dir / "none"), calendar=CAL)
        self.assertFalse(r.ok)
        self.assertEqual(len(r.reasons), 2)

    def test_a_non_live_source_is_never_ready(self) -> None:
        self.assertFalse(self.check(live=False).ok)


class Endpoint(unittest.TestCase):
    def test_the_committed_evidence_is_never_ready_to_stop(self) -> None:
        demo = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"
        client = TestClient(create_app(resolve("", demo), backup_file="/nonexistent",
                                       offsite_file="/nonexistent"))
        body = client.get("/api/v1/system/stop-readiness").json()
        self.assertFalse(body["data"]["ok"])
        self.assertIn("the API is not reading the live database", body["data"]["reasons"])
        self.assertEqual(body["source_mode"], "FROZEN_REPLAY")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
