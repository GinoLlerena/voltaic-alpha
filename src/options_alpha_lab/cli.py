from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import case_from_dict
from .orchestrator import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an agent interaction experiment")
    parser.add_argument("fixture", type=Path, help="Path to an experiment JSON fixture")
    args = parser.parse_args()

    raw = json.loads(args.fixture.read_text(encoding="utf-8"))
    result = run_experiment(case_from_dict(raw))
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()

