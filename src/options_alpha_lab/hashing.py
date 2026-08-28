"""Canonical hashing for the evidence-to-intent lineage.

The project's central claim is that every decision can be reconstructed from
recorded inputs. That requires one canonical serialization: two runs over the
same inputs must produce the same digest, and any change to an input must change
it. Ordering, whitespace, and numeric formatting are therefore pinned here rather
than left to whatever ``json.dumps`` defaults happen to be.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, Decimal):
        # Normalized so that 1.50 and 1.5 cannot produce different digests.
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("refusing to hash a naive datetime")
        # Always UTC: local time would make digests machine-dependent.
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        raise TypeError(
            "refusing to hash a float; use Decimal so the digest is exact and reproducible"
        )
    raise TypeError(f"cannot canonicalize {type(value).__name__}")


def canonical_json(payload: Any) -> str:
    """Serialize deterministically: sorted keys, no insignificant whitespace."""
    return json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"))


def payload_hash(payload: Any) -> str:
    """Return the ``sha256:`` prefixed digest of a canonical serialization."""
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
