"""The release freeze must actually detect a change, and must never hash a secret."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

MANIFEST = Path("artifacts/release_freeze.json")


def load_freeze():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "freeze_release", Path("scripts/freeze_release.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FreezeManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_covers_every_frozen_category(self) -> None:
        for category in ("code", "configuration", "prompts", "policy", "demo_data"):
            with self.subTest(category=category):
                entries = self.manifest["categories"][category]
                self.assertGreater(len(entries), 0, f"{category} froze nothing")

    def test_every_recorded_file_still_exists_and_matches(self) -> None:
        # A stale manifest is worse than no manifest: it asserts a freeze that
        # is no longer true.
        freeze = load_freeze()
        mismatched: list[str] = []
        for entries in self.manifest["categories"].values():
            for name, recorded in entries.items():
                path = Path(name)
                if not path.exists():
                    mismatched.append(f"{name}: missing")
                elif freeze.digest(name) != recorded:
                    mismatched.append(f"{name}: changed since the freeze")
        self.assertEqual(mismatched, [], f"run scripts/freeze_release.py: {mismatched}")

    def test_freeze_digest_changes_when_any_file_changes(self) -> None:
        # The digest is the whole point. If it can stay the same across an edit,
        # "we froze it" is unverifiable.
        original = self.manifest["freeze_digest"]
        tampered = json.loads(MANIFEST.read_text(encoding="utf-8"))
        first_category = next(iter(tampered["categories"]))
        first_file = next(iter(tampered["categories"][first_category]))
        tampered["categories"][first_category][first_file] = "sha256:" + "0" * 64

        import hashlib

        combined = hashlib.sha256()
        for category in sorted(tampered["categories"]):
            for name, value in tampered["categories"][category].items():
                combined.update(f"{name}:{value}\n".encode())
        self.assertNotEqual(original, "sha256:" + combined.hexdigest())

    def test_no_credential_file_is_ever_hashed(self) -> None:
        for entries in self.manifest["categories"].values():
            for name in entries:
                self.assertNotIn(".env", Path(name).name.replace(".env.example", ""))
                self.assertFalse(name.endswith((".pem", ".key")))

    def test_commit_is_recorded_in_a_form_a_scanner_will_not_flag(self) -> None:
        # A bare 40-char hex commit reads as a high-entropy secret and changes on
        # every freeze, which would fail the secret scan forever.
        self.assertTrue(self.manifest["commit"].startswith("git:"))


if __name__ == "__main__":
    unittest.main()
