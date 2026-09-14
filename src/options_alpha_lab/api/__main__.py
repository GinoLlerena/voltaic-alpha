"""`python -m options_alpha_lab.api` -- serve the presentation API.

Binds to loopback by default. Exposing it is a deployment decision, made in a
unit file, not a default a developer inherits by running the module.
"""

from __future__ import annotations

import os

import uvicorn

from .server import build_app


def main() -> None:
    uvicorn.run(
        build_app(),
        host=os.environ.get("PRESENTATION_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("PRESENTATION_API_PORT", "8600")),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
