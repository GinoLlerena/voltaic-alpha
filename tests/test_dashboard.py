"""The judge dashboard must actually render, for every decision, without error.

An AST check proves the file parses. It does not prove a judge can open tab 4 on
the refusal case, which takes a different path through the same code. These tests
run the real Streamlit script.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

# AppTest resolves a relative path against the *calling* file, which would
# look for tests/app.py. Resolve from the repository root instead.
APP = (Path(__file__).resolve().parents[1] / "app.py").resolve()
DECISIONS = 4
TABS = 5


def run_app() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=90).run()


class DashboardRenderTests(unittest.TestCase):
    def test_app_renders_without_exception(self) -> None:
        app = run_app()
        self.assertEqual(list(app.exception), [], "dashboard raised on first render")

    def test_every_decision_renders_without_exception(self) -> None:
        # The refusal case has no thesis, no spread, and no evidence pack, so it
        # exercises a different path through every view.
        app = run_app()
        options = app.radio[0].options
        self.assertEqual(len(options), DECISIONS)
        for option in options:
            with self.subTest(decision=option):
                run = AppTest.from_file(str(APP), default_timeout=90)
                run.run()
                run.radio[0].set_value(option).run()
                self.assertEqual(list(run.exception), [], f"raised on {option}")

    def test_all_five_views_are_present(self) -> None:
        self.assertEqual(len(run_app().tabs), TABS)

    def test_render_produces_substantive_content(self) -> None:
        app = run_app()
        self.assertGreater(len(app.markdown), 10)
        self.assertGreater(len(app.metric), 3)

    def test_no_deprecated_streamlit_arguments(self) -> None:
        # use_container_width was removed after 2025-12-31; leaving it in would
        # break a fresh deploy on a current Streamlit rather than warn.
        self.assertNotIn("use_container_width", APP.read_text(encoding="utf-8"))


class DashboardBoundaryTests(unittest.TestCase):
    def test_dashboard_exposes_no_control_actions(self) -> None:
        # The surface a judge browses must not be a surface that can trade.
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
        }
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
