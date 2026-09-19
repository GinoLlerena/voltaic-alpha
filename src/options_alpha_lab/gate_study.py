"""How often would the structure gate have fired, and on which branch?

The live system has recorded 266 decisions and taken zero positions. Every
structure reading so far refuses at `separation_or_side`, and none of them
marginally: separation runs about three times its minimum, and what fails is
that the close sat *below* EMA20 while the EMA stack was bullish. The retest
condition — the one the strategy is named after — is never evaluated, because
the side requirement short-circuits first.

Whether that is the intended rule is a decision for the owner. This module does
not take it. It answers the narrower question that can be answered from the
evidence on hand: **over two years of SPY history, how many sessions land on
each branch of the gate, and how does that count move under a named variation?**

The method is `sensitivity.py`'s and the same warning applies twice over. This
measures *decision* counts, not outcomes. It cannot say whether any rule makes
money, whether the current gate is right, or whether a variant would have been
profitable — one trade has ever been taken. Section 9 of the signal
specification forbids reading any of this as evidence of an edge, and a count of
qualifying sessions is not a backtest, a hit rate, or a return.

The gate is re-implemented here so that variations can be applied to it. That is
a risk — a study whose gate has drifted from the real one measures nothing — so
`test_gate_study.py` asserts the baseline reproduces `evidence.structure_reading`
on every session in the fixture. If that test fails, this report is void.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .evaluations import dataset_manifest, record
from .evidence import (
    FAST_EMA,
    MIN_BARS_REQUIRED,
    MIN_EMA_SEPARATION,
    RETEST_LOOKBACK_SESSIONS,
    RETEST_TOLERANCE,
    SLOW_EMA,
    Bar,
    ema,
)

BARS_FIXTURE = Path("fixtures/h0/sensitivity_bars.json")

#: The provider is asked for 400 calendar days, which is what the worker sees.
#: Using the whole series instead would measure a system nobody is running.
LOOKBACK_DAYS = 400

#: Variations to report beside the current rule. Each is a question someone
#: could reasonably ask about the gate, not a proposal to change it.
TOLERANCES = (Decimal("0.0025"), Decimal("0.005"), Decimal("0.010"))


@dataclass(frozen=True)
class Verdict:
    """One session's answer, plus how near it came."""

    session: object
    gate: str
    separation: Decimal | None
    close_side: str | None
    #: Signed distance of the close from the fast EMA, as a fraction of it.
    #: Negative means the close sat below EMA20.
    close_gap: Decimal | None
    retest_touched: bool | None


def load_spy() -> list[Bar]:
    payload = json.loads(BARS_FIXTURE.read_text())
    bars = [
        Bar(
            datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(UTC).date(),
            Decimal(str(r["o"])), Decimal(str(r["h"])), Decimal(str(r["l"])),
            Decimal(str(r["c"])), Decimal(str(r["v"])),
        )
        for r in payload["symbols"]["SPY"]["bars"]
    ]
    bars.sort(key=lambda bar: bar.session)
    return bars


def windows(bars: list[Bar]) -> list[list[Bar]]:
    """Each session's view of history, as the worker would have received it."""
    out: list[list[Bar]] = []
    for cut in range(len(bars)):
        last = bars[cut].session
        first = last - timedelta(days=LOOKBACK_DAYS)
        window = [bar for bar in bars[: cut + 1] if bar.session > first]
        if len(window) >= MIN_BARS_REQUIRED:
            out.append(window)
    return out


def verdict(
    window: list[Bar], *, require_side: bool = True, side_tolerance: Decimal = Decimal(0)
) -> Verdict:
    """The gate, with the side requirement made adjustable.

    `require_side=True, side_tolerance=0` is the rule as it ships. A tolerance
    lets the close sit that far the wrong side of EMA20 and still qualify;
    `require_side=False` drops the side test entirely, so separation alone opens
    the retest check.
    """
    last = window[-1]
    closes = [bar.close for bar in window]
    fast = ema(closes, FAST_EMA)
    slow = ema(closes, SLOW_EMA)
    if fast is None or slow is None or slow == 0:
        return Verdict(last.session, "ema_unavailable", None, None, None, None)

    separation = (fast - slow) / slow
    side = "above" if last.close > fast else "below"
    gap = (last.close - fast) / fast
    room = fast * side_tolerance

    if require_side:
        bullish_ok = separation >= MIN_EMA_SEPARATION and last.close > fast - room
        bearish_ok = separation <= -MIN_EMA_SEPARATION and last.close < fast + room
    else:
        bullish_ok = separation >= MIN_EMA_SEPARATION
        bearish_ok = separation <= -MIN_EMA_SEPARATION
    if not (bullish_ok or bearish_ok):
        return Verdict(last.session, "separation_or_side", separation, side, gap, None)

    recent = window[-RETEST_LOOKBACK_SESSIONS:]
    tolerance = fast * RETEST_TOLERANCE
    touched = (
        any(bar.low <= fast + tolerance for bar in recent)
        if separation > 0
        else any(bar.high >= fast - tolerance for bar in recent)
    )
    return Verdict(
        last.session, "passed" if touched else "no_retest", separation, side, gap, touched
    )


def census(
    views: list[list[Bar]], *, require_side: bool = True, side_tolerance: Decimal = Decimal(0)
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for window in views:
        answer = verdict(window, require_side=require_side, side_tolerance=side_tolerance)
        counts[answer.gate] = counts.get(answer.gate, 0) + 1
    return counts


def run() -> dict[str, Any]:
    bars = load_spy()
    views = windows(bars)
    baseline = [verdict(window) for window in views]
    refused = [v for v in baseline if v.gate == "separation_or_side"]

    # Of the sessions the side test rejected, how many had separation anyway?
    separated = [
        v for v in refused
        if v.separation is not None and abs(v.separation) >= MIN_EMA_SEPARATION
    ]
    # How far below EMA20 did those closes actually sit?
    gaps = sorted(v.close_gap for v in separated if v.close_gap is not None)

    # How long does a refusal last? The live system has refused every decision
    # it has made, which reads as a broken gate until you ask whether refusals
    # arrive in runs. If they do, a week of them is weather, not a fault.
    runs: list[int] = []
    current = 0
    for v in baseline:
        if v.gate == "passed":
            if current:
                runs.append(current)
            current = 0
        else:
            current += 1
    if current:
        runs.append(current)

    report: dict[str, Any] = {
        "sessions": len(views),
        "first": str(views[0][-1].session) if views else None,
        "last": str(views[-1][-1].session) if views else None,
        "lookback_days": LOOKBACK_DAYS,
        "baseline": census(views),
        "refused_with_separation": len(separated),
        "refusal_runs": len(runs),
        "longest_refusal_run": max(runs) if runs else 0,
        "runs_of_five_or_more": sum(1 for r in runs if r >= 5),
        "close_gap_quartiles": _quartiles(gaps),
        "variations": {
            "no_side_requirement": census(views, require_side=False),
            **{
                f"side_tolerance_{t}": census(views, side_tolerance=t) for t in TOLERANCES
            },
        },
    }
    return report


def _quartiles(values: list[Decimal]) -> dict[str, str]:
    if not values:
        return {}
    def at(fraction: float) -> str:
        return f"{values[min(len(values) - 1, int(len(values) * fraction))]:.5f}"
    return {"min": f"{values[0]:.5f}", "p25": at(0.25), "median": at(0.5),
            "p75": at(0.75), "max": f"{values[-1]:.5f}"}


def render(report: dict[str, Any]) -> str:
    lines = [
        "Structure gate over SPY daily history",
        "=" * 64,
        f"sessions evaluated : {report['sessions']}"
        f"  ({report['first']} .. {report['last']})",
        f"window per session : {report['lookback_days']} calendar days, as the worker sees it",
        "",
        "The rule as it ships",
        "-" * 64,
    ]
    total = report["sessions"]
    for gate, count in sorted(report["baseline"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {gate:<22} {count:>5}  {count / total:>6.1%}")
    lines += [
        "",
        f"Of the {report['baseline'].get('separation_or_side', 0)} refused on separation-or-side,",
        f"{report['refused_with_separation']} had separation at or beyond the minimum and failed",
        "on the side test alone. Their closes sat this far from EMA20",
        "(negative = below it, as a fraction of the EMA):",
    ]
    for name, value in report["close_gap_quartiles"].items():
        lines.append(f"  {name:<8} {value}")
    lines += [
        "",
        "How long a refusal lasts",
        "-" * 64,
        f"  refusal runs           : {report['refusal_runs']}",
        f"  longest run            : {report['longest_refusal_run']} consecutive sessions",
        f"  runs of five or more   : {report['runs_of_five_or_more']}",
        "  A stretch of consecutive refusals is ordinary here. A live run that",
        "  has refused every decision so far is consistent with this history",
        "  and is not, on its own, evidence that the gate is misconfigured.",
        "",
        "Variations",
        "-" * 64,
    ]
    for name, counts in report["variations"].items():
        passed = counts.get("passed", 0)
        lines.append(f"  {name}")
        for gate, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"      {gate:<20} {count:>5}  {count / total:>6.1%}")
        lines.append(f"      -> qualifying sessions: {passed} ({passed / total:.1%})")
    lines += [
        "",
        "What this does not say",
        "-" * 64,
        "  Nothing about profit, edge, or whether the current gate is right.",
        "  These are decision counts over one symbol's history. One trade has",
        "  ever been taken. Signal specification section 9 forbids reading a",
        "  count of qualifying sessions as evidence of an edge.",
    ]
    return "\n".join(lines)


def parameters() -> dict[str, Any]:
    """The constants in force, so a later run can be compared against this one."""
    return {
        "MIN_BARS_REQUIRED": MIN_BARS_REQUIRED,
        "FAST_EMA": FAST_EMA,
        "SLOW_EMA": SLOW_EMA,
        "MIN_EMA_SEPARATION": str(MIN_EMA_SEPARATION),
        "RETEST_LOOKBACK_SESSIONS": RETEST_LOOKBACK_SESSIONS,
        "RETEST_TOLERANCE": str(RETEST_TOLERANCE),
        "LOOKBACK_DAYS": LOOKBACK_DAYS,
        "TOLERANCES": [str(t) for t in TOLERANCES],
    }


def manifest(report: dict[str, Any]) -> dict[str, Any]:
    """The dataset, named by its digest rather than its path alone."""
    return dataset_manifest(
        BARS_FIXTURE,
        symbol="SPY",
        sessions=report["sessions"],
        first=report["first"],
        last=report["last"],
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument(
        "--record", action="store_true",
        help="append this run to evaluation_runs, so the answer survives a later change",
    )
    args = parser.parse_args(argv)
    report = run()
    print(json.dumps(report, indent=2, default=str) if args.json else render(report))

    if args.record:
        from sqlalchemy.orm import Session

        from .config import load_settings
        from .persistence.repository import build_engine

        with Session(build_engine(load_settings())) as session:
            saved = record(
                session,
                harness="gate_study",
                dataset=manifest(report),
                parameters=parameters(),
                outputs=report,
            )
            session.commit()
            print(f"\nrecorded evaluation run {saved.id} at {saved.code_revision}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
