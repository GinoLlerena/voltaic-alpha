"""Take a fresh verified dump and upload it, encrypted, as the pre-resize copy.

Runs ON THE INSTANCE with the backup env loaded, after the hourly backup unit has
just run. Uses the uploader role: it can write daily/, and the operator copies the
object into anchor/ server-side. Sent by scripts/resize_trial.py.
"""

import hashlib
import json
import pathlib
import subprocess
from datetime import UTC, datetime

from options_alpha_lab.offsite import (
    Oss,
    OssConfig,
    _read_recipient,
    subprocess_runner,
    verify_source,
)

now = datetime.now(UTC)
src = verify_source(json.loads(pathlib.Path("/var/lib/options-alpha/backup.json").read_text()), now)
key = f"daily/{src.at.strftime('%Y-%m-%dT%H%MZ')}-preresize.dump.age"
staged = pathlib.Path("/run/options-alpha-backup-offsite-anchor.age")
try:
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            "/usr/bin/age",
            "-r",
            _read_recipient("/etc/options-alpha-backup.pub"),
            "-o",
            str(staged),
            str(src.path),
        ],
        check=True,
    )
    sha = hashlib.sha256(src.path.read_bytes()).hexdigest()
    oss = Oss(OssConfig.from_env_file("/etc/options-alpha-backup.env"), subprocess_runner)
    oss.put(
        key,
        staged,
        {
            "dump-at": src.at.isoformat(),
            "dump-sha256": sha,
            "alembic-revision": src.alembic_revision,
            "tables": str(src.tables),
            "rows-restored": str(src.rows_restored),
            "purpose": "pre-resize",
        },
    )
    landed = oss.exists(key)
    assert landed is not None and landed.size == staged.stat().st_size, (
        "pre-resize copy did not land intact"
    )
    print(
        json.dumps(
            {
                # The host's env file is the source of truth for the bucket, so the
                # operator script - in a public repository - never has to name it.
                "bucket": oss.config.bucket,
                "key": key,
                "bytes": landed.size,
                "dump_at": src.at.isoformat(),
                "dump_sha256": sha,
                "tables": src.tables,
                "rows_restored": src.rows_restored,
                "alembic": src.alembic_revision,
            }
        )
    )
finally:
    staged.unlink(missing_ok=True)
