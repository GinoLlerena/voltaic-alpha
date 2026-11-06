#!/usr/bin/env python3
"""Deploy the React UI behind port 80, verify it, and undo it (runbook §11.2).

Runs on the OPERATOR machine and reuses `resize_trial.py`'s `aliyun` layer:
retries on network blips, and stderr never shown unredacted.

Subcommands:

  inspect            read-only: what the deploy would change on the host
  deploy [--apply]   ship, install, verify on the operator's IP and on port 80;
                     without --apply it prints the plan
  rollback           put back the previous React build and API modules

Designed to run unattended (owner, 27 September 2026: "don't start an operation
that depends on my intervention"). Unlike the resize, nothing here stops the
instance. A failure after the first change is reverted by this same run, so the
revert depends on this machine staying up until the run ends - it is not a
host-side safety net. What keeps a revert small:

  - the payload is two API modules and `frontend/dist`. The worker's code is
    not touched and the worker is not restarted;
  - every deploy first keeps the host's API modules and build in
    `.deploy-backup/<stamp>/`, so undoing it is copying them back and
    restarting one service (Streamlit retirement plan, §3 and phase 2);
  - port 80 already points at the API: the port-80 unit itself redirects it to
    8600, so a deploy never touches the redirect;
  - the temporary security-group rule for 8600 is revoked in a `finally`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import resize_trial as rt

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
HOST_ROOT = "/opt/options-alpha"
HOST_DIST = f"{HOST_ROOT}/frontend/dist"
BACKUP_DIR = f"{HOST_ROOT}/.deploy-backup"
SG = "sg-t4naetmr3bp6sry6lw7a"
EIP = "47.236.50.157"
API_PORT = 8600
RECORD_DIR = Path.home() / "options-alpha-offsite" / "react-deploy"

#: The only source that changes. `inspect` refuses to plan if anything else in
#: the package differs: the host would then not be at the state this deploy was
#: tested against, and the worker would run untested code on its next restart.
API_FILES = ("src/options_alpha_lab/api/server.py", "src/options_alpha_lab/api/limits.py")

API_DROPIN = "/etc/systemd/system/options-alpha-api.service.d/public.conf"
API_DROPIN_TEXT = f"""\
# React UI (runbook §11.2): serve the build and listen beyond loopback. The
# security group admits 80 only; 8600 is opened to the operator's /32 for the
# verification step and revoked afterwards.
[Service]
Environment=PRESENTATION_API_HOST=0.0.0.0
Environment=PRESENTATION_UI_DIR={HOST_DIST}
"""

#: A remote script's CommandContent is capped near 18 KB once encoded.
CHUNK = 9000


def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Local tools (git, pnpm) resolved from the operator's PATH, as in a shell."""
    return subprocess.run(argv, text=True, capture_output=True, **kwargs)  # noqa: S603


# --- the guard ------------------------------------------------------------------


def market_window_reason(now: datetime) -> str | None:
    """Why now is not a deploy window, or None. SPY options trade to 16:15 ET.

    A weekday deploy waits for 17:15 ET, after the close and the hourly backup
    that follows it; it must also be done before 08:30 ET, an hour before the open.
    """
    et = now.astimezone(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return None
    minutes = et.hour * 60 + et.minute
    if 8 * 60 + 30 <= minutes < 17 * 60 + 15:
        return f"{et:%a %H:%M} ET is inside the trading day plus the post-close backup"
    return None


# --- the payload ----------------------------------------------------------------


def build_payload() -> tuple[bytes, dict[str, str]]:
    """Build the UI from a clean tree and tar it with the API modules.

    Returns the gzip tarball and a manifest of path -> sha256.
    """
    dirty = run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, check=True
    ).stdout.strip()
    if dirty:
        raise rt.Stop(f"working tree has tracked changes; deploy from a clean main:\n{dirty}")
    run(["pnpm", "run", "build"], cwd=FRONTEND, check=True)
    files = list(API_FILES) + sorted(
        str(p.relative_to(ROOT)) for p in (FRONTEND / "dist").rglob("*") if p.is_file()
    )
    if "frontend/dist/index.html" not in files:
        raise rt.Stop("the build produced no index.html")
    manifest = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in files:
            info = tar.gettarinfo(str(ROOT / f), arcname=f)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o644
            with open(ROOT / f, "rb") as fh:
                tar.addfile(info, fh)
    return buf.getvalue(), manifest


def chunks(payload: bytes, size: int = CHUNK) -> list[str]:
    encoded = base64.b64encode(payload).decode()
    return [encoded[i : i + size] for i in range(0, len(encoded), size)] or [""]


def ship(payload: bytes, stamp: str) -> str:
    """Upload the tarball in chunks and check it arrived whole. Returns its host path."""
    staged = f"/root/react-deploy-{stamp}.tar.gz"
    for i, part in enumerate(chunks(payload)):
        op = ">" if i == 0 else ">>"
        rt.remote(f"umask 077; printf '%s' '{part}' {op} {staged}.b64", timeout=120)
    want = hashlib.sha256(payload).hexdigest()
    got = rt.remote(
        f"set -euo pipefail; base64 -d {staged}.b64 > {staged}; rm -f {staged}.b64\n"
        f"sha256sum {staged} | cut -d' ' -f1",
        timeout=120,
    ).strip()
    if got != want:
        raise rt.Stop(f"payload arrived corrupted: {got[:12]} != {want[:12]}")
    return staged


# --- host steps -----------------------------------------------------------------


def install_script(staged: str, stamp: str) -> str:
    """Keep the old API modules and dist, then extract. dist moves in by one rename."""
    backup = f"{BACKUP_DIR}/{stamp}"
    return f"""set -euo pipefail
cd {HOST_ROOT}
install -d -m 700 {backup}
for f in {" ".join(API_FILES)}; do
  if [ -f "$f" ]; then install -D -m 644 "$f" "{backup}/$f"; else echo "$f" >> {backup}/absent; fi
done
if [ -d {HOST_DIST} ]; then mv {HOST_DIST} {backup}/dist; fi
work=$(mktemp -d); tar -xzf {staged} -C "$work"
install -m 644 "$work"/src/options_alpha_lab/api/*.py src/options_alpha_lab/api/
install -d -m 755 {HOST_ROOT}/frontend
mv "$work"/frontend/dist {HOST_DIST}
rm -rf "$work" {staged}
find {HOST_DIST} -type d -exec chmod 755 {{}} + ; find {HOST_DIST} -type f -exec chmod 644 {{}} +
echo "installed; previous state kept in {backup}"
"""


def write_dropin(path: str, text: str) -> str:
    body = base64.b64encode(text.encode()).decode()
    return f"install -d -m 755 {os.path.dirname(path)}\nprintf '%s' '{body}' | base64 -d > {path}"


RESTART_API = f"""systemctl daemon-reload
systemctl restart options-alpha-api
for i in $(seq 30); do
  curl -fsS -o /dev/null http://127.0.0.1:{API_PORT}/api/v1/system/status && break; sleep 1
done
"""

HOST_CHECKS = f"""set -uo pipefail
code() {{ curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 "$1"; }}
echo "api_status=$(code http://127.0.0.1:{API_PORT}/api/v1/system/status)"
echo "ui_shell=$(curl -s --max-time 10 http://127.0.0.1:{API_PORT}/ | grep -c 'id=.root')"
echo "deep_link=$(code http://127.0.0.1:{API_PORT}/activity)"
echo "unknown_api=$(code http://127.0.0.1:{API_PORT}/api/v1/no-such-route)"
echo "worker=$(systemctl is-active options-alpha-worker)"
echo "api_unit=$(systemctl is-active options-alpha-api)"
"""


def parse_checks(output: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def check_failures(c: dict[str, str]) -> list[str]:
    want = {
        "api_status": "200", "deep_link": "200", "unknown_api": "404",
        "worker": "active", "api_unit": "active",
    }
    bad = [f"{k}={c.get(k)} (want {v})" for k, v in want.items() if c.get(k) != v]
    if c.get("ui_shell", "0") == "0":
        bad.append("the API does not serve the UI shell")
    return bad


def revert_api_script() -> str:
    """Put back the newest backup not yet restored: its API modules and build.

    The API drop-in stays: it is what serves the build on port 80. The build is
    copied, not moved, and the backup is then marked, so a second rollback goes
    one deploy further back instead of finding an empty backup. A backup without
    a build is refused rather than leaving port 80 with no UI.
    """
    return f"""set -euo pipefail
cd {HOST_ROOT}
last=""
for d in $(ls -1d {BACKUP_DIR}/*/ 2>/dev/null | sort -r); do
  if [ ! -e "$d/restored" ]; then last="${{d%/}}"; break; fi
done
if [ -z "$last" ]; then echo "no unrestored backup in {BACKUP_DIR}" >&2; exit 1; fi
if [ ! -d "$last/dist" ]; then
  echo "$last has no frontend build; refusing to leave port 80 without a UI" >&2; exit 1
fi
for f in {" ".join(API_FILES)}; do
  if [ -f "$last/$f" ]; then install -m 644 "$last/$f" "$f"
  elif grep -qx "$f" "$last/absent" 2>/dev/null; then rm -f "$f"; fi
done
work=$(mktemp -d {HOST_ROOT}/frontend/.restore.XXXXXX)
cp -a "$last/dist" "$work/dist"
if [ -d {HOST_DIST} ]; then mv {HOST_DIST} "$work/replaced"; fi
mv "$work/dist" {HOST_DIST}
rm -rf "$work"
touch "$last/restored"
echo "restored from $last"
{RESTART_API}systemctl is-active options-alpha-api
"""


# --- the operator side ------------------------------------------------------------


def as_cidr(ip: str) -> str:
    """A single IPv4 address as a /32, or Stop: never open a port to a guess."""
    ip = ip.strip()
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        raise rt.Stop("could not determine the operator's IPv4 address")
    return f"{ip}/32"


def operator_cidr() -> str:
    # curl rather than urllib: python.org's macOS build ships without a CA bundle,
    # and the first --apply on 28 September stopped here on certificate
    # verification. curl uses the system trust store, as deploy_worker.sh does.
    done = run(["curl", "-fsS", "--max-time", "15", "https://api.ipify.org"], check=False)
    if done.returncode != 0:
        raise rt.Stop(f"could not look up the operator's address (curl exit {done.returncode})")
    return as_cidr(done.stdout)


def sg_rule(action: str, cidr: str) -> None:
    extra = ["--Priority", "1", "--Description", "react verification, temporary"]
    rt.aliyun(
        "ecs", f"{action}SecurityGroup", "--RegionId", rt.REGION, "--SecurityGroupId", SG,
        "--IpProtocol", "tcp", "--PortRange", f"{API_PORT}/{API_PORT}", "--SourceCidrIp", cidr,
        *(extra if action == "Authorize" else []),
    )


def live_suite(url: str) -> bool:
    done = run(
        ["pnpm", "exec", "playwright", "test", "-c", "playwright.live.config.ts",
         "--reporter=line"],
        cwd=FRONTEND, env={**os.environ, "LIVE_URL": url}, check=False,
    )
    tail = [line for line in done.stdout.splitlines() if line.strip()][-6:]
    print("\n".join(f"    {line}" for line in tail), flush=True)
    return done.returncode == 0


def wait_public(url: str, limit: int = 60) -> None:
    deadline = time.time() + limit
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(3)
    raise rt.Stop(f"{url} not reachable within {limit}s")


# --- subcommands ----------------------------------------------------------------


INSPECT = f"""set -uo pipefail
cd {HOST_ROOT}
echo "## digests"
find src -type f -name '*.py' ! -path '*/__pycache__/*' -exec sha256sum {{}} + | sort -k2
echo "## state"
echo "dist=$([ -f {HOST_DIST}/index.html ] && echo present || echo absent)"
echo "api_dropin=$([ -f {API_DROPIN} ] && echo present || echo absent)"
unused=0
for d in {BACKUP_DIR}/*/; do [ -d "$d" ] && [ ! -e "$d/restored" ] && unused=$((unused + 1)); done
echo "backups_unrestored=$unused"
echo "port80_to=$(iptables -t nat -S PREROUTING | grep -- '--dport 80 ' | grep -o 'ports [0-9]*')"
echo "api_listen=$(ss -ltn | awk '{{print $4}}' | grep ':{API_PORT}$')"
echo "mem_available_mib=$(awk '/MemAvailable/{{print int($2/1024)}}' /proc/meminfo)"
"""


def plan_differences(host: dict[str, str], local: dict[str, str]) -> tuple[list[str], list[str]]:
    """Split source differences into the payload and anything else (which blocks)."""
    changed = sorted(f for f in local if host.get(f) != local[f])
    payload = [f for f in changed if f in API_FILES]
    other = [f for f in changed if f not in API_FILES]
    return payload, other


def inspect(args: argparse.Namespace) -> int:
    out = rt.remote(INSPECT, timeout=120)
    digests: dict[str, str] = {}
    state: dict[str, str] = {}
    section = ""
    for line in out.splitlines():
        if line.startswith("## "):
            section = line[3:]
        elif section == "digests" and line.strip():
            digest, path = line.split(maxsplit=1)
            digests[path] = digest
        elif section == "state" and "=" in line:
            k, v = line.split("=", 1)
            state[k] = v.strip()
    tracked = run(["git", "ls-files", "src/*.py"], cwd=ROOT, check=True).stdout.split()
    local = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in tracked}
    payload, other = plan_differences(digests, local)
    print(json.dumps(state, indent=1))
    print("API modules the deploy replaces:", payload or "none (already current)")
    if state.get("port80_to") != f"ports {API_PORT}":
        # Phase 2 of the Streamlit retirement: the port-80 unit itself points at
        # the API. Anything else means the host is not at the tested state.
        print(f"BLOCKED: port 80 redirects to {state.get('port80_to')!r}, "
              f"not the API on {API_PORT}")
        return 1
    if other:
        print("BLOCKED: other package source differs on the host, so it is not at the")
        print("state this deploy was tested against:")
        for f in other:
            print("   ", f)
        return 1
    print("rest of the package: identical to this checkout")
    return 0


def deploy(args: argparse.Namespace) -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    record: dict[str, Any] = {"stamp": stamp, "apply": args.apply}
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    out = RECORD_DIR / f"{stamp}.json"

    reason = market_window_reason(datetime.now(UTC))
    if reason and not args.ignore_window:
        raise rt.Stop(f"not a deploy window: {reason}")
    if inspect(args) != 0:
        raise rt.Stop("inspect found unexpected differences on the host")
    state = rt.host_state()
    down = [u for u, s in state["units"].items() if s != "active"]
    if down or not state["watchdog_ok"] or state["open_incidents"]:
        raise rt.Stop(
            f"host not healthy: down={down} watchdog={state['watchdog_failures']} "
            f"incidents={state['open_incidents']}"
        )
    payload, manifest = build_payload()
    commit = run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True).stdout.strip()
    rt.log(record, "built", commit=commit[:12], files=len(manifest), bytes=len(payload),
           chunks=len(chunks(payload)), index_sha256=manifest["frontend/dist/index.html"][:16])
    if not args.apply:
        print("\nDry run. Would: ship, install (keeping the old API and build), write the")
        if args.verify_on_port_80:
            print("API drop-in, restart the API, run the live suite on port 80. Nothing changed.")
        else:
            print(f"API drop-in, restart the API, open {API_PORT} to this machine's /32, run the")
            print(f"live suite there and on port 80, revoke {API_PORT}. Nothing changed.")
        return 0

    # --verify-on-port-80 (owner, 29 September 2026): a Cloudflare WARP client
    # reaches the host from several egress addresses, so no /32 rule can admit
    # only the operator. The host checks still gate the live suite, which
    # then runs on port 80 only, and a failure puts the previous build back.
    restricted = not args.verify_on_port_80
    record["verification"] = "operator /32 on 8600, then port 80" if restricted else "port 80 only"
    cidr = operator_cidr() if restricted else ""
    stage = "ship"
    try:
        staged = ship(payload, stamp)
        rt.log(record, "shipped", sha256=hashlib.sha256(payload).hexdigest()[:16])
        stage = "api"
        rt.remote(
            install_script(staged, stamp) + write_dropin(API_DROPIN, API_DROPIN_TEXT)
            + "\n" + RESTART_API,
            timeout=300,
        )
        checks = parse_checks(rt.remote(HOST_CHECKS, timeout=120))
        rt.log(record, "api restarted", **checks)
        if bad := check_failures(checks):
            raise rt.Stop(f"host checks failed: {bad}")

        if restricted:
            sg_rule("Authorize", cidr)
            record["sg_open"] = True
            rt.log(record, f"{API_PORT} opened to the operator's /32")
            wait_public(f"http://{EIP}:{API_PORT}/")
            if not live_suite(f"http://{EIP}:{API_PORT}"):
                raise rt.Stop(f"live suite failed on :{API_PORT}")
            rt.log(record, "live suite passed", target=f":{API_PORT}")
        else:
            rt.log(record, "restricted check skipped", reason="--verify-on-port-80")

        wait_public(f"http://{EIP}/")
        if not live_suite(f"http://{EIP}"):
            raise rt.Stop("live suite failed on port 80")
        rt.log(record, "live suite passed", target=":80")
        checks = parse_checks(rt.remote(HOST_CHECKS, timeout=120))
        if bad := check_failures(checks):
            raise rt.Stop(f"host checks failed after the port-80 suite: {bad}")
        record["result"] = "DEPLOYED"
    except (rt.Stop, subprocess.CalledProcessError, OSError) as exc:
        record["result"] = "REVERTED"
        record["error"] = str(exc)[:500]
        rt.log(record, "failed; reverting", stage=stage, error=str(exc)[:300])
        if stage == "ship":
            rt.remote(f"rm -f /root/react-deploy-{stamp}.tar.gz*", timeout=60)
        if stage == "api":
            rt.remote(revert_api_script(), timeout=300)
            rt.log(record, "previous API modules and build restored")
    finally:
        if record.get("sg_open"):
            sg_rule("Revoke", cidr)
            rt.log(record, f"{API_PORT} rule revoked")
        out.write_text(json.dumps(record, indent=2))
    print(f"\n{record['result']}  (record: {out})")
    if record["result"] == "DEPLOYED":
        print(f"React UI: http://{EIP}/   undo: deploy_react.py rollback")
    return 0 if record["result"] == "DEPLOYED" else 1


def rollback(args: argparse.Namespace) -> int:
    print(rt.remote(revert_api_script(), timeout=300).strip())
    print(f"port 80 serves the previous React build: http://{EIP}/")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inspect")
    d = sub.add_parser("deploy")
    d.add_argument("--apply", action="store_true", help="make the change; default is a dry run")
    d.add_argument("--ignore-window", action="store_true", help="deploy during the trading day")
    d.add_argument(
        "--verify-on-port-80", action="store_true",
        help="skip the operator-/32 check on 8600 (it cannot admit a WARP client); "
        "verify on port 80, restoring the previous build on failure",
    )
    sub.add_parser("rollback")
    args = parser.parse_args()
    try:
        return {"inspect": inspect, "deploy": deploy, "rollback": rollback}[args.cmd](args)
    except rt.Stop as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
