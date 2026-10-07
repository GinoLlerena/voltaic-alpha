"""`deploy_all.py` decides which existing deploy steps a set of differences needs.

It holds no deploy logic of its own, so what is tested is the decision: which
flags `ship_host.py` gets, when the worker restarts, when a session lock is
needed, and what is refused during the trading day. Nothing here reaches a host.
"""

from __future__ import annotations

import sys
import tempfile
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

    def test_api_only_source_restarts_the_api_alone_and_may_ship_in_the_day(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/api/server.py"])
        steps = da.steps_for(plan, DAY)
        self.assertEqual(steps.ship, ["--apply", "--restart", "options-alpha-api"])
        self.assertFalse(steps.worker)
        self.assertIsNone(steps.blocked, "no worker restart, so the trading day does not block it")

    def test_a_file_the_worker_loads_restarts_the_worker_and_waits_for_the_close(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/agent.py"])
        blocked = da.steps_for(plan, DAY)
        self.assertEqual(blocked.ship, ["--apply", "--restart-worker"])
        self.assertIn("RUN IT AT OR AFTER 17:15 ET", blocked.blocked or "")
        self.assertIsNone(da.steps_for(plan, None).blocked)

    def test_a_file_every_service_loads_restarts_them_all(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/calendar.py"])
        self.assertEqual(
            da.steps_for(plan, None).ship, ["--apply", "--restart-worker", *RESTARTS]
        )

    def test_source_no_service_loads_restarts_nothing_and_ships_in_the_day(self) -> None:
        # 7 October 2026: the scheduler function's module was held until after
        # the close as "worker source". Nothing running on the host imports it.
        plan = sh.Plan(changed=[
            "src/options_alpha_lab/scheduler.py", "deploy/scheduler/handler.py",
            "scripts/arm_worker.sh",
        ])
        steps = da.steps_for(plan, DAY)
        self.assertEqual((steps.ship, steps.worker, steps.blocked), (["--apply"], False, None))

    def test_a_packaged_data_file_restarts_everything_because_imports_cannot_trace_it(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/data/nyse_sessions.json"])
        self.assertEqual(
            da.steps_for(plan, None).ship, ["--apply", "--restart-worker", *RESTARTS]
        )

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

    def test_a_host_running_a_copy_of_the_package_is_relinked_and_everything_restarts(self) -> None:
        # 5 Oct 2026: nothing differed on disk, yet no service ran the checkout.
        site = "/opt/options-alpha/.venv/lib/python3.12/site-packages"
        plan = sh.Plan(package=f"{site}/options_alpha_lab")
        steps = da.steps_for(plan, None)
        self.assertEqual(steps.ship, ["--apply", "--restart-worker", *RESTARTS])
        self.assertTrue(steps.worker)
        self.assertIn("RUN IT AT OR AFTER", da.steps_for(plan, DAY).blocked or "")

    def test_scripts_and_docs_restart_nothing(self) -> None:
        steps = da.steps_for(sh.Plan(changed=["scripts/session.py", "README.md"]), DAY)
        self.assertEqual(steps.ship, ["--apply"])

    def test_ignoring_the_window_is_explicit_and_passed_through(self) -> None:
        plan = sh.Plan(changed=["src/options_alpha_lab/worker.py"])
        steps = da.steps_for(plan, DAY, ignore_window=True)
        self.assertIsNone(steps.blocked)
        self.assertIn("--ignore-window", steps.ship)


class LoadedBy(unittest.TestCase):
    """What each service loads is read from its imports, so it cannot drift."""

    def loads(self, service: str) -> frozenset[str]:
        return da.loaded_by(da.ENTRY_POINTS[service])

    def test_the_worker_loads_the_agent_and_the_lifecycle_but_no_read_only_surface(self) -> None:
        worker = self.loads(da.WORKER)
        for path in ("worker.py", "agent.py", "outcomes.py", "execution/lifecycle.py",
                     "calendar.py", "__init__.py"):
            self.assertIn(f"src/options_alpha_lab/{path}", worker)
        for path in ("api/server.py", "presentation/review.py", "scheduler.py"):
            self.assertNotIn(f"src/options_alpha_lab/{path}", worker)

    def test_the_api_loads_its_read_models_and_nothing_that_can_trade(self) -> None:
        api = self.loads(da.API)
        for path in ("api/server.py", "api/dto.py", "presentation/positions.py",
                     "presentation/review.py"):
            self.assertIn(f"src/options_alpha_lab/{path}", api)
        # The same boundary `test_api` asserts against the running import graph.
        for path in ("agent.py", "worker.py", "config.py", "execution/gateway.py"):
            self.assertNotIn(f"src/options_alpha_lab/{path}", api)

    def test_an_import_inside_a_function_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "src" / "options_alpha_lab"
            (pkg / "sub").mkdir(parents=True)
            (pkg / "__init__.py").write_text("")
            (pkg / "sub" / "__init__.py").write_text("")
            (pkg / "entry.py").write_text("def run():\n    from .sub import late\n")
            (pkg / "sub" / "late.py").write_text("from .. import top\n")
            (pkg / "top.py").write_text("")
            (pkg / "unused.py").write_text("")
            got = da.loaded_by("src/options_alpha_lab/entry.py", root)
        names = {p.removeprefix("src/options_alpha_lab/") for p in got}
        self.assertEqual(names, {"entry.py", "sub/__init__.py", "sub/late.py", "top.py",
                                 "__init__.py"})


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
