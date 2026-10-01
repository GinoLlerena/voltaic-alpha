"""The hourly backup survives a PostgreSQL restart mid-run, and only that.

On 30 Sep 2026 an unattended security upgrade restarted PostgreSQL four minutes
after a scheduled start, during the 22:00 UTC backup's restore check. The
backup failed, stop-readiness said no, and the scheduled stop waited an hour.
A dropped connection is now retried once, after the server answers again; any
other failure still fails at once. The real script runs against stub tools.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_database.sh"

STUBS = {
    # `sudo -u postgres cmd args` -> `cmd args`
    "sudo": 'shift 2; exec "$@"',
    "install": "exit 0",
    "pg_isready": "exit 0",
    "createdb": "exit 0",
    "dropdb": "exit 0",
    "stat": "echo 42",
    "pg_dump": 'while [ $# -gt 0 ]; do [ "$1" = -f ] && echo dump > "$2"; shift; done',
    # Fails the first N calls with the message in $STUB/restore_error.
    "pg_restore": (
        'n=$(cat "$STUB/restore_calls" 2>/dev/null || echo 0)\n'
        'echo $((n+1)) > "$STUB/restore_calls"\n'
        'fails=$(cat "$STUB/restore_fails")\n'
        'if [ "$n" -lt "$fails" ]; then cat "$STUB/restore_error" >&2; exit 1; fi'
    ),
    "psql": (
        'q="$*"\n'
        'case "$q" in\n'
        '  *"table_name ||"*) echo "decisions|3" ;;\n'
        '  *information_schema.tables*) echo 1 ;;\n'
        '  *version_num*) echo 0008_evaluation_runs ;;\n'
        '  *) echo 3 ;;\n'
        "esac"
    ),
}


class BackupRetry(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.stub = self.dir / "stub"
        self.stub.mkdir()
        for name, body in STUBS.items():
            path = self.stub / name
            path.write_text(f"#!/bin/bash\n{body}\n")
            path.chmod(0o755)
        self.status = self.dir / "backup.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_backup(self, fails: int, error: str) -> tuple[int, dict[str, object], str]:
        (self.stub / "restore_fails").write_text(str(fails))
        (self.stub / "restore_error").write_text(error)
        env = {
            **os.environ, "PATH": f"{self.stub}:{os.environ['PATH']}", "STUB": str(self.stub),
            "BACKUP_DIR": str(self.dir / "dumps"), "BACKUP_STATUS": str(self.status),
        }
        (self.dir / "dumps").mkdir(exist_ok=True)
        done = subprocess.run(  # noqa: S603 - fixed argv, the script under test
            [shutil.which("bash") or "bash", str(SCRIPT)],
            env=env, capture_output=True, text=True, check=False,
        )
        return done.returncode, json.loads(self.status.read_text()), done.stderr

    def calls(self) -> int:
        return int((self.stub / "restore_calls").read_text())

    def test_a_clean_run_verifies_with_one_restore(self) -> None:
        code, status, _ = self.run_backup(0, "")
        self.assertEqual((code, status["verified"], self.calls()), (0, True, 1))

    def test_a_restart_mid_restore_is_retried_once_and_verifies(self) -> None:
        code, status, err = self.run_backup(
            1, "pg_restore: error: server closed the connection unexpectedly"
        )
        self.assertEqual((code, status["verified"], self.calls()), (0, True, 2))
        self.assertIn("retrying once", err)

    def test_a_second_connection_loss_still_fails(self) -> None:
        code, status, _ = self.run_backup(
            2, "FATAL:  terminating connection due to administrator command"
        )
        self.assertEqual((code, status["verified"], self.calls()), (1, False, 2))

    def test_a_real_restore_error_is_never_retried(self) -> None:
        code, status, _ = self.run_backup(1, 'pg_restore: error: relation "x" does not exist')
        self.assertEqual((code, status["verified"], self.calls()), (1, False, 1))
        self.assertIn("does not exist", str(status["detail"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
