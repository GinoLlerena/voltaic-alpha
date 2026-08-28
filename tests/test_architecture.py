from __future__ import annotations

import unittest
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from options_alpha_lab.architecture import (
    AccountSnapshot,
    DataQuality,
    DecisionAction,
    DecisionSnapshot,
    DecisionWorkflow,
    Direction,
    RiskDecision,
    SetupCandidate,
    SetupFamily,
    Signal,
    SignalFamily,
    SpreadCandidate,
    SpreadStrategy,
    Thesis,
    WorkflowStage,
)


NOW = datetime(2026, 8, 20, 15, 45, tzinfo=timezone.utc)


def build_snapshot(
    *,
    data_quality: DataQuality | None = None,
    is_paper: bool = True,
) -> DecisionSnapshot:
    return DecisionSnapshot(
        snapshot_id="snapshot-001",
        as_of=NOW,
        symbol="spy",
        underlying_price=Decimal("650.00"),
        account=AccountSnapshot(
            account_id="paper-account",
            as_of=NOW - timedelta(seconds=5),
            equity=Decimal("100000"),
            options_buying_power=Decimal("50000"),
            is_paper=is_paper,
        ),
        signals=(
            Signal(
                signal_id="structure-1",
                family=SignalFamily.STRUCTURE,
                direction=Direction.BULLISH,
                strength=Decimal("0.80"),
                as_of=NOW - timedelta(minutes=1),
                source="fixture",
                summary="Completed breakout and successful retest.",
            ),
            Signal(
                signal_id="breadth-1",
                family=SignalFamily.PARTICIPATION,
                direction=Direction.BULLISH,
                strength=Decimal("0.70"),
                as_of=NOW - timedelta(minutes=1),
                source="fixture",
                summary="Participation confirms the move.",
            ),
        ),
        data_quality=data_quality or DataQuality(),
    )


def bullish_setup(*, evidence_ids: tuple[str, ...] = ("structure-1",)) -> SetupCandidate:
    return SetupCandidate(
        setup_id="setup-001",
        family=SetupFamily.BREAKOUT_BREAKDOWN,
        direction=Direction.BULLISH,
        evidence_ids=evidence_ids,
        invalidation_conditions=("Close below the retest level.",),
    )


def bullish_thesis(
    *,
    direction: Direction = Direction.BULLISH,
    evidence_ids: tuple[str, ...] = ("structure-1", "breadth-1"),
) -> Thesis:
    return Thesis(
        direction=direction,
        confidence=Decimal("0.78"),
        evidence_ids=evidence_ids,
        counter_evidence_ids=(),
        invalidation_conditions=("Close below the retest level.",),
        reasoning_summary="Structure and participation align.",
    )


def neutral_thesis() -> Thesis:
    return Thesis(
        direction=Direction.NEUTRAL,
        confidence=Decimal("0.40"),
        evidence_ids=("structure-1",),
        counter_evidence_ids=("breadth-1",),
        invalidation_conditions=(),
        reasoning_summary="The supplied evidence is not directionally coherent.",
    )


def bull_spread() -> SpreadCandidate:
    return SpreadCandidate(
        candidate_id="spread-001",
        strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        long_contract_symbol="SPY260918C00640000",
        short_contract_symbol="SPY260918C00650000",
        quantity=1,
        estimated_debit=Decimal("4.00"),
        calculated_max_loss=Decimal("400.00"),
    )


def approved_risk() -> RiskDecision:
    return RiskDecision(
        approved=True,
        reason_codes=(),
        risk_budget=Decimal("750.00"),
        calculated_max_loss=Decimal("400.00"),
        policy_version="risk.v1",
    )


class StubSetupClassifier:
    name = "setup_classifier"

    def __init__(self, result: SetupCandidate | None) -> None:
        self.result = result
        self.calls = 0

    def classify(self, snapshot: DecisionSnapshot) -> SetupCandidate | None:
        self.calls += 1
        return self.result


class StubThesisSynthesizer:
    name = "thesis_synthesizer"

    def __init__(self, result: Thesis) -> None:
        self.result = result
        self.calls = 0

    def synthesize(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
    ) -> Thesis:
        self.calls += 1
        return self.result


class StubOptionsSelector:
    name = "options_selector"

    def __init__(self, result: SpreadCandidate | None) -> None:
        self.result = result
        self.calls = 0

    def select(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
        thesis: Thesis,
    ) -> SpreadCandidate | None:
        self.calls += 1
        return self.result


class StubRiskGovernor:
    name = "risk_governor"

    def __init__(self, result: RiskDecision) -> None:
        self.result = result
        self.calls = 0

    def evaluate(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
        thesis: Thesis,
        spread: SpreadCandidate,
    ) -> RiskDecision:
        self.calls += 1
        return self.result


class RecordingAuditSink:
    def __init__(self) -> None:
        self.records: list[tuple[str, WorkflowStage]] = []

    def record(self, snapshot_id, transition) -> None:
        self.records.append((snapshot_id, transition.stage))


def build_workflow(
    *,
    setup: SetupCandidate | None = None,
    thesis: Thesis | None = None,
    spread: SpreadCandidate | None = None,
    risk: RiskDecision | None = None,
    audit_sink: RecordingAuditSink | None = None,
):
    classifier = StubSetupClassifier(setup if setup is not None else bullish_setup())
    synthesizer = StubThesisSynthesizer(thesis if thesis is not None else bullish_thesis())
    selector = StubOptionsSelector(spread if spread is not None else bull_spread())
    governor = StubRiskGovernor(risk if risk is not None else approved_risk())
    workflow = DecisionWorkflow(
        setup_classifier=classifier,
        thesis_synthesizer=synthesizer,
        options_selector=selector,
        risk_governor=governor,
        audit_sink=audit_sink,
    )
    return workflow, classifier, synthesizer, selector, governor


class ArchitectureContractTests(unittest.TestCase):
    def test_snapshot_contract_has_no_expected_answer_fields(self) -> None:
        field_names = {item.name for item in fields(DecisionSnapshot)}

        self.assertNotIn("expected_direction", field_names)
        self.assertNotIn("expected_decision", field_names)
        self.assertNotIn("confidence", field_names)

    def test_snapshot_rejects_look_ahead_signal(self) -> None:
        snapshot = build_snapshot()
        future_signal = replace(
            snapshot.signals[0],
            as_of=snapshot.as_of + timedelta(seconds=1),
        )

        with self.assertRaisesRegex(ValueError, "signals cannot be newer"):
            replace(snapshot, signals=(future_signal,))

    def test_happy_path_has_bounded_ordered_transitions(self) -> None:
        audit = RecordingAuditSink()
        workflow, classifier, synthesizer, selector, governor = build_workflow(
            audit_sink=audit
        )

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.OPTIONS_POSITION)
        self.assertEqual(outcome.direction, Direction.BULLISH)
        self.assertTrue(outcome.risk.approved)
        self.assertEqual(classifier.calls, 1)
        self.assertEqual(synthesizer.calls, 1)
        self.assertEqual(selector.calls, 1)
        self.assertEqual(governor.calls, 1)
        expected_stages = [
            WorkflowStage.OBSERVED,
            WorkflowStage.QUALIFIED,
            WorkflowStage.THESIS_READY,
            WorkflowStage.STRUCTURE_READY,
            WorkflowStage.RISK_REVIEWED,
            WorkflowStage.DECIDED,
        ]
        self.assertEqual(
            [transition.stage for transition in outcome.transitions],
            expected_stages,
        )
        self.assertEqual(
            [stage for _, stage in audit.records],
            expected_stages,
        )

    def test_unusable_data_stops_before_setup_classification(self) -> None:
        workflow, classifier, synthesizer, selector, governor = build_workflow()
        snapshot = build_snapshot(
            data_quality=DataQuality(stale_fields=("underlying.quote",))
        )

        outcome = workflow.evaluate(snapshot)

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.reason_codes, ("stale:underlying.quote",))
        self.assertEqual(classifier.calls, 0)
        self.assertEqual(synthesizer.calls, 0)
        self.assertEqual(selector.calls, 0)
        self.assertEqual(governor.calls, 0)

    def test_non_paper_account_stops_before_setup_classification(self) -> None:
        workflow, classifier, _, _, _ = build_workflow()

        outcome = workflow.evaluate(build_snapshot(is_paper=False))

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.reason_codes, ("non_paper_account",))
        self.assertEqual(classifier.calls, 0)

    def test_missing_setup_stops_before_thesis_synthesis(self) -> None:
        classifier = StubSetupClassifier(None)
        synthesizer = StubThesisSynthesizer(bullish_thesis())
        selector = StubOptionsSelector(bull_spread())
        governor = StubRiskGovernor(approved_risk())
        workflow = DecisionWorkflow(
            setup_classifier=classifier,
            thesis_synthesizer=synthesizer,
            options_selector=selector,
            risk_governor=governor,
        )

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.reason_codes, ("no_qualified_setup",))
        self.assertEqual(classifier.calls, 1)
        self.assertEqual(synthesizer.calls, 0)
        self.assertEqual(selector.calls, 0)
        self.assertEqual(governor.calls, 0)

    def test_setup_cannot_reference_unknown_evidence(self) -> None:
        workflow, _, synthesizer, selector, governor = build_workflow(
            setup=bullish_setup(evidence_ids=("fabricated-signal",))
        )

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(
            outcome.reason_codes,
            ("setup_references_unknown_evidence",),
        )
        self.assertEqual(synthesizer.calls, 0)
        self.assertEqual(selector.calls, 0)
        self.assertEqual(governor.calls, 0)

    def test_neutral_thesis_stops_before_options_selection(self) -> None:
        workflow, _, synthesizer, selector, governor = build_workflow(
            thesis=neutral_thesis()
        )

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.direction, Direction.NEUTRAL)
        self.assertEqual(outcome.reason_codes, ("thesis_neutral",))
        self.assertEqual(synthesizer.calls, 1)
        self.assertEqual(selector.calls, 0)
        self.assertEqual(governor.calls, 0)

    def test_thesis_cannot_reverse_deterministic_setup(self) -> None:
        workflow, _, _, selector, governor = build_workflow(
            thesis=bullish_thesis(direction=Direction.BEARISH)
        )

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.reason_codes, ("thesis_direction_outside_setup",))
        self.assertEqual(selector.calls, 0)
        self.assertEqual(governor.calls, 0)

    def test_thesis_cannot_reference_unknown_evidence(self) -> None:
        workflow, _, _, selector, governor = build_workflow(
            thesis=bullish_thesis(evidence_ids=("fabricated-signal",))
        )

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(
            outcome.reason_codes,
            ("thesis_references_unknown_evidence",),
        )
        self.assertEqual(selector.calls, 0)
        self.assertEqual(governor.calls, 0)

    def test_thesis_cannot_change_deterministic_invalidation(self) -> None:
        thesis = replace(
            bullish_thesis(),
            invalidation_conditions=("A model-selected invalidation.",),
        )
        workflow, _, _, selector, governor = build_workflow(thesis=thesis)

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(
            outcome.reason_codes,
            ("thesis_changed_deterministic_invalidation",),
        )
        self.assertEqual(selector.calls, 0)
        self.assertEqual(governor.calls, 0)

    def test_missing_eligible_spread_stops_before_risk_review(self) -> None:
        classifier = StubSetupClassifier(bullish_setup())
        synthesizer = StubThesisSynthesizer(bullish_thesis())
        selector = StubOptionsSelector(None)
        governor = StubRiskGovernor(approved_risk())
        workflow = DecisionWorkflow(
            setup_classifier=classifier,
            thesis_synthesizer=synthesizer,
            options_selector=selector,
            risk_governor=governor,
        )

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.reason_codes, ("no_eligible_spread",))
        self.assertEqual(selector.calls, 1)
        self.assertEqual(governor.calls, 0)

    def test_spread_cannot_conflict_with_thesis_direction(self) -> None:
        bearish_spread = replace(
            bull_spread(),
            strategy=SpreadStrategy.BEAR_PUT_DEBIT_SPREAD,
        )
        workflow, _, _, selector, governor = build_workflow(spread=bearish_spread)

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.reason_codes, ("spread_direction_mismatch",))
        self.assertEqual(selector.calls, 1)
        self.assertEqual(governor.calls, 0)

    def test_risk_contract_cannot_approve_loss_above_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            RiskDecision(
                approved=True,
                reason_codes=(),
                risk_budget=Decimal("300.00"),
                calculated_max_loss=Decimal("400.00"),
                policy_version="risk.v1",
            )

    def test_risk_veto_is_terminal(self) -> None:
        rejected_risk = RiskDecision(
            approved=False,
            reason_codes=("max_loss_above_budget",),
            risk_budget=Decimal("300.00"),
            calculated_max_loss=Decimal("400.00"),
            policy_version="risk.v1",
        )
        workflow, _, _, selector, governor = build_workflow(risk=rejected_risk)

        outcome = workflow.evaluate(build_snapshot())

        self.assertEqual(outcome.action, DecisionAction.NO_TRADE)
        self.assertEqual(outcome.reason_codes, ("max_loss_above_budget",))
        self.assertEqual(selector.calls, 1)
        self.assertEqual(governor.calls, 1)
        self.assertFalse(outcome.risk.approved)


if __name__ == "__main__":
    unittest.main()
