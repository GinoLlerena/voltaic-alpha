#!/usr/bin/env python3
"""Run the 2c2g pay-as-you-go trial (cost analysis §7.4-§7.5), and undo it.

Runs on the OPERATOR machine, never on the instance: the instance is the thing
being stopped, so nothing on it can be trusted to bring it back. Authenticates
with the operator's `aliyun` profile. Every `aliyun` call's stderr is captured
and never shown unredacted - that CLI prints the whole signed request, key id
included, on any failure.

Subcommands:

  preflight          read-only: instance, stock for target AND rollback type,
                     backups fresh, watchdog green, no open incidents
  resize --to TYPE   the change itself; the same path serves the rollback
  health             post-start checks; exit 0 only when every one passes
  evaluate           the trial verdict against the baseline session

The rollback criteria were set by the account owner on 23 September 2026, with
the memory thresholds revised on 26 September, and are not tunable here: p95
latency more than 20% worse than the baseline session; any OOM kill; memory
pressure (PSI some avg10) above 1.0 in any sample or present in more than 1% of
samples; MemAvailable under 256 MiB for five minutes; any API, dashboard,
worker, trading, backup or restore failure; or measurements that are
insufficient or inconclusive.
`evaluate --apply` returns the instance to ecs.e-c1m2.large on any of them.

This runs on the operator's machine and cannot outlive it: the resize and any
rollback are run under active supervision, with the console open on the manual
rollback card in cost analysis §7.7. Launch it under `nohup caffeinate` so a
closed session or a sleeping Mac cannot kill it mid-change.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REGION = "ap-southeast-1"
INSTANCE = "i-t4n88bkfwsq0lhzmfjii"
TRIAL_TYPE = "ecs.e-c1m1.large"
ROLLBACK_TYPE = "ecs.e-c1m2.large"
RECORD_DIR = Path.home() / "options-alpha-offsite" / "resize-trial"
ABORT_SECONDS = 30 * 60
#: Samples every 30 s; a 6.5 h session holds 780. Below 90% is insufficient.
SESSION_SAMPLES = 780
MIN_SAMPLE_FRACTION = 0.9
MAX_P95_REGRESSION = 0.20
#: Memory rollback thresholds, agreed 26 September 2026 (see evaluate()).
MAX_PSI_SOME = 1.0  # any sample: >1% of a 10 s window stalled on memory
MAX_PSI_SHARE = 0.01  # pressure present in more than 1% of samples
LOW_MEMORY_MIB = 256  # cost analysis §7.3: MemAvailable floor ...
LOW_MEMORY_SECONDS = 300  # ... for five minutes


class Stop(Exception):
    """Abort the current step. The message says why."""


def _redact(text: str) -> str:
    text = re.sub(r"https?://\S+", "<url-redacted>", text)
    text = re.sub(
        r"(AccessKeyId|Signature|CommandContent|SecurityToken)=[^&\s\"]*", r"\1=<redacted>", text
    )
    return re.sub(r"(LTAI|STS\.)[A-Za-z0-9]+", r"\1<redacted>", text)


#: Error codes that describe the moment rather than the request. Anything else -
#: DryRunOperation, a permission refusal, a state error - is an answer, and
#: retrying an answer only delays acting on it.
TRANSIENT_CODES = frozenset(
    {
        "Throttling",
        "Throttling.User",
        "Throttling.Api",
        "ServiceUnavailable",
        "InternalError",
        "InternalError.Dispatch",
        "UnknownError",
        "OperationConflict",
    }
)
#: Backoff between attempts, seconds: about 90 s in all before giving up.
RETRY_BACKOFF = (5, 10, 15, 20, 20, 20)


def aliyun(*args: str, check: bool = True) -> dict[str, Any]:
    """Call the Alibaba CLI, retrying what a network blip or throttling can cause.

    A dropped connection mid-maintenance is the failure most likely to strand the
    instance between stop and start, so a call is only allowed to fail once the
    backoff is exhausted or the service has given a definite answer.
    """
    code = None
    for delay in (*RETRY_BACKOFF, None):
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                ["aliyun", *args], capture_output=True, text=True, timeout=120, check=False
            )
        except subprocess.TimeoutExpired:
            code, done = None, None
        if done is not None and done.returncode == 0:
            out = done.stdout
            start, end = out.find("{"), out.rfind("}")
            return json.loads(out[start : end + 1]) if start >= 0 else {}
        found = re.search(r"ErrorCode: ([A-Za-z0-9.]+)", done.stderr) if done else None
        code = found.group(1) if found else None
        # No error code means the request never got a service answer: network.
        if (code is not None and code not in TRANSIENT_CODES) or delay is None:
            break
        time.sleep(delay)
    if done is not None and done.returncode != 0:
        if check:
            raise Stop(
                f"aliyun {args[1] if len(args) > 1 else args[0]} failed: "
                f"{code or _redact(done.stderr)[:200]}"
            )
        return {"_error": code or "unknown"}
    raise Stop(f"aliyun {args[1] if len(args) > 1 else args[0]} timed out on every attempt")


def remote(script: str, timeout: int = 600) -> str:
    """Run a shell script on the instance via Cloud Assistant; return its output."""
    body = "#!/bin/bash\n" + script
    invoke = aliyun(
        "ecs",
        "RunCommand",
        "--RegionId",
        REGION,
        "--Type",
        "RunShellScript",
        "--InstanceId.1",
        INSTANCE,
        "--ContentEncoding",
        "Base64",
        "--Timeout",
        str(timeout),
        "--CommandContent",
        base64.b64encode(body.encode()).decode(),
    )["InvokeId"]
    deadline = time.time() + timeout + 60
    while time.time() < deadline:
        result = aliyun(
            "ecs", "DescribeInvocationResults", "--RegionId", REGION, "--InvokeId", invoke
        )["Invocation"]["InvocationResults"]["InvocationResult"][0]
        if result["InvocationStatus"] not in ("Running", "Pending", "Invoked"):
            output = base64.b64decode(result.get("Output", "")).decode("utf-8", "replace")
            if result.get("ExitCode") != 0:
                raise Stop(f"remote step failed (exit {result.get('ExitCode')}): {output[-400:]}")
            return output
        time.sleep(4)
    raise Stop("remote step timed out")


REMOTE_DIR = Path(__file__).with_name("resize_trial_remote")
VENV_PYTHON = "/opt/options-alpha/.venv/bin/python"


def remote_py(
    name: str,
    *argv: str,
    venv: bool = False,
    env_file: str | None = None,
    before: str = "",
    timeout: int = 600,
) -> dict[str, Any]:
    """Run one host-side program from resize_trial_remote/ and parse its last JSON line.

    The file is sent as-is, so what was reviewed is what runs.
    """
    code = (REMOTE_DIR / name).read_text(encoding="utf-8")
    python = VENV_PYTHON if venv else "python3"
    lines = ["set -euo pipefail", "cd /opt/options-alpha"]
    if before:
        lines.append(before)
    if env_file:
        lines.append(f"set -a; . {env_file}; set +a")
    args = " ".join(f"'{a}'" for a in argv)
    lines.append(f"{python} - {args} <<'PY'\n{code}\nPY")
    output = remote("\n".join(lines), timeout=timeout)
    return dict(json.loads(output.strip().splitlines()[-1]))


def instance() -> dict[str, Any]:
    items = aliyun(
        "ecs", "DescribeInstances", "--RegionId", REGION, "--InstanceIds", json.dumps([INSTANCE])
    )["Instances"]["Instance"]
    return dict(items[0])


def wait_status(want: str, limit: int = 900) -> float:
    start = time.time()
    while time.time() - start < limit:
        if instance()["Status"] == want:
            return time.time() - start
        time.sleep(8)
    raise Stop(f"instance did not reach {want} within {limit} s")


def in_stock(instance_type: str) -> bool:
    data = aliyun(
        "ecs",
        "DescribeResourcesModification",
        "--RegionId",
        REGION,
        "--ResourceId",
        INSTANCE,
        "--DestinationResource",
        "InstanceType",
    )
    for zone in data.get("AvailableZones", {}).get("AvailableZone", []):
        for res in zone["AvailableResources"]["AvailableResource"]:
            for s in res["SupportedResources"]["SupportedResource"]:
                if s["Value"] == instance_type:
                    return bool(
                        s["Status"] == "Available" and s.get("StatusCategory") == "WithStock"
                    )
    return False


def log(record: dict[str, Any], step: str, **fields: Any) -> None:
    entry = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "step": step, **fields}
    record.setdefault("steps", []).append(entry)
    print(json.dumps(entry), flush=True)


HOST_STATE = "host_state.py"


def host_state() -> dict[str, Any]:
    return remote_py(HOST_STATE, timeout=120)


def preflight(args: argparse.Namespace) -> int:
    problems: list[str] = []
    inst = instance()
    print(f"instance {inst['InstanceType']} {inst['Status']} {inst['InstanceChargeType']}")
    if inst["InstanceChargeType"] != "PostPaid":
        problems.append("not pay-as-you-go: the trial must stay reversible without a purchase")
    for t in (TRIAL_TYPE, ROLLBACK_TYPE):
        ok = in_stock(t)
        print(f"stock {t}: {'yes' if ok else 'NO'}")
        if not ok:
            problems.append(
                f"{t} not in stock - "
                + ("cannot trial" if t == TRIAL_TYPE else "rollback not assured")
            )
    if inst["Status"] == "Running":
        state = host_state()
        print(json.dumps(state, indent=1))
        now = datetime.now(UTC)
        b_at = datetime.fromisoformat(state["backup"]["at"].replace("Z", "+00:00"))
        if not state["backup"]["verified"] or (now - b_at) > timedelta(hours=2, minutes=10):
            problems.append("latest local backup not verified or older than 2 h 10 min")
        if not state["offsite"]["ok"]:
            problems.append("last offsite run failed")
        if not state["watchdog_ok"]:
            problems.append(f"watchdog failing: {state['watchdog_failures']}")
        if state["open_incidents"]:
            problems.append(f"{state['open_incidents']} open incident(s) - §7.4 step 1 says defer")
        if state["not_enabled"]:
            problems.append(
                f"units not enabled, would not return after the restart: {state['not_enabled']}"
            )
        down = [u for u, s in state["units"].items() if s != "active"]
        if down:
            problems.append(f"units not active: {down}")
    for p in problems:
        print(f"PREFLIGHT FAIL: {p}")
    print("PREFLIGHT PASS" if not problems else "PREFLIGHT FAILED")
    return 0 if not problems else 1


FRESH_ANCHOR = "fresh_anchor.py"

QUIESCE = r"""
set -u
systemctl stop options-alpha-backup.timer options-alpha-backup-offsite.timer \
  options-alpha-watchdog.timer
systemctl stop options-alpha-worker options-alpha options-alpha-api options-alpha-capacity
systemctl stop postgresql
sync
echo "quiesced: $(systemctl is-active postgresql options-alpha-worker | tr '\n' ' ')"
"""


def resize(args: argparse.Namespace) -> int:
    target = args.to
    rollback = target == ROLLBACK_TYPE
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RECORD_DIR / f"{stamp}-{'rollback' if rollback else 'resize'}.json"
    record: dict[str, Any] = {"target": target, "rollback": rollback, "dry_run": args.dry_run}

    def save() -> None:
        path.write_text(json.dumps(record, indent=2))

    try:
        inst = instance()
        record["before"] = {k: inst[k] for k in ("InstanceType", "Status", "InstanceChargeType")}
        if inst["InstanceType"] == target:
            raise Stop(f"already {target}; nothing to do")
        if not in_stock(target):
            raise Stop(
                f"{target} not in stock; not stopping a healthy instance "
                "for a change that cannot land"
            )
        if inst["Status"] == "Running":
            try:
                record["checkpoint"] = host_state()
                log(
                    record,
                    "checkpoint",
                    **{
                        k: record["checkpoint"][k]
                        for k in (
                            "alembic",
                            "decisions",
                            "market_snapshots",
                            "decision_outcomes",
                            "open_incidents",
                        )
                    },
                )
            except Stop as exc:
                if not rollback:
                    raise
                # A rollback exists for the case where the host is unwell; failing to
                # read it must not block the way back.
                log(record, "checkpoint_skipped", reason=str(exc))
            if not rollback and not args.dry_run:
                record["pre_resize_copy"] = remote_py(
                    FRESH_ANCHOR,
                    venv=True,
                    env_file="/etc/options-alpha-backup.env",
                    before="systemctl start options-alpha-backup.service",
                    timeout=900,
                )
                copy = record["pre_resize_copy"]
                src = f"oss://{copy['bucket']}/{copy['key']}"
                dst = f"oss://{copy['bucket']}/anchor/{Path(copy['key']).name}"
                for _ in range(3):
                    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                        ["aliyun", "oss", "cp", src, dst],
                        capture_output=True,
                        text=True,
                        timeout=600,
                        check=False,
                    )
                    if done.returncode == 0:
                        break
                    time.sleep(15)
                if done.returncode != 0:
                    raise Stop("server-side copy to anchor/ failed")
                record["anchor_object"] = dst
                log(record, "fresh_verified_copy", **record["pre_resize_copy"], anchor=dst)
                disk = aliyun(
                    "ecs", "DescribeDisks", "--RegionId", REGION, "--InstanceId", INSTANCE
                )["Disks"]["Disk"][0]["DiskId"]
                snap = aliyun(
                    "ecs",
                    "CreateSnapshot",
                    "--RegionId",
                    REGION,
                    "--DiskId",
                    disk,
                    "--SnapshotName",
                    f"pre-resize-{stamp}",
                    check=False,
                )
                record["snapshot"] = (
                    snap.get("SnapshotId")
                    or f"not created ({snap.get('_error')}) - optional per plan"
                )
                log(record, "snapshot", result=record["snapshot"])
                if snap.get("SnapshotId"):
                    for _ in range(90):
                        s = aliyun(
                            "ecs",
                            "DescribeSnapshots",
                            "--RegionId",
                            REGION,
                            "--SnapshotIds",
                            json.dumps([snap["SnapshotId"]]),
                        )["Snapshots"]["Snapshot"][0]
                        if s["Status"] == "accomplished":
                            break
                        time.sleep(10)
                    log(record, "snapshot_done", status=s["Status"])
            if args.dry_run:
                log(record, "dry_run_stop_here", note="would quiesce, stop, resize and start")
                save()
                return 0
            try:
                log(record, "quiesce", out=remote(QUIESCE, timeout=180).strip())
            except Stop as exc:
                if not rollback:
                    raise
                log(record, "quiesce_skipped", reason=str(exc))
            stopped_at = time.time()
            record["stopped_at"] = datetime.now(UTC).isoformat(timespec="seconds")
            aliyun("ecs", "StopInstance", "--InstanceId", INSTANCE, "--StoppedMode", "KeepCharging")
            log(record, "stopped", seconds=round(wait_status("Stopped")))
        else:
            stopped_at = time.time()
        dry = aliyun(
            "ecs",
            "ModifyInstanceSpec",
            "--RegionId",
            REGION,
            "--InstanceId",
            INSTANCE,
            "--InstanceType",
            target,
            "--DryRun",
            "true",
            check=False,
        )
        if dry.get("_error") != "DryRunOperation":
            raise Stop(
                f"dry run returned {dry.get('_error')}, not DryRunOperation - restarting unchanged"
            )
        aliyun(
            "ecs",
            "ModifyInstanceSpec",
            "--RegionId",
            REGION,
            "--InstanceId",
            INSTANCE,
            "--InstanceType",
            target,
            "--AllowMigrateAcrossZone",
            "false",
        )
        log(record, "modified", to=target)
        aliyun("ecs", "StartInstance", "--InstanceId", INSTANCE)
        log(record, "running", seconds=round(wait_status("Running")))
        record["health"] = wait_healthy(stopped_at)
        record["after"] = {k: instance()[k] for k in ("InstanceType", "Status")}
        record["downtime_seconds"] = round(time.time() - stopped_at)
        log(record, "done", **record["after"], downtime_s=record["downtime_seconds"])
        save()
        return 0
    except Stop as exc:
        log(record, "STOPPED", reason=str(exc))
        save()
        modified = any(step["step"] == "modified" for step in record.get("steps", []))
        if modified and not rollback:
            log(record, "auto_rollback", reason="not healthy on the trial type")
            save()
            return resize(argparse.Namespace(to=ROLLBACK_TYPE, dry_run=False)) or 1
        inst = instance()
        if inst["Status"] == "Stopped":
            # Never leave production down: start it on whatever type it has, and
            # keep trying - each call already retries for ~90 s; this loops for ~10 min.
            for attempt in range(6):
                try:
                    aliyun("ecs", "StartInstance", "--InstanceId", INSTANCE)
                    break
                except Stop as start_exc:
                    log(
                        record, "restart_attempt_failed", attempt=attempt + 1, reason=str(start_exc)
                    )
                    save()
            else:
                log(record, "RESTART_FAILED", action="start it from the console now")
                save()
                return 1
            log(
                record,
                "restarted_unchanged",
                type=inst["InstanceType"],
                seconds=round(wait_status("Running")),
            )
            save()
        return 1


HEALTH = "health.py"


def health_ok(h: dict[str, Any]) -> list[str]:
    bad = [f"{u} {s}" for u, s in h["units"].items() if s != "active"]
    if h["lease_holders"] != 1:
        bad.append(f"lease holders {h['lease_holders']} (want exactly 1)")
    if not isinstance(h["api_status_items"], int) or h["api_status_items"] < 1:
        bad.append(f"API payload {h['api_status_items']}")
    if h["dashboard_http"] != 200:
        bad.append(f"dashboard {h['dashboard_http']}")
    if not h["startup_reconcile_clean"]:
        bad.append("startup reconciliation not clean")
    if not h["first_tick_at"]:
        bad.append("no tick yet")
    if not h["watchdog_ok"]:
        bad.append(f"watchdog: {h['watchdog_failures']}")
    return bad


def wait_healthy(stopped_at: float) -> dict[str, Any]:
    last: list[str] = ["not checked"]
    while time.time() - stopped_at < ABORT_SECONDS:
        try:
            h = remote_py(HEALTH, timeout=120)
            last = health_ok(h)
            if not last:
                return h
        except Stop as exc:
            last = [str(exc)]
        time.sleep(30)
    raise Stop(f"not healthy within the 30-minute abort threshold: {last}")


def health(args: argparse.Namespace) -> int:
    h = remote_py(HEALTH, timeout=120)
    print(json.dumps(h, indent=1))
    bad = health_ok(h)
    for b in bad:
        print(f"HEALTH FAIL: {b}")
    print("HEALTH PASS" if not bad else "HEALTH FAILED")
    return 0 if not bad else 1


SESSION_STATS = "session_stats.py"


def session_stats(start: str, end: str) -> dict[str, Any]:
    return remote_py(SESSION_STATS, start, end, venv=True, timeout=300)


def evaluate(args: argparse.Namespace) -> int:
    base = session_stats(args.baseline_start, args.baseline_end)
    trial = session_stats(args.trial_start, args.trial_end)
    reasons: list[str] = []
    for label, s in (("baseline", base), ("trial", trial)):
        if s["samples"] < SESSION_SAMPLES * MIN_SAMPLE_FRACTION:
            reasons.append(
                f"insufficient {label} samples: {s['samples']} < "
                f"{int(SESSION_SAMPLES * MIN_SAMPLE_FRACTION)}"
            )
    for probe in ("api_status", "api_decisions", "dashboard"):
        b, t = base["p95_ms"][probe], trial["p95_ms"][probe]
        if not b or not t:
            reasons.append(f"inconclusive: no {probe} latency in one window")
            continue
        change = (t - b) / b
        print(f"p95 {probe}: baseline {b:.0f} ms -> trial {t:.0f} ms ({change:+.1%})")
        if change > MAX_P95_REGRESSION:
            reasons.append(f"p95 {probe} {change:+.1%} worse than baseline (limit +20%)")
    if trial["oom_kills"]:
        reasons.append(f"{trial['oom_kills']} OOM kill(s)")
    # Memory thresholds as agreed on 26 September 2026. "Any PSI above zero" was
    # dropped: the 4 GB baseline itself showed 0.12 in 2 of 780 session samples
    # (about 12 ms stalled in a 10 s window), so it could not tell a healthy server
    # from a struggling one. Real memory trouble is sustained and whole-percent.
    if (trial["psi_memory_max"] or 0) > MAX_PSI_SOME:
        reasons.append(
            f"memory pressure: PSI some avg10 reached {trial['psi_memory_max']} "
            f"(limit {MAX_PSI_SOME})"
        )
    share = trial["psi_memory_nonzero"] / max(trial["samples"], 1)
    if share > MAX_PSI_SHARE:
        reasons.append(f"memory pressure in {share:.1%} of samples (limit {MAX_PSI_SHARE:.0%})")
    if trial["low_memory_longest_s"] >= LOW_MEMORY_SECONDS:
        reasons.append(
            f"MemAvailable under {LOW_MEMORY_MIB} MiB for "
            f"{trial['low_memory_longest_s']:.0f} s (limit {LOW_MEMORY_SECONDS} s)"
        )
    if any(trial["probe_failures"].values()):
        reasons.append(f"API/dashboard probe failures: {trial['probe_failures']}")
    if trial["backup_failures"] or trial["offsite_failures"]:
        reasons.append(
            f"backup/restore failures: {trial['backup_failures']} hourly, "
            f"{trial['offsite_failures']} offsite"
        )
    if trial["failed_ticks"]:
        reasons.append(f"worker failed ticks: {len(trial['failed_ticks'])}")
    if (trial["tick_age_max_s"] or 0) > 900 or (trial["lease_age_max_s"] or 0) > 120:
        reasons.append("worker stalled or lease heartbeat late")
    verdict = {
        "baseline": base,
        "trial": trial,
        "rollback_reasons": reasons,
        "verdict": "PASS" if not reasons else "ROLLBACK",
    }
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    out = RECORD_DIR / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-evaluation.json"
    out.write_text(json.dumps(verdict, indent=2))
    print(json.dumps(verdict, indent=1))
    if reasons and args.apply:
        print("rolling back to", ROLLBACK_TYPE)
        return resize(argparse.Namespace(to=ROLLBACK_TYPE, dry_run=False))
    return 0 if not reasons else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    r = sub.add_parser("resize")
    r.add_argument("--to", required=True, choices=(TRIAL_TYPE, ROLLBACK_TYPE))
    r.add_argument("--dry-run", action="store_true", help="checkpoint and stop before any change")
    sub.add_parser("health")
    e = sub.add_parser("evaluate")
    for k in ("baseline-start", "baseline-end", "trial-start", "trial-end"):
        e.add_argument(f"--{k}", required=True, help="UTC ISO, e.g. 2026-09-24T13:30")
    e.add_argument("--apply", action="store_true", help="roll back automatically on any criterion")
    args = parser.parse_args()
    return {"preflight": preflight, "resize": resize, "health": health, "evaluate": evaluate}[
        args.cmd
    ](args)


if __name__ == "__main__":
    sys.exit(main())
