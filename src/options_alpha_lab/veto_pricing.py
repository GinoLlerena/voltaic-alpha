"""Implied volatility and delta from a traded option price, for the veto backtest.

Protocol: docs/improvements/options_alpha_veto_backtest_protocol_v0_1.md,
section 2. The provider keeps no historical implied volatility or greeks, so the
study rebuilds both from trade prices with one stated model:

- Black-Scholes-Merton, European exercise, continuous dividend yield. SPY
  options are American, so this is an approximation; the protocol's parity
  gates measure it against the values the worker stored.
- Time to expiry is calendar time to 16:00 New York on the expiry date, over
  365 days.
- The volatility is solved with Brent's method between 1% and 300%, to a price
  tolerance of $0.0001. A price at or below intrinsic value less $0.01, or one
  with no root inside the bounds, gives `None`: the contract is dropped by the
  caller and counted, never clipped into a valid value.
- The rate is the 3-month Treasury yield published for the latest business day
  before the session (FRED series DGS3MO), read as an annual rate with no
  compounding conversion. At these maturities the difference is a few
  hundredths of a volatility point.

Floats, not `Decimal`: this is a research calculation, and nothing here prices
an order.
"""

from __future__ import annotations

import csv
import math
from bisect import bisect_left
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .architecture.contracts import OptionType

MIN_VOLATILITY = 0.01
MAX_VOLATILITY = 3.00
PRICE_TOLERANCE = 0.0001
#: A price this far under intrinsic value is not a usable observation.
INTRINSIC_SLACK = 0.01
DIVIDEND_YIELD = 0.012
DIVIDEND_YIELD_SENSITIVITY = (0.007, 0.017)
DAYS_IN_YEAR = 365.0
NEW_YORK = ZoneInfo("America/New_York")
EXPIRY_TIME = time(16, 0)


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def years_to_expiry(at: datetime, expiration: date) -> float:
    """Calendar time from `at` to the close on the expiry date. May be negative."""
    close = datetime.combine(expiration, EXPIRY_TIME, tzinfo=NEW_YORK)
    return (close - at).total_seconds() / (DAYS_IN_YEAR * 86400.0)


def _d1(spot: float, strike: float, years: float, rate: float, dividend: float,
        volatility: float) -> float:
    drift = (rate - dividend + 0.5 * volatility * volatility) * years
    return (math.log(spot / strike) + drift) / (volatility * math.sqrt(years))


def price(kind: OptionType, spot: float, strike: float, years: float, rate: float,
          dividend: float, volatility: float) -> float:
    d1 = _d1(spot, strike, years, rate, dividend, volatility)
    d2 = d1 - volatility * math.sqrt(years)
    forward_spot = spot * math.exp(-dividend * years)
    present_strike = strike * math.exp(-rate * years)
    if kind is OptionType.CALL:
        return forward_spot * _cdf(d1) - present_strike * _cdf(d2)
    return present_strike * _cdf(-d2) - forward_spot * _cdf(-d1)


def delta(kind: OptionType, spot: float, strike: float, years: float, rate: float,
          dividend: float, volatility: float) -> float:
    d1 = _d1(spot, strike, years, rate, dividend, volatility)
    carry = math.exp(-dividend * years)
    return carry * _cdf(d1) if kind is OptionType.CALL else carry * (_cdf(d1) - 1.0)


def brent(f: Callable[[float], float], low: float, high: float, tolerance: float) -> float | None:
    """A root of `f` in [low, high], or `None` when the ends do not bracket one.

    Stops when `|f|` is within `tolerance`. Brent's method: inverse quadratic
    interpolation or a secant step when it stays inside the bracket and
    converges, and bisection otherwise.
    """
    a, b = low, high
    fa, fb = f(a), f(b)
    if abs(fa) <= tolerance:
        return a
    if abs(fb) <= tolerance:
        return b
    if (fa > 0) == (fb > 0):
        return None
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc = a, fa
    d = b - a
    bisected = True
    for _ in range(200):
        if abs(fb) <= tolerance:
            return b
        if fa != fc and fb != fc:
            s = (
                a * fb * fc / ((fa - fb) * (fa - fc))
                + b * fa * fc / ((fb - fa) * (fb - fc))
                + c * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            s = b - fb * (b - a) / (fb - fa)
        midpoint = (a + b) / 2.0
        inside = min((3 * a + b) / 4.0, b) < s < max((3 * a + b) / 4.0, b)
        slow = abs(s - b) >= (abs(b - c) if bisected else abs(c - d)) / 2.0
        if not inside or slow:
            s = midpoint
            bisected = True
        else:
            bisected = False
        fs = f(s)
        d, c, fc = c, b, fb
        if (fa > 0) != (fs > 0):
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa
        if a == b:
            break
    return b if abs(fb) <= tolerance else None


def implied_volatility(kind: OptionType, observed: float, spot: float, strike: float,
                       years: float, rate: float,
                       dividend: float = DIVIDEND_YIELD) -> float | None:
    """The volatility that prices the option at `observed`, or `None`."""
    if years <= 0 or spot <= 0 or strike <= 0 or observed <= 0:
        return None
    intrinsic = max(spot - strike, 0.0) if kind is OptionType.CALL else max(strike - spot, 0.0)
    if observed <= intrinsic - INTRINSIC_SLACK:
        return None
    return brent(
        lambda volatility: price(kind, spot, strike, years, rate, dividend, volatility) - observed,
        MIN_VOLATILITY, MAX_VOLATILITY, PRICE_TOLERANCE,
    )


class Rates:
    """The risk-free series, as published: one annual rate per business day."""

    def __init__(self, observations: dict[date, float]) -> None:
        self._days = sorted(observations)
        self._rates = [observations[day] for day in self._days]

    @classmethod
    def load(cls, path: Path) -> Rates:
        """A FRED download: a date column and a percent column, '.' where unpublished."""
        observations: dict[date, float] = {}
        with path.open(newline="") as handle:
            rows = csv.reader(handle)
            next(rows)
            for day, value in rows:
                if value not in ("", "."):
                    observations[date.fromisoformat(day)] = float(value) / 100.0
        return cls(observations)

    def before(self, session: date) -> float:
        """The latest rate published for a day strictly before `session`."""
        index = bisect_left(self._days, session)
        if index == 0:
            raise LookupError(f"no rate is published before {session}")
        return self._rates[index - 1]
