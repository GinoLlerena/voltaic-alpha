#!/usr/bin/env python3
"""The one way to deploy host code: ship exactly what differs, and say so first.

    python3 scripts/ship_host.py                         # dry run: every difference
    python3 scripts/ship_host.py --apply                 # ship; restart nothing
    python3 scripts/ship_host.py --apply --restart options-alpha-api
    python3 scripts/ship_host.py --apply --restart-worker   # outside the trading day only
    python3 scripts/ship_host.py --apply --migrate          # schema change; outside the day
    python3 scripts/ship_host.py --apply --install-deps     # requirements.txt changed
    python3 scripts/ship_host.py --apply --prune-junk       # remove macOS ._* files

Runs on the operator machine over Cloud Assistant (no SSH, no inbound port),
reusing `deploy_react.ship` (checksummed chunks) and `resize_trial`'s
redacting `aliyun` layer.

What belongs on the host is a list, `HOST_PATHS`, not a habit. It replaced
`deploy_worker.sh`, whose payload had no `migrations/` or `scripts/`: the host
once ran revision 0007 with 0008's file absent entirely, and drifted from the
release freeze in a dozen files (deploy-hygiene follow-ups, 21 Sep 2026).

Two layers are compared, both by sha256:

* the checkout under /opt/options-alpha, against every tracked file in
  `HOST_PATHS`;
* the installed systemd units and drop-ins under /etc/systemd/system, against
  `deploy/systemd/`.

Old copies are kept under /opt/options-alpha/.deploy-backup/<stamp>/. Files
only the host has are reported, never deleted, except macOS `._*` junk with
`--prune-junk`. Nothing is restarted unless asked; the worker and schema
migrations need their own flags and are refused during the trading day.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import deploy_react as dr
import resize_trial as rt

ROOT = Path(__file__).resolve().parents[1]
HOST = "/opt/options-alpha"
UNIT_DIR = "/etc/systemd/system"

#: Everything the host runs or serves from its checkout. Repository-only files
#: (CI, Docker, docs, tests, the frontend source) stay out; the built UI ships
#: with `deploy_react.py`.
HOST_PATHS = (
    "src", "migrations", "scripts", "deploy", "demo", "artifacts", "fixtures", ".streamlit",
    "app.py", "alembic.ini", "pyproject.toml", "requirements.txt", "README.md",
)
#: Restarted only with --restart-worker, and only outside the trading day.
WORKER = "options-alpha-worker"
#: Kept for callers of the older interface and its tests.
HOST_SCRIPTS = ("scripts/backup_database.sh",)


def tracked() -> list[str]:
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "ls-files", *HOST_PATHS],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return out.split()


def is_unit(f: str) -> bool:
    """A file installed into /etc/systemd/system as well as kept in the checkout."""
    if not f.startswith("deploy/systemd/"):
        return False
    rel = f.removeprefix("deploy/systemd/")
    return rel.endswith((".service", ".timer")) and "/" not in rel or (
        rel.endswith(".d/options-alpha.conf")
    )


def local_files() -> dict[str, str]:
    """Checkout files by path, plus installed units under the key `unit:<path>`."""
    out: dict[str, str] = {}
    for f in tracked():
        digest = hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
        out[f] = digest
        if is_unit(f):
            out[f"unit:{f}"] = digest
    return out


#: The schema revision the host's database is at.
REVISION_QUERY = "select version_num from alembic_version"

#: Where the host's services must import the package from: the checkout this
#: tool writes to. On 5 Oct 2026 `--install-deps` ran `pip install -r
#: requirements.txt`, whose last line (`.`) installs the project itself, and
#: that replaced the editable install with a copy in site-packages. Shipped
#: source stopped taking effect, and the worker could not start at all: it
#: finds alembic.ini relative to its own file. Found at the next start, a day
#: later, because the running worker had already imported the old path.
PACKAGE_DIR = f"{HOST}/src/options_alpha_lab"
WHERE = (
    "./.venv/bin/python -c "
    "'import options_alpha_lab, os; print(os.path.dirname(options_alpha_lab.__file__))'"
    " 2>/dev/null"
)

DIGESTS = f"""set -uo pipefail
cd {HOST}
find {" ".join(HOST_PATHS)} -type f ! -path '*/__pycache__/*' ! -path '*.egg-info/*' \\
  -exec sha256sum {{}} + 2>/dev/null | sort -k2
for f in {UNIT_DIR}/options-alpha*.service {UNIT_DIR}/options-alpha*.timer; do
  [ -f "$f" ] || continue
  b=$(basename "$f")
  echo "$(sha256sum "$f" | cut -d' ' -f1)  unit:deploy/systemd/$b"
done
for f in {UNIT_DIR}/*.d/options-alpha.conf; do
  [ -f "$f" ] || continue
  d=$(basename "$(dirname "$f")")
  echo "$(sha256sum "$f" | cut -d' ' -f1)  unit:deploy/systemd/$d/options-alpha.conf"
done
echo "@alembic $(sudo -u postgres psql -d options_alpha -tAc '{REVISION_QUERY}')"
echo "@package $({WHERE})"
"""


@dataclass
class Plan:
    changed: list[str] = field(default_factory=list)  # checkout files to write
    units: list[str] = field(default_factory=list)  # repo paths to install into /etc
    host_only: list[str] = field(default_factory=list)
    junk: list[str] = field(default_factory=list)
    host_revision: str = ""
    repo_head: str = ""
    #: Where the host's venv imports options_alpha_lab from.
    package: str = PACKAGE_DIR

    @property
    def editable(self) -> bool:
        """The services run this checkout's source, not a copy of it."""
        return self.package == PACKAGE_DIR

    @property
    def needs_migration(self) -> bool:
        return bool(self.repo_head) and self.host_revision != self.repo_head

    @property
    def deps_changed(self) -> bool:
        return "requirements.txt" in self.changed


def repo_head(root: Path = ROOT) -> str:
    """The single Alembic head: a revision no other revision names as its parent."""
    revisions, parents = set(), set()
    for path in (root / "migrations" / "versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision\s*[:=][^"\']*["\']([^"\']+)', text, re.M)
        down = re.search(r'^down_revision\s*[:=][^"\'\n]*["\']([^"\']+)', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            parents.add(down.group(1))
    heads = sorted(revisions - parents)
    if len(heads) != 1:
        raise rt.Stop(f"expected one migration head, found {heads}")
    return heads[0]


def compare(local: dict[str, str], host: dict[str, str]) -> Plan:
    plan = Plan()
    for key, digest in sorted(local.items()):
        if host.get(key) == digest:
            continue
        if key.startswith("unit:"):
            plan.units.append(key.removeprefix("unit:"))
        else:
            plan.changed.append(key)
    for key in sorted(host):
        if key.startswith("unit:") or key in local:
            continue
        (plan.junk if Path(key).name.startswith("._") else plan.host_only).append(key)
    return plan


def host_state() -> tuple[dict[str, str], str, str]:
    out = rt.remote(DIGESTS, timeout=180)
    files: dict[str, str] = {}
    revision = package = ""
    for line in out.splitlines():
        if line.startswith("@alembic "):
            revision = line.removeprefix("@alembic ").strip()
        elif line.startswith("@package"):
            package = line.removeprefix("@package").strip()
        elif line.strip():
            digest, path = line.split(maxsplit=1)
            files[path] = digest
    return files, revision, package


def make_plan() -> Plan:
    files, revision, package = host_state()
    plan = compare(local_files(), files)
    plan.host_revision, plan.repo_head, plan.package = revision, repo_head(), package
    return plan


MANIFEST = "__ship_manifest__"


def tarball(files: list[str], manifest: str = "") -> bytes:
    """The files, plus the install manifest, so the remote script stays small."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if manifest:
            data = manifest.encode()
            info = tarfile.TarInfo(MANIFEST)
            info.size, info.mode = len(data), 0o644
            tar.addfile(info, io.BytesIO(data))
        for f in files:
            info = tar.gettarinfo(str(ROOT / f), arcname=f)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o644
            with open(ROOT / f, "rb") as fh:
                tar.addfile(info, fh)
    return buf.getvalue()


def live_path(f: str) -> str:
    """Where an installed unit lives (or, for anything else, its checkout path)."""
    if is_unit(f):
        return f"{UNIT_DIR}/{f.removeprefix('deploy/systemd/')}"
    return f"{HOST}/{f}"


def timers_touched(files: list[str]) -> list[str]:
    """Timers to restart: changed timer units, and timers whose drop-in changed."""
    names = set()
    for f in files:
        if not f.startswith("deploy/systemd/"):
            continue
        head = f.removeprefix("deploy/systemd/").split("/")[0]
        if head.endswith(".timer"):
            names.add(head)
        elif head.endswith(".timer.d"):
            names.add(head.removesuffix(".d"))
    return sorted(names)


def manifest(plan: Plan) -> str:
    """One `mode source destination` line per file, read by the remote loop.

    Shipped inside the checksummed tarball rather than spelled out in the
    command: Cloud Assistant refuses a command over about 18 KB, and 41 files
    written out one install pair each exceeded it (CmdContent.ExceedLimit).
    """
    spaced = [f for f in plan.changed + plan.units if any(c.isspace() for c in f)]
    if spaced:
        raise rt.Stop(f"paths with whitespace cannot be shipped by the manifest: {spaced}")
    rows = [
        f"{'755' if f.endswith('.sh') else '644'} {f} {HOST}/{f}" for f in plan.changed
    ] + [f"644 {f} {live_path(f)}" for f in plan.units]
    return "\n".join(rows) + "\n"


def install(staged: str, stamp: str, plan: Plan, restart: list[str],
            *, prune_junk: bool = False) -> str:
    """A fixed-size script: the per-file work comes from the shipped manifest."""
    backup = f"{HOST}/.deploy-backup/{stamp}"
    lines = [
        "set -euo pipefail",
        f"cd {HOST}",
        f"install -d -m 700 {backup}",
        "work=$(mktemp -d)",
        f"tar -xzf {staged} -C \"$work\"",
        "while read -r mode src dest; do",
        f'  if [ -f "$dest" ]; then install -D -m 644 "$dest" "{backup}${{dest}}"; '
        f'else echo "$dest" >> {backup}/absent; fi',
        '  install -D -m "$mode" "$work/$src" "$dest"',
        f'done < "$work/{MANIFEST}"',
    ]
    if prune_junk:
        lines += [f"rm -f {HOST}/{j}" for j in plan.junk]
    lines += [f"rm -rf \"$work\" {staged}"]
    if plan.units:
        lines.append("systemctl daemon-reload")
        lines += [f"systemctl restart {t}" for t in timers_touched(plan.units)]
    lines += [f"systemctl restart {s}" for s in restart]
    count = len(plan.changed) + len(plan.units)
    lines.append(f"echo \"shipped {count} file(s); previous copies in {backup}\"")
    return "\n".join(lines) + "\n"


MIGRATE = f"""set -euo pipefail
cd {HOST}
systemctl stop {WORKER}
set -a; . /etc/options-alpha.env; set +a
./.venv/bin/alembic upgrade head 2>&1 | tail -5
echo "revision=$(sudo -u postgres psql -d options_alpha -tAc '{REVISION_QUERY}')"
systemctl start {WORKER}
"""

#: The dependencies only. The file's last line, `.`, would install the project
#: itself as a copy; the project is linked by `EDITABLE` instead.
DEPS = f"""set -euo pipefail
cd {HOST}
grep -vxF . requirements.txt | ./.venv/bin/pip install -q -r /dev/stdin 2>&1 | tail -3
"""

#: Link the venv to the checkout, so what is shipped is what runs.
EDITABLE = f"""set -euo pipefail
cd {HOST}
./.venv/bin/pip install -q --no-deps -e . 2>&1 | tail -3
echo "package=$({WHERE})"
"""


def restart_script(services: list[str]) -> str:
    return "set -euo pipefail\n" + "".join(f"systemctl restart {s}\n" for s in services)


#: Pins in requirements.txt the venv does not satisfy; empty means in step.
#: A pin whose environment marker excludes this interpreter (emscripten, win32,
#: an older Python) does not apply; reading past the marker reported three such
#: pins as off on 1 Oct while the venv was in step.
PIN_CHECK_PY = """
import re
import sys
from importlib import metadata
try:
    from packaging.markers import Marker
except ImportError:
    from pip._vendor.packaging.markers import Marker
off = []
for line in open(sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"):
    m = re.match(r"^([A-Za-z0-9_.-]+)==([^ ;#]+)\\s*(?:;([^#]*))?", line.strip())
    if not m:
        continue
    if m.group(3) and not Marker(m.group(3).strip()).evaluate():
        continue
    try:
        have = metadata.version(m.group(1))
    except metadata.PackageNotFoundError:
        have = "absent"
    if have != m.group(2):
        off.append(m.group(1) + " " + have + " (pinned " + m.group(2) + ")")
print("pins_off=" + ("; ".join(off) or "none"))
"""

PIN_CHECK = f"""set -uo pipefail
cd {HOST}
./.venv/bin/python - <<'PY'
{PIN_CHECK_PY}
PY
"""

#: Exits non-zero when the host is not running what was shipped. The worker is
#: given time to start: on 5 Oct it was checked five seconds after its restart,
#: while it was crash-looping, and `is-active` had not yet said so.
VERIFY = f"""set -uo pipefail
code() {{ curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 "$1"; }}
steady=no
for _ in $(seq 24); do
  sleep 5
  since=$(systemctl show {WORKER} -p ActiveEnterTimestampMonotonic --value)
  now=$(awk '{{print int($1 * 1000000)}}' /proc/uptime)
  if [ "$(systemctl is-active {WORKER})" = active ] && [ $((now - since)) -gt 20000000 ]; then
    steady=yes; break
  fi
done
package=$({WHERE})
echo "package=$package"
echo "api_status=$(code http://127.0.0.1:8600/api/v1/system/status)"
echo "stop_readiness=$(code http://127.0.0.1:8600/api/v1/system/stop-readiness)"
echo "worker=$(systemctl is-active {WORKER}) steady=$steady"
echo "api=$(systemctl is-active options-alpha-api)"
echo "streamlit=$(code http://127.0.0.1:8501/)"
systemctl start options-alpha-watchdog.service || true
python3 - <<'PY'
import json
try:
    w = json.load(open("/var/run/options-alpha/watchdog.json"))
except OSError:
    print("watchdog_ok=unknown (no watchdog.json: the worker's run directory is absent)")
else:
    print("watchdog_ok=" + str(w["ok"]))
    for c in w["checks"]:
        if not c["ok"]:
            print("watchdog_fail=" + c["name"] + ": " + c["detail"])
PY
if [ "$steady" != yes ]; then
  echo "VERIFY FAILED: the worker is not staying up:"
  journalctl -u {WORKER} --since "-3 min" --no-pager -o cat | grep -v '^ ' | tail -3
  exit 1
fi
if [ "$package" != "{PACKAGE_DIR}" ]; then
  echo "VERIFY FAILED: services import a copy of the package, not {PACKAGE_DIR}"
  exit 1
fi
"""


def report(plan: Plan) -> None:
    if not (plan.changed or plan.units or plan.junk) and plan.editable:
        print("the host matches this checkout")
    for title, items in (
        ("checkout files that differ or are missing", plan.changed),
        ("installed units / drop-ins that differ", plan.units),
        ("macOS junk on the host (--prune-junk removes)", plan.junk),
        ("files only the host has (reported, never deleted)", plan.host_only),
    ):
        if items:
            print(f"{title}:")
            for f in items:
                print("   ", f)
    if not plan.editable:
        print("the host's services run a COPY of the package "
              f"({plan.package or 'not importable'}), not this checkout's source: "
              "--apply re-links it (pip install -e .)")
    print(f"schema: host {plan.host_revision or '?'}, repository head {plan.repo_head}"
          + ("  <- MIGRATION NEEDED (--migrate)" if plan.needs_migration else ""))
    if plan.deps_changed:
        print("requirements.txt changes: pins are checked after shipping; --install-deps installs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restart", action="append", default=[], help="a service to restart")
    parser.add_argument("--restart-worker", action="store_true",
                        help="restart the worker (refused during the trading day)")
    parser.add_argument("--migrate", action="store_true",
                        help="stop the worker, alembic upgrade head, start it (outside the day)")
    parser.add_argument("--install-deps", action="store_true",
                        help="pip install -r requirements.txt")
    parser.add_argument("--prune-junk", action="store_true", help="delete macOS ._* files")
    parser.add_argument("--ignore-window", action="store_true",
                        help="allow the worker restart / migration during the day")
    args = parser.parse_args()

    if WORKER in args.restart:
        print("refusing: use --restart-worker for the worker", file=sys.stderr)
        return 2
    window = dr.market_window_reason(datetime.now(UTC))
    if (args.restart_worker or args.migrate) and window and not args.ignore_window:
        print(f"refusing the worker restart / migration: {window}", file=sys.stderr)
        return 2
    dirty = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty:
        print(f"refusing: tracked changes in the working tree\n{dirty}", file=sys.stderr)
        return 2
    try:
        plan = make_plan()
        report(plan)
        if plan.needs_migration and not args.migrate:
            print("\nrefusing to ship code ahead of its schema; re-run with --migrate",
                  file=sys.stderr)
            return 2 if args.apply else 0
        nothing = plan.editable and not (
            plan.changed or plan.units or (args.prune_junk and plan.junk)
        )
        if not args.apply or (nothing and not (args.migrate and plan.needs_migration)):
            if not args.apply and not nothing:
                print("\nDry run. Re-run with --apply to ship these.")
            return 0
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        files = sorted(set(plan.changed) | set(plan.units))
        if files:
            staged = dr.ship(tarball(files, manifest(plan)), stamp)
            print(rt.remote(install(staged, stamp, plan, [], prune_junk=args.prune_junk),
                            timeout=600).strip())
        # Everything a service will import is in place before any service
        # starts: dependencies, then the link to the checkout, then the schema.
        if args.install_deps:
            print(rt.remote(DEPS, timeout=600).strip())
        if args.install_deps or not plan.editable:
            print(rt.remote(EDITABLE, timeout=600).strip())
        if args.migrate and plan.needs_migration:
            print(rt.remote(MIGRATE, timeout=600).strip())
        restart = list(args.restart)
        if args.restart_worker and not (args.migrate and plan.needs_migration):
            restart.append(WORKER)
        if restart:
            rt.remote(restart_script(restart), timeout=300)
            print("restarted: " + ", ".join(restart))
        elif not plan.editable:
            print("the package was re-linked; services keep the old copy until restarted")
        if plan.deps_changed or args.install_deps:
            print(rt.remote(PIN_CHECK, timeout=120).strip())
        print(rt.remote(VERIFY, timeout=300).strip())
    except rt.Stop as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
