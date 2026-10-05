"""How many SQL statements the decision page costs, held to a budget.

`CSA-005`. The page asks eight endpoints about one decision. Each used to load
every record set the decision has and map two or three of them: 78 statements
for a plain decision and 107 for one with a Paper lifecycle, on every 15-second
refresh, on a host that also runs the worker. A view now reads a part only when
an endpoint uses it.

The budgets are the measured counts on the committed evidence. A change that
makes an endpoint read more must raise its number here, on purpose.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import event

from options_alpha_lab.api.server import create_app
from options_alpha_lab.presentation import decision as decision_read
from options_alpha_lab.presentation.source import resolve

DB = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"

#: Statements per endpoint: (a decision with no lifecycle, the lifecycle decision).
BUDGET = {
    "summary": (8, 10),
    "market": (5, 5),
    "memo": (2, 2),
    "structure": (2, 2),
    "risk": (4, 4),
    "lifecycle": (4, 8),
    "proof": (7, 10),
    "outcomes": (3, 3),
}
LIFECYCLE = "spy-lifecycle-20260828T154747Z"


class DecisionPageQueryBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = resolve("", DB)
        cls.client = TestClient(create_app(cls.source))
        cls.statements = 0

        def count(*_: object) -> None:
            cls.statements += 1

        cls._count = count
        event.listen(cls.source.engine, "before_cursor_execute", count)
        items = cls.client.get("/api/v1/decisions?limit=200").json()["data"]["items"]
        cls.digests = {i["snapshot_id"]: i["decision_id"] for i in items}

    @classmethod
    def tearDownClass(cls) -> None:
        event.remove(cls.source.engine, "before_cursor_execute", cls._count)

    def cost(self, digest: str, leaf: str) -> int:
        type(self).statements = 0
        response = self.client.get(f"/api/v1/decisions/{digest}/{leaf}")
        self.assertEqual(response.status_code, 200, leaf)
        return type(self).statements

    def test_no_endpoint_exceeds_its_budget_on_any_committed_decision(self) -> None:
        for snapshot_id, digest in self.digests.items():
            for leaf, (plain, lifecycle) in BUDGET.items():
                with self.subTest(decision=snapshot_id, endpoint=leaf):
                    limit = lifecycle if snapshot_id == LIFECYCLE else plain
                    self.assertLessEqual(self.cost(digest, leaf), limit)

    def test_the_whole_page_costs_less_than_half_of_what_it_did(self) -> None:
        for snapshot_id, digest in self.digests.items():
            with self.subTest(decision=snapshot_id):
                page = sum(self.cost(digest, leaf) for leaf in BUDGET)
                before = 107 if snapshot_id == LIFECYCLE else 78
                self.assertLess(page, before / 2)

    def test_a_loaded_view_needs_no_session_afterwards(self) -> None:
        """`load` reads everything at once, for callers that outlive the session."""
        from sqlalchemy.orm import Session

        with Session(self.source.engine) as session:
            row = decision_read.by_hash(session, f"sha256:{self.digests[LIFECYCLE]}")
            assert row is not None
            view = decision_read.load(session, row)
        type(self).statements = 0
        for part in decision_read.PARTS:
            getattr(view, part)
        self.assertTrue(view.reached_the_broker)
        self.assertEqual(type(self).statements, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
