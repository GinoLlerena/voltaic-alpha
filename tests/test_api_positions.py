"""The positions read model (PUI Phase 4, step 1).

`docs/improvements/options_alpha_pui_phase4_read_models_v0_1.md`, approved 6
October 2026. Its release gate asks for every lifecycle state, a missing mark, a
stale mark, and a realised result that exists only for a completed round trip.
The live source has never held a position, so each state is built here with the
lifecycle store itself: the same calls the worker makes, never an invented row.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import ExecutionState
from options_alpha_lab.calendar import committed_calendar
from options_alpha_lab.execution.lifecycle import OrderState
from options_alpha_lab.persistence.models import Position
from options_alpha_lab.presentation import positions
from positions_support import AFTER_CLOSE, MONDAY_OPEN, PositionsCase
from reconcile_support import NOW


class EveryState(PositionsCase):
    def test_pending_is_unconfirmed_exposure_with_no_entry_price(self) -> None:
        p = self.summary(self.pending())
        self.assertEqual((p["state"], p["open"]), ("PENDING", True))
        self.assertIn("unknown, not zero", p["state_meaning"])
        self.assertIsNone(p["entry_debit"], "never the estimated debit")
        self.assertEqual((p["requested_quantity"], p["filled_quantity"]), (1, 0))
        self.assertEqual(p["open_risk"], "339.000000")
        self.assertEqual(p["mark_state"], "never_observed")
        self.assertIsNone(p["unrealized"])
        self.assertIsNone(p["realized"])

    def test_open_carries_reconciled_fills_and_its_typed_invalidation(self) -> None:
        position_id, _ = self.opened()
        p = self.summary(position_id)
        self.assertEqual((p["state"], p["open"], p["filled_quantity"]), ("OPEN", True, 1))
        self.assertEqual(p["entry_debit"], "3.130000")
        self.assertEqual(p["instrument"], "SPY")
        self.assertEqual(p["invalidation_level"], "631.630000")
        self.assertIsNotNone(p["decision_id"])
        self.assertIsNone(p["realized"], "an open position has no result")

    def test_closing_is_still_open_until_the_broker_confirms_flat(self) -> None:
        position_id, intent = self.opened()
        self.closing(position_id, intent)
        p = self.summary(position_id)
        self.assertEqual((p["state"], p["open"]), ("CLOSING", True))
        self.assertIn("not confirmed flat", p["state_meaning"])
        self.assertIsNone(p["realized"], "a half round trip has no result")

    def test_closed_has_a_result_computed_from_the_fills(self) -> None:
        p = self.summary(self.closed())
        self.assertEqual((p["state"], p["open"]), ("CLOSED", False))
        # (2.80 - 3.13) x 100 x 1, from broker_orders.filled_avg_price.
        self.assertEqual(Decimal(p["realized"]), Decimal("-33.00"))
        self.assertEqual(p["close_reason"], "stop_loss")
        self.assertIsNotNone(p["closed_at"])

    def test_abandoned_never_had_exposure_and_has_no_result(self) -> None:
        position_id = self.pending()
        self.store.apply_entry_outcome(position_id, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        p = self.summary(position_id)
        self.assertEqual((p["state"], p["open"]), ("ABANDONED", False))
        self.assertIn("never exposure", p["state_meaning"])
        self.assertIsNone(p["entry_debit"])
        self.assertIsNone(p["realized"], "not a zero result")

    def test_an_incident_marks_exposure_unknown_and_is_listed_redacted(self) -> None:
        position_id, _ = self.opened()
        self.store.open_incident(
            kind="position_mismatch", detail="broker says 2, local says 1",
            execution_state=ExecutionState.NO_NEW_RISK, position_id=position_id, now=NOW,
        )
        detail = self.get(position_id)
        p = detail["position"]
        self.assertEqual((p["state"], p["open"], p["open_incidents"]), ("INCIDENT", True, 1))
        self.assertEqual(detail["incidents"][0]["kind"], "position_mismatch")
        self.assertEqual(detail["incidents"][0]["withheld"], ["detail"])
        self.assertNotIn("broker says", str(detail))


class Marks(PositionsCase):
    def test_a_recent_mark_in_an_open_session_is_current(self) -> None:
        position_id, _ = self.opened()
        observation = self.mark(position_id, NOW - timedelta(minutes=1))
        self.hold(position_id, observation, "27.00")
        p = self.summary(position_id)
        self.assertEqual(p["mark_state"], "current")
        self.assertEqual(p["latest_mark"]["spread_value"], "3.400000")
        self.assertEqual(p["latest_mark"]["underlying_source"], "completed_daily_close")
        self.assertEqual(Decimal(p["unrealized"]), Decimal("27.00"))

    def test_the_boundary_is_five_minutes(self) -> None:
        position_id, _ = self.opened()
        self.mark(position_id, NOW - positions.STALE_AFTER)
        self.assertEqual(self.summary(position_id)["mark_state"], "current")
        self.assertEqual(
            self.summary(position_id, NOW + timedelta(seconds=1))["mark_state"], "stale"
        )

    def test_an_unreadable_mark_is_a_recorded_fact_not_a_zero(self) -> None:
        position_id, _ = self.opened()
        observation = self.mark(position_id, NOW - timedelta(minutes=1), value=None)
        self.hold(position_id, observation, None)
        p = self.summary(position_id)
        self.assertEqual(p["mark_state"], "unreadable")
        self.assertIsNone(p["latest_mark"]["spread_value"])
        self.assertEqual(p["latest_mark"]["data_quality"], ["long_leg_no_bid"])
        self.assertIsNone(p["unrealized"])

    def test_after_the_close_the_days_last_mark_is_last_session_not_stale(self) -> None:
        position_id, _ = self.opened()
        self.mark(position_id, NOW)
        self.assertEqual(self.summary(position_id, AFTER_CLOSE)["mark_state"], "last_session")

    def test_a_mark_from_an_earlier_session_is_stale_once_the_market_reopens(self) -> None:
        position_id, _ = self.opened()
        self.mark(position_id, NOW)
        calendar, _ = committed_calendar()
        session = calendar.session_for(MONDAY_OPEN)
        assert session is not None and session.open_at <= MONDAY_OPEN < session.close_at
        self.assertEqual(self.summary(position_id, MONDAY_OPEN)["mark_state"], "stale")

    def test_a_closed_positions_last_mark_is_final_however_old(self) -> None:
        position_id = self.closed()
        self.mark(position_id, NOW - timedelta(hours=1))
        self.assertEqual(self.summary(position_id, MONDAY_OPEN)["mark_state"], "final")

    def test_the_newest_mark_wins_and_all_are_paged_newest_first(self) -> None:
        position_id, _ = self.opened()
        for minutes in (30, 20, 10):
            self.mark(position_id, NOW - timedelta(minutes=minutes), value=f"3.{minutes}")
        self.assertEqual(self.summary(position_id)["latest_mark"]["spread_value"], "3.100000")
        client = self.client()
        seen: list[str] = []
        cursor = None
        while True:
            url = f"/api/v1/positions/{position_id}/observations?limit=2"
            page = client.get(url + (f"&cursor={cursor}" if cursor else "")).json()["data"]
            seen += [m["spread_value"] for m in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(seen, ["3.100000", "3.200000", "3.300000"])
        self.assertEqual(page["total"], 3)
        self.assertEqual(self.get(position_id)["observations_recorded"], 3)


class ListAndBoundary(PositionsCase):
    def build_book(self) -> dict[str, str]:
        book = {"PENDING": self.pending(), "OPEN": self.opened()[0], "CLOSED": self.closed()}
        abandoned = self.pending()
        self.store.apply_entry_outcome(abandoned, state=OrderState.CANCELED,
                                       filled_quantity=0, avg_debit=None, now=NOW)
        book["ABANDONED"] = abandoned
        return book

    def test_open_and_closed_partition_every_position(self) -> None:
        book = self.build_book()
        client = self.client()

        def ids(state: str) -> set[str]:
            data = client.get(f"/api/v1/positions?state={state}").json()["data"]
            self.assertEqual(data["total"], len(data["items"]))
            self.assertEqual(data["ever"], len(book))
            return {p["position_id"] for p in data["items"]}

        self.assertEqual(ids("open"), {book["PENDING"], book["OPEN"]})
        self.assertEqual(ids("closed"), {book["CLOSED"], book["ABANDONED"]})
        self.assertEqual(ids("all"), set(book.values()))

    def test_the_list_pages_on_the_servers_cursor_without_loss_or_repeat(self) -> None:
        book = self.build_book()
        client = self.client()
        seen: list[str] = []
        cursor = None
        while True:
            url = "/api/v1/positions?limit=1" + (f"&cursor={cursor}" if cursor else "")
            page = client.get(url).json()["data"]
            seen += [p["position_id"] for p in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(sorted(seen), sorted(book.values()))
        self.assertEqual(len(seen), len(set(seen)))

    def test_a_source_that_never_held_a_position_says_ever_zero(self) -> None:
        data = self.client().get("/api/v1/positions").json()["data"]
        self.assertEqual((data["items"], data["total"], data["ever"]), ([], 0, 0))

    def test_unknown_and_malformed_requests(self) -> None:
        client = self.client()
        self.assertEqual(client.get("/api/v1/positions/nosuchposition").status_code, 404)
        self.assertEqual(
            client.get("/api/v1/positions/nosuchposition/observations").status_code, 404
        )
        self.assertEqual(client.get("/api/v1/positions?state=flat").status_code, 422)
        self.assertEqual(client.get("/api/v1/positions?cursor=%%%").status_code, 400)
        for method in ("post", "put", "patch", "delete"):
            self.assertEqual(getattr(client, method)("/api/v1/positions").status_code, 405)

    def test_no_number_crosses_as_a_float_and_units_are_in_the_contract(self) -> None:
        position_id, _ = self.opened()
        self.hold(position_id, self.mark(position_id, NOW), "27.00")
        body = self.client().get(f"/api/v1/positions/{position_id}").json()

        def floats(node: Any) -> list[float]:
            if isinstance(node, float):
                return [node]
            if isinstance(node, dict):
                return [f for v in node.values() for f in floats(v)]
            if isinstance(node, list):
                return [f for v in node for f in floats(v)]
            return []

        self.assertEqual(floats(body), [])
        schema = self.client().get("/openapi.json").json()["components"]["schemas"]
        fields = schema["PositionSummaryOut"]["properties"]
        self.assertIn("per share", fields["entry_debit"]["description"])
        self.assertIn("whole structure", fields["open_risk"]["description"])
        self.assertIn("reconciled broker fills", fields["realized"]["description"])

    def test_the_list_costs_the_same_statements_however_many_positions(self) -> None:
        from sqlalchemy import event

        self.build_book()
        client = self.client()
        counted = [0]

        def count(*_: object) -> None:
            counted[0] += 1

        event.listen(self.engine, "before_cursor_execute", count)
        try:
            client.get("/api/v1/positions?state=open")
            two = counted[0]
            for _ in range(4):
                self.opened()
            counted[0] = 0
            client.get("/api/v1/positions?state=open")
            six = counted[0]
        finally:
            event.remove(self.engine, "before_cursor_execute", count)
        self.assertEqual(six, two, "open positions must not cost a query each")

    def test_every_state_has_a_served_meaning(self) -> None:
        from options_alpha_lab.execution.lifecycle import PositionState

        self.assertEqual(set(positions.STATE_MEANING), {s.value for s in PositionState})
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(Position)).all(), [])
