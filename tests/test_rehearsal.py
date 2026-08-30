"""A demonstration recorded outside market hours, without a way to trade.

The point of these tests is not that the rehearsal produces output. It is that
the rehearsal cannot become a second, quieter trading path: no provider, no
gateway, and no route to the production database.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from options_alpha_lab.agent import Observation
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.providers.alpaca_readonly import ProviderError
from options_alpha_lab.rehearsal import (
    DEFAULT_SNAPSHOTS,
    RehearsalClient,
    SnapshotSource,
    main,
)

NOW = datetime(2026, 8, 29, 13, 30, tzinfo=UTC)
ENV = {
    "BOT_MODE": "recommend",
    "ALPACA_PAPER_TRADE": "true",
    "ALPACA_TRADING_ENABLED": "false",
}


def run(argv: list[str], env: dict[str, str] | None = None) -> tuple[int, list[dict]]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv, env=env or dict(ENV))
    events = [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]
    return code, events


class RehearsalCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "rehearsal.db"
        self.url = f"sqlite+pysqlite:///{self.db}"

    def tearDown(self) -> None:
        self._tmp.cleanup()


class DemonstrationTests(RehearsalCase):
    def test_the_market_being_closed_does_not_end_the_demonstration(self) -> None:
        # The whole reason this exists: the live worker would print
        # MARKET_CLOSED and stop, which shows a judge nothing at all.
        code, events = run(["--interval", "0", "--database-url", self.url])
        self.assertEqual(code, 0)
        actions = [e["action"] for e in events if e["event"] == "tick"]
        self.assertTrue(actions)
        self.assertNotIn("MARKET_CLOSED", actions)

    def test_every_committed_snapshot_reaches_its_own_decision(self) -> None:
        _, events = run(["--interval", "0", "--database-url", self.url])
        ticks = [e for e in events if e["event"] == "tick"]
        self.assertEqual(len(ticks), len(DEFAULT_SNAPSHOTS))
        # Both qualified directions and the refusal, each with a distinct hash.
        self.assertEqual(
            {t["action"] for t in ticks}, {"TRADE_CANDIDATE", "NO_TRADE"}
        )
        hashes = [t["decision_hash"] for t in ticks]
        self.assertEqual(len(set(hashes)), len(hashes))

    def test_a_qualified_setup_stops_at_the_candidate_with_no_write_authority(self) -> None:
        _, events = run(["--interval", "0", "--database-url", self.url])
        candidates = [e for e in events if e.get("action") == "TRADE_CANDIDATE"]
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertIn("no write authority", candidate["detail"])

    def test_the_refusal_carries_its_reason_codes(self) -> None:
        _, events = run(["--interval", "0", "--database-url", self.url])
        refusals = [e for e in events if e.get("action") == "NO_TRADE"]
        self.assertTrue(refusals)
        self.assertTrue(all(r["reason_codes"] for r in refusals))

    def test_ticks_cycle_the_snapshots_when_more_are_asked_for(self) -> None:
        _, events = run(
            ["--interval", "0", "--ticks", "5", "--database-url", self.url]
        )
        ticks = [e for e in events if e["event"] == "tick"]
        self.assertEqual(len(ticks), 5)
        self.assertEqual(ticks[0]["snapshot"], ticks[3]["snapshot"])


class NoTradingPathTests(RehearsalCase):
    def test_the_provider_client_refuses_every_read(self) -> None:
        client = RehearsalClient()
        for name in ("account", "clock", "daily_bars", "option_chain", "calendar"):
            with self.subTest(read=name), self.assertRaises(ProviderError):
                getattr(client, name)("SPY")

    def test_the_client_still_reports_the_feed_a_decision_must_record(self) -> None:
        self.assertEqual(RehearsalClient().option_feed, "indicative")

    def test_the_production_database_is_not_addressable(self) -> None:
        code, _ = run(
            ["--interval", "0", "--database-url", "postgresql+psycopg://host/options"]
        )
        self.assertEqual(code, 2)

    def test_an_ambient_production_database_url_is_ignored(self) -> None:
        env = dict(ENV, DATABASE_URL="postgresql+psycopg://host/options")
        code, events = run(["--interval", "0", "--database-url", self.url], env=env)
        self.assertEqual(code, 0)
        started = next(e for e in events if e["event"] == "rehearsal_started")
        self.assertEqual(started["database"], self.url)

    def test_a_write_capable_environment_is_downgraded_and_says_so(self) -> None:
        # Rehearsing on the worker host inherits its configuration. The
        # override is the safe outcome; announcing it is what stops someone
        # believing they watched the armed system run.
        env = dict(ENV, BOT_MODE="paper_execute", ALPACA_TRADING_ENABLED="true")
        code, events = run(["--interval", "0", "--database-url", self.url], env=env)
        self.assertEqual(code, 0)
        started = next(e for e in events if e["event"] == "rehearsal_started")
        self.assertEqual(started["mode"], "recommend")
        self.assertEqual(started["writes"], "disabled")
        self.assertEqual(started["inherited_config"], "overridden")

    def test_no_broker_order_can_be_reached_because_no_gateway_exists(self) -> None:
        env = dict(ENV, BOT_MODE="paper_execute", ALPACA_TRADING_ENABLED="true")
        _, events = run(["--interval", "0", "--database-url", self.url], env=env)
        actions = {e["action"] for e in events if e["event"] == "tick"}
        self.assertFalse(actions & {"ENTRY_SUBMITTED", "ENTRY_AMBIGUOUS", "ENTRY_REFUSED"})

    def test_the_run_reports_that_it_had_no_broker_and_no_provider(self) -> None:
        _, events = run(["--interval", "0", "--database-url", self.url])
        started = next(e for e in events if e["event"] == "rehearsal_started")
        self.assertEqual(started["broker"], "none")
        self.assertEqual(started["provider"], "none")
        self.assertEqual(started["writes"], "disabled")


class EvidenceProvenanceTests(RehearsalCase):
    def test_the_persisted_snapshots_are_committed_fixtures_not_minted_ids(self) -> None:
        # A rehearsal row must be recognisable as one. The live agent mints
        # `spy-agent-<stamp>`; these keep the committed fixture's own id, so a
        # rehearsal decision cannot be mistaken for an observed one.
        run(["--interval", "0", "--database-url", self.url])
        settings = _settings(self.url)
        engine = build_engine(settings)
        create_schema(engine)
        with engine.connect() as conn:
            ids = [row[0] for row in conn.execute(text("select snapshot_id from market_snapshots"))]
        self.assertTrue(ids)
        self.assertTrue(all(not i.startswith("spy-agent-") for i in ids))

    def test_the_run_is_closed_out_so_the_trace_is_not_left_open(self) -> None:
        run(["--interval", "0", "--database-url", self.url])
        engine = build_engine(_settings(self.url))
        with engine.connect() as conn:
            rows = list(conn.execute(text("select ended_at, health_result from runs")))
        self.assertTrue(rows)
        self.assertTrue(all(row[0] is not None for row in rows))
        self.assertEqual({row[1] for row in rows}, {"ok"})


class SnapshotSourceTests(unittest.TestCase):
    def test_it_reports_the_market_open_because_the_recording_was(self) -> None:
        source = SnapshotSource(list(DEFAULT_SNAPSHOTS))
        observation = source(NOW)
        self.assertIsInstance(observation, Observation)
        self.assertTrue(observation.market_open)

    def test_it_refuses_to_rehearse_nothing(self) -> None:
        with self.assertRaises(ValueError):
            SnapshotSource([])


def _settings(url: str):  # type: ignore[no-untyped-def]
    from options_alpha_lab.config import load_settings

    return load_settings(dict(ENV, DATABASE_URL=url))


if __name__ == "__main__":
    unittest.main()
