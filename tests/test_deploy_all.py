"""`deploy_all.py` decides which existing deploy steps a set of differences needs.

It holds no deploy logic of its own, so what is tested is the decision: which
flags `ship_host.py` gets, when the worker restarts, when a session lock is
needed, and what is refused during the trading day. Nothing here reaches a host.
"""

from __future__ import annotations

import sys
import unittest
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
        self.assertIn("after 17:15 ET", blocked.blocked or "")
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


class NeedsSession(unittest.TestCase):
    def status(self, instance: str, inside: bool, lock: str) -> dict[str, object]:
        return {"instance": instance, "inside_market_run_window": inside, "lock": lock}

    def test_a_stopped_server_needs_one(self) -> None:
        self.assertTrue(da.needs_session(self.status("Stopped", False, "expired")))

    def test_a_server_running_in_market_hours_does_not(self) -> None:
        self.assertFalse(da.needs_session(self.status("Running", True, "expired")))

    def test_running_after_hours_without_a_lock_needs_one(self) -> None:
        # The scheduler stops such a server on its next tick, mid-deploy.
        self.assertTrue(da.needs_session(self.status("Running", False, "expired")))
        self.assertFalse(da.needs_session(self.status("Running", False, "active")))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
