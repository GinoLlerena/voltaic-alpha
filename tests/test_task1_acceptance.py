"""Acceptance tests for Multi-Position Task 1 — manage many, enter one.

Written **before** the implementation, which is the order `SRC-HANDOFF` section
14 asks for: reproduce two simultaneous active positions first, then refactor.
Every test here is the executable form of a row in `SRC-TASK-1` section 6.

Tests for behaviour Task 1 has not built yet carry
`@pytest.mark.xfail(strict=True)`. That is deliberate and load-bearing in both
directions. The suite stays green today, so these can be committed without
breaking the gate; and the moment the behaviour arrives the test **fails** as
`XPASS(strict)`, which is a demand to delete the marker rather than a quiet
pass nobody notices. A skipped test would rot instead.

The tests without that marker already pass. They are here to pin behaviour Task
1 must not regress while it rearranges everything around them.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import Direction, ExecutionState, PriceSource
from options_alpha_lab.execution.intent import IntentLeg, OrderIntent
from options_alpha_lab.execution.lifecycle import (
    OrderState,
    PositionState,
    TypedInvalidation,
)
from options_alpha_lab.execution.reconcile import Reconciler
from options_alpha_lab.execution.request import prepare_mleg_request
from options_alpha_lab.persistence.models import Incident
from options_alpha_lab.persistence.models import Position as PositionRow
from test_agent import (
    NOW,
    WRITE_ENV,
    DurableAgentCase,
    FakeBroker,
    occ,
)

#: A second, disjoint vertical. Different strikes, so nothing about it overlaps
#: the first: these are two independent strategies, not two lots of one.
LONG_A, SHORT_A = occ(619), occ(624)
LONG_B, SHORT_B = occ(630), occ(635)

PENDING = "Task 1 (T1-01..T1-06) is not implemented; see SRC-TASK-1"


def intent_for(long_symbol: str, short_symbol: str, tag: str) -> OrderIntent:
    from options_alpha_lab.architecture.contracts import SpreadStrategy

    return OrderIntent(
        decision_hash=f"sha256:{tag}",
        strategy=SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        legs=(IntentLeg(long_symbol, 1, "buy", "buy_to_open"),
              IntentLeg(short_symbol, 1, "sell", "sell_to_open")),
        strategy_quantity=1, limit_price=Decimal("3.39"),
        approval_reference="risk", created_at=NOW,
        expires_at=NOW + timedelta(seconds=90),
    )


class Task1Case(DurableAgentCase):
    """`DurableAgentCase`, but able to hold more than one position at a time."""

    def open_spread(
        self, long_symbol: str, short_symbol: str, tag: str, *,
        avg_debit: str = "3.13", invalidation: str = "600.00",
        filled_at: datetime | None = None, leave_pending: bool = False,
    ) -> str:
        intent = intent_for(long_symbol, short_symbol, tag)
        order_id, position_id = self.store.prepare_entry(
            decision_id=self.decision_id, intent=intent,
            request=prepare_mleg_request(intent, now=NOW),
            direction=Direction.BULLISH, long_symbol=long_symbol,
            short_symbol=short_symbol, expiration=NOW + timedelta(days=25),
            width=Decimal("5.00"), max_loss=Decimal("339.00"),
            invalidation=TypedInvalidation(
                Decimal(invalidation), Direction.BULLISH,
                PriceSource.COMPLETED_DAILY_CLOSE,
            ),
            now=NOW,
        )
        self.store.record_submission(
            order_id, broker_order_id=f"brk-{tag}", broker_status="accepted", now=NOW
        )
        if leave_pending:
            return position_id
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal(avg_debit), now=NOW,
        )
        self.store.apply_entry_outcome(
            position_id, state=OrderState.FILLED, filled_quantity=1,
            avg_debit=Decimal(avg_debit), now=filled_at or NOW,
        )
        return position_id

    def exposure(self, *pairs: tuple[str, str]) -> list[dict[str, Any]]:
        held: list[dict[str, Any]] = []
        for long_symbol, short_symbol in pairs:
            held.append({"symbol": long_symbol, "qty": "1"})
            held.append({"symbol": short_symbol, "qty": "-1"})
        return held

    def states(self) -> dict[str, str]:
        with Session(self.store._engine) as session:  # noqa: SLF001 - test introspection
            return {
                row.id: row.lifecycle_status
                for row in session.scalars(select(PositionRow)).all()
            }

    def incidents(self) -> list[Incident]:
        with Session(self.store._engine) as session:  # noqa: SLF001 - test introspection
            return list(session.scalars(select(Incident)).all())


# ------------------------------------------------------- managing several rows
class ManagingSeveralPositionsTests(Task1Case):
    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_01_one_stop_fires_and_one_holds(self) -> None:
        """Both are marked and evaluated; only the stop-triggered one closes."""
        agent = self.build(WRITE_ENV)
        stopping = self.open_spread(LONG_A, SHORT_A, "a", invalidation="9999.00")
        holding = self.open_spread(LONG_B, SHORT_B, "b", invalidation="1.00")
        self.with_recon(agent, self.exposure((LONG_A, SHORT_A), (LONG_B, SHORT_B)))

        cycle = agent.manage_positions()  # type: ignore[attr-defined]

        self.assertEqual(cycle.positions_valued, 2)
        by_id = {r.position_id: r for r in cycle.results}
        self.assertEqual(set(by_id), {stopping, holding})
        self.assertIsNotNone(by_id[stopping].submitted_order_id)
        self.assertIsNone(by_id[holding].submitted_order_id)

    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_02_two_exits_in_one_cycle_do_not_suppress_each_other(self) -> None:
        agent = self.build(WRITE_ENV)
        first = self.open_spread(LONG_A, SHORT_A, "a", invalidation="9999.00")
        second = self.open_spread(LONG_B, SHORT_B, "b", invalidation="9999.00")
        self.with_recon(agent, self.exposure((LONG_A, SHORT_A), (LONG_B, SHORT_B)))

        cycle = agent.manage_positions()  # type: ignore[attr-defined]

        submitted = {
            r.position_id for r in cycle.results if r.submitted_order_id is not None
        }
        self.assertEqual(submitted, {first, second})

    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_03_a_failed_close_does_not_stop_the_other(self) -> None:
        class OneBadSubmit(FakeBroker):
            calls = 0

            def submit(self, *args: Any, **kwargs: Any) -> Any:
                OneBadSubmit.calls += 1
                if OneBadSubmit.calls == 1:
                    raise RuntimeError("broker refused the first close")
                return super().submit(*args, **kwargs)

        agent = self.build(WRITE_ENV, broker=OneBadSubmit())
        self.open_spread(LONG_A, SHORT_A, "a", invalidation="9999.00")
        self.open_spread(LONG_B, SHORT_B, "b", invalidation="9999.00")
        self.with_recon(agent, self.exposure((LONG_A, SHORT_A), (LONG_B, SHORT_B)))

        cycle = agent.manage_positions()  # type: ignore[attr-defined]

        failed = [r for r in cycle.results if r.incident_id is not None]
        submitted = [r for r in cycle.results if r.submitted_order_id is not None]
        self.assertEqual(len(failed), 1, "the failure is position-linked")
        self.assertEqual(len(submitted), 1, "the other close still proceeded")

    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_04_an_open_and_a_pending_are_both_serviced(self) -> None:
        agent = self.build(WRITE_ENV)
        opened = self.open_spread(LONG_A, SHORT_A, "a")
        pending = self.open_spread(LONG_B, SHORT_B, "b", leave_pending=True)
        self.with_recon(agent, self.exposure((LONG_A, SHORT_A)))

        cycle = agent.manage_positions()  # type: ignore[attr-defined]

        seen = {r.position_id for r in cycle.results}
        self.assertIn(opened, seen, "the open position is valued")
        self.assertIn(pending, seen, "the pending entry is reported, not skipped")

    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_07_one_unvaluable_position_does_not_suppress_the_others(self) -> None:
        agent = self.build(WRITE_ENV)
        valuable = self.open_spread(LONG_A, SHORT_A, "a")
        # Contracts the snapshot chain does not carry: it cannot be priced.
        unvaluable = self.open_spread(occ(700), occ(705), "z")
        self.with_recon(agent, self.exposure((LONG_A, SHORT_A), (occ(700), occ(705))))

        cycle = agent.manage_positions()  # type: ignore[attr-defined]

        by_id = {r.position_id: r for r in cycle.results}
        self.assertIn(valuable, by_id)
        self.assertIsNotNone(by_id[unvaluable].incident_id)
        self.assertEqual(by_id[valuable].incident_id, None)


class DeterministicOrderTests(Task1Case):
    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_06_database_return_order_does_not_change_the_outcome(self) -> None:
        """`active_positions()` has no ORDER BY, so today this is luck."""
        agent = self.build(WRITE_ENV)
        self.open_spread(LONG_A, SHORT_A, "a")
        self.open_spread(LONG_B, SHORT_B, "b")

        first = [p.position_id for p in agent.managed_positions()]  # type: ignore[attr-defined]
        with Session(self.store._engine) as session:  # noqa: SLF001
            for row in session.scalars(select(PositionRow)).all():
                row.recorded_at = row.recorded_at + timedelta(microseconds=1)
            session.commit()
        second = [p.position_id for p in agent.managed_positions()]  # type: ignore[attr-defined]

        self.assertEqual(first, second)


class BatchDurationTests(Task1Case):
    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_13_a_management_batch_stays_inside_the_lease_margin(self) -> None:
        """30 s against the 90 s LEASE_TTL. Nothing heartbeats during a batch."""
        from options_alpha_lab.worker import LEASE_TTL

        agent = self.build(WRITE_ENV)
        self.open_spread(LONG_A, SHORT_A, "a")
        self.open_spread(LONG_B, SHORT_B, "b")
        self.with_recon(agent, self.exposure((LONG_A, SHORT_A), (LONG_B, SHORT_B)))

        cycle = agent.manage_positions()  # type: ignore[attr-defined]

        self.assertLessEqual(cycle.elapsed_ms, 30_000)
        self.assertLessEqual(
            Decimal(cycle.elapsed_ms) / Decimal(1000),
            Decimal(LEASE_TTL.total_seconds()) / Decimal(3),
        )


# ------------------------------------------------- inherited overlapping lots
class OverlappingContractsTests(unittest.TestCase):
    """`T1-05`. Section 2.1 of `SRC-TASK-1` records what happens today.

    Both scenarios below are currently answered by attributing broker exposure
    to whichever local row is settled first, which is a decision the task
    document forbids and which follows unordered database return order.
    """

    def setUp(self) -> None:
        from test_reconcile import ReconcileCase

        self.case = ReconcileCase("run")
        self.case.setUp()

    def tearDown(self) -> None:
        self.case.tearDown()

    def two_live_rows(self) -> tuple[str, str]:
        from test_reconcile import entry_intent

        a, _ = self.case.open_position(entry_intent(decision_hash="sha256:a"), "brk-a")
        b, _ = self.case.open_position(entry_intent(decision_hash="sha256:b"), "brk-b")
        return a, b

    def reconcile(self, long_qty: str, short_qty: str) -> Any:
        from test_reconcile import LONG, SHORT, FakeBroker

        broker = FakeBroker(positions=[{"symbol": LONG, "qty": long_qty},
                                       {"symbol": SHORT, "qty": short_qty}])
        return Reconciler(broker, self.case.store).reconcile()

    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_09_no_row_changes_state_by_attribution(self) -> None:
        """Broker holds the correct aggregate for two live lots.

        Today: `leg_imbalance` against the first row, which goes to INCIDENT.
        A healthy pair reported as broken, because one local row is compared
        against an aggregate quantity.
        """
        a, b = self.two_live_rows()
        report = self.reconcile("2", "-2")

        self.assertFalse(report.clean, "the ambiguity itself must halt new risk")
        for position_id in (a, b):
            managed = self.case.store.get_position(position_id)
            assert managed is not None
            self.assertIs(
                managed.state, PositionState.OPEN,
                "neither overlapping row may change lifecycle state by attribution",
            )

    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_09b_a_missing_lot_names_no_survivor(self) -> None:
        """One lot genuinely closed; the broker holds one spread.

        Today: the first row silently claims the survivor and the second is
        declared `position_vanished`. Which row wins depends on database order.
        """
        a, b = self.two_live_rows()
        report = self.reconcile("1", "-1")

        self.assertFalse(report.clean)
        kinds = [i.kind for i in self.case.incidents()]
        self.assertNotIn(
            "position_vanished", kinds,
            "the shortfall is an aggregate fact; no individual row vanished",
        )
        states = {
            self.case.store.get_position(p).state  # type: ignore[union-attr]
            for p in (a, b)
        }
        self.assertEqual(
            states, {PositionState.OPEN},
            "no row may be declared the survivor while attribution is ambiguous",
        )

    def test_t1_ac_10_a_late_fill_with_no_live_claimant_is_still_caught(self) -> None:
        """Passes today. Pinned so `T1-05` cannot silence it while generalising."""
        from test_reconcile import LONG, SHORT, FakeBroker, entry_intent

        order_id, position_id, _ = self.case.prepare(entry_intent())
        self.case.store.record_submission(
            order_id, broker_order_id="brk-dead", broker_status="accepted", now=NOW
        )
        self.case.store.apply_order_reconciliation(
            order_id, broker_status="canceled", filled_quantity=0,
            filled_avg_price=None, now=NOW,
        )
        self.case.store.apply_entry_outcome(
            position_id, state=OrderState.CANCELED, filled_quantity=0,
            avg_debit=None, now=NOW,
        )
        broker = FakeBroker(positions=[{"symbol": LONG, "qty": "1"},
                                       {"symbol": SHORT, "qty": "-1"}])
        report = Reconciler(broker, self.case.store).reconcile()

        self.assertFalse(report.clean)
        self.assertIn(
            "late_fill_after_terminal", [i.kind for i in self.case.incidents()]
        )

    def test_t1_ac_05_every_row_is_reconciled_before_entry_is_considered(self) -> None:
        """Passes today: reconciliation already iterates the whole set."""
        from test_reconcile import entry_intent

        self.case.open_position(entry_intent(decision_hash="sha256:a"), "brk-a")
        self.case.open_position(entry_intent(decision_hash="sha256:b"), "brk-b")
        self.case.prepare(entry_intent(decision_hash="sha256:c"))

        report = self.reconcile("2", "-2")

        self.assertEqual(
            report.positions_checked, 3,
            "pending rows are reconstructed too, not only filled ones",
        )


class EntryStaysCappedTests(Task1Case):
    def test_t1_ac_12_a_second_entry_is_refused_with_several_positions(self) -> None:
        """Passes today, and is the invariant Task 1 must not weaken."""
        from options_alpha_lab.execution.gateway import ExecutionRefused

        agent = self.build(WRITE_ENV, broker=FakeBroker(open_strategies=2))
        self.open_spread(LONG_A, SHORT_A, "a")
        self.open_spread(LONG_B, SHORT_B, "b")
        intent = intent_for(occ(640), occ(645), "new")

        with self.assertRaises(ExecutionRefused) as ctx:
            agent.gateway.submit(
                intent, prepare_mleg_request(intent, now=NOW),
                reduces_risk=False, operator_approval="operator:test",
            )
        self.assertIn(
            "one open or pending strategy", str(ctx.exception).lower(),
            "the cap is stated by the gateway, not inferred by the caller",
        )

    def test_t1_ac_08_no_new_risk_still_permits_a_close(self) -> None:
        """Passes today. Only FREEZE_ALL_WRITES may block risk reduction."""
        agent = self.build(WRITE_ENV, state=ExecutionState.NO_NEW_RISK)
        self.open_spread(LONG_A, SHORT_A, "a")
        self.open_spread(LONG_B, SHORT_B, "b")
        closing = intent_for(LONG_A, SHORT_A, "close-a")

        result = agent.gateway.submit(
            closing, prepare_mleg_request(closing, now=NOW), reduces_risk=True
        )
        self.assertIsNotNone(result)


class IncidentVisibilityTests(Task1Case):
    @pytest.mark.xfail(strict=True, reason=PENDING)
    def test_t1_ac_11_an_incident_position_is_never_reported_flat(self) -> None:
        """Needs the cycle health `T1-06` introduces."""
        agent = self.build(WRITE_ENV)
        troubled = self.open_spread(LONG_A, SHORT_A, "a")
        self.store.open_incident(
            kind="leg_imbalance", detail="unbalanced", position_id=troubled, now=NOW,
        )
        self.with_recon(agent, self.exposure((LONG_A, SHORT_A)))

        cycle = agent.manage_positions()  # type: ignore[attr-defined]

        self.assertIn(troubled, {r.position_id for r in cycle.results})
        self.assertGreaterEqual(cycle.positions_seen, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
