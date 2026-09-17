"""`CIIP-008`'s evidence, presented — and what the presentation refuses to say.

The interesting assertions are the negative ones. Over the recorded corpus every
`direction_agreed` is `NULL`, because every decision is a refusal, so any rate
computed from it would be a sentence about nothing. This module is where a win
rate would be invented if it were going to be, so the tests say it is not.
"""

from __future__ import annotations

import unittest
import uuid
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from options_alpha_lab import outcomes
from options_alpha_lab.calendar import TradingCalendar
from options_alpha_lab.persistence.models import (
    Base,
    Decision,
    MarketSnapshot,
    Position,
    Run,
)
from options_alpha_lab.presentation import horizons

NOW = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
SESSIONS = [{"date": d, "open": "09:30", "close": "16:00"} for d in
            ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-08")]


class HorizonCase(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.calendar = TradingCalendar.from_payload({"sessions": SESSIONS})
        self.session.add(Run(id="r", runtime_version="t", policy_version="h0",
                             bot_mode="observe", trading_enabled=False, started_at=NOW))
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def snapshot(self, sid: str, when: datetime, price: str) -> MarketSnapshot:
        row = MarketSnapshot(
            id=uuid.uuid4().hex, run_id="r", snapshot_id=sid, symbol="SPY", provider="t",
            feed="fixture", source_time=when, received_time=when,
            underlying_price=Decimal(price), payload_hash="h", payload={}, data_quality={},
        )
        self.session.add(row)
        self.session.commit()
        return row

    def decide(self, snap: MarketSnapshot, *, action: str = "NO_TRADE",
               direction: str = "neutral", at: datetime | None = None) -> Decision:
        row = Decision(
            id=uuid.uuid4().hex, run_id="r", market_snapshot_id=snap.id,
            snapshot_id=snap.snapshot_id, action=action, direction=direction,
            reason_codes=[], transitions=[], input_hash="i",
            decision_hash=f"sha256:{uuid.uuid4().hex}", policy_version="h0",
            decided_at=at or snap.source_time,
        )
        self.session.add(row)
        self.session.commit()
        outcomes.ensure_jobs(self.session, row)
        self.session.commit()
        return row


class NoRateIsEverComputedTests(HorizonCase):
    def test_no_field_can_be_read_as_a_rate(self) -> None:
        names = {f.name for f in fields(horizons.HorizonCounts)}
        names |= {f.name for f in fields(horizons.ReviewOverview)}
        for name in names:
            self.assertNotRegex(name, r"rate|ratio|percent|pct|accuracy|score|win")

    def test_an_all_unanswerable_corpus_says_so_rather_than_scoring_it(self) -> None:
        snap = self.snapshot("s1", NOW, "600")
        self.decide(snap)
        self.snapshot("s2", datetime(2026, 9, 2, 20, tzinfo=UTC), "606")
        outcomes.review(self.session, self.calendar,
                        now=datetime(2026, 9, 8, 21, tzinfo=UTC))
        self.session.commit()
        view = horizons.overview(self.session)
        self.assertGreater(view.resolved, 0)
        self.assertEqual(sum(h.agreed + h.disagreed for h in view.horizons), 0)
        self.assertIn("refusals", view.caveat)
        self.assertIn("no realised result", view.caveat)


class CaveatIsDerivedTests(HorizonCase):
    def test_nothing_reviewed_says_nothing_reviewed(self) -> None:
        self.decide(self.snapshot("s1", NOW, "600"))
        self.assertIn("No horizon has elapsed", horizons.overview(self.session).caveat)

    def test_it_changes_when_a_direction_becomes_answerable(self) -> None:
        """The sentence is computed, so it moves with the records rather than
        being prose somebody forgets to update."""
        snap = self.snapshot("s1", NOW, "600")
        self.decide(snap, action="OPTIONS_POSITION", direction="bullish")
        self.session.add(
            Position(
                id="p1",
                decision_id=self.session.scalars(select(Decision)).one().id,
                entry_order_id="o1",
                strategy="vertical",
                direction="bullish",
                lifecycle_status="OPEN",
                long_symbol="A",
                short_symbol="B",
                expiration=NOW,
                width=Decimal("5"),
                requested_quantity=1,
                filled_quantity=1,
                avg_entry_debit=Decimal("3"),
                open_risk=Decimal("300"),
                opened_at=NOW,
            )
        )
        self.session.commit()
        self.snapshot("s2", datetime(2026, 9, 2, 20, tzinfo=UTC), "606")
        outcomes.review(self.session, self.calendar, now=datetime(2026, 9, 8, 21, tzinfo=UTC))
        self.session.commit()
        caveat = horizons.overview(self.session).caveat
        self.assertIn("state a direction that can", caveat)
        self.assertIn("a sample, not a result", caveat)


class WaitingHorizonsAreShownTests(HorizonCase):
    def test_a_horizon_that_has_not_elapsed_is_listed_as_waiting(self) -> None:
        """Omitting it would make a decision awaiting review look reviewed."""
        decision = self.decide(self.snapshot("s1", NOW, "600"))
        rows = horizons.for_decision(self.session, decision)
        self.assertEqual([r.horizon for r in rows], [h.label for h in outcomes.HORIZONS])
        self.assertTrue(all(not r.resolved for r in rows))
        self.assertTrue(all(r.change is None for r in rows))

    def test_a_resolved_horizon_carries_what_it_observed(self) -> None:
        decision = self.decide(self.snapshot("s1", NOW, "600"))
        self.snapshot("s2", datetime(2026, 9, 2, 20, tzinfo=UTC), "606")
        outcomes.review(self.session, self.calendar,
                        now=datetime(2026, 9, 8, 21, tzinfo=UTC))
        self.session.commit()
        resolved = [r for r in horizons.for_decision(self.session, decision) if r.resolved]
        self.assertTrue(resolved)
        first = resolved[0]
        self.assertEqual(first.change, Decimal("6"))
        self.assertEqual(first.observed_snapshot_id, "s2")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
