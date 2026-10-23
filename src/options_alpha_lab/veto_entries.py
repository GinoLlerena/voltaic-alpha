"""Step 4 of the breadth veto backtest: the spread the bot would have chosen.

Plan: docs/improvements/options_alpha_veto_backtest_plan_v0_1.md, section 5.1
and Step 4 (`VBT-201`). Protocol: options_alpha_veto_backtest_protocol_v0_1.md,
sections 2 to 4 and the Step 4 note of 23 October 2026 in section 11.

For each Permitted and Breadth-vetoed session it rebuilds the call chain at the
10:00 decision from traded prices: implied volatility and delta from Step 1's
reconstruction, and a synthetic bid and ask around each traded price. It then
runs the shipped `DeterministicBaselineThesis`, `DeterministicSpreadSelector`
and `DeterministicRiskGovernor` unchanged, checks the two legs' bars are close
enough in time, and records the fill reference in the next bar.

It reads nothing after the 10:00–10:05 fill bar, so it computes no outcome.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import veto_pricing as pricing
from . import veto_reconstruction as recon
from . import veto_replay as vr
from .architecture.contracts import (
    AccountSnapshot,
    DecisionSnapshot,
    OptionQuoteSnapshot,
    OptionType,
    PriceSource,
    SetupCandidate,
    Signal,
)
from .components import (
    DeterministicBaselineThesis,
    DeterministicRiskGovernor,
    DeterministicSpreadSelector,
    crossing_debit,
)
from .veto_calibration import K

CACHE = recon.CACHE
#: Protocol section 3.
MAX_LEG_GAP = timedelta(minutes=10)
#: Protocol section 1: the bar a fill uses.
FILL_SLOT = "10:00"
MIN_HALF_WIDTH = Decimal("0.01")
#: Protocol section 11, Step 4 note: the independent analysis's account.
EQUITY = Decimal("100000")
FEED = "reconstructed"

NO_CHAIN = "no chain downloaded"
NO_PAIR = "selector found no eligible pair"
NOT_SYNCHRONIZED = "legs' bars more than 10 minutes apart"
RISK_REFUSED = "risk governor refused"
UNFILLED = "a leg did not trade in the 10:00-10:05 bar"
ENTERED = "entered"


@dataclass(frozen=True)
class Entry:
    session: str
    group: str
    status: str
    #: Contracts in the rebuilt chain, and those the reconstruction dropped.
    chain_calls: int
    dropped: int
    long_symbol: str | None = None
    short_symbol: str | None = None
    expiration: str | None = None
    dte: int | None = None
    long_strike: str | None = None
    short_strike: str | None = None
    width: str | None = None
    long_delta: float | None = None
    short_delta: float | None = None
    #: `long.ask - short.bid` on the synthetic quotes, the selector's screen.
    quoted_debit: str | None = None
    #: With the crossing allowance: what risk approves against.
    estimated_debit: str | None = None
    leg_gap_minutes: float | None = None
    risk_reasons: tuple[str, ...] = ()
    #: `P` in the 10:00-10:05 bar, before any friction case.
    fill_reference: str | None = None
    invalidation: str | None = None
    reference_close: str | None = None


def half_width(price: Decimal) -> Decimal:
    return max(MIN_HALF_WIDTH, K * price)


def quote(reading: recon.Reading, session: date) -> OptionQuoteSnapshot:
    """A synthetic quote around one traded price (protocol section 4)."""
    price = Decimal(repr(reading.price))
    h = half_width(price)
    return OptionQuoteSnapshot(
        contract_symbol=reading.symbol,
        option_type=reading.kind,
        expiration=reading.expiration,
        # As the worker counts it: expiry minus the decision's UTC date.
        dte=(reading.expiration - vr.decision_moment(session).date()).days,
        strike=Decimal(repr(reading.strike)),
        bid=price - h,
        ask=price + h,
        quote_as_of=reading.bar_end.astimezone(UTC),
        feed=FEED,
        delta=Decimal(repr(round(reading.delta, 6))),
        implied_volatility=Decimal(repr(round(reading.implied_volatility, 6))),
    )


def fill_prices(chain: dict[str, Any]) -> dict[str, Decimal]:
    """Each contract's volume-weighted price in the fill bar, where it traded."""
    slot = chain["slots"].index(FILL_SLOT)
    out: dict[str, Decimal] = {}
    for symbol, *bars in chain["rows"]:
        bar = bars[slot]
        if bar and bar[1] >= recon.MIN_VOLUME:
            out[symbol] = Decimal(repr(bar[0]))
    return out


def select(session: str, group: str, setup: SetupCandidate, signals: tuple[Signal, ...],
           reference_close: Decimal, completed: date, chain: dict[str, Any] | None,
           spot: dict[tuple[str, str], float], rate: float,
           dividend: float = pricing.DIVIDEND_YIELD) -> Entry:
    """One session's entry, or the first gate that stopped it."""
    level = str(setup.invalidation.level) if setup.invalidation else None
    entry = Entry(session=session, group=group, status=NO_CHAIN, chain_calls=0, dropped=0,
                  invalidation=level, reference_close=str(reference_close))
    if chain is None:
        return entry
    day = date.fromisoformat(session)
    readings, dropped = recon.reconstruct(chain, spot, rate, dividend)
    calls = [r for r in readings if r.kind is OptionType.CALL]
    by_symbol = {r.symbol: r for r in calls}
    as_of = vr.decision_moment(day)
    snapshot = DecisionSnapshot(
        snapshot_id=f"veto-entry-{session}",
        as_of=as_of,
        symbol="SPY",
        underlying_price=reference_close,
        account=AccountSnapshot("research", as_of, EQUITY, EQUITY, True),
        signals=signals,
        option_chain=tuple(quote(r, day) for r in calls),
        underlying_source=PriceSource.COMPLETED_DAILY_CLOSE,
        underlying_session=completed,
    )
    entry = replace(entry, chain_calls=len(calls), dropped=sum(dropped.values()))
    thesis = DeterministicBaselineThesis().synthesize(snapshot, setup)
    spread = DeterministicSpreadSelector().select(snapshot, setup, thesis)
    if spread is None:
        return replace(entry, status=NO_PAIR)

    quotes = {q.contract_symbol: q for q in snapshot.option_chain}
    long_q, short_q = quotes[spread.long_contract_symbol], quotes[spread.short_contract_symbol]
    long_r, short_r = by_symbol[long_q.contract_symbol], by_symbol[short_q.contract_symbol]
    gap = abs(long_r.bar_end - short_r.bar_end)
    entry = replace(
        entry,
        long_symbol=long_q.contract_symbol, short_symbol=short_q.contract_symbol,
        expiration=long_q.expiration.isoformat(), dte=long_q.dte,
        long_strike=str(long_q.strike), short_strike=str(short_q.strike),
        width=str(short_q.strike - long_q.strike),
        long_delta=long_r.delta, short_delta=short_r.delta,
        quoted_debit=str(long_q.ask - short_q.bid),
        estimated_debit=str(crossing_debit(long_q, short_q)),
        leg_gap_minutes=gap.total_seconds() / 60,
    )
    if gap > MAX_LEG_GAP:
        return replace(entry, status=NOT_SYNCHRONIZED)
    risk = DeterministicRiskGovernor().evaluate(snapshot, setup, thesis, spread)
    if not risk.approved:
        return replace(entry, status=RISK_REFUSED, risk_reasons=risk.reason_codes)
    fills = fill_prices(chain)
    if long_q.contract_symbol not in fills or short_q.contract_symbol not in fills:
        return replace(entry, status=UNFILLED)
    reference = fills[long_q.contract_symbol] - fills[short_q.contract_symbol]
    return replace(entry, status=ENTERED, fill_reference=str(reference))


def entries(rows: Sequence[vr.Row],
            qualified: dict[str, tuple[SetupCandidate, tuple[Signal, ...]]],
            closes: dict[str, Decimal], chains: dict[str, dict[str, Any]],
            spot: dict[tuple[str, str], float], rates: pricing.Rates,
            dividend: float = pricing.DIVIDEND_YIELD) -> list[Entry]:
    out: list[Entry] = []
    for row in rows:
        if row.bucket not in (vr.PERMITTED, vr.BREADTH_VETOED):
            continue
        if row.completed is None or row.session not in qualified:
            raise ValueError(f"{row.session}: a qualifying row has no setup")
        setup, signals = qualified[row.session]
        day = date.fromisoformat(row.session)
        out.append(select(row.session, row.bucket, setup, signals, closes[row.completed],
                          date.fromisoformat(row.completed), chains.get(row.session),
                          spot, rates.before(day), dividend))
    return out


def summary(found: Sequence[Entry]) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for g in (vr.PERMITTED, vr.BREADTH_VETOED):
        members = [e for e in found if e.group == g]
        entered = [e for e in members if e.status == ENTERED]

        def spread_of(values: list[Decimal]) -> dict[str, str] | None:
            if not values:
                return None
            ordered = sorted(values)
            return {"min": str(ordered[0]), "median": str(ordered[len(ordered) // 2]),
                    "max": str(ordered[-1])}

        groups[g] = {
            "sessions": len(members),
            "status": dict(Counter(e.status for e in members)),
            "risk_reasons": dict(Counter(r for e in members for r in e.risk_reasons)),
            "entered": len(entered),
            "dte": spread_of([Decimal(e.dte) for e in entered if e.dte is not None]),
            "width": spread_of([Decimal(e.width) for e in entered if e.width]),
            "estimated_debit": spread_of([Decimal(e.estimated_debit) for e in entered
                                          if e.estimated_debit]),
            "fill_reference": spread_of([Decimal(e.fill_reference) for e in entered
                                         if e.fill_reference]),
            "by_year": dict(Counter(e.session[:4] for e in entered)),
        }
    return {"sessions": len(found), "groups": groups, "entries_digest": digest(found)}


def digest(found: Sequence[Entry]) -> str:
    payload = json.dumps([asdict(e) for e in found], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def render(report: dict[str, Any], reference: Entry | None) -> str:
    lines = ["Breadth veto, Step 4: the spread chosen at each entry (no outcomes)", ""]
    for g, info in report["groups"].items():
        lines.append(f"{g}: {info['sessions']} sessions, {info['entered']} entered")
        for status, n in sorted(info["status"].items()):
            lines.append(f"  {status}: {n}")
        if info["risk_reasons"]:
            lines.append(f"  risk reasons: {info['risk_reasons']}")
        for key in ("dte", "width", "estimated_debit", "fill_reference"):
            lines.append(f"  {key}: {info[key]}")
        lines.append(f"  entered by year: {info['by_year']}")
        lines.append("")
    if reference is not None:
        lines.append(f"9 October 2026, the first Paper trade's session: {asdict(reference)}")
    lines += ["", f"Entries digest: {report['entries_digest']}"]
    return "\n".join(lines)


def load(cache: Path = CACHE, dividend: float = pricing.DIVIDEND_YIELD
         ) -> tuple[list[Entry], dict[str, Any]]:
    from .veto_study import load_bars

    spy, rsp = load_bars(cache / "daily_bars.json")
    options = {path.stem: json.loads(path.read_text())
               for path in (cache / "options").glob("*.json")}
    spot = recon.spot_by_bar(json.loads((cache / "spy_5min_open.json").read_text()))
    rates = pricing.Rates.load(cache / "DGS3MO.csv")
    qualified: dict[str, tuple[SetupCandidate, tuple[Signal, ...]]] = {}
    rows = vr.replay(spy, rsp, vr.readings(options, spot, rates, dividend), qualified)
    live = vr.reference(json.loads((cache / "decision_snapshots.json").read_text()),
                        json.loads((cache / "stored_signals.json").read_text()))
    closes = {str(bar.session): bar.close for bar in spy}
    check = vr.parity(rows, live, closes)
    if not check["passes"]:
        raise SystemExit("Step 2 parity fails; no entry is selected")
    chains = {path.stem: json.loads(path.read_text())
              for path in (cache / "chains").glob("*.json")}
    return entries(rows, qualified, closes, chains, spot, rates, dividend), {
        "rows_digest": vr.digest(rows),
        # Every replayed session's place in the sequence, for Part 2's bootstrap.
        "index": {row.session: row.index for row in rows}}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--entries", type=Path, help="write every entry as JSON here")
    args = parser.parse_args(argv)
    found, facts = load(args.cache)
    print(f"Step 2 rows digest: {facts['rows_digest']}")
    if args.entries:
        args.entries.write_text(json.dumps([asdict(e) for e in found], indent=1))
    reference = next((e for e in found if e.session == "2026-10-09"), None)
    print(render(summary(found), reference))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
