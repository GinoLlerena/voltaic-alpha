"""Phase 1 exit gate: both H0 fixtures replay into a durable, reconstructable trace.

These tests also hold the two properties the project's central claim rests on:
the fixture cannot leak its answer into the system, and no broker write path
exists at this commit.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from options_alpha_lab.architecture.contracts import DecisionAction, Direction
from options_alpha_lab.config import Settings, load_settings
from options_alpha_lab.hashing import payload_hash
from options_alpha_lab.persistence.models import (
    EXECUTION_TABLES,
    AuditEvent,
    Base,
    Decision,
    EvidencePack,
    MarketSnapshot,
    RiskDecisionRecord,
    SignalRecord,
    SpreadCandidateRecord,
    ThesisRecord,
)
from options_alpha_lab.replay import ReplayResult, replay_paths
from options_alpha_lab.snapshot_io import (
    SnapshotFormatError,
    load_oracle,
    load_snapshot,
    snapshot_from_dict,
    snapshot_to_dict,
)

FIXTURES = Path("fixtures/h0")
QUALIFIED = FIXTURES / "spy_qualified.snapshot.json"
REFUSAL = FIXTURES / "spy_refusal.snapshot.json"


def settings_for(db_path: Path) -> Settings:
    return load_settings(
        {
            "BOT_MODE": "observe",
            "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{db_path}",
        }
    )


class ReplayGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "replay.db"
        self.settings = settings_for(self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def replay(self) -> list[ReplayResult]:
        return replay_paths([QUALIFIED, REFUSAL], self.settings)

    def test_qualified_fixture_matches_its_oracle(self) -> None:
        result = self.replay()[0]
        oracle = load_oracle(FIXTURES / "spy_qualified.oracle.json")
        outcome = result.outcome

        self.assertEqual(outcome.action.value, oracle["expected_action"])
        self.assertEqual(outcome.direction.value, oracle["expected_direction"])
        self.assertEqual(list(outcome.reason_codes), oracle["expected_reason_codes"])
        self.assertIsNotNone(outcome.setup)
        assert outcome.setup is not None
        self.assertEqual(outcome.setup.family.value, oracle["expected_setup_family"])

        assert outcome.spread is not None
        self.assertEqual(outcome.spread.strategy.value, oracle["expected_strategy"])
        self.assertEqual(
            outcome.spread.long_contract_symbol, oracle["expected_long_contract_symbol"]
        )
        self.assertEqual(
            outcome.spread.short_contract_symbol, oracle["expected_short_contract_symbol"]
        )
        self.assertEqual(
            outcome.spread.estimated_debit, Decimal(oracle["expected_estimated_debit"])
        )

        assert outcome.risk is not None
        self.assertTrue(outcome.risk.approved)
        self.assertEqual(
            outcome.risk.calculated_max_loss, Decimal(oracle["expected_calculated_max_loss"])
        )
        self.assertEqual(outcome.risk.risk_budget, Decimal(oracle["expected_risk_budget"]))

    def test_refusal_fixture_matches_its_oracle(self) -> None:
        result = self.replay()[1]
        oracle = load_oracle(FIXTURES / "spy_refusal.oracle.json")

        self.assertEqual(result.outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(result.outcome.direction, Direction.NEUTRAL)
        self.assertEqual(list(result.outcome.reason_codes), oracle["expected_reason_codes"])
        self.assertIsNone(result.outcome.setup)
        self.assertIsNone(result.outcome.spread)

    def test_refusal_stops_before_the_thesis_is_ever_requested(self) -> None:
        # The model is never asked to adjudicate contradictory evidence, because
        # it has no authority to resolve it.
        result = self.replay()[1]
        self.assertIsNone(result.outcome.thesis)
        stages = [transition.stage.value for transition in result.outcome.transitions]
        self.assertNotIn("THESIS_READY", stages)

    def test_selector_excludes_out_of_band_and_untradeable_quotes(self) -> None:
        snapshot = load_snapshot(QUALIFIED)
        result = self.replay()[0]
        assert result.outcome.spread is not None
        chosen = {
            result.outcome.spread.long_contract_symbol,
            result.outcome.spread.short_contract_symbol,
        }
        by_symbol = {quote.contract_symbol: quote for quote in snapshot.option_chain}
        for symbol in chosen:
            self.assertTrue(14 <= by_symbol[symbol].dte <= 45)
        self.assertNotIn("SPY260904C00640000", chosen)  # 8 DTE
        self.assertNotIn("SPY261016C00640000", chosen)  # 50 DTE
        self.assertNotIn("SPY260918C00655000", chosen)  # quote too wide

    def test_trace_is_persisted_for_both_fixtures(self) -> None:
        results = self.replay()
        from sqlalchemy.orm import sessionmaker

        from options_alpha_lab.persistence.repository import build_engine

        engine = build_engine(self.settings)
        with sessionmaker(bind=engine, future=True)() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Decision)), 2)
            self.assertEqual(session.scalar(select(func.count()).select_from(MarketSnapshot)), 2)
            self.assertEqual(session.scalar(select(func.count()).select_from(SignalRecord)), 6)
            self.assertEqual(session.scalar(select(func.count()).select_from(EvidencePack)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(ThesisRecord)), 1)
            self.assertEqual(
                session.scalar(select(func.count()).select_from(SpreadCandidateRecord)), 1
            )
            self.assertEqual(
                session.scalar(select(func.count()).select_from(RiskDecisionRecord)), 1
            )

            stored = session.scalars(select(Decision)).all()
            self.assertEqual(
                {row.decision_hash for row in stored},
                {result.recorded.decision_hash for result in results},
            )

    def test_audit_events_preserve_transition_order(self) -> None:
        self.replay()
        from sqlalchemy.orm import sessionmaker

        from options_alpha_lab.persistence.repository import build_engine

        engine = build_engine(self.settings)
        with sessionmaker(bind=engine, future=True)() as session:
            rows = session.scalars(
                select(AuditEvent)
                .where(AuditEvent.correlation_id == "spy-qualified-2026-08-27")
                .order_by(AuditEvent.sequence)
            ).all()
        self.assertEqual([row.sequence for row in rows], list(range(len(rows))))
        self.assertEqual(
            [row.stage for row in rows],
            [
                "OBSERVED",
                "QUALIFIED",
                "THESIS_READY",
                "STRUCTURE_READY",
                "RISK_REVIEWED",
                "DECIDED",
            ],
        )

    def test_no_execution_table_receives_a_row(self) -> None:
        # Phase 1 exit gate: the shapes exist, nothing writes to them.
        self.replay()
        from sqlalchemy.orm import sessionmaker

        from options_alpha_lab.persistence.repository import build_engine

        engine = build_engine(self.settings)
        with sessionmaker(bind=engine, future=True)() as session:
            for table_name in sorted(EXECUTION_TABLES):
                table = Base.metadata.tables[table_name]
                count = session.scalar(select(func.count()).select_from(table))
                self.assertEqual(count, 0, f"{table_name} must be empty at Phase 1")

    def test_replay_is_deterministic(self) -> None:
        first = self.replay()
        with tempfile.TemporaryDirectory() as other:
            second = replay_paths(
                [QUALIFIED, REFUSAL], settings_for(Path(other) / "again.db")
            )
        self.assertEqual(
            [r.recorded.decision_hash for r in first],
            [r.recorded.decision_hash for r in second],
        )
        self.assertEqual(
            [r.recorded.input_hash for r in first],
            [r.recorded.input_hash for r in second],
        )

    def test_changing_one_input_changes_the_input_hash(self) -> None:
        payload = json.loads(QUALIFIED.read_text(encoding="utf-8"))
        original = payload_hash(snapshot_to_dict(snapshot_from_dict(payload)))
        payload["underlying_price"] = "641.26"
        mutated = payload_hash(snapshot_to_dict(snapshot_from_dict(payload)))
        self.assertNotEqual(original, mutated)


class OracleIsolationTests(unittest.TestCase):
    def test_snapshot_loader_rejects_a_leaked_expected_answer(self) -> None:
        payload = json.loads(QUALIFIED.read_text(encoding="utf-8"))
        payload["expected_action"] = "OPTIONS_POSITION"
        with self.assertRaises(SnapshotFormatError) as ctx:
            snapshot_from_dict(payload)
        self.assertIn("oracle", str(ctx.exception))

    def test_production_fixtures_carry_no_oracle_fields(self) -> None:
        for path in (QUALIFIED, REFUSAL):
            with self.subTest(path=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("expected_action", document)
                self.assertNotIn("expected", document)

    def test_floats_are_refused_so_hashes_stay_exact(self) -> None:
        payload = json.loads(QUALIFIED.read_text(encoding="utf-8"))
        payload["underlying_price"] = 641.25
        with self.assertRaises(SnapshotFormatError):
            snapshot_from_dict(payload)


def _load_guard():
    """Import the standalone guard script without making scripts/ a package."""
    spec = importlib.util.spec_from_file_location(
        "check_no_write_path", Path("scripts/check_no_write_path.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoBrokerWritePathTests(unittest.TestCase):
    """The strongest Phase 1 claim: order submission does not exist yet."""

    def test_source_tree_cannot_express_a_broker_write(self) -> None:
        # Parses Python rather than grepping it, so a docstring explaining why we
        # never call submit_order does not count as calling it.
        self.assertEqual(_load_guard().offenders(Path("src")), [])

    def test_the_guard_actually_catches_a_write(self) -> None:
        # A guard nobody has seen fail is not a guard.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sneaky.py").write_text(
                "def go(client):\n    return client.submit_order(qty=1)\n", encoding="utf-8"
            )
            found = _load_guard().offenders(Path(tmp))
        self.assertEqual(len(found), 1)
        self.assertIn("submit_order", found[0])

    def test_the_guard_ignores_prose_that_names_a_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "documented.py").write_text(
                '"""We never call submit_order or build a TradingClient."""\n'
                "# cancel_order is out of scope for this module.\n"
                "VALUE = 1\n",
                encoding="utf-8",
            )
            self.assertEqual(_load_guard().offenders(Path(tmp)), [])




class ForeignKeyIntegrityTests(unittest.TestCase):
    """SQLite must enforce what PostgreSQL enforces, or bugs hide until CI."""

    def test_sqlite_engine_enforces_foreign_keys(self) -> None:
        from sqlalchemy import text

        from options_alpha_lab.persistence.repository import build_engine

        with tempfile.TemporaryDirectory() as tmp:
            engine = build_engine(settings_for(Path(tmp) / "fk.db"))
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("PRAGMA foreign_keys")).scalar(), 1)

    def test_every_persisted_row_satisfies_its_foreign_keys(self) -> None:
        from sqlalchemy import text

        from options_alpha_lab.persistence.repository import build_engine

        with tempfile.TemporaryDirectory() as tmp:
            settings = settings_for(Path(tmp) / "fk.db")
            replay_paths([QUALIFIED, REFUSAL], settings)
            with build_engine(settings).connect() as connection:
                violations = connection.execute(text("PRAGMA foreign_key_check")).fetchall()
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
