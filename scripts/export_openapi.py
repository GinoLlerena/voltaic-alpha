#!/usr/bin/env python3
"""Write the presentation API's OpenAPI document to a file.

`RUI-2`. The browser contract is generated from the server's own schema rather
than typed by hand, and the document is committed so the frontend's type check
needs no Python and no running server. A test regenerates it and fails if the
committed copy has drifted, which is what makes the generated types trustworthy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from options_alpha_lab.api.server import create_app  # noqa: E402
from options_alpha_lab.presentation.source import Source  # noqa: E402

DEFAULT = Path("frontend/openapi.json")


def document() -> dict:
    from sqlalchemy import create_engine

    root = Path(__file__).resolve().parents[1]
    # The schema does not depend on the data, so an engine that is never queried
    # is enough -- and keeps this runnable without a database.
    engine = create_engine(f"sqlite+pysqlite:///{root / 'demo' / 'h0_demo.db'}", future=True)
    app = create_app(Source(engine, "FROZEN_REPLAY", "schema export"), root=root)
    return app.openapi()


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
