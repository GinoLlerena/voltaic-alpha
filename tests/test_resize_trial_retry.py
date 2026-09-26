"""The resize tool must ride out a network blip, but never retry a definite answer.

A call that gives up on the first dropped connection can strand the instance
between stop and start. A call that retries a DryRunOperation or a permission
refusal only delays the decision it should act on. A fake `aliyun` on PATH plays
each part.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "resize_trial.py"
spec = importlib.util.spec_from_file_location("resize_trial", SCRIPT)
assert spec is not None and spec.loader is not None
resize_trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resize_trial)


class FakeAliyun:
    """Replies from a script: each line is 'ok' or an error to emit, in order."""

    def __init__(self, replies: list[str]) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "replies").write_text("\n".join(replies) + "\n")
        (self.dir / "count").write_text("0")
        fake = self.dir / "aliyun"
        fake.write_text(
            "#!/bin/bash\n"
            f'd="{self.dir}"\n'
            'n=$(cat "$d/count"); echo $((n+1)) > "$d/count"\n'
            'reply=$(sed -n "$((n+1))p" "$d/replies")\n'
            'case "$reply" in\n'
            '  ok) echo \'{"Result": "ok"}\'; exit 0;;\n'
            '  network) echo "Post https://ecs.aliyuncs.com/?AccessKeyId=LTAIsecret: '
            'connection reset by peer" >&2; exit 1;;\n'
            '  *) echo "ERROR: SDK.ServerError" >&2; echo "ErrorCode: $reply" >&2; exit 1;;\n'
            "esac\n"
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    @property
    def calls(self) -> int:
        return int((self.dir / "count").read_text())

    def __enter__(self) -> FakeAliyun:
        self._patches = [
            mock.patch.dict(os.environ, {"PATH": f"{self.dir}:{os.environ['PATH']}"}),
            mock.patch.object(resize_trial.time, "sleep", lambda _s: None),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc: object) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()


class RetryTests(unittest.TestCase):
    def test_a_dropped_connection_is_retried_until_it_succeeds(self) -> None:
        with FakeAliyun(["network", "network", "ok"]) as fake:
            self.assertEqual(resize_trial.aliyun("ecs", "StartInstance"), {"Result": "ok"})
            self.assertEqual(fake.calls, 3)

    def test_throttling_is_retried(self) -> None:
        with FakeAliyun(["Throttling.User", "ok"]) as fake:
            resize_trial.aliyun("ecs", "DescribeInstances")
            self.assertEqual(fake.calls, 2)

    def test_a_definite_answer_is_not_retried(self) -> None:
        with FakeAliyun(["DryRunOperation", "ok"]) as fake:
            result = resize_trial.aliyun("ecs", "ModifyInstanceSpec", check=False)
            self.assertEqual(result, {"_error": "DryRunOperation"})
            self.assertEqual(fake.calls, 1)

    def test_a_permission_refusal_fails_at_once(self) -> None:
        with FakeAliyun(["Forbidden.RAM", "ok"]) as fake:
            with self.assertRaisesRegex(resize_trial.Stop, "Forbidden.RAM"):
                resize_trial.aliyun("ecs", "StopInstance")
            self.assertEqual(fake.calls, 1)

    def test_a_persistent_outage_gives_up_after_the_backoff(self) -> None:
        attempts = len(resize_trial.RETRY_BACKOFF) + 1
        with FakeAliyun(["network"] * (attempts + 2)) as fake:
            with self.assertRaises(resize_trial.Stop):
                resize_trial.aliyun("ecs", "StartInstance")
            self.assertEqual(fake.calls, attempts)

    def test_a_network_failure_never_surfaces_the_signed_request(self) -> None:
        attempts = len(resize_trial.RETRY_BACKOFF) + 1
        with FakeAliyun(["network"] * attempts):
            with self.assertRaises(resize_trial.Stop) as caught:
                resize_trial.aliyun("ecs", "StartInstance")
        message = str(caught.exception)
        self.assertNotIn("LTAIsecret", message)
        self.assertNotIn("https://", message)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
