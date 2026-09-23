"""The operator command closes one open incident, by id, with a reason."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.lifecycle import LifecycleStore
from options_alpha_lab.incidents import main
from options_alpha_lab.persistence.repository import build_engine, create_schema

NOW = datetime(2026, 9, 23, 7, 35, tzinfo=UTC)


class IncidentCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite+pysqlite:///{Path(self._tmp.name) / 'i.db'}"
        engine = build_engine(load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false", "DATABASE_URL": self.url,
        }))
        create_schema(engine)
        self.store = LifecycleStore(engine)
        self.incident = self.store.open_incident(
            kind="broker_unreachable", detail="request timed out", now=NOW)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": self.url}), \
                redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_list_shows_the_open_incident(self) -> None:
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn(self.incident, out)
        self.assertIn("1 open incident(s)", out)

    def test_resolve_closes_it_once(self) -> None:
        code, _, _ = self.run_cli("resolve", self.incident, "--reason", "Alpaca recovered")
        self.assertEqual(code, 0)
        self.assertEqual(self.store.open_incidents(), [])
        code, _, err = self.run_cli("resolve", self.incident, "--reason", "again")
        self.assertEqual(code, 1)
        self.assertIn("not an open incident", err)

    def test_a_blank_reason_is_refused(self) -> None:
        code, _, _ = self.run_cli("resolve", self.incident, "--reason", " ")
        self.assertEqual(code, 2)
        self.assertEqual(len(self.store.open_incidents()), 1)

    def test_no_database_url_is_an_error_not_a_guess(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["list"]), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
