#!/usr/bin/env python3
"""Deploy everything on this checkout to the host, in one command.

    python3 scripts/deploy_all.py            # dry run: what differs, what would run
    python3 scripts/deploy_all.py --apply    # do it

It adds no deploy logic of its own. It reads what differs between this
checkout and the host, then runs the existing commands in order, each with its
own checks and refusals intact:

  1. `session.py start`     only when the server is stopped, or is running
                            outside market hours with no lock (the scheduler
                            would otherwise stop it mid-deploy)
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
`ship_host.py`; this script says so up front instead of failing at step 2.
`--ignore-window` is passed through for the rare case that is intended.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

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


@dataclass
class Steps:
    ship: list[str] = field(default_factory=list)
    """Arguments for `ship_host.py`; empty when the host already matches."""
    worker: bool = False
    """The worker will be restarted (directly, or by the migration)."""
    blocked: str | None = None
    """Why this cannot run now, in the terms the operator can act on."""


def steps_for(plan: sh.Plan, window: str | None, *, ignore_window: bool = False) -> Steps:
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
            f"this deploy restarts the worker, and {window}. "
            "Run it after 17:15 ET, or on a weekend."
        )
    if worker and ignore_window:
        args.append("--ignore-window")
    return Steps(ship=args, worker=worker, blocked=blocked)


def needs_session(status: dict[str, object]) -> bool:
    """Whether the scheduler could stop the server under this deploy."""
    if status.get("instance") != "Running":
        return True
    return not status.get("inside_market_run_window") and status.get("lock") != "active"


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

    window = dr.market_window_reason(datetime.now(UTC))
    opened = False
    try:
        status = session_status()
        session = needs_session(status)
        print(f"server: {status.get('instance')}, lock {status.get('lock')}, "
              f"{'inside' if status.get('inside_market_run_window') else 'outside'} market hours")
        if status.get("instance") != "Running" and not args.apply:
            print("\nThe server is stopped, so the differences cannot be read in a dry run.")
            print(f"--apply would: open a {SESSION_HOURS}-hour session (starts the server), "
                  "deploy what differs, deploy the UI, end the session.")
            return 0
        if session and args.apply:
            if run("session.py", "start", "--hours", SESSION_HOURS, "--reason", "dev") != 0:
                return 1
            opened = True

        plan = wait_for_host()
        sh.report(plan)
        steps = steps_for(plan, window, ignore_window=args.ignore_window)
        ui = not args.skip_ui
        ui_blocked = ui and bool(window) and not args.ignore_window

        print("\nplan:")
        if session:
            print(f"  1. open a {SESSION_HOURS}-hour session, so the scheduler "
                  "does not stop the server")
        print("  2. ship_host.py " + (" ".join(steps.ship) or "(nothing to ship)"))
        print("  3. " + ("deploy_react.py deploy --apply --verify-on-port-80"
                         if ui else "(UI skipped)"))
        print("  4. confirm the host matches" + ("; end the session" if session else ""))
        if steps.blocked:
            print(f"\nNOT NOW: {steps.blocked}", file=sys.stderr)
            return 2
        if ui_blocked:
            print(f"\nNOT NOW: the UI deploy waits for the close ({window}). "
                  "Re-run after 17:15 ET, or pass --skip-ui to ship only the host code now.",
                  file=sys.stderr)
            return 2
        if not args.apply:
            print("\nDry run. Re-run with --apply to deploy.")
            return 0

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
