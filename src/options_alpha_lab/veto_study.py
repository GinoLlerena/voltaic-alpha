"""Is there enough history to study the breadth veto at all?

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, section 4.0
(`VBT-100`). The option-backed backtest is the expensive part of that plan, and
this runs before any of it is built.

It counts two things for each completed session and nothing else: whether a
bullish structure signal reaches the qualifying strength, and whether opposing
breadth reaches the veto line. Implied volatility is not supplied.

That makes the count an **upper bound**, which is what gives it its use.
Supplying volatility later can only remove sessions: one may lose its
confirmation, or gain a stressed-volatility veto. It cannot add a qualifying
one. `test_veto_study.py` holds that against the shipped classifier. So a count
too small here means the full study is too small as well, and the work stops.

It computes **no outcomes**: no forward price, no return. Nothing in it can be
tuned towards a result, which is why it may run before the backtest's numeric
protocol is frozen. Its groups are not "permitted" and "vetoed": those need the
whole rule, and this applies two of its three conditions.

The signals come from `evidence.build_signals` on the worker's own bounded
window, never from a copy of the arithmetic.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .architecture.contracts import Direction, Signal, SignalFamily
from .components import CONTRADICTION_VETO_STRENGTH, MIN_STRUCTURE_STRENGTH
from .evidence import MIN_BARS_REQUIRED, Bar, build_signals

BARS_FIXTURE = Path("fixtures/h0/sensitivity_bars.json")
#: What the worker asks the provider for (`ReadOnlyAlpacaClient.daily_bars`).
LOOKBACK_DAYS = 400
#: Members this many sessions apart or more belong to different clusters. Eight
#: vetoed sessions in a row are one episode, not eight observations.
CLUSTER_GAP_SESSIONS = 3
#: The proposed screen (plan section 4.0, decision 10). Not a power calculation.
MIN_SESSIONS = 30
MIN_CLUSTERS = 10

BELOW_LINE = "bullish structure, opposing breadth below the line"
AT_OR_ABOVE_LINE = "bullish structure, opposing breadth at or above the line"
GROUPS = (BELOW_LINE, AT_OR_ABOVE_LINE)


@dataclass(frozen=True)
class Row:
    #: The last completed session. The worker would decide on the next one.
    completed: date
    #: Position in the series, so clusters are measured in sessions, not days.
    index: int
    signals: tuple[Signal, ...]

    def _strongest(self, family: SignalFamily, direction: Direction) -> Decimal | None:
        found = [
            s.strength for s in self.signals if s.family is family and s.direction is direction
        ]
        return max(found) if found else None

    @property
    def bullish_structure(self) -> bool:
        strength = self._strongest(SignalFamily.STRUCTURE, Direction.BULLISH)
        return strength is not None and strength >= MIN_STRUCTURE_STRENGTH

    @property
    def bearish_structure(self) -> bool:
        strength = self._strongest(SignalFamily.STRUCTURE, Direction.BEARISH)
        return strength is not None and strength >= MIN_STRUCTURE_STRENGTH

    @property
    def opposing_breadth(self) -> Decimal | None:
        return self._strongest(SignalFamily.PARTICIPATION, Direction.BEARISH)

    @property
    def other_veto(self) -> bool:
        """An opposing signal at the veto line from a family other than breadth."""
        return any(
            s.direction is Direction.BEARISH
            and s.family is not SignalFamily.PARTICIPATION
            and s.strength >= CONTRADICTION_VETO_STRENGTH
            for s in self.signals
        )

    @property
    def group(self) -> str | None:
        if not self.bullish_structure:
            return None
        breadth = self.opposing_breadth
        if breadth is not None and breadth >= CONTRADICTION_VETO_STRENGTH:
            return AT_OR_ABOVE_LINE
        return BELOW_LINE


def parse_bars(rows: list[dict[str, Any]]) -> list[Bar]:
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


def load_bars(path: Path = BARS_FIXTURE) -> tuple[list[Bar], list[Bar]]:
    symbols = json.loads(path.read_text())["symbols"]
    return parse_bars(symbols["SPY"]["bars"]), parse_bars(symbols["RSP"]["bars"])


def rows(spy: list[Bar], rsp: list[Bar]) -> Iterator[Row]:
    """One row per completed session, from the window the worker would have had.

    Both series are cut at the same session and the same 400-day start, because
    the worker fetches both with the same call at the same moment. Nothing after
    the cut is passed in: `build_signals` takes `as_of` as a label and does not
    itself drop later bars.
    """
    for index, last in enumerate(spy):
        first = last.session - timedelta(days=LOOKBACK_DAYS)
        window = [bar for bar in spy[: index + 1] if bar.session > first]
        if len(window) < MIN_BARS_REQUIRED:
            continue
        breadth = [bar for bar in rsp if first < bar.session <= last.session]
        as_of = datetime.combine(last.session + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        yield Row(last.session, index, tuple(build_signals(window, None, as_of, breadth)))


#: Needs implied volatility, which this count does not supply.
NOT_REPLAYED = "sig-volatility-regime"


def disagreements(measured: list[Row], stored: dict[str, Any]) -> list[str]:
    """Where the replay differs from the signals the worker stored.

    `stored` is `veto_export.py signals`: per decision session, each distinct
    signal the worker recorded. The worker decides on the session after the last
    completed bar, so a stored session is compared with the row before it. An
    empty list means every stored session was reproduced exactly; a session the
    bars do not reach is a disagreement, not a skip.
    """
    by_day: dict[str, set[tuple[str, str, Decimal]]] = {day: set() for day in stored["snapshots"]}
    for signal in stored["signals"]:
        if signal["signal_id"] != NOT_REPLAYED:
            by_day[signal["day"]].add(
                (signal["signal_id"], signal["direction"], Decimal(signal["strength"]))
            )
    problems: list[str] = []
    for day, expected in sorted(by_day.items()):
        earlier = [row for row in measured if row.completed < date.fromisoformat(day)]
        if not earlier:
            problems.append(f"{day}: no completed session before it in the bars")
            continue
        replayed = {(s.signal_id, s.direction.value, s.strength) for s in earlier[-1].signals}
        if replayed != expected:
            problems.append(
                f"{day}: stored {sorted(expected)} but replayed {sorted(replayed)} "
                f"from the session completed {earlier[-1].completed}"
            )
    return problems


def clusters(indexes: list[int]) -> list[list[int]]:
    """Runs of members, split wherever `CLUSTER_GAP_SESSIONS` or more separate them."""
    out: list[list[int]] = []
    for index in sorted(indexes):
        if out and index - out[-1][-1] < CLUSTER_GAP_SESSIONS:
            out[-1].append(index)
        else:
            out.append([index])
    return out


def longest_run(indexes: list[int]) -> int:
    """The longest stretch of consecutive sessions."""
    best = run = 0
    previous: int | None = None
    for index in sorted(indexes):
        run = run + 1 if previous is not None and index == previous + 1 else 1
        best = max(best, run)
        previous = index
    return best


def run(spy: list[Bar], rsp: list[Bar], *, since: date | None = None) -> dict[str, Any]:
    """The count. `since` limits it to the period the option data covers."""
    measured = [row for row in rows(spy, rsp) if since is None or row.completed >= since]
    groups: dict[str, Any] = {}
    for name in GROUPS:
        members = [row for row in measured if row.group == name]
        indexes = [row.index for row in members]
        per_year: dict[str, int] = {}
        for row in members:
            per_year[str(row.completed.year)] = per_year.get(str(row.completed.year), 0) + 1
        groups[name] = {
            "sessions": len(members),
            "clusters": len(clusters(indexes)),
            "longest_run": longest_run(indexes),
            "with_another_veto": sum(1 for row in members if row.other_veto),
            "per_year": per_year,
        }
    passes = all(
        g["sessions"] >= MIN_SESSIONS and g["clusters"] >= MIN_CLUSTERS for g in groups.values()
    )
    return {
        "first": str(measured[0].completed) if measured else None,
        "last": str(measured[-1].completed) if measured else None,
        "sessions": len(measured),
        "bullish_structure": sum(1 for row in measured if row.bullish_structure),
        "bearish_structure": sum(1 for row in measured if row.bearish_structure),
        "groups": groups,
        "screen": {"min_sessions": MIN_SESSIONS, "min_clusters": MIN_CLUSTERS, "passes": passes},
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "Breadth veto: feasibility count (an upper bound; no outcomes are computed)",
        "",
        f"Completed sessions measured: {report['sessions']} "
        f"({report['first']} to {report['last']})",
        f"Bullish structure at or above {MIN_STRUCTURE_STRENGTH}: {report['bullish_structure']}",
        f"Bearish structure (out of scope): {report['bearish_structure']}",
        "",
    ]
    for name, group in report["groups"].items():
        years = ", ".join(f"{year}: {n}" for year, n in sorted(group["per_year"].items()))
        lines += [
            name,
            f"  sessions {group['sessions']}, clusters {group['clusters']}, "
            f"longest run {group['longest_run']}, "
            f"with another veto {group['with_another_veto']}",
            f"  per year: {years or 'none'}",
        ]
    screen = report["screen"]
    lines += [
        "",
        f"Screen (at least {screen['min_sessions']} sessions and "
        f"{screen['min_clusters']} clusters in each group): "
        f"{'PASSES' if screen['passes'] else 'FAILS'}",
        "Passing does not mean the full study will be conclusive.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=BARS_FIXTURE,
                        help="SPY and RSP daily bars, in the fixture's format")
    parser.add_argument("--since", type=date.fromisoformat, default=None,
                        help="count completed sessions from this date")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--reference", type=Path, default=None,
                        help="stored signals to hold the replay to (veto_export.py signals)")
    args = parser.parse_args(argv)

    spy, rsp = load_bars(args.bars)
    if args.reference is not None:
        stored = json.loads(args.reference.read_text())
        problems = disagreements(list(rows(spy, rsp)), stored)
        if problems:
            print("The replay does not reproduce the stored signals; the count is void.")
            print("\n".join(problems))
            return 1
        print(f"Replay reproduces the stored signals on all {len(stored['snapshots'])} "
              "reference sessions.\n")
    report = run(spy, rsp, since=args.since)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
