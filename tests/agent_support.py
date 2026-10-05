"""Shared builders for suites that drive the agent offline.

`CSA-010`: these lived in `test_agent.py`, and three other suites imported them
from there, so a test module doubled as a library. Nothing here is a test.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from options_alpha_lab.agent import (
    TradingAgent,
)
from options_alpha_lab.architecture.contracts import Direction, ExecutionState, PriceSource
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.gateway import ExecutionGateway
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent
from options_alpha_lab.execution.lifecycle import (
    LifecycleStore,
    OrderState,
    TypedInvalidation,
)
from options_alpha_lab.execution.reconcile import Reconciler
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.providers.alpaca_readonly import ProviderRead
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
                 quotes: dict[str, tuple[str, str]] | None = None,
                 clock_payload: dict[str, Any] | None = None,
                 clock_age_seconds: int = 0) -> None:
        self.market_open = market_open
        self.fail = fail
        #: Lets a test return a clock the snapshot cannot read `is_open` from.
        self.clock_payload = clock_payload
        #: A readable but stale clock: `is_open` is trustworthy as a fact about
        #: some past moment, and not as a fact about now.
        self.clock_age_seconds = clock_age_seconds
        #: Provider reads made. Lets a test assert that a clock which should
        #: have decided from a local read did not talk to a provider at all.
        self.calls = 0
        # `quotes or {...}` would swallow an intentionally empty chain, since an
        # empty dict is falsy. The empty case is exactly what one test needs.
        self.quotes = (
            {LONG: ("12.40", "12.60"), SHORT: ("9.60", "9.80")} if quotes is None else quotes
        )

    def clock(self) -> ProviderRead:
        self.calls += 1
        if self.fail:
            raise self.fail
        payload = self.clock_payload
        if payload is None:
            payload = {"is_open": self.market_open, "timestamp": NOW.isoformat()}
        if self.clock_age_seconds:
            return ProviderRead(
                provider="alpaca", endpoint="/test", feed="indicative",
                source_time=NOW - timedelta(seconds=self.clock_age_seconds),
                received_time=NOW, pages=1, payload=payload,
            )
        return read(payload)

    def account(self) -> ProviderRead:
        self.calls += 1
        return read({
            "account_number": "PA-TEST-REDACTED", "status": "ACTIVE",
            "equity": "100000", "options_buying_power": "50000",
        })

    def daily_bars(self, symbol: str) -> ProviderRead:
        self.calls += 1
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
        self.calls += 1
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
        self.cancels: list[str] = []

    def resolved_endpoint(self) -> str:
        return "https://paper-api.alpaca.markets"

    def open_strategy_count(self) -> int:
        return self.open_strategies

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        self.submits.append(body)
        return {"id": f"brk-{len(self.submits)}", "status": "accepted"}

    def cancel_order(self, broker_order_id: str) -> None:
        self.cancels.append(broker_order_id)

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
        from pgsupport import database_url

        settings = load_settings(dict(env, DATABASE_URL=database_url(db)))
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
            from reconcile_support import FakeBroker as ReconBroker

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

    def with_recon(self, agent, positions, *, orders=None, once=None):
        """Attach reconciliation to a built agent; the store exists only by then.

        `once` gates when the broker starts reporting the exposure, so a test can
        distinguish the reconciliation that opens a tick from the one that must
        follow a submission.
        """
        from options_alpha_lab.execution.reconcile import Reconciler
        from reconcile_support import FakeBroker as ReconBroker

        class Broker(ReconBroker):
            def list_positions(self):
                return positions if (once is None or once()) else []

            def get_by_client_order_id(self, client_order_id: str):
                if orders is None or (once is not None and not once()):
                    return None
                return orders(client_order_id)

        agent.reconciler = Reconciler(Broker(positions=positions), self.store)
        return agent

    def open_position(self, *, avg_debit: str = "3.13", filled_at=None) -> str:
        """An OPEN position established the only legal way: from reconciled fills."""
        intent = entry_intent()
        order_id, position_id = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW),
            direction=Direction.BULLISH, long_symbol=LONG, short_symbol=SHORT,
            expiration=NOW + timedelta(days=25), width=Decimal("5.00"),
            max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("600.00"), Direction.BULLISH,
                                        PriceSource.COMPLETED_DAILY_CLOSE),
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
