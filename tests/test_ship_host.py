"""`ship_host.py` is the one host deployment path (deploy-hygiene follow-ups).

The failure it replaces: `deploy_worker.sh` shipped five paths, so the host ran
revision 0007 with 0008's file absent and drifted from the release freeze in a
dozen files. These tests pin what is compared, what is shipped, and what is
refused, without touching a host.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ship_host as sh  # noqa: E402

BASH = shutil.which("bash") or "bash"


class Compare(unittest.TestCase):
    def test_each_difference_lands_in_its_own_bucket(self) -> None:
        local = {
            "src/a.py": "1", "scripts/x.sh": "2", "migrations/versions/0009.py": "3",
            "deploy/systemd/u.service": "4", "unit:deploy/systemd/u.service": "4",
        }
        host = {
            "src/a.py": "1",                      # same
            "scripts/x.sh": "old",                # differs
            "deploy/systemd/u.service": "4",      # checkout copy same
            "unit:deploy/systemd/u.service": "x", # installed copy differs
            "artifacts/._junk.json": "j",         # macOS junk
            "artifacts/local-notes.txt": "n",     # host-only, not junk
        }
        plan = sh.compare(local, host)
        self.assertEqual(plan.changed, ["migrations/versions/0009.py", "scripts/x.sh"])
        self.assertEqual(plan.units, ["deploy/systemd/u.service"])
        self.assertEqual(plan.junk, ["artifacts/._junk.json"])
        self.assertEqual(plan.host_only, ["artifacts/local-notes.txt"])

    def test_a_requirements_change_is_flagged(self) -> None:
        plan = sh.compare({"requirements.txt": "new"}, {"requirements.txt": "old"})
        self.assertTrue(plan.deps_changed)


class HostPaths(unittest.TestCase):
    def test_what_the_old_deploy_left_out_is_now_shipped(self) -> None:
        for path in ("migrations", "scripts", "alembic.ini"):
            self.assertIn(path, sh.HOST_PATHS)
        for repo_only in ("frontend", "tests", "docs", ".github", "Dockerfile", "uv.lock"):
            self.assertNotIn(repo_only, sh.HOST_PATHS)

    def test_units_and_drop_ins_are_installed_but_their_readme_is_not(self) -> None:
        self.assertTrue(sh.is_unit("deploy/systemd/options-alpha-api.service"))
        self.assertTrue(sh.is_unit("deploy/systemd/apt-daily.timer.d/options-alpha.conf"))
        self.assertFalse(sh.is_unit("deploy/systemd/README.md"))
        self.assertFalse(sh.is_unit("deploy/install_units.sh"))
        self.assertIn("migrations/env.py", sh.local_files())


class MigrationHead(unittest.TestCase):
    def write(self, root: Path, name: str, rev: str, down: str | None) -> None:
        versions = root / "migrations" / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        down_line = f'down_revision = "{down}"' if down else "down_revision = None"
        (versions / name).write_text(f'revision = "{rev}"\n{down_line}\n')

    def test_the_repository_head_is_the_latest_revision(self) -> None:
        self.assertEqual(sh.repo_head(), "0008_evaluation_runs")

    def test_a_linear_chain_has_one_head_and_a_fork_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, "a.py", "0001", None)
            self.write(root, "b.py", "0002", "0001")
            self.assertEqual(sh.repo_head(root), "0002")
            self.write(root, "c.py", "0003", "0001")
            with self.assertRaisesRegex(sh.rt.Stop, "one migration head"):
                sh.repo_head(root)

    def test_code_ahead_of_its_schema_needs_a_migration(self) -> None:
        plan = sh.Plan(host_revision="0007_strategy_catalog", repo_head="0008_evaluation_runs")
        self.assertTrue(plan.needs_migration)
        self.assertFalse(sh.Plan(host_revision="x", repo_head="x").needs_migration)


class InstallScript(unittest.TestCase):
    def plan(self) -> sh.Plan:
        return sh.Plan(
            changed=["scripts/backup_database.sh", "src/a.py"],
            units=["deploy/systemd/apt-daily.timer.d/options-alpha.conf"],
            junk=["artifacts/._x.json"],
        )

    def script(self, **kw: object) -> str:
        return sh.install("/root/staged.tgz", "20261001T000000Z", self.plan(), [], **kw)  # type: ignore[arg-type]

    def test_it_parses(self) -> None:
        done = subprocess.run(  # noqa: S603 - fixed argv, the script is ours
            [BASH, "-n"], input=self.script(), capture_output=True, text=True, check=False
        )
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_shell_scripts_stay_executable_and_units_restart_their_timer(self) -> None:
        s = self.script()
        self.assertIn('install -D -m 755 "$work"/scripts/backup_database.sh', s)
        self.assertIn('install -D -m 644 "$work"/src/a.py', s)
        self.assertIn("systemctl restart apt-daily.timer", s)

    def test_junk_is_removed_only_when_asked_and_the_worker_is_never_implied(self) -> None:
        self.assertNotIn("._x.json", self.script())
        self.assertIn("rm -f /opt/options-alpha/artifacts/._x.json", self.script(prune_junk=True))
        self.assertNotIn("options-alpha-worker", self.script())


class Refusals(unittest.TestCase):
    def run_main(self, *argv: str, window: str | None = None) -> int:
        with (
            mock.patch.object(sys, "argv", ["ship_host.py", *argv]),
            mock.patch.object(sh.dr, "market_window_reason", lambda _now: window),
            mock.patch.object(sh, "make_plan", side_effect=AssertionError("reached the host")),
        ):
            return sh.main()

    def test_the_worker_needs_its_own_flag(self) -> None:
        self.assertEqual(self.run_main("--apply", "--restart", "options-alpha-worker"), 2)

    def test_worker_restart_and_migration_are_refused_during_the_trading_day(self) -> None:
        for flag in ("--restart-worker", "--migrate"):
            with self.subTest(flag):
                self.assertEqual(self.run_main("--apply", flag, window="Thu 10:00 ET"), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
