"""Step 3 of the breadth veto backtest: SPY's move after each qualifying session.

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, section 4.3
and Step 3 (`VBT-103`). Protocol: options_alpha_veto_backtest_protocol_v0_1.md,
section 8 and the 23 October 2026 note in section 11.

It takes the Step 2 rows unchanged and, for each Permitted and Breadth-vetoed
session, attaches the closes `C[0]`, `C[1]` and `C[2]` that follow the
completed close `C[-1]` the decision read. From them: the one-, two- and
three-session moves, whether a close fell below the setup's invalidation
level, and the worst close. The two groups are then compared with a seeded
moving-block bootstrap over the chronological sequence of sessions.

These are diagnostics of the underlying, not trade results: a move from
`C[-1]` includes the overnight gap before a 10:00 entry, and a call spread
caps the gain and exits during the day.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from . import veto_pricing as pricing
from .evidence import Bar
from .veto_replay import (
    BREADTH_VETOED,
    CACHE,
    CONTEXT_LINES,
    PERMITTED,
    Row,
)
from .veto_study import MIN_CLUSTERS, MIN_SESSIONS, clusters, longest_run

#: Protocol section 8.
REPETITIONS = 10_000
SEED = 20261012
BLOCK_LENGTH = 10
SENSITIVITY_BLOCKS = (5, 20)
CONFIDENCE = 0.95
HORIZONS = (1, 2, 3)
#: Protocol section 11, 23 October 2026: the realized-volatility window.
VOL_WINDOW = 20
GROUPS = (PERMITTED, BREADTH_VETOED)


@dataclass(frozen=True)
class Outcome:
    session: str
    index: int
    group: str
    opposing_breadth: str | None
    invalidation: str
    #: `C[-1]`, the last completed close the decision read.
    reference_close: str
    #: `C[0]`, `C[1]`, `C[2]`; None where the cache has no such session yet.
    closes: tuple[str | None, ...]
    move_usd: tuple[float | None, ...]
    move_pct: tuple[float | None, ...]
    #: Only when all three closes exist.
    breached: bool | None
    worst_pct: float | None
    realized_vol: float | None


def realized_vol(closes: Sequence[Decimal]) -> float | None:
    """Standard deviation of the last `VOL_WINDOW` daily log returns, or None."""
    if len(closes) < VOL_WINDOW + 1:
        return None
    window = [float(c) for c in closes[-(VOL_WINDOW + 1):]]
    returns = [math.log(b / a) for a, b in zip(window, window[1:], strict=False)]
    mean = sum(returns) / len(returns)
    return math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))


def outcomes(rows: Sequence[Row], spy: Sequence[Bar]) -> list[Outcome]:
    """One outcome per Permitted or Breadth-vetoed row, in session order."""
    position = {str(bar.session): i for i, bar in enumerate(spy)}
    closes = [bar.close for bar in spy]
    out: list[Outcome] = []
    for row in rows:
        if row.bucket not in GROUPS:
            continue
        if row.completed is None or row.invalidation is None:
            raise ValueError(f"{row.session}: a qualifying row lacks its close or level")
        before = position[row.completed]
        # The decision session must be the next cached session after the one it
        # read: a missing session would silently shift every horizon by one.
        if before + 1 < len(spy) and str(spy[before + 1].session) != row.session:
            raise ValueError(f"{row.session}: not the session after {row.completed}")
        base = closes[before]
        forward: list[Decimal | None] = [
            closes[before + h] if before + h < len(closes) else None for h in HORIZONS
        ]
        usd = tuple(None if c is None else float(c - base) for c in forward)
        pct = tuple(None if c is None else float((c - base) / base * 100) for c in forward)
        level = Decimal(row.invalidation)
        complete = [c for c in forward if c is not None]
        full = len(complete) == len(HORIZONS)
        worst = min(complete) if full else None
        out.append(Outcome(
            session=row.session, index=row.index, group=row.bucket,
            opposing_breadth=row.opposing_breadth, invalidation=row.invalidation,
            reference_close=str(base),
            closes=tuple(None if c is None else str(c) for c in forward),
            move_usd=usd, move_pct=pct,
            breached=any(c < level for c in complete) if full else None,
            worst_pct=None if worst is None else float((worst - base) / base * 100),
            realized_vol=realized_vol(closes[:before + 1]),
        ))
    return out


Metric = Callable[[Outcome], float | None]


def metrics() -> dict[str, Metric]:
    """Every compared quantity, by name. The first is the primary metric."""
    found: dict[str, Metric] = {
        "3-session move, %": lambda o: o.move_pct[2],
        "1-session move, %": lambda o: o.move_pct[0],
        "2-session move, %": lambda o: o.move_pct[1],
        "3-session move, USD per share": lambda o: o.move_usd[2],
        "invalidation breached, % of sessions":
            lambda o: None if o.breached is None else 100.0 * o.breached,
        "worst close within 3 sessions, %": lambda o: o.worst_pct,
    }
    return found


PRIMARY = next(iter(metrics()))


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(ordered: Sequence[float], q: float) -> float:
    """Linear interpolation between closest ranks, as protocol section 11 states."""
    pos = q * (len(ordered) - 1)
    low = math.floor(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


@dataclass(frozen=True)
class Contrast:
    metric: str
    block_length: int
    #: Usable sessions per group, then sessions excluded for a censored value.
    permitted_n: int
    vetoed_n: int
    permitted_excluded: int
    vetoed_excluded: int
    permitted_mean: float | None
    vetoed_mean: float | None
    difference: float | None
    low: float | None
    high: float | None
    #: Replicates that drew no usable member of one group.
    empty_replicates: int


def labels(sequence_length: int, members: Sequence[Outcome],
           group_of: Callable[[Outcome], str | None]) -> list[str | None]:
    """The group label at each position of the session sequence, None for gaps."""
    out: list[str | None] = [None] * sequence_length
    for o in members:
        out[o.index] = group_of(o)
    return out


def starts(sequence_length: int, block: int, rng: random.Random) -> list[int]:
    """One replicate's block starts (protocol section 11)."""
    count = math.ceil(sequence_length / block)
    return [rng.randint(0, sequence_length - block) for _ in range(count)]


def block_contrast(metric: str, group: Sequence[str | None], values: Sequence[float | None],
                   block: int = BLOCK_LENGTH, repetitions: int = REPETITIONS,
                   seed: int = SEED) -> Contrast:
    """Permitted minus Breadth-vetoed over a session sequence, with its interval.

    `group` and `values` run over the whole chronological sequence; a position
    with no group, or with no value, is a gap. Part 2 calls this with spread
    results, so both parts share one bootstrap.
    """
    sequence_length = len(group)
    usable = {g: [v for v, label in zip(values, group, strict=True)
                  if label == g and v is not None] for g in GROUPS}
    excluded = {g: sum(1 for i in range(sequence_length)
                       if group[i] == g and values[i] is None) for g in GROUPS}
    p_mean = _mean(usable[PERMITTED])
    v_mean = _mean(usable[BREADTH_VETOED])
    difference = None if p_mean is None or v_mean is None else p_mean - v_mean

    # Prefix sums per position of each group's values and counts, so a block's
    # contribution is a difference of two entries.
    def prefix(name: str, count: bool) -> list[float]:
        out = [0.0]
        for v, label in zip(values, group, strict=True):
            hit = label == name and v is not None
            out.append(out[-1] + ((1.0 if count else float(v or 0.0)) if hit else 0.0))
        return out

    sums = [prefix(PERMITTED, False), prefix(PERMITTED, True),
            prefix(BREADTH_VETOED, False), prefix(BREADTH_VETOED, True)]
    # Seeded for reproducibility (protocol section 8), not for secrecy.
    rng = random.Random(seed)  # noqa: S311
    draws: list[float] = []
    empty = 0
    for _ in range(repetitions):
        totals = [0.0, 0.0, 0.0, 0.0]
        remaining = sequence_length
        for start in starts(sequence_length, block, rng):
            take = min(block, remaining)
            for k, s in enumerate(sums):
                totals[k] += s[start + take] - s[start]
            remaining -= take
        if totals[1] == 0 or totals[3] == 0:
            empty += 1
            continue
        draws.append(totals[0] / totals[1] - totals[2] / totals[3])
    draws.sort()
    tail = (1 - CONFIDENCE) / 2
    return Contrast(
        metric=metric, block_length=block,
        permitted_n=len(usable[PERMITTED]), vetoed_n=len(usable[BREADTH_VETOED]),
        permitted_excluded=excluded[PERMITTED], vetoed_excluded=excluded[BREADTH_VETOED],
        permitted_mean=p_mean, vetoed_mean=v_mean, difference=difference,
        low=_percentile(draws, tail) if draws else None,
        high=_percentile(draws, 1 - tail) if draws else None,
        empty_replicates=empty,
    )


def contrast(sequence_length: int, members: Sequence[Outcome], metric: str,
             group_of: Callable[[Outcome], str | None] = lambda o: o.group,
             block: int = BLOCK_LENGTH, repetitions: int = REPETITIONS,
             seed: int = SEED) -> Contrast:
    """Permitted minus Breadth-vetoed for one Step 3 metric."""
    value = metrics()[metric]
    group = labels(sequence_length, members, group_of)
    values: list[float | None] = [None] * sequence_length
    for o in members:
        values[o.index] = value(o)
    return block_contrast(metric, group, values, block, repetitions, seed)


def at_line(line: Decimal) -> Callable[[Outcome], str]:
    """Regroup the qualifying sessions under another breadth line (context only)."""
    def group(o: Outcome) -> str:
        vetoed = o.opposing_breadth is not None and Decimal(o.opposing_breadth) >= line
        return BREADTH_VETOED if vetoed else PERMITTED
    return group


def within(keep: Callable[[Outcome], bool]) -> Callable[[Outcome], str | None]:
    """The real groups, restricted to a breakdown's sessions; others become gaps."""
    return lambda o: o.group if keep(o) else None


def report(rows: Sequence[Row], spy: Sequence[Bar], repetitions: int = REPETITIONS
           ) -> dict[str, Any]:
    found = outcomes(rows, spy)
    n = len(rows)
    names = list(metrics())
    main = [contrast(n, found, m, repetitions=repetitions) for m in names]
    sensitivity = [contrast(n, found, PRIMARY, block=b, repetitions=repetitions)
                   for b in SENSITIVITY_BLOCKS]

    vols = [o.realized_vol for o in found if o.realized_vol is not None]
    vol_median = median(vols) if vols else None
    breakdowns: dict[str, Contrast] = {}
    for year in sorted({o.session[:4] for o in found}):
        def in_year(o: Outcome, y: str = year) -> bool:
            return o.session.startswith(y)
        breakdowns[f"year {year}"] = contrast(n, found, PRIMARY, within(in_year),
                                              repetitions=repetitions)
    if vol_median is not None:
        breakdowns["realized volatility at or below the median"] = contrast(
            n, found, PRIMARY, within(lambda o: o.realized_vol is not None
                                      and o.realized_vol <= vol_median),
            repetitions=repetitions)
        breakdowns["realized volatility above the median"] = contrast(
            n, found, PRIMARY, within(lambda o: o.realized_vol is not None
                                      and o.realized_vol > vol_median),
            repetitions=repetitions)

    lines: dict[str, Contrast] = {
        str(line): contrast(n, found, PRIMARY, at_line(line), repetitions=repetitions)
        for line in CONTEXT_LINES
    }
    every = [o.move_pct[2] for o in found if o.move_pct[2] is not None]
    # Context: every replayed session with a completed close, whatever its bucket.
    position = {str(bar.session): i for i, bar in enumerate(spy)}
    baseline = [float((spy[position[r.completed] + 3].close - spy[position[r.completed]].close)
                      / spy[position[r.completed]].close * 100)
                for r in rows if r.completed is not None and position[r.completed] + 3 < len(spy)]

    groups: dict[str, Any] = {}
    for g in GROUPS:
        members = [o for o in found if o.group == g]
        full = [o for o in members if o.move_pct[2] is not None]
        indexes = [o.index for o in full]
        groups[g] = {
            "sessions": len(members),
            "full_horizon": len(full),
            "censored": [o.session for o in members if o.move_pct[2] is None],
            "clusters": len(clusters(indexes)),
            "longest_run": longest_run([o.index for o in members]),
            "screen_passes": len(full) >= MIN_SESSIONS and len(clusters(indexes)) >= MIN_CLUSTERS,
        }
    return {
        "first": found[0].session if found else None,
        "last": found[-1].session if found else None,
        "sequence_length": n,
        "groups": groups,
        "contrasts": [asdict(c) for c in main],
        "sensitivity": [asdict(c) for c in sensitivity],
        "breakdowns": {k: asdict(c) for k, c in breakdowns.items()},
        "vol_median": vol_median,
        "context_lines": {k: asdict(c) for k, c in lines.items()},
        "breadth_off": {"sessions": len(every), "mean": _mean(every)},
        "all_sessions": {"sessions": len(baseline), "mean": _mean(baseline)},
        "outcomes_digest": digest(found),
    }


def digest(found: Sequence[Outcome]) -> str:
    payload = json.dumps([asdict(o) for o in found], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _fmt(x: float | None, places: int = 3) -> str:
    return "n/a" if x is None else f"{x:+.{places}f}"


def render(rep: dict[str, Any]) -> str:
    lines = [
        "Breadth veto, Step 3: SPY outcomes after Permitted and Breadth-vetoed sessions", "",
        f"Sessions {rep['first']} to {rep['last']}; sequence of {rep['sequence_length']} "
        f"replayed sessions; {REPETITIONS} replicates, seed {SEED}", "",
    ]
    for g, info in rep["groups"].items():
        lines.append(f"{g}: {info['sessions']} sessions, {info['full_horizon']} with all three "
                     f"closes, {info['clusters']} clusters, longest run {info['longest_run']}, "
                     f"censored {info['censored'] or 'none'}, screen "
                     f"{'passes' if info['screen_passes'] else 'FAILS'}")

    def row(c: dict[str, Any], label: str | None = None) -> str:
        return (f"  {label or c['metric']}: Permitted {_fmt(c['permitted_mean'])} "
                f"(n={c['permitted_n']}, excl {c['permitted_excluded']}), Vetoed "
                f"{_fmt(c['vetoed_mean'])} (n={c['vetoed_n']}, excl {c['vetoed_excluded']}), "
                f"P-V {_fmt(c['difference'])} [{_fmt(c['low'])}, {_fmt(c['high'])}]"
                + (f", {c['empty_replicates']} empty replicates" if c["empty_replicates"] else ""))

    lines += ["", f"Contrasts, block length {BLOCK_LENGTH}, 95% interval:"]
    lines += [row(c) for c in rep["contrasts"]]
    lines += ["", "Primary metric, block-length sensitivity:"]
    lines += [row(c, f"block {c['block_length']}") for c in rep["sensitivity"]]
    lines += ["", f"Primary metric by breakdown (realized-vol median {rep['vol_median']:.5f}):"]
    lines += [row(c, k) for k, c in rep["breakdowns"].items()]
    lines += ["", "Context only, other breadth lines (primary metric):"]
    lines += [row(c, f"line {k}") for k, c in rep["context_lines"].items()]
    off = rep["breadth_off"]
    lines.append(f"  breadth veto off: all {off['sessions']} sessions, mean {_fmt(off['mean'])}")
    every = rep["all_sessions"]
    lines.append(f"  every replayed session, any bucket: {every['sessions']} sessions, "
                 f"mean {_fmt(every['mean'])}")
    lines += ["", f"Outcomes digest: {rep['outcomes_digest']}"]
    return "\n".join(lines)


def load(cache: Path = CACHE, dividend: float = pricing.DIVIDEND_YIELD
         ) -> tuple[list[Row], list[Bar], dict[str, Any]]:
    from . import veto_replay
    from .veto_study import load_bars

    rows, check = veto_replay.load(cache, dividend)
    spy, _ = load_bars(cache / "daily_bars.json")
    return rows, spy, check


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    from . import veto_replay

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--outcomes", type=Path, help="write every outcome as JSON here")
    parser.add_argument("--json", type=Path, help="write the report as JSON here")
    args = parser.parse_args(argv)
    rows, spy, check = load(args.cache)
    if not check["passes"]:
        print("Step 2 parity fails; no outcome is computed.")
        return 1
    print(f"Step 2 rows digest: {veto_replay.digest(rows)}")
    rep = report(rows, spy)
    if args.outcomes:
        args.outcomes.write_text(json.dumps([asdict(o) for o in outcomes(rows, spy)], indent=1))
    if args.json:
        args.json.write_text(json.dumps(rep, indent=1))
    print(render(rep))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
