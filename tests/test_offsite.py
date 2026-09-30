"""The off-host upload has to refuse what it cannot vouch for, and retry per key.

Each test is written from the failure it guards against: an unverified dump
reaching OSS, a stale record uploaded as today's, a weekly copy never retried
because the daily one was present, or an upload reported as done that never
landed. OSS and `age` are replaced by a fake that keeps the objects in memory,
so nothing here touches the network.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from options_alpha_lab import offsite, watchdog
from options_alpha_lab.calendar import committed_calendar
from options_alpha_lab.offsite import (
    MAX_DUMP_AGE_SECONDS,
    OffsiteError,
    OssConfig,
    destination_keys,
    parse_listing,
    run_offsite,
    summarize_error,
    verify_source,
)

# Post-close dumps (17:05 ET): since the scheduled-stop design (§6) the daily
# copy is the first dump after the session's close, keyed by the session.
MONDAY = datetime(2026, 9, 21, 21, 5, tzinfo=UTC)
FRIDAY = datetime(2026, 9, 25, 21, 5, tzinfo=UTC)
CONFIG = OssConfig("bucket", "ap-southeast-1", "oss-ap-southeast-1-internal.aliyuncs.com")
#: Shape only - the module checks for a single `age1...` token, not a real key.
RECIPIENT = "age1" + "q" * 58


class FakeOss:
    """Just enough of ossutil and age to exercise run_offsite."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.objects: dict[str, tuple[int, datetime]] = {}
        self.calls: list[list[str]] = []
        self.fail_put: set[str] = set()
        self.truncate: set[str] = set()

    def __call__(self, argv: Sequence[str]) -> tuple[int, str]:
        args = list(argv)
        self.calls.append(args)
        if args[0] == "age":
            out, src = Path(args[args.index("-o") + 1]), Path(args[-1])
            out.write_bytes(b"age-encryption.org/v1\n" + src.read_bytes()[::-1])
            return 0, ""
        if "list-objects-v2" in args:
            prefix = args[args.index("--prefix") + 1]
            items = [
                {"Key": k, "Size": str(size), "LastModified": at.isoformat().replace("+00:00", "Z")}
                for k, (size, at) in sorted(self.objects.items()) if k.startswith(prefix)
            ]
            doc: dict[str, object] = {"KeyCount": str(len(items)), "Prefix": prefix}
            if items:
                doc["Contents"] = items[0] if len(items) == 1 else items
            return 0, json.dumps(doc) + "\n\n0.07(s) elapsed\n"
        if "put-object" in args:
            key = args[args.index("--key") + 1]
            if key in self.fail_put:
                return 1, ("Error: operation error PutObject\nHttp Status Code: 403.\n"
                           "Error Code: AccessDenied.\nRequest Id: X.\n")
            body = Path(args[args.index("--body") + 1].removeprefix("file://"))
            size = body.stat().st_size - (1 if key in self.truncate else 0)
            self.objects[key] = (size, self.now)
            return 0, ""
        raise AssertionError(f"unexpected command {args}")

    def puts(self) -> list[str]:
        return [c[c.index("--key") + 1] for c in self.calls if "put-object" in c]

    def encryptions(self) -> int:
        return sum(1 for c in self.calls if c[0] == "age")


class OffsiteCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.dump = self.dir / "options_alpha.dump"
        self.dump.write_bytes(b"PGDMP" + b"x" * 1000)
        (self.dir / "recipient.pub").write_text(RECIPIENT + "\n")
        self.staging = self.dir / "staging"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def status(self, at: datetime, **overrides: object) -> Path:
        body: dict[str, object] = {
            "at": at.isoformat().replace("+00:00", "Z"), "verified": True,
            "path": str(self.dump), "bytes": self.dump.stat().st_size,
            "tables": 28, "rows_restored": 2771, "alembic_revision": "0008_evaluation_runs",
        }
        body.update(overrides)
        path = self.dir / "backup.json"
        path.write_text(json.dumps(body))
        return path

    def run_once(self, fake: FakeOss, at: datetime, **overrides: object) -> dict[str, object]:
        return run_offsite(
            config=CONFIG, runner=fake, now=at + timedelta(minutes=30),
            backup_file=str(self.status(at, **overrides)),
            recipient_file=str(self.dir / "recipient.pub"),
            staging_dir=str(self.staging), ossutil="ossutil", age="age",
        )


class SourceRefusals(OffsiteCase):
    def test_an_unverified_dump_is_never_uploaded(self) -> None:
        fake = FakeOss(MONDAY)
        with self.assertRaisesRegex(OffsiteError, "not verified"):
            self.run_once(fake, MONDAY, verified=False, detail="pg_restore failed")
        self.assertEqual(fake.puts(), [])

    def test_a_stale_record_is_refused_rather_than_uploaded_as_today(self) -> None:
        old = MONDAY - timedelta(seconds=MAX_DUMP_AGE_SECONDS + 60)
        with self.assertRaisesRegex(OffsiteError, "stale"):
            verify_source(json.loads(self.status(old).read_text()), MONDAY)

    def test_a_dump_that_changed_after_verification_is_refused(self) -> None:
        with self.assertRaisesRegex(OffsiteError, "changed after it was verified"):
            verify_source(json.loads(self.status(MONDAY, bytes=5).read_text()), MONDAY)

    def test_a_missing_dump_file_is_refused(self) -> None:
        self.dump.unlink()
        record = {"at": MONDAY.isoformat(), "verified": True, "path": str(self.dump), "bytes": 1}
        with self.assertRaisesRegex(OffsiteError, "gone"):
            verify_source(record, MONDAY)

    def test_an_identity_in_place_of_the_recipient_is_refused(self) -> None:
        (self.dir / "recipient.pub").write_text("AGE-SECRET-KEY-1NOTAREALKEY\n")
        with self.assertRaisesRegex(OffsiteError, "single age recipient"):
            self.run_once(FakeOss(MONDAY), MONDAY)

    def test_the_backup_file_path_matches_the_watchdog(self) -> None:
        self.assertEqual(offsite.DEFAULT_BACKUP_FILE, watchdog.DEFAULT_BACKUP_FILE)


class Uploads(OffsiteCase):
    def test_a_dump_taken_during_the_session_is_not_uploaded(self) -> None:
        # 11:00 ET: the hourly dump holds a partial day. Storing it would take
        # the session's key, and the bucket forbids overwriting it later.
        fake = FakeOss(MONDAY)
        record = self.run_once(fake, datetime(2026, 9, 21, 15, 0, tzinfo=UTC))
        self.assertEqual((record["keys"], record["uploaded"]), ([], []))
        self.assertEqual(fake.encryptions(), 0)
        self.assertEqual(fake.puts(), [])

    def test_a_weekday_uploads_daily_only(self) -> None:
        fake = FakeOss(MONDAY)
        record = self.run_once(fake, MONDAY)
        self.assertEqual(record["uploaded"], ["daily/2026-09-21.dump.age"])
        self.assertEqual(fake.encryptions(), 1)

    def test_the_weeks_last_session_encrypts_once_and_uploads_both(self) -> None:
        fake = FakeOss(FRIDAY)
        record = self.run_once(fake, FRIDAY)
        self.assertEqual(record["uploaded"],
                         ["daily/2026-09-25.dump.age", "weekly/2026-09-25.dump.age"])
        self.assertEqual(fake.encryptions(), 1)

    def test_a_second_run_the_same_day_uploads_nothing(self) -> None:
        fake = FakeOss(MONDAY)
        self.run_once(fake, MONDAY)
        record = self.run_once(fake, MONDAY)
        self.assertEqual(record["uploaded"], [])
        self.assertEqual(fake.puts(), ["daily/2026-09-21.dump.age"])

    def test_a_missing_weekly_is_retried_without_touching_daily(self) -> None:
        fake = FakeOss(FRIDAY)
        fake.fail_put = {"weekly/2026-09-25.dump.age"}
        with self.assertRaisesRegex(OffsiteError, "403"):
            self.run_once(fake, FRIDAY)
        daily_before = fake.objects["daily/2026-09-25.dump.age"]

        fake.fail_put = set()
        record = self.run_once(fake, FRIDAY)
        self.assertEqual(record["uploaded"], ["weekly/2026-09-25.dump.age"])
        self.assertEqual(fake.objects["daily/2026-09-25.dump.age"], daily_before)

    def test_an_upload_that_did_not_land_intact_fails(self) -> None:
        fake = FakeOss(MONDAY)
        fake.truncate = {"daily/2026-09-21.dump.age"}
        with self.assertRaisesRegex(OffsiteError, "did not land intact"):
            self.run_once(fake, MONDAY)

    def test_only_ciphertext_is_uploaded_and_staging_is_removed(self) -> None:
        fake = FakeOss(MONDAY)
        self.run_once(fake, MONDAY)
        put = next(c for c in fake.calls if "put-object" in c)
        self.assertIn(str(self.staging), put[put.index("--body") + 1])
        self.assertNotIn(str(self.dump), " ".join(put))
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_metadata_tells_a_restorer_what_they_hold(self) -> None:
        fake = FakeOss(MONDAY)
        self.run_once(fake, MONDAY)
        put = next(c for c in fake.calls if "put-object" in c)
        metadata = [put[i + 1] for i, a in enumerate(put) if a == "--metadata"]
        self.assertIn("alembic-revision=0008_evaluation_runs", metadata)
        self.assertIn("rows-restored=2771", metadata)
        self.assertTrue(any(m.startswith("dump-sha256=") for m in metadata))

    def test_no_credential_ever_appears_on_a_command_line(self) -> None:
        fake = FakeOss(MONDAY)
        self.run_once(fake, MONDAY)
        for call in fake.calls:
            if call[0] == "ossutil":
                self.assertEqual(call[1:3], ["--mode", "EcsRamRole"])
                self.assertNotIn("--access-key-id", call)
                self.assertNotIn("--access-key-secret", call)


class Parsing(unittest.TestCase):
    def test_one_object_arrives_as_a_bare_object(self) -> None:
        out = ('{"Contents": {"Key": "daily/a", "Size": "5", '
               '"LastModified": "2026-09-23T15:20:47.000Z"}}\n\n0.07(s) elapsed\n')
        self.assertEqual([o.key for o in parse_listing(out)], ["daily/a"])
        self.assertEqual(parse_listing(out)[0].size, 5)

    def test_several_objects_arrive_as_a_list(self) -> None:
        out = json.dumps({"Contents": [
            {"Key": "daily/a", "Size": "1", "LastModified": "2026-09-22T00:00:00.000Z"},
            {"Key": "daily/b", "Size": "2", "LastModified": "2026-09-23T00:00:00.000Z"},
        ]})
        self.assertEqual([o.key for o in parse_listing(out)], ["daily/a", "daily/b"])

    def test_an_empty_prefix_has_no_contents(self) -> None:
        self.assertEqual(parse_listing('{"KeyCount": "0"}\n0.09(s) elapsed'), [])

    def test_output_without_json_is_an_error_not_an_empty_listing(self) -> None:
        with self.assertRaises(OffsiteError):
            parse_listing("Error: connection reset")

    def test_error_summaries_keep_codes_and_drop_request_detail(self) -> None:
        out = ("Error: operation error GetObject\nHttp Status Code: 403.\n"
               "Error Code: AccessDenied.\nRequest Id: ABC.\nEC: 0003-00000201.\n"
               "Request Endpoint: GET https://bucket.oss/daily/x\n")
        summary = summarize_error(out)
        self.assertIn("403", summary)
        self.assertIn("AccessDenied", summary)
        self.assertNotIn("https://", summary)
        self.assertNotIn("Request Id", summary)


CAL = committed_calendar()


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class Keys(unittest.TestCase):
    """Scheduled-stop design §6: keyed by the session the dump follows."""

    def test_reruns_after_the_close_target_the_same_key(self) -> None:
        late = MONDAY.replace(hour=23, minute=59)
        self.assertEqual(destination_keys(MONDAY, CAL), destination_keys(late, CAL))
        self.assertEqual(destination_keys(MONDAY, CAL), ["daily/2026-09-21.dump.age"])

    def test_a_dump_taken_during_a_session_waits_for_the_post_close_one(self) -> None:
        for at in ("2026-09-21T14:00", "2026-09-21T20:14"):  # 10:00 ET; 16:14 ET, options open
            with self.subTest(at):
                self.assertEqual(destination_keys(utc(at), CAL), [])

    def test_a_morning_dump_after_a_stopped_night_belongs_to_the_previous_session(self) -> None:
        # Monday 08:35 ET, the first dump after a weekend stop: Friday's session.
        self.assertEqual(
            destination_keys(utc("2026-09-28T12:35"), CAL),
            ["daily/2026-09-25.dump.age", "weekly/2026-09-25.dump.age"],
        )

    def test_the_weekly_copy_is_the_weeks_last_session(self) -> None:
        self.assertEqual(destination_keys(FRIDAY, CAL)[1], "weekly/2026-09-25.dump.age")
        self.assertEqual(len(destination_keys(MONDAY, CAL)), 1)
        # 3 July 2026 is a holiday, so Thursday 2 July is the week's last session.
        self.assertIn("weekly/2026-07-02.dump.age", destination_keys(utc("2026-07-02T21:05"), CAL))

    def test_an_early_close_is_honoured(self) -> None:
        # 27 Nov 2026 closes at 13:00 ET (18:00 UTC); 13:20 ET is post-close.
        self.assertEqual(destination_keys(utc("2026-11-27T18:10"), CAL), [])
        self.assertIn("daily/2026-11-27.dump.age", destination_keys(utc("2026-11-27T18:20"), CAL))

    def test_past_the_calendar_the_utc_date_rule_applies(self) -> None:
        sunday_2028 = utc("2028-01-02T20:05")
        self.assertEqual(
            destination_keys(sunday_2028, CAL),
            ["daily/2028-01-02.dump.age", "weekly/2028-01-02.dump.age"],
        )

    def test_without_a_calendar_the_utc_date_rule_applies(self) -> None:
        self.assertEqual(destination_keys(MONDAY), ["daily/2026-09-21.dump.age"])


class Config(unittest.TestCase):
    def test_a_key_based_mode_is_refused(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write("OSS_MODE=AK\nOSS_BUCKET=b\nOSS_REGION=r\nOSS_ENDPOINT=e\n")
        try:
            with self.assertRaisesRegex(OffsiteError, "only EcsRamRole"):
                OssConfig.from_env_file(handle.name)
        finally:
            Path(handle.name).unlink()


if __name__ == "__main__":
    unittest.main()
