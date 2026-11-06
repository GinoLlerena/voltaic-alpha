"""The React deploy tool: when it may run, what it changes, and that its host scripts parse.

It runs unattended, so the guards are the part worth pinning: a deploy inside the
trading day is refused, anything in the package beyond the two API modules
blocks the plan, and every script it would send to the host is valid bash.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deploy_react as dr  # noqa: E402

BASH = shutil.which("bash") or "bash"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class WindowTests(unittest.TestCase):
    def test_the_trading_day_is_refused(self) -> None:
        # Monday 28 Sep 2026, EDT (UTC-4): 10:00 ET and 17:12 ET, before the backup settles.
        for at in ("2026-09-28T14:00", "2026-09-28T21:12", "2026-09-29T12:30"):
            with self.subTest(at):
                self.assertIsNotNone(dr.market_window_reason(utc(at)))

    def test_after_the_post_close_backup_and_before_the_open_is_allowed(self) -> None:
        for at in ("2026-09-28T21:15", "2026-09-29T03:00", "2026-09-29T12:29"):
            with self.subTest(at):
                self.assertIsNone(dr.market_window_reason(utc(at)))

    def test_weekends_are_allowed(self) -> None:
        self.assertIsNone(dr.market_window_reason(utc("2026-09-27T16:00")))


class PlanTests(unittest.TestCase):
    def test_only_the_api_modules_are_payload(self) -> None:
        local = {dr.API_FILES[0]: "new", dr.API_FILES[1]: "new", "src/x.py": "same"}
        host = {dr.API_FILES[0]: "old", "src/x.py": "same"}
        self.assertEqual(dr.plan_differences(host, local), (sorted(dr.API_FILES), []))

    def test_any_other_difference_blocks(self) -> None:
        local = {"src/options_alpha_lab/worker.py": "new"}
        host = {"src/options_alpha_lab/worker.py": "old"}
        self.assertEqual(dr.plan_differences(host, local)[1], ["src/options_alpha_lab/worker.py"])


class ShipTests(unittest.TestCase):
    def test_chunks_reassemble_exactly(self) -> None:
        payload = bytes(range(256)) * 200
        self.assertEqual(base64.b64decode("".join(dr.chunks(payload, 1000))), payload)

    def test_a_chunk_fits_the_command_limit(self) -> None:
        # Cloud Assistant caps CommandContent near 18 KB after base64.
        script = f"umask 077; printf '%s' '{'A' * dr.CHUNK}' >> /root/react-deploy-x.tar.gz.b64"
        self.assertLess(len(base64.b64encode(("#!/bin/bash\n" + script).encode())), 18_000)


class CheckTests(unittest.TestCase):
    GOOD = {
        "api_status": "200", "ui_shell": "1", "deep_link": "200", "unknown_api": "404",
        "worker": "active", "api_unit": "active",
    }

    def test_a_healthy_host_passes(self) -> None:
        self.assertEqual(dr.check_failures(self.GOOD), [])

    def test_the_shell_on_an_api_path_fails(self) -> None:
        self.assertTrue(dr.check_failures({**self.GOOD, "unknown_api": "200"}))

    def test_a_stopped_streamlit_is_not_a_failure(self) -> None:
        self.assertNotIn("options-alpha)", dr.HOST_CHECKS)
        self.assertNotIn("8501", dr.HOST_CHECKS)

    def test_a_missing_shell_fails(self) -> None:
        self.assertTrue(dr.check_failures({**self.GOOD, "ui_shell": "0"}))

    def test_parse_checks(self) -> None:
        self.assertEqual(dr.parse_checks("a=1\nnoise\nb=x=y\n"), {"a": "1", "b": "x=y"})


class UnitTextTests(unittest.TestCase):
    def test_nothing_starts_streamlit_or_points_port_80_at_it(self) -> None:
        source = Path(dr.__file__).read_text()
        self.assertNotIn("systemctl start options-alpha\n", source)
        self.assertNotIn("8501", source)

    def test_the_api_dropin_serves_the_deployed_build(self) -> None:
        self.assertIn(f"PRESENTATION_UI_DIR={dr.HOST_DIST}", dr.API_DROPIN_TEXT)
        self.assertIn("PRESENTATION_API_HOST=0.0.0.0", dr.API_DROPIN_TEXT)

    def test_rollback_keeps_the_api_dropin(self) -> None:
        # It is what serves the build on port 80 (retirement plan, phase 2).
        self.assertNotIn(dr.API_DROPIN, dr.revert_api_script())


@unittest.skipUnless(shutil.which("bash"), "bash is required")
class RollbackRunTests(unittest.TestCase):
    """The revert script run for real against a scratch tree, systemctl stubbed."""

    def setUp(self) -> None:
        import tempfile
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / "frontend" / "dist").mkdir(parents=True)
        (self.root / "frontend" / "dist" / "index.html").write_text("live")
        for f in dr.API_FILES:
            (self.root / f).parent.mkdir(parents=True, exist_ok=True)
            (self.root / f).write_text("live")

    def backup(self, stamp: str, label: str, dist: bool = True) -> Path:
        b = self.root / ".deploy-backup" / stamp
        for f in dr.API_FILES:
            (b / f).parent.mkdir(parents=True, exist_ok=True)
            (b / f).write_text(label)
        if dist:
            (b / "dist").mkdir()
            (b / "dist" / "index.html").write_text(label)
        return b

    def revert(self) -> subprocess.CompletedProcess[str]:
        script = (dr.revert_api_script()
                  .replace(dr.RESTART_API + "systemctl is-active options-alpha-api", "")
                  .replace(dr.HOST_ROOT, str(self.root)))
        return subprocess.run(  # noqa: S603 - fixed argv, the script is ours
            [BASH, "-c", script], capture_output=True, text=True, check=False)

    def live(self) -> tuple[str, str]:
        return ((self.root / "frontend" / "dist" / "index.html").read_text(),
                (self.root / dr.API_FILES[0]).read_text())

    def test_restores_the_newest_then_the_one_before(self) -> None:
        older = self.backup("20261101T000000Z", "older")
        newer = self.backup("20261102T000000Z", "newer")
        self.assertEqual(self.revert().returncode, 0)
        self.assertEqual(self.live(), ("newer", "newer"))
        self.assertTrue((newer / "dist" / "index.html").exists(), "copied, not moved")
        self.assertEqual(self.revert().returncode, 0)
        self.assertEqual(self.live(), ("older", "older"))
        self.assertTrue((older / "restored").exists())
        self.assertNotEqual(self.revert().returncode, 0, "nothing left to restore")
        self.assertEqual(self.live(), ("older", "older"))

    def test_a_backup_without_a_build_is_refused_and_nothing_changes(self) -> None:
        self.backup("20261102T000000Z", "newer", dist=False)
        done = self.revert()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("refusing", done.stderr)
        self.assertEqual(self.live(), ("live", "live"))


@unittest.skipUnless(shutil.which("bash"), "bash is required")
class HostScriptSyntaxTests(unittest.TestCase):
    def test_every_host_script_parses(self) -> None:
        scripts = {
            "inspect": dr.INSPECT,
            "install": dr.install_script("/root/p.tar.gz", "20260928T211500Z")
            + dr.write_dropin(dr.API_DROPIN, dr.API_DROPIN_TEXT) + "\n" + dr.RESTART_API,
            "checks": dr.HOST_CHECKS,
            "revert_api": dr.revert_api_script(),
        }
        for name, script in scripts.items():
            with self.subTest(name):
                done = subprocess.run(  # noqa: S603 - fixed argv, the script is ours
                    [BASH, "-n"], input=script, capture_output=True, text=True, check=False
                )
                self.assertEqual(done.returncode, 0, done.stderr)


class OperatorAddressTests(unittest.TestCase):
    def test_an_address_becomes_a_single_host(self) -> None:
        self.assertEqual(dr.as_cidr("203.0.113.7\n"), "203.0.113.7/32")

    def test_anything_else_is_refused(self) -> None:
        for bad in ("", "203.0.113", "203.0.113.256", "<html>", "2001:db8::1"):
            with self.subTest(bad):
                with self.assertRaises(dr.rt.Stop):
                    dr.as_cidr(bad)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
