"""Rebuild implied volatility and delta at the decision time from traded prices.

Protocol: docs/improvements/options_alpha_veto_backtest_protocol_v0_1.md,
sections 2, 3 and 7. The provider keeps no historical implied volatility, so
the study prices each contract's last trade bar before the 10:00 New York
decision and solves for the volatility. This module does that for one session,
picks the at-the-money reading the way the worker does, and measures the result
against the snapshots the worker stored (`parity`). It reads prices and stored
quotes only: no trade outcome is computed here.

Inputs, all from `scripts/veto_export.py` and `scripts/veto_rates.py`:
`options/<session>.json`, `spy_5min_open.json`, `decision_snapshots.json` and
`DGS3MO.csv`.

Two readings the protocol leaves to the implementation:

- The underlying price is the volume-weighted price of SPY's bar over the same
  five minutes as the option bar, so both sides are averages of one interval.
- A bar's age is measured from its end. The three bars that end from 09:50 to
  10:00 are all inside the 15-minute limit.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import veto_pricing as pricing
from .architecture.contracts import OptionType
from .components import LONG_DELTA_BAND, SHORT_DELTA_BAND
from .evidence import CALM_ATM_IV, STRESSED_ATM_IV, parse_occ_symbol

CACHE = Path(".cache/veto_backtest")
#: Opening times of the bars a decision may read; each ends five minutes later.
DECISION_SLOTS = (time(9, 45), time(9, 50), time(9, 55))
BAR = timedelta(minutes=5)
#: The worker asks for the chain in this range of days to expiry.
DTE_LOW, DTE_HIGH = 10, 60
MIN_VOLUME = 1

#: Parity gates (protocol section 7).
ATM_IV_TOLERANCE = 0.010
DELTA_TOLERANCE = 0.03
PASS_SHARE = 0.90


@dataclass(frozen=True)
class Reading:
    symbol: str
    kind: OptionType
    expiration: date
    strike: float
    #: When the bar that priced it ended.
    bar_end: datetime
    price: float
    spot: float
    implied_volatility: float
    delta: float


def spot_by_bar(data: dict[str, Any]) -> dict[tuple[str, str], float]:
    """SPY's volume-weighted price, keyed by session and bar opening time."""
    column = {name: i for i, name in enumerate(data["columns"])}
    return {
        (row[column["session"]], row[column["bar_open_new_york"]]):
            float(row[column["volume_weighted_price"]])
        for row in data["rows"]
    }


def reconstruct(
    options: dict[str, Any], spot: dict[tuple[str, str], float], rate: float,
    dividend: float = pricing.DIVIDEND_YIELD,
) -> tuple[list[Reading], Counter[str]]:
    """Every contract with a usable price, and a count of each reason one was dropped."""
    session = date.fromisoformat(options["session"])
    slots = [time.fromisoformat(slot) for slot in options["slots"]]
    readings: list[Reading] = []
    dropped: Counter[str] = Counter()
    for symbol, *bars in options["rows"]:
        parsed = parse_occ_symbol(symbol)
        if parsed is None:
            dropped["unreadable symbol"] += 1
            continue
        expiration, kind, strike = parsed
        if not DTE_LOW <= (expiration - session).days <= DTE_HIGH:
            dropped["outside 10 to 60 days to expiry"] += 1
            continue
        usable = [
            (slot, bar) for slot, bar in zip(slots, bars, strict=True)
            if slot in DECISION_SLOTS and bar and bar[1] >= MIN_VOLUME
        ]
        if not usable:
            dropped["no trade in the 15 minutes before the decision"] += 1
            continue
        slot, (price, _volume) = usable[-1]
        underlying = spot.get((options["session"], slot.strftime("%H:%M")))
        if underlying is None:
            dropped["no SPY bar for the same five minutes"] += 1
            continue
        bar_end = datetime.combine(session, slot, tzinfo=pricing.NEW_YORK) + BAR
        years = pricing.years_to_expiry(bar_end, expiration)
        volatility = pricing.implied_volatility(
            kind, float(price), underlying, float(strike), years, rate, dividend
        )
        if volatility is None:
            dropped["price below intrinsic value or no volatility in the bounds"] += 1
            continue
        readings.append(Reading(
            symbol, kind, expiration, float(strike), bar_end, float(price), underlying, volatility,
            pricing.delta(kind, underlying, float(strike), years, rate, dividend, volatility),
        ))
    return readings, dropped


def at_the_money(readings: list[Reading], previous_close: float) -> Reading | None:
    """The nearest strike to the previous close; the first symbol on a tie.

    The worker takes the first contract at the smallest distance as the provider
    lists them, which the stored snapshots show to be contract-symbol order:
    the nearest expiry, the call before the put, the lower strike.
    """
    if not readings:
        return None
    return min(readings, key=lambda r: (round(abs(r.strike - previous_close), 6), r.symbol))


def regime(implied_volatility: float) -> str:
    """Which side of the worker's two volatility thresholds a reading falls on."""
    value = Decimal(str(implied_volatility))
    if value <= CALM_ATM_IV:
        return "calm"
    if value >= STRESSED_ATM_IV:
        return "stressed"
    return "neither"


def stored_at_the_money(snapshot: dict[str, Any]) -> tuple[str, float] | None:
    """The contract and volatility the worker's own reading came from."""
    column = {name: i for i, name in enumerate(snapshot["columns"])}
    price = float(snapshot["underlying_price"])
    best: tuple[float, str, float] | None = None
    for row in snapshot["rows"]:
        parsed = parse_occ_symbol(row[column["contract_symbol"]])
        implied = row[column["implied_volatility"]]
        if parsed is None or implied is None or float(implied) <= 0:
            continue
        key = (round(abs(float(parsed[2]) - price), 6), row[column["contract_symbol"]])
        if best is None or key < best[:2]:
            best = (*key, float(implied))
    return None if best is None else (best[1], best[2])


def in_a_delta_band(delta: float) -> bool:
    value = Decimal(str(delta))
    return any(low <= value <= high for low, high in (LONG_DELTA_BAND, SHORT_DELTA_BAND))


def parity(
    snapshots: dict[str, Any], options: dict[str, dict[str, Any]],
    spot: dict[tuple[str, str], float], rates: pricing.Rates,
    dividend: float = pricing.DIVIDEND_YIELD,
) -> dict[str, Any]:
    """Reconstructed values against the worker's stored ones, and the three gates."""
    sessions: list[dict[str, Any]] = []
    delta_errors: list[float] = []
    band_contracts = band_priced = 0
    for day, snapshot in sorted(snapshots["sessions"].items()):
        row: dict[str, Any] = {"session": day}
        sessions.append(row)
        stored = stored_at_the_money(snapshot)
        if day not in options or stored is None:
            row["problem"] = "no option prices" if stored is not None else "no stored reading"
            continue
        readings, dropped = reconstruct(
            options[day], spot, rates.before(date.fromisoformat(day)), dividend
        )
        rebuilt = at_the_money(readings, float(snapshot["underlying_price"]))
        row.update(stored_contract=stored[0], stored=stored[1], priced=len(readings),
                   dropped=dict(dropped))
        if rebuilt is None:
            row["problem"] = "no contract could be priced"
            continue
        row.update(
            contract=rebuilt.symbol, rebuilt=rebuilt.implied_volatility,
            error=rebuilt.implied_volatility - stored[1],
            same_regime=regime(rebuilt.implied_volatility) == regime(stored[1]),
        )
        column = {name: i for i, name in enumerate(snapshot["columns"])}
        by_symbol = {r.symbol: r for r in readings}
        for quote in snapshot["rows"]:
            symbol, delta = quote[column["contract_symbol"]], quote[column["delta"]]
            parsed = parse_occ_symbol(symbol)
            if parsed is None or parsed[1] is not OptionType.CALL or delta is None:
                continue
            if not in_a_delta_band(float(delta)):
                continue
            band_contracts += 1
            if symbol in by_symbol:
                band_priced += 1
                delta_errors.append(by_symbol[symbol].delta - float(delta))

    measured = [row for row in sessions if "error" in row]
    iv_within = sum(1 for row in measured if abs(row["error"]) <= ATM_IV_TOLERANCE)
    delta_within = sum(1 for error in delta_errors if abs(error) <= DELTA_TOLERANCE)
    total = len(sessions)
    return {
        "sessions": sessions,
        "atm_iv": {
            "sessions": total, "measured": len(measured), "within": iv_within,
            # A session that could not be measured does not count as within.
            "passes": total > 0 and iv_within / total >= PASS_SHARE,
        },
        "delta": {
            "band_contracts": band_contracts, "priced": band_priced, "within": delta_within,
            "errors": sorted(delta_errors),
            "passes": band_priced > 0 and delta_within / band_priced >= PASS_SHARE,
        },
        "regime": {
            "same": sum(1 for row in measured if row["same_regime"]),
            "passes": total > 0 and len(measured) == total
            and all(row["same_regime"] for row in measured),
        },
    }


def coverage(
    options: dict[str, dict[str, Any]], spot: dict[tuple[str, str], float], rates: pricing.Rates,
    dividend: float = pricing.DIVIDEND_YIELD,
) -> dict[str, Any]:
    """Which sessions have an at-the-money reading, and why contracts were dropped.

    The reading's level is reported only as a distribution and by class: it is an
    input to the replay, not a result.
    """
    unmeasurable: list[dict[str, Any]] = []
    classes: Counter[str] = Counter()
    dropped: Counter[str] = Counter()
    near_a_threshold: list[str] = []
    levels: list[float] = []
    priced = 0
    for day, data in sorted(options.items()):
        readings, reasons = reconstruct(
            data, spot, rates.before(date.fromisoformat(day)), dividend
        )
        dropped.update(reasons)
        priced += len(readings)
        chosen = at_the_money(readings, float(data["previous_close"]))
        if chosen is None:
            unmeasurable.append({"session": day, "listed": data["listed"],
                                 "traded": data["traded"]})
            continue
        levels.append(chosen.implied_volatility)
        classes[regime(chosen.implied_volatility)] += 1
        if any(abs(chosen.implied_volatility - float(line)) <= ATM_IV_TOLERANCE
               for line in (CALM_ATM_IV, STRESSED_ATM_IV)):
            near_a_threshold.append(day)
    levels.sort()
    return {
        "sessions": len(options),
        "measured": len(levels),
        "unmeasurable": unmeasurable,
        "priced_contracts": priced,
        "dropped": dict(dropped),
        "classes": dict(classes),
        "near_a_threshold": near_a_threshold,
        "levels": {"min": levels[0], "median": _quantile(levels, 0.5), "max": levels[-1]}
        if levels else None,
    }


def render_coverage(report: dict[str, Any]) -> str:
    lines = [
        "At-the-money reading over the download (inputs only; no outcome is read)", "",
        f"Sessions: {report['sessions']}; with a reading: {report['measured']}",
    ]
    for row in report["unmeasurable"]:
        lines.append(f"  {row['session']}: no reading ({row['traded']} of {row['listed']} "
                     "listed contracts traded)")
    lines.append(f"Contracts priced: {report['priced_contracts']}")
    for reason, count in sorted(report["dropped"].items()):
        lines.append(f"  dropped, {reason}: {count}")
    if report["levels"]:
        levels = report["levels"]
        lines.append(f"Reading: lowest {levels['min']:.4f}, median {levels['median']:.4f}, "
                     f"highest {levels['max']:.4f}")
    lines.append("Class: " + ", ".join(f"{name} {count}"
                                        for name, count in sorted(report["classes"].items())))
    lines.append(f"Within {ATM_IV_TOLERANCE} of a threshold: {len(report['near_a_threshold'])} "
                 "sessions")
    return "\n".join(lines)


def _quantile(values: list[float], share: float) -> float:
    return values[min(len(values) - 1, int(share * len(values)))]


def render(report: dict[str, Any]) -> str:
    lines = [
        "Reconstruction against the worker's stored snapshots (no outcome is read)", "",
        "session     stored  rebuilt  error   same contract  priced",
    ]
    for row in report["sessions"]:
        if "error" not in row:
            lines.append(f"{row['session']}  {row['problem']}")
            continue
        lines.append(
            f"{row['session']}  {row['stored']:.4f}  {row['rebuilt']:.4f}  {row['error']:+.4f}  "
            f"{'yes' if row['contract'] == row['stored_contract'] else 'no ':<13}  {row['priced']}"
        )
    atm, delta, same = report["atm_iv"], report["delta"], report["regime"]
    verdict = {True: "PASSES", False: "FAILS"}
    lines += [
        "",
        f"At-the-money volatility within {ATM_IV_TOLERANCE}: {atm['within']} of "
        f"{atm['sessions']} sessions (needs {PASS_SHARE:.0%}): {verdict[atm['passes']]}",
        f"Delta within {DELTA_TOLERANCE}: {delta['within']} of {delta['priced']} priced calls "
        f"in the delta bands (needs {PASS_SHARE:.0%}): {verdict[delta['passes']]}",
        f"  {delta['priced']} of {delta['band_contracts']} stored band contracts had a trade "
        "to price",
    ]
    if delta["errors"]:
        absolute = sorted(abs(error) for error in delta["errors"])
        lines.append(f"  absolute delta error: median {_quantile(absolute, 0.5):.4f}, "
                     f"90th percentile {_quantile(absolute, 0.9):.4f}, largest {absolute[-1]:.4f}")
    lines.append(f"Same calm/neither/stressed class: {same['same']} of {atm['sessions']} "
                 f"sessions (needs all): {verdict[same['passes']]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--dividend", type=float, default=pricing.DIVIDEND_YIELD)
    parser.add_argument("--coverage", action="store_true",
                        help="report the reading over every downloaded session instead")
    args = parser.parse_args(argv)
    if args.coverage:
        every = {path.stem: json.loads(path.read_text())
                 for path in (args.cache / "options").glob("*.json")}
        spot = spot_by_bar(json.loads((args.cache / "spy_5min_open.json").read_text()))
        rates = pricing.Rates.load(args.cache / "DGS3MO.csv")
        print(render_coverage(coverage(every, spot, rates, args.dividend)))
        return 0
    snapshots = json.loads((args.cache / "decision_snapshots.json").read_text())
    options = {
        path.stem: json.loads(path.read_text())
        for path in (args.cache / "options").glob("*.json") if path.stem in snapshots["sessions"]
    }
    spot = spot_by_bar(json.loads((args.cache / "spy_5min_open.json").read_text()))
    rates = pricing.Rates.load(args.cache / "DGS3MO.csv")
    report = parity(snapshots, options, spot, rates, args.dividend)
    print(render(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
