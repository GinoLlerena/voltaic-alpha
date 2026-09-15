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
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab.api import dto
from options_alpha_lab.api.server import build_app, create_app
from options_alpha_lab.persistence.models import Base, Run, WorkerEvent
from options_alpha_lab.presentation import decision as decision_read
from options_alpha_lab.presentation import export
from options_alpha_lab.presentation.source import Resolver, Source, resolve

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


WORKSPACES = ("summary", "proof", "market", "memo", "structure", "risk", "lifecycle")


def _json_paths(client: TestClient) -> list[str]:
    """Every JSON route. Indexes 3 and 4 are decision-scoped summary and proof."""
    digest = client.get("/api/v1/decisions?limit=1").json()["data"]["items"][0]["decision_id"]
    return [
        "/api/v1/system/status",
        "/api/v1/system/proof",
        "/api/v1/decisions",
        *[f"/api/v1/decisions/{digest}/{w}" for w in WORKSPACES],
        "/api/v1/activity",
        "/api/v1/worker/events",
        "/api/v1/incidents",
        "/api/v1/tour",
    ]


def _all_digests(client: TestClient) -> list[str]:
    items = client.get("/api/v1/decisions?limit=200").json()["data"]["items"]
    return [i["decision_id"] for i in items]


def _floats(value: object, path: str = "$") -> list[str]:
    if isinstance(value, float):
        return [path]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _floats(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _floats(v, f"{path}[{i}]")]
    return []


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
        for digest in _all_digests(self.client):
            for workspace in WORKSPACES:
                body = self.client.get(f"/api/v1/decisions/{digest}/{workspace}").json()
                self.assertEqual(body["correlation_id"], f"sha256:{digest}", workspace)

    def test_no_float_crosses_the_boundary_anywhere(self) -> None:
        """Money, prices, strengths, confidences and percentages are all strings.

        Checked as a property over every route and every committed decision,
        because a single `float` that slipped through one field is exactly the
        drift the decimal-string rule exists to prevent.
        """
        paths = [p for p in _json_paths(self.client) if "/decisions/" not in p]
        paths += [
            f"/api/v1/decisions/{d}/{w}" for d in _all_digests(self.client) for w in WORKSPACES
        ]
        for path in paths:
            self.assertEqual(_floats(self.client.get(path).json()), [], path)

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
        self.assertIn("Resolver(LIVE_DATABASE_URL, DB)", app_source)
        self.assertNotIn("create_engine(", app_source)


class WorkspaceTests(unittest.TestCase):
    """The workspaces mirror the dashboard's tabs and add no interpretation."""

    def setUp(self) -> None:
        self.client = _frozen_client()
        self.session = Session(create_engine(f"sqlite+pysqlite:///{DB}", future=True))
        self.rows = {r.snapshot_id: r for r in decision_read.listing(self.session, limit=50)[0]}

    def tearDown(self) -> None:
        self.session.close()

    def _get(self, snapshot_id: str, workspace: str) -> dict:
        digest = self.rows[snapshot_id].decision_hash.removeprefix("sha256:")
        response = self.client.get(f"/api/v1/decisions/{digest}/{workspace}")
        self.assertEqual(response.status_code, 200, workspace)
        return response.json()["data"]

    def test_every_workspace_answers_for_every_decision(self) -> None:
        for snapshot_id in self.rows:
            for workspace in WORKSPACES:
                self._get(snapshot_id, workspace)

    def test_signal_roles_are_the_dashboard_rule(self) -> None:
        for snapshot_id, row in self.rows.items():
            view = decision_read.load(self.session, row)
            pack = view.packs[0] if view.packs else None
            cited = set(pack.evidence_ids) if pack else set()
            expected = {
                s.signal_id: decision_read.signal_role(
                    s.signal_id, s.direction, cited, pack.direction if pack else ""
                )
                for s in view.signals
            }
            got = {s["signal_id"]: s["role"] for s in self._get(snapshot_id, "market")["signals"]}
            self.assertEqual(got, expected, snapshot_id)

    def test_a_refusal_has_no_memo_and_says_so(self) -> None:
        memo = self._get("spy-refusal-2026-08-27", "memo")
        self.assertFalse(memo["produced"])
        self.assertIsNone(memo["thesis"])

    def test_risk_accounting_is_computed_from_the_records(self) -> None:
        view = decision_read.load(self.session, self.rows["spy-lifecycle-20260828T154747Z"])
        risk = self._get("spy-lifecycle-20260828T154747Z", "risk")["accounting"]
        record = view.risks[0]
        self.assertEqual(Decimal(risk["risk_budget"]), Decimal(str(record.risk_budget)))
        self.assertEqual(Decimal(risk["maximum_loss"]), Decimal(str(record.calculated_max_loss)))

    def test_the_lifecycle_traverses_this_decision_only(self) -> None:
        """CIIP-CV-003's defect, checked through the API: another decision's
        orders must never appear under this one."""
        life = self._get("spy-lifecycle-20260828T154747Z", "lifecycle")
        self.assertEqual(len(life["orders"]), 2)
        refusal = self._get("spy-refusal-2026-08-27", "lifecycle")
        self.assertEqual(refusal["orders"], [])
        self.assertFalse(refusal["reached_the_broker"])

    def test_the_receipt_correlation_is_reported_not_assumed(self) -> None:
        """CIIP-VAL-004: the committed receipt belongs to no committed decision."""
        receipt = self._get("spy-lifecycle-20260828T154747Z", "lifecycle")["receipt"]
        self.assertFalse(receipt["belongs"])
        self.assertEqual(receipt["relation"], "OTHER_DECISION")

    def test_every_tour_scene_resolves_in_committed_evidence(self) -> None:
        scenes = self.client.get("/api/v1/tour").json()["data"]
        self.assertTrue(scenes)
        self.assertEqual([s["number"] for s in scenes if s["decision_id"] is None], [])


class AllowlistTests(unittest.TestCase):
    """Free-form stored data passes an allowlist that names what it withheld."""

    def _live_copy(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        live = Path(tmp.name) / "live.db"
        shutil.copy(DB, live)
        return live

    def test_an_unexpected_request_field_is_named_not_shown(self) -> None:
        live = self._live_copy()
        with sqlite3.connect(live) as conn:
            (req_id, body), *_ = conn.execute(
                "select id, serialized_request from prepared_order_requests"
            ).fetchall()
            payload = json.loads(body)
            payload["headers"] = {"APCA-API-SECRET-KEY": "do-not-publish-this"}
            conn.execute(
                "update prepared_order_requests set serialized_request=? where id=?",
                (json.dumps(payload), req_id),
            )
        client = TestClient(create_app(resolve(f"sqlite+pysqlite:///{live}", DB)))
        digest = next(
            d for d in _all_digests(client)
            if client.get(f"/api/v1/decisions/{d}/lifecycle").json()["data"]["intents"]
        )
        response = client.get(f"/api/v1/decisions/{digest}/lifecycle")
        self.assertNotIn("do-not-publish-this", response.text)
        withheld = [w for i in response.json()["data"]["intents"] for r in i["requests"]
                    for w in r["withheld"]]
        self.assertIn("headers", withheld)

    def _with_incident(self, detail: str) -> Path:
        live = self._live_copy()
        with sqlite3.connect(live) as conn:
            run_id = conn.execute("select id from runs limit 1").fetchone()[0]
            conn.execute(
                "insert into incidents (id, run_id, position_id, kind, severity, detail, "
                "execution_state, opened_at, resolved_at, recorded_at, schema_version) "
                "values ('i1', ?, null, 'broker_unreachable', 'high', ?, 'NO_NEW_RISK', "
                "'2026-09-14 15:00:00', null, '2026-09-14 15:00:00', 'h0.1')",
                (run_id, detail),
            )
        return live

    def test_incident_detail_is_withheld_from_the_api(self) -> None:
        canary = "reconciliation could not read broker state: 401 key=PKLEAKED123"
        live = self._with_incident(canary)
        client = TestClient(create_app(resolve(f"sqlite+pysqlite:///{live}", DB)))
        response = client.get("/api/v1/incidents")
        self.assertNotIn("PKLEAKED123", response.text)
        (incident,) = response.json()["data"]
        self.assertEqual(incident["kind"], "broker_unreachable")
        self.assertEqual(incident["withheld"], ["detail"])

    def test_incident_detail_is_withheld_from_the_dashboard(self) -> None:
        """RUI-VAL-007: the public page printed exception text verbatim."""
        from streamlit.testing.v1 import AppTest

        canary = "reconciliation could not read broker state: 401 key=PKLEAKED123"
        live = self._with_incident(canary)
        saved = os.environ.get("DASHBOARD_DATABASE_URL")
        os.environ["DASHBOARD_DATABASE_URL"] = f"sqlite+pysqlite:///{live}"
        try:
            run = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
        finally:
            if saved is None:
                os.environ.pop("DASHBOARD_DATABASE_URL", None)
            else:
                os.environ["DASHBOARD_DATABASE_URL"] = saved
        self.assertFalse(run.exception)
        rendered = " ".join(m.value for m in run.markdown)
        self.assertIn("broker_unreachable", rendered, "the incident must still be shown")
        self.assertIn("detail withheld", rendered)
        self.assertNotIn("PKLEAKED123", rendered)


class PerRequestSourceTests(unittest.TestCase):
    """RUI-VAL-006: the answer is recomputed; only the engines are kept."""

    def test_the_label_count_follows_the_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.db"
            shutil.copy(DB, live)
            client = TestClient(create_app(Resolver(f"sqlite+pysqlite:///{live}", DB)))
            first = client.get("/api/v1/system/status").json()["source_label"]
            with sqlite3.connect(live) as conn:
                conn.execute("delete from decisions where snapshot_id='spy-refusal-2026-08-27'")
            second = client.get("/api/v1/system/status").json()["source_label"]
        self.assertEqual(first, "live worker database (5 decisions)")
        self.assertEqual(second, "live worker database (4 decisions)")

    def test_a_live_source_that_gains_its_first_decision_is_picked_up(self) -> None:
        """Previously a surface started before the worker's first decision stayed
        on committed evidence until it was restarted."""
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.db"
            shutil.copy(DB, live)
            with sqlite3.connect(live) as conn:
                conn.execute("create table held as select * from decisions")
                conn.execute("delete from decisions")
            client = TestClient(create_app(Resolver(f"sqlite+pysqlite:///{live}", DB)))
            before = client.get("/api/v1/system/status").json()
            with sqlite3.connect(live) as conn:
                conn.execute("insert into decisions select * from held")
            after = client.get("/api/v1/system/status").json()
        self.assertEqual(before["source_mode"], "FROZEN_REPLAY")
        self.assertIn("decided nothing yet", before["source_label"])
        self.assertEqual(after["source_mode"], "LIVE")


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
        """A source built before migration 0004 -- or a live database mid-migration.
        Unavailable is not "did nothing"."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old = Path(tmp.name) / "pre0004.db"
        shutil.copy(DB, old)
        with sqlite3.connect(old) as conn:
            conn.execute("drop table if exists worker_events")
        client = TestClient(create_app(Source(
            create_engine(f"sqlite+pysqlite:///{old}", future=True), "FROZEN_REPLAY", "test"
        )))
        data = client.get("/api/v1/worker/events").json()["data"]
        self.assertFalse(data["available"])
        self.assertIn("0004", data["reason"])
        self.assertEqual(data["items"], [])

    def test_committed_evidence_now_holds_the_table(self) -> None:
        data = _frozen_client().get("/api/v1/worker/events").json()["data"]
        self.assertTrue(data["available"])

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
