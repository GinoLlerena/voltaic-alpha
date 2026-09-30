#!/usr/bin/env python3
"""The owner's manual session lock (scheduled-stop design §4).

    python3 scripts/session.py start --hours 4 --reason dev   # lock; start the server if stopped
    python3 scripts/session.py extend --hours 2               # lock until now + 2 h
    python3 scripts/session.py end                            # expire the lock now
    python3 scripts/session.py status

Uses the operator's own `aliyun` profile through `resize_trial`'s redacting
layer. Times are UTC. A lock never reaches more than 24 hours ahead: the
scheduler would treat a longer one as invalid (held, alerted, rewritten to 24 h).
`end` sets the expiry to now rather than deleting the tag, so ending and
forgetting follow one path: after a 15-minute grace, the next tick stops the
server if it is outside market hours and ready.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import resize_trial as rt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from options_alpha_lab.calendar import committed_calendar  # noqa: E402
from options_alpha_lab.scheduler import (  # noqa: E402
    LOCK_REASON_TAG,
    LOCK_UNTIL_TAG,
    MAX_LOCK,
    in_run_window,
    read_lock,
)


def stamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def tags() -> dict[str, str]:
    inst = rt.instance()
    return {t["TagKey"]: t.get("TagValue", "") for t in inst.get("Tags", {}).get("Tag", [])}


def set_lock(until: datetime, reason: str) -> None:
    rt.aliyun(
        "ecs", "TagResources", "--RegionId", rt.REGION, "--ResourceType", "instance",
        "--ResourceId.1", rt.INSTANCE,
        "--Tag.1.Key", LOCK_UNTIL_TAG, "--Tag.1.Value", stamp(until),
        "--Tag.2.Key", LOCK_REASON_TAG, "--Tag.2.Value", reason,
    )


def hours(value: str) -> timedelta:
    span = timedelta(hours=float(value))
    if not timedelta(0) < span <= MAX_LOCK:
        cap = MAX_LOCK.total_seconds() / 3600
        raise argparse.ArgumentTypeError(f"between 0 and {cap:.0f} hours")
    return span


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start")
    start.add_argument("--hours", type=hours, required=True)
    start.add_argument("--reason", choices=("dev", "demo"), default="dev")
    extend = sub.add_parser("extend")
    extend.add_argument("--hours", type=hours, required=True)
    sub.add_parser("end")
    sub.add_parser("status")
    args = parser.parse_args()
    now = datetime.now(UTC)

    try:
        if args.cmd == "start":
            set_lock(now + args.hours, args.reason)
            print(f"locked until {stamp(now + args.hours)} ({args.reason})")
            if rt.instance()["Status"] == "Stopped":
                rt.aliyun("ecs", "StartInstance", "--InstanceId", rt.INSTANCE)
                print("StartInstance sent; the server is up in about 2 minutes")
        elif args.cmd == "extend":
            reason = tags().get(LOCK_REASON_TAG, "dev")
            set_lock(now + args.hours, reason)
            print(f"locked until {stamp(now + args.hours)} ({reason})")
        elif args.cmd == "end":
            set_lock(now, tags().get(LOCK_REASON_TAG, "dev"))
            print("lock expired now; after the 15-minute grace the scheduler may stop the server")
        inst = rt.instance()
        current = {t["TagKey"]: t.get("TagValue", "") for t in inst.get("Tags", {}).get("Tag", [])}
        lock = read_lock(current, now)
        calendar, covered = committed_calendar()
        print(json.dumps({
            "instance": inst["Status"],
            "lock": lock.state.value,
            "lock_until": lock.until.isoformat() if lock.until else None,
            "lock_reason": lock.reason or None,
            "lock_problem": lock.problem or None,
            "inside_market_run_window": in_run_window(calendar, now, covered),
        }, indent=1))
    except rt.Stop as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
