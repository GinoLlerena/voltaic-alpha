"""A research result must be reproducible, or it is an anecdote.

`CIIP-3`'s `evaluation_runs`, built now that `gate_study` and `sensitivity` can
fill it. These assert the two properties that make a recorded run worth more
than the number pasted into a document: the dataset is identified by its bytes,
and what the run does not answer is named rather than left empty.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab import evaluations, gate_study
from options_alpha_lab.persistence.models import Base


class RecordingARun(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite+pysqlite:///{self._tmp.name}/runs.db", future=True)
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self._tmp.cleanup()

    def _record(self, **over: object) -> dict[str, object]:
        """Returns the stored values, read inside the session.

        Returning the ORM instance detaches it the moment the session closes,
        and every attribute read then raises rather than telling you what was
        stored.
        """
        payload: dict[str, object] = {
            "harness": "gate_study",
            "dataset": {"path": "fixtures/h0/sensitivity_bars.json", "sha256": "sha256:abc"},
            "parameters": {"MIN_EMA_SEPARATION": "0.002"},
            "outputs": {"baseline": {"passed": 346}},
        }
        payload.update(over)
        with Session(self.engine) as session:
            run = evaluations.record(session, **payload)  # type: ignore[arg-type]
            stored = {
                "id": run.id,
                "harness": run.harness,
                "code_revision": run.code_revision,
                "dataset_manifest": run.dataset_manifest,
                "parameters": run.parameters,
                "outputs": run.outputs,
                "not_covered": run.not_covered,
            }
            session.commit()
            return stored

    def test_a_run_names_what_it_does_not_answer(self) -> None:
        """An empty `stress` column would read as a run that looked and found
        nothing. Naming it says nobody has designed that yet."""
        run = self._record()
        for dimension in ("folds", "costs", "stress", "regime_slices", "uncertainty"):
            self.assertIn(dimension, run["not_covered"])

    def test_the_revision_is_recorded_and_marks_a_dirty_tree(self) -> None:
        run = self._record()
        self.assertTrue(run["code_revision"])
        # Either a hex sha, that sha marked dirty, or an honest "unknown".
        base = str(run["code_revision"]).removesuffix("-dirty")
        self.assertTrue(
            base == "unknown" or all(c in "0123456789abcdef" for c in base),
            run["code_revision"],
        )

    def test_runs_accumulate_rather_than_overwrite(self) -> None:
        """Comparing this week's answer to last week's is the whole point."""
        self._record(outputs={"baseline": {"passed": 346}})
        self._record(outputs={"baseline": {"passed": 351}})
        with Session(self.engine) as session:
            runs = evaluations.history(session, "gate_study")
        self.assertEqual(len(runs), 2)
        self.assertEqual(
            [r.outputs["baseline"]["passed"] for r in runs], [346, 351]
        )

    def test_decimals_and_dates_survive_the_round_trip(self) -> None:
        """One backend accepting a Decimal and another rejecting it is how a
        harness silently stops recording."""
        from datetime import date
        from decimal import Decimal

        run = self._record(
            parameters={"threshold": Decimal("0.002")},
            outputs={"first": date(2024, 9, 11)},
        )
        self.assertEqual(run["parameters"]["threshold"], "0.002")
        self.assertEqual(run["outputs"]["first"], "2024-09-11")
        json.dumps(run["outputs"])  # must be serialisable, not merely stored


class TheDatasetIsIdentifiedByItsBytes(unittest.TestCase):
    def test_the_manifest_carries_a_digest_of_the_file(self) -> None:
        manifest = evaluations.dataset_manifest(Path("fixtures/h0/sensitivity_bars.json"))
        self.assertTrue(manifest["sha256"].startswith("sha256:"))
        self.assertGreater(manifest["bytes"], 0)

    def test_a_changed_dataset_changes_the_digest(self) -> None:
        """Two runs that disagree must be decidably about the same data or not."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.json"
            path.write_text('{"a": 1}')
            before = evaluations.dataset_manifest(path)["sha256"]
            path.write_text('{"a": 2}')
            self.assertNotEqual(before, evaluations.dataset_manifest(path)["sha256"])


class TheGateStudyRecordsWhatItRan(unittest.TestCase):
    def test_the_parameters_are_the_constants_actually_in_force(self) -> None:
        """Recorded from the module, not retyped: a copy would drift silently."""
        from options_alpha_lab import evidence

        params = gate_study.parameters()
        self.assertEqual(params["MIN_EMA_SEPARATION"], str(evidence.MIN_EMA_SEPARATION))
        self.assertEqual(params["FAST_EMA"], evidence.FAST_EMA)
        self.assertEqual(params["RETEST_TOLERANCE"], str(evidence.RETEST_TOLERANCE))
        self.assertEqual(params["LOOKBACK_DAYS"], gate_study.LOOKBACK_DAYS)

    def test_the_manifest_describes_the_fixture_the_study_read(self) -> None:
        report = {"sessions": 493, "first": "2024-09-11", "last": "2026-08-28"}
        manifest = gate_study.manifest(report)
        self.assertEqual(manifest["symbol"], "SPY")
        self.assertEqual(manifest["sessions"], 493)
        self.assertTrue(manifest["sha256"].startswith("sha256:"))


class NothingReadsThisTable(unittest.TestCase):
    def test_no_decision_path_imports_the_recorder(self) -> None:
        """It is a record, not an input. If the agent or the gateway grew a
        dependency on it, a research result could steer a live decision."""
        root = Path(__file__).resolve().parents[1] / "src" / "options_alpha_lab"
        for module in ("agent.py", "execution/gateway.py", "risk.py", "evidence.py"):
            path = root / module
            if not path.exists():
                continue
            with self.subTest(module=module):
                self.assertNotIn("evaluations", path.read_text())
