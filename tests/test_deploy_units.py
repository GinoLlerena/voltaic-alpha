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
import re
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
        for timer in sorted(p.name for p in UNITS.glob("*.timer")):
            self.assertIn(timer, installer, f"{timer} is never installed")

    def test_timers_are_started_not_merely_enabled(self) -> None:
        """`enable` alone leaves a rebuilt host with no backups and no watchdog
        until something reboots it."""
        installer = INSTALLER.read_text()
        self.assertIn("enable --now", installer)
        self.assertIn("TIMERS", installer)

    def test_the_installer_refuses_to_enable_without_an_env_file(self) -> None:
        self.assertIn("NOT enabled", INSTALLER.read_text())


class UnitsParseTests(unittest.TestCase):
    def test_both_units_are_valid_ini_with_an_install_section(self) -> None:
        for path in (WORKER, DASHBOARD):
            parsed = _parse(path)
            self.assertIn("Unit", parsed)
            self.assertIn("Service", parsed)
            self.assertEqual(parsed["Install"]["WantedBy"], "multi-user.target")


class ConsolidatedUnitTests(unittest.TestCase):
    """`CIIP-I-016`, finished: one definition per unit, and the drift it found.

    Five units lived as heredocs inside `restore_hosted_demo.sh` while the host
    ran different text. Every one of the five differed, and two differences were
    functional rather than cosmetic.
    """

    def unit(self, name: str) -> str:
        return (UNITS / name).read_text()

    def test_the_watchdog_records_what_it_finds(self) -> None:
        """The deployed unit had lost `--record`, so it detected and printed and
        the durable incident record never heard about it."""
        exec_start = _exec_start(UNITS / "options-alpha-watchdog.service")
        self.assertIn("options_alpha_lab.watchdog", exec_start)
        self.assertIn("--record", exec_start)

    def test_the_watchdog_can_reach_the_database_it_records_into(self) -> None:
        service = _parse(UNITS / "options-alpha-watchdog.service")["Service"]
        self.assertEqual(service["EnvironmentFile"], "/etc/options-alpha.env")

    def test_no_unit_carries_an_unexpanded_shell_variable(self) -> None:
        """The port 80 unit was written by a quoted heredoc, so systemd would have
        received a literal `$PUBLIC_PORT`. systemd does not expand shell
        variables in ExecStart, so a rebuilt host got a unit that could not work."""
        for path in sorted(UNITS.glob("options-alpha*")):
            for line in path.read_text().splitlines():
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotRegex(
                    line, r"\$[A-Z_]{3,}", f"{path.name} has an unexpanded variable: {line}"
                )

    def test_the_backup_unit_keeps_its_retention_and_says_why(self) -> None:
        text = self.unit("options-alpha-backup.service")
        self.assertIn("BACKUP_KEEP=12", text)
        self.assertIn("NOT a backup", text)

    def test_the_restore_script_no_longer_writes_units(self) -> None:
        """One definition per unit. Two drift, and these had."""
        script = (UNITS.parents[1] / "scripts" / "restore_hosted_demo.sh").read_text()
        self.assertNotIn("cat > /etc/systemd/system/", script)
        self.assertNotIn("cat >/etc/systemd/system/", script)
        self.assertIn("deploy/install_units.sh", script)

    def test_every_unit_the_restore_path_needs_is_committed(self) -> None:
        committed = {p.name for p in UNITS.glob("options-alpha*")}
        for name in (
            "options-alpha-port80.service",
            "options-alpha-backup.service",
            "options-alpha-backup.timer",
            "options-alpha-watchdog.service",
            "options-alpha-watchdog.timer",
        ):
            self.assertIn(name, committed)


class ReadOnlyRoleScriptTests(unittest.TestCase):
    """`CIIP-I-017`. The scripts handle a live credential, so the tests are
    about the credential rather than about the SQL."""

    CREATE = UNITS.parent / "create_readonly_role.sh"
    VERIFY = UNITS.parent / "verify_readonly_role.sh"

    def _sql_block(self) -> str:
        """The `{ ... } | psql` heredoc-free block. Everything in it goes to
        psql's stdin, not to the terminal."""
        text = self.CREATE.read_text()
        start = text.index("\n{\n")
        end = text.index("} | sudo -u postgres psql", start)
        return text[start:end]

    def test_the_password_never_reaches_the_terminal(self) -> None:
        """A password in stdout is a password in the journal and in a transcript.

        The `printf` lines that carry it are piped into psql, so the check is
        that every one of them sits inside that pipe and none is a bare `echo`.
        """
        sql_block = self._sql_block()
        for line in self.CREATE.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "$PW" not in stripped:
                continue
            if stripped.startswith("echo"):
                self.fail(f"password echoed to the terminal: {stripped}")
            if stripped.startswith("printf"):
                self.assertIn(
                    stripped, sql_block,
                    f"printf carrying the password is not piped to psql: {stripped}",
                )

    def test_the_reported_url_is_masked(self) -> None:
        """The script does print the URL shape, so it must redact the credential."""
        for line in self.CREATE.read_text().splitlines():
            if line.strip().startswith("echo") and "$NEW" in line:
                self.assertIn("<pw>", line, f"URL printed unmasked: {line.strip()}")

    def test_the_password_is_never_passed_through_argv(self) -> None:
        """`psql -c "...$PW..."` would expose it to any user running `ps`."""
        for path in (self.CREATE, self.VERIFY):
            for match in re.findall(r"psql[^\n|]*", path.read_text()):
                if "$PW" in match:
                    self.fail(f"{path.name} puts the password in argv: {match}")

    def test_sql_reaches_psql_over_stdin(self) -> None:
        self.assertIn("-f -", self.CREATE.read_text())

    def test_the_verifier_is_a_gate_not_a_report(self) -> None:
        """It must fail the process, or a rebuild will 'pass' by not being read."""
        text = self.VERIFY.read_text()
        self.assertIn("exit \"$fail\"", text)
        self.assertIn("fail=1", text)

    def test_the_verifier_attempts_every_destructive_form(self) -> None:
        text = self.VERIFY.read_text()
        for sql in ("insert into", "update runs", "delete from", "truncate",
                    "create table", "drop table"):
            self.assertIn(sql, text.lower(), f"{sql} is never attempted")

    def test_the_verifier_checks_reads_too(self) -> None:
        """A role that can do nothing at all would pass a writes-only check."""
        self.assertIn("expect allow", self.VERIFY.read_text())

    def test_the_env_file_is_written_restrictively(self) -> None:
        text = self.CREATE.read_text()
        self.assertIn("umask 077", text)
        self.assertIn("chmod 0600", text)

    def test_a_rollback_copy_is_kept(self) -> None:
        self.assertIn(".bak", self.CREATE.read_text())

    def test_future_tables_stay_readable(self) -> None:
        """Without this a migration silently breaks the dashboard."""
        self.assertIn("ALTER DEFAULT PRIVILEGES", self.CREATE.read_text())

    def test_the_rebuild_sequence_names_both_scripts(self) -> None:
        """CIIP-I-016's lesson: an uncaptured step is a step the rebuild loses."""
        doc = (UNITS.parents[1] / "docs" / "improvements"
               / "options_alpha_infrastructure_redesign_v0_1.md").read_text()
        section = doc.split("## 6. Rebuild sequence")[1].split("## 7.")[0]
        self.assertIn("create_readonly_role.sh", section)
        self.assertIn("verify_readonly_role.sh", section)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ScriptsAddressTheHostThatExists(unittest.TestCase):
    """Every committed script must name a live instance.

    `CIIP-I-001` consolidated the worker onto the demo host on 10 September 2026
    and the separate worker instance was released. Five scripts kept naming the
    released one for nine days, including `disarm_worker.sh` — the command an
    operator reaches for to turn autonomous Paper entry off. It failed loudly
    rather than silently, and nothing was armed, so the hazard stayed latent.
    Nothing was watching for it, which is what this fixes.

    A released instance cannot be detected from here without a cloud call, so
    the check is the other way round: the id of a machine that no longer exists
    must not appear, and any instance id in `scripts/` must be one this file
    knows about.
    """

    SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
    #: The consolidated host. A second entry belongs here only when a second
    #: machine genuinely exists again.
    LIVE = {"i-t4n88bkfwsq0lhzmfjii"}
    #: Released by the consolidation. Naming it is the defect.
    RELEASED = {"i-t4nfdbjx66so1we0aysh"}

    def _scripts(self) -> list[Path]:
        return sorted(self.SCRIPTS.glob("*.sh"))

    def test_no_script_addresses_a_released_instance(self) -> None:
        for path in self._scripts():
            with self.subTest(script=path.name):
                text = path.read_text(encoding="utf-8")
                for dead in self.RELEASED:
                    # Named in a comment explaining the history is fine; used as
                    # a value is not. Strip comment bodies before looking.
                    code = "\n".join(
                        line.split("#", 1)[0] for line in text.splitlines()
                    )
                    self.assertNotIn(dead, code, f"{path.name} addresses a released instance")

    def test_every_instance_id_is_one_we_know_about(self) -> None:
        """A new id appearing without this list being updated is the same bug
        arriving from the other direction."""
        pattern = re.compile(r"\bi-[a-z0-9]{20,}\b")
        for path in self._scripts():
            code = "\n".join(line.split("#", 1)[0] for line in path.read_text().splitlines())
            for found in pattern.findall(code):
                with self.subTest(script=path.name, instance=found):
                    self.assertIn(found, self.LIVE | self.RELEASED)
                    self.assertIn(found, self.LIVE, f"{path.name} uses a released instance")

    def test_the_restore_script_visits_each_machine_once(self) -> None:
        """Both role names resolve to one box, so a loop over both would start
        it twice and report it twice."""
        restore = (self.SCRIPTS / "restore_hosted_demo.sh").read_text(encoding="utf-8")
        self.assertIn("hosts()", restore)
        self.assertIn("sort -u", restore)
        self.assertNotIn('for id in "$DEMO" "$WORKER"', restore)
        self.assertNotIn('for id in "$WORKER" "$DEMO"', restore)
