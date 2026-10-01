"""Security updates run on trading-day mornings, between the boot and the backup.

Ubuntu's apt timers were missed while the server was stopped and caught up at
the next boot, where an upgrade restarted PostgreSQL in the middle of the
boot-time backup (30 Sep 2026). The drop-ins pin them to a fixed weekday slot
in New York time, after the scheduled start and its boot-time backup and
before the 09:00 ET backup, and never catch up a missed run.
"""

from __future__ import annotations

import configparser
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "deploy" / "systemd"
sys.path.insert(0, str(ROOT / "scripts"))
import ship_host  # noqa: E402


def timer(name: str) -> dict[str, list[str]]:
    lines = (UNITS / f"{name}.d" / "options-alpha.conf").read_text().splitlines()
    out: dict[str, list[str]] = {}
    for line in lines:
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            out.setdefault(key.strip(), []).append(value.strip())
    return out


def et_minutes(value: str) -> int:
    match = re.fullmatch(r"Mon\.\.Fri (\d\d):(\d\d) America/New_York", value)
    assert match, value
    return int(match.group(1)) * 60 + int(match.group(2))


class AptTimers(unittest.TestCase):
    def test_each_drop_in_replaces_the_schedule_rather_than_adding_to_it(self) -> None:
        for name in ("apt-daily.timer", "apt-daily-upgrade.timer"):
            with self.subTest(name):
                cal = timer(name)["OnCalendar"]
                self.assertEqual(cal[0], "", "the first OnCalendar= must reset Ubuntu's own times")
                self.assertEqual(len(cal), 2)

    def test_no_catch_up_and_no_random_delay(self) -> None:
        for name in ("apt-daily.timer", "apt-daily-upgrade.timer"):
            with self.subTest(name):
                self.assertEqual(timer(name)["Persistent"], ["false"])
                self.assertEqual(timer(name)["RandomizedDelaySec"], ["0"])

    def test_after_the_scheduled_start_and_before_the_nine_o_clock_backup(self) -> None:
        # The scheduler starts the server between 08:30 and 08:45 ET (15-minute
        # ticks) and the boot-time backup takes a minute or two.
        download = et_minutes(timer("apt-daily.timer")["OnCalendar"][1])
        upgrade = et_minutes(timer("apt-daily-upgrade.timer")["OnCalendar"][1])
        self.assertGreaterEqual(download, 8 * 60 + 46)
        self.assertLess(download, upgrade)
        self.assertLessEqual(upgrade, 8 * 60 + 52)

    def test_the_files_are_valid_unit_syntax(self) -> None:
        for name in ("apt-daily.timer", "apt-daily-upgrade.timer"):
            parser = configparser.ConfigParser(strict=False, interpolation=None)
            parser.read_string((UNITS / f"{name}.d" / "options-alpha.conf").read_text())
            self.assertIn("Timer", parser.sections())


class ShipHostPaths(unittest.TestCase):
    def test_drop_ins_go_under_their_unit_and_restart_it(self) -> None:
        f = "deploy/systemd/apt-daily-upgrade.timer.d/options-alpha.conf"
        expected = "/etc/systemd/system/apt-daily-upgrade.timer.d/options-alpha.conf"
        self.assertEqual(ship_host.live_path(f), expected)
        self.assertEqual(ship_host.timers_touched([f]), ["apt-daily-upgrade.timer"])

    def test_the_backup_script_ships_with_the_units(self) -> None:
        self.assertIn("scripts/backup_database.sh", ship_host.HOST_SCRIPTS)
        self.assertEqual(
            ship_host.live_path("scripts/backup_database.sh"),
            "/opt/options-alpha/scripts/backup_database.sh",
        )
        self.assertIn("scripts/backup_database.sh", ship_host.local_files())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
