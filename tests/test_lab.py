from __future__ import annotations

import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from options_alpha_lab.models import Decision, case_from_dict
from options_alpha_lab.orchestrator import run_experiment
from options_alpha_lab.secrets_setup import configuration_status, render_env, write_env


FIXTURE = Path(__file__).parents[1] / "fixtures" / "nvda_earnings_bearish.json"


def load_raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class AgentInteractionLabTests(unittest.TestCase):
    def test_risk_gate_requests_one_bounded_quantity_revision(self) -> None:
        result = run_experiment(case_from_dict(load_raw()))

        self.assertEqual(result.decision, Decision.TRADE_CANDIDATE)
        self.assertIsNotNone(result.proposal)
        self.assertEqual(result.proposal.quantity, 1)
        self.assertEqual(str(result.risk.calculated_max_loss), "360.0")
        self.assertEqual(len(result.trace), 6)
        self.assertEqual(result.trace[2].payload["suggested_quantity"], 1)
        self.assertEqual(result.trace[3].kind, "revised_spread_proposal")

    def test_weak_evidence_cannot_be_repaired_by_resizing(self) -> None:
        raw = deepcopy(load_raw())
        raw["evidence"] = ["Only one synthetic evidence item."]

        result = run_experiment(case_from_dict(raw))

        self.assertEqual(result.decision, Decision.NO_TRADE)
        self.assertIn("insufficient_evidence", result.risk.reasons)
        self.assertNotIn(
            "revised_spread_proposal", [message.kind for message in result.trace]
        )

    def test_wide_quote_is_rejected(self) -> None:
        raw = deepcopy(load_raw())
        raw["option_chain"][0]["bid"] = 4.0

        result = run_experiment(case_from_dict(raw))

        self.assertEqual(result.decision, Decision.NO_TRADE)
        self.assertIn("long_leg_spread_too_wide", result.risk.reasons)

    def test_secret_configuration_defaults_to_paper_and_disables_trading(self) -> None:
        content = render_env(
            {
                "OPENAI_API_KEY": "test-openai",
                "ALPACA_API_KEY": "test-alpaca",
                "ALPACA_SECRET_KEY": "test-secret",
            }
        )

        self.assertIn("ALPACA_PAPER_TRADE=true", content)
        self.assertIn("ALPACA_TRADING_ENABLED=false", content)

    def test_secret_file_is_owner_only_and_status_never_returns_values(self) -> None:
        content = render_env(
            {
                "OPENAI_API_KEY": "test-openai",
                "ALPACA_API_KEY": "test-alpaca",
                "ALPACA_SECRET_KEY": "test-secret",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            write_env(path, content, overwrite=False)

            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(
                configuration_status(path),
                {
                    "OPENAI_API_KEY": True,
                    "ALPACA_API_KEY": True,
                    "ALPACA_SECRET_KEY": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
