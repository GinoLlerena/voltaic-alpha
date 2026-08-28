"""The judge dashboard must import, read the committed evidence, and hold no controls."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

APP = Path("app.py")


class DashboardTests(unittest.TestCase):
    def test_app_parses(self) -> None:
        ast.parse(APP.read_text(encoding="utf-8"))

    def test_dashboard_exposes_no_control_actions(self) -> None:
        # The surface a judge browses must not be a surface that can trade.
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        names = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for forbidden in ("submit", "ExecutionGateway", "AlpacaBroker", "TradingClient"):
            self.assertNotIn(forbidden, names, f"dashboard must not reference {forbidden}")

    def test_evidence_database_is_committed_and_readable(self) -> None:
        from sqlalchemy import create_engine, func, select
        from sqlalchemy.orm import Session

        from options_alpha_lab.persistence.models import BrokerOrder, Decision

        db = Path("demo/h0_demo.db")
        self.assertTrue(db.exists(), "run scripts/build_demo_db.py")
        engine = create_engine(f"sqlite+pysqlite:///{db}", future=True)
        with Session(engine) as session:
            decisions = session.scalar(select(func.count()).select_from(Decision))
            orders = session.scalar(select(func.count()).select_from(BrokerOrder))
        self.assertGreaterEqual(decisions or 0, 2, "need a qualified and a refused case")
        self.assertGreaterEqual(orders or 0, 2, "need the open and close lifecycle")

    def test_every_required_disclosure_is_present(self) -> None:
        text = APP.read_text(encoding="utf-8")
        for phrase in ("Paper", "indicative", "No alpha is claimed", "investment advice"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
