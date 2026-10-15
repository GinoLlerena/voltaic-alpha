"""Step 2 of the breadth veto backtest: replay the signals and attribute each veto.

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, section 4.2
and Step 2 (`VBT-102`). Protocol: options_alpha_veto_backtest_protocol_v0_1.md.

For every downloaded session this rebuilds what the worker would have seen at
10:00 New York - the completed daily bars of its 400-day window, RSP's over the
same window, and the at-the-money implied volatility reconstructed from traded
option prices - and passes them through the shipped `build_signals` and
`DeterministicSetupClassifier`. Nothing here restates their arithmetic.

Each session gets one bucket, in the plan's order of prerequisites: input
usability, study direction, structure and confirmation, then veto attribution.
A breadth veto is attributed by removing only the opposing participation signal
from the session's signals and classifying again; every other signal and
threshold is kept.

It computes **no outcomes**: no forward price is read. The daily bars passed to
each session end at the last completed session before it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import veto_pricing as pricing
from . import veto_reconstruction as recon
from .architecture.contracts import (
    AccountSnapshot,
    DecisionSnapshot,
    Direction,
    PriceSource,
    SetupCandidate,
    Signal,
    SignalFamily,
)
from .components import (
    CONTRADICTION_VETO_STRENGTH,
    MIN_STRUCTURE_STRENGTH,
    DeterministicSetupClassifier,
)
from .evidence import MIN_BARS_REQUIRED, Bar, build_signals
from .veto_study import LOOKBACK_DAYS, MIN_CLUSTERS, MIN_SESSIONS, clusters, longest_run

CACHE = recon.CACHE
NEW_YORK = ZoneInfo("America/New_York")
#: Protocol section 1.
DECISION_TIME = time(10, 0)
#: The daily bars were requested from this day (manifest, `daily_bars.json`), so
#: the provider has confirmed there is no session in the cache's range before
#: its first bar. A window reaching back before it would be missing sessions.
COVERED_FROM = date(2023, 1, 1)

UNMEASURABLE = "Unmeasurable"
OUT_OF_SCOPE = "Out of scope"
NO_SETUP = "No setup"
PERMITTED = "Permitted"
BREADTH_VETOED = "Breadth-vetoed"
OTHER_VETOES = "Other/multiple vetoes"
BUCKETS = (UNMEASURABLE, OUT_OF_SCOPE, NO_SETUP, PERMITTED, BREADTH_VETOED, OTHER_VETOES)
#: Shown side by side for context only (plan section 4.3); never a rule change.
CONTEXT_LINES = (Decimal("0.60"), Decimal("0.70"), Decimal("0.80"))

_CLASSIFIER = DeterministicSetupClassifier()
_GAP = re.compile(r"moved ([+-]\d+\.\d+) against")


@dataclass(frozen=True)
class Attribution:
    bucket: str
    reason: str
    #: The level a qualifying setup would be invalidated at, from the baseline
    #: or, for a breadth veto, from its qualifying counterfactual.
    invalidation: str | None = None


@dataclass(frozen=True)
class Row:
    session: str
    #: The last completed session the decision could read.
    completed: str | None
    #: Position among the replayed sessions, so runs are measured in sessions
    #: and an unmeasurable session interrupts a run instead of being bridged.
    index: int
    implied_volatility: float | None
    regime: str | None
    signals: tuple[tuple[str, str, str], ...]
    opposing_breadth: str | None
    breadth_gap: str | None
    bucket: str
    reason: str
    invalidation: str | None


def _snapshot(signals: tuple[Signal, ...], price: Decimal, session: date | None,
              as_of: datetime) -> DecisionSnapshot:
    """The minimum the classifier reads: signals and the completed close."""
    return DecisionSnapshot(
        snapshot_id=f"veto-replay-{as_of:%Y%m%d}",
        as_of=as_of,
        symbol="SPY",
        underlying_price=price,
        account=AccountSnapshot("research", as_of, Decimal("1"), Decimal("0"), True),
        signals=signals,
        underlying_source=PriceSource.COMPLETED_DAILY_CLOSE,
        underlying_session=session,
    )


def _level(setup: SetupCandidate) -> str | None:
    return str(setup.invalidation.level) if setup.invalidation is not None else None


def _opposing(signals: tuple[Signal, ...], direction: Direction) -> list[Signal]:
    return [
        s for s in signals
        if s.direction not in (direction, Direction.NEUTRAL)
        and s.strength >= CONTRADICTION_VETO_STRENGTH
    ]


def attribute(signals: tuple[Signal, ...], price: Decimal, session: date | None,
              as_of: datetime) -> Attribution:
    """Section 4.2, from structure onwards. Input usability is the caller's."""
    structure = [s for s in signals if s.family is SignalFamily.STRUCTURE
                 and s.direction is not Direction.NEUTRAL]
    if not structure:
        return Attribution(NO_SETUP, "no structure signal")
    anchor = max(structure, key=lambda s: (s.strength, s.signal_id))
    if anchor.strength < MIN_STRUCTURE_STRENGTH:
        return Attribution(NO_SETUP, f"structure {anchor.strength} below {MIN_STRUCTURE_STRENGTH}")
    if anchor.direction is not Direction.BULLISH:
        return Attribution(OUT_OF_SCOPE, "bearish structure")

    baseline = _CLASSIFIER.classify(_snapshot(signals, price, session, as_of))
    if baseline is not None:
        return Attribution(PERMITTED, "qualified", _level(baseline))

    opposing = _opposing(signals, anchor.direction)
    if not opposing:
        return Attribution(NO_SETUP, "no confirmation from another family")
    # The counterfactual: the same signals without the opposing breadth only.
    without_breadth = tuple(
        s for s in signals
        if not (s.family is SignalFamily.PARTICIPATION and s in opposing)
    )
    counterfactual = _CLASSIFIER.classify(_snapshot(without_breadth, price, session, as_of))
    if counterfactual is not None:
        return Attribution(BREADTH_VETOED, "qualifies without opposing breadth",
                           _level(counterfactual))
    # Not breadth alone. Does it qualify once every opposing signal is gone?
    without_any = tuple(s for s in signals if s not in opposing)
    if _CLASSIFIER.classify(_snapshot(without_any, price, session, as_of)) is not None:
        families = ", ".join(sorted(s.family.value for s in opposing))
        return Attribution(OTHER_VETOES, f"vetoed by {families}")
    return Attribution(NO_SETUP, "no confirmation from another family")


def _opposing_breadth(signals: tuple[Signal, ...]) -> Signal | None:
    found = [s for s in signals if s.family is SignalFamily.PARTICIPATION
             and s.direction is Direction.BEARISH]
    return found[0] if found else None


def decision_moment(session: date) -> datetime:
    return datetime.combine(session, DECISION_TIME, tzinfo=NEW_YORK).astimezone(UTC)


def replay(spy: list[Bar], rsp: list[Bar], readings: dict[str, float | None]) -> list[Row]:
    """One row per session in `readings`, the session's ATM reading or None."""
    rsp_sessions = {bar.session for bar in rsp}
    rows: list[Row] = []
    for index, day in enumerate(sorted(readings)):
        session = date.fromisoformat(day)
        iv = readings[day]
        as_of = decision_moment(session)
        earlier = [bar for bar in spy if bar.session < session]

        def unmeasurable(reason: str, completed: Bar | None = None,
                         index: int = index, day: str = day, iv: float | None = iv) -> Row:
            return Row(day, str(completed.session) if completed else None, index, iv,
                       recon.regime(iv) if iv is not None else None, (), None, None,
                       UNMEASURABLE, reason, None)

        if not earlier:
            rows.append(unmeasurable("no completed session before it"))
            continue
        last = earlier[-1]
        first = last.session - timedelta(days=LOOKBACK_DAYS)
        if first + timedelta(days=1) < COVERED_FROM:
            rows.append(unmeasurable("400-day window starts before the cached bars", last))
            continue
        window = [bar for bar in earlier if bar.session > first]
        if len(window) < MIN_BARS_REQUIRED:
            rows.append(unmeasurable(f"{len(window)} bars, fewer than {MIN_BARS_REQUIRED}", last))
            continue
        if last.session not in rsp_sessions:
            rows.append(unmeasurable("no RSP bar for the last completed session", last))
            continue
        if iv is None:
            rows.append(unmeasurable("no at-the-money reading", last))
            continue
        breadth = [bar for bar in rsp if first < bar.session <= last.session]
        signals = tuple(build_signals(window, Decimal(repr(iv)), as_of, breadth))
        verdict = attribute(signals, last.close, last.session, as_of)
        opposing = _opposing_breadth(signals)
        gap = _GAP.search(opposing.summary) if opposing else None
        rows.append(Row(
            day, str(last.session), index, iv, recon.regime(iv),
            tuple((s.signal_id, s.direction.value, str(s.strength)) for s in signals),
            str(opposing.strength) if opposing else None,
            gap.group(1) if gap else None,
            verdict.bucket, verdict.reason, verdict.invalidation,
        ))
    return rows


def readings(options: dict[str, dict[str, Any]], spot: dict[tuple[str, str], float],
             rates: pricing.Rates, dividend: float = pricing.DIVIDEND_YIELD
             ) -> dict[str, float | None]:
    """Each session's reconstructed at-the-money implied volatility, or None."""
    out: dict[str, float | None] = {}
    for day, data in sorted(options.items()):
        found, _ = recon.reconstruct(data, spot, rates.before(date.fromisoformat(day)), dividend)
        chosen = recon.at_the_money(found, float(data["previous_close"]))
        out[day] = chosen.implied_volatility if chosen else None
    return out


def stored_signal(raw: dict[str, Any], as_of: datetime) -> Signal:
    return Signal(
        signal_id=raw["signal_id"], family=SignalFamily(raw["family"]),
        direction=Direction(raw["direction"]), strength=Decimal(raw["strength"]),
        as_of=as_of, source="stored", summary=raw.get("summary") or "stored",
    )


def reference(snapshots: dict[str, Any], stored: dict[str, Any]
              ) -> dict[str, tuple[Signal, ...]]:
    """The worker's own signals per decision session.

    The 10:00 decision snapshot where one was exported; otherwise, for a session
    whose signals did not vary, the stored set (9 October: one snapshot at 09:45,
    the one that opened the position).
    """
    out: dict[str, tuple[Signal, ...]] = {}
    for day, snap in snapshots["sessions"].items():
        as_of = datetime.fromisoformat(snap["as_of"])
        out[day] = tuple(stored_signal(raw, as_of) for raw in snap["signals"])
    for day in stored["snapshots"]:
        if day in out:
            continue
        found = [raw for raw in stored["signals"] if raw["day"] == day]
        ids = [raw["signal_id"] for raw in found]
        if len(ids) == len(set(ids)):
            as_of = decision_moment(date.fromisoformat(day))
            out[day] = tuple(stored_signal(raw, as_of) for raw in found)
    return out


def parity(rows: list[Row], live: dict[str, tuple[Signal, ...]],
           closes: dict[str, Decimal]) -> dict[str, Any]:
    """Replay against the worker's own record, session by session.

    Must pass: every session gets the same bucket from the replayed signals as
    from the worker's. Reported, not gated: signals other than the volatility
    reading must match exactly; the volatility reading's strength is compared,
    since it comes from a reconstructed input.
    """
    by_day = {row.session: row for row in rows}
    sessions: list[dict[str, Any]] = []
    for day, signals in sorted(live.items()):
        row = by_day.get(day)
        if row is None or row.completed is None:
            sessions.append({"session": day, "problem": "not replayed"})
            continue
        as_of = decision_moment(date.fromisoformat(day))
        expected = attribute(signals, closes[row.completed], date.fromisoformat(row.completed),
                             max([as_of, *(s.as_of for s in signals)]))
        theirs = {(s.signal_id, s.direction.value, s.strength) for s in signals
                  if s.signal_id != "sig-volatility-regime"}
        ours = {(sid, d, Decimal(st)) for sid, d, st in row.signals
                if sid != "sig-volatility-regime"}
        vol_theirs = [s for s in signals if s.signal_id == "sig-volatility-regime"]
        vol_ours = [s for s in row.signals if s[0] == "sig-volatility-regime"]
        sessions.append({
            "session": day,
            "bucket_live": expected.bucket,
            "bucket_replay": row.bucket,
            "same_bucket": expected.bucket == row.bucket,
            "other_signals_identical": theirs == ours,
            "volatility_live": (f"{vol_theirs[0].direction.value} {vol_theirs[0].strength}"
                                if vol_theirs else None),
            "volatility_replay": f"{vol_ours[0][1]} {vol_ours[0][2]}" if vol_ours else None,
        })
    return {
        "sessions": sessions,
        "passes": bool(sessions) and all(s.get("same_bucket") for s in sessions),
    }


def summary(rows: list[Row]) -> dict[str, Any]:
    buckets = Counter(row.bucket for row in rows)
    per_year: dict[str, Counter[str]] = {}
    for row in rows:
        per_year.setdefault(row.session[:4], Counter())[row.bucket] += 1
    groups: dict[str, dict[str, Any]] = {}
    for name in (PERMITTED, BREADTH_VETOED):
        indexes = [row.index for row in rows if row.bucket == name]
        groups[name] = {"sessions": len(indexes), "clusters": len(clusters(indexes)),
                        "longest_run": longest_run(indexes),
                        "by_regime": dict(Counter(row.regime for row in rows
                                                  if row.bucket == name))}
    qualifying = [row for row in rows if row.bucket in (PERMITTED, BREADTH_VETOED)]
    lines = {}
    for line in CONTEXT_LINES:
        vetoed = sum(1 for row in qualifying
                     if row.opposing_breadth is not None and Decimal(row.opposing_breadth) >= line)
        lines[str(line)] = {"permitted": len(qualifying) - vetoed, "breadth_vetoed": vetoed}
    lines["off"] = {"permitted": len(qualifying), "breadth_vetoed": 0}
    return {
        "sessions": len(rows),
        "first": rows[0].session if rows else None,
        "last": rows[-1].session if rows else None,
        "buckets": {name: buckets.get(name, 0) for name in BUCKETS},
        "per_year": {year: {name: c.get(name, 0) for name in BUCKETS}
                     for year, c in sorted(per_year.items())},
        "unmeasurable": dict(Counter(row.reason for row in rows if row.bucket == UNMEASURABLE)),
        "other_vetoes": dict(Counter(row.reason for row in rows if row.bucket == OTHER_VETOES)),
        "no_setup": dict(Counter(
            "structure below the line" if row.reason.startswith("structure ") else row.reason
            for row in rows if row.bucket == NO_SETUP)),
        "groups": groups,
        "screen": {
            "min_sessions": MIN_SESSIONS, "min_clusters": MIN_CLUSTERS,
            "passes": all(g["sessions"] >= MIN_SESSIONS and g["clusters"] >= MIN_CLUSTERS
                          for g in groups.values()),
        },
        "context_lines": lines,
        "rows_digest": digest(rows),
    }


def digest(rows: list[Row]) -> str:
    payload = json.dumps([asdict(row) for row in rows], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def render(report: dict[str, Any], check: dict[str, Any]) -> str:
    lines = [
        "Breadth veto, Step 2: signal replay and veto attribution (no outcomes)", "",
        f"Sessions: {report['sessions']} ({report['first']} to {report['last']})", "",
    ]
    for name, count in report["buckets"].items():
        lines.append(f"  {name}: {count}")
    lines += ["", "Unmeasurable: " + "; ".join(f"{r} {n}" for r, n in
                                                 sorted(report["unmeasurable"].items()))]
    lines.append("No setup: " + "; ".join(f"{r} {n}" for r, n in
                                          sorted(report["no_setup"].items())))
    if report["other_vetoes"]:
        lines.append("Other/multiple vetoes: " + "; ".join(
            f"{r} {n}" for r, n in sorted(report["other_vetoes"].items())))
    lines.append("")
    for name, group in report["groups"].items():
        lines.append(f"{name}: {group['sessions']} sessions, {group['clusters']} clusters, "
                     f"longest run {group['longest_run']}, by regime {group['by_regime']}")
    screen = report["screen"]
    lines += ["", f"Screen (at least {screen['min_sessions']} sessions and "
              f"{screen['min_clusters']} clusters in each group): "
              f"{'PASSES' if screen['passes'] else 'FAILS'}", ""]
    lines.append("Context only, breadth line: " + "; ".join(
        f"{line} -> {v['permitted']} permitted / {v['breadth_vetoed']} vetoed"
        for line, v in report["context_lines"].items()))
    lines += ["", f"Parity with the worker's record: {'PASSES' if check['passes'] else 'FAILS'}"]
    for s in check["sessions"]:
        if "problem" in s:
            lines.append(f"  {s['session']}: {s['problem']}")
            continue
        lines.append(
            f"  {s['session']}: live {s['bucket_live']}, replay {s['bucket_replay']}; "
            f"other signals {'identical' if s['other_signals_identical'] else 'DIFFER'}; "
            f"volatility live {s['volatility_live']}, replay {s['volatility_replay']}"
        )
    lines += ["", f"Rows digest: {report['rows_digest']}"]
    return "\n".join(lines)


def load(cache: Path = CACHE, dividend: float = pricing.DIVIDEND_YIELD
         ) -> tuple[list[Row], dict[str, Any]]:
    from .veto_study import load_bars

    spy, rsp = load_bars(cache / "daily_bars.json")
    options = {path.stem: json.loads(path.read_text())
               for path in (cache / "options").glob("*.json")}
    spot = recon.spot_by_bar(json.loads((cache / "spy_5min_open.json").read_text()))
    rates = pricing.Rates.load(cache / "DGS3MO.csv")
    rows = replay(spy, rsp, readings(options, spot, rates, dividend))
    live = reference(json.loads((cache / "decision_snapshots.json").read_text()),
                     json.loads((cache / "stored_signals.json").read_text()))
    closes = {str(bar.session): bar.close for bar in spy}
    return rows, parity(rows, live, closes)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--dividend", type=float, default=pricing.DIVIDEND_YIELD)
    parser.add_argument("--rows", type=Path, help="write every row as JSON here")
    args = parser.parse_args(argv)
    rows, check = load(args.cache, args.dividend)
    if args.rows:
        args.rows.write_text(json.dumps([asdict(row) for row in rows], indent=1))
    print(render(summary(rows), check))
    return 0 if check["passes"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
