#!/usr/bin/env python3
"""Produce the release freeze manifest.

Phase 7 freezes code, configuration, prompts, policy, and demo data. A freeze
that is only a promise is worth nothing, so this records a SHA-256 for every
tracked file in those categories. Re-running it after any edit changes the
manifest digest, which is what makes "we froze it" checkable rather than
asserted.

Credential files are excluded by construction: only files tracked by git are
hashed, and .env has never been tracked.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

OUTPUT = Path("artifacts/release_freeze.json")

CATEGORIES = {
    "code": ("src/", "app.py", "scripts/"),
    "configuration": ("pyproject.toml", "uv.lock", ".streamlit/", "docker-compose.yml",
                      "Dockerfile", ".github/", ".env.example"),
    "prompts": ("src/options_alpha_lab/providers/openai_thesis.py",),
    "policy": ("src/options_alpha_lab/components.py", "src/options_alpha_lab/evidence.py",
               "src/options_alpha_lab/config.py"),
    "demo_data": ("fixtures/", "demo/", "artifacts/h0_paper_lifecycle.json"),
}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def digest(path: str) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    files = tracked_files()
    if any(name == ".env" or name.endswith("/.env") for name in files):
        print("ABORT: .env is tracked", file=sys.stderr)
        return 1

    manifest: dict[str, object] = {
        "manifest_version": "release_freeze.v1",
        "frozen_at": datetime.now(UTC).isoformat(),
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "categories": {},
    }

    categories: dict[str, dict[str, str]] = {}
    for category, prefixes in CATEGORIES.items():
        entries = {
            name: digest(name)
            for name in files
            if any(name == p or name.startswith(p) for p in prefixes)
        }
        categories[category] = dict(sorted(entries.items()))
    manifest["categories"] = categories

    combined = hashlib.sha256()
    for category in sorted(categories):
        for name, value in categories[category].items():
            combined.update(f"{name}:{value}\n".encode())
    manifest["freeze_digest"] = "sha256:" + combined.hexdigest()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for category in sorted(categories):
        print(f"  {category:14} {len(categories[category])} file(s)")
    print(f"\nfreeze digest {manifest['freeze_digest']}")
    print(f"written to    {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
