"""requirements.txt must stay in step with uv.lock.

Two dependency manifests are two chances to resolve different versions. uv.lock
is the source of truth; requirements.txt exists only because some hosts install
from it. This test fails when they drift, which is the moment the difference is
cheap to fix rather than the moment a deploy behaves differently from CI.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REQUIREMENTS = Path("requirements.txt")
EXPORT = [
    "uv", "export", "--no-dev", "--no-hashes", "--no-emit-project",
    "--format", "requirements-txt",
]


def pinned(text: str) -> list[str]:
    return sorted(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#") and line.strip() != "."
    )


class RequirementsSyncTests(unittest.TestCase):
    def test_requirements_match_the_lockfile(self) -> None:
        exported = subprocess.run(  # noqa: S603 - fixed argv, no user input
            EXPORT, capture_output=True, text=True, check=True
        ).stdout
        committed = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertEqual(
            pinned(committed),
            pinned(exported),
            "requirements.txt is stale; regenerate it with:\n  " + " ".join(EXPORT),
        )

    def test_requirements_installs_the_project_itself(self) -> None:
        # Without this line a host installs the dependencies but not
        # options_alpha_lab, and app.py fails on import.
        lines = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()]
        self.assertIn(".", lines)

    def test_every_requirement_is_pinned(self) -> None:
        for line in pinned(REQUIREMENTS.read_text(encoding="utf-8")):
            with self.subTest(requirement=line):
                self.assertIn("==", line, f"{line} is not pinned to an exact version")


if __name__ == "__main__":
    unittest.main()
