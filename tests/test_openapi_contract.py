"""The committed OpenAPI document is the browser's contract (`RUI-2`).

The frontend generates its types from `frontend/openapi.json` rather than from a
running server, so CI can type-check the browser code without Python. That is
only trustworthy while the committed document is what the server would produce,
which is what this asserts.

It also re-asserts the read-only boundary at the contract level. The server's own
tests prove no route accepts a write; this proves the document a client generates
from cannot even describe one.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "frontend" / "openapi.json"


def _generated() -> dict:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from export_openapi import document  # noqa: PLC0415

    return document()


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.committed = json.loads(COMMITTED.read_text(encoding="utf-8"))

    def test_the_committed_document_matches_the_server(self) -> None:
        """If this fails, run scripts/export_openapi.py and regenerate the types."""
        self.assertEqual(
            self.committed, _generated(),
            "frontend/openapi.json has drifted from the API; the generated browser "
            "types describe a server that no longer exists",
        )

    def test_the_contract_publishes_only_get(self) -> None:
        methods = {m for ops in self.committed["paths"].values() for m in ops}
        self.assertEqual(methods, {"get"})

    def test_every_response_carries_an_envelope_or_is_the_proof_file(self) -> None:
        """A payload without its source could be rendered as if it were live."""
        for path, ops in self.committed["paths"].items():
            if path.endswith(".json"):
                continue  # the kept proof bytes, deliberately unenveloped
            schema = ops["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            self.assertIn("Envelope", json.dumps(schema), path)

    def test_the_generated_types_are_current(self) -> None:
        """The checked-in types must have been generated from this document."""
        types = (ROOT / "frontend" / "src" / "api" / "schema.ts").read_text(encoding="utf-8")
        for path in self.committed["paths"]:
            self.assertIn(path, types, f"{path} is missing from the generated types")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
