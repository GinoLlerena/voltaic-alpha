"""EXIT-AC-13: a complete lifecycle through the agent, driven only by broker facts.

Entry submitted, filled by reconciliation, held, stopped out, closed, and
confirmed flat - with a forced restart in the middle to prove nothing depends on
process memory.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, "tests")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from options_alpha_lab.agent import TradingAgent  # noqa: E402
from options_alpha_lab.architecture.contracts import ExecutionState  # noqa: E402
from options_alpha_lab.config import load_settings  # noqa: E402
from options_alpha_lab.execution.deadline import DeadlineEnforcer  # noqa: E402
from options_alpha_lab.execution.gateway import BrokerPort, ExecutionGateway  # noqa: E402
from options_alpha_lab.execution.lifecycle import (  # noqa: E402
    LifecycleStore,
    PositionState,
)
from options_alpha_lab.execution.reconcile import Reconciler  # noqa: E402
from options_alpha_lab.persistence.models import Decision, Fill  # noqa: E402
from options_alpha_lab.persistence.repository import (  # noqa: E402
    DecisionRecorder,
    build_engine,
    create_schema,
)
from test_agent import LONG, NOW, SHORT, WRITE_ENV, FakeClient  # noqa: E402


class ScriptedBroker(BrokerPort):
    """A broker whose fills are controlled by the test, not by the agent."""

    def __init__(self) -> None:
        self.orders: dict[str, dict[str, Any]] = {}
        self.positions: list[dict[str, Any]] = []
        self.submits: list[dict[str, Any]] = []
        self.cancels: list[str] = []

    def resolved_endpoint(self) -> str:
        return "https://paper-api.alpaca.markets"

    def open_strategy_count(self) -> int:
        return len(self.positions) + sum(
            1 for o in self.orders.values() if o["status"] in {"new", "accepted"}
        )

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        self.submits.append(body)
        cid = body["client_order_id"]
        self.orders[cid] = {
            "client_order_id": cid, "id": f"brk-{len(self.submits)}",
            "status": "accepted", "filled_qty": "0", "filled_avg_price": None,
        }
        return self.orders[cid]

    def get_by_client_order_id(self, cid: str) -> dict[str, Any] | None:
        return self.orders.get(cid)

    def list_open_orders(self) -> list[dict[str, Any]]:
        return [o for o in self.orders.values() if o["status"] in {"new", "accepted"}]

    def list_positions(self) -> list[dict[str, Any]]:
        return self.positions

    def cancel_order(self, broker_order_id: str) -> None:
        self.cancels.append(broker_order_id)

    # -- test controls -----------------------------------------------------
    def fill(self, index: int, avg: str, legs: list[tuple[str, str]]) -> None:
        cid = self.submits[index]["client_order_id"]
        self.orders[cid].update({
            "status": "filled", "filled_qty": "1", "filled_avg_price": avg,
            "legs": [
                {"symbol": s, "filled_qty": "1", "filled_avg_price": p} for s, p in legs
            ],
        })

    def hold(self) -> None:
        self.positions = [{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}]

    def flatten(self) -> None:
        self.positions = []


class EndToEndLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "e2e.db"
        self.settings = load_settings(
            dict(WRITE_ENV, DATABASE_URL=f"sqlite+pysqlite:///{self.db}")
        )
        engine = build_engine(self.settings)
        create_schema(engine)
        from options_alpha_lab.replay import replay_paths

        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")],
                     self.settings, create=False)
        with Session(engine) as session:
            self.decision_id = session.scalars(select(Decision)).first().id
        self.broker = ScriptedBroker()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def agent(self, *, quotes: dict[str, tuple[str, str]] | None = None,
              at: datetime | None = None) -> TradingAgent:
        """A brand-new process every time: fresh engine, fresh store, shared DB."""
        moment = at or NOW
        engine = build_engine(self.settings)
        store = LifecycleStore(engine)
        gateway = ExecutionGateway(self.broker, self.settings, clock=lambda: moment)
        agent = TradingAgent(
            self.settings,
            client=FakeClient(quotes=quotes) if quotes is not None else FakeClient(),
            gateway=gateway, store=store,
            reconciler=Reconciler(self.broker, store),
            deadlines=DeadlineEnforcer(gateway, store),
            recorder=DecisionRecorder(engine, self.settings),
            clock=lambda: moment, operator_approval="operator:e2e",
        )
        agent.decision_row_id = self.decision_id
        agent.run_id = DecisionRecorder(engine, self.settings).start_run()
        return agent

    def store(self) -> LifecycleStore:
        return LifecycleStore(build_engine(self.settings))

    def only_position(self):
        """Every position regardless of state: a CLOSED one still has to be read."""
        from options_alpha_lab.persistence.models import Position

        with Session(build_engine(self.settings)) as session:
            rows = session.scalars(select(Position)).all()
            self.assertEqual(len(rows), 1)
            return LifecycleStore._to_managed(rows[0])

    def test_full_lifecycle_survives_a_restart_and_ends_flat(self) -> None:
        # 1. Entry is submitted. Acceptance is not a fill.
        first = self.agent().tick()
        self.assertEqual(first.action, "ENTRY_SUBMITTED")
        self.assertIs(self.only_position().state, PositionState.PENDING)
        self.assertIsNone(self.only_position().avg_entry_debit)

        # 2. The broker fills it. A brand-new process learns this by reconciling.
        self.broker.fill(0, "3.13", [(LONG, "6.90"), (SHORT, "3.77")])
        self.broker.hold()
        restarted = self.agent()
        restarted.tick()
        position = self.only_position()
        self.assertIs(position.state, PositionState.OPEN)
        self.assertEqual(position.avg_entry_debit, Decimal("3.13"),
                         "the exit basis is the fill, not the limit")

        # 3. Another new process holds it while the value sits between thresholds.
        held = self.agent(quotes={LONG: ("12.40", "12.60"), SHORT: ("9.60", "9.80")}).tick()
        self.assertEqual(held.action, "POSITION_HELD")

        # 4. The value collapses through the stop. A close is submitted.
        stopped = self.agent(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}).tick()
        self.assertEqual(stopped.action, "CLOSE_SUBMITTED")
        self.assertIs(self.only_position().state, PositionState.CLOSING)
        self.assertEqual(len(self.broker.submits), 2)

        # 5. Still holding: responsibility is retained, no duplicate close.
        working = self.agent(quotes={LONG: ("1.00", "1.10"), SHORT: ("0.20", "0.30")}).tick()
        self.assertEqual(working.action, "CLOSE_WORKING")
        self.assertEqual(len(self.broker.submits), 2, "no duplicate close")

        # 6. The close fills and the broker reports flat. The clock advances,
        # as it would in production: a later tick observes a later snapshot.
        self.broker.fill(1, "1.05", [(LONG, "1.00"), (SHORT, "0.30")])
        self.broker.flatten()
        self.agent(at=NOW + timedelta(minutes=5)).tick()
        final = self.only_position()
        self.assertIs(final.state, PositionState.CLOSED)
        self.assertEqual(self.store().active_positions(), [])

    def test_the_whole_lifecycle_is_reconstructable_from_one_query(self) -> None:
        self.agent().tick()
        self.broker.fill(0, "3.13", [(LONG, "6.90"), (SHORT, "3.77")])
        self.broker.hold()
        self.agent().tick()
        self.broker.flatten()

        engine = build_engine(self.settings)
        with Session(engine) as session:
            fills = session.scalars(select(Fill)).all()
        # Both legs of the entry are recorded with their actual prices.
        self.assertEqual(
            sorted((f.leg_symbol, str(Decimal(str(f.price)).normalize())) for f in fills),
            sorted([(LONG, "6.9"), (SHORT, "3.77")]),
        )

    def test_an_entry_that_never_fills_is_cancelled_and_creates_no_position(self) -> None:
        # EXIT-AC-14: unfilled entry at the deadline.
        self.agent().tick()
        self.assertIs(self.only_position().state, PositionState.PENDING)

        late = NOW + timedelta(seconds=200)
        result = self.agent(at=late).tick()
        self.assertEqual(result.action, "DEADLINE_ACTION")
        self.assertEqual(len(self.broker.cancels), 1)

        # The broker confirms the cancel; no exposure was ever created.
        cid = self.broker.submits[0]["client_order_id"]
        self.broker.orders[cid]["status"] = "canceled"
        self.agent(at=late + timedelta(seconds=10)).tick()
        self.assertIs(self.only_position().state, PositionState.ABANDONED)
        self.assertEqual(self.broker.positions, [])

    def test_the_same_approved_intent_cannot_be_prepared_twice(self) -> None:
        # The client order id is derived from the intent hash, so a collision
        # means the same authority is being reused. Refusing is the guard
        # working; crashing on a database constraint is the same decision made
        # badly.
        self.agent().tick()
        self.broker.fill(0, "3.13", [(LONG, "6.90"), (SHORT, "3.77")])
        self.broker.flatten()
        self.agent().tick()
        result = self.agent().tick()
        self.assertNotEqual(result.action, "ENTRY_SUBMITTED")
        self.assertLessEqual(len(self.broker.submits), 2)

    def test_unexpected_broker_exposure_halts_new_entries(self) -> None:
        # EXIT-AC-05.
        self.broker.positions = [{"symbol": "SPY260918P00600000", "qty": "-1"}]
        agent = self.agent()
        result = agent.tick()
        self.assertEqual(result.action, "ENTRY_HALTED")
        self.assertEqual(self.broker.submits, [])
        self.assertIs(agent.execution_state, ExecutionState.NO_NEW_RISK)




if __name__ == "__main__":
    unittest.main()
