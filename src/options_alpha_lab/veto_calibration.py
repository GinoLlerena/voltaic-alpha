"""The synthetic quote's half-width, measured from the worker's stored quotes.

Protocol: docs/improvements/options_alpha_veto_backtest_protocol_v0_1.md,
section 4. The provider keeps no bid/ask history, so the backtest models a
quote around each traded price with a half-width of `max($0.01, k * price)`.
`k` is the median relative half-spread of the contracts inside the worker's two
delta bands in the live decision snapshots. It is measured once, from quotes
only, and then frozen: nothing here reads a trade outcome.

The contracts are calls, the legs of the bullish spread the study covers. A
quote with no positive bid, or an ask below the bid, is not a spread and is
counted apart.

Input: `veto_export.py snapshots`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from .architecture.contracts import OptionType
from .components import LONG_DELTA_BAND, SHORT_DELTA_BAND
from .evidence import parse_occ_symbol

SNAPSHOTS = Path(".cache/veto_backtest/decision_snapshots.json")
#: Measured on 12 October 2026 from 2,271 quotes in 13 sessions and frozen
#: (protocol section 11). The backtest uses this; it does not measure again.
K = Decimal("0.006224")
#: What the protocol named for the case where the snapshots could not be exported.
FALLBACK_K = Decimal("0.010")
BANDS = {"long": LONG_DELTA_BAND, "short": SHORT_DELTA_BAND}


def band_of(delta: Decimal) -> str | None:
    for name, (low, high) in BANDS.items():
        if low <= delta <= high:
            return name
    return None


def relative_half_spread(bid: Decimal, ask: Decimal) -> Decimal | None:
    """Half the quoted spread over the midpoint, or `None` for an unusable quote."""
    if bid <= 0 or ask < bid:
        return None
    return (ask - bid) / (ask + bid)


def measure(data: dict[str, Any]) -> dict[str, Any]:
    """`k` and what it was measured from."""
    pooled: list[Decimal] = []
    by_band: dict[str, list[Decimal]] = {name: [] for name in BANDS}
    by_session: dict[str, Decimal] = {}
    unusable = 0
    for day, session in sorted(data["sessions"].items()):
        column = {name: i for i, name in enumerate(session["columns"])}
        found: list[Decimal] = []
        for row in session["rows"]:
            parsed = parse_occ_symbol(row[column["contract_symbol"]])
            delta = row[column["delta"]]
            if parsed is None or parsed[1] is not OptionType.CALL or delta is None:
                continue
            band = band_of(Decimal(str(delta)))
            if band is None:
                continue
            spread = relative_half_spread(
                Decimal(str(row[column["bid"]])), Decimal(str(row[column["ask"]]))
            )
            if spread is None:
                unusable += 1
                continue
            found.append(spread)
            by_band[band].append(spread)
        if found:
            by_session[day] = median(found)
            pooled.extend(found)
    return {
        "k": median(pooled) if pooled else None,
        "quotes": len(pooled),
        "unusable_quotes": unusable,
        "sessions": len(by_session),
        "by_band": {name: (median(v) if v else None) for name, v in by_band.items()},
        "by_session": by_session,
    }


def render(report: dict[str, Any]) -> str:
    if report["k"] is None:
        return f"No usable quote in the delta bands. The protocol's fallback is k = {FALLBACK_K}."
    lines = [
        "Synthetic quote half-width (quotes only; no outcome is read)",
        "",
        f"k = {report['k']:.4%} of price: the median over {report['quotes']} call quotes "
        f"in {report['sessions']} sessions ({report['unusable_quotes']} unusable quotes set aside)",
    ]
    for name, value in report["by_band"].items():
        low, high = BANDS[name]
        shown = "none" if value is None else f"{value:.4%}"
        lines.append(f"  {name} leg band, delta {low} to {high}: {shown}")
    values = sorted(report["by_session"].values())
    lines.append(f"  session medians: {values[0]:.4%} to {values[-1]:.4%}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS)
    args = parser.parse_args(argv)
    print(render(measure(json.loads(args.snapshots.read_text()))))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
