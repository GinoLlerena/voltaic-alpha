"""The arm and disarm scripts, run against a stand-in for the cloud CLI.

Readiness review PER-R-2 (7 October 2026). These scripts are the one action
that lets an unattended process open Paper risk, and they predated two rules
every other operator script follows: the cloud CLI's stderr is never shown,
because it echoes the AccessKey ID on a failure, and a worker restart waits for
the trading day to end.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BASH = shutil.which("bash") or "bash"
#: What the stand-in CLI prints to stderr; it must never reach the operator.
LEAK = "AccessKeyId=LTAI-EXAMPLE-NOT-A-KEY"  # pragma: allowlist secret
MIDDAY = "2026-10-07T13:00:00-04:00"   # Wednesday, inside the trading day
EVENING = "2026-10-07T17:15:00-04:00"  # the first minute arming is allowed
SATURDAY = "2026-10-10T13:00:00-04:00"


class ArmScriptCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self._tmp.name)
        self.calls = self.bin / "calls"
        fake = self.bin / "aliyun"
        # Records each call, leaks on stderr, and fails: the worst case.
        fake.write_text(
            f'#!/bin/bash\necho "$*" >> "{self.calls}"\necho "{LEAK}" >&2\nexit 1\n'
        )
        fake.chmod(0o755)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_script(self, name: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - fixed argv, the script under test
            [BASH, str(SCRIPTS / name)], capture_output=True, text=True, check=False,
            env={**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", **env},
        )

    def called(self) -> bool:
        return self.calls.exists()


class Arming(ArmScriptCase):
    def test_arming_is_refused_during_the_trading_day_before_any_cloud_call(self) -> None:
        done = self.run_script("arm_worker.sh", ARM_AT=MIDDAY)
        self.assertEqual(done.returncode, 2)
        self.assertIn("REFUSING to arm: Wed 13:00 ET is inside the trading day", done.stderr)
        self.assertIn("17:15 ET", done.stderr)
        self.assertFalse(self.called(), "nothing may be sent to the host")

    def test_arming_is_allowed_from_1715_eastern_and_at_the_weekend(self) -> None:
        for at in (EVENING, SATURDAY):
            with self.subTest(at):
                self.calls.unlink(missing_ok=True)
                done = self.run_script("arm_worker.sh", ARM_AT=at)
                self.assertNotIn("REFUSING", done.stderr)
                self.assertTrue(self.called())

    def test_the_window_can_be_overridden_explicitly(self) -> None:
        self.run_script("arm_worker.sh", ARM_AT=MIDDAY, ARM_IGNORE_WINDOW="1")
        self.assertTrue(self.called())

    def test_a_failing_cli_stops_the_script_and_never_shows_its_stderr(self) -> None:
        done = self.run_script("arm_worker.sh", ARM_AT=EVENING)
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn(LEAK, done.stdout + done.stderr)
        self.assertIn("aliyun ecs RunCommand failed", done.stderr)
        self.assertNotIn("Armed.", done.stdout)


class Disarming(ArmScriptCase):
    def test_disarming_is_never_refused_by_the_clock(self) -> None:
        # Removing write authority must be possible at any moment.
        done = self.run_script("disarm_worker.sh", ARM_AT=MIDDAY)
        self.assertNotIn("REFUSING", done.stderr)
        self.assertTrue(self.called())

    def test_a_failing_cli_never_shows_its_stderr(self) -> None:
        done = self.run_script("disarm_worker.sh")
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn(LEAK, done.stdout + done.stderr)
        self.assertNotIn("Disarmed.", done.stdout)

    def test_it_says_the_mode_the_base_unit_really_runs(self) -> None:
        text = (SCRIPTS / "disarm_worker.sh").read_text(encoding="utf-8")
        self.assertIn('\\"mode\\": \\"observe\\"', text)
        self.assertNotIn("recommend", text)


class EveryOperatorShellScript(unittest.TestCase):
    def test_no_shell_script_lets_the_cloud_clis_stderr_through(self) -> None:
        for path in sorted(SCRIPTS.glob("*.sh")):
            text = path.read_text(encoding="utf-8")
            if "aliyun " not in text:
                continue
            with self.subTest(path.name):
                self.assertIn('command aliyun "$@" 2>/dev/null', text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
