"""Run the same frozen cases through the deterministic baseline and the model path.

The point is not to show that the model helps. The point is to make the question
answerable. `AI-010` and the null hypothesis in the signal specification both
start from the assumption that it does not, and this report is what would have to
change that assumption.

Cost is reported in tokens rather than currency: token counts are observed, and
a dollar figure would be an unverified constant presented as a measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .architecture.contracts import DecisionOutcome, DecisionSnapshot
from .architecture.workflow import DecisionWorkflow
from .components import (
    DeterministicBaselineThesis,
    DeterministicRiskGovernor,
    DeterministicSetupClassifier,
    DeterministicSpreadSelector,
)
from .config import resolved_env
from .providers.openai_thesis import (
    BoundedThesisSynthesizer,
    ModelCall,
    OpenAIResponsesTransport,
)
from .snapshot_io import load_snapshot


@dataclass
class ArmResult:
    arm: str
    snapshot_id: str
    action: str
    direction: str
    reason_codes: list[str]
    thesis_direction: str | None
    confidence: str | None
    evidence_ids: list[str]
    counter_evidence_ids: list[str]
    spread: str | None
    max_loss: str | None
    model_call: dict[str, Any] | None = None


@dataclass
class AblationReport:
    generated_at: str
    cases: int
    results: list[ArmResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def _workflow(synthesizer: Any, governor: DeterministicRiskGovernor) -> DecisionWorkflow:
    # Only the thesis component differs between arms. Everything that carries
    # authority is identical, which is what makes the comparison meaningful.
    return DecisionWorkflow(
        setup_classifier=DeterministicSetupClassifier(),
        thesis_synthesizer=synthesizer,
        options_selector=DeterministicSpreadSelector(),
        risk_governor=governor,
    )


def _to_result(
    arm: str,
    snapshot: DecisionSnapshot,
    outcome: DecisionOutcome,
    call: ModelCall | None,
) -> ArmResult:
    return ArmResult(
        arm=arm,
        snapshot_id=snapshot.snapshot_id,
        action=outcome.action.value,
        direction=outcome.direction.value,
        reason_codes=list(outcome.reason_codes),
        thesis_direction=outcome.thesis.direction.value if outcome.thesis else None,
        confidence=str(outcome.thesis.confidence) if outcome.thesis else None,
        evidence_ids=list(outcome.thesis.evidence_ids) if outcome.thesis else [],
        counter_evidence_ids=(
            list(outcome.thesis.counter_evidence_ids) if outcome.thesis else []
        ),
        spread=(
            f"{outcome.spread.long_contract_symbol}/{outcome.spread.short_contract_symbol}"
            if outcome.spread
            else None
        ),
        max_loss=str(outcome.risk.calculated_max_loss) if outcome.risk else None,
        model_call=asdict(call) if call else None,
    )


def run_ablation(
    snapshots: Sequence[DecisionSnapshot],
    synthesizer: BoundedThesisSynthesizer,
    *,
    policy_version: str = "h0-provisional-0",
) -> AblationReport:
    report = AblationReport(generated_at=datetime.now(UTC).isoformat(), cases=len(snapshots))

    for snapshot in snapshots:
        baseline_outcome = _workflow(
            DeterministicBaselineThesis(), DeterministicRiskGovernor(policy_version)
        ).evaluate(snapshot)
        report.results.append(_to_result("baseline", snapshot, baseline_outcome, None))

        # Cleared per case: a refusal that never reaches thesis synthesis must not
        # inherit the previous case's model call and appear to have made one.
        synthesizer.last_call = None
        model_outcome = _workflow(
            synthesizer, DeterministicRiskGovernor(policy_version)
        ).evaluate(snapshot)
        report.results.append(
            _to_result("model", snapshot, model_outcome, synthesizer.last_call)
        )

    report.metrics = compute_metrics(report.results)
    return report


def compute_metrics(results: Sequence[ArmResult]) -> dict[str, Any]:
    baseline = {r.snapshot_id: r for r in results if r.arm == "baseline"}
    model = {r.snapshot_id: r for r in results if r.arm == "model"}
    shared = sorted(set(baseline) & set(model))

    agreements = sum(1 for sid in shared if baseline[sid].action == model[sid].action)
    model_abstentions = sum(1 for sid in shared if model[sid].thesis_direction == "neutral")
    with_counter = sum(1 for sid in shared if model[sid].counter_evidence_ids)
    calls = [model[sid].model_call for sid in shared if model[sid].model_call]
    constrained = [c for c in calls if c and c.get("reason_codes")]
    reversal_attempts = sum(
        1
        for c in calls
        if c and "model_attempted_direction_reversal" in (c.get("reason_codes") or [])
    )
    hallucinations = sum(
        1 for c in calls if c and "hallucinated_evidence" in (c.get("reason_codes") or [])
    )
    failures = [c for c in calls if c and c.get("status") == "failed"]
    latencies = [c["latency_ms"] for c in calls if c and c.get("latency_ms") is not None]
    input_tokens = sum(c.get("input_tokens") or 0 for c in calls if c)
    output_tokens = sum(c.get("output_tokens") or 0 for c in calls if c)

    return {
        "cases_compared": len(shared),
        "action_agreement": f"{agreements}/{len(shared)}" if shared else "0/0",
        "decisions_changed_by_model": len(shared) - agreements,
        "model_abstentions": model_abstentions,
        "counter_evidence_detected": f"{with_counter}/{len(shared)}" if shared else "0/0",
        "evidence_fidelity": (
            "all cited ids resolve to supplied signals"
            if hallucinations == 0
            else f"{hallucinations} case(s) cited unknown ids and were coerced to abstain"
        ),
        "direction_reversal_attempts": reversal_attempts,
        "malformed_or_failed_calls": len(failures),
        "constrained_calls": len(constrained),
        "latency_ms": {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "tokens": {"input": input_tokens, "output": output_tokens},
        "interpretation": (
            "This is a mechanism check on a tiny sample, not evidence about returns. "
            "The null hypothesis that the model does not improve decisions is not "
            "rejected by this report and is not testable at this sample size."
        ),
    }


def format_report(report: AblationReport) -> str:
    lines = [f"Ablation over {report.cases} frozen case(s)", ""]
    by_case: dict[str, list[ArmResult]] = {}
    for result in report.results:
        by_case.setdefault(result.snapshot_id, []).append(result)
    for snapshot_id, arms in by_case.items():
        lines.append(snapshot_id)
        for arm in arms:
            detail = f"  {arm.arm:9} {arm.action:17} {arm.direction:8}"
            if arm.thesis_direction:
                detail += f" thesis={arm.thesis_direction}"
            if arm.confidence:
                detail += f" conf={arm.confidence}"
            if arm.spread:
                detail += f" {arm.spread}"
            if arm.reason_codes:
                detail += f" [{', '.join(arm.reason_codes)}]"
            lines.append(detail)
            if arm.model_call:
                call = arm.model_call
                reasons = call["reason_codes"]
                suffix = f" reasons={','.join(reasons)}" if reasons else ""
                lines.append(
                    f"            call status={call['status']} "
                    f"latency={call['latency_ms']}ms "
                    f"tokens={call['input_tokens']}/{call['output_tokens']}{suffix}"
                )
        lines.append("")
    lines.append("Metrics")
    for key, value in report.metrics.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.ablation",
        description="Compare the deterministic baseline against the bounded model path.",
    )
    parser.add_argument("snapshots", nargs="+", help="Frozen snapshot JSON paths")
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=None, type=Path, help="Write the JSON report here")
    args = parser.parse_args(argv)

    env = resolved_env()
    api_key = env.get("OPENAI_API_KEY", "")
    if not api_key:
        print("OPENAI_API_KEY is not set; cannot run the model arm", file=sys.stderr)
        return 2

    synthesizer = BoundedThesisSynthesizer(
        OpenAIResponsesTransport(api_key),
        model=args.model or env.get("OPENAI_MODEL", "gpt-5.6-terra"),
    )
    snapshots = [load_snapshot(path) for path in args.snapshots]
    report = run_ablation(snapshots, synthesizer)

    print(format_report(report))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "generated_at": report.generated_at,
                    "cases": report.cases,
                    "results": [asdict(r) for r in report.results],
                    "metrics": report.metrics,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nreport written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
