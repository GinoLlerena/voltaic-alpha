"""Step 5 of the breadth veto backtest: each entered spread's exit, per cost case.

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, sections 5.2,
5.3 and 5.5 and Step 5 (`VBT-202`). Protocol: options_alpha_veto_backtest_
protocol_v0_1.md, section 5 and the Step 5 note of 23 October 2026 in section 11.

Each Step 4 entry is stepped through the 5-minute bars of its two legs after
the 10:05 fill. At every observation the shipped `evaluate_exit` decides, from
the filled debit, the conservative value, days to expiry, the last completed
SPY close and completed sessions counted by the shipped `TradingCalendar`. The
exit fills at the next bar in which both legs traded. Each cost case runs on
its own from the entry, because its debit moves the stop and the target.

This is the first half of Part 2: independent setups, overlaps allowed. Their
sum is not a strategy's equity curve.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from . import veto_entries as ve
from . import veto_replay as vr
from .architecture.contracts import Direction, PriceSource, TypedInvalidation
from .calendar import MARKET_TZ, TradingCalendar
from .exits import ExitInputs, evaluate_exit
from .veto_outcomes import BLOCK_LENGTH, SENSITIVITY_BLOCKS, Contrast, block_contrast

CACHE = ve.CACHE
#: Protocol section 5: friction per spread share, each way.
COST_CASES = {"optimistic": Decimal("0.00"), "central": Decimal("0.05"),
              "pessimistic": Decimal("0.10")}
#: Protocol section 8.
NO_WORSE_MARGIN = 15.0
MULTIPLIER = Decimal("100")
BAR = timedelta(minutes=5)
MAX_AGE = timedelta(minutes=15)
MAX_LEG_GAP = ve.MAX_LEG_GAP
FILL_AT = time(10, 5)
#: An observation at a bar ending on the close is the last one *before* it: the
#: worker manages nothing once the market has closed, so that session's close
#: counts from the next session's first observation (protocol section 5).
BEFORE = timedelta(microseconds=1)

CLOSED = "closed"
NO_EXIT_FILL = "unresolved: triggered, no later bar with both legs traded"
NO_TRIGGER = "unresolved: no trigger inside the downloaded window"
NO_PATH = "unresolved: no exit path downloaded"


@dataclass(frozen=True)
class Trade:
    session: str
    group: str
    case: str
    entry_debit: str
    width: str
    status: str
    trigger: str | None = None
    triggered_at: str | None = None
    exited_at: str | None = None
    exit_value: str | None = None
    result_usd: float | None = None
    sessions_held: int | None = None
    #: Observations at which the spread value could not be measured.
    unmeasured: int = 0
    #: A trade-derived value outside 0 to the width, kept as computed.
    flags: tuple[str, ...] = ()


Bars = dict[tuple[str, str], tuple[Decimal, int]]


def leg_bars(rows: Sequence[Sequence[Any]]) -> Bars:
    """(New York date, bar opening time) to (volume-weighted price, volume)."""
    return {(r[0], r[1]): (Decimal(repr(r[2])), int(r[3])) for r in rows}


def at(day: date, hhmm: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), tzinfo=MARKET_TZ)


def key(opened: datetime) -> tuple[str, str]:
    """A bar's key: its New York date and opening time, as the download stores it."""
    local = opened.astimezone(MARKET_TZ)
    return local.date().isoformat(), local.strftime("%H:%M")


def observations(calendar: TradingCalendar, entry: date, last: date) -> list[datetime]:
    """Ends of the regular-session bars after the fill, in order (protocol section 11)."""
    out: list[datetime] = []
    day = entry
    while day <= last:
        session = calendar.session_for(datetime.combine(day, time(12), tzinfo=MARKET_TZ))
        if session is not None:
            opened = (at(day, FILL_AT.strftime("%H:%M")) if day == entry
                      else session.open_at.astimezone(MARKET_TZ))
            while opened + BAR <= session.close_at:
                out.append(opened + BAR)
                opened += BAR
        day += timedelta(days=1)
    return out


def _latest(bars: Bars, moment: datetime) -> tuple[datetime, Decimal] | None:
    """The leg's newest trade bar ending at or before `moment`, at most 15 minutes old."""
    end = moment
    while moment - end <= MAX_AGE:
        opened = end - BAR
        found = bars.get(key(opened))
        if found is not None and found[1] >= 1:
            return end, found[0]
        end -= BAR
    return None


def value_at(long: Bars, short: Bars, moment: datetime) -> Decimal | None:
    """Long minus short from bars within the age and leg-gap limits, before friction."""
    a, b = _latest(long, moment), _latest(short, moment)
    if a is None or b is None or abs(a[0] - b[0]) > MAX_LEG_GAP:
        return None
    return a[1] - b[1]


def traded_in(long: Bars, short: Bars, moment: datetime) -> Decimal | None:
    """Long minus short when both legs traded in the bar ending at `moment`."""
    a, b = long.get(key(moment - BAR)), short.get(key(moment - BAR))
    if a is None or b is None or a[1] < 1 or b[1] < 1:
        return None
    return a[0] - b[0]


def simulate(entry: ve.Entry, case: str, path: dict[str, Any] | None,
             calendar: TradingCalendar, closes: dict[date, Decimal]) -> Trade:
    assert entry.fill_reference and entry.width and entry.expiration and entry.invalidation
    friction = COST_CASES[case]
    debit = Decimal(entry.fill_reference) + friction
    width = Decimal(entry.width)
    base = Trade(entry.session, entry.group, case, str(debit), entry.width, NO_PATH)
    flags = []
    if not Decimal("0") < debit < width:
        flags.append("entry debit outside 0 to the width")
    if path is None:
        return _with(base, flags=tuple(flags))
    assert entry.long_symbol and entry.short_symbol
    long = leg_bars(path["legs"][entry.long_symbol])
    short = leg_bars(path["legs"][entry.short_symbol])
    rule = TypedInvalidation(Decimal(entry.invalidation), Direction.BULLISH,
                             PriceSource.COMPLETED_DAILY_CLOSE)
    expiry = date.fromisoformat(entry.expiration)
    day = date.fromisoformat(entry.session)
    filled = at(day, FILL_AT.strftime("%H:%M"))
    sessions = sorted(closes)
    unmeasured = 0
    moments = observations(calendar, day, date.fromisoformat(path["last"]))
    for i, moment in enumerate(moments):
        raw = value_at(long, short, moment)
        if raw is None:
            unmeasured += 1
        current = None if raw is None else raw - friction
        today = moment.astimezone(MARKET_TZ).date()
        previous = sessions[bisect_left(sessions, today) - 1]
        decision = evaluate_exit(ExitInputs(
            direction=Direction.BULLISH, entry_debit=debit, width=width, quantity=1,
            dte=(expiry - today).days, underlying_price=closes[previous],
            underlying_source=PriceSource.COMPLETED_DAILY_CLOSE, invalidation=rule,
            current_value=current, as_of=today,
            sessions_elapsed=calendar.completed_sessions_between(filled, moment - BEFORE),
        ))
        if not decision.should_close:
            continue
        held = calendar.completed_sessions_between(filled, moment - BEFORE)
        for later in moments[i + 1:]:
            price = traded_in(long, short, later)
            if price is None:
                continue
            value = price - friction
            if not Decimal("0") <= price <= width:
                flags.append("exit value outside 0 to the width")
            return _with(base, status=CLOSED, trigger=decision.trigger.value,
                         triggered_at=moment.isoformat(), exited_at=later.isoformat(),
                         exit_value=str(value),
                         result_usd=float((value - debit) * MULTIPLIER),
                         sessions_held=held, unmeasured=unmeasured, flags=tuple(flags))
        return _with(base, status=NO_EXIT_FILL, trigger=decision.trigger.value,
                     triggered_at=moment.isoformat(), sessions_held=held,
                     unmeasured=unmeasured, flags=tuple(flags))
    return _with(base, status=NO_TRIGGER, unmeasured=unmeasured, flags=tuple(flags))


def _with(trade: Trade, **changes: Any) -> Trade:
    return Trade(**{**asdict(trade), **changes})


def trades(found: Sequence[ve.Entry], paths: dict[str, dict[str, Any]],
           calendar: TradingCalendar, closes: dict[date, Decimal]) -> list[Trade]:
    out: list[Trade] = []
    for entry in found:
        if entry.status != ve.ENTERED:
            continue
        for case in COST_CASES:
            out.append(simulate(entry, case, paths.get(entry.session), calendar, closes))
    return out


def contrasts(done: Sequence[Trade], index: dict[str, int], length: int, case: str,
              block: int = BLOCK_LENGTH, repetitions: int | None = None) -> Contrast:
    """Breadth-vetoed minus Permitted, mean result in USD, over the session sequence.

    `block_contrast` returns Permitted minus Vetoed; its interval is negated
    here, so the lower end is the one the no-worse test reads.
    """
    group: list[str | None] = [None] * length
    values: list[float | None] = [None] * length
    for t in done:
        if t.case != case:
            continue
        group[index[t.session]] = t.group
        values[index[t.session]] = t.result_usd if t.status == CLOSED else None
    kwargs = {} if repetitions is None else {"repetitions": repetitions}
    c = block_contrast(f"mean result, USD, {case}", group, values, block, **kwargs)
    return Contrast(
        metric=c.metric, block_length=c.block_length,
        permitted_n=c.permitted_n, vetoed_n=c.vetoed_n,
        permitted_excluded=c.permitted_excluded, vetoed_excluded=c.vetoed_excluded,
        permitted_mean=c.permitted_mean, vetoed_mean=c.vetoed_mean,
        difference=None if c.difference is None else -c.difference,
        low=None if c.high is None else -c.high,
        high=None if c.low is None else -c.low,
        empty_replicates=c.empty_replicates,
    )


def describe(results: Sequence[float]) -> dict[str, Any]:
    if not results:
        return {"trades": 0}
    return {"trades": len(results), "win_rate": sum(r > 0 for r in results) / len(results),
            "mean": sum(results) / len(results), "median": median(results),
            "worst": min(results), "best": max(results), "total": sum(results)}


def report(done: Sequence[Trade], index: dict[str, int], length: int,
           repetitions: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"cases": {}, "trades_digest": digest(done)}
    for case in COST_CASES:
        mine = [t for t in done if t.case == case]
        groups = {}
        for g in (vr.PERMITTED, vr.BREADTH_VETOED):
            members = [t for t in mine if t.group == g]
            closed = [t.result_usd for t in members if t.status == CLOSED
                      and t.result_usd is not None]
            unresolved = [t for t in members if t.status != CLOSED]
            groups[g] = {
                **describe(closed),
                "status": dict(Counter(t.status for t in members)),
                "triggers": dict(Counter(t.trigger for t in members if t.status == CLOSED)),
                "unresolved_bound_usd": -sum(float(Decimal(t.entry_debit) * MULTIPLIER)
                                             for t in unresolved),
                "flagged": sum(1 for t in members if t.flags),
                "by_year": {year: describe([t.result_usd for t in members
                                            if t.session.startswith(year)
                                            and t.status == CLOSED
                                            and t.result_usd is not None])
                            for year in sorted({t.session[:4] for t in members})},
            }
        main = contrasts(mine, index, length, case, repetitions=repetitions)
        out["cases"][case] = {
            "groups": groups,
            "contrast": asdict(main),
            "sensitivity": [asdict(contrasts(mine, index, length, case, block=b,
                                             repetitions=repetitions))
                            for b in SENSITIVITY_BLOCKS],
            "no_worse": main.low is not None and main.low > -NO_WORSE_MARGIN,
        }
    out["no_worse_in_all_cases"] = all(c["no_worse"] for c in out["cases"].values())
    return out


def digest(done: Sequence[Trade]) -> str:
    payload = json.dumps([asdict(t) for t in done], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def render(rep: dict[str, Any]) -> str:
    lines = ["Breadth veto, Step 5: independent spread results per cost case", ""]
    for case, info in rep["cases"].items():
        lines.append(f"{case}:")
        for g, s in info["groups"].items():
            if s["trades"]:
                lines.append(f"  {g}: {s['trades']} closed, win {s['win_rate']:.1%}, mean "
                             f"{_fmt(s['mean'])}, median {_fmt(s['median'])}, worst "
                             f"{_fmt(s['worst'])}, total {_fmt(s['total'])}")
            lines.append(f"    status {s['status']}; triggers {s['triggers']}; "
                         f"unresolved bound {_fmt(s['unresolved_bound_usd'])}; "
                         f"flagged {s['flagged']}")
        c = info["contrast"]
        lines.append(f"  Vetoed - Permitted {_fmt(c['difference'])} "
                     f"[{_fmt(c['low'])}, {_fmt(c['high'])}] (block {c['block_length']}); "
                     f"no worse than -${NO_WORSE_MARGIN:.0f}: {info['no_worse']}")
        for s in info["sensitivity"]:
            lines.append(f"    block {s['block_length']}: [{_fmt(s['low'])}, {_fmt(s['high'])}]")
        lines.append("")
    lines.append(f"No worse in all three cases: {rep['no_worse_in_all_cases']}")
    lines.append(f"Trades digest: {rep['trades_digest']}")
    return "\n".join(lines)


def load(cache: Path = CACHE) -> tuple[list[Trade], dict[str, int], int, list[ve.Entry]]:
    from .veto_study import load_bars

    found, facts = ve.load(cache)
    spy, _ = load_bars(cache / "daily_bars.json")
    closes = {bar.session: bar.close for bar in spy}
    calendar = TradingCalendar.from_payload(json.loads((cache / "calendar.json").read_text()))
    paths = {p.stem: json.loads(p.read_text()) for p in (cache / "paths").glob("*.json")}
    index: dict[str, int] = facts["index"]
    return trades(found, paths, calendar, closes), index, len(index), found


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--trades", type=Path, help="write every trade as JSON here")
    parser.add_argument("--json", type=Path, help="write the report as JSON here")
    args = parser.parse_args(argv)
    done, index, length, _ = load(args.cache)
    rep = report(done, index, length)
    if args.trades:
        args.trades.write_text(json.dumps([asdict(t) for t in done], indent=1))
    if args.json:
        args.json.write_text(json.dumps(rep, indent=1))
    print(render(rep))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
