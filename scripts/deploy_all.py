#!/usr/bin/env python3
"""Deploy everything on this checkout to the host, in one command.

    python3 scripts/deploy_all.py            # dry run: what differs, what would run
    python3 scripts/deploy_all.py --apply    # do it

It adds no deploy logic of its own. It reads what differs between this
checkout and the host, then runs the existing commands in order, each with its
own checks and refusals intact:

  1. `session.py start`     whenever no session lock is held, so the scheduler
                            cannot stop the server mid-deploy - including at
                            17:15-17:30 ET, as its run window closes
  2. `ship_host.py --apply` with the flags the differences call for
  3. `deploy_react.py deploy --apply --verify-on-port-80`   (skip: --skip-ui)
  4. `ship_host.py`         a dry run, to show the host now matches
  5. `session.py end`       only if step 1 opened the session

Which flags step 2 gets is decided here, by `steps_for`:

  - `requirements.txt` differs        -> `--install-deps`, and every service restarts
  - the schema is behind              -> `--migrate` (which restarts the worker itself)
  - source the worker runs differs    -> `--restart-worker`
  - any source differs                -> restart the API and the dashboard

A worker restart or a migration is refused during the trading day by
`ship_host.py`; this script says so up front, with the time it may run, in New
York time and on this computer's clock, instead of failing at step 2.
`--ignore-window` is passed through for the rare case that is intended.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import deploy_react as dr
import resize_trial as rt
import ship_host as sh

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PACKAGE = "src/options_alpha_lab/"
#: Source only the read-only surfaces import; the worker never loads it.
READ_ONLY = (f"{PACKAGE}api/", f"{PACKAGE}presentation/")
API, DASHBOARD = "options-alpha-api", "options-alpha"
SESSION_HOURS = "1"
#: A lock with less than this left is extended: a full deploy takes about ten minutes.
DEPLOY_COVER = timedelta(minutes=30)


@dataclass
class Steps:
    ship: list[str] = field(default_factory=list)
    """Arguments for `ship_host.py`; empty when the host already matches."""
    worker: bool = False
    """The worker will be restarted (directly, or by the migration)."""
    blocked: str | None = None
    """Why this cannot run now, in the terms the operator can act on."""


def steps_for(
    plan: sh.Plan, window: str | None, *, ignore_window: bool = False, after: str = "17:15 ET",
) -> Steps:
    """The `ship_host.py` invocation a set of differences calls for."""
    if not (plan.changed or plan.units or plan.needs_migration):
        return Steps()
    source = [f for f in plan.changed if f.startswith("src/")]
    worker_source = [f for f in source if not f.startswith(READ_ONLY)]
    args = ["--apply"]
    worker = bool(worker_source) or plan.deps_changed or plan.needs_migration
    if plan.deps_changed:
        args.append("--install-deps")
    if plan.needs_migration:
        args.append("--migrate")
    elif worker:
        args.append("--restart-worker")
    if source or plan.deps_changed:
        args += ["--restart", API, "--restart", DASHBOARD]
    blocked = None
    if worker and window and not ignore_window:
        blocked = (
            f"this deploy restarts the trading worker, and the market day is not over "
            f"({window}).\nRUN IT AT OR AFTER {after}. Any later time tonight works, "
            "and so does any time on a weekend."
        )
    if worker and ignore_window:
        args.append("--ignore-window")
    return Steps(ship=args, worker=worker, blocked=blocked)


def session_action(status: dict[str, object], now: datetime) -> str | None:
    """How to keep the scheduler from stopping the server under this deploy.

    `open`: no lock is held, so take one and end it afterwards. That includes a
    server running in market hours: a deploy started at 17:15 ET would otherwise
    still be running when the run window closes at 17:30 and the scheduler
    stops the server. `extend`: the owner's own lock is about to expire; push
    it out and leave ending it to them. `None`: their lock already covers it.
    """
    if status.get("instance") != "Running" or status.get("lock") != "active":
        return "open"
    until = status.get("lock_until")
    if isinstance(until, str) and datetime.fromisoformat(until) - now < DEPLOY_COVER:
        return "extend"
    return None


def clear_from(now: datetime) -> datetime | None:
    """When the trading-day refusal lifts today, or None if nothing is refused now."""
    if dr.market_window_reason(now) is None:
        return None
    et = now.astimezone(ZoneInfo("America/New_York"))
    return et.replace(hour=17, minute=15, second=0, microsecond=0)


def when(at: datetime) -> str:
    """A time the owner can act on: New York, and this machine's own clock."""
    local = at.astimezone()
    return f"{at:%H:%M} ET today ({local:%H:%M} on this computer's clock, {local:%Z})"


def run(*argv: str) -> int:
    print(f"\n$ python3 scripts/{' '.join(argv)}", flush=True)
    return subprocess.run(  # noqa: S603 - fixed scripts, our own arguments
        [sys.executable, str(SCRIPTS / argv[0]), *argv[1:]], cwd=ROOT, check=False
    ).returncode


def session_status() -> dict[str, object]:
    done = subprocess.run(  # noqa: S603 - fixed script
        [sys.executable, str(SCRIPTS / "session.py"), "status"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        raise rt.Stop("could not read the server's status (session.py status failed)")
    loaded: dict[str, object] = json.loads(done.stdout[done.stdout.index("{"):])
    return loaded


def wait_for_host(seconds: int = 420) -> sh.Plan:
    """The first plan the host answers with; a booting server needs a few minutes."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            return sh.make_plan()
        except rt.Stop:
            if time.monotonic() > deadline:
                raise
            print("  waiting for the server to answer...", flush=True)
            time.sleep(20)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="deploy; default is a dry run")
    parser.add_argument("--skip-ui", action="store_true", help="leave the React build alone")
    parser.add_argument("--ignore-window", action="store_true",
                        help="allow a worker restart and the UI deploy during the trading day")
    args = parser.parse_args()

    now = datetime.now(UTC)
    window = dr.market_window_reason(now)
    clear = clear_from(now)
    after = when(clear) if clear else "now"
    opened = False
    try:
        status = session_status()
        session = session_action(status, now)
        print(f"server: {status.get('instance')}, lock {status.get('lock')}, "
              f"{'inside' if status.get('inside_market_run_window') else 'outside'} market hours")
        if status.get("instance") != "Running" and not args.apply:
            print("\nThe server is stopped, so the differences cannot be read in a dry run.")
            print(f"--apply would: open a {SESSION_HOURS}-hour session (starts the server), "
                  "deploy what differs, deploy the UI, end the session.")
            return 0
        # A stopped server has to be started before its differences can be read,
        # and starting it during the trading day is what the scheduler does anyway.
        if status.get("instance") != "Running":
            if run("session.py", "start", "--hours", SESSION_HOURS, "--reason", "dev") != 0:
                return 1
            opened = True

        plan = wait_for_host()
        sh.report(plan)
        steps = steps_for(plan, window, ignore_window=args.ignore_window, after=after)
        ui = not args.skip_ui
        ui_blocked = ui and bool(window) and not args.ignore_window

        print("\nplan:")
        if session:
            print(f"  1. {session} a {SESSION_HOURS}-hour session, so the scheduler "
                  "does not stop the server mid-deploy")
        print("  2. ship_host.py " + (" ".join(steps.ship) or "(nothing to ship)"))
        print("  3. " + ("deploy_react.py deploy --apply --verify-on-port-80"
                         if ui else "(UI skipped)"))
        print("  4. confirm the host matches"
              + ("; end the session" if session == "open" else ""))
        if steps.blocked:
            print(f"\nNOT NOW: {steps.blocked}", file=sys.stderr)
            return 2
        if ui_blocked:
            print(f"\nNOT NOW: the UI deploy waits for the market day to end ({window}).\n"
                  f"RUN IT AT OR AFTER {after}, or pass --skip-ui to ship only the "
                  "host code now.", file=sys.stderr)
            return 2
        if not args.apply:
            print("\nDry run. Nothing is refused right now: re-run with --apply to deploy.")
            return 0
        # Held from here to the end: nothing was refused, so the deploy will run.
        if session == "extend":
            if run("session.py", "extend", "--hours", SESSION_HOURS) != 0:
                return 1
        elif session == "open" and not opened:
            if run("session.py", "start", "--hours", SESSION_HOURS, "--reason", "dev") != 0:
                return 1
            opened = True

        if steps.ship and run("ship_host.py", *steps.ship) != 0:
            print("\nSTOPPED: ship_host.py failed; the UI was not deployed.", file=sys.stderr)
            return 1
        if ui:
            extra = ["--ignore-window"] if args.ignore_window else []
            if run("deploy_react.py", "deploy", "--apply", "--verify-on-port-80", *extra) != 0:
                print("\nSTOPPED: the UI deploy failed and reverted itself (port 80 is on "
                      "Streamlit). The host code from step 2 is in place.", file=sys.stderr)
                return 1
        if run("ship_host.py") != 0:
            return 1
        print("\nDEPLOYED.")
        return 0
    except rt.Stop as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1
    finally:
        if opened:
            run("session.py", "end")


if __name__ == "__main__":
    sys.exit(main())
