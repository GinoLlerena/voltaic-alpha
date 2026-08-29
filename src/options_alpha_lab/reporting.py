"""Operational report over the worker's durable records.

Answers the questions you actually ask after a session: what did it decide, what
did it refuse and why, what did the model contribute, and did anything need a
human. It reads only; nothing here can change a lifecycle.

Refusal reasons are reported as a distribution rather than a total, because
"twelve refusals" is not actionable and "twelve refusals, all
`no_qualified_setup`" is.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from .persistence.models import (
    AuditEvent,
    BrokerOrder,
    Decision,
    Fill,
    Incident,
    MarketSnapshot,
    ModelCall,
    Position,
    Run,
    ThesisRecord,
)


@dataclass
class AgentReport:
    generated_at: datetime
    window_hours: int
    runs: int = 0
    decisions: int = 0
    actions: dict[str, int] = field(default_factory=dict)
    refusal_reasons: dict[str, int] = field(default_factory=dict)
    directions: dict[str, int] = field(default_factory=dict)
    model_calls: int = 0
    model_status: dict[str, int] = field(default_factory=dict)
    model_latency_ms: dict[str, int | None] = field(default_factory=dict)
    model_tokens: dict[str, int] = field(default_factory=dict)
    model_agreements: int = 0
    model_abstentions: int = 0
    counter_evidence_rate: str = "0/0"
    orders: dict[str, int] = field(default_factory=dict)
    fills: int = 0
    positions: dict[str, int] = field(default_factory=dict)
    incidents: list[dict[str, str]] = field(default_factory=list)
    snapshots: int = 0
    unique_input_hashes: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }
        payload["generated_at"] = self.generated_at.isoformat()
        return payload


def _since(window_hours: int) -> datetime:
    return datetime.now(UTC) - timedelta(hours=window_hours)


def build_report(engine: Engine, *, window_hours: int = 24) -> AgentReport:
    cutoff = _since(window_hours)
    report = AgentReport(generated_at=datetime.now(UTC), window_hours=window_hours)

    with Session(engine) as session:
        report.runs = int(
            session.scalar(
                select(func.count()).select_from(Run).where(Run.started_at >= cutoff)
            )
            or 0
        )

        decisions = list(
            session.scalars(select(Decision).where(Decision.decided_at >= cutoff)).all()
        )
        report.decisions = len(decisions)
        report.actions = dict(Counter(d.action for d in decisions))
        report.directions = dict(Counter(d.direction for d in decisions))

        reasons: Counter[str] = Counter()
        for decision in decisions:
            for reason in decision.reason_codes or []:
                reasons[str(reason)] += 1
        report.refusal_reasons = dict(reasons.most_common())

        snapshots = list(
            session.scalars(
                select(MarketSnapshot).where(MarketSnapshot.received_time >= cutoff)
            ).all()
        )
        report.snapshots = len(snapshots)
        report.unique_input_hashes = len({s.payload_hash for s in snapshots})
        if report.snapshots and report.unique_input_hashes < report.snapshots:
            # Identical inputs across ticks are expected outside market hours and
            # suspicious during them: it usually means a feed has gone stale.
            report.notes.append(
                f"{report.snapshots - report.unique_input_hashes} snapshot(s) repeated an "
                "earlier input hash; expected outside market hours, worth checking during"
            )

        calls = list(
            session.scalars(select(ModelCall).where(ModelCall.recorded_at >= cutoff)).all()
        )
        report.model_calls = len(calls)
        report.model_status = dict(Counter(c.status for c in calls))
        latencies = [c.latency_ms for c in calls if c.latency_ms is not None]
        report.model_latency_ms = {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "mean": int(sum(latencies) / len(latencies)) if latencies else None,
        }
        report.model_tokens = {
            "input": sum(c.input_tokens or 0 for c in calls),
            "output": sum(c.output_tokens or 0 for c in calls),
        }

        theses = list(
            session.scalars(select(ThesisRecord).where(ThesisRecord.recorded_at >= cutoff)).all()
        )
        report.model_abstentions = sum(1 for t in theses if t.direction == "neutral")
        report.model_agreements = sum(1 for t in theses if t.direction != "neutral")
        with_counter = sum(1 for t in theses if t.counter_evidence_ids)
        report.counter_evidence_rate = f"{with_counter}/{len(theses)}" if theses else "0/0"

        orders = list(
            session.scalars(select(BrokerOrder).where(BrokerOrder.prepared_at >= cutoff)).all()
        )
        report.orders = dict(Counter(o.local_state for o in orders))
        report.fills = int(
            session.scalar(
                select(func.count()).select_from(Fill).where(Fill.recorded_at >= cutoff)
            )
            or 0
        )

        positions = list(session.scalars(select(Position)).all())
        report.positions = dict(Counter(p.lifecycle_status for p in positions))

        report.incidents = [
            {
                "kind": i.kind,
                "severity": i.severity,
                "opened_at": i.opened_at.isoformat(),
                "detail": i.detail[:160],
            }
            for i in session.scalars(
                select(Incident).where(Incident.resolved_at.is_(None))
            ).all()
        ]

        stages = Counter(
            e.stage
            for e in session.scalars(
                select(AuditEvent).where(AuditEvent.occurred_at >= cutoff)
            ).all()
        )
        if stages:
            reached = stages.get("DECIDED", 0)
            qualified = stages.get("QUALIFIED", 0)
            if reached and not qualified:
                report.notes.append(
                    "every decision terminated before qualification; the setup "
                    "classifier is rejecting everything, which is worth inspecting"
                )

    if report.decisions and not report.actions.get("OPTIONS_POSITION"):
        report.notes.append(
            "no decision reached a position in this window; a refusal-only session is "
            "a valid result, not necessarily a fault"
        )
    return report


def format_report(report: AgentReport) -> str:
    lines = [
        f"Agent report - last {report.window_hours}h "
        f"(generated {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')})",
        "",
        f"  runs                {report.runs}",
        f"  observations        {report.snapshots} "
        f"({report.unique_input_hashes} unique input hashes)",
        f"  decisions           {report.decisions}",
    ]
    for action, count in sorted(report.actions.items()):
        lines.append(f"    {action:<18}{count}")
    if report.refusal_reasons:
        lines.append("  refusal reasons")
        for reason, count in report.refusal_reasons.items():
            lines.append(f"    {reason:<24} {count}")
    lines += [
        "",
        f"  model calls         {report.model_calls}  status={report.model_status or '-'}",
        f"    latency ms        {report.model_latency_ms}",
        f"    tokens            {report.model_tokens}",
        f"    agreed/abstained  {report.model_agreements}/{report.model_abstentions}",
        f"    counter-evidence  {report.counter_evidence_rate}",
        "",
        f"  orders              {report.orders or '-'}",
        f"  fills               {report.fills}",
        f"  positions           {report.positions or '-'}",
    ]
    if report.incidents:
        lines.append(f"  OPEN INCIDENTS      {len(report.incidents)}")
        for incident in report.incidents:
            lines.append(f"    [{incident['severity']}] {incident['kind']}: {incident['detail']}")
    else:
        lines.append("  open incidents      none")
    if report.notes:
        lines.append("")
        lines.append("  notes")
        for note in report.notes:
            lines.append(f"    - {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .config import ConfigurationError, load_settings, resolved_env
    from .persistence.repository import build_engine

    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.reporting",
        description="Summarize what the agent did. Read-only.",
    )
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    env = dict(resolved_env())
    if args.database_url:
        env["DATABASE_URL"] = args.database_url
    env.setdefault("BOT_MODE", "observe")
    env["ALPACA_TRADING_ENABLED"] = "false"
    try:
        settings = load_settings(env)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}")
        return 2

    report = build_report(build_engine(settings), window_hours=args.hours)
    print(json.dumps(report.as_dict(), indent=2) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
