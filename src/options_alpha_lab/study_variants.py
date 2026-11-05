"""Part B of the setup and exit study: a fixed list of alternatives, exploratory.

Plan: docs/improvements/options_alpha_setup_exit_study_plan_v0_1.md, section 4
and the definitions fixed on 5 November 2026 in section 4.1, before computing.

Each variant changes one constant of the shipped exit policy or selector for the
run only, then restores it. The simulator, bootstrap and portfolio are Part 2's
own (`veto_exits`, `study_decomposition.block_mean`, `veto_portfolio`), so the
current rules must reproduce the Part 2 trades digest before a variant is read.

Nothing here changes a trading rule. A variant that passes the reading rule is a
candidate for Paper testing, not a change.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import components, exits
from . import veto_entries as ve
from . import veto_exits as vx
from . import veto_portfolio as vp
from . import veto_replay as vr
from .calendar import TradingCalendar
from .study_decomposition import Mean, block_mean
from .veto_outcomes import BLOCK_LENGTH, REPETITIONS, SENSITIVITY_BLOCKS

CACHE = vx.CACHE
#: The Part 2 trades digest the current rules must reproduce (Part 2 report).
PART2_DIGEST = "sha256:59d5e170cb6a564e27ea09c35dbb992e38c6e399ed9040f656de223112dc8fa7"
BLOCKS = (BLOCK_LENGTH, *SENSITIVITY_BLOCKS)
#: Section 4.1, reading rule: the cases whose lower ends must clear zero.
READ_CASES = ("central", "pessimistic")
NOT_RUN_OWNER = "not run: no download, by the owner's decision of 26 October 2026"


def _never(state: exits.ExitInputs) -> Decimal:
    return Decimal("-Infinity")


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    #: (module, attribute, value) set for the run and restored afterwards.
    patches: tuple[tuple[Any, str, Any], ...]
    #: The variant selects its own entries (B5), from this paths folder.
    paths_folder: str = "paths"
    own_entries: bool = False
    not_run: str | None = None
    #: Sessions in each downloaded window; an unresolved trade is held to its end.
    window: int = 5


VARIANTS: tuple[Variant, ...] = (
    Variant("B1-2", "session stop 2", ((exits, "SESSION_STOP", 2),)),
    Variant("B1-5", "session stop 5", ((exits, "SESSION_STOP", 5),),
            paths_folder="paths_s7", window=7),
    Variant("B2", "profit target 30%",
            ((exits, "PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN", Decimal("0.30")),)),
    Variant("B3", "no stop loss", ((exits, "stop_level", _never),)),
    Variant("B4", "entry 11:00", (), not_run=NOT_RUN_OWNER),
    Variant("B5", "21-45 days to expiry", ((components, "MIN_DTE", 21),),
            paths_folder="paths_dte21", own_entries=True),
)


@contextmanager
def patched(changes: Sequence[tuple[Any, str, Any]]) -> Iterator[None]:
    """Set each attribute for the block and always restore the original."""
    saved = [(module, name, getattr(module, name)) for module, name, _ in changes]
    try:
        for module, name, value in changes:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in reversed(saved):
            setattr(module, name, value)


def permitted(done: Sequence[vx.Trade]) -> list[vx.Trade]:
    return [t for t in done if t.group == vr.PERMITTED]


def differences(variant: Sequence[vx.Trade], current: Sequence[vx.Trade],
                index: dict[str, int], length: int, case: str
                ) -> tuple[list[float | None], int]:
    """Per-session variant minus current result, over the session sequence.

    Sessions where either arm has no closed Permitted trade are gaps. Returns the
    sequence and the number of sessions that are gaps because of one arm only.
    """
    def closed(trades: Sequence[vx.Trade]) -> dict[str, float]:
        return {t.session: t.result_usd for t in trades
                if t.case == case and t.group == vr.PERMITTED
                and t.status == vx.CLOSED and t.result_usd is not None}

    def seen(trades: Sequence[vx.Trade]) -> set[str]:
        return {t.session for t in trades if t.case == case and t.group == vr.PERMITTED}

    a, b = closed(variant), closed(current)
    values: list[float | None] = [None] * length
    for session in a.keys() & b.keys():
        values[index[session]] = a[session] - b[session]
    one_sided = len((seen(variant) | seen(current)) - (a.keys() & b.keys()))
    return values, one_sided


def own_means(trades: Sequence[vx.Trade], index: dict[str, int], length: int,
              case: str, block: int = BLOCK_LENGTH, repetitions: int | None = None) -> Mean:
    values: list[float | None] = [None] * length
    for t in trades:
        if (t.case == case and t.group == vr.PERMITTED and t.status == vx.CLOSED
                and t.result_usd is not None):
            values[index[t.session]] = t.result_usd
    return block_mean(values, block=block, repetitions=repetitions or REPETITIONS)


def window_ends(entries: Sequence[ve.Entry], sessions: Sequence[date],
                window: int) -> dict[str, date]:
    """Each entry's last downloaded session, as `veto_portfolio.window_ends` for five."""
    if window == 5:
        return vp.window_ends(entries, sessions)
    out: dict[str, date] = {}
    for e in entries:
        at = list(sessions).index(date.fromisoformat(e.session))
        out[e.session] = sessions[min(at + window - 1, len(sessions) - 1)]
    return out


def portfolio_totals(entries: Sequence[ve.Entry], done: Sequence[vx.Trade],
                     sessions: Sequence[date], window: int = 5) -> dict[str, dict[str, Any]]:
    trades = {(t.session, t.case): t for t in done}
    ends = window_ends(entries, sessions, window)
    return {case: vp.summarize(vp.run(vp.BASELINE, case, entries, trades, ends))
            for case in vx.COST_CASES}


def verdict(contrast: dict[str, dict[int, Mean]], better: dict[str, bool]) -> dict[str, Any]:
    """Section 4.1's reading rule, each condition reported on its own."""
    def clears(case: str, block: int) -> bool:
        m = contrast[case][block]
        return m.low is not None and m.low > 0

    first = all(clears(c, BLOCK_LENGTH) for c in READ_CASES)
    second = all(clears(c, b) for c in READ_CASES for b in SENSITIVITY_BLOCKS)
    third = all(better.values())
    return {"interval_above_zero_block_10": first, "holds_at_5_and_20": second,
            "portfolio_better_all_cases": third, "candidate": first and second and third}


def evaluate(variant: Sequence[vx.Trade], current: Sequence[vx.Trade],
             variant_entries: Sequence[ve.Entry], current_entries: Sequence[ve.Entry],
             index: dict[str, int], length: int, sessions: Sequence[date],
             repetitions: int | None = None, window: int = 5) -> dict[str, Any]:
    reps = repetitions or REPETITIONS
    contrast: dict[str, dict[int, Mean]] = {}
    own: dict[str, Mean] = {}
    gaps: dict[str, int] = {}
    for case in vx.COST_CASES:
        values, gaps[case] = differences(variant, current, index, length, case)
        contrast[case] = {b: block_mean(values, block=b, repetitions=reps) for b in BLOCKS}
        own[case] = own_means(variant, index, length, case, repetitions=repetitions)
    mine = portfolio_totals(variant_entries, variant, sessions, window)
    theirs = portfolio_totals(current_entries, current, sessions)
    better = {c: mine[c]["total_usd"] > theirs[c]["total_usd"] for c in vx.COST_CASES}
    return {
        "own": {c: asdict(m) for c, m in own.items()},
        "against_current": {c: {str(b): asdict(m) for b, m in by.items()}
                            for c, by in contrast.items()},
        "one_sided_gaps": gaps,
        "status": {c: _status(variant, c) for c in vx.COST_CASES},
        "portfolio": {c: {"variant": mine[c]["total_usd"], "current": theirs[c]["total_usd"],
                          "variant_trades": mine[c]["trades"],
                          "variant_unresolved": len(mine[c]["unresolved"]),
                          "better": better[c]} for c in vx.COST_CASES},
        "verdict": verdict(contrast, better),
    }


def _status(trades: Sequence[vx.Trade], case: str) -> dict[str, Any]:
    from collections import Counter
    mine = [t for t in trades if t.case == case and t.group == vr.PERMITTED]
    return {"trades": len(mine), "status": dict(Counter(t.status for t in mine)),
            "triggers": dict(Counter(t.trigger for t in mine if t.status == vx.CLOSED))}


Loader = Callable[[Variant], tuple[list[vx.Trade], list[ve.Entry]]]


def run_all(load: Loader, current: Sequence[vx.Trade], current_entries: Sequence[ve.Entry],
            index: dict[str, int], length: int, sessions: Sequence[date],
            repetitions: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "current": {"digest": vx.digest(current),
                    "status": {c: _status(current, c) for c in vx.COST_CASES},
                    "own": {c: asdict(own_means(current, index, length, c,
                                                repetitions=repetitions))
                            for c in vx.COST_CASES}},
        "variants": {},
    }
    for v in VARIANTS:
        if v.not_run:
            out["variants"][v.key] = {"label": v.label, "not_run": v.not_run}
            continue
        trades, entries = load(v)
        out["variants"][v.key] = {"label": v.label, **evaluate(
            trades, current, entries, current_entries, index, length, sessions,
            repetitions=repetitions, window=v.window)}
    out["comparisons"] = len(VARIANTS)
    out["candidates"] = [k for k, r in out["variants"].items()
                         if r.get("verdict", {}).get("candidate")]
    return out


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def _iv(m: dict[str, Any]) -> str:
    return f"{_fmt(m['mean'])} [{_fmt(m['low'])}, {_fmt(m['high'])}] (n {m['n']})"


def render(rep: dict[str, Any]) -> str:
    lines = ["Setup and exit study, Part B (exploratory; Permitted only)", "",
             f"Current rules: digest {rep['current']['digest']}"]
    for case, m in rep["current"]["own"].items():
        lines.append(f"  {case}: mean {_iv(m)}")
    for key, r in rep["variants"].items():
        lines += ["", f"{key}, {r['label']}:"]
        if "not_run" in r:
            lines.append(f"  {r['not_run']}")
            continue
        for case in vx.COST_CASES:
            by = r["against_current"][case]
            p = r["portfolio"][case]
            lines.append(f"  {case}: own {_iv(r['own'][case])}; minus current "
                         f"{_iv(by['10'])}; block 5 [{_fmt(by['5']['low'])}, "
                         f"{_fmt(by['5']['high'])}], block 20 [{_fmt(by['20']['low'])}, "
                         f"{_fmt(by['20']['high'])}]")
            lines.append(f"    status {r['status'][case]['status']}; triggers "
                         f"{r['status'][case]['triggers']}")
            lines.append(f"    portfolio {_fmt(p['variant'])} vs {_fmt(p['current'])} "
                         f"({p['variant_trades']} trades, {p['variant_unresolved']} "
                         f"unresolved); better {p['better']}")
        lines.append(f"  verdict: {r['verdict']}")
    lines += ["", f"Comparisons on the list: {rep['comparisons']}; "
              f"candidates: {rep['candidates'] or 'none'}"]
    return "\n".join(lines)


def load(cache: Path = CACHE) -> tuple[Loader, list[vx.Trade], list[ve.Entry],
                                       dict[str, int], int, list[date]]:
    from .veto_study import load_bars

    current, index, length, entries = vx.load(cache)
    if vx.digest(current) != PART2_DIGEST:
        raise SystemExit(f"current rules do not reproduce Part 2: {vx.digest(current)}")
    spy, _ = load_bars(cache / "daily_bars.json")
    closes = {bar.session: bar.close for bar in spy}
    calendar = TradingCalendar.from_payload(json.loads((cache / "calendar.json").read_text()))

    def run_variant(v: Variant) -> tuple[list[vx.Trade], list[ve.Entry]]:
        paths = {p.stem: json.loads(p.read_text())
                 for p in (cache / v.paths_folder).glob("*.json")}
        with patched(v.patches):
            found = ve.load(cache)[0] if v.own_entries else entries
            if v.own_entries:
                found = [e for e in found if e.group == vr.PERMITTED]
            return vx.trades(found, paths, calendar, closes), list(found)

    return run_variant, current, entries, index, length, [bar.session for bar in spy]


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--json", type=Path, help="write the report as JSON here")
    args = parser.parse_args(argv)
    run_variant, current, entries, index, length, sessions = load(args.cache)
    rep = run_all(run_variant, current, entries, index, length, sessions)
    if args.json:
        args.json.write_text(json.dumps(rep, indent=1))
    print(render(rep))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
