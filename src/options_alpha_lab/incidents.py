"""List and resolve durable incidents: the operator's way to close one.

Most incidents need a person to decide what happened. Until this existed, the
only way to close one was hand-written SQL against the production database,
which records nothing about who decided or why. This closes one incident at a
time, by exact id, only while it is still open, and refuses to do so without a
reason, which is kept with the incident (see `LifecycleStore.resolve_incident`).

Usage, on the host, with the worker's environment:

    python -m options_alpha_lab.incidents list
    python -m options_alpha_lab.incidents resolve <id> --reason "why this is closed"

Incidents that heal on their own, such as a broker that became reachable again,
are closed by reconciliation itself and should not need this.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from .execution.lifecycle import LifecycleStore


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m options_alpha_lab.incidents")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show every open incident")
    resolve = commands.add_parser("resolve", help="close one open incident")
    resolve.add_argument("incident_id")
    resolve.add_argument("--reason", required=True, help="why it is closed; kept with it")
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    from sqlalchemy import create_engine

    store = LifecycleStore(create_engine(url))

    if args.command == "list":
        open_now = sorted(store.open_incidents(), key=lambda r: r.opened_at)
        for record in open_now:
            first_line = record.detail.splitlines()[0] if record.detail else ""
            print(f"{record.incident_id}  {record.opened_at.isoformat(timespec='seconds')}  "
                  f"{record.severity:<6} {record.kind:<28} {first_line[:100]}")
        print(f"{len(open_now)} open incident(s)")
        return 0

    try:
        closed = store.resolve_incident(args.incident_id, reason=args.reason)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not closed:
        print(f"{args.incident_id}: not an open incident; nothing changed", file=sys.stderr)
        return 1
    print(f"{args.incident_id}: resolved")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
