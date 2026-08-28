from __future__ import annotations

import argparse
import json
import os
import tempfile
from getpass import getpass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
REQUIRED_KEYS = ("OPENAI_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")


def _secret(prompt: str) -> str:
    value = getpass(prompt).strip()
    if not value:
        raise ValueError("A required credential was left empty.")
    if "\n" in value or "\r" in value:
        raise ValueError("Credentials cannot contain line breaks.")
    return value


def render_env(values: Mapping[str, str]) -> str:
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise ValueError(f"Missing required credentials: {', '.join(missing)}")

    lines = [
        "# Generated locally by scripts/configure_secrets.py",
        "# Never commit or paste this file into chat.",
        f"OPENAI_API_KEY={json.dumps(values['OPENAI_API_KEY'])}",
        f"ALPACA_API_KEY={json.dumps(values['ALPACA_API_KEY'])}",
        f"ALPACA_SECRET_KEY={json.dumps(values['ALPACA_SECRET_KEY'])}",
        "ALPACA_PAPER_TRADE=true",
        "ALPACA_TRADING_ENABLED=false",
        "",
    ]
    return "\n".join(lines)


def write_env(path: Path, content: str, *, overwrite: bool) -> None:
    path = path.resolve()
    if path.exists() and not overwrite:
        raise FileExistsError(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def configuration_status(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {key: False for key in REQUIRED_KEYS}

    configured = {key: False for key in REQUIRED_KEYS}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in configured:
            configured[key] = bool(value.strip().strip('"').strip("'"))
    return configured


def _print_status(path: Path) -> int:
    status = configuration_status(path)
    print(f"Configuration file: {path}")
    for key, is_set in status.items():
        print(f"{key}: {'configured' if is_set else 'missing'}")
    print("ALPACA_PAPER_TRADE: true")
    print("ALPACA_TRADING_ENABLED: false")
    return 0 if all(status.values()) else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Securely configure local OpenAI and Alpaca Paper credentials."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report whether required values exist without displaying them.",
    )
    args = parser.parse_args()

    if args.check:
        raise SystemExit(_print_status(DEFAULT_ENV_PATH))

    print("Inputs are hidden and will not be displayed.")
    values = {
        "OPENAI_API_KEY": _secret("OpenAI API key: "),
        "ALPACA_API_KEY": _secret("Alpaca Paper API key: "),
        "ALPACA_SECRET_KEY": _secret("Alpaca Paper secret key: "),
    }

    overwrite = False
    if DEFAULT_ENV_PATH.exists():
        answer = input(".env already exists. Replace it? [y/N]: ").strip().lower()
        overwrite = answer in {"y", "yes"}
        if not overwrite:
            print("No changes made.")
            return

    write_env(DEFAULT_ENV_PATH, render_env(values), overwrite=overwrite)
    print(f"Saved credentials to {DEFAULT_ENV_PATH} with owner-only permissions.")
    print("Paper mode is enabled and trading remains disabled.")

