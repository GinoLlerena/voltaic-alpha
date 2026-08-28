from __future__ import annotations

import json
import unittest
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from options_alpha_lab.agents import (
    DecisionArbiter,
    EventThesisAgent,
    OptionsStructureAgent,
)
from options_alpha_lab.models import Decision, case_from_dict
from options_alpha_lab.orchestrator import run_experiment
from options_alpha_lab.risk import DeterministicRiskGate


FIXTURE = Path(__file__).parents[1] / "fixtures" / "nvda_earnings_bearish.json"


def load_raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def build_components(raw: dict | None = None):
    case = case_from_dict(raw or load_raw())
    thesis = EventThesisAgent().analyze(case)
    proposal = OptionsStructureAgent().propose(case, thesis, quantity=1)
    if proposal is None:
        raise AssertionError("The test fixture did not produce a spread proposal.")
    return case, thesis, proposal


class OptionsStructureContractTests(unittest.TestCase):
    def test_builds_bull_call_spread_in_correct_strike_order(self) -> None:
        raw = load_raw()
        raw["expected_direction"] = "bullish"
        raw["option_chain"] = [
            {
                "symbol": "NVDA260925C00180000",
                "option_type": "call",
                "expiration": "2026-09-25",
                "dte": 26,
                "strike": 180,
                "bid": 7.1,
                "ask": 7.5,
                "delta": 0.55,
                "implied_volatility": 0.62,
            },
            {
                "symbol": "NVDA260925C00190000",
                "option_type": "call",
                "expiration": "2026-09-25",
                "dte": 26,
                "strike": 190,
                "bid": 3.9,
                "ask": 4.2,
                "delta": 0.32,
                "implied_volatility": 0.6,
            },
        ]

        case = case_from_dict(raw)
        thesis = EventThesisAgent().analyze(case)
        proposal = OptionsStructureAgent().propose(case, thesis, quantity=1)

        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.strategy, "call_debit_spread")
        self.assertEqual(proposal.long_leg.strike, Decimal("180"))
        self.assertEqual(proposal.short_leg.strike, Decimal("190"))
        self.assertEqual(proposal.estimated_debit, Decimal("3.6"))

    def test_ignores_unpaired_quote_from_another_expiration(self) -> None:
        raw = load_raw()
        extra_quote = deepcopy(raw["option_chain"][0])
        extra_quote.update(
            symbol="NVDA261002P00190000",
            expiration="2026-10-02",
            dte=33,
            strike=190,
        )
        raw["option_chain"].append(extra_quote)

        case = case_from_dict(raw)
        thesis = EventThesisAgent().analyze(case)
        proposal = OptionsStructureAgent().propose(case, thesis, quantity=1)

        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.long_leg.strike, Decimal("180.0"))
        self.assertEqual(proposal.short_leg.strike, Decimal("170.0"))
        self.assertEqual(proposal.long_leg.expiration, proposal.short_leg.expiration)

    def test_returns_none_without_a_same_expiration_pair(self) -> None:
        raw = load_raw()
        raw["option_chain"][1]["expiration"] = "2026-10-02"
        raw["option_chain"][1]["dte"] = 33

        case = case_from_dict(raw)
        thesis = EventThesisAgent().analyze(case)

        self.assertIsNone(OptionsStructureAgent().propose(case, thesis))


class RiskGateContractTests(unittest.TestCase):
    def test_rejects_crossed_quote_without_requesting_revision(self) -> None:
        raw = load_raw()
        raw["option_chain"][0]["bid"] = 8.0

        result = run_experiment(case_from_dict(raw))

        self.assertEqual(result.decision, Decision.NO_TRADE)
        self.assertIn("long_leg_quote_crossed", result.risk.reasons)
        self.assertIsNone(result.risk.suggested_quantity)
        self.assertNotIn(
            "revised_spread_proposal", [message.kind for message in result.trace]
        )

    def test_rejects_zero_and_negative_quantities(self) -> None:
        case, thesis, proposal = build_components()
        gate = DeterministicRiskGate()

        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                result = gate.evaluate(
                    case,
                    thesis,
                    replace(proposal, quantity=quantity),
                )
                self.assertFalse(result.approved)
                self.assertIn("quantity_below_policy", result.reasons)

    def test_rejects_duplicate_or_blank_evidence(self) -> None:
        for evidence in (["duplicate", "duplicate"], ["", "  "]):
            with self.subTest(evidence=evidence):
                raw = load_raw()
                raw["evidence"] = evidence

                result = run_experiment(case_from_dict(raw))

                self.assertEqual(result.decision, Decision.NO_TRADE)
                self.assertIn("insufficient_evidence", result.risk.reasons)
                self.assertEqual(len(result.trace), 4)

    def test_rejects_blank_invalidation_conditions(self) -> None:
        raw = load_raw()
        raw["invalidation_conditions"] = ["", "  "]

        result = run_experiment(case_from_dict(raw))

        self.assertEqual(result.decision, Decision.NO_TRADE)
        self.assertIn("missing_invalidation_conditions", result.risk.reasons)

    def test_rejects_agent_supplied_debit_that_does_not_match_quotes(self) -> None:
        case, thesis, proposal = build_components()

        risk = DeterministicRiskGate().evaluate(
            case,
            thesis,
            replace(proposal, estimated_debit=Decimal("0.01")),
        )

        self.assertFalse(risk.approved)
        self.assertIn("estimated_debit_mismatch", risk.reasons)

    def test_rejects_contract_not_present_in_observed_chain(self) -> None:
        case, thesis, proposal = build_components()
        fabricated_long_leg = replace(
            proposal.long_leg,
            symbol="NVDA260925P00185000",
            strike=Decimal("185"),
        )

        risk = DeterministicRiskGate().evaluate(
            case,
            thesis,
            replace(proposal, long_leg=fabricated_long_leg),
        )

        self.assertFalse(risk.approved)
        self.assertIn("long_leg_not_in_option_chain", risk.reasons)

    def test_rejects_debit_without_positive_payoff_geometry(self) -> None:
        raw = load_raw()
        raw["option_chain"][0]["ask"] = 14.0
        case = case_from_dict(raw)
        thesis = EventThesisAgent().analyze(case)
        proposal = OptionsStructureAgent().propose(case, thesis, quantity=1)
        self.assertIsNotNone(proposal)

        risk = DeterministicRiskGate().evaluate(case, thesis, proposal)

        self.assertFalse(risk.approved)
        self.assertIn("debit_not_below_spread_width", risk.reasons)

    def test_rejects_legs_with_different_expirations(self) -> None:
        case, thesis, proposal = build_components()
        short_leg = replace(
            proposal.short_leg,
            expiration="2026-10-02",
            dte=33,
        )

        risk = DeterministicRiskGate().evaluate(
            case,
            thesis,
            replace(proposal, short_leg=short_leg),
        )

        self.assertFalse(risk.approved)
        self.assertIn("legs_expiration_mismatch", risk.reasons)
        self.assertIn("legs_dte_mismatch", risk.reasons)

    def test_only_size_rejection_can_request_a_revision(self) -> None:
        approved_after_resize = run_experiment(case_from_dict(load_raw()))
        self.assertEqual(approved_after_resize.decision, Decision.TRADE_CANDIDATE)
        self.assertEqual(approved_after_resize.proposal.quantity, 1)

        weak_raw = load_raw()
        weak_raw["confidence"] = 0.2
        rejected = run_experiment(case_from_dict(weak_raw))

        self.assertEqual(rejected.decision, Decision.NO_TRADE)
        self.assertIsNone(rejected.risk.suggested_quantity)
        self.assertEqual(
            [message.kind for message in rejected.trace],
            ["thesis", "spread_proposal", "risk_result", "decision"],
        )
        self.assertEqual(rejected.trace[2].recipient, "decision_arbiter")

    def test_unaffordable_single_contract_is_no_trade(self) -> None:
        raw = load_raw()
        raw["account_equity"] = 1000

        result = run_experiment(case_from_dict(raw))

        self.assertEqual(result.decision, Decision.NO_TRADE)
        self.assertIn("max_loss_above_risk_budget", result.risk.reasons)
        self.assertIsNone(result.risk.suggested_quantity)
        self.assertEqual(len(result.trace), 4)


class OrchestrationContractTests(unittest.TestCase):
    def test_happy_path_trace_records_one_bounded_revision(self) -> None:
        result = run_experiment(case_from_dict(load_raw()))

        self.assertEqual(
            [message.kind for message in result.trace],
            [
                "thesis",
                "spread_proposal",
                "risk_result",
                "revised_spread_proposal",
                "final_risk_result",
                "decision",
            ],
        )
        self.assertEqual(result.trace[-1].sender, "decision_arbiter")
        self.assertEqual(
            result.trace[-1].payload,
            {"decision": Decision.TRADE_CANDIDATE.value},
        )

    def test_arbiter_maps_risk_result_to_decision(self) -> None:
        case, thesis, proposal = build_components()
        risk = DeterministicRiskGate().evaluate(case, thesis, proposal)
        arbiter = DecisionArbiter()

        self.assertEqual(arbiter.decide(risk), Decision.TRADE_CANDIDATE)
        self.assertEqual(
            arbiter.decide(replace(risk, approved=False)),
            Decision.NO_TRADE,
        )

    def test_result_serializes_decimal_and_enum_values_to_json(self) -> None:
        result = run_experiment(case_from_dict(load_raw()))

        serialized = json.dumps(result.to_dict())

        self.assertIn('"decision": "TRADE_CANDIDATE"', serialized)
        self.assertIn('"calculated_max_loss": "360.0"', serialized)


if __name__ == "__main__":
    unittest.main()
