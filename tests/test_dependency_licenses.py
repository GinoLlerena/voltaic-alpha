"""The licence classifier, and the substring trap it fell into first.

`HK-008` asks for a dependency licence inventory as evidence that submissions
are MIT-compliant. The inventory is only evidence if its classifier is right,
and the first version was not: it tested strong copyleft before weak, and
`LGPL-3.0-only` contains `GPL-3`, so it reported `psycopg` - an LGPL library -
as a blocking GPL finding. Two false blocking results on the exact question the
artifact exists to answer.

That failure is the reason these tests exist and why they lead with it.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "dependency_licenses",
    Path(__file__).resolve().parent.parent / "scripts" / "dependency_licenses.py",
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["dependency_licenses"] = _mod
_spec.loader.exec_module(_mod)

classify = _mod.classify
build = _mod.build


class SubstringTrapTests(unittest.TestCase):
    def test_lgpl_is_weak_copyleft_not_strong(self) -> None:
        """The regression. `LGPL-3.0-only` contains `GPL-3`."""
        for text in ("LGPL-3.0-only", "LGPL-2.1", "GNU Lesser General Public License v3"):
            with self.subTest(text):
                self.assertEqual(classify(text), "WEAK_COPYLEFT")

    def test_agpl_is_still_strong_despite_containing_gpl(self) -> None:
        """Testing weak first must not let the strongest licence through."""
        for text in ("AGPL-3.0", "GNU Affero General Public License v3"):
            with self.subTest(text):
                self.assertEqual(classify(text), "STRONG_COPYLEFT")

    def test_plain_gpl_is_strong(self) -> None:
        for text in ("GPL-3.0-only", "GPLv2", "GNU General Public License"):
            with self.subTest(text):
                self.assertEqual(classify(text), "STRONG_COPYLEFT")


class CategoryTests(unittest.TestCase):
    def test_permissive_licences(self) -> None:
        for text in ("MIT", "BSD-3-Clause", "Apache-2.0", "ISC",
                     "Python Software Foundation License"):
            with self.subTest(text):
                self.assertEqual(classify(text), "PERMISSIVE")

    def test_other_weak_copyleft(self) -> None:
        for text in ("MPL-2.0", "Mozilla Public License 2.0 (MPL 2.0)",
                     "EPL-2.0", "CDDL-1.0"):
            with self.subTest(text):
                self.assertEqual(classify(text), "WEAK_COPYLEFT")

    def test_an_unnameable_licence_is_unknown_not_permissive(self) -> None:
        """A licence nobody can name is not evidence of compliance."""
        for text in ("UNKNOWN", "", "see LICENCE file", "Proprietary"):
            with self.subTest(text):
                self.assertEqual(classify(text), "UNKNOWN")


class InventoryTests(unittest.TestCase):
    def test_the_installed_tree_has_no_strong_copyleft_at_runtime(self) -> None:
        """The claim HK-008 actually makes, asserted against what is installed."""
        blocking = [
            p for p in build().packages
            if p.runtime and p.category == "STRONG_COPYLEFT"
        ]
        self.assertEqual(blocking, [], f"strong copyleft at runtime: {blocking}")

    def test_every_runtime_licence_resolves_to_a_name(self) -> None:
        unresolved = [
            p.name for p in build().packages if p.runtime and p.category == "UNKNOWN"
        ]
        self.assertEqual(unresolved, [], f"unresolved runtime licences: {unresolved}")

    def test_psycopg_is_present_and_classified_weak(self) -> None:
        """Pins the real package the trap misclassified."""
        found = [p for p in build().packages if p.name.lower() == "psycopg"]
        self.assertTrue(found, "psycopg should be installed")
        self.assertEqual(found[0].category, "WEAK_COPYLEFT")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
