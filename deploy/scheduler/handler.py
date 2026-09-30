"""Function Compute handler for the scheduled stop (design §2-§5).

Every 15 minutes: gather the inputs, ask `options_alpha_lab.scheduler.decide`,
carry out its answer, and leave a durable record. All the rules live in
`decide`; this file only talks to Alibaba Cloud and the server.

Standard library only. The two Alibaba APIs it needs (ECS, CloudMonitor) are
called with the RPC signature, using the temporary credentials Function Compute
passes in `context.credentials` for the function's RAM role; nothing is
bundled that could drift from what was reviewed.

Environment:
  DRY_RUN       "0" to act. Anything else, or unset, decides and logs only:
                no StartInstance, StopInstance or tag rewrite.
  INSTANCE_ID   the one instance (the role is scoped to it as well)
  REGION        default ap-southeast-1
  BASE_URL      the server's public URL, default http://47.236.50.157
  CMS_GROUP_ID  CloudMonitor application group that routes alerts to email
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from options_alpha_lab.calendar import committed_calendar
from options_alpha_lab.scheduler import (
    LOCK_REASON_TAG,
    LOCK_UNTIL_TAG,
    Action,
    LockState,
    Readiness,
    decide,
    in_run_window,
    read_lock,
)

ECS_VERSION = "2014-05-26"
CMS_VERSION = "2019-01-01"
#: A start is judged once, on the first tick at least this long after it.
START_CHECK_AFTER = timedelta(minutes=20)
START_CHECK_UNTIL = timedelta(minutes=35)


# --- signed RPC ------------------------------------------------------------------


def _pct(value: str) -> str:
    return urllib.parse.quote(value, safe="~")


def sign(query: dict[str, str], secret: str, method: str = "GET") -> str:
    """The RPC signature (version 1.0, HMAC-SHA1) over every query parameter."""
    canonical = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(query.items()))
    to_sign = f"{method}&{_pct('/')}&{_pct(canonical)}"
    digest = hmac.new(f"{secret}&".encode(), to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def rpc(endpoint: str, version: str, action: str, params: dict[str, str], creds: Any) -> Any:
    """One signed GET to an Alibaba Cloud RPC API (signature version 1.0)."""
    query = {
        "Format": "JSON",
        "Version": version,
        "Action": action,
        "AccessKeyId": creds.access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
        "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **params,
    }
    token = getattr(creds, "security_token", None)
    if token:
        query["SecurityToken"] = token
    query["Signature"] = sign(query, creds.access_key_secret)
    url = f"https://{endpoint}/?{urllib.parse.urlencode(query, quote_via=urllib.parse.quote)}"
    failure = ""
    try:
        with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - fixed https host
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body)
            code = f"{detail.get('Code', '?')}: {str(detail.get('Message', ''))[:160]}"
        except ValueError:
            code = body[:160]
        failure = f"{action} failed: HTTP {exc.code} {code}"
    # Raised outside the handler, so no chained HTTPError exists for the runtime
    # to report instead: Function Compute prints an exception's context.
    raise RuntimeError(failure)


class Cloud:
    def __init__(self, creds: Any, region: str, instance_id: str, group_id: str) -> None:
        self.creds, self.region = creds, region
        self.instance_id, self.group_id = instance_id, group_id

    def ecs(self, action: str, **params: str) -> Any:
        return rpc(f"ecs.{self.region}.aliyuncs.com", ECS_VERSION, action,
                   {"RegionId": self.region, **params}, self.creds)

    def instance(self) -> dict[str, Any]:
        found = self.ecs("DescribeInstances", InstanceIds=json.dumps([self.instance_id]))
        items = found["Instances"]["Instance"]
        if not items:
            raise RuntimeError(f"instance {self.instance_id} not found")
        return dict(items[0])

    def event(self, name: str, content: dict[str, Any]) -> None:
        # CloudMonitor takes the event as numbered fields, not one JSON value
        # (a single `EventInfo` is refused as MissingEventInfo).
        params = {
            "EventInfo.1.EventName": name,
            "EventInfo.1.GroupId": self.group_id,
            "EventInfo.1.Content": json.dumps(content, sort_keys=True)[:4000],
            "EventInfo.1.Time": datetime.now(UTC).strftime("%Y%m%dT%H%M%S.000+0000"),
        }
        rpc(f"metrics.{self.region}.aliyuncs.com", CMS_VERSION, "PutCustomEvent",
            params, self.creds)


def tags_of(inst: dict[str, Any]) -> dict[str, str]:
    return {t["TagKey"]: t.get("TagValue", "") for t in inst.get("Tags", {}).get("Tag", [])}


def http_json(url: str) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310 - configured URL
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (OSError, ValueError) as exc:
        return 0, str(exc)


def readiness_from(base_url: str) -> Readiness:
    status, body = http_json(f"{base_url}/api/v1/system/stop-readiness")
    if status != 200 or not isinstance(body, dict):
        return Readiness(False, (f"stop-readiness unreachable (HTTP {status})",))
    data = body.get("data") or {}
    return Readiness(bool(data.get("ok")), tuple(data.get("reasons") or ()))


def started_healthy(base_url: str) -> tuple[bool, str]:
    """HTTP 200 from the status endpoint and the worker holding its lease."""
    status, body = http_json(f"{base_url}/api/v1/system/status")
    if status != 200 or not isinstance(body, dict):
        return False, f"status endpoint answered HTTP {status}"
    worker = next((i for i in body.get("data") or [] if i.get("label") == "Worker"), None)
    if worker is None or worker.get("tone") != "ok":
        return False, f"worker not live: {worker.get('value') if worker else 'no Worker item'}"
    return True, "status 200, worker live"


def parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- the tick ----------------------------------------------------------------------


def tick(cloud: Cloud, *, now: datetime, dry_run: bool, base_url: str) -> dict[str, Any]:
    inst = cloud.instance()
    status = str(inst.get("Status"))
    tags = tags_of(inst)
    calendar, covered = committed_calendar()
    decision = decide(
        now=now, status=status, tags=tags, calendar=calendar, covered_until=covered,
        readiness=lambda: readiness_from(base_url),
    )
    alerts = list(decision.alerts)
    done: list[str] = []

    if decision.retag_until is not None:
        until = decision.retag_until.strftime("%Y-%m-%dT%H:%M:%SZ")
        if dry_run:
            done.append(f"would rewrite the lock to {until}")
        else:
            try:
                cloud.ecs(
                    "TagResources", ResourceType="instance", **{"ResourceId.1": cloud.instance_id},
                    **{"Tag.1.Key": LOCK_UNTIL_TAG, "Tag.1.Value": until,
                       "Tag.2.Key": LOCK_REASON_TAG,
                       "Tag.2.Value": tags.get(LOCK_REASON_TAG, "rewritten")},
                )
                done.append(f"lock rewritten to {until}")
            except RuntimeError as exc:
                alerts.append(f"lock rewrite failed ({exc}); the server stays up")

    if decision.action is Action.START:
        if dry_run:
            done.append("would StartInstance")
        else:
            try:
                cloud.ecs("StartInstance", InstanceId=cloud.instance_id)
                done.append("StartInstance")
            except RuntimeError as exc:
                alerts.append(f"StartInstance failed: {exc}")
    elif decision.action is Action.STOP:
        if dry_run:
            done.append("would StopInstance (StopCharging)")
        else:
            cloud.ecs("StopInstance", InstanceId=cloud.instance_id, StoppedMode="StopCharging")
            done.append("StopInstance (StopCharging)")

    # §5 layer 1: judge a start once, 20-35 minutes after it.
    started = parse_time(inst.get("StartTime"))
    wanted = in_run_window(calendar, now, covered) or read_lock(tags, now).state is LockState.ACTIVE
    if status == "Running" and started and wanted:
        age = now - started
        if START_CHECK_AFTER <= age < START_CHECK_UNTIL:
            healthy, detail = started_healthy(base_url)
            done.append(f"start check: {detail}")
            if not healthy:
                alerts.append(f"server started {int(age.total_seconds() // 60)} min ago "
                              f"but is not healthy: {detail}")

    record = {
        "at": now.isoformat(), "dry_run": dry_run, "status": status,
        "action": decision.action.value, "reason": decision.reason, "done": done,
        "alerts": alerts,
    }
    for alert in alerts:
        cloud.event("oa-scheduler-alert", {"alert": alert, "dry_run": dry_run, "at": record["at"]})
    cloud.event("oa-scheduler-decision", record)
    return record


@dataclass(frozen=True)
class Credentials:
    access_key_id: str
    access_key_secret: str
    security_token: str | None


def role_credentials(context: Any) -> Any:
    """The function role's temporary credentials.

    Function Compute 3.0 passes them as environment variables; older runtimes
    as `context.credentials`. Either way they are STS credentials for
    `oa-scheduler-role`, never a long-lived key.
    """
    key = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
    if key:
        return Credentials(
            key, os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
            os.environ.get("ALIBABA_CLOUD_SECURITY_TOKEN"),
        )
    creds = getattr(context, "credentials", None)
    if creds is None:
        raise RuntimeError("no role credentials: is oa-scheduler-role attached to the function?")
    return creds


def handler(event: Any, context: Any) -> str:
    cloud = Cloud(
        role_credentials(context), os.environ.get("REGION", "ap-southeast-1"),
        os.environ["INSTANCE_ID"], os.environ["CMS_GROUP_ID"],
    )
    now = datetime.now(UTC)
    try:
        record = tick(
            cloud, now=now, dry_run=os.environ.get("DRY_RUN", "1") != "0",
            base_url=os.environ.get("BASE_URL", "http://47.236.50.157"),
        )
    except Exception as exc:
        # A tick that cannot decide is itself an alert, and fails the invocation
        # so the function's error metric sees it too (§5 layer 2). If the alert
        # cannot be sent either, the original failure is still what is raised.
        try:
            failed = {"alert": f"tick failed: {exc}", "at": now.isoformat()}
            cloud.event("oa-scheduler-alert", failed)
        except Exception:  # noqa: BLE001, S110 - the error metric still fires
            pass
        raise
    return json.dumps(record)
