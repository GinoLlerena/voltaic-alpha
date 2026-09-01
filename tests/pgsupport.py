"""Point a test harness at PostgreSQL instead of SQLite, when asked.

Section 8 of `SRC-TASK-1` requires the acceptance suite to pass against a
production-shaped PostgreSQL as well as SQLite, and the reason is specific:
Task 1 is a change about row order and locking, and those are exactly the two
things the two engines do not agree about. A suite that only ever ran on SQLite
would be silent on the property it exists to check.

Set `OPTIONS_ALPHA_TEST_DATABASE_URL` to a PostgreSQL URL and every harness that
calls `database_url` gets its own fresh database. Unset - which is the default,
and what CI and the validation gate run - nothing changes and the suite stays
on SQLite with no server required.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

ENV = "OPTIONS_ALPHA_TEST_DATABASE_URL"


def targeting_postgres() -> bool:
    return bool(os.environ.get(ENV))


def database_url(sqlite_path: Path | str) -> str:
    """A URL for one test: SQLite by default, else a fresh PostgreSQL database.

    A database per test rather than a shared one with truncation between: these
    tests assert on row *order*, and a table reused across tests carries page
    layout from whatever ran before it. That is precisely the hidden coupling
    the deterministic ordering is meant to remove, so the harness must not
    reintroduce it.
    """
    base = os.environ.get(ENV)
    if not base:
        return f"sqlite+pysqlite:///{sqlite_path}"

    name = f"t_{uuid.uuid4().hex[:16]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    head, _, _ = base.rpartition("/")
    return f"{head}/{name}"


# Cleanup is the container, not this module: `docker compose down -v` discards
# every per-test database at once. Dropping them individually from a teardown
# would need each test's connections closed first, and a teardown that hangs on
# a stray connection is worse than a disposable volume.
