"""Inventory every installed dependency's licence, and refuse copyleft at runtime.

`HK-008` asks for a tagged baseline **and** a dependency licence inventory, and
the second half did not exist. That gap mattered more than bookkeeping: the
event requires submissions to be MIT-compliant, and MIT compliance is a claim
about the whole dependency tree, not about this repository's own LICENSE file.
A single strong-copyleft package in the runtime set would make the claim false,
and nothing was checking.

Runtime and development dependencies are separated on purpose. A GPL test
runner does not affect what is distributed; a GPL library imported by the worker
does. The exit status reflects the runtime set only, so the check fails for the
reason that actually matters rather than for tidiness.

Licence text is read from installed metadata: PEP 639 `License-Expression`
first, then the legacy `License` field, then trove classifiers. Anything that
cannot be resolved is reported as `UNKNOWN` and counted as a finding, because a
licence nobody can name is not evidence of compliance.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Matched against the resolved licence string, upper-cased; the first hit wins.
#:
#: Weak copyleft is tested **before** strong, which looks backwards and is not.
#: These are substring tests, and `LGPL-3.0-only` contains `GPL-3`: ordering the
#: stronger obligation first classified psycopg, an LGPL library, as GPL and
#: would have reported two false blocking findings. `AGPL` is unaffected because
#: it matches no weak needle and falls through to strong.
CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("WEAK_COPYLEFT", (
        "LGPL", "LESSER GENERAL PUBLIC",
        "MPL", "MOZILLA PUBLIC", "EPL", "ECLIPSE PUBLIC", "CDDL",
    )),
    ("STRONG_COPYLEFT", (
        "AGPL", "AFFERO", "GPL-3", "GPLV3", "GPL-2", "GPLV2",
        # Spelled out, which is how trove classifiers write it. Without these a
        # package declaring "GNU General Public License" fell through to
        # UNKNOWN - reported as merely unresolved rather than blocking, which
        # is the more dangerous way for a compliance check to be wrong.
        "GENERAL PUBLIC LICENSE", "GENERAL PUBLIC LICENCE",
    )),
    ("PERMISSIVE", (
        "MIT", "BSD", "APACHE", "ISC", "PYTHON SOFTWARE FOUNDATION", "PSF",
        "ZLIB", "UNLICENSE", "CC0", "HPND", "0BSD",
    )),
)
#: A bare "GPL" with nothing after it. Weak copyleft is already consumed above,
#: and the lookbehind stops `LGPL` matching a second time through this path.
BARE_GPL = re.compile(r"(?<![A-Z])GPL\b")


@dataclass
class Package:
    name: str
    version: str
    licence: str
    category: str
    runtime: bool
    source: str


@dataclass
class Inventory:
    packages: list[Package] = field(default_factory=list)

    def by_category(self, runtime_only: bool = False) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for p in self.packages:
            if runtime_only and not p.runtime:
                continue
            out.setdefault(p.category, []).append(f"{p.name} {p.version}")
        return {k: sorted(v) for k, v in sorted(out.items())}


def declared() -> tuple[set[str], set[str]]:
    """Direct runtime and development requirement names, normalised."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())

    def names(items: list[str]) -> set[str]:
        return {
            re.split(r"[<>=!\[;\s]", item.strip())[0].lower().replace("_", "-")
            for item in items
            if item.strip() and not item.strip().startswith("#")
        }

    runtime = names(data.get("project", {}).get("dependencies", []))
    dev: set[str] = set()
    for group in data.get("dependency-groups", {}).values():
        dev |= names([g for g in group if isinstance(g, str)])
    return runtime, dev


def classify(licence: str) -> str:
    text = licence.upper()
    for category, needles in CATEGORIES:
        if any(needle in text for needle in needles):
            return category
    if BARE_GPL.search(text):
        return "STRONG_COPYLEFT"
    return "UNKNOWN"


def licence_of(dist: metadata.Distribution) -> tuple[str, str]:
    """Resolve a licence string and say where it came from."""
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression and expression.strip():
        return expression.strip(), "License-Expression"
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::") and "OSI Approved" not in c.split("::")[-1]
    ]
    if classifiers:
        return "; ".join(sorted(set(classifiers))), "Classifier"
    legacy = meta.get("License")
    if legacy and legacy.strip() and len(legacy.strip()) < 200:
        return legacy.strip(), "License"
    if legacy and legacy.strip():
        # Some projects paste the whole licence text into the field.
        first = legacy.strip().splitlines()[0]
        return first[:120], "License (first line)"
    return "UNKNOWN", "unresolved"


def build() -> Inventory:
    runtime_names, dev_names = declared()
    inventory = Inventory()
    seen: set[str] = set()
    for dist in metadata.distributions():
        name = (dist.metadata.get("Name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        key = name.lower().replace("_", "-")
        licence, source = licence_of(dist)
        inventory.packages.append(Package(
            name=name,
            version=dist.version,
            licence=licence,
            category=classify(licence),
            # Transitive packages are treated as runtime unless they are only
            # reachable from a dev requirement: assuming otherwise would let a
            # copyleft transitive dependency hide behind a dev parent.
            runtime=key in runtime_names or key not in dev_names,
            source=source,
        ))
    inventory.packages.sort(key=lambda p: p.name.lower())
    return inventory


def render(inv: Inventory) -> str:
    runtime = [p for p in inv.packages if p.runtime]
    dev = [p for p in inv.packages if not p.runtime]
    findings = [
        p for p in runtime if p.category in ("STRONG_COPYLEFT", "UNKNOWN")
    ]
    lines = [
        "# Dependency licence inventory",
        "",
        "Evidence for `HK-008`. The event requires submissions to be "
        "MIT-compliant, and that is a claim about the whole dependency tree "
        "rather than about this repository's own `LICENSE`.",
        "",
        f"- packages installed: **{len(inv.packages)}**",
        f"- reachable at runtime: **{len(runtime)}**",
        f"- development only: **{len(dev)}**",
        "",
        "## Runtime, by licence category",
        "",
        "| Category | Packages |",
        "|---|---:|",
    ]
    for category, names in inv.by_category(runtime_only=True).items():
        lines.append(f"| `{category}` | {len(names)} |")
    lines += [
        "",
        "## Findings",
        "",
        (
            "**None.** No runtime dependency carries a strong-copyleft licence, "
            "and every runtime licence resolved to a named licence."
            if not findings
            else "The following runtime dependencies need a decision:"
        ),
        "",
    ]
    for p in findings:
        lines.append(f"- `{p.name} {p.version}` — {p.licence} (`{p.category}`)")
    weak = [p for p in runtime if p.category == "WEAK_COPYLEFT"]
    if weak:
        lines += [
            "## Weak copyleft at runtime, and why it is compatible",
            "",
            "Reported rather than waved through, and not gated, because these "
            "obligations do not reach this repository's own MIT-licensed source:",
            "",
        ]
        for p in weak:
            lines.append(f"- `{p.name} {p.version}` — {p.licence}")
        lines += [
            "",
            "- **MPL-2.0** is file-level copyleft. Its obligations attach to the "
            "MPL files themselves and to modifications of them. These packages "
            "are used unmodified, so nothing propagates outward.",
            "- **LGPL-3.0** attaches to the library. `psycopg` is imported "
            "through its ordinary Python interface and installed unmodified from "
            "PyPI by the user running `uv sync`; this repository neither "
            "modifies it nor redistributes it.",
            "",
            "This is engineering documentation, not a legal opinion. If the "
            "organizers read MIT-compliance as excluding any copyleft in the "
            "dependency tree, `psycopg` is the one to revisit - it is the "
            "PostgreSQL driver, and swapping it is a real change rather than a "
            "note.",
            "",
        ]

    lines += [
        "",
        "## Every package",
        "",
        "| Package | Version | Licence | Category | Scope |",
        "|---|---|---|---|---|",
    ]
    for p in inv.packages:
        scope = "runtime" if p.runtime else "dev"
        lines.append(
            f"| `{p.name}` | {p.version} | {p.licence} | `{p.category}` | {scope} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--json", default="artifacts/dependency_licenses.json")
    parser.add_argument("--markdown", default="artifacts/dependency_licenses.md")
    args = parser.parse_args(argv)

    inv = build()
    runtime = [p for p in inv.packages if p.runtime]
    blocking = [p for p in runtime if p.category == "STRONG_COPYLEFT"]
    unknown = [p for p in runtime if p.category == "UNKNOWN"]

    payload = {
        "generated_for": "HK-008",
        "packages_installed": len(inv.packages),
        "runtime_packages": len(runtime),
        "runtime_by_category": inv.by_category(runtime_only=True),
        "strong_copyleft_at_runtime": [p.name for p in blocking],
        "unresolved_at_runtime": [p.name for p in unknown],
        "packages": [
            {
                "name": p.name, "version": p.version, "licence": p.licence,
                "category": p.category, "runtime": p.runtime, "source": p.source,
            }
            for p in inv.packages
        ],
    }
    for path, body in (
        (args.json, json.dumps(payload, indent=2) + "\n"),
        (args.markdown, render(inv)),
    ):
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    print(f"{len(inv.packages)} packages, {len(runtime)} reachable at runtime")
    for category, names in inv.by_category(runtime_only=True).items():
        print(f"  {category:18} {len(names)}")
    if blocking:
        print("\nSTRONG COPYLEFT at runtime:", ", ".join(p.name for p in blocking))
    if unknown:
        print("unresolved at runtime:", ", ".join(p.name for p in unknown))
    # Only the runtime set gates: a copyleft test runner is not distributed.
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
