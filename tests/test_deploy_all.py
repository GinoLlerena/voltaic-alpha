"""`deploy_all.py` decides which existing deploy steps a set of differences needs.

It holds no deploy logic of its own, so what is tested is the decision: which
flags `ship_host.py` gets, when the worker restarts, when a session lock is
needed, and what is refused during the trading day. Nothing here reaches a host.
"""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy_all as da  # noqa: E402
import ship_host as sh  # noqa: E402

DAY = "Mon 13:00 ET is inside the trading day plus the post-close backup"
RESTARTS = ["--restart", "options-alpha-api", "--restart", "options-alpha"]


class StepsFor(unittest.TestCase):
    def test_a_matching_host_ships_nothing(self) -> None:
        steps = da.steps_for(sh.Plan(), DAY)
        self.assertEqual((steps.ship, steps.worker, steps.blocked), ([], False, None))

    def test_read_only_source_restarts_the_api_and_dashboard_but_not_the_worker(self) -> None:
        plan = sh.Plan(changed=[
            "src/options_alpha_lab/api/server.py", "src/options_alpha_lab/presentation/decision.py",
        ])
        steps = da.steps_for(plan, DAY)
        self.assertEqual(steps.ship, ["--apply", *RESTARTS])
        self.assertFalse(steps.worker)
        self.assertIsNone(steps.blocked, "no worker restart, so the trading day does not block it")

    def test_worker_source_restarts_the_worker_and_waits_for_the_close(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/agent.py"])
        blocked = da.steps_for(plan, DAY)
        self.assertEqual(blocked.ship, ["--apply", "--restart-worker", *RESTARTS])
        self.assertIn("RUN IT AT OR AFTER 17:15 ET", blocked.blocked or "")
        self.assertIsNone(da.steps_for(plan, None).blocked)

    def test_changed_requirements_install_and_restart_everything(self) -> None:
        plan = sh.Plan(changed=["requirements.txt"])
        steps = da.steps_for(plan, None)
        self.assertEqual(steps.ship, ["--apply", "--install-deps", "--restart-worker", *RESTARTS])

    def test_a_schema_behind_migrates_instead_of_restarting_the_worker(self) -> None:
        plan = sh.Plan(changed=["migrations/versions/0009_x.py"],
                       host_revision="0008", repo_head="0009")
        steps = da.steps_for(plan, None)
        self.assertIn("--migrate", steps.ship)
        self.assertNotIn("--restart-worker", steps.ship)
        self.assertTrue(steps.worker)

    def test_scripts_and_docs_restart_nothing(self) -> None:
        steps = da.steps_for(sh.Plan(changed=["scripts/session.py", "README.md"]), DAY)
        self.assertEqual(steps.ship, ["--apply"])

    def test_ignoring_the_window_is_explicit_and_passed_through(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/worker.py"])
        steps = da.steps_for(plan, DAY, ignore_window=True)
        self.assertIsNone(steps.blocked)
        self.assertIn("--ignore-window", steps.ship)


class SessionAction(unittest.TestCase):
    NOW = datetime(2026, 10, 5, 21, 20, tzinfo=UTC)  # 17:20 ET, a Monday

    def status(
        self, instance: str, lock: str, minutes_left: int | None = None
    ) -> dict[str, object]:
        until = None if minutes_left is None else self.NOW + timedelta(minutes=minutes_left)
        return {
            "instance": instance, "lock": lock, "inside_market_run_window": True,
            "lock_until": until.isoformat() if until else None,
        }

    def test_a_stopped_server_gets_a_session(self) -> None:
        self.assertEqual(da.session_action(self.status("Stopped", "expired"), self.NOW), "open")

    def test_a_running_server_with_no_lock_gets_one_even_in_market_hours(self) -> None:
        # 17:15 ET clears the trading-day refusal, and the run window closes at
        # 17:30: without a lock the scheduler would stop the server mid-deploy.
        self.assertEqual(da.session_action(self.status("Running", "expired"), self.NOW), "open")

    def test_the_owners_long_lock_is_left_alone(self) -> None:
        self.assertIsNone(da.session_action(self.status("Running", "active", 120), self.NOW))

    def test_the_owners_lock_about_to_expire_is_extended_not_replaced(self) -> None:
        soon = self.status("Running", "active", 10)
        self.assertEqual(da.session_action(soon, self.NOW), "extend")


class WhenToRun(unittest.TestCase):
    def test_during_the_trading_day_the_time_is_stated_in_new_york_and_local_time(self) -> None:
        midday = datetime(2026, 10, 5, 19, 6, tzinfo=UTC)  # Mon 15:06 ET
        clear = da.clear_from(midday)
        assert clear is not None
        self.assertEqual((clear.hour, clear.minute), (17, 15))
        self.assertEqual(str(clear.tzinfo), "America/New_York")
        text = da.when(clear)
        self.assertIn("17:15 ET today", text)
        self.assertIn(f"{clear.astimezone():%H:%M} on this computer's clock", text)

    def test_nothing_is_refused_in_the_evening_or_at_the_weekend(self) -> None:
        self.assertIsNone(da.clear_from(datetime(2026, 10, 5, 21, 20, tzinfo=UTC)))  # Mon 17:20 ET
        self.assertIsNone(da.clear_from(datetime(2026, 10, 3, 15, 0, tzinfo=UTC)))   # Saturday

    def test_the_refusal_says_when(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/agent.py"])
        after = "17:15 ET today (16:15 on this computer's clock, -05)"
        steps = da.steps_for(plan, DAY, after=after)
        self.assertIn("RUN IT AT OR AFTER 17:15 ET today (16:15", steps.blocked or "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
