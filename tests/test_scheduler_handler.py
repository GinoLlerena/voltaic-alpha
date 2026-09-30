"""The Function Compute handler (design §2-§5): it only carries out `decide`.

A fake cloud records every call, so each test says what was and was not sent
to ECS. Dry run must send nothing that changes the instance.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

HANDLER = Path(__file__).resolve().parents[1] / "deploy" / "scheduler" / "handler.py"
spec = importlib.util.spec_from_file_location("scheduler_handler", HANDLER)
assert spec is not None and spec.loader is not None
handler = importlib.util.module_from_spec(spec)
sys.modules["scheduler_handler"] = handler
spec.loader.exec_module(handler)

SATURDAY = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)      # outside any run window
TUESDAY_OPEN = datetime(2026, 10, 6, 13, 0, tzinfo=UTC)  # 09:00 ET, inside the window


class FakeCloud:
    instance_id = "i-test"

    def __init__(self, status: str = "Running", tags: dict[str, str] | None = None,
                 started: datetime | None = None) -> None:
        self.status, self.tags, self.started = status, tags or {}, started
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.events: list[tuple[str, dict[str, Any]]] = []

    def instance(self) -> dict[str, Any]:
        return {
            "Status": self.status,
            "Tags": {"Tag": [{"TagKey": k, "TagValue": v} for k, v in self.tags.items()]},
            "StartTime": self.started.strftime("%Y-%m-%dT%H:%MZ") if self.started else None,
        }

    def ecs(self, action: str, **params: str) -> Any:
        self.calls.append((action, params))
        return {}

    def event(self, name: str, content: dict[str, Any]) -> None:
        self.events.append((name, content))

    def actions(self) -> list[str]:
        return [a for a, _ in self.calls]

    def alerts(self) -> list[str]:
        return [c["alert"] for n, c in self.events if n == "oa-scheduler-alert"]


def run(cloud: FakeCloud, now: datetime, *, dry: bool, ready: bool = True,
        healthy: bool = True) -> dict[str, Any]:
    readiness = handler.Readiness(ready, () if ready else ("1 open position",))
    with (
        mock.patch.object(handler, "readiness_from", lambda _u: readiness),
        mock.patch.object(handler, "started_healthy",
                          lambda _u: (healthy, "ok" if healthy else "worker not live: Stale")),
    ):
        return dict(handler.tick(cloud, now=now, dry_run=dry, base_url="http://x"))


class DryRun(unittest.TestCase):
    def test_a_due_stop_is_logged_not_sent(self) -> None:
        cloud = FakeCloud()
        record = run(cloud, SATURDAY, dry=True)
        self.assertEqual(record["action"], "stop")
        self.assertIn("would StopInstance (StopCharging)", record["done"])
        self.assertEqual(cloud.actions(), [])
        self.assertEqual([n for n, _ in cloud.events], ["oa-scheduler-decision"])

    def test_a_due_start_and_a_rewrite_are_logged_not_sent(self) -> None:
        cloud = FakeCloud(status="Stopped", tags={"oa-session-until": "tomorrow"})
        record = run(cloud, SATURDAY, dry=True)
        self.assertEqual(cloud.actions(), [])
        self.assertTrue(any(d.startswith("would rewrite the lock") for d in record["done"]))
        self.assertIn("would StartInstance", record["done"])


class Live(unittest.TestCase):
    def test_a_stop_uses_economical_mode(self) -> None:
        cloud = FakeCloud()
        run(cloud, SATURDAY, dry=False)
        self.assertEqual(cloud.calls, [("StopInstance", {"InstanceId": "i-test",
                                                         "StoppedMode": "StopCharging"})])

    def test_not_ready_means_no_stop_and_an_alert(self) -> None:
        cloud = FakeCloud()
        run(cloud, SATURDAY, dry=False, ready=False)
        self.assertEqual(cloud.actions(), [])
        self.assertTrue(any("1 open position" in a for a in cloud.alerts()))

    def test_an_invalid_lock_is_rewritten_to_24_hours_and_nothing_is_stopped(self) -> None:
        cloud = FakeCloud(tags={"oa-session-until": "2027-01-01T00:00Z"})
        run(cloud, SATURDAY, dry=False)
        self.assertEqual(cloud.actions(), ["TagResources"])
        params = cloud.calls[0][1]
        self.assertEqual(params["Tag.1.Key"], "oa-session-until")
        self.assertEqual(params["Tag.1.Value"], "2026-10-04T15:00:00Z")
        self.assertTrue(cloud.alerts())

    def test_an_active_lock_starts_a_stopped_server(self) -> None:
        until = (SATURDAY + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%MZ")
        cloud = FakeCloud(status="Stopped", tags={"oa-session-until": until})
        run(cloud, SATURDAY, dry=False)
        self.assertEqual(cloud.actions(), ["StartInstance"])


class StartCheck(unittest.TestCase):
    def test_an_unhealthy_start_alerts_once_in_its_window(self) -> None:
        started = TUESDAY_OPEN - timedelta(minutes=25)
        cloud = FakeCloud(started=started)
        run(cloud, TUESDAY_OPEN, dry=False, healthy=False)
        self.assertTrue(any("not healthy" in a for a in cloud.alerts()))
        later = FakeCloud(started=TUESDAY_OPEN - timedelta(minutes=50))
        run(later, TUESDAY_OPEN, dry=False, healthy=False)
        self.assertFalse(later.alerts())

    def test_a_healthy_start_is_quiet(self) -> None:
        cloud = FakeCloud(started=TUESDAY_OPEN - timedelta(minutes=25))
        run(cloud, TUESDAY_OPEN, dry=False, healthy=True)
        self.assertFalse(cloud.alerts())


class Signature(unittest.TestCase):
    def test_the_documented_example_signs_identically(self) -> None:
        # Alibaba Cloud's published RPC signature example.
        query = {
            "Timestamp": "2016-02-23T12:46:24Z", "Format": "XML", "AccessKeyId": "testid",
            "Action": "DescribeRegions", "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": "3ee8c1b8-83d3-44af-a94f-4e0ad82fd6cf",
            "Version": "2014-05-26", "SignatureVersion": "1.0",
        }
        self.assertEqual(handler.sign(query, "testsecret"), "OLeaidS1JvxuMvnyHOwuJ+uX5qY=")


class Failure(unittest.TestCase):
    def test_a_tick_that_cannot_decide_alerts_and_fails_the_invocation(self) -> None:
        class Broken(FakeCloud):
            def instance(self) -> dict[str, Any]:
                raise RuntimeError("DescribeInstances failed: HTTP 403 Forbidden.RAM")

        broken = Broken()
        context = mock.Mock()
        with (
            mock.patch.object(handler, "Cloud", lambda *a: broken),
            mock.patch.dict("os.environ", {"INSTANCE_ID": "i-test", "CMS_GROUP_ID": "1"}),
            self.assertRaises(RuntimeError),
        ):
            handler.handler({}, context)
        self.assertTrue(any("Forbidden.RAM" in a for a in broken.alerts()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
