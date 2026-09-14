"""The read-only presentation API.

`RUI-1`. Every route is a GET over a read model the Streamlit dashboard already
renders; this module adds only the boundary: public DTOs, a response envelope
that always states its source, UTC timestamps, decimal strings and opaque
cursors. It holds no interpretation of its own, so it cannot disagree with the
dashboard about what a record means.

What it deliberately cannot do is as important as what it serves. It imports no
broker client, no model client and no execution module -- a test asserts that
against the live import graph -- and it has no route that accepts a body.
"""

# No `from __future__ import annotations` here, deliberately. FastAPI resolves
# string annotations against module globals, and the `Db` dependency alias is
# local to `create_app`; postponed evaluation turns every `db: Db` parameter
# into a required query field and every route into a 422.

import base64
import binascii
import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..presentation import activity, decision, explain, export, proof, status
from ..presentation.source import Source
from ..presentation.source import resolve as resolve_source
from . import dto

ROOT = Path(__file__).resolve().parents[3]
COMMITTED = ROOT / "demo" / "h0_demo.db"
DIGEST = r"^[0-9a-f]{64}$"
Digest = Annotated[str, PathParam(pattern=DIGEST, description="decision_hash hex, no prefix")]


def _encode(at: datetime, key: str) -> str:
    raw = json.dumps([at.isoformat(), key]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at, key = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(at), str(key)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="malformed cursor") from exc


def create_app(
    source: Source,
    *,
    root: Path = ROOT,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    app = FastAPI(
        title="Options Alpha presentation API",
        version="0.1.0",
        # No interactive docs on a public surface: the OpenAPI document is what a
        # client generator needs, and it is still served.
        docs_url=None,
        redoc_url=None,
    )
    api = APIRouter(prefix="/api/v1")

    def session() -> Iterator[Session]:
        with Session(source.engine) as db:
            yield db

    Db = Annotated[Session, Depends(session)]

    def envelope(data: Any, correlation_id: str | None = None) -> dict[str, Any]:
        return {
            "source_mode": source.mode,
            "source_label": source.label,
            "observed_at": dto.utc(clock()),
            "correlation_id": correlation_id,
            "data": data,
        }

    def found(db: Session, digest: str):  # type: ignore[no-untyped-def]
        row = decision.by_hash(db, f"sha256:{digest}")
        if row is None:
            raise HTTPException(status_code=404, detail="no decision with that hash")
        return row

    @api.get("/system/status", response_model=dto.Envelope[list[dto.StatusItemOut]])
    def system_status(db: Db) -> dict[str, Any]:
        items = status.system_status(db, now=clock())
        return envelope([
            dto.StatusItemOut(
                label=i.label, value=i.value, tone=i.tone, known=i.known,
                source=i.source, observed_at=dto.utc(i.observed_at), reason=i.reason,
            )
            for i in items
        ])

    @api.get("/system/proof", response_model=dto.Envelope[list[dto.ProofTileOut]])
    def system_proof(db: Db) -> dict[str, Any]:
        return envelope([
            dto.ProofTileOut(
                value=t.value, label=t.label, mode=t.mode, available=t.available,
                source=t.source, detail=t.detail,
            )
            for t in proof.proof_tiles(db, root=root)
        ])

    @api.get("/decisions", response_model=dto.Envelope[dto.DecisionPage])
    def decisions(
        db: Db,
        action: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        rows, after = decision.listing(db, action=action, limit=limit, before=_decode(cursor))
        return envelope(dto.DecisionPage(
            items=[
                dto.DecisionListItem(
                    decision_id=r.decision_hash.removeprefix("sha256:"),
                    snapshot_id=r.snapshot_id, action=r.action, direction=r.direction,
                    reason_codes=sorted(r.reason_codes or []),
                    policy_version=r.policy_version, decided_at=dto.utc(r.decided_at),
                )
                for r in rows
            ],
            next_cursor=_encode(*after) if after else None,
        ))

    @api.get("/decisions/{digest}/summary", response_model=dto.Envelope[dto.DecisionSummary])
    def decision_summary(db: Db, digest: Digest) -> dict[str, Any]:
        row = found(db, digest)
        view = decision.load(db, row)
        snap = view.snapshot
        return envelope(
            dto.DecisionSummary(
                decision_id=digest, snapshot_id=row.snapshot_id, action=row.action,
                direction=row.direction, reason_codes=sorted(row.reason_codes or []),
                input_hash=row.input_hash, decision_hash=row.decision_hash,
                policy_version=row.policy_version, decided_at=dto.utc(row.decided_at),
                observation=None if snap is None else dto.Observation(
                    symbol=snap.symbol, provider=snap.provider, feed=snap.feed,
                    source_time=dto.utc(snap.source_time),
                    received_time=dto.utc(snap.received_time),
                    underlying_price=dto.decimal(snap.underlying_price),
                    payload_hash=snap.payload_hash,
                ),
                reached_the_broker=view.reached_the_broker,
                model_was_called=view.model_was_called,
                why=[
                    dto.ExplainLineOut(
                        stage=w.stage, text=w.text, source=w.source, present=w.present
                    )
                    for w in explain.why_decision(db, row)
                ],
            ),
            correlation_id=row.decision_hash,
        )

    @api.get("/decisions/{digest}/proof", response_model=dto.Envelope[dto.ProofOut])
    def decision_proof(db: Db, digest: Digest) -> dict[str, Any]:
        row = found(db, digest)
        view = decision.load(db, row)
        return envelope(
            dto.ProofOut(manifest_digest=export.digest(view), manifest=export.manifest(view)),
            correlation_id=row.decision_hash,
        )

    @api.get(
        "/proof/{digest}.json",
        response_class=Response,
        responses={200: {"content": {"application/json": {}}}},
    )
    def proof_file(db: Db, digest: Digest) -> Response:
        """The manifest as the exact bytes a reviewer keeps.

        Deliberately not enveloped: wrapping would change the bytes and so the
        digest, and the digest is the thing a reviewer checks.
        """
        view = decision.load(db, found(db, digest))
        return Response(
            content=export.render(view),
            media_type="application/json",
            headers={
                "X-Proof-Digest": export.digest(view),
                "Content-Disposition": f'attachment; filename="proof-{digest[:16]}.json"',
            },
        )

    @api.get("/activity", response_model=dto.Envelope[dto.ActivityPage])
    def system_activity(
        db: Db,
        limit: Annotated[int, Query(ge=1, le=200)] = 40,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        events, after = activity.page(db, limit=limit, before=_decode(cursor))
        return envelope(dto.ActivityPage(
            items=[
                dto.ActivityEventOut(
                    correlation_id=e.correlation_id, sequence=e.sequence, stage=e.stage,
                    outcome=e.outcome, component=e.component,
                    reason_codes=list(e.reason_codes), occurred_at=dto.utc(e.occurred_at),
                    refused=e.refused,
                )
                for e in events
            ],
            next_cursor=_encode(*after) if after else None,
        ))

    @api.get("/worker/events", response_model=dto.Envelope[dto.WorkerEventsOut])
    def worker_events(
        db: Db,
        limit: Annotated[int, Query(ge=1, le=200)] = 40,
        faults_only: bool = False,
    ) -> dict[str, Any]:
        if not activity.worker_events_recorded(db):
            return envelope(dto.WorkerEventsOut(
                available=False,
                reason="this source predates worker event recording (migration 0004)",
                items=[],
            ))
        read = activity.worker_faults if faults_only else activity.worker_events
        out = []
        for e in read(db, limit=limit):
            detail = {k: v for k, v in e.detail.items() if k in dto.WORKER_DETAIL_ALLOWLIST}
            out.append(dto.WorkerEventOut(
                event=e.event, kind=e.kind, occurred_at=dto.utc(e.occurred_at),
                detail=detail,
                withheld=sorted(k for k in e.detail if k not in dto.WORKER_DETAIL_ALLOWLIST),
            ))
        return envelope(dto.WorkerEventsOut(available=True, reason=None, items=out))

    app.include_router(api)
    return app


def build_app() -> FastAPI:
    """The deployed configuration: the dashboard's SELECT-only credential.

    `RUI-VAL-002`. The API reads `DASHBOARD_DATABASE_URL`, the same read-only role
    the dashboard uses, and never `DATABASE_URL`, which is the worker's.
    """
    live_url = os.environ.get("DASHBOARD_DATABASE_URL", "").strip()
    return create_app(resolve_source(live_url, COMMITTED))
