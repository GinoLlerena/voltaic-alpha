from __future__ import annotations

from typing import Protocol

from .contracts import (
    DecisionSnapshot,
    RiskDecision,
    SetupCandidate,
    SpreadCandidate,
    Thesis,
    WorkflowTransition,
)


class SetupClassifier(Protocol):
    name: str

    def classify(self, snapshot: DecisionSnapshot) -> SetupCandidate | None: ...


class ThesisSynthesizer(Protocol):
    name: str

    def synthesize(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
    ) -> Thesis: ...


class OptionsSelector(Protocol):
    name: str

    def select(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
        thesis: Thesis,
    ) -> SpreadCandidate | None: ...


class RiskGovernor(Protocol):
    name: str

    def evaluate(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
        thesis: Thesis,
        spread: SpreadCandidate,
    ) -> RiskDecision: ...


class AuditSink(Protocol):
    def record(self, snapshot_id: str, transition: WorkflowTransition) -> None: ...
