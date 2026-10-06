"""The review read model (PUI Phase 4, step 2).

`docs/improvements/options_alpha_pui_phase4_read_models_v0_1.md` §4, approved 6
October 2026. Two things that must never be read as one: execution outcomes
(closed positions, realised from reconciled fills) and research horizons (what
the underlying did afterwards, one row per market session). Counts only.
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab import outcomes
from options_alpha_lab.api import dto
from options_alpha_lab.api.server import create_app
from options_alpha_lab.calendar import committed_calendar
from options_alpha_lab.execution.lifecycle import OrderState
from options_alpha_lab.persistence.models import Base, Decision, MarketSnapshot, Run
from options_alpha_lab.presentation.source import Source
from pgsupport import database_url
from positions_support import PositionsCase
from reconcile_support import NOW

ET = ZoneInfo("America/New_York")


def et(day: str, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(
        datetime.fromisoformat(day).date(), time(hour, minute), tzinfo=ET
    ).astimezone(UTC)


class Executions(PositionsCase):
    def page(self, kind: str = "closed", **params: Any) -> dict[str, Any]:
        query = "&".join(f"{k}={v}" for k, v in {"kind": kind, **params}.items())
        data: dict[str, Any] = self.client().get(
            f"/api/v1/review/executions?{query}"
        ).json()["data"]
        return data

    def test_a_source_with_no_closed_position_says_so_with_zeros(self) -> None:
        self.opened()  # an open position is not an outcome
        data = self.page()
        self.assertEqual((data["items"], data["closed"], data["abandoned"]), ([], 0, 0))

    def test_a_round_trip_carries_both_prices_and_a_result_from_the_fills(self) -> None:
        position_id = self.closed()
        (row,) = self.page()["items"]
        self.assertEqual(row["position"]["position_id"], position_id)
        self.assertEqual(row["result"], "closed")
        self.assertEqual(row["position"]["entry_debit"], "3.130000")
        self.assertEqual(row["close_price"], "2.800000")
        self.assertEqual(Decimal(row["position"]["realized"]), Decimal("-33.00"))
        self.assertEqual(row["position"]["close_reason"], "stop_loss")
        self.assertEqual((row["held_seconds"], row["sessions_held"]), (0, 0))

    def test_the_exit_that_produced_the_close_is_named(self) -> None:
        position_id, intent = self.opened()
        observation = self.mark(position_id, NOW)
        order_id = self.closing(position_id, intent)
        self.store.record_exit_decision(
            position_id=position_id, observation_id=observation, trigger="stop_loss",
            should_close=True, reason="spread value fell through the stop",
            evaluated=[{"trigger": "stop_loss", "met": True}], precedence=["stop_loss"],
            disposition="close_submitted", policy_version="h0-provisional-1",
            decided_at=NOW, unrealized=Decimal("-33.00"), close_order_id=order_id,
        )
        self.store.record_submission(order_id, broker_order_id="brk-c",
                                     broker_status="accepted", now=NOW)
        self.store.apply_order_reconciliation(
            order_id, broker_status="filled", filled_quantity=1,
            filled_avg_price=Decimal("2.80"), now=NOW,
        )
        self.store.apply_close_outcome(position_id, broker_flat=True, remaining_quantity=0,
                                       now=NOW + timedelta(hours=1))
        (row,) = self.page()["items"]
        self.assertEqual(row["exit_trigger"], "stop_loss")
        self.assertEqual(row["exit_reason"], "spread value fell through the stop")
        self.assertEqual(row["held_seconds"], 3600)

    def test_an_abandoned_entry_is_listed_apart_and_is_not_a_zero_result(self) -> None:
        self.closed()
        abandoned = self.pending()
        self.store.apply_entry_outcome(abandoned, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        closed = self.page("closed")
        self.assertEqual((closed["closed"], closed["abandoned"]), (1, 1))
        self.assertNotIn(abandoned, [r["position"]["position_id"] for r in closed["items"]])
        (row,) = self.page("abandoned")["items"]
        self.assertEqual(row["position"]["position_id"], abandoned)
        self.assertEqual(row["result"], "no_exposure")
        self.assertIsNone(row["position"]["realized"])
        self.assertIsNone(row["close_price"])

    def test_requests_outside_the_contract_are_refused(self) -> None:
        client = self.client()
        self.assertEqual(client.get("/api/v1/review/executions?kind=open").status_code, 422)
        for method in ("post", "put", "patch", "delete"):
            self.assertEqual(
                getattr(client, method)("/api/v1/review/executions").status_code, 405
            )


class JournalCase(unittest.TestCase):
    """Decisions on chosen days, in a database of the engine under test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(database_url(Path(self._tmp.name) / "j.db"), future=True)
        Base.metadata.create_all(self.engine)
        self.calendar, _ = committed_calendar()
        with Session(self.engine) as session:
            session.add(Run(
                id="run", runtime_version="t", policy_version="h0", bot_mode="observe",
                trading_enabled=False, started_at=et("2026-08-27", 9),
            ))
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self._tmp.cleanup()

    def snapshot(self, at: datetime, price: str) -> str:
        with Session(self.engine) as session:
            row = MarketSnapshot(
                id=uuid.uuid4().hex, run_id="run", snapshot_id=f"s-{uuid.uuid4().hex[:8]}",
                symbol="SPY", provider="test", feed="fixture", source_time=at,
                received_time=at, underlying_price=Decimal(price),
                payload_hash="sha256:snap", payload={}, data_quality={},
            )
            session.add(row)
            session.commit()
            return row.id

    def decide(
        self, snapshot_id: str, at: datetime, *, action: str = "NO_TRADE",
        direction: str = "neutral", reasons: tuple[str, ...] = ("no_qualified_setup",),
    ) -> str:
        with Session(self.engine) as session:
            row = Decision(
                id=uuid.uuid4().hex, run_id="run", market_snapshot_id=snapshot_id,
                snapshot_id=f"d-{uuid.uuid4().hex[:8]}", action=action, direction=direction,
                reason_codes=list(reasons), transitions=[], input_hash="sha256:in",
                decision_hash=f"sha256:{uuid.uuid4().hex}{uuid.uuid4().hex}",
                policy_version="h0", decided_at=at,
            )
            session.add(row)
            session.flush()
            outcomes.ensure_jobs(session, row)
            session.commit()
            return row.decision_hash.removeprefix("sha256:")

    def review(self, now: datetime) -> None:
        with Session(self.engine) as session:
            outcomes.review(session, self.calendar, now=now)
            session.commit()

    def client(self, now: datetime) -> TestClient:
        return TestClient(create_app(
            Source(self.engine, "LIVE", "test", "live"), clock=lambda: now
        ))

    def journal(self, now: datetime, **params: Any) -> dict[str, Any]:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        data: dict[str, Any] = self.client(now).get(
            f"/api/v1/review/sessions?{query}"
        ).json()["data"]
        return data


class Sessions(JournalCase):
    """Thu 27 Aug, Fri 28 Aug, Mon 31 Aug, Tue 1 Sep and Wed 2 Sep 2026."""

    WEDNESDAY = et("2026-09-02", 17)

    def build(self) -> dict[str, str]:
        # Thursday: three decisions on one close. Two identical refusals and a
        # bullish position.
        thursday = self.snapshot(et("2026-08-27", 9, 40), "600")
        made = {}
        self.decide(thursday, et("2026-08-27", 9, 45))
        self.decide(thursday, et("2026-08-27", 11))
        made["thu"] = self.decide(thursday, et("2026-08-27", 15), action="OPTIONS_POSITION",
                                  direction="bullish", reasons=())
        # Friday: one refusal for a different reason, reading Thursday's close.
        friday = self.snapshot(et("2026-08-28", 9, 40), "606")
        made["fri"] = self.decide(friday, et("2026-08-28", 10), reasons=("stale_data",))
        # Monday: nothing was recorded. Tuesday: one refusal.
        tuesday = self.snapshot(et("2026-09-01", 9, 40), "603")
        made["tue"] = self.decide(tuesday, et("2026-09-01", 10))
        self.snapshot(et("2026-09-02", 9, 40), "610")
        self.review(self.WEDNESDAY)
        return made

    def by_day(self, **params: Any) -> dict[str, dict[str, Any]]:
        data = self.journal(self.WEDNESDAY, limit=60, **params)
        return {row["day"]: row for row in data["items"]}

    def test_one_row_per_market_session_newest_first_from_the_first_decision(self) -> None:
        self.build()
        data = self.journal(self.WEDNESDAY, limit=60)
        self.assertEqual(
            [row["day"] for row in data["items"]],
            ["2026-09-02", "2026-09-01", "2026-08-31", "2026-08-28", "2026-08-27"],
        )
        self.assertEqual((data["total"], data["next_cursor"]), (5, None))
        self.assertEqual(data["horizons"], ["T+1", "T+3"])

    def test_a_days_decisions_are_one_row_with_their_verdicts_counted(self) -> None:
        made = self.build()
        thursday = self.by_day()["2026-08-27"]
        self.assertEqual(thursday["decisions"], 3)
        self.assertEqual(thursday["closes_read"], ["600.000000"])
        self.assertEqual(
            [(v["outcome"], v["direction"], v["reason_codes"], v["count"])
             for v in thursday["verdicts"]],
            [("refusal", "neutral", ["no_qualified_setup"], 2), ("position", "bullish", [], 1)],
        )
        self.assertEqual(thursday["latest_decision_id"], made["thu"])
        self.assertEqual(thursday["first_decided_at"], et("2026-08-27", 9, 45).isoformat())

    def test_the_horizon_is_counted_never_scored(self) -> None:
        self.build()
        one = self.by_day(horizon="T%2B1")["2026-08-27"]["horizon"]
        # Thursday's decisions read 600; one session later the record reads 606.
        self.assertEqual((one["horizon"], one["sessions"]), ("T+1", 1))
        self.assertEqual((one["resolved"], one["pending"]), (3, 0))
        self.assertEqual(one["at_horizon"], ["606.000000"])
        self.assertEqual((one["smallest_move"], one["largest_move"]), ("6.000000", "6.000000"))
        # The bullish position agreed with an up move; a refusal states no direction.
        self.assertEqual((one["agreed"], one["disagreed"], one["unanswerable"]), (1, 0, 2))

    def test_the_longer_horizon_reads_a_later_close(self) -> None:
        self.build()
        three = self.by_day(horizon="T%2B3")["2026-08-27"]["horizon"]
        self.assertEqual((three["sessions"], three["resolved"]), (3, 3))
        self.assertEqual(three["at_horizon"], ["603.000000"])

    def test_a_horizon_that_has_not_elapsed_is_pending_not_absent(self) -> None:
        self.build()
        tuesday = self.by_day(horizon="T%2B3")["2026-09-01"]["horizon"]
        self.assertEqual((tuesday["resolved"], tuesday["pending"]), (0, 1))
        self.assertEqual(tuesday["at_horizon"], [])
        self.assertIsNone(tuesday["smallest_move"])

    def test_a_session_with_no_decision_is_listed_and_says_nothing_more(self) -> None:
        self.build()
        monday = self.by_day()["2026-08-31"]
        self.assertEqual((monday["decisions"], monday["verdicts"]), (0, []))
        self.assertIsNone(monday["horizon"])
        self.assertIsNone(monday["latest_decision_id"])
        self.assertEqual(monday["open_at"], et("2026-08-31", 9, 30).isoformat())

    def test_the_journal_pages_backwards_by_day_without_loss_or_repeat(self) -> None:
        self.build()
        seen: list[str] = []
        before = None
        while True:
            params = {"limit": 2, **({"before": before} if before else {})}
            data = self.journal(self.WEDNESDAY, **params)
            seen += [row["day"] for row in data["items"]]
            before = data["next_cursor"]
            if before is None:
                break
        self.assertEqual(
            seen, ["2026-09-02", "2026-09-01", "2026-08-31", "2026-08-28", "2026-08-27"]
        )

    def test_a_row_links_to_exactly_its_sessions_decisions(self) -> None:
        self.build()
        client = self.client(self.WEDNESDAY)
        for day, expected in (("2026-08-27", 3), ("2026-08-28", 1), ("2026-08-31", 0)):
            data = client.get(f"/api/v1/decisions?day={day}").json()["data"]
            self.assertEqual((data["total"], len(data["items"])), (expected, expected), day)

    def test_a_late_evening_decision_belongs_to_its_new_york_day(self) -> None:
        # 19:30 in New York on Thursday is already Friday in UTC.
        snapshot = self.snapshot(et("2026-08-27", 9, 40), "600")
        self.decide(snapshot, et("2026-08-27", 19, 30))
        rows = self.by_day()
        self.assertEqual(rows["2026-08-27"]["decisions"], 1)
        self.assertEqual(rows["2026-08-28"]["decisions"], 0)

    def test_a_page_costs_the_same_statements_however_many_decisions_it_covers(self) -> None:
        from sqlalchemy import event

        self.build()
        client = self.client(self.WEDNESDAY)
        counted = [0]

        def count(*_: object) -> None:
            counted[0] += 1

        event.listen(self.engine, "before_cursor_execute", count)
        try:
            client.get("/api/v1/review/sessions?limit=60")
            few = counted[0]
            snapshot = self.snapshot(et("2026-09-02", 9, 45), "611")
            for minute in range(40):
                self.decide(snapshot, et("2026-09-02", 10, minute))
            counted[0] = 0
            client.get("/api/v1/review/sessions?limit=60")
            many = counted[0]
        finally:
            event.remove(self.engine, "before_cursor_execute", count)
        self.assertEqual(many, few, "a session's decisions must not cost a query each")

    def test_an_empty_source_has_an_empty_journal(self) -> None:
        data = self.journal(self.WEDNESDAY)
        self.assertEqual((data["items"], data["total"], data["next_cursor"]), ([], 0, None))

    def test_an_unknown_horizon_or_a_write_is_refused(self) -> None:
        client = self.client(self.WEDNESDAY)
        self.assertEqual(client.get("/api/v1/review/sessions?horizon=T%2B9").status_code, 422)
        self.assertEqual(client.get("/api/v1/review/sessions?before=soon").status_code, 422)
        self.assertEqual(client.post("/api/v1/review/sessions").status_code, 405)


class CountsOnly(unittest.TestCase):
    """Owner decision D3: no rate, average or score in the review contract."""

    FORBIDDEN = ("rate", "ratio", "percent", "pct", "average", "mean", "win", "score", "expect")

    def test_no_review_field_reads_like_a_score(self) -> None:
        for model in (dto.ReviewSessionOut, dto.SessionHorizonOut, dto.VerdictCountOut,
                      dto.ReviewSessionPage, dto.ExecutionOutcomeOut, dto.ExecutionPage):
            for name in model.model_fields:
                with self.subTest(model=model.__name__, field=name):
                    self.assertFalse(
                        any(word in name.lower() for word in self.FORBIDDEN), name
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
