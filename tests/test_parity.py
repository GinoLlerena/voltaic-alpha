"""`RUI-6`: the two surfaces must make the same claims about the same records.

Streamlit and React do not share a renderer, but they do share a read layer:
`app.py` imports `presentation/*` and holds no ORM query of its own, and the API
builds its DTOs from the same functions. Parity is therefore structural for the
values themselves, and the risk that remains is the DTO layer — reshaping,
rounding, renaming or redacting on the way out, so that the browser shows
something the dashboard does not.

These tests call exactly what `app.py` calls, then ask the API for the same
thing, and compare. Anything the API is allowed to add (an envelope, a schema
version) is stripped rather than special-cased, so a genuine difference in a
value cannot hide behind a difference in shape.
"""

import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from options_alpha_lab.api.server import create_app
from options_alpha_lab.presentation import decision as decision_read
from options_alpha_lab.presentation import export
from options_alpha_lab.presentation import listing as decision_list
from options_alpha_lab.presentation.explain import why_decision
from options_alpha_lab.presentation.horizons import for_decision as horizons_for_decision
from options_alpha_lab.presentation.horizons import overview as horizons_overview
from options_alpha_lab.presentation.proof import proof_tiles
from options_alpha_lab.presentation.source import resolve
from options_alpha_lab.presentation.status import system_status

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "demo" / "h0_demo.db"
NOW = datetime(2026, 9, 14, 15, 0, tzinfo=UTC)


class ParityTests(unittest.TestCase):
    """The dashboard's calls on the left, the API's answers on the right."""

    def setUp(self) -> None:
        self.source = resolve("", DB)
        self.client = TestClient(create_app(self.source, clock=lambda: NOW))
        self.engine = self.source.engine

    def _session(self) -> Session:
        return Session(self.engine)

    def _rows(self, session: Session) -> list[object]:
        """Exactly what `app.py` loads, ordering included."""
        recent, _ = decision_read.listing(session, limit=200)
        return list(reversed(recent))

    def _digests(self) -> list[str]:
        """Hashes as a URL carries them: the record keeps the `sha256:` prefix."""
        with self._session() as session:
            return [row.decision_hash.removeprefix("sha256:") for row in self._rows(session)]

    # -- the export, which is the claim a reviewer keeps -------------------

    def test_exported_bytes_are_identical(self) -> None:
        """The file the browser downloads is the file the dashboard offers.

        Not "equivalent JSON": the same bytes. The digest is over these bytes,
        so a whitespace difference between the two surfaces would give a
        reviewer two files, one digest, and no way to tell which was checked.
        """
        for digest in self._digests():
            with self.subTest(decision=digest[:12]):
                with self._session() as session:
                    row = decision_read.by_hash(session, f"sha256:{digest}")
                    dashboard = export.render(decision_read.load(session, row))
                served = self.client.get(f"/api/v1/proof/{digest}.json").content
                self.assertEqual(dashboard, served)

    def test_exported_digest_matches_the_bytes_on_both_surfaces(self) -> None:
        for digest in self._digests():
            with self.subTest(decision=digest[:12]):
                with self._session() as session:
                    row = decision_read.by_hash(session, f"sha256:{digest}")
                    view = decision_read.load(session, row)
                    dashboard_digest = export.digest(view)
                response = self.client.get(f"/api/v1/proof/{digest}.json")
                self.assertEqual(dashboard_digest, response.headers["X-Proof-Digest"])
                # And the digest the /proof endpoint reports for the same decision.
                body = self.client.get(f"/api/v1/decisions/{digest}/proof").json()
                self.assertEqual(dashboard_digest, body["data"]["manifest_digest"])

    # -- what the first screen asserts -------------------------------------

    def test_status_cells_say_the_same_thing(self) -> None:
        with self._session() as session:
            cells = system_status(session)
        served = self.client.get("/api/v1/system/status").json()["data"]
        self.assertEqual(len(cells), len(served))
        for cell, row in zip(cells, served, strict=True):
            with self.subTest(cell=cell.label):
                self.assertEqual(cell.label, row["label"])
                self.assertEqual(cell.value, row["value"])
                self.assertEqual(cell.known, row["known"])
                # A cell the dashboard cannot answer must not become an answer.
                self.assertEqual(cell.reason, row["reason"])
                self.assertEqual(cell.source, row["source"])

    def test_proof_tiles_say_the_same_thing(self) -> None:
        with self._session() as session:
            tiles = proof_tiles(session, root=ROOT)
        served = self.client.get("/api/v1/system/proof").json()["data"]
        self.assertEqual(len(tiles), len(served))
        for tile, row in zip(tiles, served, strict=True):
            with self.subTest(tile=tile.label):
                self.assertEqual(tile.value, row["value"])
                self.assertEqual(tile.label, row["label"])
                self.assertEqual(tile.mode, row["mode"])
                self.assertEqual(tile.available, row["available"])
                self.assertEqual(tile.source, row["source"])

    def test_the_decision_list_offers_the_same_decisions(self) -> None:
        with self._session() as session:
            built = decision_list.build(self._rows(session), decision_list.VIEWS[0])
        served = self.client.get(
            f"/api/v1/decisions/grouped?view={decision_list.VIEWS[0]}"
        ).json()["data"]
        # `shown` and `total` exist only in the DTO, so they are checked against
        # what they are derived from rather than against themselves.
        self.assertEqual(len(built.entries), served["shown"])
        with self._session() as session:
            self.assertEqual(decision_read.count(session), served["total"])
        self.assertEqual(built.grouped, served["grouped"])
        self.assertEqual(
            [entry.decision.decision_hash.removeprefix("sha256:") for entry in built.entries],
            [entry["decision_id"] for entry in served["entries"]],
        )
        self.assertEqual(
            [entry.label for entry in built.entries],
            [entry["label"] for entry in served["entries"]],
        )
        # Grouping is the dashboard's, not the DTO's: the counts must survive.
        self.assertEqual(
            [entry.count for entry in built.entries],
            [entry["count"] for entry in served["entries"]],
        )

    # -- what the ticket asserts ------------------------------------------

    def test_why_lines_agree_in_order_and_in_wording(self) -> None:
        """Order carries meaning here: the lines are in authority order."""
        for digest in self._digests():
            with self.subTest(decision=digest[:12]):
                with self._session() as session:
                    row = decision_read.by_hash(session, f"sha256:{digest}")
                    lines = why_decision(session, row)
                served = self.client.get(f"/api/v1/decisions/{digest}/summary").json()
                served_why = served["data"]["why"]
                self.assertEqual(
                    [(line.stage, line.text, line.source, line.present) for line in lines],
                    [(w["stage"], w["text"], w["source"], w["present"]) for w in served_why],
                )

    def test_horizons_agree_including_the_ones_still_waiting(self) -> None:
        for digest in self._digests():
            with self.subTest(decision=digest[:12]):
                with self._session() as session:
                    row = decision_read.by_hash(session, f"sha256:{digest}")
                    horizons = horizons_for_decision(session, row)
                served = self.client.get(f"/api/v1/decisions/{digest}/outcomes").json()["data"]
                self.assertEqual(
                    [(h.horizon, h.state, h.resolved) for h in horizons],
                    [(h["horizon"], h["state"], h["resolved"]) for h in served],
                )

    def test_the_review_caveat_is_the_same_sentence(self) -> None:
        """The caveat is the most load-bearing sentence on the overview."""
        with self._session() as session:
            overview = horizons_overview(session)
        served = self.client.get("/api/v1/outcomes").json()["data"]
        self.assertEqual(overview.caveat, served["caveat"])
        self.assertEqual(overview.resolved, served["resolved"])
        self.assertEqual(overview.pending, served["pending"])


class SurfaceBoundaryTests(unittest.TestCase):
    """Neither surface may reach past the read layer to get its numbers."""

    def test_the_dashboard_holds_no_query_of_its_own(self) -> None:
        """`RUI-1` moved the ad hoc queries behind read services.

        If one comes back, the two surfaces can disagree without either being
        wrong about its own source, and every test above would still pass.
        """
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        for forbidden in ("session.query", "session.execute", "session.scalars", "select("):
            with self.subTest(construct=forbidden):
                self.assertNotIn(forbidden, source)
