"""`ship_host.py` is the one host deployment path (deploy-hygiene follow-ups).

The failure it replaces: `deploy_worker.sh` shipped five paths, so the host ran
revision 0007 with 0008's file absent and drifted from the release freeze in a
dozen files. These tests pin what is compared, what is shipped, and what is
refused, without touching a host.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tarfile
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
        rows = sh.manifest(self.plan()).splitlines()
        self.assertIn(
            "755 scripts/backup_database.sh /opt/options-alpha/scripts/backup_database.sh", rows
        )
        self.assertIn("644 src/a.py /opt/options-alpha/src/a.py", rows)
        self.assertIn(
            "644 deploy/systemd/apt-daily.timer.d/options-alpha.conf "
            "/etc/systemd/system/apt-daily.timer.d/options-alpha.conf", rows,
        )
        self.assertIn("systemctl restart apt-daily.timer", self.script())

    def test_the_command_stays_small_however_many_files_ship(self) -> None:
        # Cloud Assistant refuses commands over about 18 KB (CmdContent.ExceedLimit,
        # hit on 1 Oct with 41 files written out one by one).
        many = sh.Plan(changed=[f"fixtures/f{i:04}.json" for i in range(2000)])
        self.assertLess(len(sh.install("/root/t.tgz", "S", many, [])), 2000)

    def test_a_path_with_whitespace_is_refused(self) -> None:
        with self.assertRaises(sh.rt.Stop):
            sh.manifest(sh.Plan(changed=["docs/a file.md"]))

    def test_the_manifest_travels_inside_the_tarball(self) -> None:
        plan = sh.Plan(changed=["pyproject.toml"])
        data = sh.tarball(plan.changed, sh.manifest(plan))
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            names = tar.getnames()
            body = tar.extractfile(sh.MANIFEST).read().decode()  # type: ignore[union-attr]
        self.assertEqual(names, [sh.MANIFEST, "pyproject.toml"])
        self.assertEqual(body, "644 pyproject.toml /opt/options-alpha/pyproject.toml\n")

    def test_junk_is_removed_only_when_asked_and_the_worker_is_never_implied(self) -> None:
        self.assertNotIn("._x.json", self.script())
        self.assertIn("rm -f /opt/options-alpha/artifacts/._x.json", self.script(prune_junk=True))
        self.assertNotIn("options-alpha-worker", self.script())


class PinCheck(unittest.TestCase):
    def off(self, requirements: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text(requirements)
            done = subprocess.run(  # noqa: S603 - fixed argv, the script is ours
                [sys.executable, "-", str(req)], input=sh.PIN_CHECK_PY,
                capture_output=True, text=True, check=True,
            )
        return done.stdout.strip()

    def test_pins_for_another_platform_or_python_do_not_apply(self) -> None:
        # The three false alarms of 1 Oct 2026.
        reqs = (
            "httpx2-jsfetch==1.0 ; sys_platform == 'emscripten'\n"
            "tzdata==2026.3 ; sys_platform == 'emscripten' or sys_platform == 'win32'\n"
            "numpy==2.4.6 ; python_full_version < '3.0'\n"
        )
        self.assertEqual(self.off(reqs), "pins_off=none")

    def test_a_pin_that_applies_is_still_checked(self) -> None:
        self.assertEqual(
            self.off("not-installed-pkg==1.0 ; python_full_version >= '3.0'\n"),
            "pins_off=not-installed-pkg absent (pinned 1.0)",
        )


class EditableInstall(unittest.TestCase):
    """The services must run the checkout this tool writes to, not a copy.

    5 Oct 2026: `--install-deps` ran `pip install -r requirements.txt`. Its last
    line, `.`, installed the project as a copy in site-packages, replacing the
    editable install. Shipped source stopped taking effect, and the worker could
    not start (it finds alembic.ini relative to its own file). Nothing noticed
    until the next start, a day later.
    """

    SITE = "/opt/options-alpha/.venv/lib/python3.12/site-packages/options_alpha_lab"

    def test_installing_dependencies_never_installs_the_project_as_a_copy(self) -> None:
        self.assertIn("grep -vxF . requirements.txt", sh.DEPS)
        self.assertNotIn("-r requirements.txt", sh.DEPS)

    def test_the_dependency_filter_drops_only_the_project_line(self) -> None:
        done = subprocess.run(  # noqa: S603 - fixed argv
            [shutil.which("grep") or "grep", "-vxF", ".", str(ROOT / "requirements.txt")],
            capture_output=True, text=True, check=True,
        )
        kept = [line for line in done.stdout.splitlines() if not line.startswith("#")]
        self.assertNotIn(".", kept)
        self.assertTrue(all("==" in line for line in kept), kept[:3])
        self.assertIn(".", (ROOT / "requirements.txt").read_text().splitlines())

    def test_the_project_is_linked_not_copied(self) -> None:
        self.assertIn("pip install -q --no-deps -e .", sh.EDITABLE)

    def test_a_plan_knows_whether_the_host_runs_the_checkout(self) -> None:
        self.assertTrue(sh.Plan().editable)
        self.assertTrue(sh.Plan(package="/opt/options-alpha/src/options_alpha_lab").editable)
        self.assertFalse(sh.Plan(package=self.SITE).editable)
        self.assertFalse(sh.Plan(package="").editable, "an unimportable package is not fine")

    def test_verification_fails_on_a_copy_or_a_worker_that_does_not_stay_up(self) -> None:
        self.assertIn('if [ "$package" != "/opt/options-alpha/src/options_alpha_lab" ]', sh.VERIFY)
        self.assertIn('if [ "$steady" != yes ]', sh.VERIFY)
        self.assertEqual(sh.VERIFY.count("exit 1"), 2)

    def test_the_scripts_parse(self) -> None:
        for script in (sh.DEPS, sh.EDITABLE, sh.VERIFY, sh.DIGESTS, sh.restart_script(["a", "b"])):
            done = subprocess.run(  # noqa: S603 - fixed argv, the script is ours
                [BASH, "-n"], input=script, capture_output=True, text=True, check=False
            )
            self.assertEqual(done.returncode, 0, done.stderr)


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
