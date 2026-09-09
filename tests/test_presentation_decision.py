"""Selected-decision isolation, tested against two complete lifecycles.

`CIIP-006`, and the disposition of `CIIP-VAL-002`. The plan requires isolation
to be proved with at least two lifecycles; the committed evidence contains one,
and one lifecycle cannot fail this way — every query returns the only records
there are, filtered or not. That is exactly how `CIIP-CV-003` survived review.

So the second lifecycle is built here as a fixture. These tests would have
failed against the pre-`CIIP-001` dashboard, which is the point of writing them.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab.persistence.models import (
    Base,
    BrokerOrder,
    Decision,
    Fill,
    MarketSnapshot,
    OrderIntent,
    Position,
    Run,
    ThesisRecord,
)
from options_alpha_lab.presentation.decision import load

NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)


def _build(session: Session, tag: str, *, price: str) -> Decision:
    """A complete lifecycle: snapshot, decision, memo, intent, orders, fills."""
    session.add(
        Run(
            id=f"run-{tag}",
            runtime_version="t",
            policy_version="t",
            bot_mode="paper_execute",
            trading_enabled=True,
            started_at=NOW,
        )
    )
    session.add(
        MarketSnapshot(
            id=f"snap-{tag}",
            run_id=f"run-{tag}",
            snapshot_id=f"spy-{tag}",
            symbol="SPY",
            provider="fixture",
            feed="fixture",
            source_time=NOW,
            received_time=NOW,
            underlying_price=600,
            payload_hash=f"ph-{tag}",
            payload={},
            data_quality={},
        )
    )
    decision = Decision(
        id=f"dec-{tag}",
        run_id=f"run-{tag}",
        market_snapshot_id=f"snap-{tag}",
        snapshot_id=f"spy-{tag}",
        action="OPTIONS_POSITION",
        direction="bullish",
        reason_codes=[],
        transitions=[],
        input_hash=f"ih-{tag}",
        decision_hash=f"dh-{tag}",
        policy_version="t",
        decided_at=NOW,
    )
    session.add(decision)
    session.add(
        ThesisRecord(
            id=f"th-{tag}",
            decision_id=f"dec-{tag}",
            synthesizer_name="s",
            direction="bullish",
            confidence="0.7",
            evidence_ids=[],
            counter_evidence_ids=[],
            invalidation_conditions=[],
            reasoning_summary=f"memo for {tag}",
        )
    )
    for role in ("entry", "close"):
        session.add(
            OrderIntent(
                id=f"i-{tag}-{role}",
                decision_id=f"dec-{tag}",
                intent_hash=f"ih-{tag}-{role}",
                client_order_id=f"oa-{tag}-{role}",
                legs=[],
                desired_limit_price=price,
                approval_reference="t",
                expires_at=NOW + timedelta(minutes=5),
            )
        )
        session.add(
            BrokerOrder(
                id=f"o-{tag}-{role}",
                order_intent_id=f"i-{tag}-{role}",
                client_order_id=f"oa-{tag}-{role}",
                role=role,
                status="filled",
                local_state="FILLED",
                terminal=True,
                strategy_quantity=1,
                prepared_at=NOW,
            )
        )
        session.add(
            Fill(
                id=f"f-{tag}-{role}",
                broker_order_id=f"o-{tag}-{role}",
                leg_symbol=f"SPY-{tag}",
                quantity=1,
                price=price,
                filled_at=NOW,
            )
        )
    session.add(
        Position(
            id=f"p-{tag}",
            decision_id=f"dec-{tag}",
            entry_order_id=f"o-{tag}-entry",
            strategy="bull_call_debit_spread",
            direction="bullish",
            lifecycle_status="CLOSED",
            long_symbol=f"L-{tag}",
            short_symbol=f"S-{tag}",
            expiration=NOW + timedelta(days=12),
            width=6,
            requested_quantity=1,
            open_risk=339,
        )
    )
    session.commit()
    return decision


class IsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.first = _build(self.session, "alpha", price="3.13")
        self.second = _build(self.session, "beta", price="7.77")

    def tearDown(self) -> None:
        self.session.close()

    def test_each_view_sees_only_its_own_orders(self) -> None:
        a = load(self.session, self.first)
        b = load(self.session, self.second)
        self.assertEqual(len(a.orders), 2)
        self.assertEqual(len(b.orders), 2)
        self.assertEqual(a.order_ids & b.order_ids, set())

    def test_each_view_sees_only_its_own_fills(self) -> None:
        a = load(self.session, self.first)
        # Numeric(18,6) round-trips as 3.130000, so compare values not strings.
        prices = {Decimal(str(f.price)) for f in a.fills}
        self.assertEqual(
            prices,
            {Decimal("3.13")},
            "a fill from the other lifecycle leaked in",
        )

    def test_each_view_sees_only_its_own_memo(self) -> None:
        a = load(self.session, self.first)
        self.assertEqual(len(a.theses), 1)
        self.assertIn("alpha", a.theses[0].reasoning_summary)

    def test_each_view_sees_only_its_own_position(self) -> None:
        b = load(self.session, self.second)
        self.assertEqual([p.id for p in b.positions], ["p-beta"])

    def test_each_view_sees_only_its_own_intents(self) -> None:
        a = load(self.session, self.first)
        self.assertTrue(all(i.decision_id == "dec-alpha" for i in a.intents))
        self.assertEqual(len(a.intents), 2)

    def test_fills_for_scopes_to_one_order(self) -> None:
        a = load(self.session, self.first)
        entry = next(o for o in a.orders if o.role == "entry")
        fills = a.fills_for(entry.id)
        self.assertEqual([f.id for f in fills], ["f-alpha-entry"])

    def test_a_decision_that_never_traded_has_an_empty_lineage(self) -> None:
        lonely = Decision(
            id="dec-none",
            run_id="run-alpha",
            market_snapshot_id="snap-alpha",
            snapshot_id="spy-none",
            action="NO_TRADE",
            direction="neutral",
            reason_codes=["no_qualified_setup"],
            transitions=[],
            input_hash="x",
            decision_hash="dh-none",
            policy_version="t",
            decided_at=NOW,
        )
        self.session.add(lonely)
        self.session.commit()
        view = load(self.session, lonely)
        self.assertEqual(view.orders, [])
        self.assertEqual(view.fills, [])
        self.assertEqual(view.positions, [])
        self.assertFalse(view.reached_the_broker)
        self.assertFalse(view.model_was_called)

    def test_a_missing_snapshot_does_not_raise(self) -> None:
        orphan = Decision(
            id="dec-orphan",
            run_id="run-alpha",
            market_snapshot_id="snap-absent",
            snapshot_id="spy-orphan",
            action="NO_TRADE",
            direction="neutral",
            reason_codes=[],
            transitions=[],
            input_hash="x",
            decision_hash="dh-orphan",
            policy_version="t",
            decided_at=NOW,
        )
        self.session.add(orphan)
        self.session.commit()
        self.assertIsNone(load(self.session, orphan).snapshot)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
