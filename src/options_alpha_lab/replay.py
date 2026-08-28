"""Replay frozen snapshots through the production workflow into a durable trace.

This is the Phase 1 exit gate made executable: a clean checkout runs this against
both H0 fixtures, persists their traces, and contains no broker write path. The
command never contacts a provider and never submits an order.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
from .config import ConfigurationError, Settings, load_env_file, load_settings
from .persistence.repository import DecisionRecorder, RecordedDecision, build_engine, create_schema
from .snapshot_io import load_snapshot

DEFAULT_FIXTURES = (
    "fixtures/h0/spy_qualified.snapshot.json",
    "fixtures/h0/spy_refusal.snapshot.json",
)


@dataclass(frozen=True)
class ReplayResult:
    path: str
    snapshot: DecisionSnapshot
    outcome: DecisionOutcome
    recorded: RecordedDecision


def build_workflow(
    governor: DeterministicRiskGovernor, synthesizer: Any = None
) -> DecisionWorkflow:
    return DecisionWorkflow(
        setup_classifier=DeterministicSetupClassifier(),
        thesis_synthesizer=synthesizer or DeterministicBaselineThesis(),
        options_selector=DeterministicSpreadSelector(),
        risk_governor=governor,
    )


def replay_paths(
    paths: Sequence[str | Path],
    settings: Settings,
    *,
    create: bool = True,
    synthesizer: Any = None,
) -> list[ReplayResult]:
    """Replay each snapshot and persist its trace. Returns one result per path."""
    engine = build_engine(settings)
    if create:
        create_schema(engine)
    recorder = DecisionRecorder(engine, settings)
    run_id = recorder.start_run()

    results: list[ReplayResult] = []
    try:
        for path in paths:
            snapshot = load_snapshot(path)
            # The allowlist is enforced before any work, not after a decision.
            settings.require_allowed_underlying(snapshot.symbol)

            governor = DeterministicRiskGovernor(settings.policy_version)
            if synthesizer is not None:
                synthesizer.last_call = None
            workflow = build_workflow(governor, synthesizer)
            outcome = workflow.evaluate(snapshot)

            if outcome.spread is not None:
                settings.require_allowed_strategy(outcome.spread.strategy)

            recorded = recorder.record_decision(
                run_id=run_id,
                snapshot=snapshot,
                outcome=outcome,
                risk_checks=[dict(check) for check in governor.last_checks],
                classifier_name=DeterministicSetupClassifier.name,
                synthesizer_name=(
                    getattr(synthesizer, "name", None) or DeterministicBaselineThesis.name
                ),
                model_call=getattr(synthesizer, "last_call", None),
            )
            results.append(ReplayResult(str(path), snapshot, outcome, recorded))
    except Exception:
        recorder.end_run(run_id, "failed")
        raise

    recorder.end_run(run_id, "ok")
    return results


def format_result(result: ReplayResult) -> str:
    outcome = result.outcome
    lines = [
        f"{result.snapshot.snapshot_id}  [{result.snapshot.symbol}]",
        f"  action        {outcome.action.value} ({outcome.direction.value})",
        f"  input hash    {result.recorded.input_hash}",
        f"  decision hash {result.recorded.decision_hash}",
    ]
    if outcome.reason_codes:
        lines.append(f"  reasons       {', '.join(outcome.reason_codes)}")
    if outcome.spread is not None:
        lines.append(
            f"  spread        {outcome.spread.strategy.value} "
            f"{outcome.spread.long_contract_symbol} / {outcome.spread.short_contract_symbol} "
            f"x{outcome.spread.quantity} debit {outcome.spread.estimated_debit}"
        )
    if outcome.risk is not None:
        lines.append(
            f"  risk          {'approved' if outcome.risk.approved else 'rejected'} "
            f"max loss {outcome.risk.calculated_max_loss} of budget {outcome.risk.risk_budget}"
        )
    lines.append("  trail         " + " -> ".join(t.stage.value for t in outcome.transitions))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.replay",
        description="Replay frozen H0 snapshots into a durable decision trace. Read-only.",
    )
    parser.add_argument(
        "snapshots",
        nargs="*",
        default=list(DEFAULT_FIXTURES),
        help="Snapshot JSON paths (default: both H0 fixtures)",
    )
    parser.add_argument(
        "--arm",
        choices=("baseline", "model"),
        default="baseline",
        help="baseline runs the deterministic no-LLM thesis; model runs the bounded memo",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL, for example sqlite+pysqlite:///replay.db",
    )
    args = parser.parse_args(argv)

    source: dict[str, str] = dict(os.environ if env is None else env)
    source.setdefault("BOT_MODE", "observe")
    if args.database_url:
        source["DATABASE_URL"] = args.database_url

    try:
        settings = load_settings(source)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if settings.may_write_orders:
        # Belt and braces: replay is read-only by definition, so a configuration
        # that would permit a write is a configuration mistake, not a mode.
        print(
            "refusing to replay with order-write authority enabled; "
            "use BOT_MODE=observe",
            file=sys.stderr,
        )
        return 2

    synthesizer = None
    if args.arm == "model":
        from .providers.openai_thesis import BoundedThesisSynthesizer, OpenAIResponsesTransport

        env = load_env_file(".env")
        api_key = env.get("OPENAI_API_KEY", "")
        if not api_key:
            print("OPENAI_API_KEY is not set; cannot run the model arm", file=sys.stderr)
            return 2
        synthesizer = BoundedThesisSynthesizer(
            OpenAIResponsesTransport(api_key),
            model=env.get("OPENAI_MODEL", "gpt-5.6-terra"),
        )

    results = replay_paths(args.snapshots, settings, synthesizer=synthesizer)
    for result in results:
        print(format_result(result))
        print()
    print(f"{len(results)} snapshot(s) replayed and persisted; no broker write path exists.")
    return 0


def _entrypoint() -> Any:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
