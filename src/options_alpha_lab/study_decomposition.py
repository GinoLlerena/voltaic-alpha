"""Part A of the setup and exit study: where the Part 2 result comes from.

Plan: docs/improvements/options_alpha_setup_exit_study_plan_v0_1.md, section 3
and the definitions fixed on 24 October 2026 in section 3.1.

It reads the Part 2 entries, trades and exit paths unchanged and describes
them four ways: the spread's value at the first three closes, the cost of
waiting for an exit fill, the result against SPY's move, and the entry price.
No rule is changed and nothing here is a test.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import veto_entries as ve
from . import veto_exits as vx
from . import veto_replay as vr
from .calendar import MARKET_TZ, TradingCalendar
from .evidence import Bar
from .veto_outcomes import (
    BLOCK_LENGTH,
    CONFIDENCE,
    REPETITIONS,
    SEED,
    _percentile,
    starts,
)

CACHE = vx.CACHE
#: Section 3.1: the closes A1 reads, counted from the entry session.
CLOSES = ("C0", "C1", "C2")
GROUPS = {vr.PERMITTED: (vr.PERMITTED,), vr.BREADTH_VETOED: (vr.BREADTH_VETOED,),
          "both": (vr.PERMITTED, vr.BREADTH_VETOED)}
THIRDS = ("lowest third", "middle third", "highest third")


@dataclass(frozen=True)
class Mean:
    n: int
    #: Positions in the subset without a value, left out and counted.
    missing: int
    mean: float | None
    low: float | None
    high: float | None


def block_mean(values: Sequence[float | None], block: int = BLOCK_LENGTH,
               repetitions: int = REPETITIONS, seed: int = SEED,
               subset: Sequence[bool] | None = None) -> Mean:
    """A mean over a session sequence, with the frozen moving-block interval.

    `values` runs over the whole chronological sequence; positions outside
    `subset`, or without a value, are gaps. The resampling is the one
    `block_contrast` uses, applied to a single mean.
    """
    length = len(values)
    inside = [True] * length if subset is None else list(subset)
    used = [v if keep else None for v, keep in zip(values, inside, strict=True)]
    present = [v for v in used if v is not None]
    missing = sum(1 for v, keep in zip(values, inside, strict=True) if keep and v is None)
    if not present:
        return Mean(0, missing, None, None, None)
    sums, counts = [0.0], [0.0]
    for v in used:
        sums.append(sums[-1] + (v if v is not None else 0.0))
        counts.append(counts[-1] + (1.0 if v is not None else 0.0))
    # Seeded for reproducibility (protocol section 8), not for secrecy.
    rng = random.Random(seed)  # noqa: S311
    draws: list[float] = []
    for _ in range(repetitions):
        total = count = 0.0
        remaining = length
        for start in starts(length, block, rng):
            take = min(block, remaining)
            total += sums[start + take] - sums[start]
            count += counts[start + take] - counts[start]
            remaining -= take
        if count:
            draws.append(total / count)
    draws.sort()
    tail = (1 - CONFIDENCE) / 2
    return Mean(len(present), missing, sum(present) / len(present),
                _percentile(draws, tail) if draws else None,
                _percentile(draws, 1 - tail) if draws else None)


def session_closes(calendar: TradingCalendar, entry: date, last: date, count: int = 3
                   ) -> list[datetime]:
    """The closes of the entry session and the sessions after it, inside the path."""
    out: list[datetime] = []
    day = entry
    while day <= last and len(out) < count:
        session = calendar.session_for(datetime.combine(day, time(12), tzinfo=MARKET_TZ))
        if session is not None:
            out.append(session.close_at.astimezone(MARKET_TZ))
        day += timedelta(days=1)
    return out


def _legs(entry: ve.Entry, path: dict[str, Any]) -> tuple[vx.Bars, vx.Bars]:
    assert entry.long_symbol and entry.short_symbol
    return (vx.leg_bars(path["legs"][entry.long_symbol]),
            vx.leg_bars(path["legs"][entry.short_symbol]))


def close_changes(entry: ve.Entry, trade: vx.Trade, path: dict[str, Any] | None,
                  calendar: TradingCalendar) -> list[float | None]:
    """A1: (value at C0, C1, C2 less friction minus the entry debit) x 100."""
    if path is None:
        return [None] * len(CLOSES)
    long, short = _legs(entry, path)
    friction = vx.COST_CASES[trade.case]
    debit = Decimal(trade.entry_debit)
    moments = session_closes(calendar, date.fromisoformat(entry.session),
                             date.fromisoformat(path["last"]), len(CLOSES))
    out: list[float | None] = []
    for i in range(len(CLOSES)):
        raw = vx.value_at(long, short, moments[i]) if i < len(moments) else None
        out.append(None if raw is None else float((raw - friction - debit) * vx.MULTIPLIER))
    return out


@dataclass(frozen=True)
class Delay:
    trigger: str
    observations: int
    #: (exit value - value at the trigger) x 100, both less friction; None if
    #: the trigger's value could not be measured.
    cost_usd: float | None


def exit_delay(entry: ve.Entry, trade: vx.Trade, path: dict[str, Any],
               calendar: TradingCalendar) -> Delay:
    """A2, for a closed trade."""
    assert trade.triggered_at and trade.exited_at and trade.exit_value and trade.trigger
    long, short = _legs(entry, path)
    moments = vx.observations(calendar, date.fromisoformat(entry.session),
                              date.fromisoformat(path["last"]))
    stamps = [m.isoformat() for m in moments]
    triggered = moments[stamps.index(trade.triggered_at)]
    waited = stamps.index(trade.exited_at) - stamps.index(trade.triggered_at)
    raw = vx.value_at(long, short, triggered)
    cost = None if raw is None else float(
        (Decimal(trade.exit_value) - (raw - vx.COST_CASES[trade.case])) * vx.MULTIPLIER)
    return Delay(trade.trigger, waited, cost)


def spy_move(session: str, spy: Sequence[Bar], reference: str | None) -> float | None:
    """A3: Part 1's 3-session move, `C[-1]` to `C[2]`, in %."""
    position = {str(bar.session): i for i, bar in enumerate(spy)}
    at = position[session]
    if at == 0 or at + 2 >= len(spy):
        return None
    base = spy[at - 1].close
    if reference is not None and Decimal(reference) != base:
        raise ValueError(f"{session}: entry's reference close is not C[-1]")
    return float((spy[at + 2].close - base) / base * 100)


def thirds(values: Sequence[float]) -> tuple[float, float]:
    """Cut points at the 1/3 and 2/3 quantiles of the values alone."""
    ordered = sorted(values)
    return _percentile(ordered, 1 / 3), _percentile(ordered, 2 / 3)


def third_of(value: float, cuts: tuple[float, float]) -> str:
    if value <= cuts[0]:
        return THIRDS[0]
    return THIRDS[1] if value <= cuts[1] else THIRDS[2]


Row = dict[str, Any]


def rows(entries: Sequence[ve.Entry], done: Sequence[vx.Trade],
         paths: dict[str, dict[str, Any]], calendar: TradingCalendar,
         spy: Sequence[Bar]) -> list[Row]:
    """One row per trade and cost case, with every Part A quantity."""
    by_session = {e.session: e for e in entries}
    out: list[Row] = []
    for t in done:
        e = by_session[t.session]
        path = paths.get(t.session)
        closed = t.status == vx.CLOSED and t.result_usd is not None
        delay = exit_delay(e, t, path, calendar) if closed and path is not None else None
        assert e.fill_reference and e.estimated_debit and e.width
        out.append({
            "session": t.session, "group": t.group, "case": t.case,
            "result_usd": t.result_usd if closed else None,
            "trigger": t.trigger,
            "close_changes_usd": close_changes(e, t, path, calendar),
            "delay": None if delay is None else asdict(delay),
            "spy_move_pct": spy_move(t.session, spy, e.reference_close),
            "fill_minus_estimate_usd": float(
                (Decimal(e.fill_reference) - Decimal(e.estimated_debit)) * vx.MULTIPLIER),
            "debit_to_width": float(Decimal(t.entry_debit) / Decimal(e.width)),
        })
    return out


def _sequence(members: Sequence[Row], index: dict[str, int], length: int,
              value: Callable[[Row], float | None]) -> tuple[list[float | None], list[bool]]:
    values: list[float | None] = [None] * length
    subset = [False] * length
    for r in members:
        values[index[r["session"]]] = value(r)
        subset[index[r["session"]]] = True
    return values, subset


def _mean(members: Sequence[Row], index: dict[str, int], length: int,
          value: Callable[[Row], float | None], repetitions: int) -> dict[str, Any]:
    values, subset = _sequence(members, index, length, value)
    return asdict(block_mean(values, subset=subset, repetitions=repetitions))


def by_thirds(members: Sequence[Row], index: dict[str, int], length: int, key: str,
              repetitions: int) -> dict[str, Any]:
    """Mean result per third of `key`, cut on `key` alone."""
    known = [r for r in members if r[key] is not None]
    if len(known) < 3:
        return {}
    cuts = thirds([r[key] for r in known])
    out: dict[str, Any] = {"cuts": list(cuts)}
    for name in THIRDS:
        part = [r for r in known if third_of(r[key], cuts) == name]
        # Ties at a cut point go to the lower third, which can leave one empty.
        span = [min(r[key] for r in part), max(r[key] for r in part)] if part else None
        out[name] = {"range": span,
                     **_mean(part, index, length, lambda r: r["result_usd"], repetitions)}
    return out


def _close(i: int) -> Callable[[Row], float | None]:
    return lambda r: r["close_changes_usd"][i]


def report(found: Sequence[Row], index: dict[str, int], length: int,
           repetitions: int = REPETITIONS) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for case in vx.COST_CASES:
        groups: dict[str, Any] = {}
        for name, labels in GROUPS.items():
            members = [r for r in found if r["case"] == case and r["group"] in labels]
            closed = [r for r in members if r["result_usd"] is not None]
            delays = [r for r in closed if r["delay"] is not None]
            late = [r for r in delays if r["delay"]["observations"] >= 2]
            estimate = [r["fill_minus_estimate_usd"] for r in members]
            groups[name] = {
                "trades": len(members),
                "unresolved": len(members) - len(closed),
                "result": _mean(closed, index, length, lambda r: r["result_usd"],
                                repetitions),
                "A1": {c: _mean(members, index, length, _close(i), repetitions)
                       for i, c in enumerate(CLOSES)},
                "A2": {
                    "all": _mean(delays, index, length, lambda r: r["delay"]["cost_usd"],
                                 repetitions),
                    "two_or_more": _mean(late, index, length,
                                         lambda r: r["delay"]["cost_usd"], repetitions),
                    "observations": dict(sorted(Counter(
                        r["delay"]["observations"] for r in delays).items())),
                    "by_trigger": {
                        trig: _mean([r for r in delays if r["trigger"] == trig], index, length,
                                    lambda r: r["delay"]["cost_usd"], repetitions)
                        for trig in sorted({r["trigger"] for r in delays})},
                },
                "A3": by_thirds(closed, index, length, "spy_move_pct", repetitions),
                "A4": {
                    "fill_minus_estimate": _mean(members, index, length,
                                                 lambda r: r["fill_minus_estimate_usd"],
                                                 repetitions),
                    "fill_above_estimate": sum(1 for x in estimate if x > 0),
                    "by_debit_to_width": by_thirds(closed, index, length, "debit_to_width",
                                                   repetitions),
                },
            }
        out[case] = groups
    return out


def _fmt(m: dict[str, Any]) -> str:
    if m.get("mean") is None:
        return f"n/a (n=0, missing {m.get('missing', 0)})"
    return (f"{m['mean']:+8.2f} [{m['low']:+8.2f}, {m['high']:+8.2f}] (n={m['n']}"
            + (f", missing {m['missing']}" if m["missing"] else "") + ")")


def render(rep: dict[str, Any], cases: Sequence[str] = ("central",)) -> str:
    lines = ["Setup and exit study, Part A: decomposition of the Part 2 trades", ""]
    for case in cases:
        for name, g in rep[case].items():
            lines.append(f"{case}, {name}: {g['trades']} trades, unresolved {g['unresolved']}")
            lines.append(f"  result per spread       {_fmt(g['result'])}")
            for c, m in g["A1"].items():
                lines.append(f"  A1 change at {c}        {_fmt(m)}")
            a2 = g["A2"]
            lines.append(f"  A2 cost of waiting, all {_fmt(a2['all'])}")
            lines.append(f"  A2 waited 2+ obs        {_fmt(a2['two_or_more'])}")
            lines.append(f"     observations waited {a2['observations']}")
            for trig, m in a2["by_trigger"].items():
                lines.append(f"     {trig:22} {_fmt(m)}")
            for label, block in (("A3 by SPY 3-session move %", g["A3"]),
                                 ("A4 by debit / width", g["A4"]["by_debit_to_width"])):
                if not block:
                    continue
                lines.append(f"  {label}, cuts {block['cuts'][0]:+.3f}, {block['cuts'][1]:+.3f}")
                for third in THIRDS:
                    b = block[third]
                    span = ("(empty)" if b["range"] is None
                            else f"{b['range'][0]:+7.3f} to {b['range'][1]:+7.3f}")
                    lines.append(f"     {third:14} {span:18}  {_fmt(b)}")
            a4 = g["A4"]
            lines.append(f"  A4 fill minus estimate  {_fmt(a4['fill_minus_estimate'])}; "
                         f"fill above estimate {a4['fill_above_estimate']} of {g['trades']}")
            lines.append("")
    return "\n".join(lines)


def load(cache: Path = CACHE) -> tuple[list[Row], dict[str, int], int]:
    from .veto_study import load_bars

    done, index, length, entries = vx.load(cache)
    spy, _ = load_bars(cache / "daily_bars.json")
    calendar = TradingCalendar.from_payload(json.loads((cache / "calendar.json").read_text()))
    paths = {p.stem: json.loads(p.read_text()) for p in (cache / "paths").glob("*.json")}
    print(f"Part 2 trades digest: {vx.digest(done)}")
    return rows(entries, done, paths, calendar, spy), index, length


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--rows", type=Path, help="write every row as JSON here")
    parser.add_argument("--json", type=Path, help="write the report as JSON here")
    parser.add_argument("--all-cases", action="store_true", help="render every cost case")
    args = parser.parse_args(argv)
    found, index, length = load(args.cache)
    rep = report(found, index, length)
    if args.rows:
        args.rows.write_text(json.dumps(found, indent=1))
    if args.json:
        args.json.write_text(json.dumps(rep, indent=1))
    print(render(rep, tuple(vx.COST_CASES) if args.all_cases else ("central",)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
