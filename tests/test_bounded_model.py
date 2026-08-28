"""Phase 3: the model may inform a memo and may not influence a decision."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from options_alpha_lab.architecture.contracts import (
    AccountSnapshot,
    DecisionAction,
    DecisionSnapshot,
    Direction,
    OptionQuoteSnapshot,
    OptionType,
    SetupCandidate,
    Signal,
    SignalFamily,
)
from options_alpha_lab.architecture.workflow import DecisionWorkflow
from options_alpha_lab.components import (
    DeterministicRiskGovernor,
    DeterministicSetupClassifier,
    DeterministicSpreadSelector,
)
from options_alpha_lab.providers.openai_thesis import (
    BoundedThesisSynthesizer,
    ModelTransport,
)

AS_OF = datetime(2026, 8, 27, 19, 45, tzinfo=UTC)


class ScriptedTransport(ModelTransport):
    """Returns a canned response, or raises, so every branch is reachable."""

    def __init__(self, payload: Any = None, *, raises: Exception | None = None,
                 raw_text: str | None = None, refusal: bool = False) -> None:
        self.payload = payload
        self.raises = raises
        self.raw_text = raw_text
        self.refusal = refusal
        self.seen: dict[str, Any] | None = None

    def create(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.seen = payload
        if self.raises is not None:
            raise self.raises
        if self.refusal:
            return {"output": [{"type": "message", "content": [{"type": "refusal"}]}]}
        text = self.raw_text if self.raw_text is not None else json.dumps(self.payload)
        return {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 400, "output_tokens": 120},
        }


def snapshot() -> DecisionSnapshot:
    return DecisionSnapshot(
        snapshot_id="case-1",
        as_of=AS_OF,
        symbol="SPY",
        underlying_price=Decimal("641.25"),
        account=AccountSnapshot(
            account_id="PA",
            as_of=AS_OF,
            equity=Decimal("100000"),
            options_buying_power=Decimal("50000"),
            is_paper=True,
        ),
        signals=(
            Signal(
                signal_id="sig-structure",
                family=SignalFamily.STRUCTURE,
                direction=Direction.BULLISH,
                strength=Decimal("0.72"),
                as_of=AS_OF,
                source="test",
                summary="structure",
            ),
            Signal(
                signal_id="sig-vol",
                family=SignalFamily.VOLATILITY_OPTIONS,
                direction=Direction.BULLISH,
                strength=Decimal("0.61"),
                as_of=AS_OF,
                source="test",
                summary="confirmation",
            ),
        ),
        option_chain=(
            OptionQuoteSnapshot(
                contract_symbol="SPY260918C00640000",
                option_type=OptionType.CALL,
                expiration=date(2026, 9, 18),
                dte=22,
                strike=Decimal("640"),
                bid=Decimal("12.40"),
                ask=Decimal("12.60"),
                quote_as_of=AS_OF,
                feed="indicative",
                delta=Decimal("0.56"),
            ),
            OptionQuoteSnapshot(
                contract_symbol="SPY260918C00645000",
                option_type=OptionType.CALL,
                expiration=date(2026, 9, 18),
                dte=22,
                strike=Decimal("645"),
                bid=Decimal("9.60"),
                ask=Decimal("9.80"),
                quote_as_of=AS_OF,
                feed="indicative",
                delta=Decimal("0.38"),
            ),
        ),
    )


def setup_for(snap: DecisionSnapshot) -> SetupCandidate:
    found = DeterministicSetupClassifier().classify(snap)
    assert found is not None
    return found


def good_memo(**overrides: Any) -> dict[str, Any]:
    memo = {
        "direction": "bullish",
        "confidence": 0.64,
        "evidence_ids": ["sig-structure", "sig-vol"],
        "counter_evidence_ids": [],
        "reasoning_summary": "Structure and volatility agree.",
    }
    memo.update(overrides)
    return memo


class PromptBoundaryTests(unittest.TestCase):
    def test_the_model_never_sees_invalidation_conditions(self) -> None:
        snap = snapshot()
        setup = setup_for(snap)
        synth = BoundedThesisSynthesizer(ScriptedTransport(good_memo()))
        model_input = synth.build_input(snap, setup)
        serialized = json.dumps(model_input)
        self.assertNotIn("invalidation", serialized)
        for condition in setup.invalidation_conditions:
            self.assertNotIn(condition, serialized)

    def test_the_model_never_sees_an_expected_answer_or_account_state(self) -> None:
        snap = snapshot()
        model_input = BoundedThesisSynthesizer(ScriptedTransport(good_memo())).build_input(
            snap, setup_for(snap)
        )
        serialized = json.dumps(model_input).lower()
        for leak in ("expected", "equity", "buying_power", "budget", "quantity", "max_loss"):
            self.assertNotIn(leak, serialized)

    def test_provider_retention_is_disabled(self) -> None:
        snap = snapshot()
        transport = ScriptedTransport(good_memo())
        BoundedThesisSynthesizer(transport).synthesize(snap, setup_for(snap))
        assert transport.seen is not None
        self.assertIs(transport.seen["store"], False)
        self.assertEqual(transport.seen["text"]["format"]["type"], "json_schema")
        self.assertTrue(transport.seen["text"]["format"]["strict"])


class BoundedOutputTests(unittest.TestCase):
    def synth(self, transport: ScriptedTransport) -> BoundedThesisSynthesizer:
        return BoundedThesisSynthesizer(transport)

    def test_agreement_is_accepted(self) -> None:
        snap = snapshot()
        thesis = self.synth(ScriptedTransport(good_memo())).synthesize(snap, setup_for(snap))
        self.assertIs(thesis.direction, Direction.BULLISH)
        self.assertEqual(thesis.confidence, Decimal("0.64"))

    def test_reversal_is_coerced_to_abstention_and_recorded(self) -> None:
        snap = snapshot()
        synth = self.synth(ScriptedTransport(good_memo(direction="bearish")))
        thesis = synth.synthesize(snap, setup_for(snap))
        self.assertIs(thesis.direction, Direction.NEUTRAL)
        assert synth.last_call is not None
        self.assertIn("model_attempted_direction_reversal", synth.last_call.reason_codes)

    def test_abstention_is_a_valid_answer(self) -> None:
        snap = snapshot()
        synth = self.synth(ScriptedTransport(good_memo(direction="neutral")))
        thesis = synth.synthesize(snap, setup_for(snap))
        self.assertIs(thesis.direction, Direction.NEUTRAL)
        assert synth.last_call is not None
        self.assertNotIn("model_attempted_direction_reversal", synth.last_call.reason_codes)

    def test_hallucinated_evidence_forces_abstention(self) -> None:
        snap = snapshot()
        synth = self.synth(
            ScriptedTransport(good_memo(evidence_ids=["sig-structure", "sig-invented"]))
        )
        thesis = synth.synthesize(snap, setup_for(snap))
        self.assertIs(thesis.direction, Direction.NEUTRAL)
        assert synth.last_call is not None
        self.assertIn("hallucinated_evidence", synth.last_call.reason_codes)

    def test_invalidation_is_always_the_deterministic_one(self) -> None:
        snap = snapshot()
        setup = setup_for(snap)
        for memo in (good_memo(), good_memo(direction="bearish"), good_memo(confidence=5)):
            with self.subTest(memo=memo["direction"]):
                thesis = self.synth(ScriptedTransport(memo)).synthesize(snap, setup)
                self.assertEqual(thesis.invalidation_conditions, setup.invalidation_conditions)

    def test_out_of_range_confidence_is_zeroed(self) -> None:
        snap = snapshot()
        synth = self.synth(ScriptedTransport(good_memo(confidence=4.2)))
        thesis = synth.synthesize(snap, setup_for(snap))
        self.assertEqual(thesis.confidence, Decimal("0"))
        assert synth.last_call is not None
        self.assertIn("confidence_out_of_range", synth.last_call.reason_codes)

    def test_empty_summary_forces_abstention(self) -> None:
        snap = snapshot()
        thesis = self.synth(ScriptedTransport(good_memo(reasoning_summary="  "))).synthesize(
            snap, setup_for(snap)
        )
        self.assertIs(thesis.direction, Direction.NEUTRAL)

    def test_a_signal_cannot_be_both_evidence_and_counter_evidence(self) -> None:
        # Observed live: the model cited the structure signal as support and as a
        # contradiction in the same memo.
        snap = snapshot()
        synth = self.synth(
            ScriptedTransport(
                good_memo(
                    evidence_ids=["sig-structure", "sig-vol"],
                    counter_evidence_ids=["sig-structure"],
                )
            )
        )
        thesis = synth.synthesize(snap, setup_for(snap))
        self.assertEqual(thesis.counter_evidence_ids, ())
        self.assertEqual(thesis.evidence_ids, ("sig-structure", "sig-vol"))
        assert synth.last_call is not None
        self.assertIn("evidence_and_counter_evidence_overlap", synth.last_call.reason_codes)

    def test_genuine_counter_evidence_survives_the_overlap_check(self) -> None:
        snap = snapshot()
        thesis = self.synth(
            ScriptedTransport(
                good_memo(evidence_ids=["sig-structure"], counter_evidence_ids=["sig-vol"])
            )
        ).synthesize(snap, setup_for(snap))
        self.assertEqual(thesis.counter_evidence_ids, ("sig-vol",))

    def test_counter_evidence_is_preserved(self) -> None:
        # Non-overlapping ids: this fixture previously listed sig-vol as both
        # evidence and counter-evidence, which the coherence rule now rejects.
        snap = snapshot()
        thesis = self.synth(
            ScriptedTransport(
                good_memo(evidence_ids=["sig-structure"], counter_evidence_ids=["sig-vol"])
            )
        ).synthesize(snap, setup_for(snap))
        self.assertEqual(thesis.counter_evidence_ids, ("sig-vol",))


class FailClosedTests(unittest.TestCase):
    def assert_fails_closed(self, transport: ScriptedTransport) -> None:
        snap = snapshot()
        setup = setup_for(snap)
        synth = BoundedThesisSynthesizer(transport)
        thesis = synth.synthesize(snap, setup)
        self.assertIs(thesis.direction, Direction.NEUTRAL)
        self.assertEqual(thesis.evidence_ids, ())
        self.assertEqual(thesis.invalidation_conditions, setup.invalidation_conditions)
        assert synth.last_call is not None
        self.assertEqual(synth.last_call.status, "failed")

    def test_transport_error_fails_closed(self) -> None:
        self.assert_fails_closed(ScriptedTransport(raises=TimeoutError("timed out")))

    def test_http_error_fails_closed(self) -> None:
        self.assert_fails_closed(ScriptedTransport(raises=RuntimeError("model returned 500")))

    def test_malformed_json_fails_closed(self) -> None:
        self.assert_fails_closed(ScriptedTransport(raw_text="{not json"))

    def test_refusal_fails_closed(self) -> None:
        self.assert_fails_closed(ScriptedTransport(refusal=True))

    def test_empty_output_fails_closed(self) -> None:
        transport = ScriptedTransport()
        transport.create = lambda payload, timeout: {"output": []}  # type: ignore[method-assign]
        self.assert_fails_closed(transport)


class WorkflowAuthorityTests(unittest.TestCase):
    """The exit gate: the model cannot change what the system does."""

    def workflow(self, transport: ScriptedTransport) -> DecisionWorkflow:
        return DecisionWorkflow(
            setup_classifier=DeterministicSetupClassifier(),
            thesis_synthesizer=BoundedThesisSynthesizer(transport),
            options_selector=DeterministicSpreadSelector(),
            risk_governor=DeterministicRiskGovernor(),
        )

    def test_model_agreement_reaches_a_position(self) -> None:
        outcome = self.workflow(ScriptedTransport(good_memo())).evaluate(snapshot())
        self.assertIs(outcome.action, DecisionAction.OPTIONS_POSITION)

    def test_model_reversal_terminates_as_no_trade(self) -> None:
        outcome = self.workflow(ScriptedTransport(good_memo(direction="bearish"))).evaluate(
            snapshot()
        )
        self.assertIs(outcome.action, DecisionAction.NO_TRADE)
        self.assertIn("thesis_neutral", outcome.reason_codes)

    def test_model_failure_terminates_as_no_trade(self) -> None:
        outcome = self.workflow(ScriptedTransport(raises=TimeoutError())).evaluate(snapshot())
        self.assertIs(outcome.action, DecisionAction.NO_TRADE)

    def test_model_confidence_cannot_change_position_size(self) -> None:
        low = self.workflow(ScriptedTransport(good_memo(confidence=0.01))).evaluate(snapshot())
        high = self.workflow(ScriptedTransport(good_memo(confidence=0.99))).evaluate(snapshot())
        assert low.spread is not None and high.spread is not None
        self.assertEqual(low.spread.quantity, high.spread.quantity)
        assert low.risk is not None and high.risk is not None
        self.assertEqual(low.risk.calculated_max_loss, high.risk.calculated_max_loss)

    def test_model_cannot_change_which_contracts_are_eligible(self) -> None:
        a = self.workflow(ScriptedTransport(good_memo())).evaluate(snapshot())
        b = self.workflow(ScriptedTransport(good_memo(confidence=0.2))).evaluate(snapshot())
        assert a.spread is not None and b.spread is not None
        self.assertEqual(a.spread.long_contract_symbol, b.spread.long_contract_symbol)
        self.assertEqual(a.spread.short_contract_symbol, b.spread.short_contract_symbol)


if __name__ == "__main__":
    unittest.main()
