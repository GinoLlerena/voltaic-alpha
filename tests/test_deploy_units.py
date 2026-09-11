"""The committed systemd units, and the safety property the base unit carries.

`CIIP-I-016`. These units previously existed only on the deployed host, so a
rebuild could not restore them and one did not.

The assertion worth the file is that the **base** worker unit is disarmed.
`arm_worker.sh` writes a drop-in that overrides `ExecStart` with
`--mode paper_execute` and an approval token. A drop-in overrides something it
assumes is present, so if the base unit were ever rebuilt by hand with arming
baked in, the next arm would inherit it silently and nothing would say so. The
base unit is the thing under test precisely because the override is not.
"""

from __future__ import annotations

import configparser
import unittest
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "deploy" / "systemd"
WORKER = UNITS / "options-alpha-worker.service"
DASHBOARD = UNITS / "options-alpha.service"
INSTALLER = UNITS.parent / "install_units.sh"


def _parse(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(path.read_text())
    return parser


def _exec_start(path: Path) -> str:
    """`ExecStart` with systemd's line continuations folded back to one line."""
    return " ".join(_parse(path)["Service"]["ExecStart"].split())


class WorkerUnitIsDisarmedTests(unittest.TestCase):
    def test_the_base_unit_runs_in_observe_mode(self) -> None:
        self.assertIn("--mode observe", _exec_start(WORKER))

    def test_the_base_unit_cannot_reach_a_broker(self) -> None:
        """`paper_execute` belongs in a drop-in, never in the committed base."""
        exec_start = _exec_start(WORKER)
        self.assertNotIn("paper_execute", exec_start)
        self.assertNotIn("--approve", exec_start)

    def test_arming_is_expressed_as_a_drop_in_not_an_edit(self) -> None:
        """If arm_worker.sh ever rewrites the base unit, this file is wrong."""
        arm = (UNITS.parents[1] / "scripts" / "arm_worker.sh").read_text()
        self.assertIn("options-alpha-worker.service.d/", arm)
        self.assertNotIn(
            "cat > /etc/systemd/system/options-alpha-worker.service\n",
            arm,
            "arming must not overwrite the base unit",
        )

    def test_the_disarmed_default_is_explained_in_the_unit(self) -> None:
        """A bare `--mode observe` invites someone to 'fix' it."""
        self.assertIn("Disarmed on purpose", WORKER.read_text())


class EnvironmentContractTests(unittest.TestCase):
    def test_each_unit_names_the_file_it_cannot_start_without(self) -> None:
        self.assertEqual(
            _parse(WORKER)["Service"]["EnvironmentFile"], "/etc/options-alpha.env"
        )
        self.assertEqual(
            _parse(DASHBOARD)["Service"]["EnvironmentFile"],
            "/etc/options-alpha-dashboard.env",
        )

    def test_the_units_do_not_use_separate_environment_files_by_accident(self) -> None:
        """The split is deliberate: the dashboard gets no broker credentials."""
        self.assertNotEqual(
            _parse(WORKER)["Service"]["EnvironmentFile"],
            _parse(DASHBOARD)["Service"]["EnvironmentFile"],
        )

    def test_no_secret_is_baked_into_a_unit(self) -> None:
        for path in (WORKER, DASHBOARD):
            text = path.read_text()
            for marker in ("ALPACA_API_KEY=", "ALPACA_SECRET_KEY=", "OPENAI_API_KEY=", "sk-"):
                self.assertNotIn(marker, text, f"{path.name} carries a credential")


class DashboardUnitTests(unittest.TestCase):
    def test_it_runs_the_dashboard(self) -> None:
        self.assertIn("streamlit run app.py", _exec_start(DASHBOARD))

    def test_it_does_not_grant_itself_privileges(self) -> None:
        service = _parse(DASHBOARD)["Service"]
        self.assertEqual(service["NoNewPrivileges"], "true")


class InstallerCoversWhatIsCommittedTests(unittest.TestCase):
    def test_every_committed_unit_is_installed_by_the_script(self) -> None:
        """A unit added here but not wired into the installer is dead weight."""
        installer = INSTALLER.read_text()
        for unit in sorted(p.name for p in UNITS.glob("*.service")):
            self.assertIn(unit, installer, f"{unit} is never installed")

    def test_the_installer_refuses_to_enable_without_an_env_file(self) -> None:
        self.assertIn("NOT enabled", INSTALLER.read_text())


class UnitsParseTests(unittest.TestCase):
    def test_both_units_are_valid_ini_with_an_install_section(self) -> None:
        for path in (WORKER, DASHBOARD):
            parsed = _parse(path)
            self.assertIn("Unit", parsed)
            self.assertIn("Service", parsed)
            self.assertEqual(parsed["Install"]["WantedBy"], "multi-user.target")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
