#!/usr/bin/env python3
"""Provision, switch and inspect the scheduled-stop function (design §9).

    python3 scripts/provision_scheduler.py apply            # create/update; new is DRY_RUN
    python3 scripts/provision_scheduler.py mode dry|live    # the only switch that lets it act
    python3 scripts/provision_scheduler.py disable|enable   # stop/start the 15-minute timer
    python3 scripts/provision_scheduler.py status           # config, timer, last decisions

Runs on the operator machine with the operator's `aliyun` profile, through
`resize_trial`'s redacting layer. Idempotent: `apply` updates what exists.
The account id is read at run time and never written to the repository.

Resources (all in ap-southeast-1):
  CloudMonitor group `oa-scheduler` -> contact group `oa-alerts` (email)
  custom-event rule: every `oa-scheduler-alert` event emails the owner
  metric rules: function errors; no timer deliveries for an hour
  Function Compute 3.0 function `oa-scheduler`, role `oa-scheduler-role`
  timer trigger `every-15-min`
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import resize_trial as rt

ROOT = Path(__file__).resolve().parents[1]
FUNCTION = "oa-scheduler"
TRIGGER = "every-15-min"
ROLE = "oa-scheduler-role"
GROUP = "oa-scheduler"
CONTACTS = "oa-alerts"
FC = "/2023-03-30/functions"
RUNTIME = "python3.12"

PACKAGE_INIT = '"""The scheduled-stop subset of options_alpha_lab, for Function Compute."""\n'


def fc(method: str, path: str, body: dict[str, Any] | None = None, check: bool = True) -> Any:
    args = ["fc", method, path, "--region", rt.REGION]
    if body is not None:
        args += ["--header", "Content-Type=application/json", "--body", json.dumps(body)]
    return rt.aliyun(*args, check=check)


def cms(action: str, *params: str, check: bool = True) -> Any:
    return rt.aliyun("cms", action, "--region", rt.REGION, *params, check=check)


def package() -> bytes:
    """handler.py, the two pure modules, the calendar, and tzdata for zoneinfo."""
    buf = io.BytesIO()
    with (
        tempfile.TemporaryDirectory() as tmp,
        zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z,
    ):
        subprocess.run(  # noqa: S603 - fixed argv
            [sys.executable, "-m", "pip", "install", "--quiet", "--target", tmp, "tzdata"],
            check=True, capture_output=True,
        )
        for path in Path(tmp).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, path.relative_to(tmp))
        z.write(ROOT / "deploy/scheduler/handler.py", "handler.py")
        z.writestr("options_alpha_lab/__init__.py", PACKAGE_INIT)
        for name in ("calendar.py", "scheduler.py", "data/nyse_sessions.json"):
            z.write(ROOT / "src/options_alpha_lab" / name, f"options_alpha_lab/{name}")
    return buf.getvalue()


def account_id() -> str:
    return str(rt.aliyun("sts", "GetCallerIdentity")["AccountId"])


def group_id() -> str:
    found = cms("DescribeMonitorGroups", "--GroupName", GROUP)
    for g in found.get("Resources", {}).get("Resource", []):
        if g.get("GroupName") == GROUP:
            return str(g["GroupId"])
    made = cms("CreateMonitorGroup", "--GroupName", GROUP, "--ContactGroups", CONTACTS)
    return str(made["GroupId"])


def apply(args: argparse.Namespace) -> int:
    gid = group_id()
    print(f"CloudMonitor group {GROUP}: {gid}")
    cms("PutCustomEventRule", "--RuleId", "oa-scheduler-alert", "--RuleName", "oa-scheduler-alert",
        "--EventName", "oa-scheduler-alert", "--GroupId", gid, "--ContactGroups", CONTACTS,
        "--Level", "CRITICAL", "--Threshold", "1", "--Period", "60",
        "--EffectiveInterval", "00:00-23:59",
        "--EmailSubject", "Options Alpha scheduler alert")
    print("custom-event rule oa-scheduler-alert -> email")

    existing = fc("GET", f"{FC}/{FUNCTION}", check=False)
    dry = "1"
    if "_error" not in existing:
        dry = str((existing.get("environmentVariables") or {}).get("DRY_RUN", "1"))
    body = {
        "runtime": RUNTIME, "handler": "handler.handler", "memorySize": 128, "timeout": 60,
        "description": "Options Alpha scheduled stop (design v0.1); decides via scheduler.decide",
        "role": f"acs:ram::{account_id()}:role/{ROLE}",
        "environmentVariables": {
            "DRY_RUN": dry, "INSTANCE_ID": rt.INSTANCE, "REGION": rt.REGION,
            "BASE_URL": "http://47.236.50.157", "CMS_GROUP_ID": gid,
        },
        "code": {"zipFile": base64.b64encode(package()).decode()},
    }
    if "_error" in existing:
        fc("POST", FC, {"functionName": FUNCTION, **body})
        print(f"function {FUNCTION} created (DRY_RUN=1)")
    else:
        fc("PUT", f"{FC}/{FUNCTION}", body)
        print(f"function {FUNCTION} updated (DRY_RUN={dry}, unchanged)")

    trigger = fc("GET", f"{FC}/{FUNCTION}/triggers/{TRIGGER}", check=False)
    config = json.dumps({"cronExpression": "@every 15m", "enable": True, "payload": ""})
    if "_error" in trigger:
        fc("POST", f"{FC}/{FUNCTION}/triggers",
           {"triggerName": TRIGGER, "triggerType": "timer", "triggerConfig": config})
        print(f"timer {TRIGGER} created")

    resources = json.dumps([{"functionName": FUNCTION, "region": rt.REGION}])
    for rule_id, metric, comparison, threshold, window in (
        ("oa-scheduler-errors", "FunctionErrors", "GreaterThanOrEqualToThreshold", "1", "300"),
        ("oa-scheduler-silent", "AsyncEventsReceived", "LessThanThreshold", "1", "3600"),
    ):
        cms("PutResourceMetricRule", "--RuleId", rule_id, "--RuleName", rule_id,
            "--Namespace", "acs_fc", "--MetricName", metric, "--Resources", resources,
            "--ContactGroups", CONTACTS, "--Interval", window,
            "--NoDataPolicy", "INSUFFICIENT_DATA",
            "--Escalations.Critical.Statistics", "Value",
            "--Escalations.Critical.ComparisonOperator", comparison,
            "--Escalations.Critical.Threshold", threshold, "--Escalations.Critical.Times", "1")
        print(f"metric rule {rule_id} -> email")
    return 0


def mode(args: argparse.Namespace) -> int:
    current = fc("GET", f"{FC}/{FUNCTION}")
    env = dict(current.get("environmentVariables") or {})
    env["DRY_RUN"] = "0" if args.to == "live" else "1"
    fc("PUT", f"{FC}/{FUNCTION}", {"environmentVariables": env})
    effect = "acts" if args.to == "live" else "decides and logs only"
    print(f"{FUNCTION}: DRY_RUN={env['DRY_RUN']} ({effect})")
    return 0


def switch(args: argparse.Namespace) -> int:
    on = args.cmd == "enable"
    config = json.dumps({"cronExpression": "@every 15m", "enable": on, "payload": ""})
    fc("PUT", f"{FC}/{FUNCTION}/triggers/{TRIGGER}", {"triggerConfig": config})
    state = "enabled" if on else "DISABLED - nothing will start or stop the server"
    print(f"timer {TRIGGER}: {state}")
    return 0


def status(args: argparse.Namespace) -> int:
    f = fc("GET", f"{FC}/{FUNCTION}", check=False)
    if "_error" in f:
        print(f"function: {f['_error']}")
        return 1
    env = f.get("environmentVariables") or {}
    t = fc("GET", f"{FC}/{FUNCTION}/triggers/{TRIGGER}", check=False)
    enabled = json.loads(t.get("triggerConfig", "{}")).get("enable") if "_error" not in t else None
    print(json.dumps({
        "DRY_RUN": env.get("DRY_RUN"), "timer_enabled": enabled,
        "runtime": f.get("runtime"), "last_modified": f.get("lastModifiedTime"),
    }, indent=1))
    now = datetime.now(UTC)
    for name in ("oa-scheduler-decision", "oa-scheduler-alert"):
        since = int((now - timedelta(hours=args.hours)).timestamp() * 1000)
        got = cms("DescribeCustomEventAttribute", "--Name", name,
                  "--GroupId", env.get("CMS_GROUP_ID", ""), "--StartTime", str(since),
                  "--EndTime", str(int(now.timestamp() * 1000)), check=False)
        found = got.get("CustomEvents") or {} if "_error" not in got else {}
        events = found.get("CustomEvent", [])
        print(f"\n{name}: {len(events)} in the last {args.hours} h")
        for e in sorted(events, key=lambda e: e.get("Time", ""))[-args.show:]:
            print("  ", e.get("Time"), e.get("Content", "")[:300])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("apply")
    m = sub.add_parser("mode")
    m.add_argument("to", choices=("dry", "live"))
    sub.add_parser("disable")
    sub.add_parser("enable")
    s = sub.add_parser("status")
    s.add_argument("--hours", type=int, default=24)
    s.add_argument("--show", type=int, default=8)
    args = parser.parse_args()
    handlers = {"apply": apply, "mode": mode, "disable": switch, "enable": switch, "status": status}
    try:
        return handlers[args.cmd](args)
    except rt.Stop as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
