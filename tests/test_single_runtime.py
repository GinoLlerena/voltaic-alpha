"""One continuous runtime, and a package that does not open with its history.

`CSA-001`: `python -m options_alpha_lab.agent --ticks 0` used to loop forever
on its own scheduler, without the worker's lease, heartbeat, or the order,
position and review clocks the worker runs between ticks. The agent command
now runs one-shot cycles only, and the worker is the only continuous runner.

`CSA-003`: importing the package used to import the original hackathon
experiment (`run_experiment`). It is still there, imported by name.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path

from options_alpha_lab import agent

ROOT = Path(__file__).resolve().parents[1]


class AgentCommand(unittest.TestCase):
    def refused(self, *argv: str) -> str:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(agent.main(list(argv)), 2)
        return err.getvalue()

    def test_the_agent_refuses_to_run_continuously_and_names_the_worker(self) -> None:
        # Refused before any settings, database or client is touched.
        message = self.refused("--ticks", "0")
        self.assertIn("options_alpha_lab.worker", message)
        self.assertIn("one-shot", message)

    def test_a_negative_count_is_refused_the_same_way(self) -> None:
        self.assertIn("options_alpha_lab.worker", self.refused("--ticks", "-1"))

    def test_the_agent_has_no_scheduler_of_its_own(self) -> None:
        self.assertFalse(hasattr(agent.TradingAgent, "run"))
        source = (ROOT / "src" / "options_alpha_lab" / "agent.py").read_text(encoding="utf-8")
        self.assertNotIn("apscheduler", source)
        self.assertNotIn("apscheduler", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class PackageFrontDoor(unittest.TestCase):
    def test_importing_the_package_does_not_import_the_experiment(self) -> None:
        code = (
            "import sys, options_alpha_lab as p; "
            "legacy = [m for m in ('orchestrator', 'agents', 'models', 'risk') "
            "if 'options_alpha_lab.' + m in sys.modules]; "
            "print(legacy, hasattr(p, 'run_experiment'))"
        )
        done = subprocess.run(  # noqa: S603 - fixed argv, no user input
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        self.assertEqual(done.stdout.strip(), "[] False")

    def test_the_experiment_is_still_importable_by_name(self) -> None:
        from options_alpha_lab.orchestrator import run_experiment

        self.assertTrue(callable(run_experiment))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
