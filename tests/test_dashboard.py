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
TABS = 5


def decisions_in_evidence() -> int:
    """Read the count from the evidence database rather than hard-coding it.

    A magic number here fails every time a fixture is added, which trains people
    to edit the test instead of reading it.
    """
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from options_alpha_lab.persistence.models import Decision

    db = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"
    engine = create_engine(f"sqlite+pysqlite:///{db}", future=True)
    with Session(engine) as session:
        return int(session.scalar(select(func.count()).select_from(Decision)) or 0)


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
        # radio[0] is the view filter; radio[1] is the decision list.
        options = app.radio[1].options
        self.assertGreaterEqual(len(options), 3, "need bullish, bearish, and refused cases")
        self.assertLessEqual(len(options), decisions_in_evidence())
        for option in options:
            with self.subTest(decision=option):
                run = AppTest.from_file(str(APP), default_timeout=90)
                run.run()
                run.radio[1].set_value(option).run()
                self.assertEqual(list(run.exception), [], f"raised on {option}")

    def test_all_five_views_are_present(self) -> None:
        self.assertEqual(len(run_app().tabs), TABS)

    def test_render_produces_substantive_content(self) -> None:
        # Asserts on what the page says rather than on which Streamlit widget
        # says it: the annunciator panel and the authority rail are custom
        # markup, so counting st.metric measured an implementation detail.
        app = run_app()
        self.assertGreater(len(app.markdown), 10)
        rendered = " ".join(m.value for m in app.markdown)
        for expected in ("Options Alpha", "Environment", "Order writes", "Memo"):
            self.assertIn(expected, rendered)

    def test_the_authority_rail_marks_the_model_stage(self) -> None:
        # The central claim is spatial: the model occupies one fenced stage of
        # seven. If that markup disappears, the page stops making the argument.
        rendered = " ".join(m.value for m in run_app().markdown)
        self.assertIn("node model", rendered)
        self.assertIn("model advises only", rendered)
        self.assertIn("deterministic code decides", rendered)

    def test_the_colour_rule_is_stated_not_assumed(self) -> None:
        # Semantic colour only works if the reader is told the rule once.
        source = APP.read_text(encoding="utf-8")
        self.assertIn("model advises only", source)
        self.assertIn("--warm", source)
        self.assertIn("--cool", source)

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

    def test_evidence_covers_both_directions_and_a_refusal(self) -> None:
        # A demo that only ever shows one direction hides half the mirrored path.
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from options_alpha_lab.persistence.models import SpreadCandidateRecord

        db = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"
        engine = create_engine(f"sqlite+pysqlite:///{db}", future=True)
        with Session(engine) as session:
            strategies = set(session.scalars(select(SpreadCandidateRecord.strategy)).all())
        self.assertIn("bull_call_debit_spread", strategies)
        self.assertIn("bear_put_debit_spread", strategies)

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




class LiveSourceFallbackTests(unittest.TestCase):
    """A judge must never see an empty page because the worker is between sessions."""

    def test_an_unreachable_live_source_falls_back_to_committed_evidence(self) -> None:
        import os

        # Port 1 refuses instantly. Deliberately no user:password in the URL:
        # a credential-shaped string here trips the secret scanner for no reason.
        os.environ["DASHBOARD_DATABASE_URL"] = "postgresql+psycopg://localhost:1/nothing"
        try:
            app = AppTest.from_file(str(APP), default_timeout=90).run()
            self.assertEqual(list(app.exception), [])
            self.assertGreaterEqual(len(app.radio[1].options), 1)
        finally:
            del os.environ["DASHBOARD_DATABASE_URL"]

    def test_the_source_is_always_labelled(self) -> None:
        # "live" must never be implied when it is not true.
        app = run_app()
        labels = [m.value for m in app.caption] if hasattr(app, "caption") else []
        text = " ".join(labels) or APP.read_text(encoding="utf-8")
        self.assertIn("Source:", text)




class SelectorScaleTests(unittest.TestCase):
    """A polling agent produces ~66 decisions a session; the list must survive that."""

    def build_busy_database(self, tmp: str, refusals: int = 282) -> str:
        import uuid
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import select as sa_select
        from sqlalchemy.orm import Session

        from options_alpha_lab.config import load_settings
        from options_alpha_lab.persistence.models import Decision, MarketSnapshot, Run
        from options_alpha_lab.persistence.repository import build_engine, create_schema
        from options_alpha_lab.replay import replay_paths

        db = Path(tmp) / "busy.db"
        settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{db}",
        })
        engine = build_engine(settings)
        create_schema(engine)
        replay_paths(
            [Path("fixtures/h0/spy_qualified.snapshot.json"),
             Path("fixtures/h0/spy_refusal.snapshot.json")],
            settings, create=False,
        )
        with Session(engine) as session:
            run = session.scalars(sa_select(Run)).first()
            snap = session.scalars(sa_select(MarketSnapshot)).first()
            base = datetime.now(UTC) - timedelta(hours=30)
            for i in range(refusals):
                session.add(Decision(
                    id=uuid.uuid4().hex, run_id=run.id, market_snapshot_id=snap.id,
                    snapshot_id=f"spy-agent-{i:04d}", action="NO_TRADE",
                    direction="neutral", reason_codes=["no_qualified_setup"],
                    transitions=[], input_hash=f"sha256:{i:064d}",
                    decision_hash=f"sha256:d{i:063d}",
                    policy_version="h0-provisional-0",
                    decided_at=base + timedelta(minutes=5 * i),
                    recorded_at=base + timedelta(minutes=5 * i),
                ))
            session.commit()
        return f"sqlite+pysqlite:///{db}"

    def test_hundreds_of_decisions_collapse_to_a_readable_list(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DASHBOARD_DATABASE_URL"] = self.build_busy_database(tmp)
            try:
                app = AppTest.from_file(str(APP), default_timeout=120).run()
                self.assertEqual(list(app.exception), [])
                options = app.radio[1].options
                # 282 identical consecutive refusals are one fact, not 282 rows.
                self.assertLessEqual(
                    len(options), 12,
                    f"selector offered {len(options)} options; it must collapse runs",
                )
                self.assertGreaterEqual(len(options), 2, "the distinct cases survive")
            finally:
                del os.environ["DASHBOARD_DATABASE_URL"]

    def test_the_query_is_bounded(self) -> None:
        # Without a limit the page loads the whole decisions table on every
        # interaction, which is a different failure from the list being long.
        source = APP.read_text(encoding="utf-8")
        self.assertIn("DECISION_LIMIT", source)
        self.assertIn(".limit(", source)

    def test_every_filter_renders(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DASHBOARD_DATABASE_URL"] = self.build_busy_database(tmp, refusals=40)
            try:
                for choice in ("Notable", "Positions", "Refusals", "Everything"):
                    with self.subTest(view=choice):
                        run = AppTest.from_file(str(APP), default_timeout=120)
                        run.run()
                        run.radio[0].set_value(choice).run()
                        self.assertEqual(list(run.exception), [], f"{choice} raised")
            finally:
                del os.environ["DASHBOARD_DATABASE_URL"]


if __name__ == "__main__":
    unittest.main()
