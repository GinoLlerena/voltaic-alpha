from __future__ import annotations

from dataclasses import asdict
from typing import Protocol

from .agents import DecisionArbiter, EventThesisAgent, OptionsStructureAgent
from .models import ExperimentCase, ExperimentResult, Thesis, TraceMessage, _jsonable
from .risk import DeterministicRiskGate


class ThesisAgent(Protocol):
    name: str

    def analyze(self, case: ExperimentCase) -> Thesis: ...


def run_experiment(
    case: ExperimentCase,
    *,
    thesis_agent: ThesisAgent | None = None,
) -> ExperimentResult:
    thesis_agent = thesis_agent or EventThesisAgent()
    options_agent = OptionsStructureAgent()
    risk_gate = DeterministicRiskGate()
    arbiter = DecisionArbiter()
    trace: list[TraceMessage] = []

    thesis = thesis_agent.analyze(case)
    trace.append(
        TraceMessage(
            sender=thesis_agent.name,
            recipient=options_agent.name,
            kind="thesis",
            payload=_jsonable(asdict(thesis)),
        )
    )

    proposal = options_agent.propose(case, thesis)
    trace.append(
        TraceMessage(
            sender=options_agent.name,
            recipient=risk_gate.name,
            kind="spread_proposal",
            payload=_jsonable(asdict(proposal)) if proposal else {"proposal": None},
        )
    )

    risk = risk_gate.evaluate(case, thesis, proposal)
    trace.append(
        TraceMessage(
            sender=risk_gate.name,
            recipient=options_agent.name if risk.suggested_quantity else arbiter.name,
            kind="risk_result",
            payload=_jsonable(asdict(risk)),
        )
    )

    # One bounded revision tests feedback without introducing an open-ended
    # agent loop. Only quantity is revisable; strategy and evidence are not.
    if not risk.approved and risk.suggested_quantity:
        proposal = options_agent.propose(case, thesis, risk.suggested_quantity)
        trace.append(
            TraceMessage(
                sender=options_agent.name,
                recipient=risk_gate.name,
                kind="revised_spread_proposal",
                payload=_jsonable(asdict(proposal)) if proposal else {"proposal": None},
            )
        )
        risk = risk_gate.evaluate(case, thesis, proposal)
        trace.append(
            TraceMessage(
                sender=risk_gate.name,
                recipient=arbiter.name,
                kind="final_risk_result",
                payload=_jsonable(asdict(risk)),
            )
        )

    decision = arbiter.decide(risk)
    trace.append(
        TraceMessage(
            sender=arbiter.name,
            recipient="experiment_output",
            kind="decision",
            payload={"decision": decision.value},
        )
    )

    return ExperimentResult(
        case_id=case.case_id,
        decision=decision,
        thesis=thesis,
        proposal=proposal,
        risk=risk,
        trace=trace,
    )
