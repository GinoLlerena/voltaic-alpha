from __future__ import annotations

from .contracts import (
    DecisionAction,
    DecisionOutcome,
    DecisionSnapshot,
    Direction,
    RiskDecision,
    SetupCandidate,
    SpreadCandidate,
    SpreadStrategy,
    Thesis,
    WorkflowStage,
    WorkflowTransition,
)
from .ports import (
    AuditSink,
    OptionsSelector,
    RiskGovernor,
    SetupClassifier,
    ThesisSynthesizer,
)


class DecisionWorkflow:
    """Bounded decision workflow with deterministic gates around thesis synthesis."""

    def __init__(
        self,
        *,
        setup_classifier: SetupClassifier,
        thesis_synthesizer: ThesisSynthesizer,
        options_selector: OptionsSelector,
        risk_governor: RiskGovernor,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.setup_classifier = setup_classifier
        self.thesis_synthesizer = thesis_synthesizer
        self.options_selector = options_selector
        self.risk_governor = risk_governor
        self.audit_sink = audit_sink

    def evaluate(self, snapshot: DecisionSnapshot) -> DecisionOutcome:
        transitions: list[WorkflowTransition] = []
        self._record(
            snapshot,
            transitions,
            WorkflowTransition(WorkflowStage.OBSERVED, "decision_workflow", "accepted"),
        )

        if not snapshot.data_quality.is_usable:
            return self._no_trade(
                snapshot,
                transitions,
                snapshot.data_quality.reason_codes,
            )
        if not snapshot.account.is_paper:
            return self._no_trade(snapshot, transitions, ("non_paper_account",))

        setup = self.setup_classifier.classify(snapshot)
        if setup is None:
            return self._no_trade(snapshot, transitions, ("no_qualified_setup",))

        known_signal_ids = {signal.signal_id for signal in snapshot.signals}
        if not set(setup.evidence_ids) <= known_signal_ids:
            return self._no_trade(
                snapshot,
                transitions,
                ("setup_references_unknown_evidence",),
                setup=setup,
            )
        self._record(
            snapshot,
            transitions,
            WorkflowTransition(
                WorkflowStage.QUALIFIED,
                self.setup_classifier.name,
                "qualified",
            ),
        )

        thesis = self.thesis_synthesizer.synthesize(snapshot, setup)
        thesis_references = set(thesis.evidence_ids) | set(thesis.counter_evidence_ids)
        if not thesis_references <= known_signal_ids:
            return self._no_trade(
                snapshot,
                transitions,
                ("thesis_references_unknown_evidence",),
                setup=setup,
                thesis=thesis,
            )
        self._record(
            snapshot,
            transitions,
            WorkflowTransition(
                WorkflowStage.THESIS_READY,
                self.thesis_synthesizer.name,
                "synthesized",
            ),
        )

        if thesis.direction is Direction.NEUTRAL:
            return self._no_trade(
                snapshot,
                transitions,
                ("thesis_neutral",),
                setup=setup,
                thesis=thesis,
            )
        if thesis.direction is not setup.direction:
            return self._no_trade(
                snapshot,
                transitions,
                ("thesis_direction_outside_setup",),
                setup=setup,
                thesis=thesis,
            )
        if thesis.invalidation_conditions != setup.invalidation_conditions:
            return self._no_trade(
                snapshot,
                transitions,
                ("thesis_changed_deterministic_invalidation",),
                setup=setup,
                thesis=thesis,
            )

        spread = self.options_selector.select(snapshot, setup, thesis)
        if spread is None:
            return self._no_trade(
                snapshot,
                transitions,
                ("no_eligible_spread",),
                setup=setup,
                thesis=thesis,
            )
        expected_strategy = (
            SpreadStrategy.BULL_CALL_DEBIT_SPREAD
            if thesis.direction is Direction.BULLISH
            else SpreadStrategy.BEAR_PUT_DEBIT_SPREAD
        )
        if spread.strategy is not expected_strategy:
            return self._no_trade(
                snapshot,
                transitions,
                ("spread_direction_mismatch",),
                setup=setup,
                thesis=thesis,
                spread=spread,
            )
        self._record(
            snapshot,
            transitions,
            WorkflowTransition(
                WorkflowStage.STRUCTURE_READY,
                self.options_selector.name,
                "selected",
            ),
        )

        risk = self.risk_governor.evaluate(snapshot, setup, thesis, spread)
        self._record(
            snapshot,
            transitions,
            WorkflowTransition(
                WorkflowStage.RISK_REVIEWED,
                self.risk_governor.name,
                "approved" if risk.approved else "rejected",
                risk.reason_codes,
            ),
        )
        if not risk.approved:
            return self._no_trade(
                snapshot,
                transitions,
                risk.reason_codes or ("risk_rejected",),
                setup=setup,
                thesis=thesis,
                spread=spread,
                risk=risk,
            )

        self._record(
            snapshot,
            transitions,
            WorkflowTransition(
                WorkflowStage.DECIDED,
                "decision_workflow",
                DecisionAction.OPTIONS_POSITION.value,
            ),
        )
        return DecisionOutcome(
            snapshot_id=snapshot.snapshot_id,
            action=DecisionAction.OPTIONS_POSITION,
            direction=thesis.direction,
            reason_codes=(),
            transitions=tuple(transitions),
            setup=setup,
            thesis=thesis,
            spread=spread,
            risk=risk,
        )

    def _no_trade(
        self,
        snapshot: DecisionSnapshot,
        transitions: list[WorkflowTransition],
        reason_codes: tuple[str, ...],
        *,
        setup: SetupCandidate | None = None,
        thesis: Thesis | None = None,
        spread: SpreadCandidate | None = None,
        risk: RiskDecision | None = None,
    ) -> DecisionOutcome:
        self._record(
            snapshot,
            transitions,
            WorkflowTransition(
                WorkflowStage.DECIDED,
                "decision_workflow",
                DecisionAction.NO_TRADE.value,
                reason_codes,
            ),
        )
        return DecisionOutcome(
            snapshot_id=snapshot.snapshot_id,
            action=DecisionAction.NO_TRADE,
            direction=thesis.direction if thesis else Direction.NEUTRAL,
            reason_codes=reason_codes,
            transitions=tuple(transitions),
            setup=setup,
            thesis=thesis,
            spread=spread,
            risk=risk,
        )

    def _record(
        self,
        snapshot: DecisionSnapshot,
        transitions: list[WorkflowTransition],
        transition: WorkflowTransition,
    ) -> None:
        transitions.append(transition)
        if self.audit_sink is not None:
            self.audit_sink.record(snapshot.snapshot_id, transition)
