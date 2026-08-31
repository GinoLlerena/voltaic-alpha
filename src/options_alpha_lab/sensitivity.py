"""Which thresholds are knife-edges?

Every numeric value in this system is labelled `PROVISIONAL`, and `DEC-008` has
been open since the exit review. This module does not close it. It answers a
narrower question that can actually be answered with the evidence available:
**how close does each threshold sit to a value that would change decisions?**

That distinction matters enough to state twice. This measures *decision*
sensitivity, not *outcome* sensitivity. It cannot say whether a threshold makes
money, because that needs many trades with known results and this system has
taken one. Nothing here may be read as evidence of an edge, and section 9 of the
signal specification forbids exactly that reading.

What it does catch is fragility. On 31 August 2026 two thresholds turned out to
be sitting on their own boundary: the qualified fixture priced at a debit/width
of exactly 0.6000 against a 0.60 ceiling, and four of nine live candidates
priced within $60 of the risk budget. Neither was noticed until one of them
produced an order that could not fill. A threshold whose nearest decision flip
is a rounding error away is not a policy, it is a coincidence, and this report
names those.

Method: set the real constant, re-run the real code, compare the answers. It
monkeypatches module globals and calls `build_signals` and `DecisionWorkflow`
directly rather than reimplementing either, because a sweep over a copy of the
logic measures the copy.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import components, evidence
from .architecture.contracts import DecisionSnapshot
from .components import DeterministicRiskGovernor
from .evidence import Bar, build_signals
from .replay import build_workflow
from .snapshot_io import load_snapshot

BARS_FIXTURE = Path("fixtures/h0/sensitivity_bars.json")
SNAPSHOTS = (
    Path("fixtures/h0/spy_qualified.snapshot.json"),
    Path("fixtures/h0/spy_bearish_qualified.snapshot.json"),
    Path("fixtures/h0/spy_refusal.snapshot.json"),
    Path("fixtures/h0/frozen/spy-live-20260828T153310Z.snapshot.json"),
    Path("fixtures/h0/frozen/spy-lifecycle-20260828T154747Z.snapshot.json"),
)
#: How many historical as-of points the structure sweep evaluates.
HISTORY_SESSIONS = 120
#: A threshold whose nearest flip is inside this fraction of its own value is
#: reported as fragile. Not a policy limit - a reading aid.
FRAGILE_MARGIN = Decimal("0.10")


# --------------------------------------------------------------------- targets
@dataclass(frozen=True)
class Threshold:
    """One number, the values to try, and how to install it.

    `companions` exists because some constants are derived at import time.
    `MIN_BARS_REQUIRED` is `SLOW_EMA + MOMENTUM_LONG_SESSIONS`, computed once, so
    sweeping `SLOW_EMA` without recomputing it would silently sweep two
    independent things at once and attribute the result to one of them.
    """

    name: str
    module: Any
    attribute: str
    values: tuple[Any, ...]
    current: Any
    element: int | None = None
    companions: tuple[str, ...] = ()
    note: str = ""

    def install(self, value: Any) -> None:
        if self.element is None:
            setattr(self.module, self.attribute, value)
        else:
            existing = list(getattr(self.module, self.attribute))
            existing[self.element] = value
            setattr(self.module, self.attribute, tuple(existing))
        for companion in self.companions:
            if companion == "MIN_BARS_REQUIRED":
                evidence.MIN_BARS_REQUIRED = (
                    evidence.SLOW_EMA + evidence.MOMENTUM_LONG_SESSIONS
                )

    def snapshot_state(self) -> dict[str, Any]:
        state = {self.attribute: getattr(self.module, self.attribute)}
        for companion in self.companions:
            state[companion] = getattr(self.module, companion)
        return state

    def restore(self, state: dict[str, Any]) -> None:
        for key, value in state.items():
            setattr(self.module, key, value)


@contextmanager
def _installed(threshold: Threshold, value: Any) -> Iterator[None]:
    state = threshold.snapshot_state()
    try:
        threshold.install(value)
        yield
    finally:
        threshold.restore(state)


def _span(low: str, high: str, step: str) -> tuple[Decimal, ...]:
    lo, hi, inc = Decimal(low), Decimal(high), Decimal(step)
    out, value = [], lo
    while value <= hi:
        out.append(value)
        value += inc
    return tuple(out)


# ------------------------------------------------------------------ evaluation
def load_bars() -> tuple[list[Bar], list[Bar]]:
    payload = json.loads(BARS_FIXTURE.read_text())

    def parse(symbol: str) -> list[Bar]:
        rows = payload["symbols"][symbol]["bars"]
        bars = [
            Bar(
                datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(UTC).date(),
                Decimal(str(r["o"])), Decimal(str(r["h"])), Decimal(str(r["l"])),
                Decimal(str(r["c"])), Decimal(str(r["v"])),
            )
            for r in rows
        ]
        bars.sort(key=lambda bar: bar.session)
        return bars

    return parse("SPY"), parse("RSP")


def signals_over_history(spy: list[Bar], rsp: list[Bar]) -> tuple[str, ...]:
    """The whole signal set at each of the last `HISTORY_SESSIONS` sessions.

    Summarising only the structure direction was the first version of this, and
    it was wrong in a way worth recording: participation and momentum thresholds
    cannot change whether *structure* qualifies, so sweeping them produced "no
    flip found" - which reads as robust when it means untested. The summary
    therefore carries the confirmers and opposers too.

    `atm_iv` is `None` throughout: implied volatility is not in the bar history,
    and inventing one would put a fabricated number inside a report whose whole
    purpose is to say which numbers are load-bearing. `CALM_ATM_IV` and
    `STRESSED_ATM_IV` are consequently **not covered** by this sweep, and are
    listed as uncovered rather than silently omitted.
    """
    by_date = {bar.session: bar for bar in rsp}
    answers: list[str] = []
    for cut in range(len(spy) - HISTORY_SESSIONS, len(spy)):
        window = spy[: cut + 1]
        as_of = datetime.combine(
            window[-1].session + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
        partner = [by_date[b.session] for b in window if b.session in by_date]
        signals = build_signals(window, None, as_of, partner)
        structure = next((s for s in signals if s.family.value == "structure"), None)
        if structure is None:
            answers.append("-")
            continue
        aligned: list[str] = []
        against: list[str] = []
        for signal in signals:
            if signal is structure:
                continue
            target = aligned if signal.direction is structure.direction else against
            target.append(f"{signal.family.value}:{signal.strength:.2f}")
        answers.append(
            f"{structure.direction.value[0]}"
            f"|{','.join(sorted(aligned))}|{','.join(sorted(against))}"
        )
    return tuple(answers)


def actions_over_snapshots(snapshots: list[DecisionSnapshot]) -> tuple[str, ...]:
    workflow = build_workflow(DeterministicRiskGovernor())
    out: list[str] = []
    for snapshot in snapshots:
        try:
            outcome = workflow.evaluate(snapshot)
        except Exception as exc:  # noqa: BLE001 - a threshold that crashes is a result
            out.append(f"error:{type(exc).__name__}")
            continue
        out.append(outcome.action.value)
    return tuple(out)


# ----------------------------------------------------------------------- sweep
@dataclass
class Result:
    threshold: Threshold
    baseline: tuple[str, ...]
    observations: list[tuple[Any, tuple[str, ...]]] = field(default_factory=list)

    @property
    def stable_low(self) -> Any:
        low = self.threshold.current
        for value, answer in sorted(self.observations, key=lambda o: o[0], reverse=True):
            if value > self.threshold.current:
                continue
            if answer != self.baseline:
                break
            low = value
        return low

    @property
    def stable_high(self) -> Any:
        high = self.threshold.current
        for value, answer in sorted(self.observations, key=lambda o: o[0]):
            if value < self.threshold.current:
                continue
            if answer != self.baseline:
                break
            high = value
        return high

    def _answer_at(self, value: Any) -> tuple[str, ...] | None:
        for candidate, answer in self.observations:
            if candidate == value:
                return answer
        return None

    def _flip_fraction(self, answer: tuple[str, ...]) -> Decimal:
        if not self.baseline:
            return Decimal("0")
        differing = sum(1 for a, b in zip(answer, self.baseline, strict=True) if a != b)
        return Decimal(differing) / Decimal(len(self.baseline))

    @property
    def worst_flip_within_10pct(self) -> Decimal:
        """The largest share of outcomes that change for a +/-10% move.

        This, not "the smallest change that flips anything", is the useful
        measure. Over 120 sessions almost any nudge flips one of them, so a
        binary any-flip test calls everything fragile and therefore says
        nothing. A gradient distinguishes a threshold that moves one session
        from one that moves a third of them.
        """
        current = Decimal(str(self.threshold.current))
        if current == 0:
            return Decimal("0")
        low, high = current * Decimal("0.9"), current * Decimal("1.1")
        worst = Decimal("0")
        for value, answer in self.observations:
            as_dec = Decimal(str(value))
            if low <= as_dec <= high:
                worst = max(worst, self._flip_fraction(answer))
        return worst

    @property
    def any_flip_found(self) -> bool:
        return any(answer != self.baseline for _, answer in self.observations)

    @property
    def fragile(self) -> bool:
        """More than a tenth of outcomes change for a tenth of a move."""
        return self.worst_flip_within_10pct > FRAGILE_MARGIN

    @property
    def inert(self) -> bool:
        """Nothing anywhere in the swept range depends on this value.

        A third category, and not the same as robust. Inert means either the
        constant is dead, or the path it governs was never exercised by this
        evidence. Both are worth knowing and neither is reassuring, so they are
        reported separately rather than folded in with the stable thresholds.
        """
        return not self.any_flip_found


def sweep(threshold: Threshold, evaluate: Callable[[], tuple[str, ...]]) -> Result:
    with _installed(threshold, threshold.current):
        baseline = evaluate()
    result = Result(threshold=threshold, baseline=baseline)
    for value in threshold.values:
        with _installed(threshold, value):
            result.observations.append((value, evaluate()))
    return result


# ------------------------------------------------------------------ thresholds
def structure_thresholds() -> list[Threshold]:
    """Swept against 120 historical sessions of real SPY and RSP closes."""
    return [
        Threshold(
            "evidence.MIN_EMA_SEPARATION", evidence, "MIN_EMA_SEPARATION",
            _span("0", "0.020", "0.0005"), evidence.MIN_EMA_SEPARATION,
        ),
        Threshold(
            "evidence.RETEST_TOLERANCE", evidence, "RETEST_TOLERANCE",
            _span("0.001", "0.050", "0.001"), evidence.RETEST_TOLERANCE,
        ),
        Threshold(
            "evidence.RETEST_LOOKBACK_SESSIONS", evidence, "RETEST_LOOKBACK_SESSIONS",
            tuple(range(1, 26)), evidence.RETEST_LOOKBACK_SESSIONS,
        ),
        Threshold(
            "evidence.FAST_EMA", evidence, "FAST_EMA",
            tuple(range(5, 41)), evidence.FAST_EMA,
        ),
        Threshold(
            "evidence.SLOW_EMA", evidence, "SLOW_EMA",
            tuple(range(25, 101)), evidence.SLOW_EMA,
            companions=("MIN_BARS_REQUIRED",),
            note="MIN_BARS_REQUIRED is recomputed with it; they are not independent",
        ),
        Threshold(
            "evidence.PARTICIPATION_SESSIONS", evidence, "PARTICIPATION_SESSIONS",
            tuple(range(2, 61)), evidence.PARTICIPATION_SESSIONS,
            note="signal spec section 6 records that this window changes the answer",
        ),
        Threshold(
            "evidence.MIN_PARTICIPATION_DIVERGENCE", evidence,
            "MIN_PARTICIPATION_DIVERGENCE", _span("0", "0.020", "0.0005"),
            evidence.MIN_PARTICIPATION_DIVERGENCE,
        ),
        Threshold(
            "evidence.MOMENTUM_SHORT_SESSIONS", evidence, "MOMENTUM_SHORT_SESSIONS",
            tuple(range(2, 21)), evidence.MOMENTUM_SHORT_SESSIONS,
        ),
        Threshold(
            "evidence.MOMENTUM_LONG_SESSIONS", evidence, "MOMENTUM_LONG_SESSIONS",
            tuple(range(10, 61)), evidence.MOMENTUM_LONG_SESSIONS,
            companions=("MIN_BARS_REQUIRED",),
            note=(
                "inert, and the sweep is how that was found: `long_return` is "
                "computed in `build_signals` and never read, so the trigger is "
                "`short_return` against the trend alone. The signal is named "
                "divergence and compares nothing"
            ),
        ),
    ]


def decision_thresholds() -> list[Threshold]:
    """Swept against the five committed snapshots, which carry real chains."""
    c = components
    return [
        Threshold("components.MIN_STRUCTURE_STRENGTH", c, "MIN_STRUCTURE_STRENGTH",
                  _span("0.30", "0.95", "0.01"), c.MIN_STRUCTURE_STRENGTH),
        Threshold("components.MIN_CONFIRMATION_STRENGTH", c, "MIN_CONFIRMATION_STRENGTH",
                  _span("0.20", "0.95", "0.01"), c.MIN_CONFIRMATION_STRENGTH),
        Threshold("components.CONTRADICTION_VETO_STRENGTH", c, "CONTRADICTION_VETO_STRENGTH",
                  _span("0.30", "1.00", "0.01"), c.CONTRADICTION_VETO_STRENGTH),
        Threshold("components.MIN_DTE", c, "MIN_DTE", tuple(range(1, 41)), c.MIN_DTE),
        Threshold("components.MAX_DTE", c, "MAX_DTE", tuple(range(20, 121)), c.MAX_DTE),
        Threshold("components.MAX_RELATIVE_QUOTE_SPREAD", c, "MAX_RELATIVE_QUOTE_SPREAD",
                  _span("0.02", "0.80", "0.01"), c.MAX_RELATIVE_QUOTE_SPREAD),
        Threshold("components.LONG_DELTA_BAND[low]", c, "LONG_DELTA_BAND",
                  _span("0.30", "0.69", "0.01"), c.LONG_DELTA_BAND[0], element=0),
        Threshold("components.LONG_DELTA_BAND[high]", c, "LONG_DELTA_BAND",
                  _span("0.56", "0.95", "0.01"), c.LONG_DELTA_BAND[1], element=1),
        Threshold("components.SHORT_DELTA_BAND[low]", c, "SHORT_DELTA_BAND",
                  _span("0.05", "0.39", "0.01"), c.SHORT_DELTA_BAND[0], element=0),
        Threshold("components.SHORT_DELTA_BAND[high]", c, "SHORT_DELTA_BAND",
                  _span("0.26", "0.70", "0.01"), c.SHORT_DELTA_BAND[1], element=1),
        Threshold("components.MAX_DEBIT_TO_WIDTH", c, "MAX_DEBIT_TO_WIDTH",
                  _span("0.20", "0.95", "0.01"), c.MAX_DEBIT_TO_WIDTH,
                  note="binding constraint since the budget rose on 31 August; DEC-010"),
        Threshold("components.MIN_WIDTH_FRACTION_OF_SPOT", c, "MIN_WIDTH_FRACTION_OF_SPOT",
                  _span("0.0005", "0.0300", "0.0005"), c.MIN_WIDTH_FRACTION_OF_SPOT),
        Threshold("components.RISK_FRACTION_OF_EQUITY", c, "RISK_FRACTION_OF_EQUITY",
                  _span("0.001", "0.020", "0.00025"), c.RISK_FRACTION_OF_EQUITY,
                  note="raised from 0.005 on 31 August; DEC-010"),
        Threshold("components.EXECUTION_ALLOWANCE_FRACTION", c, "EXECUTION_ALLOWANCE_FRACTION",
                  _span("0", "2.0", "0.05"), c.EXECUTION_ALLOWANCE_FRACTION,
                  note="added 31 August; signal spec section 7.1"),
    ]


# ---------------------------------------------------------------------- report
def _fmt(value: Any) -> str:
    return str(value.normalize()) if isinstance(value, Decimal) else str(value)


def run() -> dict[str, Any]:
    spy, rsp = load_bars()
    snapshots = [load_snapshot(path) for path in SNAPSHOTS]

    groups: list[tuple[str, list[Threshold], Callable[[], tuple[str, ...]], str]] = [
        (
            "structure",
            structure_thresholds(),
            lambda: signals_over_history(spy, rsp),
            f"the full signal set at each of the last {HISTORY_SESSIONS} "
            "completed sessions: structure direction, confirmers and opposers",
        ),
        (
            "decision",
            decision_thresholds(),
            lambda: actions_over_snapshots(snapshots),
            f"decided action on each of {len(snapshots)} committed snapshots",
        ),
    ]

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "measures": "decision sensitivity, not outcome sensitivity",
        "caveat": (
            "This says which thresholds are close to changing decisions. It says "
            "nothing about whether any threshold is profitable: that needs many "
            "trades with known results, and this system has taken one. DEC-008 "
            "stays open."
        ),
        "history_sessions": HISTORY_SESSIONS,
        "spy_sessions_available": len(spy),
        "fragile_margin": str(FRAGILE_MARGIN),
        "groups": [],
    }

    for key, thresholds, evaluate, described in groups:
        rows = []
        for threshold in thresholds:
            result = sweep(threshold, evaluate)
            rows.append({
                "threshold": threshold.name,
                "current": _fmt(threshold.current),
                "unchanged_from": _fmt(result.stable_low),
                "unchanged_to": _fmt(result.stable_high),
                "flip_share_within_10pct": f"{result.worst_flip_within_10pct:.3f}",
                "any_flip_in_swept_range": result.any_flip_found,
                "swept_from": _fmt(min(threshold.values)),
                "swept_to": _fmt(max(threshold.values)),
                "fragile": result.fragile,
                "inert": result.inert,
                "distinct_outcomes": len({answer for _, answer in result.observations}),
                "note": threshold.note,
            })
        report["groups"].append({
            "group": key, "outcome_measured": described, "thresholds": rows,
        })

    report["not_covered"] = [
        {
            "threshold": "evidence.CALM_ATM_IV / evidence.STRESSED_ATM_IV",
            "why": (
                "Implied volatility is not in the daily bar history, and the "
                "committed snapshots carry their signals precomputed, so neither "
                "sweep can reach these. Covering them needs a historical option "
                "chain, which this project does not hold."
            ),
        },
        {
            "threshold": "components.EXECUTION_ALLOWANCE_FRACTION",
            "why": (
                "Swept, but every committed snapshot quotes far tighter than the "
                "live indicative feed - 0.20 wide against the 0.45 to 0.90 seen on "
                "31 August - so the allowance never approaches the budget on this "
                "evidence and reports no flip. Read that as the fixtures being "
                "unrepresentative here, not as the threshold being robust."
            ),
        },
    ]
    return report


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Threshold sensitivity",
        "",
        f"Generated {report['generated_at']}.",
        "",
        f"**{report['measures']}.** {report['caveat']}",
        "",
    ]
    for group in report["groups"]:
        lines += [
            f"## {group['group']}",
            "",
            f"Outcome measured: {group['outcome_measured']}.",
            "",
            "| Threshold | Current | Unchanged over | Share of outcomes "
            "changed by ±10% | Distinct outcomes | |",
            "|---|---|---|---|---|---|",
        ]
        for row in group["thresholds"]:
            flag = "**fragile**" if row["fragile"] else ""
            share = f"{float(row['flip_share_within_10pct']):.1%}"
            if not row["any_flip_in_swept_range"]:
                share = f"no flip across {row['swept_from']}–{row['swept_to']}"
            lines.append(
                f"| `{row['threshold']}` | {row['current']} | "
                f"{row['unchanged_from']} – {row['unchanged_to']} | {share} | "
                f"{row['distinct_outcomes']} | {flag} |"
            )
        lines.append("")
    fragile = [
        r["threshold"] for g in report["groups"] for r in g["thresholds"] if r["fragile"]
    ]
    inert = [
        (r["threshold"], r["note"])
        for g in report["groups"] for r in g["thresholds"] if r["inert"]
    ]
    lines += [
        "## Fragile thresholds",
        "",
        (
            f"None: a ±10% move changes at most {FRAGILE_MARGIN:.0%} of outcomes "
            "for every threshold swept."
            if not fragile
            else f"A ±10% move changes more than {FRAGILE_MARGIN:.0%} of outcomes "
            "for: " + ", ".join(f"`{name}`" for name in fragile)
            + ". These are the numbers most in need of the evidence `DEC-008` "
            "and `DEC-010` still owe."
        ),
        "",
        "## Inert thresholds",
        "",
        (
            "None: every threshold swept changes some outcome somewhere in its range."
            if not inert
            else "No outcome anywhere in the swept range depends on these. That is "
            "not the same as robust - it means the constant is dead, or the path "
            "it governs was never exercised by this evidence:"
        ),
        "",
    ]
    for name, note in inert:
        lines.append(f"- `{name}`" + (f" — {note}" if note else ""))
    lines += [
        "",
        "## Not covered",
        "",
    ]
    for item in report.get("not_covered", []):
        lines += [f"- `{item['threshold']}` — {item['why']}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--json", default="artifacts/threshold_sensitivity.json")
    parser.add_argument("--markdown", default="artifacts/threshold_sensitivity.md")
    args = parser.parse_args(argv)

    report = run()
    text = render(report)
    for path, body in ((args.json, json.dumps(report, indent=2) + "\n"),
                       (args.markdown, text)):
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
