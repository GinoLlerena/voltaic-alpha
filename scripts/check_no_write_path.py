#!/usr/bin/env python3
"""Fail if the source tree can express a broker write.

This parses Python rather than grepping it. A grep cannot tell the difference
between calling ``submit_order`` and a docstring explaining why we never call
it, and a guard that punishes documentation gets deleted the first time it is
inconvenient. Only real identifier usage counts: attribute access, calls, names,
and imported symbols.

Phase 4 introduced the deterministic execution gateway, so the check is now
"no write outside the gateway" rather than "no write anywhere". The allowance is
a single named file, not a directory or a pattern, so a second write path cannot
appear by being placed next to the first one.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN = {
    "submit_order",
    "place_order",
    "close_position",
    "close_all_positions",
    "cancel_order",
    "cancel_orders",
    "replace_order",
    "exercise_option_position",
    "TradingClient",
    "MarketOrderRequest",
    "LimitOrderRequest",
    "OptionLegRequest",
}


#: The one file permitted to express a broker write. Everything else is checked.
GATEWAY = Path("src/options_alpha_lab/execution/gateway.py")


def offenders(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path == GATEWAY or path.resolve() == GATEWAY.resolve():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - a parse failure is a real failure
            found.append(f"{path}:{exc.lineno}: cannot parse ({exc.msg})")
            continue
        for node in ast.walk(tree):
            name: str | None = None
            if isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.alias):
                name = node.asname or node.name.rsplit(".", 1)[-1]
            if name in FORBIDDEN:
                found.append(f"{path}:{getattr(node, 'lineno', 0)}: {name}")
    return found


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "src")
    problems = offenders(root)
    if problems:
        print("broker write path found:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"no broker write path in {root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
