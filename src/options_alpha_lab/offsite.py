"""Put the verified hourly dump somewhere the host cannot take down with it.

`options-alpha-backup.service` already dumps the database every hour and proves
each dump restores. Every one of those dumps sits on the same disk as the
database it protects, which makes it a fast-restore convenience rather than a
backup. This module is the other half: it encrypts the newest *verified* dump
and uploads it to OSS, once a day, with a second copy under `weekly/` on
Sundays. Plan: docs/implementation/options_alpha_oss_backup_implementation_v0_1.md
sections 6 and 7.

Rules it keeps, each of which is a test:

* It never runs `pg_dump`. A second dump would be unverified, would double the
  load and would race the hourly job. It uploads the exact file that
  `backup.json` names, and only when that record says the file was restored
  and checked (§6.1).
* It refuses loudly rather than uploading something it cannot vouch for: an
  unverified record, a stale one, or a file whose size no longer matches.
* It uploads ciphertext only. The host holds the `age` *recipient* and never
  the identity, so a compromised host can add backups but cannot read them.
* Each destination key is checked on its own (§7.1). A run that finds `daily/`
  present and `weekly/` missing uploads `weekly/` alone, instead of seeing the
  daily object and concluding the day is done.
* Keys are derived from the dump's date, so a rerun targets the same key.
  There is no forbid-overwrite on a versioned bucket (§0.6, finding 2); what
  stops a rewrite is that the key is checked first and is never re-uploaded.

It authenticates as the ECS instance RAM role, so no credential appears on any
command line or in any file this module reads. Every run leaves a status record
that the watchdog reads, which is how a failure here becomes a durable incident
rather than a line in a journal nobody opens (§7.3).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Must equal `watchdog.DEFAULT_BACKUP_FILE`; a test holds the two together.
#: Restated rather than imported because importing the watchdog would pull the
#: worker and the ORM into a unit that deliberately holds no database access.
DEFAULT_BACKUP_FILE = "/var/lib/options-alpha/backup.json"
DEFAULT_STATUS_FILE = "/var/lib/options-alpha/offsite.json"
DEFAULT_ENV_FILE = "/etc/options-alpha-backup.env"
DEFAULT_RECIPIENT_FILE = "/etc/options-alpha-backup.pub"
DEFAULT_OSSUTIL = "/usr/local/bin/ossutil"
DEFAULT_AGE = "/usr/bin/age"
#: The unit's own RuntimeDirectory. Never /run/options-alpha, which belongs to
#: the worker unit and is removed whenever the worker stops (§6.3).
DEFAULT_STAGING_DIR = "/run/options-alpha-backup-offsite"

#: Same bound the watchdog applies to the hourly job: two missed runs. A record
#: older than this is a stale record, not this cycle's dump.
MAX_DUMP_AGE_SECONDS = 7800
#: Sunday, in `datetime.weekday()` numbering. The plan names no day. Sunday's
#: dump is taken with the market closed and so carries the whole trading week.
WEEKLY_WEEKDAY = 6
#: §7.2: one daily cycle plus margin. With a run every four hours, roughly six
#: attempts have failed before this fires.
MAX_OFFSITE_AGE_SECONDS = 30 * 3600
#: The timer fires every four hours and every run writes a status record, even
#: one that uploads nothing. Six hours without one means the job is not running.
MAX_STATUS_AGE_SECONDS = 6 * 3600

#: argv -> (exit status, combined output). Injected so tests never touch OSS.
Runner = Callable[[Sequence[str]], tuple[int, str]]


class OffsiteError(Exception):
    """A reason to upload nothing. The message ends up in the status record."""


@dataclass(frozen=True)
class OssConfig:
    bucket: str
    region: str
    endpoint: str

    @classmethod
    def from_env_file(cls, path: str | Path) -> OssConfig:
        values = read_env_file(path)
        missing = [k for k in ("OSS_BUCKET", "OSS_REGION", "OSS_ENDPOINT") if not values.get(k)]
        if missing:
            raise OffsiteError(f"{path} does not set {', '.join(missing)}")
        mode = values.get("OSS_MODE", "EcsRamRole")
        if mode != "EcsRamRole":
            # The design keeps every long-lived key off the host. A file that
            # asks for another mode has drifted from it; refuse rather than
            # quietly authenticate some other way.
            raise OffsiteError(f"{path} sets OSS_MODE={mode!r}; only EcsRamRole is supported")
        return cls(values["OSS_BUCKET"], values["OSS_REGION"], values["OSS_ENDPOINT"])


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    last_modified: datetime


@dataclass(frozen=True)
class SourceDump:
    path: Path
    bytes: int
    at: datetime
    alembic_revision: str
    tables: int
    rows_restored: int


def read_env_file(path: str | Path) -> dict[str, str]:
    """Parse the KEY=VALUE lines systemd would read. Comments and blanks skipped."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise OffsiteError(f"cannot read {path}: {exc.strerror or exc}") from exc
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def subprocess_runner(argv: Sequence[str]) -> tuple[int, str]:
    completed = subprocess.run(  # noqa: S603 - fixed binaries, no shell, no credentials in argv
        list(argv), capture_output=True, text=True, timeout=600, check=False,
    )
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def _utc(stamp: datetime) -> datetime:
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def verify_source(status: dict[str, Any] | None, now: datetime) -> SourceDump:
    """Accept only the dump the hourly job restored and checked, and only now (§6.1)."""
    if status is None:
        raise OffsiteError("backup.json is missing or unreadable")
    if status.get("verified") is not True:
        raise OffsiteError(
            f"latest dump is not verified: {status.get('detail') or 'no detail'}"
        )
    raw_at, raw_path, raw_bytes = status.get("at"), status.get("path"), status.get("bytes")
    if (
        not isinstance(raw_at, str)
        or not isinstance(raw_path, str)
        or not isinstance(raw_bytes, int)
    ):
        raise OffsiteError("backup.json lacks at, path or bytes")
    try:
        at = _utc(datetime.fromisoformat(raw_at.replace("Z", "+00:00")))
    except ValueError as exc:
        raise OffsiteError(f"unparseable dump timestamp {raw_at!r}") from exc
    age = (now - at).total_seconds()
    if age > MAX_DUMP_AGE_SECONDS:
        raise OffsiteError(
            f"latest verified dump is {age / 3600:.1f}h old "
            f"(limit {MAX_DUMP_AGE_SECONDS / 3600:.1f}h); refusing a stale record"
        )
    path = Path(raw_path)
    try:
        actual = path.stat().st_size
    except OSError as exc:
        raise OffsiteError(f"dump named by backup.json is gone: {path}") from exc
    if actual != raw_bytes:
        raise OffsiteError(
            f"{path} is {actual} bytes but backup.json recorded {raw_bytes}; "
            "refusing a file that changed after it was verified"
        )
    return SourceDump(
        path=path, bytes=raw_bytes, at=at,
        alembic_revision=str(status.get("alembic_revision", "")),
        tables=int(status.get("tables", 0)),
        rows_restored=int(status.get("rows_restored", 0)),
    )


def destination_keys(dump_at: datetime) -> list[str]:
    """`daily/` always; `weekly/` too when the dump was taken on the weekly day."""
    day = _utc(dump_at).date()
    keys = [f"daily/{day.isoformat()}.dump.age"]
    if day.weekday() == WEEKLY_WEEKDAY:
        keys.append(f"weekly/{day.isoformat()}.dump.age")
    return keys


def parse_listing(output: str) -> list[StoredObject]:
    """Read `ossutil api list-objects-v2 --output-format json`.

    Three quirks, all observed on 2.4.0: one match arrives as a bare object and
    several as a list; numbers arrive as strings; and a timing line such as
    `0.07(s) elapsed` follows the JSON.
    """
    start, end = output.find("{"), output.rfind("}")
    if start < 0 or end < start:
        raise OffsiteError("listing returned no JSON")
    try:
        document = json.loads(output[start:end + 1])
    except ValueError as exc:
        raise OffsiteError("listing returned malformed JSON") from exc
    contents = document.get("Contents") or []
    if isinstance(contents, dict):
        contents = [contents]
    objects: list[StoredObject] = []
    for item in contents:
        stamp = datetime.fromisoformat(str(item["LastModified"]).replace("Z", "+00:00"))
        objects.append(StoredObject(str(item["Key"]), int(item["Size"]), _utc(stamp)))
    return objects


def summarize_error(output: str) -> str:
    """Keep the status and error codes; drop everything else.

    ossutil's error text includes request endpoints and, for some failures,
    fragments of the request. Only the codes are needed to act on a failure, so
    only the codes are kept, which keeps the status file safe to read by anyone.
    """
    wanted = ("Http Status Code", "Error Code", "EC:")
    lines = [line.strip().rstrip(".") for line in output.splitlines()
             if line.strip().startswith(wanted)]
    if lines:
        return "; ".join(lines)
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    return first[:160] or "no output"


class Oss:
    def __init__(self, config: OssConfig, runner: Runner, ossutil: str = DEFAULT_OSSUTIL):
        self.config, self.runner, self.ossutil = config, runner, ossutil

    def _base(self) -> list[str]:
        return [self.ossutil, "--mode", "EcsRamRole", "--region", self.config.region,
                "-e", self.config.endpoint]

    def list(self, prefix: str) -> list[StoredObject]:
        status, output = self.runner([
            *self._base(), "api", "list-objects-v2", "--bucket", self.config.bucket,
            "--prefix", prefix, "--max-keys", "1000", "--output-format", "json",
        ])
        if status != 0:
            raise OffsiteError(f"listing {prefix} failed: {summarize_error(output)}")
        return parse_listing(output)

    def exists(self, key: str) -> StoredObject | None:
        return next((o for o in self.list(key) if o.key == key), None)

    def put(self, key: str, source: Path, metadata: dict[str, str]) -> None:
        argv = [*self._base(), "api", "put-object", "--bucket", self.config.bucket,
                "--key", key, "--body", f"file://{source}"]
        for name, value in metadata.items():
            argv += ["--metadata", f"{name}={value}"]
        status, output = self.runner(argv)
        if status != 0:
            raise OffsiteError(f"upload of {key} failed: {summarize_error(output)}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_recipient(path: str | Path) -> str:
    try:
        recipient = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise OffsiteError(f"cannot read the age recipient {path}") from exc
    if not recipient.startswith("age1") or any(c.isspace() for c in recipient):
        # Not an X25519 recipient - and, crucially, not an identity
        # (AGE-SECRET-KEY-...), which must never be on this host at all.
        raise OffsiteError(f"{path} does not hold a single age recipient")
    return recipient


def run_offsite(
    *,
    config: OssConfig,
    runner: Runner,
    now: datetime,
    backup_file: str = DEFAULT_BACKUP_FILE,
    recipient_file: str = DEFAULT_RECIPIENT_FILE,
    staging_dir: str = DEFAULT_STAGING_DIR,
    ossutil: str = DEFAULT_OSSUTIL,
    age: str = DEFAULT_AGE,
) -> dict[str, Any]:
    """One idempotent pass. Returns the status record; raises OffsiteError to refuse."""
    try:
        status = json.loads(Path(backup_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = None
    source = verify_source(status if isinstance(status, dict) else None, now)
    recipient = _read_recipient(recipient_file)
    oss = Oss(config, runner, ossutil)

    keys = destination_keys(source.at)
    missing = [key for key in keys if oss.exists(key) is None]
    record: dict[str, Any] = {
        "dump_at": source.at.isoformat(), "dump_path": str(source.path),
        "keys": keys, "uploaded": [],
    }
    if missing:
        staged = Path(staging_dir) / f"{source.at.date().isoformat()}.dump.age"
        staged.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            code, output = runner([age, "-r", recipient, "-o", str(staged), str(source.path)])
            if code != 0 or not staged.exists():
                raise OffsiteError(f"age encryption failed: {summarize_error(output)}")
            ciphertext_bytes = staged.stat().st_size
            metadata = {
                "dump-at": source.at.isoformat(),
                "dump-sha256": _sha256(source.path),
                "alembic-revision": source.alembic_revision,
                "tables": str(source.tables),
                "rows-restored": str(source.rows_restored),
            }
            # Encrypt once, upload that ciphertext to every missing key (§6.3).
            for key in missing:
                oss.put(key, staged, metadata)
                landed = oss.exists(key)
                if landed is None or landed.size != ciphertext_bytes:
                    raise OffsiteError(
                        f"{key} did not land intact: expected {ciphertext_bytes} bytes, "
                        f"found {landed.size if landed else 'nothing'}"
                    )
                record["uploaded"].append(key)
            record["ciphertext_bytes"] = ciphertext_bytes
        finally:
            staged.unlink(missing_ok=True)

    daily = oss.list("daily/")
    newest = max((o.last_modified for o in daily), default=None)
    record["newest_daily_at"] = newest.isoformat() if newest else None
    return record


def write_status(path: str | Path, record: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def main(argv: list[str] | None = None) -> int:
    """Exit 0 when every destination holds today's dump, 1 otherwise."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Encrypt the verified dump and upload it off-host."
    )
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--backup-file", default=DEFAULT_BACKUP_FILE)
    parser.add_argument("--status-file", default=DEFAULT_STATUS_FILE)
    parser.add_argument("--recipient-file", default=DEFAULT_RECIPIENT_FILE)
    parser.add_argument("--staging-dir",
                        default=os.environ.get("RUNTIME_DIRECTORY", DEFAULT_STAGING_DIR))
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
    base: dict[str, Any] = {"checked_at": now.isoformat()}
    try:
        record = run_offsite(
            config=OssConfig.from_env_file(args.env_file), runner=subprocess_runner, now=now,
            backup_file=args.backup_file, recipient_file=args.recipient_file,
            staging_dir=args.staging_dir,
        )
        outcome = {**base, "ok": True, **record,
                   "detail": ("uploaded " + ", ".join(record["uploaded"])) if record["uploaded"]
                   else "all destinations already hold this dump"}
    except OffsiteError as exc:
        outcome = {**base, "ok": False, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - anything unforeseen is still a failed run
        outcome = {**base, "ok": False, "detail": f"unexpected {type(exc).__name__}"}

    try:
        write_status(args.status_file, outcome)
    except OSError as exc:
        print(f"could not write {args.status_file}: {exc}", file=sys.stderr)
    print(json.dumps(outcome, indent=2))
    return 0 if outcome["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
