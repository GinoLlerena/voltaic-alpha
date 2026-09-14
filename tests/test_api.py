"""The presentation API: its boundary first, its contract second.

`RUI-1`. The order of the classes is the order of what would hurt most. An API
that serves a wrong number is a bug; an API that can reach a broker, publish a
credential, or accept a write has changed what this project is. Those properties
are asserted against the running application and its real import graph, not
against a description of either.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab.api import dto
from options_alpha_lab.api.server import build_app, create_app
from options_alpha_lab.persistence.models import Base, Run, WorkerEvent
from options_alpha_lab.presentation import decision as decision_read
from options_alpha_lab.presentation import export
from options_alpha_lab.presentation.source import Source, resolve

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "demo" / "h0_demo.db"
NOW = datetime(2026, 9, 14, 15, 0, tzinfo=UTC)
MUTATIONS = ("post", "put", "patch", "delete")

#: Modules that can reach a broker, a model, or credentials. The API must load
#: none of them -- not merely avoid calling them.
FORBIDDEN_MODULES = (
    "alpaca",
    "openai",
    "options_alpha_lab.execution",
    "options_alpha_lab.providers",
    "options_alpha_lab.worker",
    "options_alpha_lab.agent",
    "options_alpha_lab.config",
    "options_alpha_lab.secrets_setup",
    "options_alpha_lab.lifecycle",
)


def _frozen_client() -> TestClient:
    return TestClient(create_app(resolve("", DB), clock=lambda: NOW))


def _json_paths(client: TestClient) -> list[str]:
    digest = client.get("/api/v1/decisions?limit=1").json()["data"]["items"][0]["decision_id"]
    return [
        "/api/v1/system/status",
        "/api/v1/system/proof",
        "/api/v1/decisions",
        f"/api/v1/decisions/{digest}/summary",
        f"/api/v1/decisions/{digest}/proof",
        "/api/v1/activity",
        "/api/v1/worker/events",
    ]


class ReadOnlyBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _frozen_client()

    def test_openapi_publishes_only_get(self) -> None:
        spec = self.client.get("/openapi.json").json()
        methods = {m for ops in spec["paths"].values() for m in ops}
        self.assertEqual(methods, {"get"}, f"non-GET operations published: {methods}")

    def test_no_route_accepts_a_write(self) -> None:
        """Walks included routers, and proves it walked them.

        FastAPI keeps an included router as a nested object rather than
        flattening its routes, so a naive walk sees only `/openapi.json` and
        passes without checking a single API route. The count assertion is what
        stops a framework upgrade from turning this back into that.
        """
        def walk(routes):  # type: ignore[no-untyped-def]
            for route in routes:
                nested = getattr(route, "original_router", None)
                if nested is not None:
                    yield from walk(nested.routes)
                else:
                    yield route

        api_routes = [
            r for r in walk(self.client.app.routes)
            if getattr(r, "path", "").startswith("/api/v1")
        ]
        published = self.client.get("/openapi.json").json()["paths"]
        self.assertEqual(len(api_routes), len(published), "route walk missed routes")
        for route in api_routes:
            allowed = set(route.methods)
            self.assertLessEqual(allowed, {"GET", "HEAD"}, f"{route.path} accepts {allowed}")

    def test_every_mutation_method_is_refused(self) -> None:
        for path in _json_paths(self.client):
            for method in MUTATIONS:
                status = getattr(self.client, method)(path).status_code
                self.assertEqual(status, 405, f"{method.upper()} {path} returned {status}")

    def test_the_import_graph_cannot_reach_a_broker_or_model(self) -> None:
        """Checked in a clean interpreter, so no other test can pre-load a module."""
        probe = (
            "import sys, json\n"
            "import options_alpha_lab.api.server as s\n"
            "s.create_app\n"
            "print(json.dumps(sorted(sys.modules)))\n"
        )
        result = subprocess.run(  # noqa: S603 - fixed argv, no user input
            [sys.executable, "-c", probe], capture_output=True, text=True, cwd=ROOT, check=True
        )
        loaded = json.loads(result.stdout.strip().splitlines()[-1])
        leaked = sorted(
            m for m in loaded for f in FORBIDDEN_MODULES if m == f or m.startswith(f + ".")
        )
        self.assertEqual(leaked, [], f"API import graph reaches: {leaked}")

    def test_interactive_docs_are_not_served(self) -> None:
        self.assertEqual(self.client.get("/docs").status_code, 404)
        self.assertEqual(self.client.get("/redoc").status_code, 404)

    def test_no_raw_payload_or_private_field_crosses(self) -> None:
        for path in _json_paths(self.client):
            text = self.client.get(path).text
            self.assertNotIn('"payload":', text, f"{path} leaks a raw provider payload")
            self.assertNotIn('"account_number"', text.replace('"[redacted]"', ""), path)
            self.assertNotIn('"host":', text, f"{path} names a host")
            for marker in ("sk-", "APCA-API", "ALPACA_SECRET", "PASSWORD"):
                self.assertNotIn(marker, text, f"{path} carries {marker}")


class CredentialSelectionTests(unittest.TestCase):
    """`RUI-VAL-002`: the API uses the dashboard's read-only URL, never the worker's."""

    def test_the_worker_url_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.db"
            shutil.copy(DB, live)
            saved = {k: os.environ.get(k) for k in ("DATABASE_URL", "DASHBOARD_DATABASE_URL")}
            try:
                os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{live}"
                os.environ.pop("DASHBOARD_DATABASE_URL", None)
                body = TestClient(build_app()).get("/api/v1/system/status").json()
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        self.assertEqual(body["source_mode"], "FROZEN_REPLAY")


class EnvelopeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _frozen_client()

    def test_every_json_response_states_its_source(self) -> None:
        for path in _json_paths(self.client):
            body = self.client.get(path).json()
            self.assertEqual(body["schema_version"], "public.v1", path)
            self.assertEqual(body["source_mode"], "FROZEN_REPLAY", path)
            self.assertEqual(body["source_label"], "committed evidence", path)
            self.assertEqual(body["observed_at"], NOW.isoformat(), path)

    def test_decision_scoped_responses_carry_the_correlation(self) -> None:
        digest = _json_paths(self.client)[3].split("/")[4]
        for path in _json_paths(self.client)[3:5]:
            self.assertEqual(self.client.get(path).json()["correlation_id"], f"sha256:{digest}")

    def test_timestamps_are_utc_with_an_offset(self) -> None:
        """SQLite returns naive datetimes; a naive time in a contract is misplaced."""
        summary = self.client.get(_json_paths(self.client)[3]).json()["data"]
        for stamp in (summary["decided_at"], summary["observation"]["source_time"]):
            self.assertTrue(stamp.endswith("+00:00"), stamp)

    def test_prices_cross_as_decimal_strings(self) -> None:
        summary = self.client.get(_json_paths(self.client)[3]).json()["data"]
        self.assertIsInstance(summary["observation"]["underlying_price"], str)

    def test_a_live_source_is_labelled_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.db"
            shutil.copy(DB, live)
            client = TestClient(create_app(resolve(f"sqlite+pysqlite:///{live}", DB)))
            body = client.get("/api/v1/system/status").json()
        self.assertEqual(body["source_mode"], "LIVE")
        self.assertEqual(body["source_label"], "live worker database (5 decisions)")

    def test_a_broken_live_source_falls_back_and_says_why(self) -> None:
        source = resolve("postgresql+psycopg://nobody@127.0.0.1:1/none", DB)
        self.assertEqual(source.mode, "FROZEN_REPLAY")
        self.assertIn("live source unavailable", source.label)

    def test_unknown_and_malformed_identifiers(self) -> None:
        self.assertEqual(self.client.get(f"/api/v1/decisions/{'0' * 64}/summary").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/decisions/nope/summary").status_code, 422)
        self.assertEqual(self.client.get("/api/v1/decisions?cursor=%%%").status_code, 400)


class ParityWithRecordsTests(unittest.TestCase):
    """The API adds a boundary, not an interpretation."""

    def setUp(self) -> None:
        self.client = _frozen_client()
        self.session = Session(create_engine(f"sqlite+pysqlite:///{DB}", future=True))

    def tearDown(self) -> None:
        self.session.close()

    def test_the_proof_file_is_the_exact_manifest_bytes(self) -> None:
        for row in decision_read.listing(self.session, limit=50)[0]:
            digest = row.decision_hash.removeprefix("sha256:")
            view = decision_read.load(self.session, row)
            response = self.client.get(f"/api/v1/proof/{digest}.json")
            self.assertEqual(response.content, export.render(view), row.snapshot_id)
            self.assertEqual(response.headers["X-Proof-Digest"], export.digest(view))

    def test_the_enveloped_proof_names_the_same_digest(self) -> None:
        row = decision_read.listing(self.session, limit=1)[0][0]
        digest = row.decision_hash.removeprefix("sha256:")
        enveloped = self.client.get(f"/api/v1/decisions/{digest}/proof").json()["data"]
        kept = self.client.get(f"/api/v1/proof/{digest}.json")
        self.assertEqual(enveloped["manifest_digest"], kept.headers["X-Proof-Digest"])

    def test_the_dashboard_and_api_share_one_source_rule(self) -> None:
        app_source = (ROOT / "app.py").read_text()
        self.assertIn("resolve_source(LIVE_DATABASE_URL, DB)", app_source)
        self.assertNotIn("create_engine(LIVE_DATABASE_URL", app_source)


class PaginationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _frozen_client()

    def _walk(self, path: str, key: str, limit: int) -> list[str]:
        seen: list[str] = []
        cursor: str | None = None
        for _ in range(100):
            url = f"{path}?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
            data = self.client.get(url).json()["data"]
            seen += [
                item[key] if isinstance(key, str) else key(item) for item in data["items"]
            ]
            cursor = data["next_cursor"]
            if not cursor:
                return seen
        self.fail("pagination did not terminate")

    def test_decision_pages_cover_every_decision_once(self) -> None:
        ids = self._walk("/api/v1/decisions", "decision_id", 2)
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)

    def test_activity_pages_cover_every_event_once(self) -> None:
        """26 events share only six sequence values. A sequence cursor would lose
        or repeat most of them; this is the test that would catch it."""
        with sqlite3.connect(DB) as conn:
            total = conn.execute("select count(*) from audit_events").fetchone()[0]
        seen: list[tuple[str, int]] = []
        cursor = None
        while True:
            url = "/api/v1/activity?limit=7" + (f"&cursor={cursor}" if cursor else "")
            data = self.client.get(url).json()["data"]
            seen += [(i["correlation_id"], i["sequence"]) for i in data["items"]]
            cursor = data["next_cursor"]
            if not cursor:
                break
        self.assertEqual(len(seen), total)
        self.assertEqual(len(set(seen)), total)


class WorkerEventsTests(unittest.TestCase):
    def test_a_source_without_the_table_says_so(self) -> None:
        """Committed evidence predates 0004. Unavailable is not "did nothing"."""
        data = _frozen_client().get("/api/v1/worker/events").json()["data"]
        self.assertFalse(data["available"])
        self.assertIn("0004", data["reason"])
        self.assertEqual(data["items"], [])

    def test_private_and_free_text_detail_is_withheld_by_name(self) -> None:
        # A file, not :memory: -- every new SQLite connection to :memory: is a
        # fresh empty database, so the API session would read nothing and this
        # test would pass by never seeing the dangerous fields.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        engine = create_engine(f"sqlite+pysqlite:///{Path(tmp.name) / 'w.db'}", future=True)
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Run(id="r", runtime_version="t", policy_version="t", bot_mode="observe",
                       trading_enabled=False, started_at=NOW))
            db.add(WorkerEvent(id="w1", run_id="r", kind="state", event="worker_started",
                               detail={"host": "options-alpha", "mode": "observe",
                                       "writes": "disabled"},
                               occurred_at=NOW, recorded_at=NOW, schema_version="t"))
            db.add(WorkerEvent(id="w2", run_id="r", kind="fault", event="tick_failed",
                               detail={"error": "OperationalError: password=hunter2"},
                               occurred_at=NOW, recorded_at=NOW, schema_version="t"))
            db.commit()
        client = TestClient(create_app(Source(engine, "LIVE", "test")))
        response = client.get("/api/v1/worker/events")
        self.assertNotIn("hunter2", response.text)
        self.assertNotIn("options-alpha", response.text)
        items = {i["event"]: i for i in response.json()["data"]["items"]}
        self.assertEqual(
            items["worker_started"]["detail"], {"mode": "observe", "writes": "disabled"}
        )
        self.assertEqual(items["worker_started"]["withheld"], ["host"])
        self.assertEqual(items["tick_failed"]["withheld"], ["error"])
        faults = client.get("/api/v1/worker/events?faults_only=true").json()["data"]["items"]
        self.assertEqual([f["event"] for f in faults], ["tick_failed"])

    def test_the_allowlist_excludes_the_known_dangerous_keys(self) -> None:
        for key in ("host", "error", "summary"):
            self.assertNotIn(key, dto.WORKER_DETAIL_ALLOWLIST)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
