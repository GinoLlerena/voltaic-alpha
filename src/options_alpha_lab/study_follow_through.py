"""Setup follow-through study: does SPY rise more after qualifying sessions?

Plan: docs/improvements/options_alpha_setup_follow_through_study_plan_v0_1.md,
sections 3 and 4, with the details fixed on approval in section 3.1
(5 November 2026, before computing).

It reads the Step 2 replay rows unchanged (their digest must be reproduced)
and the cached SPY daily bars. Part A compares the h-session SPY move after
qualifying sessions (Permitted plus Breadth-vetoed) with the move after
non-qualifying ones (No setup, Out of scope, Other/multiple vetoes). Part B
splits the qualifying sessions four fixed ways and only describes them.
Nothing here changes a rule.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import veto_replay as vr
from .components import MIN_CONFIRMATION_STRENGTH
from .evidence import Bar
from .study_decomposition import Mean, block_mean
from .veto_outcomes import (
    BLOCK_LENGTH,
    HORIZONS,
    REPETITIONS,
    SENSITIVITY_BLOCKS,
    block_contrast,
)

ROWS_DIGEST = "sha256:e959635b3dc7e1861ff3c9969b53fcc29528f53e552cd1741ee8877b02bb4080"
BLOCKS = (BLOCK_LENGTH, *SENSITIVITY_BLOCKS)
PRIMARY_H = 3
QUALIFYING = (vr.PERMITTED, vr.BREADTH_VETOED)
NON_QUALIFYING = (vr.NO_SETUP, vr.OUT_OF_SCOPE, vr.OTHER_VETOES)
#: block_contrast compares two fixed labels; qualifying is passed as the first.
_Q, _N = vr.PERMITTED, vr.BREADTH_VETOED
#: The four signals build_signals emits, by family. An unknown ID is an error.
FAMILY = {
    "sig-structure-trend-retest": "structure",
    "sig-momentum-divergence": "momentum",
    "sig-participation-breadth": "participation",
    "sig-volatility-regime": "volatility",
}
THIRDS = ("lower", "middle", "upper")
PRIOR_RUN = 20


def moves(rows: Sequence[vr.Row], spy: Sequence[Bar]) -> dict[int, list[float | None]]:
    """Per horizon, the % move from `C[-1]` to the h-th close after it, by row index.

    None for a row with no completed close or with that close not cached yet.
    """
    position = {str(bar.session): i for i, bar in enumerate(spy)}
    out: dict[int, list[float | None]] = {h: [None] * len(rows) for h in HORIZONS}
    for row in rows:
        if row.completed is None:
            continue
        before = position[row.completed]
        base = spy[before].close
        for h in HORIZONS:
            if before + h < len(spy):
                out[h][row.index] = float((spy[before + h].close - base) / base * 100)
    return out


def prior_move(rows: Sequence[vr.Row], spy: Sequence[Bar], back: int
               ) -> list[float | None]:
    """The % move from `C[-1-back]` to `C[-1]`, by row index (D3: 20, D4: 1)."""
    position = {str(bar.session): i for i, bar in enumerate(spy)}
    out: list[float | None] = [None] * len(rows)
    for row in rows:
        if row.completed is None:
            continue
        end = position[row.completed]
        if end - back >= 0:
            start = spy[end - back].close
            out[row.index] = float((spy[end].close - start) / start * 100)
    return out


def _bullish(row: vr.Row) -> list[tuple[str, Decimal]]:
    found = []
    for signal_id, direction, strength in row.signals:
        if signal_id not in FAMILY:
            raise ValueError(f"{row.session}: unknown signal {signal_id}")
        if direction == "bullish":
            found.append((signal_id, Decimal(strength)))
    return found


def confirming_family(row: vr.Row) -> str | None:
    """The confirmation the classifier picks: strongest, ties by signal ID (3.1, 4)."""
    candidates = [(s, sid) for sid, s in _bullish(row)
                  if FAMILY[sid] != "structure" and s >= MIN_CONFIRMATION_STRENGTH]
    return FAMILY[max(candidates)[1]] if candidates else None


def structure_strength(row: vr.Row) -> float | None:
    """The anchor's strength: the strongest bullish structure signal (3.1, 5)."""
    found = [s for sid, s in _bullish(row) if FAMILY[sid] == "structure"]
    return float(max(found)) if found else None


def cuts(values: Sequence[float]) -> tuple[float, float]:
    """The two cut values, at ranks ceil(n/3) and ceil(2n/3) (3.1, 6)."""
    ordered = sorted(values)
    n = len(ordered)
    if n < 3:
        raise ValueError("fewer than three values to cut in thirds")
    return ordered[math.ceil(n / 3) - 1], ordered[math.ceil(2 * n / 3) - 1]


def third(value: float, cut: tuple[float, float]) -> str:
    if value <= cut[0]:
        return THIRDS[0]
    return THIRDS[1] if value <= cut[1] else THIRDS[2]


def _mean_line(values: Sequence[float | None], subset: Sequence[bool],
               repetitions: int) -> dict[str, Any]:
    m: Mean = block_mean(values, repetitions=repetitions, subset=subset)
    return asdict(m)


def report(rows: Sequence[vr.Row], spy: Sequence[Bar], repetitions: int = REPETITIONS
           ) -> dict[str, Any]:
    n = len(rows)
    move = moves(rows, spy)
    label: list[str | None] = [None] * n
    for row in rows:
        if row.bucket in QUALIFYING:
            label[row.index] = _Q
        elif row.bucket in NON_QUALIFYING:
            label[row.index] = _N
    counts = {
        "qualifying": sum(1 for g in label if g == _Q),
        "non_qualifying": sum(1 for g in label if g == _N),
        "unmeasurable": sum(1 for r in rows if r.bucket == vr.UNMEASURABLE),
        "by_bucket": {b: sum(1 for r in rows if r.bucket == b) for b in vr.BUCKETS},
    }

    part_a: dict[str, Any] = {}
    for h in HORIZONS:
        for block in (BLOCKS if h == PRIMARY_H else (BLOCK_LENGTH,)):
            c = block_contrast(f"{h}-session move, %", label, move[h], block=block,
                               repetitions=repetitions)
            part_a[f"h{h}_block{block}"] = {
                "h": h, "block": block,
                "qualifying_n": c.permitted_n, "qualifying_censored": c.permitted_excluded,
                "qualifying_mean": c.permitted_mean,
                "non_qualifying_n": c.vetoed_n, "non_qualifying_censored": c.vetoed_excluded,
                "non_qualifying_mean": c.vetoed_mean,
                "difference": c.difference, "low": c.low, "high": c.high,
                "empty_replicates": c.empty_replicates,
            }
    primary = [part_a[f"h{PRIMARY_H}_block{b}"] for b in BLOCKS]
    lows_ok = all(p["low"] is not None for p in primary)
    reading = ("lags" if lows_ok and all(p["high"] < 0 for p in primary)
               else "leads" if lows_ok and all(p["low"] > 0 for p in primary)
               else "no measurable difference")

    outcome = move[PRIMARY_H]
    q_full = [r for r in rows if label[r.index] == _Q and outcome[r.index] is not None]
    by_index = {r.index: r for r in rows}

    def subset(keep: Callable[[vr.Row], bool], group: str = _Q) -> list[bool]:
        return [label[i] == group and keep(by_index[i]) for i in range(n)]

    part_b: dict[str, Any] = {}
    families = {r.index: confirming_family(r) for r in q_full}
    if any(f is None for f in families.values()):
        raise ValueError("a qualifying session without a confirming signal")
    def of_family(name: str) -> Callable[[vr.Row], bool]:
        return lambda r: families.get(r.index) == name

    part_b["D1"] = {
        fam: _mean_line(outcome, subset(of_family(fam)), repetitions)
        for fam in sorted({f for f in families.values() if f is not None})
    }

    strength = {r.index: structure_strength(r) for r in rows}
    prior20 = prior_move(rows, spy, PRIOR_RUN)
    last1 = prior_move(rows, spy, 1)
    splits: dict[str, tuple[Sequence[float | None], bool]] = {
        "D2": ([strength[i] for i in range(n)], False),
        "D3": (prior20, True),
        "D4": (last1, True),
    }
    for key, (variable, with_non) in splits.items():
        values = [variable[r.index] for r in q_full]
        if any(v is None for v in values):
            raise ValueError(f"{key}: a qualifying session without its split value")
        cut = cuts([v for v in values if v is not None])
        entry: dict[str, Any] = {"cuts": list(cut), "qualifying": {}, "non_qualifying": {}}
        for t in THIRDS:
            def keep(r: vr.Row, t: str = t, var: Sequence[float | None] = variable,
                     cut: tuple[float, float] = cut) -> bool:
                v = var[r.index]
                return v is not None and third(v, cut) == t
            entry["qualifying"][t] = _mean_line(outcome, subset(keep), repetitions)
            if with_non:
                entry["non_qualifying"][t] = _mean_line(outcome, subset(keep, _N),
                                                        repetitions)
        if not with_non:
            del entry["non_qualifying"]
        part_b[key] = entry

    return {
        "rows": n, "first": rows[0].session if rows else None,
        "last": rows[-1].session if rows else None,
        "counts": counts, "part_a": part_a, "reading": reading,
        "part_b": part_b,
    }


def _f(x: float | None, places: int = 3) -> str:
    return "n/a" if x is None else f"{x:+.{places}f}"


def render(rep: dict[str, Any]) -> str:
    c = rep["counts"]
    out = [f"Follow-through study, {rep['first']} to {rep['last']}, {rep['rows']} rows",
           f"qualifying {c['qualifying']}, non-qualifying {c['non_qualifying']}, "
           f"unmeasurable left out {c['unmeasurable']}; buckets {c['by_bucket']}", "",
           "Part A: qualifying minus non-qualifying, SPY move %"]
    for a in rep["part_a"].values():
        out.append(f"  h={a['h']} block {a['block']}: Q {_f(a['qualifying_mean'])} "
                   f"(n={a['qualifying_n']}, cens {a['qualifying_censored']}) "
                   f"N {_f(a['non_qualifying_mean'])} (n={a['non_qualifying_n']}, cens "
                   f"{a['non_qualifying_censored']}) diff {_f(a['difference'])} "
                   f"[{_f(a['low'])}, {_f(a['high'])}]")
    out += [f"  reading at h={PRIMARY_H}: {rep['reading']}", "",
            f"Part B: qualifying sessions, h={PRIMARY_H}, block {BLOCK_LENGTH}"]

    def line(name: str, m: dict[str, Any]) -> str:
        return f"    {name}: n={m['n']} mean {_f(m['mean'])} [{_f(m['low'])}, {_f(m['high'])}]"

    b = rep["part_b"]
    out.append("  D1 confirming family")
    out += [line(k, m) for k, m in b["D1"].items()]
    for key, title in (("D2", "structure strength"), ("D3", "20-session prior move %"),
                       ("D4", "last-session move %")):
        out.append(f"  {key} {title}, cuts {b[key]['cuts'][0]:.4f} / {b[key]['cuts'][1]:.4f}")
        for t in THIRDS:
            out.append(line(f"qualifying {t}", b[key]["qualifying"][t]))
            if "non_qualifying" in b[key]:
                out.append(line(f"non-qualifying {t}", b[key]["non_qualifying"][t]))
    return "\n".join(out)


def load(cache: Path = vr.CACHE) -> tuple[list[vr.Row], list[Bar]]:
    """The Step 2 rows and SPY bars; refuses unless the rows digest is reproduced."""
    from .veto_study import load_bars

    rows, check = vr.load(cache)
    if not check["passes"] or vr.digest(rows) != ROWS_DIGEST:
        raise SystemExit(f"Step 2 rows not reproduced: {vr.digest(rows)}")
    spy, _ = load_bars(cache / "daily_bars.json")
    return rows, spy


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=vr.CACHE)
    parser.add_argument("--json", type=Path, help="write the report as JSON here")
    args = parser.parse_args(argv)
    rows, spy = load(args.cache)
    print(f"Step 2 rows digest: {ROWS_DIGEST} (reproduced)")
    rep = report(rows, spy)
    if args.json:
        args.json.write_text(json.dumps(rep, indent=1))
    print(render(rep))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
