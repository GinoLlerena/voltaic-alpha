"""The autonomous cycle, driven entirely offline."""

from __future__ import annotations

import unittest
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import agent_support as support
from agent_support import (
    BASE_ENV,
    LONG,
    NOW,
    SHORT,
    WRITE_ENV,
    DurableAgentCase,
    FakeBroker,
    FakeClient,
    agent,
    entry_intent,
    read,
)
from options_alpha_lab.agent import (
    TradingAgent,
    halt_state_for,
    spread_value,
)
from options_alpha_lab.architecture.contracts import (
    Direction,
    ExecutionState,
    PriceSource,
    SignalFamily,
)
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.gateway import ExecutionGateway
from options_alpha_lab.execution.lifecycle import (
    PositionState,
)
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import Position as PositionRow
from options_alpha_lab.providers.alpaca_readonly import ProviderError


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



class MalformedBreadthBarsTests(unittest.TestCase):
    """Malformed RSP bars are recorded like a failed read, and block nothing.

    They used to land in `provider_errors`, which made the snapshot unusable:
    a broken optional input halted the decision, against the rule that
    breadth must never fail an otherwise sound one.
    """

    #: A payload whose bars are not a list, and a bar whose time does not parse.
    MALFORMED = ({"symbol": "RSP", "bars": "not a list"},
                 {"symbol": "RSP", "bars": [{"t": "not a time"}]})

    @staticmethod
    def client(payload: dict) -> FakeClient:
        class Client(FakeClient):
            def daily_bars(self, symbol: str):
                if symbol != "RSP":
                    return super().daily_bars(symbol)
                return support.read(payload, feed="sip")
        return Client()

    def test_recorded_as_an_advisory_not_a_provider_error(self) -> None:
        for payload in self.MALFORMED:
            with self.subTest(payload=payload):
                snapshot, _ = agent(BASE_ENV, client=self.client(payload)).observe()
                self.assertEqual(snapshot.data_quality.advisories, ("rsp:bars_unreadable",))
                self.assertEqual(snapshot.data_quality.provider_errors, ())

    def test_it_does_not_block_the_decision(self) -> None:
        for payload in self.MALFORMED:
            with self.subTest(payload=payload):
                snapshot, _ = agent(BASE_ENV, client=self.client(payload)).observe()
                self.assertTrue(snapshot.data_quality.is_usable)
                self.assertEqual(agent(BASE_ENV, client=self.client(payload)).tick().action,
                                 "TRADE_CANDIDATE")


class FailedBreadthReadTests(unittest.TestCase):
    """A failed RSP read is recorded, and blocks nothing (plan decision 5).

    It used to be swallowed: the snapshot of a session whose breadth read
    failed looked the same as one where breadth simply had nothing to say.
    """

    class Client(FakeClient):
        def daily_bars(self, symbol: str):
            if symbol == "RSP":
                raise ProviderError("GET https://data.example/v2/stocks/bars?symbols=RSP "
                                    "returned 503: upstream unavailable")
            return super().daily_bars(symbol)

    def test_the_failure_is_recorded_as_an_advisory(self) -> None:
        snapshot, _ = agent(BASE_ENV, client=self.Client()).observe()
        self.assertEqual(snapshot.data_quality.advisories,
                         ("rsp:read_failed:ProviderError:status_503",))

    def test_the_record_keeps_neither_the_url_nor_the_reply(self) -> None:
        snapshot, _ = agent(BASE_ENV, client=self.Client()).observe()
        text = " ".join(snapshot.data_quality.advisories)
        self.assertNotIn("example", text)
        self.assertNotIn("upstream", text)

    def test_it_neither_blocks_the_decision_nor_becomes_a_reason(self) -> None:
        snapshot, _ = agent(BASE_ENV, client=self.Client()).observe()
        self.assertTrue(snapshot.data_quality.is_usable)
        self.assertEqual(snapshot.data_quality.reason_codes, ())
        self.assertEqual(agent(BASE_ENV, client=self.Client()).tick().action,
                         "TRADE_CANDIDATE")

    def test_a_healthy_read_records_nothing(self) -> None:
        snapshot, _ = agent(BASE_ENV).observe()
        self.assertEqual(snapshot.data_quality.advisories, ())

    def test_the_record_survives_serialization(self) -> None:
        import json

        from options_alpha_lab.hashing import canonical_json
        from options_alpha_lab.snapshot_io import snapshot_from_dict, snapshot_to_dict

        snapshot, _ = agent(BASE_ENV, client=self.Client()).observe()
        stored = json.loads(canonical_json(snapshot_to_dict(snapshot)))
        again = snapshot_from_dict(stored)
        self.assertEqual(again.data_quality.advisories, snapshot.data_quality.advisories)

    def test_a_snapshot_without_one_serializes_as_before(self) -> None:
        from options_alpha_lab.snapshot_io import snapshot_to_dict

        snapshot, _ = agent(BASE_ENV).observe()
        self.assertNotIn("advisories", snapshot_to_dict(snapshot)["data_quality"])

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

    def test_the_invalidation_level_is_carried_typed_not_recovered_from_prose(self) -> None:
        # EXIT-AC-06. The classifier used to format the level into English and
        # the agent regexed it back out, so the first decimal in an arbitrary
        # sentence became the level a live position was managed against.
        from options_alpha_lab.components import DeterministicSetupClassifier
        from options_alpha_lab.snapshot_io import load_snapshot

        snap = load_snapshot("fixtures/h0/spy_qualified.snapshot.json")
        setup = DeterministicSetupClassifier().classify(snap)
        assert setup is not None and setup.invalidation is not None

        # The prose is written from the rule, so it agrees by construction.
        self.assertIn(str(setup.invalidation.level), setup.invalidation_conditions[0])
        self.assertIs(setup.invalidation.direction, setup.direction)
        self.assertIs(setup.invalidation.source, snap.underlying_source)

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
        from reconcile_support import FakeBroker as ReconBroker

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




class OutOfHoursReconciliationTests(DurableAgentCase):
    """Broker state does not stop changing at the close."""

    def test_reconciliation_runs_even_when_the_market_is_closed(self) -> None:
        # An order that expired at 16:00, or a fill that landed at 15:59:59,
        # must not go unnoticed until the next open.
        agent = self.build(
            WRITE_ENV, client=FakeClient(market_open=False),
            reconcile_positions=[{"symbol": "SPY260918P00600000", "qty": "-1"}],
        )
        result = agent.tick()
        self.assertEqual(result.action, "MARKET_CLOSED")
        self.assertIn("reconciled", result.detail)
        self.assertIsNotNone(agent.last_reconciliation)

    def test_an_out_of_hours_mismatch_still_halts_new_risk(self) -> None:
        agent = self.build(
            WRITE_ENV, client=FakeClient(market_open=False),
            reconcile_positions=[{"symbol": "SPY260918P00600000", "qty": "-1"}],
        )
        agent.tick()
        self.assertIs(agent.execution_state, ExecutionState.NO_NEW_RISK)
        assert agent.gateway is not None
        self.assertIs(agent.gateway.execution_state, ExecutionState.NO_NEW_RISK)

    def test_no_entry_is_attempted_out_of_hours(self) -> None:
        agent = self.build(WRITE_ENV, client=FakeClient(market_open=False))
        self.assertEqual(agent.tick().action, "MARKET_CLOSED")
        self.assertEqual(self.broker.submits, [])


if __name__ == "__main__":
    unittest.main()


class ReconciliationIsNotOptionalTests(DurableAgentCase):
    """Findings 2 and 5: broker responsibility survives a data outage, and a
    mutation is followed by a read rather than by an assumption."""

    def test_a_market_data_outage_does_not_suppress_reconciliation(self) -> None:
        # The regression: observe() ran first, so a chain outage returned
        # OBSERVE_FAILED and every open order and position went unmanaged until
        # the provider recovered. The broker keeps filling regardless.
        agent = self.with_recon(
            self.build(
                WRITE_ENV, client=FakeClient(fail=ProviderError("chain unavailable"))
            ),
            [],
        )
        self.open_position()
        result = agent.tick()

        self.assertEqual(result.action, "OBSERVE_FAILED")
        self.assertIn("reconciled", result.detail, "the tick must report what it found")
        self.assertIn("position_vanished", [i.kind for i in self.store.open_incidents()])
        self.assertIs(agent.execution_state, ExecutionState.NO_NEW_RISK)

    def test_an_accepted_entry_is_reconciled_before_the_tick_returns(self) -> None:
        # Acceptance is SUBMITTED, never FILLED. Waiting a whole 300-second tick
        # to learn which one it was leaves a filled position unmanaged.
        from reconcile_support import filled_order

        broker = FakeBroker()
        agent = self.build(WRITE_ENV, broker=broker)
        # The broker holds the spread only after the order reaches it, so the
        # reconciliation that opens the tick still sees a flat account.
        self.with_recon(
            agent,
            [{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}],
            orders=lambda cid: filled_order(cid),
            once=lambda: bool(broker.submits),
        )
        result = agent.tick()
        self.assertEqual(result.action, "ENTRY_SUBMITTED")

        managed = agent.active_position()
        assert managed is not None, "the fill must be established inside the tick"
        self.assertIs(managed.state, PositionState.OPEN)
        self.assertEqual(managed.avg_entry_debit, Decimal("3.13"))

    def test_deadline_enforcement_does_not_depend_on_market_data(self) -> None:
        # A 90-second deadline cannot wait for a chain that may never return.
        from options_alpha_lab.execution.deadline import DeadlineEnforcer

        broker = FakeBroker()
        agent = self.with_recon(
            self.build(
                WRITE_ENV, broker=broker,
                client=FakeClient(fail=ProviderError("chain unavailable")),
            ),
            [],
        )
        intent = entry_intent()
        order_id, _ = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=25),
            width=Decimal("5.00"), max_loss=Decimal("339.00"), invalidation=None, now=NOW,
        )
        self.store.record_submission(order_id, broker_order_id="brk-late",
                                     broker_status="accepted", now=NOW)
        agent.deadlines = DeadlineEnforcer(agent.gateway, self.store)
        agent._clock = lambda: NOW + timedelta(seconds=200)

        result = agent.tick()
        self.assertEqual(result.action, "DEADLINE_ACTION")
        self.assertIn("canceled 1", result.detail)
        self.assertEqual(broker.cancels, ["brk-late"])


class InvalidationSourceTests(DurableAgentCase):
    """EXIT-AC-06 at the agent: the price a rule is judged on must be checkable."""

    DEGRADED_CLOCK = {"timestamp": NOW.isoformat()}  # no `is_open` at all

    def test_a_clock_without_is_open_is_a_provider_error_not_a_closed_market(self) -> None:
        # `bool(None)` used to read a missing `is_open` as "closed", which told
        # parse_bars to keep the forming bar and presented a partial session as
        # a completed close.
        agent = self.build(WRITE_ENV, client=FakeClient(clock_payload=self.DEGRADED_CLOCK))
        snapshot, market_open = agent.observe()
        self.assertFalse(market_open)
        self.assertIn("clock:is_open_unreadable", snapshot.data_quality.reason_codes[0])
        self.assertIs(snapshot.underlying_source, PriceSource.UNKNOWN)
        self.assertFalse(snapshot.data_quality.is_usable, "entries must be halted")

    def test_a_healthy_clock_states_the_source_and_the_session(self) -> None:
        agent = self.build(WRITE_ENV)
        snapshot, _ = agent.observe()
        self.assertIs(snapshot.underlying_source, PriceSource.COMPLETED_DAILY_CLOSE)
        self.assertIsNotNone(snapshot.underlying_session, "the close must be attributable")

    def test_an_unreadable_clock_is_not_treated_as_a_closed_market(self) -> None:
        agent = self.build(
            WRITE_ENV,
            client=FakeClient(clock_payload=self.DEGRADED_CLOCK, market_open=True),
        )
        self.open_position()
        # It reports closed because it does not know, which is the safe reading -
        # but it reaches that answer from a recorded provider error, not from
        # `bool(None)`.
        self.assertEqual(agent.tick().action, "MARKET_CLOSED")

    def test_a_stale_clock_leaves_the_position_managed_but_the_rule_unevaluated(self) -> None:
        # The reachable mismatch: `is_open` parses, so the market is open and
        # exits are evaluated, but the read is too old to establish that the last
        # bar is a completed close. Exits are deliberately not gated on data
        # quality, so without this check the rule would be judged anyway.
        agent = self.build(
            WRITE_ENV, client=FakeClient(clock_age_seconds=600, market_open=True)
        )
        position_id = self.open_position()
        snapshot, market_open = agent.observe()
        self.assertTrue(market_open)
        self.assertIs(snapshot.underlying_source, PriceSource.UNKNOWN)

        result = agent.tick()
        self.assertEqual(result.action, "POSITION_REVIEW")
        assert result.exit is not None
        self.assertTrue(result.exit.invalidation_unverifiable)
        self.assertFalse(result.exit.should_close)
        self.assertIn(
            "unverifiable_invalidation_source",
            [i.kind for i in self.store.open_incidents()],
        )
        self.assertIs(agent.execution_state, ExecutionState.NO_NEW_RISK)

        # The incident marks the position, and `active_position` skips INCIDENT.
        # Responsibility is not lost by that: reconciliation opens the next tick
        # and heals it from broker state, so the position keeps being evaluated
        # by every rule that does not read the underlying, tick after tick.
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.INCIDENT)

        from reconcile_support import filled_order

        self.with_recon(
            agent,
            [{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}],
            orders=lambda cid: filled_order(cid),
        )
        self.assertEqual(agent.tick().action, "POSITION_REVIEW", "still managed")

        # The steady state while the clock stays stale: healed at the top of the
        # tick, evaluated by every premium- and price-independent rule, marked
        # again at the bottom. It never becomes flat or disowned on its own.
        after = self.store.get_position(position_id)
        assert after is not None
        self.assertIs(after.state, PositionState.INCIDENT)
        self.assertEqual(after.filled_quantity, 1)
        self.assertNotIn(
            after.state, {PositionState.CLOSED, PositionState.ABANDONED},
            "an integrity incident must never release exposure",
        )

    def test_the_rule_is_reported_unverifiable_rather_than_silently_skipped(self) -> None:
        from options_alpha_lab.exits import ExitInputs, evaluate_exit

        agent = self.build(WRITE_ENV)
        position_id = self.open_position()
        managed = agent.active_position()
        assert managed is not None and managed.invalidation is not None
        self.assertIs(managed.invalidation.source, PriceSource.COMPLETED_DAILY_CLOSE)

        # The stored rule is judged against an intraday price.
        decision = evaluate_exit(ExitInputs(
            direction=managed.direction, entry_debit=Decimal("3.13"),
            width=managed.width, quantity=managed.filled_quantity, dte=25,
            underlying_price=Decimal("500.00"),
            underlying_source=PriceSource.INTRADAY,
            invalidation=managed.invalidation, current_value=Decimal("3.10"),
            as_of=NOW.date(),
        ))
        self.assertTrue(decision.invalidation_unverifiable)
        self.assertFalse(decision.should_close, "500 is far below the level, and irrelevant")
        self.assertIsNotNone(position_id)

    def test_a_direction_conflict_halts_rather_than_picking_a_side(self) -> None:
        agent = self.build(WRITE_ENV)
        self.open_position()
        managed = agent.active_position()
        assert managed is not None

        # Corrupt the stored rule's direction, as a bad migration or a hand-edit
        # would. Nothing may quietly manage the position against it.
        with Session(agent.store._engine) as session:
            row = session.get(PositionRow, managed.position_id)
            row.invalidation_direction = Direction.BEARISH.value
            session.commit()

        result = agent.tick()
        self.assertEqual(result.action, "POSITION_REVIEW")
        self.assertIn("disagrees", result.detail)
        self.assertIn(
            "invalidation_direction_conflict",
            [i.kind for i in self.store.open_incidents()],
        )
        self.assertIs(agent.execution_state, ExecutionState.NO_NEW_RISK)


class RiskCheckRecordingTests(DurableAgentCase):
    """Finding 7: the governor's individual checks must reach the recorder.

    Replay already stored them. The live agent built a governor inline and
    discarded it, so a decision made in production kept its reason codes and
    lost the arithmetic behind them - which is the half you need to re-argue a
    refusal months later.
    """

    def checks_for_the_only_decision(self) -> list[dict[str, Any]]:
        from options_alpha_lab.persistence.models import RiskDecisionRecord

        with Session(self.store._engine) as session:
            rows = list(session.scalars(select(RiskDecisionRecord)).all())
        # The fixture replay in build() records one; the tick records the other.
        return [row.checks for row in rows]

    def test_a_live_decision_stores_the_checks_not_only_the_reason_codes(self) -> None:
        agent = self.build(WRITE_ENV)
        result = agent.tick()
        self.assertIn(result.action, {"ENTRY_SUBMITTED", "TRADE_CANDIDATE"})

        recorded = self.checks_for_the_only_decision()
        self.assertTrue(recorded, "a risk decision must have been recorded")
        live = recorded[-1]
        self.assertTrue(live, "the live path stored an empty check list")
        for check in live:
            self.assertIn("check", check)

    def test_the_checks_match_the_governor_that_actually_decided(self) -> None:
        agent = self.build(WRITE_ENV)
        agent.tick()
        stored = self.checks_for_the_only_decision()[-1]
        self.assertEqual(
            [c["check"] for c in stored],
            [c["check"] for c in agent.risk_governor.last_checks],
        )


class PositionClockTests(DurableAgentCase):
    """An open spread is valued on its own cadence, not the strategy's.

    A stop loss judged once per 300-second tick is enforced against a mark up to
    300 seconds stale, and the observation series MFE and MAE are computed from
    has 300-second resolution - which is to say it cannot see the excursion it
    exists to measure.
    """

    def flat_agent(self):
        return self.with_recon(self.build(BASE_ENV), [])

    def held_agent(self, positions=None):
        agent = self.with_recon(
            self.build(BASE_ENV),
            positions if positions is not None else [
                {"symbol": LONG, "qty": "1", "side": "long"},
                {"symbol": SHORT, "qty": "1", "side": "short"},
            ],
        )
        return agent

    def test_a_flat_agent_never_calls_a_provider_on_this_cadence(self) -> None:
        # It runs every 60 seconds. If being flat did not short-circuit it
        # locally, an idle worker would spend its rate limit on nothing.
        client = FakeClient()
        agent = self.with_recon(self.build(BASE_ENV, client=client), [])
        client.calls = 0
        self.assertIsNone(agent.position_clock())
        self.assertEqual(client.calls, 0, "a flat agent must not reach a provider")

    def test_an_open_position_is_valued_between_ticks(self) -> None:
        agent = self.held_agent()
        self.open_position()
        result = agent.position_clock()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotEqual(result.action, "MARKET_CLOSED")

    def test_it_records_an_observation_every_pass(self) -> None:
        agent = self.held_agent()
        position_id = self.open_position()
        for _ in range(3):
            agent.position_clock()
        observations = self.store.observations_for(position_id)
        self.assertEqual(len(observations), 3, "MFE and MAE need an unbroken series")

    def test_it_never_considers_an_entry(self) -> None:
        # The single strategy slot is already spoken for, and re-deciding a
        # daily hypothesis every minute adds correlated records, not signal.
        agent = self.held_agent()
        self.open_position()
        result = agent.position_clock()
        assert result is not None
        self.assertNotIn(
            result.action,
            {"ENTRY_SUBMITTED", "TRADE_CANDIDATE", "NO_TRADE", "ENTRY_REFUSED"},
        )

    def test_a_closed_market_is_a_quiet_pass(self) -> None:
        # A mark taken when nothing is trading is not a valuation.
        agent = self.with_recon(
            self.build(BASE_ENV, client=FakeClient(market_open=False)),
            [{"symbol": LONG, "qty": "1", "side": "long"},
             {"symbol": SHORT, "qty": "1", "side": "short"}],
        )
        position_id = self.open_position()
        self.assertIsNone(agent.position_clock())
        self.assertEqual(self.store.observations_for(position_id), [])

    def test_an_observation_failure_is_recorded_without_flooding_the_log(self) -> None:
        # Reconciliation already ran and its state stands. The strategy tick is
        # what reports an outage; repeating it every minute buries the log.
        class Broken(FakeClient):
            def option_chain(self, *a, **k):
                raise ProviderError("chain unavailable")

        agent = self.with_recon(
            self.build(BASE_ENV, client=Broken()),
            [{"symbol": LONG, "qty": "1", "side": "long"},
             {"symbol": SHORT, "qty": "1", "side": "short"}],
        )
        self.open_position()
        self.assertIsNone(agent.position_clock())
        self.assertIsNotNone(agent.last_observation_error)

    def test_reconciliation_runs_before_the_position_is_read(self) -> None:
        # A close that filled resolves the position out from under us. Managing
        # the object we read first would evaluate exits on exposure we no
        # longer have.
        agent = self.with_recon(self.build(BASE_ENV), [])
        self.open_position()
        result = agent.position_clock()
        self.assertIsNone(
            result, "the broker reports nothing held, so there is nothing to value"
        )


class HeldLegsOutsideTheChainTests(DurableAgentCase):
    """A held spread must stay priceable until the expiry guard closes it.

    The chain is read from 10 to 60 days out and the expiry guard fires at 7.
    On 14 October 2026 a Paper spread reached 9 days, its legs fell out of the
    chain, and the session stop that fired at the open could not be priced, so
    the position was held under an incident instead of being closed.
    """

    NEAR = NOW + timedelta(days=9)

    def near_leg(self, strike: int) -> str:
        return f"SPY{self.NEAR:%y%m%d}C{strike * 1000:08d}"

    def client(self):
        near = (self.near_leg(620), self.near_leg(625))

        class WindowedClient(FakeClient):
            """Honours the expiry window, as the provider does."""

            windows: list[tuple[str, str]] = []

            def option_chain(self, symbol, *, expiration_gte, expiration_lte):
                self.windows.append((expiration_gte, expiration_lte))
                fresh = (NOW - timedelta(seconds=20)).isoformat()
                # The near legs sit at the money with a stressed volatility, so
                # any leak into the at-the-money reading would show in the signals.
                every = {
                    LONG: ("12.40", "12.60", 0.60, 0.15), SHORT: ("9.60", "9.80", 0.32, 0.15),
                    near[0]: ("4.00", "4.10", 0.52, 0.90), near[1]: ("1.50", "1.60", 0.30, 0.90),
                }
                snaps = {
                    sym: {"latestQuote": {"bp": float(bid), "ap": float(ask), "t": fresh},
                          "impliedVolatility": iv, "greeks": {"delta": delta}}
                    for sym, (bid, ask, delta, iv) in every.items()
                    if expiration_gte <= f"20{sym[3:5]}-{sym[5:7]}-{sym[7:9]}" <= expiration_lte
                }
                return read({"underlying": symbol, "snapshots": snaps})

        WindowedClient.windows = []
        return WindowedClient()

    def test_legs_nine_days_out_are_still_priced(self) -> None:
        client = self.client()
        agent = self.build(WRITE_ENV, client=client)
        self.open_position(legs=(self.near_leg(620), self.near_leg(625)), expires_in_days=9)
        snapshot, _ = agent.observe()
        self.assertEqual(
            spread_value(snapshot, self.near_leg(620), self.near_leg(625)), Decimal("2.40")
        )
        self.assertEqual(client.windows[-1], ((NOW + timedelta(days=9)).date().isoformat(),) * 2)

    def test_the_held_legs_do_not_reach_the_at_the_money_reading(self) -> None:
        client = self.client()
        agent = self.build(WRITE_ENV, client=client)
        self.open_position(legs=(self.near_leg(620), self.near_leg(625)), expires_in_days=9)
        snapshot, _ = agent.observe()
        volatility = [s for s in snapshot.signals if s.family is SignalFamily.VOLATILITY_OPTIONS]
        self.assertTrue(volatility)
        self.assertTrue(all(s.direction is Direction.BULLISH for s in volatility),
                        "a 0.90 reading from the held legs would have read as stress")
        symbols = {q.contract_symbol for q in snapshot.option_chain}
        self.assertEqual(symbols, {LONG, SHORT, self.near_leg(620), self.near_leg(625)})

    def test_the_session_stop_closes_instead_of_blocking(self) -> None:
        client = self.client()
        agent = self.build(WRITE_ENV, client=client)
        self.open_position(legs=(self.near_leg(620), self.near_leg(625)), expires_in_days=9,
                           filled_at=NOW - timedelta(days=7))
        result = agent.tick()
        self.assertNotEqual(result.action, "EXIT_BLOCKED", result.detail)
        self.assertNotIn("unmeasurable_position_value",
                         [i.kind for i in self.store.open_incidents()])

    def test_a_position_inside_the_window_costs_no_extra_read(self) -> None:
        client = self.client()
        agent = self.build(WRITE_ENV, client=client)
        self.open_position()
        agent.observe()
        self.assertEqual(len(client.windows), 1)

    def test_a_flat_agent_reads_only_the_chain_window(self) -> None:
        client = self.client()
        agent = self.build(WRITE_ENV, client=client)
        snapshot, _ = agent.observe()
        self.assertEqual(len(client.windows), 1)
        self.assertEqual({q.contract_symbol for q in snapshot.option_chain}, {LONG, SHORT})


class OrderClockTests(DurableAgentCase):
    """Finding 1: the deadline check runs on the deadline's timescale.

    A 90-second deadline enforced by a 300-second loop is enforced up to 300
    seconds late, by which time the unfilled order still occupies the single
    strategy slot and the market has moved away from its limit.
    """

    def pending_entry(self) -> str:
        """An entry that has been submitted and has not come back."""
        intent = entry_intent()
        order_id, _ = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=25),
            width=Decimal("5.00"), max_loss=Decimal("339.00"), invalidation=None, now=NOW,
        )
        self.store.record_submission(order_id, broker_order_id="brk-slow",
                                     broker_status="accepted", now=NOW)
        return order_id

    def agent_with_deadlines(self, broker):
        from options_alpha_lab.execution.deadline import DeadlineEnforcer

        agent = self.with_recon(self.build(WRITE_ENV, broker=broker), [])
        agent.deadlines = DeadlineEnforcer(agent.gateway, self.store)
        return agent

    def test_a_quiet_pass_does_no_broker_work_at_all(self) -> None:
        # The fast clock runs every few seconds. It must decide whether to talk
        # to the broker from a local read, or it becomes the rate-limit problem.
        broker = FakeBroker()
        agent = self.agent_with_deadlines(broker)
        self.assertIsNone(agent.working_order_deadline(NOW), "nothing is outstanding")
        self.assertIsNone(agent.order_clock())
        self.assertEqual(broker.cancels, [])

    def test_it_does_nothing_before_the_deadline(self) -> None:
        broker = FakeBroker()
        agent = self.agent_with_deadlines(broker)
        self.pending_entry()

        agent._clock = lambda: NOW + timedelta(seconds=60)
        self.assertIsNotNone(agent.working_order_deadline(NOW + timedelta(seconds=60)))
        self.assertIsNone(agent.order_clock(), "60s is inside the 90s entry deadline")
        self.assertEqual(broker.cancels, [])

    def test_it_cancels_at_the_deadline_without_a_strategy_tick(self) -> None:
        broker = FakeBroker()
        agent = self.agent_with_deadlines(broker)
        self.pending_entry()

        agent._clock = lambda: NOW + timedelta(seconds=95)
        result = agent.order_clock()
        assert result is not None
        self.assertEqual(result.action, "DEADLINE_ACTION")
        self.assertIn("canceled 1", result.detail)
        self.assertEqual(broker.cancels, ["brk-slow"])
        # And it did so without evaluating the strategy: no decision was made.
        self.assertEqual(
            [r.action for r in agent.history], ["DEADLINE_ACTION"],
        )

    def test_the_deadline_is_enforced_within_one_clock_interval(self) -> None:
        # The property the separation exists for, stated as a bound rather than
        # as "it is faster now".
        from options_alpha_lab.agent import DEFAULT_ORDER_CLOCK_SECONDS
        from options_alpha_lab.execution.deadline import ENTRY_DEADLINE

        broker = FakeBroker()
        agent = self.agent_with_deadlines(broker)
        self.pending_entry()

        fired_at = None
        for second in range(0, 200, DEFAULT_ORDER_CLOCK_SECONDS):
            agent._clock = lambda s=second: NOW + timedelta(seconds=s)
            if agent.order_clock() is not None:
                fired_at = second
                break

        self.assertIsNotNone(fired_at, "the deadline was never enforced")
        assert fired_at is not None
        lateness = fired_at - ENTRY_DEADLINE.total_seconds()
        self.assertGreaterEqual(lateness, 0, "it must not fire early")
        self.assertLess(lateness, DEFAULT_ORDER_CLOCK_SECONDS)

    def test_it_stops_watching_an_order_that_has_outlived_every_deadline(self) -> None:
        # A submitted order still non-terminal ten minutes later has something
        # wrong with it that five-second polling will not fix. The strategy loop
        # keeps reconciling it; the fast clock stands down.
        agent = self.agent_with_deadlines(FakeBroker())
        self.pending_entry()

        self.assertIsNotNone(agent.working_order_deadline(NOW + timedelta(minutes=9)))
        self.assertIsNone(agent.working_order_deadline(NOW + timedelta(minutes=11)))

    def test_a_resolved_order_is_no_longer_watched(self) -> None:
        agent = self.agent_with_deadlines(FakeBroker())
        order_id = self.pending_entry()
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("3.13"), now=NOW,
        )
        self.assertIsNone(agent.working_order_deadline(NOW + timedelta(seconds=95)))
