"""Record what a research harness was given and what it answered.

`CIIP-3`'s `evaluation_runs` was deliberately left unbuilt while nothing could
fill it. Two harnesses now can — `sensitivity` and `gate_study` — and until this
existed their numbers lived only in prose. A threshold changed next week would
have left no record of the previous answer, against which dataset, at which
revision, which is exactly the failure this project guards against elsewhere.

Two rules shape what is stored.

**A dataset is identified by its bytes.** The manifest carries the file's
SHA-256, not its path and a promise. Two runs that disagree are then either
disagreeing about the same data or about different data, and it is decidable
which.

**What a run does not answer is named.** `CIIP-3` also asks for folds, costs,
stress and regime slices. None of those has been designed, so every run lists
them in `not_covered`. A row with those columns empty would read as a run that
considered them and found nothing to say; naming them says no one has designed
that yet, which is the truth.

Nothing reads this table. It is a record, not an input: no decision path, and no
part of the execution gateway, consults it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .persistence.models import EvaluationRun

#: `CIIP-3` dimensions that no harness here designs yet. Named on every run.
NOT_COVERED = (
    "folds",
    "costs",
    "stress",
    "regime_slices",
    "uncertainty",
)


def code_revision(root: Path | None = None) -> str:
    """The commit the harness ran at, or an honest marker when unknown.

    A run recorded from a dirty tree says so. "Reproducible at revision X" is
    false if X is not what actually ran, and a suffix is cheaper than the
    argument that would follow discovering it later.
    """
    where = root or Path(__file__).resolve().parents[2]
    try:
        # Constant argv, with the directory passed as `cwd` rather than
        # interpolated into the command: nothing here is built from input.
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=where,
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=where,
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    return f"{rev}-dirty" if dirty else rev


def dataset_manifest(path: Path, **facts: Any) -> dict[str, Any]:
    """A dataset named by its digest, so two runs can be compared honestly."""
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "bytes": len(data),
        **facts,
    }


def record(
    session: Session,
    *,
    harness: str,
    dataset: dict[str, Any],
    parameters: dict[str, Any],
    outputs: dict[str, Any],
    not_covered: tuple[str, ...] = NOT_COVERED,
) -> EvaluationRun:
    """Append one run. Nothing is updated in place; runs accumulate."""
    run = EvaluationRun(
        id=uuid.uuid4().hex,
        harness=harness,
        code_revision=code_revision(),
        dataset_manifest=dataset,
        # Round-tripped through JSON so a Decimal or a date cannot be stored by
        # one backend and rejected by another.
        parameters=json.loads(json.dumps(parameters, default=str)),
        outputs=json.loads(json.dumps(outputs, default=str)),
        not_covered=list(not_covered),
    )
    session.add(run)
    session.flush()
    return run


def history(session: Session, harness: str) -> list[EvaluationRun]:
    """Every run of one harness, oldest first, so answers can be compared."""
    return list(
        session.query(EvaluationRun)
        .filter(EvaluationRun.harness == harness)
        .order_by(EvaluationRun.recorded_at)
        .all()
    )
