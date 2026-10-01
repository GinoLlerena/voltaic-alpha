#!/usr/bin/env python3
"""Ship the package source and systemd units that differ from the host, and nothing else.

    python3 scripts/ship_host.py                      # dry run: what differs
    python3 scripts/ship_host.py --apply --restart options-alpha-api

Runs on the operator machine over Cloud Assistant, reusing `deploy_react.ship`
(checksummed chunks) and `resize_trial`'s redacting `aliyun` layer.

The payload is computed, not chosen: every tracked file under `src/` and
`deploy/systemd/` whose digest differs from the host's copy, or that the host
lacks. The dry run lists it, so what is reviewed is what ships. Old copies are
kept under /opt/options-alpha/.deploy-backup/<stamp>/.

Only the named services are restarted. The worker is never restarted by this
tool: its source changes take effect at its next start, which the scheduled
stop makes routine.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import deploy_react as dr
import resize_trial as rt

ROOT = Path(__file__).resolve().parents[1]
HOST = "/opt/options-alpha"
UNIT_DIR = "/etc/systemd/system"
NEVER_RESTART = {"options-alpha-worker"}
#: Scripts the units run, shipped with them. Other operator scripts are not
#: host files and stay out (deploy-hygiene follow-up).
HOST_SCRIPTS = ("scripts/backup_database.sh",)

DIGESTS = f"""set -uo pipefail
cd {HOST}
find src -type f \\( -name '*.py' -o -name '*.json' \\) ! -path '*/__pycache__/*' \\
  ! -path '*.egg-info/*' -exec sha256sum {{}} + | sort -k2
for f in {UNIT_DIR}/options-alpha*.service {UNIT_DIR}/options-alpha*.timer; do
  [ -f "$f" ] && echo "$(sha256sum "$f" | cut -d' ' -f1)  deploy/systemd/$(basename "$f")"
done
for f in {UNIT_DIR}/*.d/options-alpha.conf; do
  [ -f "$f" ] || continue
  d=$(basename "$(dirname "$f")")
  echo "$(sha256sum "$f" | cut -d' ' -f1)  deploy/systemd/$d/options-alpha.conf"
done
for f in {" ".join(HOST_SCRIPTS)}; do
  [ -f "$f" ] && sha256sum "$f"
done
"""


def local_files() -> dict[str, str]:
    tracked = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "ls-files", "src", "deploy/systemd", *HOST_SCRIPTS],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    wanted = [
        f for f in tracked
        if f.endswith((".py", ".json", ".service", ".timer", ".sh"))
        or (f.startswith("deploy/systemd/") and f.endswith(".d/options-alpha.conf"))
    ]
    return {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in wanted}


def host_files() -> dict[str, str]:
    out = rt.remote(DIGESTS, timeout=120)
    pairs = (line.split(maxsplit=1) for line in out.splitlines() if line.strip())
    return {path: digest for digest, path in pairs}


def plan() -> list[str]:
    local, host = local_files(), host_files()
    return sorted(f for f, digest in local.items() if host.get(f) != digest)


def tarball(files: list[str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in files:
            info = tar.gettarinfo(str(ROOT / f), arcname=f)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o644
            with open(ROOT / f, "rb") as fh:
                tar.addfile(info, fh)
    return buf.getvalue()


def live_path(f: str) -> str:
    """Where a shipped file lives on the host."""
    if f.startswith("deploy/systemd/"):
        rel = f.removeprefix("deploy/systemd/")
        return f"{UNIT_DIR}/{rel}"
    return f"{HOST}/{f}"


def timers_touched(files: list[str]) -> list[str]:
    """Timers to restart: changed timer units, and timers whose drop-in changed."""
    names = set()
    for f in files:
        if not f.startswith("deploy/systemd/"):
            continue
        rel = f.removeprefix("deploy/systemd/")
        head = rel.split("/")[0]
        if head.endswith(".timer"):
            names.add(head)
        elif head.endswith(".timer.d"):
            names.add(head.removesuffix(".d"))
    return sorted(names)


def install(staged: str, stamp: str, files: list[str], restart: list[str]) -> str:
    backup = f"{HOST}/.deploy-backup/{stamp}"
    units = [f for f in files if f.startswith("deploy/systemd/")]
    lines = [
        "set -euo pipefail",
        f"cd {HOST}",
        f"install -d -m 700 {backup}",
        "work=$(mktemp -d)",
        f"tar -xzf {staged} -C \"$work\"",
    ]
    for f in files:
        live = live_path(f)
        mode = "755" if f in HOST_SCRIPTS else "644"
        lines += [
            f"if [ -f {live} ]; then install -D -m 644 {live} {backup}/{f}; "
            f"else echo {f} >> {backup}/absent; fi",
            f"install -D -m {mode} \"$work\"/{f} {live}",
        ]
        if f not in units:
            # The repository copy of a unit is shipped as well, so the host's
            # checkout matches the tree it was installed from.
            continue
        lines.append(f"install -D -m 644 \"$work\"/{f} {HOST}/{f}")
    lines += [f"rm -rf \"$work\" {staged}", "systemctl daemon-reload"]
    for timer in timers_touched(files):
        lines.append(f"systemctl restart {timer}")
    for service in restart:
        lines.append(f"systemctl restart {service}")
    lines.append(f"echo \"shipped {len(files)} file(s); previous copies in {backup}\"")
    return "\n".join(lines) + "\n"


VERIFY = """set -uo pipefail
sleep 5
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1"; }
echo "api_status=$(code http://127.0.0.1:8600/api/v1/system/status)"
echo "stop_readiness=$(code http://127.0.0.1:8600/api/v1/system/stop-readiness)"
echo "worker=$(systemctl is-active options-alpha-worker)"
echo "api=$(systemctl is-active options-alpha-api)"
echo "streamlit=$(code http://127.0.0.1:8501/)"
timer=options-alpha-backup-offsite.timer
echo "offsite_timer_next=$(systemctl show -p NextElapseUSecRealtime --value $timer)"
systemctl start options-alpha-watchdog.service || true
python3 - <<'PY'
import json
w = json.load(open("/var/run/options-alpha/watchdog.json"))
print("watchdog_ok=" + str(w["ok"]))
for c in w["checks"]:
    if not c["ok"]:
        print("watchdog_fail=" + c["name"] + ": " + c["detail"])
PY
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restart", action="append", default=[], help="a service to restart")
    args = parser.parse_args()
    if set(args.restart) & NEVER_RESTART:
        print("refusing: this tool never restarts the worker", file=sys.stderr)
        return 2
    dirty = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty:
        print(f"refusing: tracked changes in the working tree\n{dirty}", file=sys.stderr)
        return 2
    try:
        files = plan()
        print("differs from the host:" if files else "the host already matches this checkout")
        for f in files:
            print("   ", f)
        if not files or not args.apply:
            if files:
                print("\nDry run. Re-run with --apply to ship these.")
            return 0
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        staged = dr.ship(tarball(files), stamp)
        print(rt.remote(install(staged, stamp, files, args.restart), timeout=300).strip())
        print(rt.remote(VERIFY, timeout=300).strip())
    except rt.Stop as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
