"""Item 2: reconciliation at startup and periodically; mismatches halt new risk."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import (
    Direction,
    ExecutionState,
    PriceSource,
    SpreadStrategy,
)
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.gateway import BrokerPort
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent, build_close_intent
from options_alpha_lab.execution.lifecycle import (
    LifecycleStore,
    OrderState,
    PositionState,
    TypedInvalidation,
)
from options_alpha_lab.execution.reconcile import Reconciler
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import Decision, Incident, Position
from options_alpha_lab.persistence.repository import build_engine, create_schema
from options_alpha_lab.replay import replay_paths

NOW = datetime(2026, 8, 28, 15, 30, tzinfo=UTC)
LONG, SHORT = "SPY260918C00640000", "SPY260918C00645000"


def entry_intent(qty: int = 1, decision_hash: str = "sha256:x") -> OrderIntent:
    return OrderIntent(
        decision_hash=decision_hash, strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        legs=(IntentLeg(LONG, 1, "buy", "buy_to_open"),
              IntentLeg(SHORT, 1, "sell", "sell_to_open")),
        strategy_quantity=qty, limit_price=Decimal("3.39"),
        approval_reference="risk:h0", created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )


class FakeBroker(BrokerPort):
    def __init__(self, *, positions: list[dict[str, Any]] | None = None,
                 open_orders: list[dict[str, Any]] | None = None,
                 by_client_id: dict[str, dict[str, Any]] | None = None,
                 raises: Exception | None = None) -> None:
        self._positions = positions or []
        self._open_orders = open_orders or []
        self._by_client_id = by_client_id or {}
        self._raises = raises

    def resolved_endpoint(self) -> str:
        return "https://paper-api.alpaca.markets"

    def open_strategy_count(self) -> int:
        return len(self._positions) + len(self._open_orders)

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("reconciliation must never submit")

    def list_positions(self) -> list[dict[str, Any]]:
        if self._raises:
            raise self._raises
        return self._positions

    def list_open_orders(self) -> list[dict[str, Any]]:
        if self._raises:
            raise self._raises
        return self._open_orders

    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        return self._by_client_id.get(client_order_id)


def filled_order(client_order_id: str, qty: int = 1, avg: str = "3.13",
                 status: str = "filled") -> dict[str, Any]:
    return {
        "client_order_id": client_order_id, "id": "brk-1", "status": status,
        "filled_qty": str(qty), "filled_avg_price": avg,
        "legs": [
            {"symbol": LONG, "filled_qty": str(qty), "filled_avg_price": "6.90"},
            {"symbol": SHORT, "filled_qty": str(qty), "filled_avg_price": "3.77"},
        ],
    }


class ReconcileCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "r.db"
        self.settings = load_settings({
            "BOT_MODE": "observe", "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{db}",
        })
        self.engine = build_engine(self.settings)
        create_schema(self.engine)
        replay_paths([Path("fixtures/h0/spy_qualified.snapshot.json")],
                     self.settings, create=False)
        with Session(self.engine) as session:
            self.decision_id = session.scalars(select(Decision)).first().id
        self.store = LifecycleStore(self.engine)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def prepare(self, intent: OrderIntent | None = None) -> tuple[str, str, OrderIntent]:
        intent = intent or entry_intent()
        order_id, position_id = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW), direction=Direction.BULLISH,
            long_symbol=LONG, short_symbol=SHORT, expiration=NOW + timedelta(days=22),
            width=Decimal("5.00"), max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(Decimal("631.63"), Direction.BULLISH,
                                        PriceSource.COMPLETED_DAILY_CLOSE),
            now=NOW,
        )
        return order_id, position_id, intent

    def open_position(
        self, intent: OrderIntent | None = None, broker_order_id: str = "brk-1"
    ) -> tuple[str, OrderIntent]:
        order_id, position_id, intent = self.prepare(intent)
        self.store.record_submission(order_id, broker_order_id=broker_order_id,
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("3.13"), now=NOW,
        )
        self.store.apply_entry_outcome(position_id, state=OrderState.FILLED,
                                       filled_quantity=1, avg_debit=Decimal("3.13"), now=NOW)
        return position_id, intent

    def incidents(self) -> list[Incident]:
        with Session(self.engine) as session:
            return list(session.scalars(select(Incident)).all())


class StartupRecoveryTests(ReconcileCase):
    def test_a_pending_entry_that_filled_while_we_were_down_becomes_open(self) -> None:
        # EXIT-002: the crash-during-submit case.
        _, position_id, intent = self.prepare()
        broker = FakeBroker(
            positions=[{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}],
            by_client_id={intent.client_order_id: filled_order(intent.client_order_id)},
        )
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.OPEN)
        self.assertEqual(managed.avg_entry_debit, Decimal("3.13"))
        self.assertTrue(report.clean, report.mismatches)
        self.assertIs(report.execution_state, ExecutionState.NORMAL)

    def test_a_pending_entry_that_was_canceled_becomes_abandoned(self) -> None:
        _, position_id, intent = self.prepare()
        broker = FakeBroker(by_client_id={
            intent.client_order_id: {
                "client_order_id": intent.client_order_id, "id": "brk-1",
                "status": "canceled", "filled_qty": "0", "filled_avg_price": None,
            }
        })
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.ABANDONED)
        self.assertTrue(report.clean)

    def test_a_submitted_entry_the_broker_cannot_find_raises_an_incident(self) -> None:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status=None, ambiguous=True, now=NOW)
        report = Reconciler(FakeBroker(), self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertEqual([i.kind for i in self.incidents()], ["ambiguous_entry"])


class MismatchTests(ReconcileCase):
    def test_an_open_position_the_broker_does_not_hold_halts_new_risk(self) -> None:
        position_id, _ = self.open_position()
        report = Reconciler(FakeBroker(positions=[]), self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertIn("position_vanished", [i.kind for i in self.incidents()])
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.INCIDENT)

    def test_broker_exposure_nobody_owns_halts_new_risk(self) -> None:
        broker = FakeBroker(positions=[{"symbol": "SPY260918P00600000", "qty": "-1"}])
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertEqual(report.unexpected_symbols, ["SPY260918P00600000"])
        self.assertIn("unexpected_exposure", [i.kind for i in self.incidents()])

    def test_an_unreachable_broker_halts_new_risk_rather_than_assuming_flat(self) -> None:
        broker = FakeBroker(raises=ConnectionError("network down"))
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertTrue(report.broker_unreachable)
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertIn("broker_unreachable", [i.kind for i in self.incidents()])

    def test_an_unresolved_incident_keeps_new_risk_halted_on_later_passes(self) -> None:
        self.open_position()
        store, broker = self.store, FakeBroker(positions=[])
        Reconciler(broker, store).reconcile(now=NOW)
        second = Reconciler(broker, store).reconcile(now=NOW)
        self.assertIs(second.execution_state, ExecutionState.NO_NEW_RISK)


class ReentryOnTheSameContractsTests(ReconcileCase):
    """The 2026-08-31 case: abandon an entry, re-enter the same spread.

    The live worker submitted a SPY 765/775 call debit spread at 09:51 ET, the
    order never filled, and the deadline cancelled it - so the position went to
    ABANDONED. It re-entered the identical spread at 11:05 ET and that one
    filled. Both rows then named the same two contracts, and every reconcile
    cycle read the live position's legs as evidence that the abandoned order
    had filled late, raising a false `late_fill_after_terminal` incident once a
    minute until the table was mostly noise.
    """

    def abandoned_then_open(self) -> tuple[str, str]:
        dead_order, dead_position, intent = self.prepare()
        self.store.record_submission(dead_order, broker_order_id="brk-dead",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            dead_order, broker_status="canceled", filled_quantity=0,
            filled_avg_price=None, now=NOW,
        )
        self.store.apply_entry_outcome(dead_position, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        # A re-entry is a different decision, so it carries a different intent
        # and a different client order id; the duplicate guard would refuse a
        # literal resubmission of the same approved authority.
        live_position, _ = self.open_position(
            entry_intent(decision_hash="sha256:reentry"), broker_order_id="brk-live"
        )
        return dead_position, live_position

    def held_by_the_broker(self) -> FakeBroker:
        return FakeBroker(positions=[{"symbol": LONG, "qty": "1"},
                                     {"symbol": SHORT, "qty": "-1"}])

    def test_the_live_position_claims_the_exposure_not_the_abandoned_one(self) -> None:
        dead_position, live_position = self.abandoned_then_open()
        report = Reconciler(self.held_by_the_broker(), self.store).reconcile(now=NOW)

        self.assertTrue(report.clean, report.mismatches)
        self.assertNotIn("late_fill_after_terminal", [i.kind for i in self.incidents()])
        dead = self.store.get_position(dead_position)
        live = self.store.get_position(live_position)
        assert dead is not None and live is not None
        self.assertIs(dead.state, PositionState.ABANDONED)
        self.assertIs(live.state, PositionState.OPEN)

    def test_exposure_beyond_what_the_live_position_explains_is_still_reported(self) -> None:
        """Consuming exposure must not become a way to hide it."""
        self.abandoned_then_open()
        broker = FakeBroker(positions=[{"symbol": LONG, "qty": "2"},
                                       {"symbol": SHORT, "qty": "-2"}])
        report = Reconciler(broker, self.store).reconcile(now=NOW)

        self.assertFalse(report.clean)
        self.assertIn("late_fill_after_terminal", [i.kind for i in self.incidents()])

    def test_a_genuine_late_fill_is_still_caught_with_no_live_position(self) -> None:
        dead_order, dead_position, _ = self.prepare()
        self.store.record_submission(dead_order, broker_order_id="brk-dead",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            dead_order, broker_status="canceled", filled_quantity=0,
            filled_avg_price=None, now=NOW,
        )
        self.store.apply_entry_outcome(dead_position, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        report = Reconciler(self.held_by_the_broker(), self.store).reconcile(now=NOW)

        self.assertFalse(report.clean)
        self.assertIn("late_fill_after_terminal", [i.kind for i in self.incidents()])


class IncidentsDoNotRepeatTests(ReconcileCase):
    """One open problem is one incident, however many times it is re-observed.

    Most conditions self-limit because raising an incident moves the position
    to INCIDENT and it stops being re-examined. A terminal position is the
    exception - `open_incident` deliberately refuses to overwrite CLOSED or
    ABANDONED - so a late fill on an abandoned position is re-observed every
    cycle forever. On 2026-08-31 that produced twelve identical rows in eleven
    minutes.
    """

    def abandoned_with_broker_exposure(self) -> FakeBroker:
        order_id, position_id, _ = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-dead",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="canceled", filled_quantity=0,
            filled_avg_price=None, now=NOW,
        )
        self.store.apply_entry_outcome(position_id, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        return FakeBroker(positions=[{"symbol": LONG, "qty": "1"},
                                     {"symbol": SHORT, "qty": "-1"}])

    def test_a_condition_re_observed_every_cycle_raises_one_incident(self) -> None:
        broker = self.abandoned_with_broker_exposure()
        for _ in range(5):
            Reconciler(broker, self.store).reconcile(now=NOW)

        late = [i for i in self.incidents() if i.kind == "late_fill_after_terminal"]
        self.assertEqual(len(late), 1)

    def test_every_cycle_still_reports_the_mismatch(self) -> None:
        """Deduplicating the record must not quiet the halt."""
        broker = self.abandoned_with_broker_exposure()
        for _ in range(3):
            report = Reconciler(broker, self.store).reconcile(now=NOW)
            self.assertFalse(report.clean)
            self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)

    def test_deduplicating_the_row_still_re_marks_the_position(self) -> None:
        """The row is suppressed; the state transition is not.

        A condition can be healed at the top of a tick and re-observed at the
        bottom. If the duplicate row also swallowed the transition, the position
        would be left looking healthy while the problem was still open.
        """
        position_id, _ = self.open_position()
        for _ in range(2):
            self.store.open_incident(
                kind="position_vanished", detail="same detail",
                position_id=position_id, now=NOW,
            )
            with Session(self.engine) as session:
                row = session.get(Position, position_id)
                assert row is not None
                row.lifecycle_status = PositionState.OPEN.value  # heal
                session.commit()

        self.store.open_incident(
            kind="position_vanished", detail="same detail",
            position_id=position_id, now=NOW,
        )
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.INCIDENT)
        self.assertEqual(
            len([i for i in self.incidents() if i.kind == "position_vanished"]), 1
        )

    def test_a_resolved_incident_can_be_raised_again(self) -> None:
        """Deduplication is about an *open* item, not about silencing a recurrence."""
        broker = self.abandoned_with_broker_exposure()
        Reconciler(broker, self.store).reconcile(now=NOW)
        first = [i for i in self.incidents() if i.kind == "late_fill_after_terminal"]
        self.assertEqual(len(first), 1)

        with Session(self.engine) as session:
            row = session.get(Incident, first[0].id)
            assert row is not None
            row.resolved_at = NOW
            session.commit()

        Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertEqual(
            len([i for i in self.incidents() if i.kind == "late_fill_after_terminal"]), 2
        )


class CloseReconciliationTests(ReconcileCase):
    def closing(self) -> tuple[str, OrderIntent]:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id="brk-1",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(order_id, broker_status="filled",
                                              filled_quantity=1,
                                              filled_avg_price=Decimal("3.13"), now=NOW)
        self.store.apply_entry_outcome(position_id, state=OrderState.FILLED,
                                       filled_quantity=1, avg_debit=Decimal("3.13"), now=NOW)
        closing = build_close_intent(intent, approval_reference="exit:stop",
                                     limit_price=Decimal("2.80"), now=NOW)
        self.store.prepare_close(position_id=position_id, decision_id=self.decision_id,
                                 intent=closing,
                                 request=prepare_mleg_request(closing, now=NOW),
                                 reason="stop_loss", now=NOW)
        return position_id, closing

    def test_a_close_only_completes_when_the_broker_is_flat(self) -> None:
        position_id, closing = self.closing()
        still_held = FakeBroker(
            positions=[{"symbol": LONG, "qty": "1"}],
            by_client_id={closing.client_order_id: filled_order(
                closing.client_order_id, status="new")},
        )
        Reconciler(still_held, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.CLOSING, "must not report flat early")

        flat = FakeBroker(positions=[], by_client_id={
            closing.client_order_id: filled_order(closing.client_order_id)})
        Reconciler(flat, self.store).reconcile(now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.CLOSED)

    def test_a_closed_position_leaves_the_active_set(self) -> None:
        position_id, closing = self.closing()
        flat = FakeBroker(positions=[], by_client_id={
            closing.client_order_id: filled_order(closing.client_order_id)})
        Reconciler(flat, self.store).reconcile(now=NOW)
        self.assertEqual(self.store.active_positions(), [])
        self.assertIsNotNone(self.store.get_position(position_id))


class NoWorkTests(ReconcileCase):
    def test_nothing_to_reconcile_is_clean_and_permits_new_risk(self) -> None:
        report = Reconciler(FakeBroker(), self.store).reconcile(now=NOW)
        self.assertTrue(report.clean)
        self.assertIs(report.execution_state, ExecutionState.NORMAL)
        self.assertEqual(report.summary(), "nothing to reconcile")

    def test_reconciliation_never_submits(self) -> None:
        self.prepare()
        # FakeBroker.submit raises if called.
        Reconciler(FakeBroker(), self.store).reconcile(now=NOW)




class IncidentHealingTests(ReconcileCase):
    """Reconciliation exists to heal an incident once the facts are known."""

    def test_an_ambiguous_entry_resolves_once_the_order_is_found(self) -> None:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status=None, ambiguous=True, now=NOW)
        self.store.open_incident(kind="ambiguous_entry_submission",
                                 detail="outcome unknown", position_id=position_id, now=NOW)
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.INCIDENT)

        # The order turns out to have filled after all.
        broker = FakeBroker(
            positions=[{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}],
            by_client_id={intent.client_order_id: filled_order(intent.client_order_id)},
        )
        Reconciler(broker, self.store).reconcile(now=NOW)
        healed = self.store.get_position(position_id)
        assert healed is not None
        self.assertIs(healed.state, PositionState.OPEN)
        self.assertEqual(healed.avg_entry_debit, Decimal("3.13"))

    def test_an_ambiguous_entry_that_never_existed_resolves_to_abandoned(self) -> None:
        order_id, position_id, intent = self.prepare()
        self.store.record_submission(order_id, broker_order_id=None,
                                     broker_status=None, ambiguous=True, now=NOW)
        self.store.open_incident(kind="ambiguous_entry_submission",
                                 detail="outcome unknown", position_id=position_id, now=NOW)
        broker = FakeBroker(by_client_id={
            intent.client_order_id: {
                "client_order_id": intent.client_order_id, "id": "brk-1",
                "status": "rejected", "filled_qty": "0", "filled_avg_price": None,
            }
        })
        Reconciler(broker, self.store).reconcile(now=NOW)
        healed = self.store.get_position(position_id)
        assert healed is not None
        self.assertIs(healed.state, PositionState.ABANDONED)


if __name__ == "__main__":
    unittest.main()


class LegQuantityTests(ReconcileCase):
    """Symbol presence is not exposure. Finding 3 of the improvement plan.

    Every case below reports both leg symbols the local record claims, so the
    previous set-intersection check called each of them clean.
    """

    def test_a_short_leg_left_behind_by_a_partial_close_is_a_mismatch(self) -> None:
        # The long leg closed and the short did not. What remains is a naked
        # short call: unlimited-risk exposure the governor never sized.
        position_id, _ = self.open_position()
        broker = FakeBroker(positions=[{"symbol": SHORT, "qty": "-1"}])
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertFalse(report.clean, "a broken vertical is not a reconciled position")
        self.assertIs(report.execution_state, ExecutionState.NO_NEW_RISK)
        self.assertIn("leg_imbalance", [i.kind for i in self.incidents()])
        managed = self.store.get_position(position_id)
        assert managed is not None
        self.assertIs(managed.state, PositionState.INCIDENT)

    def test_a_quantity_drift_on_one_leg_is_a_mismatch(self) -> None:
        # Both symbols present, both sides right, quantities unequal.
        self.open_position()
        broker = FakeBroker(
            positions=[{"symbol": LONG, "qty": "2"}, {"symbol": SHORT, "qty": "-1"}]
        )
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertIn("leg_imbalance", [i.kind for i in self.incidents()])

    def test_an_inverted_leg_is_a_mismatch(self) -> None:
        # Right symbols, right quantities, wrong signs: the spread is backwards
        # and its maximum loss is not the debit we approved.
        self.open_position()
        broker = FakeBroker(
            positions=[{"symbol": LONG, "qty": "-1"}, {"symbol": SHORT, "qty": "1"}]
        )
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertFalse(report.clean)
        self.assertIn("leg_imbalance", [i.kind for i in self.incidents()])

    def test_an_unsigned_quantity_beside_an_explicit_short_side_is_read_as_short(self) -> None:
        # A provider that reports qty "1" with side "short" must not be read as
        # a long position, which would invert the whole comparison.
        self.open_position()
        broker = FakeBroker(positions=[
            {"symbol": LONG, "qty": "1", "side": "long"},
            {"symbol": SHORT, "qty": "1", "side": "short"},
        ])
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertTrue(report.clean, report.mismatches)

    def test_the_matching_vertical_still_reconciles_clean(self) -> None:
        self.open_position()
        broker = FakeBroker(
            positions=[{"symbol": LONG, "qty": "1"}, {"symbol": SHORT, "qty": "-1"}]
        )
        report = Reconciler(broker, self.store).reconcile(now=NOW)
        self.assertTrue(report.clean, report.mismatches)
        self.assertEqual([], [i.kind for i in self.incidents()])


class NestedLegPreservationTests(unittest.TestCase):
    """Finding 4: an MLeg order's per-leg fills must survive normalization."""

    def test_normalization_walks_containers_instead_of_stringifying_them(self) -> None:
        from options_alpha_lab.execution.gateway import _as_dict
        from options_alpha_lab.execution.reconcile import _leg_fills

        class Order:
            """Shaped like a pydantic order: model_dump returns nested values."""

            @staticmethod
            def model_dump() -> dict[str, Any]:
                return {
                    "status": "filled",
                    "filled_qty": 1,
                    "filled_avg_price": Decimal("3.13"),
                    "legs": [
                        {"symbol": LONG, "filled_qty": 1,
                         "filled_avg_price": Decimal("6.90")},
                        {"symbol": SHORT, "filled_qty": 1,
                         "filled_avg_price": Decimal("3.77")},
                    ],
                }

        normalized = _as_dict(Order())
        self.assertIsInstance(normalized["legs"], list, "legs must not be stringified")
        # Scalars still normalize to strings, which is what the comparison needs.
        self.assertEqual(normalized["filled_avg_price"], "3.13")

        # The real regression: this raised AttributeError while legs was a
        # string, taking reconciliation down on the first genuine MLeg fill.
        fills = _leg_fills(normalized)
        self.assertEqual(
            [(f["symbol"], f["quantity"], f["price"]) for f in fills],
            [(LONG, 1, "6.90"), (SHORT, 1, "3.77")],
        )
