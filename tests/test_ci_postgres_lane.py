"""The PostgreSQL lane runs every suite built on the engine-switching harness.

`CSA-011`: `tests/pgsupport.py` moves a harness to PostgreSQL only when
`OPTIONS_ALPHA_TEST_DATABASE_URL` is set, and CI never set it, so the
lifecycle, reconciliation and multi-position suites ran on SQLite alone while a
PostgreSQL service sat beside them. The `lifecycle-postgres` job sets it. This
test keeps that job's file list complete: a new suite that builds on the
harness, directly or through another suite's fixtures, must be added to it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:tests\.)?(\w+)", re.MULTILINE)


def on_the_harness() -> set[str]:
    """Test files that reach `pgsupport`, through any chain of imports in tests/.

    The chain runs through the shared support modules as well as other suites.
    """
    imports = {
        path.name: set(IMPORT.findall(path.read_text(encoding="utf-8")))
        for path in (ROOT / "tests").glob("*.py")
    }
    reached = {"pgsupport.py"}
    while True:
        more = {
            name for name, mods in imports.items()
            if name not in reached and any(f"{mod}.py" in reached for mod in mods)
        }
        if not more:
            return {name for name in reached if name.startswith("test_")}
        reached |= more


class PostgresLane(unittest.TestCase):
    def job(self) -> str:
        return WORKFLOW[WORKFLOW.index("\n  lifecycle-postgres:"):]

    def test_the_job_sets_the_variable_the_harness_reads(self) -> None:
        from pgsupport import ENV

        self.assertIn(f"{ENV}: postgresql+psycopg://", self.job())
        # Only this job: `check` must stay the fast SQLite lane.
        self.assertEqual(WORKFLOW.count(f"{ENV}:"), 1)

    def test_every_suite_on_the_harness_is_in_the_job(self) -> None:
        listed = set(re.findall(r"tests/(test_\w+\.py)", self.job()))
        self.assertEqual(listed, on_the_harness())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
