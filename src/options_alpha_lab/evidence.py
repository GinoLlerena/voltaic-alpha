"""Build a `DecisionSnapshot` from read-only provider data.

Three properties matter more than the indicator choices, and each is enforced
rather than documented:

* **No look-ahead.** Only completed sessions contribute. The bar for the current
  session is discarded while the market is open, because acting on a forming bar
  is the most common way a backtest lies.
* **Freshness is feed-specific and fail-closed.** Stale inputs produce a data
  quality finding that terminates the decision, never a substituted default.
* **Confirmation must come from a different instrument.** Price structure
  confirmed by another transformation of the same price series is one piece of
  evidence wearing two hats (`CLR-010`).

Every threshold here is `PROVISIONAL` until `CLR-016` is closed with replay
evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .architecture.contracts import (
    AccountSnapshot,
    DataQuality,
    DecisionSnapshot,
    Direction,
    OptionQuoteSnapshot,
    OptionType,
    PriceSource,
    Signal,
    SignalFamily,
)
from .providers.alpaca_readonly import ProviderRead, iter_snapshot_items

# --- PROVISIONAL policy values ----------------------------------------------
FAST_EMA = 20
SLOW_EMA = 50
RETEST_LOOKBACK_SESSIONS = 5
RETEST_TOLERANCE = Decimal("0.010")
MIN_EMA_SEPARATION = Decimal("0.002")
MOMENTUM_SHORT_SESSIONS = 5
MOMENTUM_LONG_SESSIONS = 20
#: Participation breadth, measured as equal-weight against cap-weight. SPY is
#: cap-weighted and RSP holds the same 500 companies equally, so the ratio
#: between them answers "is the average stock participating, or are a handful of
#: mega-caps carrying this?" - which is what breadth means. It is a different
#: instrument rather than another transformation of SPY's own price (`CLR-010`).
PARTICIPATION_SYMBOL = "RSP"
PARTICIPATION_SESSIONS = 10
MIN_PARTICIPATION_DIVERGENCE = Decimal("0.002")
CALM_ATM_IV = Decimal("0.22")
STRESSED_ATM_IV = Decimal("0.32")
MIN_BARS_REQUIRED = SLOW_EMA + MOMENTUM_LONG_SESSIONS

ACCOUNT_FRESHNESS = timedelta(seconds=30)
CLOCK_FRESHNESS = timedelta(seconds=60)
OPTION_FRESHNESS = {"opra": timedelta(seconds=30), "indicative": timedelta(seconds=120)}
MAX_SESSIONS_SINCE_LAST_BAR = 5

_OCC = re.compile(
    r"^(?P<root>[A-Z]+)(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})"
    r"(?P<cp>[CP])(?P<strike>\d{8})$"
)


class EvidenceError(ValueError):
    """The provider data cannot produce a valid snapshot at all."""


@dataclass(frozen=True)
class Bar:
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def parse_occ_symbol(symbol: str) -> tuple[date, OptionType, Decimal] | None:
    """Parse an OCC option symbol. Returns ``None`` rather than guessing."""
    match = _OCC.match(symbol)
    if not match:
        return None
    expiration = date(
        2000 + int(match["yy"]), int(match["mm"]), int(match["dd"])
    )
    option_type = OptionType.CALL if match["cp"] == "C" else OptionType.PUT
    strike = Decimal(match["strike"]) / Decimal("1000")
    return expiration, option_type, strike


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def parse_bars(read: ProviderRead, *, as_of: datetime, market_open: bool) -> list[Bar]:
    """Return completed daily bars, oldest first, with the forming bar removed."""
    raw = read.payload.get("bars") if isinstance(read.payload, dict) else None
    if not isinstance(raw, list):
        raise EvidenceError("bars payload is not a list")

    bars: list[Bar] = []
    for item in raw:
        stamp = item.get("t")
        if not isinstance(stamp, str):
            continue
        session = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC).date()
        values = [_dec(item.get(k)) for k in ("o", "h", "l", "c", "v")]
        if any(value is None for value in values):
            continue
        open_, high, low, close, volume = (v for v in values if v is not None)
        bars.append(Bar(session, open_, high, low, close, volume))

    bars.sort(key=lambda bar: bar.session)
    if market_open and bars and bars[-1].session >= as_of.astimezone(UTC).date():
        # The current session is still forming. Acting on it is look-ahead.
        bars.pop()
    return bars


def ema(values: list[Decimal], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    multiplier = Decimal(2) / Decimal(period + 1)
    current = sum(values[:period], start=Decimal("0")) / Decimal(period)
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value)).quantize(Decimal("0.01"))


def participation_signal(
    bars: list[Bar],
    participation_bars: list[Bar],
    as_of: datetime,
) -> Signal | None:
    """Breadth from equal-weight against cap-weight. ``None`` when unmeasurable.

    A rising RSP/SPY ratio means the average constituent is keeping up with or
    beating the index, so the move is broad. A falling ratio means it is
    concentrated in a shrinking group of large names. The signal reports what
    breadth says; whether that confirms or contradicts is the classifier's
    decision, not this function's.

    Returns ``None`` rather than a neutral signal when breadth cannot be
    measured: an absent confirmation must not be mistaken for a measured one.
    """
    if len(bars) <= PARTICIPATION_SESSIONS or len(participation_bars) <= PARTICIPATION_SESSIONS:
        return None

    # Align on session, not position. The two series can disagree about which
    # days exist - a halt, a late bar, a provider gap - and pairing by index
    # would then silently compare different days.
    by_session = {bar.session: bar.close for bar in participation_bars}
    paired = [
        (bar.close, by_session[bar.session]) for bar in bars if bar.session in by_session
    ]
    if len(paired) <= PARTICIPATION_SESSIONS:
        return None

    index_now, breadth_now = paired[-1]
    index_then, breadth_then = paired[-1 - PARTICIPATION_SESSIONS]
    if index_now <= 0 or index_then <= 0 or breadth_then <= 0:
        return None

    ratio_now = breadth_now / index_now
    ratio_then = breadth_then / index_then
    change = (ratio_now - ratio_then) / ratio_then
    if abs(change) < MIN_PARTICIPATION_DIVERGENCE:
        # Inside the noise band. Saying nothing is honest; emitting "neutral"
        # would let an unmeasured signal count as a considered one.
        return None

    broadening = change > 0
    carried = (
        "shared by the average constituent"
        if broadening
        else "carried by a shrinking group of large names"
    )
    return Signal(
        signal_id="sig-participation-breadth",
        family=SignalFamily.PARTICIPATION,
        direction=Direction.BULLISH if broadening else Direction.BEARISH,
        strength=_clamp(Decimal("0.50") + abs(change) * Decimal("25")),
        as_of=as_of,
        source=(
            f"alpaca:daily_bars:{PARTICIPATION_SYMBOL}_vs_index_"
            f"{PARTICIPATION_SESSIONS}_session_ratio"
        ),
        summary=(
            f"Equal-weight {PARTICIPATION_SYMBOL} has moved {change:+.4f} against the "
            f"cap-weighted index over {PARTICIPATION_SESSIONS} completed sessions, so "
            f"participation is {'broadening' if broadening else 'narrowing'}: the move is "
            f"{carried}."
        ),
    )


def build_signals(
    bars: list[Bar],
    atm_iv: Decimal | None,
    as_of: datetime,
    participation_bars: list[Bar] | None = None,
) -> list[Signal]:
    """Derive the H0 signal set. Returns ``[]`` when structure does not qualify."""
    if len(bars) < MIN_BARS_REQUIRED:
        return []

    closes = [bar.close for bar in bars]
    fast = ema(closes, FAST_EMA)
    slow = ema(closes, SLOW_EMA)
    if fast is None or slow is None or slow == 0:
        return []

    last = bars[-1]
    separation = (fast - slow) / slow
    signals: list[Signal] = []

    if separation >= MIN_EMA_SEPARATION and last.close > fast:
        direction = Direction.BULLISH
    elif separation <= -MIN_EMA_SEPARATION and last.close < fast:
        direction = Direction.BEARISH
    else:
        return []

    # A retest means price came back to the moving average and held, not that it
    # merely trended. Without this the setup is "trend", not "trend + retest".
    recent = bars[-RETEST_LOOKBACK_SESSIONS:]
    tolerance = fast * RETEST_TOLERANCE
    if direction is Direction.BULLISH:
        touched = any(bar.low <= fast + tolerance for bar in recent)
    else:
        touched = any(bar.high >= fast - tolerance for bar in recent)
    if not touched:
        return []

    strength = _clamp(Decimal("0.55") + (abs(separation) * Decimal("8")))
    signals.append(
        Signal(
            signal_id="sig-structure-trend-retest",
            family=SignalFamily.STRUCTURE,
            direction=direction,
            strength=strength,
            as_of=as_of,
            source=f"alpaca:daily_bars:ema{FAST_EMA}_{SLOW_EMA}_retest",
            summary=(
                f"EMA{FAST_EMA} is {separation:.4f} from EMA{SLOW_EMA} in the "
                f"{direction.value} direction, price closed at {last.close} on the "
                f"{direction.value} side of EMA{FAST_EMA}, and price retested it "
                f"within the last {RETEST_LOOKBACK_SESSIONS} completed sessions."
            ),
        )
    )

    # Confirmation from a different instrument: the option market's own pricing.
    if atm_iv is not None:
        if atm_iv <= CALM_ATM_IV:
            signals.append(
                Signal(
                    signal_id="sig-volatility-regime",
                    family=SignalFamily.VOLATILITY_OPTIONS,
                    direction=direction,
                    strength=_clamp(
                        Decimal("0.50") + (CALM_ATM_IV - atm_iv) * Decimal("2")
                    ),
                    as_of=as_of,
                    source="alpaca:option_chain:atm_implied_volatility",
                    summary=(
                        f"At-the-money implied volatility is {atm_iv}, at or below the "
                        f"{CALM_ATM_IV} calm threshold, so the option market is not "
                        "pricing stress that would contradict continuation."
                    ),
                )
            )
        elif atm_iv >= STRESSED_ATM_IV:
            opposing = Direction.BEARISH if direction is Direction.BULLISH else Direction.BULLISH
            signals.append(
                Signal(
                    signal_id="sig-volatility-regime",
                    family=SignalFamily.VOLATILITY_OPTIONS,
                    direction=opposing,
                    strength=_clamp(
                        Decimal("0.55") + (atm_iv - STRESSED_ATM_IV) * Decimal("2")
                    ),
                    as_of=as_of,
                    source="alpaca:option_chain:atm_implied_volatility",
                    summary=(
                        f"At-the-money implied volatility is {atm_iv}, at or above the "
                        f"{STRESSED_ATM_IV} stress threshold, which contradicts a calm "
                        "continuation."
                    ),
                )
            )

    # Participation breadth. Emitted whether it agrees or not: the classifier
    # needs confirmation from a different family to qualify a setup, and it
    # needs contradictions to veto one. Breadth can supply either.
    if participation_bars:
        breadth = participation_signal(bars, participation_bars, as_of)
        if breadth is not None:
            signals.append(breadth)

    # Explicit counter-evidence: short-horizon momentum against the trend.
    if len(closes) > MOMENTUM_LONG_SESSIONS:
        short_return = (closes[-1] - closes[-1 - MOMENTUM_SHORT_SESSIONS]) / closes[
            -1 - MOMENTUM_SHORT_SESSIONS
        ]
        long_return = (closes[-1] - closes[-1 - MOMENTUM_LONG_SESSIONS]) / closes[
            -1 - MOMENTUM_LONG_SESSIONS
        ]
        aligned = short_return > 0 if direction is Direction.BULLISH else short_return < 0
        if not aligned:
            opposing = Direction.BEARISH if direction is Direction.BULLISH else Direction.BULLISH
            signals.append(
                Signal(
                    signal_id="sig-momentum-divergence",
                    family=SignalFamily.MOMENTUM,
                    direction=opposing,
                    strength=_clamp(Decimal("0.50") + abs(short_return) * Decimal("6")),
                    as_of=as_of,
                    source=(
                        f"alpaca:daily_bars:return_{MOMENTUM_SHORT_SESSIONS}"
                        f"_vs_{MOMENTUM_LONG_SESSIONS}"
                    ),
                    summary=(
                        f"The {MOMENTUM_SHORT_SESSIONS}-session return of "
                        f"{short_return:.4f} runs against the {MOMENTUM_LONG_SESSIONS}"
                        f"-session return of {long_return:.4f} and the {direction.value} "
                        "structure."
                    ),
                )
            )
    return signals


def build_option_chain(
    chain_read: ProviderRead, *, as_of: datetime, underlying_price: Decimal
) -> tuple[list[OptionQuoteSnapshot], Decimal | None, list[str]]:
    """Map option snapshots to contracts. Returns quotes, ATM IV, and stale fields."""
    quotes: list[OptionQuoteSnapshot] = []
    stale: list[str] = []
    tolerance = OPTION_FRESHNESS.get(chain_read.feed, timedelta(seconds=120))
    best_atm: tuple[Decimal, Decimal] | None = None

    for symbol, snap in iter_snapshot_items(chain_read):
        parsed = parse_occ_symbol(symbol)
        if parsed is None:
            continue
        expiration, option_type, strike = parsed
        quote = snap.get("latestQuote") or {}
        bid, ask = _dec(quote.get("bp")), _dec(quote.get("ap"))
        quote_time = quote.get("t")
        if bid is None or ask is None or not isinstance(quote_time, str):
            continue
        stamp = datetime.fromisoformat(quote_time.replace("Z", "+00:00")).astimezone(UTC)
        if stamp > as_of:
            # Never accept a quote from after the decision instant.
            continue
        if as_of - stamp > tolerance:
            stale.append(f"option_quote:{symbol}")
            continue
        greeks = snap.get("greeks") or {}
        implied = _dec(snap.get("impliedVolatility"))
        dte = (expiration - as_of.astimezone(UTC).date()).days
        if dte < 0:
            continue

        quotes.append(
            OptionQuoteSnapshot(
                contract_symbol=symbol,
                option_type=option_type,
                expiration=expiration,
                dte=dte,
                strike=strike,
                bid=bid,
                ask=ask,
                quote_as_of=stamp,
                feed=chain_read.feed,
                delta=_dec(greeks.get("delta")),
                implied_volatility=implied,
                open_interest=None,
                open_interest_date=None,
                recent_volume=None,
            )
        )
        if implied is not None and implied > 0:
            distance = abs(strike - underlying_price)
            if best_atm is None or distance < best_atm[0]:
                best_atm = (distance, implied)

    quotes.sort(key=lambda quote: (quote.expiration, quote.option_type.value, quote.strike))
    return quotes, (best_atm[1] if best_atm else None), stale


def build_snapshot(
    *,
    snapshot_id: str,
    symbol: str,
    account_read: ProviderRead,
    clock_read: ProviderRead,
    bars_read: ProviderRead,
    chain_read: ProviderRead,
    participation_read: ProviderRead | None = None,
    as_of: datetime | None = None,
) -> DecisionSnapshot:
    """Assemble the production snapshot, recording every data-quality finding."""
    now = as_of or datetime.now(UTC)
    missing: list[str] = []
    stale: list[str] = []
    errors: list[str] = []

    clock_payload = clock_read.payload if isinstance(clock_read.payload, dict) else {}
    raw_is_open = clock_payload.get("is_open")
    # Whether the market is open is what decides if the last daily bar is a close
    # or a bar still forming. A missing or non-boolean `is_open` used to fall
    # through `bool(None)` to "closed", so a degraded clock silently promoted a
    # partial session to a completed close - and every rule downstream believed
    # it. An unreadable clock is now a provider error, which halts new entries.
    clock_trusted = isinstance(raw_is_open, bool)
    if not clock_trusted:
        errors.append("clock:is_open_unreadable")
    market_open = bool(raw_is_open)
    if clock_read.source_time and now - clock_read.source_time > CLOCK_FRESHNESS:
        stale.append("clock")
        clock_trusted = False

    account_payload = account_read.payload if isinstance(account_read.payload, dict) else {}
    equity = _dec(account_payload.get("equity"))
    buying_power = _dec(account_payload.get("options_buying_power"))
    account_id = str(account_payload.get("account_number") or "")
    if equity is None or buying_power is None or not account_id:
        raise EvidenceError("account read is missing equity, buying power, or identifier")
    if now - account_read.received_time > ACCOUNT_FRESHNESS:
        stale.append("account")
    if str(account_payload.get("status")) != "ACTIVE":
        errors.append(f"account_status:{account_payload.get('status')}")

    bars = parse_bars(bars_read, as_of=now, market_open=market_open)
    if len(bars) < MIN_BARS_REQUIRED:
        missing.append(f"daily_bars:{len(bars)}_of_{MIN_BARS_REQUIRED}")
    if bars and (now.date() - bars[-1].session).days > MAX_SESSIONS_SINCE_LAST_BAR:
        stale.append(f"daily_bars:last_session_{bars[-1].session.isoformat()}")
    if not bars:
        raise EvidenceError("no completed daily bars available")
    underlying_price = bars[-1].close
    underlying_session = bars[-1].session
    # `parse_bars` removes the forming bar, but it can only do that when the
    # clock was readable. Without one, the last bar may be a partial session, so
    # the snapshot says the source is unknown instead of asserting a close.
    underlying_source = (
        PriceSource.COMPLETED_DAILY_CLOSE if clock_trusted else PriceSource.UNKNOWN
    )

    quotes, atm_iv, chain_stale = build_option_chain(
        chain_read, as_of=now, underlying_price=underlying_price
    )
    if not quotes:
        missing.append("option_chain")
    # Individual stale contracts are normal in a wide chain; only record the
    # finding when nothing tradeable survived.
    if chain_stale and not quotes:
        stale.extend(chain_stale[:5])

    # Breadth is optional by design: it must never be able to fail a decision
    # that would otherwise be sound. A missing or broken participation read
    # costs the setup one possible confirmer, which is a smaller harm than an
    # outage on a second symbol halting the strategy.
    participation_bars: list[Bar] = []
    if participation_read is not None:
        try:
            participation_bars = parse_bars(
                participation_read, as_of=now, market_open=market_open
            )
        except EvidenceError:
            errors.append(f"{PARTICIPATION_SYMBOL.lower()}:bars_unreadable")
    signals = (
        build_signals(bars, atm_iv, now, participation_bars) if not missing else []
    )

    return DecisionSnapshot(
        snapshot_id=snapshot_id,
        as_of=now,
        symbol=symbol,
        underlying_price=underlying_price,
        account=AccountSnapshot(
            account_id=account_id,
            as_of=account_read.received_time,
            equity=equity,
            options_buying_power=buying_power,
            is_paper=True,
        ),
        signals=tuple(signals),
        option_chain=tuple(quotes),
        underlying_source=underlying_source,
        underlying_session=underlying_session,
        data_quality=DataQuality(
            missing_fields=tuple(missing),
            stale_fields=tuple(stale),
            provider_errors=tuple(errors),
        ),
    )
