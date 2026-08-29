"""The autonomous cycle, driven entirely offline."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from options_alpha_lab.agent import (
    TradingAgent,
    halt_state_for,
    invalidation_level_from,
    spread_value,
)
from options_alpha_lab.architecture.contracts import Direction, ExecutionState
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.gateway import ExecutionGateway
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent
from options_alpha_lab.execution.lifecycle import (
    LifecycleStore,
    OrderState,
    PositionState,
    TypedInvalidation,
)
from options_alpha_lab.execution.reconcile import Reconciler
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.providers.alpaca_readonly import ProviderError, ProviderRead
from options_alpha_lab.replay import replay_paths

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


def entry_intent() -> OrderIntent:
    from options_alpha_lab.architecture.contracts import SpreadStrategy

    return OrderIntent(
        decision_hash="sha256:x",
        strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        legs=(IntentLeg(LONG, 1, "buy", "buy_to_open"),
              IntentLeg(SHORT, 1, "sell", "sell_to_open")),
        strategy_quantity=1, limit_price=Decimal("3.39"),
        approval_reference="risk", created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )


class DurableAgentCase(unittest.TestCase):
    """Builds an agent backed by a real lifecycle store, as production is."""

    def build(self, env: dict[str, str], *, client: FakeClient | None = None,
              broker: FakeBroker | None = None, approval: str | None = "operator:test",
              state: ExecutionState = ExecutionState.NORMAL,
              reconcile_positions: list[dict[str, Any]] | None = None):
        import tempfile
        from pathlib import Path

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from options_alpha_lab.persistence.models import Decision

        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "agent.db"
        settings = load_settings(dict(env, DATABASE_URL=f"sqlite+pysqlite:///{db}"))
        engine = build_engine(settings)
        create_schema(engine)
        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")], settings, create=False)
        with Session(engine) as session:
            self.decision_id = session.scalars(select(Decision)).first().id

        self.store = LifecycleStore(engine)
        self.broker = broker or FakeBroker()
        gateway = ExecutionGateway(self.broker, settings, execution_state=state,
                                   clock=lambda: NOW)
        reconciler = None
        if reconcile_positions is not None:
            from test_reconcile import FakeBroker as ReconBroker

            reconciler = Reconciler(ReconBroker(positions=reconcile_positions), self.store)
        agent = TradingAgent(
            settings, client=client or FakeClient(), gateway=gateway,
            store=self.store, reconciler=reconciler, clock=lambda: NOW,
            operator_approval=approval,
        )
        agent.decision_row_id = self.decision_id
        return agent

    def tearDown(self) -> None:
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def open_position(self, *, avg_debit: str = "3.13", filled_at=None) -> str:
        """An OPEN position established the only legal way: from reconciled fills."""
        intent = entry_intent()
        order_id, position_id = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW),
            direction=Direction.BULLISH, long_symbol=LONG, short_symbol=SHORT,
            expiration=NOW + timedelta(days=25), width=Decimal("5.00"),
            max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("600.00"), Direction.BULLISH, "daily_close"),
            now=NOW,
        )
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal(avg_debit), now=NOW,
        )
        self.store.apply_entry_outcome(
            position_id, state=OrderState.FILLED, filled_quantity=1,
            avg_debit=Decimal(avg_debit), now=filled_at or NOW,
        )
        return position_id


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


class ExitsBeforeEntriesTests(DurableAgentCase):
    def test_an_open_position_is_managed_before_any_new_entry(self) -> None:
        agent = self.build(WRITE_ENV)
        self.open_position()
        result = agent.tick()
        self.assertIn(result.action, {"POSITION_HELD", "CLOSE_SUBMITTED", "POSITION_REVIEW"})
        self.assertNotEqual(result.action, "ENTRY_SUBMITTED")

    def test_stop_loss_submits_a_close_but_does_not_report_it_closed(self) -> None:
        # EXIT-001: a submitted close is CLOSING, not CLOSED.
        agent = self.build(
            WRITE_ENV,
            client=FakeClient(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}),
        )
        position_id = self.open_position()
        result = agent.tick()
        self.assertEqual(result.action, "CLOSE_SUBMITTED")
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.CLOSING)
        self.assertTrue(managed.has_confirmed_exposure, "ownership is retained")

    def test_exit_economics_use_the_filled_debit_not_the_limit(self) -> None:
        # Entry filled at 2.00; the 50% stop is 1.00. Priced off the 3.39 limit
        # the stop would be 1.70 and this position would close early.
        agent = self.build(
            WRITE_ENV,
            client=FakeClient(quotes={LONG: ("1.60", "1.70"), SHORT: ("0.30", "0.40")}),
        )
        self.open_position(avg_debit="2.00")
        result = agent.tick()
        self.assertEqual(result.action, "POSITION_HELD")
        assert result.exit is not None
        # The stop is 1.00, which is 50% of the 2.00 fill. Priced off the 3.39
        # limit it would be 1.70 and the 1.20 value would have closed the trade.
        self.assertIn("1.00 stop", result.exit.reason)

    def test_a_close_is_not_blocked_by_the_one_strategy_guard_or_a_halt(self) -> None:
        agent = self.build(
            WRITE_ENV, broker=FakeBroker(open_strategies=1), approval=None,
            state=ExecutionState.NO_NEW_RISK,
            client=FakeClient(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}),
        )
        self.open_position()
        self.assertEqual(agent.tick().action, "CLOSE_SUBMITTED")

    def test_missing_quotes_do_not_suppress_invalidation(self) -> None:
        # EXIT-004: invalidation needs no premium, so an empty chain must not hide it.
        agent = self.build(WRITE_ENV, client=FakeClient(quotes={}))
        self.open_position()
        result = agent.tick()
        assert result.exit is not None
        self.assertTrue(result.exit.value_unmeasurable)
        self.assertEqual(result.action, "POSITION_REVIEW")

    def test_an_unreadable_premium_raises_an_incident_and_halts_new_risk(self) -> None:
        agent = self.build(WRITE_ENV, client=FakeClient(quotes={}))
        self.open_position()
        agent.tick()
        kinds = [i.kind for i in self.store.open_incidents()]
        self.assertIn("unmeasurable_position_value", kinds)
        self.assertIs(agent.execution_state, ExecutionState.NO_NEW_RISK)

    def test_a_pending_position_is_not_managed_as_if_it_were_open(self) -> None:
        agent = self.build(WRITE_ENV)
        intent = entry_intent()
        self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=25),
            width=Decimal("5.00"), max_loss=Decimal("339.00"), invalidation=None, now=NOW,
        )
        self.assertIsNone(agent.active_position(), "PENDING is not managed exposure")


class NoDuplicateCloseTests(DurableAgentCase):
    """EXIT-006: a working close must not trigger a second one."""

    def test_a_working_close_is_monitored_not_resubmitted(self) -> None:
        agent = self.build(
            WRITE_ENV,
            client=FakeClient(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}),
        )
        position_id = self.open_position()

        first = agent.tick()
        self.assertEqual(first.action, "CLOSE_SUBMITTED")
        after_first = len(self.broker.submits)

        second = agent.tick()
        self.assertEqual(second.action, "CLOSE_WORKING")
        self.assertEqual(len(self.broker.submits), after_first,
                         "a working close must not produce a duplicate")

        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.CLOSING)
        self.assertTrue(managed.has_confirmed_exposure, "still owned")


class ApprovalGateTests(DurableAgentCase):
    def test_without_approval_an_entry_is_refused_and_creates_no_exposure(self) -> None:
        agent = self.build(WRITE_ENV, approval=None)
        result = agent.tick()
        self.assertEqual(result.action, "ENTRY_REFUSED")
        self.assertEqual(self.broker.submits, [])
        self.assertEqual(self.store.active_positions(), [], "a refusal leaves no position")

    def test_with_approval_an_entry_is_submitted_not_opened(self) -> None:
        # EXIT-001: acceptance is not a fill, so no OPEN position appears.
        agent = self.build(WRITE_ENV, approval="operator:gino")
        result = agent.tick()
        self.assertEqual(result.action, "ENTRY_SUBMITTED")
        self.assertEqual(len(self.broker.submits), 1)
        active = self.store.active_positions()
        self.assertEqual(len(active), 1)
        self.assertIs(active[0].state, PositionState.PENDING)
        self.assertIsNone(active[0].avg_entry_debit)
        self.assertIsNone(agent.active_position())

    def test_an_ambiguous_submission_retains_responsibility(self) -> None:
        # The request was sent and the outcome is unknown. Abandoning the
        # position here would lose responsibility for exposure that may exist.
        class RaisingBroker(FakeBroker):
            def submit(self, body: dict[str, Any]) -> dict[str, Any]:
                raise RuntimeError("connection died mid-submit")

        agent = self.build(WRITE_ENV, broker=RaisingBroker(), approval="operator:gino")
        result = agent.tick()
        self.assertEqual(result.action, "ENTRY_AMBIGUOUS")
        active = self.store.active_positions()
        self.assertEqual(len(active), 1, "the durable record survives the failed send")
        self.assertIs(active[0].state, PositionState.INCIDENT)
        self.assertTrue(active[0].position_id, "still owned and still reconcilable")
        self.assertIn("ambiguous_entry_submission",
                      [i.kind for i in self.store.open_incidents()])
        self.assertIs(agent.execution_state, ExecutionState.NO_NEW_RISK)

    def test_a_preflight_refusal_creates_no_exposure(self) -> None:
        # Nothing was sent, so abandoning the record is correct here.
        agent = self.build(WRITE_ENV, approval=None)
        self.assertEqual(agent.tick().action, "ENTRY_REFUSED")
        self.assertEqual(self.store.active_positions(), [])


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




class ReconciliationHookTests(unittest.TestCase):
    """Item 2: the agent reconciles at startup and on every tick."""

    def build(self, broker_positions: list[dict[str, Any]] | None = None,
              raises: Exception | None = None):
        import tempfile
        from pathlib import Path

        from options_alpha_lab.execution.lifecycle import LifecycleStore
        from options_alpha_lab.execution.reconcile import Reconciler
        from options_alpha_lab.persistence.repository import build_engine, create_schema
        from options_alpha_lab.replay import replay_paths
        from test_reconcile import FakeBroker as ReconBroker

        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "a.db"
        settings = load_settings(dict(WRITE_ENV, DATABASE_URL=f"sqlite+pysqlite:///{db}"))
        engine = build_engine(settings)
        create_schema(engine)
        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")], settings, create=False)
        store = LifecycleStore(engine)
        recon_broker = ReconBroker(positions=broker_positions or [], raises=raises)
        exec_broker = FakeBroker()
        gw = ExecutionGateway(exec_broker, settings, clock=lambda: NOW)
        a = TradingAgent(
            settings, client=FakeClient(), gateway=gw,  # type: ignore[arg-type]
            reconciler=Reconciler(recon_broker, store),
            clock=lambda: NOW, operator_approval="operator:test",
        )
        return a, exec_broker, store

    def tearDown(self) -> None:
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def test_startup_reconciles_before_any_entry(self) -> None:
        agent_, _, _ = self.build()
        report = agent_.startup()
        assert report is not None
        self.assertTrue(report.clean)
        self.assertEqual(agent_.history[-1].action, "STARTUP_RECONCILE")

    def test_unclaimed_broker_exposure_halts_entries(self) -> None:
        agent_, broker, _ = self.build(
            broker_positions=[{"symbol": "SPY260918P00600000", "qty": "-1"}]
        )
        result = agent_.tick()
        self.assertEqual(result.action, "ENTRY_HALTED")
        self.assertEqual(broker.submits, [], "no order may be placed while unreconciled")
        self.assertIs(agent_.execution_state, ExecutionState.NO_NEW_RISK)

    def test_an_unreachable_broker_halts_entries(self) -> None:
        # Not knowing what we hold is not the same as holding nothing.
        agent_, broker, _ = self.build(raises=ConnectionError("network down"))
        result = agent_.tick()
        self.assertEqual(result.action, "ENTRY_HALTED")
        self.assertEqual(broker.submits, [])

    def test_the_halt_reaches_the_gateway_not_just_the_agent(self) -> None:
        agent_, _, _ = self.build(
            broker_positions=[{"symbol": "SPY260918P00600000", "qty": "-1"}]
        )
        agent_.tick()
        assert agent_.gateway is not None
        self.assertIs(agent_.gateway.execution_state, ExecutionState.NO_NEW_RISK)

    def test_a_clean_reconciliation_permits_an_entry(self) -> None:
        agent_, broker, _ = self.build()
        result = agent_.tick()
        self.assertEqual(result.action, "ENTRY_SUBMITTED")
        self.assertEqual(len(broker.submits), 1)




class EntryWindowTests(DurableAgentCase):
    """Item 6: an open market is not the same as an eligible entry window."""

    def calendar_with(self, close: str = "16:00"):
        from options_alpha_lab.calendar import TradingCalendar

        day = NOW.date().isoformat()
        return TradingCalendar.from_payload(
            {"sessions": [{"date": day, "open": "09:30", "close": close}]}
        )

    def test_an_entry_outside_the_window_is_refused_without_writing(self) -> None:
        # NOW is 15:30 UTC, which is 11:30 ET on a 13:00 early close: past the
        # 12:15 session-relative cutoff would be 12:16, so use a late clock.
        agent = self.build(WRITE_ENV)
        agent.calendar = self.calendar_with(close="11:00")
        result = agent.tick()
        self.assertEqual(result.action, "OUTSIDE_ENTRY_WINDOW")
        self.assertEqual(self.broker.submits, [])

    def test_an_entry_inside_the_window_proceeds(self) -> None:
        agent = self.build(WRITE_ENV)
        agent.calendar = self.calendar_with()
        self.assertEqual(agent.tick().action, "ENTRY_SUBMITTED")

    def test_an_open_position_is_still_managed_outside_the_window(self) -> None:
        # Monitoring and risk reduction must remain available after the cutoff.
        agent = self.build(
            WRITE_ENV,
            client=FakeClient(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}),
        )
        agent.calendar = self.calendar_with(close="11:00")
        self.open_position()
        self.assertEqual(agent.tick().action, "CLOSE_SUBMITTED")


if __name__ == "__main__":
    unittest.main()
