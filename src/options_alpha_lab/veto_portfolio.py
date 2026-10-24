"""Step 6 of the breadth veto backtest: two chronological one-position portfolios.

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, section 5.5
(second analysis) and Step 6 (`VBT-203`). Protocol: options_alpha_veto_
backtest_protocol_v0_1.md, section 6 and the Step 6 note of 23 October 2026.

The baseline arm may enter only on Permitted sessions; the other arm also on
Breadth-vetoed ones. Everything else is shared: the Step 4 entries, the Step 5
trades of each cost case, $100,000 of starting equity, a risk budget of 0.75%
of the running equity, one position at a time and re-entry no earlier than the
session after an exit fill. Paths and per-year results only: a block bootstrap
of trades is not valid for a path-dependent portfolio (protocol section 8).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from . import veto_entries as ve
from . import veto_exits as vx
from . import veto_replay as vr
from .calendar import MARKET_TZ
from .components import RISK_FRACTION_OF_EQUITY

START_EQUITY = Decimal("100000")
BASELINE = "baseline"
WITHOUT_VETO = "without the breadth veto"
ARMS = {BASELINE: (vr.PERMITTED,), WITHOUT_VETO: (vr.PERMITTED, vr.BREADTH_VETOED)}

CAPACITY = "capacity in use"
OVER_BUDGET = "estimated max loss above 0.75% of running equity"
TRADED = "traded"


@dataclass
class Path:
    arm: str
    case: str
    equity: Decimal = START_EQUITY
    peak: Decimal = START_EQUITY
    worst_fall: Decimal = Decimal("0")
    #: Session, group, what happened, result, equity after.
    events: list[tuple[str, str, str, float | None, str]] = field(default_factory=list)
    by_year: dict[str, Decimal] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)


def exit_session(trade: vx.Trade) -> date | None:
    if trade.exited_at is None:
        return None
    return datetime.fromisoformat(trade.exited_at).astimezone(MARKET_TZ).date()


def run(arm: str, case: str, entries: Sequence[ve.Entry],
        trades: dict[tuple[str, str], vx.Trade], window_end: dict[str, date]) -> Path:
    path = Path(arm, case)
    allowed = ARMS[arm]
    busy_until: date | None = None
    for entry in sorted(entries, key=lambda e: e.session):
        if entry.group not in allowed:
            continue
        day = date.fromisoformat(entry.session)
        if busy_until is not None and day <= busy_until:
            path.events.append((entry.session, entry.group, CAPACITY, None, str(path.equity)))
            continue
        if entry.status != ve.ENTERED:
            path.events.append((entry.session, entry.group, entry.status, None,
                                str(path.equity)))
            continue
        budget = (path.equity * RISK_FRACTION_OF_EQUITY).quantize(Decimal("0.01"))
        assert entry.estimated_debit is not None
        if Decimal(entry.estimated_debit) * vx.MULTIPLIER > budget:
            path.events.append((entry.session, entry.group, OVER_BUDGET, None,
                                str(path.equity)))
            continue
        trade = trades[(entry.session, case)]
        if trade.status == vx.CLOSED and trade.result_usd is not None:
            result = Decimal(repr(trade.result_usd))
            ended = exit_session(trade)
            assert ended is not None
        else:
            # Protocol section 11, Step 6: the whole debit, and the position held
            # to the end of its window, so a missing exit frees nothing early.
            result = -Decimal(trade.entry_debit) * vx.MULTIPLIER
            ended = window_end[entry.session]
            path.unresolved.append(entry.session)
        busy_until = ended
        path.equity += result
        path.peak = max(path.peak, path.equity)
        path.worst_fall = max(path.worst_fall, path.peak - path.equity)
        year = entry.session[:4]
        path.by_year[year] = path.by_year.get(year, Decimal("0")) + result
        path.events.append((entry.session, entry.group, TRADED, float(result), str(path.equity)))
    return path


def window_ends(entries: Sequence[ve.Entry], sessions: Sequence[date]) -> dict[str, date]:
    """Each entry's last downloaded session (the export's five-session window)."""
    out: dict[str, date] = {}
    for e in entries:
        day = date.fromisoformat(e.session)
        at = sessions.index(day)
        out[e.session] = sessions[min(at + 4, len(sessions) - 1)]
    return out


def summarize(path: Path) -> dict[str, Any]:
    traded = [ev for ev in path.events if ev[2] == TRADED]
    results = [ev[3] for ev in traded if ev[3] is not None]
    return {
        "arm": path.arm, "case": path.case,
        "trades": len(traded),
        "from_vetoed_sessions": sum(1 for ev in traded if ev[1] == vr.BREADTH_VETOED),
        "wins": sum(1 for r in results if r > 0),
        "total_usd": float(path.equity - START_EQUITY),
        "final_equity": float(path.equity),
        "largest_fall_usd": float(path.worst_fall),
        "by_year_usd": {y: float(v) for y, v in sorted(path.by_year.items())},
        "skipped": dict(Counter(ev[2] for ev in path.events if ev[2] != TRADED)),
        "unresolved": path.unresolved,
    }


def portfolios(entries: Sequence[ve.Entry], done: Sequence[vx.Trade],
               sessions: Sequence[date]) -> list[dict[str, Any]]:
    trades = {(t.session, t.case): t for t in done}
    ends = window_ends(entries, sessions)
    return [summarize(run(arm, case, entries, trades, ends))
            for case in vx.COST_CASES for arm in ARMS]


def render(found: Sequence[dict[str, Any]]) -> str:
    lines = ["Breadth veto, Step 6: one-position portfolios, $100,000 start", ""]
    for p in found:
        lines.append(
            f"{p['case']:12} {p['arm']:26} trades {p['trades']:3} "
            f"(from vetoed {p['from_vetoed_sessions']:3}), wins {p['wins']:3}, total "
            f"{p['total_usd']:+10.2f}, largest fall {p['largest_fall_usd']:8.2f}, by year "
            f"{ {y: round(v, 2) for y, v in p['by_year_usd'].items()} }, unresolved "
            f"{len(p['unresolved'])}")
        lines.append(f"{'':40}skipped {p['skipped']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse
    import json
    from pathlib import Path as FilePath

    from .veto_study import load_bars

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=FilePath, default=vx.CACHE)
    parser.add_argument("--json", type=FilePath, help="write the portfolios as JSON here")
    args = parser.parse_args(argv)
    done, _, _, entries = vx.load(args.cache)
    spy, _ = load_bars(args.cache / "daily_bars.json")
    found = portfolios(entries, done, [bar.session for bar in spy])
    if args.json:
        args.json.write_text(json.dumps(found, indent=1))
    print(render(found))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

