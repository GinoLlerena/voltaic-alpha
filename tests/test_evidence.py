"""Phase 2: read-only evidence construction, freshness, and look-ahead protection."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from options_alpha_lab.architecture.contracts import (
    Direction,
    OptionQuoteSnapshot,
    OptionType,
    SetupCandidate,
    SetupFamily,
    Signal,
    SignalFamily,
    Thesis,
)
from options_alpha_lab.components import DeterministicSpreadSelector
from options_alpha_lab.evidence import (
    PARTICIPATION_SESSIONS,
    Bar,
    build_option_chain,
    build_signals,
    ema,
    parse_bars,
    parse_occ_symbol,
    participation_signal,
)
from options_alpha_lab.providers.alpaca_readonly import (
    EntitlementError,
    ProviderError,
    ProviderRead,
    ReadOnlyAlpacaClient,
)

AS_OF = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)


def bars_read(sessions: list[tuple[str, str]]) -> ProviderRead:
    return ProviderRead(
        provider="alpaca",
        endpoint="/v2/stocks/SPY/bars",
        feed="sip",
        source_time=AS_OF,
        received_time=AS_OF,
        pages=1,
        payload={
            "symbol": "SPY",
            "bars": [
                {"t": f"{day}T04:00:00Z", "o": close, "h": close, "l": close,
                 "c": close, "v": "1000000"}
                for day, close in sessions
            ],
        },
    )


def rising(n: int, start: float = 500.0, step: float = 1.0) -> list[tuple[str, str]]:
    base = date(2026, 1, 1)
    return [
        ((base + timedelta(days=i)).isoformat(), f"{start + i * step:.2f}") for i in range(n)
    ]


class OccParsingTests(unittest.TestCase):
    def test_parses_a_valid_symbol(self) -> None:
        self.assertEqual(
            parse_occ_symbol("SPY260918C00640000"),
            (date(2026, 9, 18), OptionType.CALL, Decimal("640")),
        )

    def test_parses_a_put_and_a_fractional_strike(self) -> None:
        parsed = parse_occ_symbol("SPY260918P00642500")
        assert parsed is not None
        self.assertIs(parsed[1], OptionType.PUT)
        self.assertEqual(parsed[2], Decimal("642.5"))

    def test_returns_none_rather_than_guessing(self) -> None:
        for symbol in ("", "SPY", "SPY26091XC00640000", "260918C00640000"):
            with self.subTest(symbol=symbol):
                self.assertIsNone(parse_occ_symbol(symbol))


class LookAheadTests(unittest.TestCase):
    def test_forming_session_is_dropped_while_the_market_is_open(self) -> None:
        sessions = [("2026-08-26", "100.00"), ("2026-08-27", "101.00"), ("2026-08-28", "102.00")]
        bars = parse_bars(bars_read(sessions), as_of=AS_OF, market_open=True)
        self.assertEqual([bar.session for bar in bars][-1], date(2026, 8, 27))

    def test_completed_session_is_kept_once_the_market_is_closed(self) -> None:
        sessions = [("2026-08-27", "101.00"), ("2026-08-28", "102.00")]
        bars = parse_bars(bars_read(sessions), as_of=AS_OF, market_open=False)
        self.assertEqual([bar.session for bar in bars][-1], date(2026, 8, 28))

    def test_option_quote_from_after_the_decision_instant_is_discarded(self) -> None:
        read = ProviderRead(
            provider="alpaca",
            endpoint="/v1beta1/options/snapshots/SPY",
            feed="indicative",
            source_time=AS_OF,
            received_time=AS_OF,
            pages=1,
            payload={
                "underlying": "SPY",
                "snapshots": {
                    "SPY260918C00640000": {
                        "latestQuote": {
                            "bp": 1.0,
                            "ap": 1.1,
                            "t": (AS_OF + timedelta(seconds=5)).isoformat(),
                        }
                    }
                },
            },
        )
        quotes, _, _ = build_option_chain(read, as_of=AS_OF, underlying_price=Decimal("640"))
        self.assertEqual(quotes, [])


class FreshnessTests(unittest.TestCase):
    def chain(self, age_seconds: int, feed: str) -> ProviderRead:
        return ProviderRead(
            provider="alpaca",
            endpoint="/v1beta1/options/snapshots/SPY",
            feed=feed,
            source_time=AS_OF,
            received_time=AS_OF,
            pages=1,
            payload={
                "underlying": "SPY",
                "snapshots": {
                    "SPY260918C00640000": {
                        "latestQuote": {
                            "bp": 1.0,
                            "ap": 1.1,
                            "t": (AS_OF - timedelta(seconds=age_seconds)).isoformat(),
                        },
                        "impliedVolatility": 0.15,
                    }
                },
            },
        )

    def test_indicative_tolerates_two_minutes(self) -> None:
        quotes, _, stale = build_option_chain(
            self.chain(100, "indicative"), as_of=AS_OF, underlying_price=Decimal("640")
        )
        self.assertEqual(len(quotes), 1)
        self.assertEqual(stale, [])

    def test_indicative_rejects_beyond_its_tolerance(self) -> None:
        quotes, _, stale = build_option_chain(
            self.chain(200, "indicative"), as_of=AS_OF, underlying_price=Decimal("640")
        )
        self.assertEqual(quotes, [])
        self.assertTrue(stale)

    def test_opra_applies_a_tighter_tolerance_than_indicative(self) -> None:
        # The same 100-second-old quote is fresh on indicative and stale on OPRA.
        opra, _, _ = build_option_chain(
            self.chain(100, "opra"), as_of=AS_OF, underlying_price=Decimal("640")
        )
        self.assertEqual(opra, [])


class SignalTests(unittest.TestCase):
    def test_no_signals_without_enough_history(self) -> None:
        bars = parse_bars(bars_read(rising(30)), as_of=AS_OF, market_open=False)
        self.assertEqual(build_signals(bars, None, AS_OF), [])

    def test_uptrend_with_a_retest_qualifies_bullish(self) -> None:
        sessions = rising(120)
        bars = parse_bars(bars_read(sessions), as_of=AS_OF, market_open=False)
        signals = build_signals(bars, Decimal("0.15"), AS_OF)
        structure = [s for s in signals if s.family is SignalFamily.STRUCTURE]
        self.assertEqual(len(structure), 1)
        self.assertIs(structure[0].direction, Direction.BULLISH)

    def test_calm_volatility_confirms_and_stressed_volatility_opposes(self) -> None:
        bars = parse_bars(bars_read(rising(120)), as_of=AS_OF, market_open=False)
        calm = build_signals(bars, Decimal("0.15"), AS_OF)
        stressed = build_signals(bars, Decimal("0.40"), AS_OF)
        calm_vol = [s for s in calm if s.family is SignalFamily.VOLATILITY_OPTIONS][0]
        stressed_vol = [s for s in stressed if s.family is SignalFamily.VOLATILITY_OPTIONS][0]
        self.assertIs(calm_vol.direction, Direction.BULLISH)
        self.assertIs(stressed_vol.direction, Direction.BEARISH)

    def test_confirmation_comes_from_a_different_family_than_structure(self) -> None:
        bars = parse_bars(bars_read(rising(120)), as_of=AS_OF, market_open=False)
        signals = build_signals(bars, Decimal("0.15"), AS_OF)
        families = {s.family for s in signals if s.direction is Direction.BULLISH}
        self.assertIn(SignalFamily.STRUCTURE, families)
        self.assertTrue(families - {SignalFamily.STRUCTURE})

    def test_ema_matches_a_hand_computed_value(self) -> None:
        values = [Decimal(x) for x in (1, 2, 3, 4, 5, 6)]
        # SMA seed over 3 = 2; then 2 + (4-2)*0.5 = 3, 3 + (5-3)*0.5 = 4, 4 + (6-4)*0.5 = 5
        self.assertEqual(ema(values, 3), Decimal("5"))

    def test_ema_returns_none_below_its_period(self) -> None:
        self.assertIsNone(ema([Decimal(1), Decimal(2)], 5))


class ParticipationBreadthTests(unittest.TestCase):
    """Breadth, from equal-weight against cap-weight.

    This existed in the committed fixtures for two days before it existed in
    the live path: `sig-participation-breadth` appeared in every demo snapshot
    while `build_signals` could not produce one from real data. A judge reading
    the evidence would have seen a setup confirmed by a signal the running
    system never generates.
    """

    def series(self, closes: list[float]) -> list[Bar]:
        base = date(2026, 1, 1)
        return [
            Bar(base + timedelta(days=i), Decimal(str(c)), Decimal(str(c)),
                Decimal(str(c)), Decimal(str(c)), Decimal("1000000"))
            for i, c in enumerate(closes)
        ]

    def test_the_average_stock_keeping_up_reads_as_broadening(self) -> None:
        n = PARTICIPATION_SESSIONS + 5
        index = self.series([100.0 + i for i in range(n)])
        # Equal-weight outruns cap-weight: the move is shared.
        breadth = self.series([100.0 + i * 1.5 for i in range(n)])
        signal = participation_signal(index, breadth, AS_OF)
        assert signal is not None
        self.assertIs(signal.family, SignalFamily.PARTICIPATION)
        self.assertIs(signal.direction, Direction.BULLISH)
        self.assertIn("broadening", signal.summary)

    def test_a_move_carried_by_mega_caps_reads_as_narrowing(self) -> None:
        n = PARTICIPATION_SESSIONS + 5
        index = self.series([100.0 + i * 1.5 for i in range(n)])
        breadth = self.series([100.0 + i * 0.2 for i in range(n)])
        signal = participation_signal(index, breadth, AS_OF)
        assert signal is not None
        self.assertIs(signal.direction, Direction.BEARISH)
        self.assertIn("narrowing", signal.summary)

    def test_movement_inside_the_noise_band_says_nothing(self) -> None:
        # An unmeasured signal must not be able to count as a considered one.
        n = PARTICIPATION_SESSIONS + 5
        flat = self.series([100.0 + i for i in range(n)])
        self.assertIsNone(participation_signal(flat, flat, AS_OF))

    def test_it_declines_rather_than_guessing_without_history(self) -> None:
        short = self.series([100.0, 101.0, 102.0])
        long = self.series([100.0 + i for i in range(PARTICIPATION_SESSIONS + 5)])
        self.assertIsNone(participation_signal(long, short, AS_OF))
        self.assertIsNone(participation_signal(short, long, AS_OF))

    def test_sessions_are_paired_by_date_not_by_position(self) -> None:
        # The two series can disagree about which days exist - a halt, a late
        # bar, a provider gap. Pairing by index would compare different days
        # and report a divergence that never happened.
        n = PARTICIPATION_SESSIONS + 6
        index = self.series([100.0 + i for i in range(n)])
        breadth = self.series([100.0 + i for i in range(n)])
        gapped = [b for b in breadth if b.session != breadth[3].session]
        self.assertIsNone(
            participation_signal(index, gapped, AS_OF),
            "identical series with one missing day must still read as no divergence",
        )

    def test_breadth_reaches_the_live_signal_set(self) -> None:
        # The gap itself: build_signals must be able to emit it.
        bars = parse_bars(bars_read(rising(120)), as_of=AS_OF, market_open=False)
        breadth = self.series(
            [float(b.close) * (1.0 + 0.0006 * i) for i, b in enumerate(bars)]
        )
        breadth = [
            Bar(b.session, b.open, b.high, b.low, c.close, b.volume)
            for b, c in zip(bars, breadth, strict=False)
        ]
        signals = build_signals(bars, Decimal("0.15"), AS_OF, breadth)
        families = {s.family for s in signals}
        self.assertIn(SignalFamily.PARTICIPATION, families)

    def test_absent_breadth_costs_a_confirmer_and_never_fails_the_decision(self) -> None:
        # An outage on a second symbol must not halt the strategy on the first.
        bars = parse_bars(bars_read(rising(120)), as_of=AS_OF, market_open=False)
        with_none = build_signals(bars, Decimal("0.15"), AS_OF, None)
        with_empty = build_signals(bars, Decimal("0.15"), AS_OF, [])
        self.assertEqual([s.signal_id for s in with_none], [s.signal_id for s in with_empty])
        self.assertTrue(any(s.family is SignalFamily.STRUCTURE for s in with_none))


class SelectorPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.setup = SetupCandidate(
            setup_id="s1",
            family=SetupFamily.TREND_CONTINUATION_RETEST,
            direction=Direction.BULLISH,
            evidence_ids=("a",),
            invalidation_conditions=("x",),
        )
        self.thesis = Thesis(
            direction=Direction.BULLISH,
            confidence=Decimal("0.7"),
            evidence_ids=("a",),
            counter_evidence_ids=(),
            invalidation_conditions=("x",),
            reasoning_summary="test",
        )

    def snapshot(self, quotes: list[OptionQuoteSnapshot], price: str = "100.00"):
        from options_alpha_lab.architecture.contracts import AccountSnapshot, DecisionSnapshot

        return DecisionSnapshot(
            snapshot_id="s",
            as_of=AS_OF,
            symbol="SPY",
            underlying_price=Decimal(price),
            account=AccountSnapshot(
                account_id="PA",
                as_of=AS_OF,
                equity=Decimal("100000"),
                options_buying_power=Decimal("50000"),
                is_paper=True,
            ),
            signals=(
                Signal(
                    signal_id="a",
                    family=SignalFamily.STRUCTURE,
                    direction=Direction.BULLISH,
                    strength=Decimal("0.7"),
                    as_of=AS_OF,
                    source="s",
                    summary="s",
                ),
            ),
            option_chain=tuple(quotes),
        )

    def quote(self, strike: str, bid: str, ask: str, delta: str | None) -> OptionQuoteSnapshot:
        return OptionQuoteSnapshot(
            contract_symbol=f"SPY260918C00{int(float(strike) * 1000):06d}",
            option_type=OptionType.CALL,
            expiration=date(2026, 9, 18),
            dte=21,
            strike=Decimal(strike),
            bid=Decimal(bid),
            ask=Decimal(ask),
            quote_as_of=AS_OF,
            feed="indicative",
            delta=None if delta is None else Decimal(delta),
        )

    def test_missing_delta_fails_closed(self) -> None:
        quotes = [
            self.quote("100", "5.00", "5.10", None),
            self.quote("105", "2.00", "2.10", None),
        ]
        selected = DeterministicSpreadSelector().select(
            self.snapshot(quotes), self.setup, self.thesis
        )
        self.assertIsNone(selected)

    def test_width_below_the_floor_is_rejected(self) -> None:
        # Floor is 0.5% of a 100.00 underlying = 0.50; this pair is 0.25 wide.
        quotes = [
            self.quote("100", "5.00", "5.10", "0.60"),
            self.quote("100.25", "4.90", "5.00", "0.35"),
        ]
        self.assertIsNone(
            DeterministicSpreadSelector().select(self.snapshot(quotes), self.setup, self.thesis)
        )

    def test_debit_above_the_width_limit_is_rejected(self) -> None:
        # 5.10 ask - 2.00 bid = 3.10 debit on a 5.00 width is 0.62, over the 0.60 cap.
        quotes = [
            self.quote("100", "5.00", "5.10", "0.60"),
            self.quote("105", "2.00", "2.10", "0.35"),
        ]
        self.assertIsNone(
            DeterministicSpreadSelector().select(self.snapshot(quotes), self.setup, self.thesis)
        )

    def test_narrowest_eligible_width_wins(self) -> None:
        quotes = [
            self.quote("100", "5.00", "5.05", "0.60"),
            self.quote("105", "2.50", "2.60", "0.35"),
            self.quote("110", "1.00", "1.10", "0.26"),
        ]
        selected = DeterministicSpreadSelector().select(
            self.snapshot(quotes), self.setup, self.thesis
        )
        assert selected is not None
        self.assertTrue(selected.short_contract_symbol.endswith("105000"))


class ReadOnlyClientTests(unittest.TestCase):
    def client(self, handler) -> ReadOnlyAlpacaClient:
        transport = httpx.MockTransport(handler)
        return ReadOnlyAlpacaClient(
            "key", "secret", client=httpx.Client(transport=transport)
        )

    def test_pagination_is_exhausted_not_truncated(self) -> None:
        pages = {
            None: {"bars": [{"t": "2026-01-01T04:00:00Z"}], "next_page_token": "p2"},
            "p2": {"bars": [{"t": "2026-01-02T04:00:00Z"}], "next_page_token": None},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=pages[request.url.params.get("page_token")])

        read = self.client(handler).daily_bars("SPY")
        self.assertEqual(read.pages, 2)
        self.assertEqual(len(read.payload["bars"]), 2)

    def test_unsigned_opra_is_reported_as_an_entitlement_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"message": "OPRA agreement is not signed"})

        with self.assertRaises(EntitlementError):
            self.client(handler).option_chain(
                "SPY", expiration_gte="2026-09-01", expiration_lte="2026-10-01"
            )

    def test_feed_detection_falls_back_to_the_entitled_feed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"message": "OPRA agreement is not signed"})

        self.assertEqual(self.client(handler).detect_option_feed("SPY"), "indicative")

    def test_provider_failure_raises_rather_than_returning_a_default(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="upstream exploded")

        with self.assertRaises(ProviderError):
            self.client(handler).account()

    def test_every_read_carries_provenance_and_a_payload_hash(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"timestamp": "2026-08-28T15:30:00Z", "is_open": True})

        read = self.client(handler).clock()
        self.assertEqual(read.provider, "alpaca")
        self.assertTrue(read.payload_hash.startswith("sha256:"))
        self.assertIsNotNone(read.source_time)
        self.assertEqual(read.pages, 1)


class BarHelperTests(unittest.TestCase):
    def test_bar_is_ordered_oldest_first(self) -> None:
        out_of_order = [("2026-01-03", "3.00"), ("2026-01-01", "1.00"), ("2026-01-02", "2.00")]
        bars = parse_bars(bars_read(out_of_order), as_of=AS_OF, market_open=False)
        self.assertEqual([b.session.day for b in bars], [1, 2, 3])
        self.assertIsInstance(bars[0], Bar)


if __name__ == "__main__":
    unittest.main()
