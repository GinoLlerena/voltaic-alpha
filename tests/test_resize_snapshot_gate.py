"""No stop without a verified disk snapshot (owner precondition, 27 September 2026).

The tool used to treat the snapshot as optional and carry on to stop the
instance when one could not be made. These tests pin the gate: a snapshot that
is not created, fails, stays incomplete or belongs to another disk stops the
run before anything is quiesced or stopped.
"""

from __future__ import annotations

import argparse
import importlib.util
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "resize_trial.py"
spec = importlib.util.spec_from_file_location("resize_trial_gate", SCRIPT)
assert spec is not None and spec.loader is not None
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

DISK = "d-system"
NOW = datetime(2026, 9, 27, 19, 0, tzinfo=UTC)


def snap(
    sid: str = "s-new", status: str = "accomplished", progress: str = "100%",
    disk: str = DISK, created: datetime = NOW,
) -> dict[str, Any]:
    return {
        "SnapshotId": sid, "Status": status, "Progress": progress, "SourceDiskId": disk,
        "CreationTime": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class FakeCloud:
    """Answers the ECS calls the gate and resize() make, and records them."""

    def __init__(
        self, *, create: dict[str, Any] | None = None, describe: dict[str, Any] | None = None,
        existing: list[dict[str, Any]] | None = None,
    ) -> None:
        self.create = create if create is not None else {"SnapshotId": "s-new"}
        self.describe = describe if describe is not None else snap()
        self.existing = existing or []
        self.calls: list[str] = []

    def __call__(self, *args: str, check: bool = True) -> dict[str, Any]:
        action = args[1]
        self.calls.append(action)
        if action == "DescribeDisks":
            return {"Disks": {"Disk": [{"DiskId": DISK}]}}
        if action == "CreateSnapshot":
            return self.create
        if action == "DescribeSnapshots":
            if "--SnapshotIds" in args:
                return {"Snapshots": {"Snapshot": [self.describe]}}
            return {"Snapshots": {"Snapshot": self.existing}}
        return {}


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        patches = [
            mock.patch.object(rt.time, "sleep", lambda _s: None),
            mock.patch.object(rt, "SNAPSHOT_WAIT_SECONDS", 0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def gate(self, cloud: FakeCloud, rollback: bool = False) -> dict[str, Any]:
        with mock.patch.object(rt, "aliyun", cloud):
            return dict(rt.snapshot_gate(rollback, "20260927T190000Z"))

    def test_a_verified_snapshot_passes(self) -> None:
        result = self.gate(FakeCloud())
        self.assertEqual((result["snapshot_id"], result["source"]), ("s-new", "new"))

    def test_a_snapshot_that_was_not_created_stops(self) -> None:
        with self.assertRaisesRegex(rt.Stop, "not created"):
            self.gate(FakeCloud(create={"_error": "Forbidden.RAM"}))

    def test_a_failed_snapshot_stops(self) -> None:
        with self.assertRaisesRegex(rt.Stop, "not verified"):
            self.gate(FakeCloud(describe=snap(status="failed", progress="40%")))

    def test_an_incomplete_snapshot_stops_at_the_deadline(self) -> None:
        with self.assertRaisesRegex(rt.Stop, "not verified"):
            self.gate(FakeCloud(describe=snap(status="progressing", progress="60%")))

    def test_a_snapshot_of_another_disk_is_not_verified(self) -> None:
        with self.assertRaises(rt.Stop):
            self.gate(FakeCloud(describe=snap(disk="d-other")))

    def test_a_rollback_uses_a_recent_verified_snapshot(self) -> None:
        cloud = FakeCloud(existing=[snap("s-pretrial", created=datetime.now(UTC))])
        result = self.gate(cloud, rollback=True)
        self.assertEqual((result["snapshot_id"], result["source"]), ("s-pretrial", "existing"))
        self.assertNotIn("CreateSnapshot", cloud.calls)

    def test_a_rollback_with_only_an_old_snapshot_takes_a_new_one(self) -> None:
        old = datetime.now(UTC) - timedelta(days=8)
        cloud = FakeCloud(existing=[snap("s-old", created=old)])
        self.assertEqual(self.gate(cloud, rollback=True)["source"], "new")
        self.assertIn("CreateSnapshot", cloud.calls)


class ResizeRespectsTheGateTests(unittest.TestCase):
    """The guarantee itself: a failed gate means nothing was quiesced or stopped."""

    def run_resize(self, cloud: FakeCloud, *, dry_run: bool = False) -> tuple[int, list[str]]:
        remote_calls: list[str] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        running = {
            "InstanceType": rt.ROLLBACK_TYPE, "Status": "Running", "InstanceChargeType": "PostPaid",
        }
        checkpoint = dict.fromkeys(
            ("alembic", "decisions", "market_snapshots", "decision_outcomes", "open_incidents"), 0
        )
        copy = {"bucket": "b", "key": "daily/x.dump.age"}
        done = mock.Mock(returncode=0)
        with (
            mock.patch.object(rt, "aliyun", cloud),
            mock.patch.object(rt, "instance", lambda: running),
            mock.patch.object(rt, "in_stock", lambda _t: True),
            mock.patch.object(rt, "host_state", lambda: checkpoint),
            mock.patch.object(rt, "remote_py", lambda *a, **k: copy),
            mock.patch.object(rt, "remote", lambda s, timeout=0: remote_calls.append(s) or ""),
            mock.patch.object(rt.subprocess, "run", lambda *a, **k: done),
            mock.patch.object(rt, "RECORD_DIR", Path(tmp.name)),
            mock.patch.object(rt, "SNAPSHOT_WAIT_SECONDS", 0),
            mock.patch.object(rt.time, "sleep", lambda _s: None),
        ):
            code = rt.resize(argparse.Namespace(to=rt.TRIAL_TYPE, dry_run=dry_run))
        return code, remote_calls

    def test_no_snapshot_means_no_quiesce_and_no_stop(self) -> None:
        cloud = FakeCloud(create={"_error": "QuotaExceed.Snapshot"})
        code, remote_calls = self.run_resize(cloud)
        self.assertEqual(code, 1)
        self.assertNotIn("StopInstance", cloud.calls)
        self.assertNotIn("ModifyInstanceSpec", cloud.calls)
        self.assertEqual(remote_calls, [])

    def test_an_unverified_snapshot_means_no_stop(self) -> None:
        cloud = FakeCloud(describe=snap(status="progressing", progress="10%"))
        code, remote_calls = self.run_resize(cloud)
        self.assertEqual(code, 1)
        self.assertNotIn("StopInstance", cloud.calls)
        self.assertEqual(remote_calls, [])

    def test_a_dry_run_proves_the_gate_and_stops_there(self) -> None:
        cloud = FakeCloud()
        code, remote_calls = self.run_resize(cloud, dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("CreateSnapshot", cloud.calls)
        self.assertNotIn("StopInstance", cloud.calls)
        self.assertEqual(remote_calls, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
