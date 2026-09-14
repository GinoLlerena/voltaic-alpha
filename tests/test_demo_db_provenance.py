"""Where `demo/h0_demo.db` comes from, and why it cannot match the receipt.

`CIIP-VAL-004` recorded that the committed receipt's `decision_hash` matches no
decision in the committed database, and prescribed the fix as "regenerate the
demo database so its lifecycle decision hash matches the receipt".

That fix is not available, and this file is the proof rather than the assertion.
The builder is deterministic: replaying the same fixtures under the same code
reproduces the committed hashes exactly, so the database is not stale and
regenerating it changes nothing. The receipt's hash was produced by the original
live Paper run on 28 August under the code of that day; the snapshot replays
under today's code to a different decision, which is what a decision hash is
*for*. A hash that survived a policy change would be the defect.

So the two can only ever correlate honestly by running a fresh Paper lifecycle
under current code, which requires arming the worker — a deliberate,
approval-gated action, not a fixture rebuild.

The tests below pin both halves. If the determinism test fails, the committed
database has drifted from the builder. If the mismatch test fails, something
produced a decision that can claim the receipt, and `CIIP-VAL-004` needs
revisiting rather than the test being edited.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "demo" / "h0_demo.db"
RECEIPT = ROOT / "artifacts" / "h0_paper_lifecycle.json"
BUILDER = ROOT / "scripts" / "build_demo_db.py"

DECISIONS = "select snapshot_id, decision_hash, input_hash from decisions order by snapshot_id"


def _decisions(path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(path) as conn:
        return list(conn.execute(DECISIONS))


class BuilderIsDeterministicTests(unittest.TestCase):
    """The committed database must be the builder's current output, not a relic."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        rebuilt = Path(cls._tmp.name) / "rebuilt.db"
        result = subprocess.run(  # noqa: S603 - fixed argv, no user input
            [sys.executable, str(BUILDER), str(rebuilt)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise AssertionError(f"builder failed:\n{result.stdout}\n{result.stderr}")
        cls.rebuilt = _decisions(rebuilt)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_committed_database_matches_a_fresh_build(self) -> None:
        """A stale demo database is the failure everyone assumed CIIP-VAL-004 was."""
        self.assertEqual(
            _decisions(DB), self.rebuilt,
            "demo/h0_demo.db has drifted from scripts/build_demo_db.py -- rebuild it",
        )

    def test_every_decision_carries_both_hashes(self) -> None:
        for snapshot_id, decision_hash, input_hash in self.rebuilt:
            self.assertTrue(decision_hash, f"{snapshot_id} has no decision_hash")
            self.assertTrue(input_hash, f"{snapshot_id} has no input_hash")

    def test_decision_hashes_are_distinct_per_snapshot(self) -> None:
        """Two snapshots hashing alike would make correlation meaningless."""
        hashes = [row[1] for row in self.rebuilt]
        self.assertEqual(len(hashes), len(set(hashes)))


class ReceiptCorrelatesToNoCommittedDecisionTests(unittest.TestCase):
    """`CIIP-VAL-004` itself, pinned so it cannot regress silently."""

    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.rows = _decisions(DB)

    def test_no_committed_decision_can_claim_the_receipt(self) -> None:
        """If this fails, CIIP-VAL-004 is resolved -- update the doc, not the test."""
        self.assertNotIn(
            self.receipt["decision_hash"],
            {row[1] for row in self.rows},
            "a decision now matches the receipt; CIIP-VAL-004 needs revisiting",
        )

    def test_the_snapshot_itself_is_committed(self) -> None:
        """The mismatch is a re-derivation, not a missing snapshot."""
        self.assertIn(
            self.receipt["snapshot_id"],
            {row[0] for row in self.rows},
            "the lifecycle snapshot is absent, which would be a different defect",
        )

    def test_the_receipt_hash_is_well_formed(self) -> None:
        """Rules out the mismatch being a malformed or empty field."""
        value = self.receipt["decision_hash"]
        self.assertTrue(value.startswith("sha256:"))
        self.assertEqual(len(value.removeprefix("sha256:")), 64)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
