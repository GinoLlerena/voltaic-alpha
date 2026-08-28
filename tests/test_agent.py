"""The autonomous cycle, driven entirely offline."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from options_alpha_lab.agent import (
    OpenPosition,
    TradingAgent,
    halt_state_for,
    invalidation_level_from,
    spread_value,
)
from options_alpha_lab.architecture.contracts import Direction, ExecutionState
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.gateway import ExecutionGateway
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent
from options_alpha_lab.providers.alpaca_readonly import ProviderError, ProviderRead

NOW = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)
EXPIRY = (NOW + timedelta(days=25)).date()

BASE_ENV = {
    "BOT_MODE": "observe",
    "ALPACA_PAPER_TRADE": "true",
    "ALPACA_TRADING_ENABLED": "false",
    "REQUIRE_OPERATOR_APPROVAL": "true",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
}
WRITE_ENV = dict(
    BASE_ENV, BOT_MODE="paper_execute", ALPACA_TRADING_ENABLED="true"
)


def occ(strike: int, kind: str = "C") -> str:
    return f"SPY{EXPIRY.strftime('%y%m%d')}{kind}{strike * 1000:08d}"


LONG, SHORT = occ(619), occ(624)


def read(payload: Any, feed: str = "indicative") -> ProviderRead:
    return ProviderRead(
        provider="alpaca", endpoint="/test", feed=feed,
        source_time=NOW, received_time=NOW, pages=1, payload=payload,
    )


class FakeClient:
    """Returns provider-shaped payloads so the real evidence path is exercised."""

    option_feed = "indicative"
    stock_feed = "sip"

    def __init__(self, *, market_open: bool = True, fail: Exception | None = None,
                 quotes: dict[str, tuple[str, str]] | None = None) -> None:
        self.market_open = market_open
        self.fail = fail
        # `quotes or {...}` would swallow an intentionally empty chain, since an
        # empty dict is falsy. The empty case is exactly what one test needs.
        self.quotes = (
            {LONG: ("12.40", "12.60"), SHORT: ("9.60", "9.80")} if quotes is None else quotes
        )

    def clock(self) -> ProviderRead:
        if self.fail:
            raise self.fail
        return read({"is_open": self.market_open, "timestamp": NOW.isoformat()})

    def account(self) -> ProviderRead:
        return read({
            "account_number": "PA-TEST-REDACTED", "status": "ACTIVE",
            "equity": "100000", "options_buying_power": "50000",
        })

    def daily_bars(self, symbol: str) -> ProviderRead:
        # Bars must run up to the current session, or the freshness rule flags
        # them stale and the decision terminates before any setup is considered.
        start = NOW.date() - timedelta(days=120)
        bars = [
            {"t": f"{(start + timedelta(days=i)).isoformat()}T04:00:00Z",
             "o": f"{500 + i:.2f}", "h": f"{500 + i:.2f}", "l": f"{500 + i:.2f}",
             "c": f"{500 + i:.2f}", "v": "1000000"}
            for i in range(121)
        ]
        return read({"symbol": symbol, "bars": bars}, feed="sip")

    def option_chain(self, symbol: str, *, expiration_gte: str, expiration_lte: str
                     ) -> ProviderRead:
        deltas = {LONG: 0.60, SHORT: 0.32}
        snaps = {
            sym: {
                "latestQuote": {"bp": float(bid), "ap": float(ask),
                                "t": (NOW - timedelta(seconds=20)).isoformat()},
                "impliedVolatility": 0.15,
                "greeks": {"delta": deltas[sym]},
            }
            for sym, (bid, ask) in self.quotes.items()
        }
        return read({"underlying": symbol, "snapshots": snaps})


class FakeBroker:
    def __init__(self, *, open_strategies: int = 0) -> None:
        self.open_strategies = open_strategies
        self.submits: list[dict[str, Any]] = []

    def resolved_endpoint(self) -> str:
        return "https://paper-api.alpaca.markets"

    def open_strategy_count(self) -> int:
        return self.open_strategies

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        self.submits.append(body)
        return {"id": f"brk-{len(self.submits)}", "status": "accepted"}

    def get_by_client_order_id(self, cid: str) -> dict[str, Any] | None:
        return None


def agent(env: dict[str, str], *, client: FakeClient | None = None,
          broker: FakeBroker | None = None, approval: str | None = None,
          state: ExecutionState = ExecutionState.NORMAL) -> TradingAgent:
    settings = load_settings(env)
    gw = None
    if broker is not None:
        gw = ExecutionGateway(broker, settings, execution_state=state, clock=lambda: NOW)
    return TradingAgent(
        settings, client=client or FakeClient(), gateway=gw,  # type: ignore[arg-type]
        clock=lambda: NOW, operator_approval=approval,
    )


def open_position() -> OpenPosition:
    return OpenPosition(
        intent=OrderIntent(
            decision_hash="sha256:x", strategy=__import__(
                "options_alpha_lab.architecture.contracts", fromlist=["SpreadStrategy"]
            ).SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
            legs=(IntentLeg(LONG, 1, "buy", "buy_to_open"),
                  IntentLeg(SHORT, 1, "sell", "sell_to_open")),
            strategy_quantity=1, limit_price=Decimal("3.00"),
            approval_reference="risk", created_at=NOW,
            expires_at=NOW + timedelta(seconds=90),
        ),
        direction=Direction.BULLISH, entry_debit=Decimal("3.00"), width=Decimal("5.00"),
        quantity=1, invalidation_level=Decimal("600.00"), expiration=EXPIRY,
    )


class ObservationTests(unittest.TestCase):
    def test_closed_market_takes_no_action(self) -> None:
        result = agent(BASE_ENV, client=FakeClient(market_open=False)).tick()
        self.assertEqual(result.action, "MARKET_CLOSED")

    def test_provider_failure_takes_no_action(self) -> None:
        result = agent(BASE_ENV, client=FakeClient(fail=ProviderError("boom"))).tick()
        self.assertEqual(result.action, "OBSERVE_FAILED")

    def test_observe_mode_reaches_a_candidate_but_never_writes(self) -> None:
        broker = FakeBroker()
        result = agent(BASE_ENV, broker=broker).tick()
        self.assertEqual(result.action, "TRADE_CANDIDATE")
        self.assertEqual(broker.submits, [], "observe mode must not write")


class ExitsBeforeEntriesTests(unittest.TestCase):
    def test_an_open_position_is_managed_before_any_new_entry(self) -> None:
        # A tick that entered before checking the open position could hold a
        # loser through its own stop while spending the single strategy slot.
        broker = FakeBroker(open_strategies=1)
        a = agent(WRITE_ENV, broker=broker, approval="operator:test")
        a.open_position = open_position()
        result = a.tick()
        self.assertIn(result.action, {"POSITION_HELD", "POSITION_CLOSED", "POSITION_REVIEW"})
        self.assertNotEqual(result.action, "POSITION_OPENED")

    def test_stop_loss_closes_and_clears_the_position(self) -> None:
        broker = FakeBroker(open_strategies=1)
        a = agent(WRITE_ENV, broker=broker,
                  client=FakeClient(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}))
        a.open_position = open_position()
        result = a.tick()
        self.assertEqual(result.action, "POSITION_CLOSED")
        self.assertIsNone(a.open_position)
        self.assertEqual(len(broker.submits), 1)

    def test_a_close_is_not_blocked_by_the_one_strategy_guard(self) -> None:
        # The position being closed occupies the slot; blocking on that would
        # make every exit impossible.
        broker = FakeBroker(open_strategies=1)
        a = agent(WRITE_ENV, broker=broker,
                  client=FakeClient(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}))
        a.open_position = open_position()
        self.assertEqual(a.tick().action, "POSITION_CLOSED")

    def test_a_close_is_not_blocked_by_a_halt_or_missing_approval(self) -> None:
        broker = FakeBroker(open_strategies=1)
        a = agent(WRITE_ENV, broker=broker, approval=None,
                  state=ExecutionState.NO_NEW_RISK,
                  client=FakeClient(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}))
        a.open_position = open_position()
        self.assertEqual(a.tick().action, "POSITION_CLOSED")

    def test_unmeasurable_position_is_flagged_not_silently_held(self) -> None:
        a = agent(WRITE_ENV, broker=FakeBroker(open_strategies=1),
                  client=FakeClient(quotes={}))
        a.open_position = open_position()
        result = a.tick()
        self.assertEqual(result.action, "POSITION_REVIEW")


class ApprovalGateTests(unittest.TestCase):
    def test_without_approval_an_entry_is_refused(self) -> None:
        broker = FakeBroker()
        result = agent(WRITE_ENV, broker=broker, approval=None).tick()
        self.assertEqual(result.action, "ENTRY_REFUSED")
        self.assertIn("REQUIRE_OPERATOR_APPROVAL", result.detail)
        self.assertEqual(broker.submits, [])

    def test_with_approval_an_entry_opens(self) -> None:
        broker = FakeBroker()
        a = agent(WRITE_ENV, broker=broker, approval="operator:gino:2026-08-28")
        result = a.tick()
        self.assertEqual(result.action, "POSITION_OPENED")
        self.assertEqual(len(broker.submits), 1)
        self.assertIsNotNone(a.open_position)

    def test_approval_disabled_allows_a_fully_autonomous_entry(self) -> None:
        broker = FakeBroker()
        env = dict(WRITE_ENV, REQUIRE_OPERATOR_APPROVAL="false")
        result = agent(env, broker=broker).tick()
        self.assertEqual(result.action, "POSITION_OPENED")


class HelperTests(unittest.TestCase):
    def test_spread_value_is_the_conservative_close(self) -> None:
        from options_alpha_lab.snapshot_io import load_snapshot

        snap = load_snapshot("fixtures/h0/spy_qualified.snapshot.json")
        value = spread_value(snap, "SPY260918C00640000", "SPY260918C00645000")
        # long bid 12.40 minus short ask 9.80
        self.assertEqual(value, Decimal("2.60"))

    def test_spread_value_is_none_when_a_leg_is_absent(self) -> None:
        from options_alpha_lab.snapshot_io import load_snapshot

        snap = load_snapshot("fixtures/h0/spy_qualified.snapshot.json")
        self.assertIsNone(spread_value(snap, "MISSING", "SPY260918C00645000"))

    def test_invalidation_level_is_recovered_from_the_condition_text(self) -> None:
        self.assertEqual(
            invalidation_level_from(("close below 631.63 invalidates the retest",)),
            Decimal("631.63"),
        )
        self.assertIsNone(invalidation_level_from(("loss of structure",)))

    def test_unusable_data_halts_new_risk_without_trapping_a_position(self) -> None:
        from options_alpha_lab.architecture.contracts import DataQuality
        from options_alpha_lab.snapshot_io import load_snapshot

        snap = load_snapshot("fixtures/h0/spy_qualified.snapshot.json")
        self.assertIs(halt_state_for(snap), ExecutionState.NORMAL)
        import dataclasses

        stale = dataclasses.replace(snap, data_quality=DataQuality(stale_fields=("account",)))
        self.assertIs(halt_state_for(stale), ExecutionState.NO_NEW_RISK)


if __name__ == "__main__":
    unittest.main()
