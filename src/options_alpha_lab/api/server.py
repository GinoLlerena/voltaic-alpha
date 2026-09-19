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

from ..presentation import (
    activity,
    book,
    decision,
    explain,
    export,
    horizons,
    listing,
    proof,
    status,
    tour,
)
from ..presentation import copy as public_copy
from ..presentation.source import Resolver, Source
from . import dto, views

ROOT = Path(__file__).resolve().parents[3]
COMMITTED = ROOT / "demo" / "h0_demo.db"
DIGEST = r"^[0-9a-f]{64}$"
VIEW_PATTERN = "^(" + "|".join(listing.VIEWS) + ")$"
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
    source: Source | Resolver,
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

    def current() -> Source:
        # A fixed `Source` is for tests; a `Resolver` answers per request, so
        # the label and the mode are never older than the response (RUI-VAL-006).
        return source.current() if isinstance(source, Resolver) else source

    # One answer per request, carried on the session itself: the rows a response
    # contains and the source its envelope names must be the same source, even if
    # the answer changes between two requests.
    def session() -> Iterator[Session]:
        chosen = current()
        with Session(chosen.engine) as db:
            db.info["source"] = chosen
            yield db

    Db = Annotated[Session, Depends(session)]

    def envelope(
        db: Session, data: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        chosen: Source = db.info["source"]
        return {
            "source_mode": chosen.mode,
            "source_label": chosen.label,
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
        return envelope(db, [
            dto.StatusItemOut(
                label=i.label, value=i.value, tone=i.tone, known=i.known,
                source=i.source, observed_at=dto.utc(i.observed_at), reason=i.reason,
            )
            for i in items
        ])

    @api.get("/system/proof", response_model=dto.Envelope[list[dto.ProofTileOut]])
    def system_proof(db: Db) -> dict[str, Any]:
        return envelope(db, [
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
        return envelope(db, dto.DecisionPage(
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

    #: The dashboard bounds its list the same way (app.DECISION_LIMIT).
    LIST_LIMIT = 400

    @api.get("/decisions/grouped", response_model=dto.Envelope[dto.DecisionListOut])
    def decisions_grouped(
        db: Db,
        view: Annotated[str, Query(pattern=VIEW_PATTERN)] = "Notable",
        pin: Annotated[str | None, Query(pattern=DIGEST)] = None,
    ) -> dict[str, Any]:
        """The sidebar list: grouped, filtered and pinned exactly as the page does it."""
        recent, _ = decision.listing(db, limit=LIST_LIMIT)
        oldest_first = list(reversed(recent))
        pinned = next(
            (d for d in oldest_first if d.decision_hash == f"sha256:{pin}"), None
        ) if pin else None
        built = listing.build(oldest_first, view, pin=pinned)  # type: ignore[arg-type]
        # A pin outside the bounded page is reported missing, not silently dropped.
        pin_missing = built.pin_missing or (pin is not None and pinned is None)

        def hex_id(d: Any) -> str:
            return str(d.decision_hash).removeprefix("sha256:")

        return envelope(db, dto.DecisionListOut(
            view=view,  # type: ignore[arg-type]
            entries=[
                dto.ListEntryOut(
                    decision_id=hex_id(e.decision), snapshot_id=e.decision.snapshot_id,
                    action=e.decision.action, direction=e.decision.direction, label=e.label,
                    count=e.count, member_ids=[hex_id(m) for m in e.members],
                )
                for e in built.entries
            ],
            shown=len(built.entries), total=decision.count(db),
            grouped=built.grouped, pin_missing=pin_missing,
        ))

    @api.get("/copy", response_model=dto.Envelope[dto.CopyOut])
    def authority_copy(db: Db) -> dict[str, Any]:
        return envelope(db, dto.CopyOut(
            what_this_is=public_copy.WHAT_THIS_IS,
            disclosures=list(public_copy.DISCLOSURES),
            write_guards=[
                dto.RuleOut(name=r.name, effect=r.effect) for r in public_copy.WRITE_GUARDS
            ],
            write_guards_note=public_copy.WRITE_GUARDS_NOTE,
            model_limits=[
                dto.RuleOut(name=r.name, effect=r.effect) for r in public_copy.MODEL_LIMITS
            ],
            halt_states=[
                dto.HaltStateOut(
                    state=h.state, tone=h.tone, explanation=h.explanation  # type: ignore[arg-type]
                )
                for h in public_copy.HALT_STATES
            ],
        ))

    @api.get("/decisions/{digest}/summary", response_model=dto.Envelope[dto.DecisionSummary])
    def decision_summary(db: Db, digest: Digest) -> dict[str, Any]:
        row = found(db, digest)
        view = decision.load(db, row)
        snap = view.snapshot
        return envelope(db,
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

    def scoped(db: Session, digest: str) -> tuple[Any, decision.DecisionView]:
        row = found(db, digest)
        return row, decision.load(db, row)

    @api.get("/outcomes", response_model=dto.Envelope[dto.ReviewOverviewOut])
    def review_overview(db: Db) -> dict[str, Any]:
        """`CIIP-008`'s evidence, as counts. No rate is served because none is
        available: see `presentation/horizons.py`."""
        view = horizons.overview(db)
        return envelope(db, dto.ReviewOverviewOut(
            horizons=[
                dto.HorizonCountsOut(
                    horizon=h.horizon, sessions=h.sessions, resolved=h.resolved,
                    pending=h.pending, trades=h.trades, refusals=h.refusals,
                    agreed=h.agreed, disagreed=h.disagreed, unanswerable=h.unanswerable,
                    with_realized=h.with_realized,
                    smallest_move=dto.decimal(h.smallest_move),
                    largest_move=dto.decimal(h.largest_move),
                )
                for h in view.horizons
            ],
            decisions=view.decisions, decisions_reviewed=view.decisions_reviewed,
            closes_observed=view.closes_observed,
            positions_ever=view.positions_ever, resolved=view.resolved,
            pending=view.pending, caveat=view.caveat,
        ))

    @api.get(
        "/decisions/{digest}/outcomes",
        response_model=dto.Envelope[list[dto.DecisionHorizonOut]],
    )
    def decision_outcomes(db: Db, digest: Digest) -> dict[str, Any]:
        row = found(db, digest)
        return envelope(db, [
            dto.DecisionHorizonOut(
                horizon=h.horizon, sessions=h.sessions, state=h.state, resolved=h.resolved,
                underlying_at_decision=dto.decimal(h.underlying_at_decision),
                underlying_at_horizon=dto.decimal(h.underlying_at_horizon),
                change=dto.decimal(h.change), direction_agreed=h.direction_agreed,
                realized=dto.decimal(h.realized),
                observed_snapshot_id=h.observed_snapshot_id,
            )
            for h in horizons.for_decision(db, row)
        ], correlation_id=row.decision_hash)

    @api.get("/decisions/{digest}/market", response_model=dto.Envelope[dto.MarketOut])
    def decision_market(db: Db, digest: Digest) -> dict[str, Any]:
        row, view = scoped(db, digest)
        return envelope(db, views.market(view), correlation_id=row.decision_hash)

    @api.get("/decisions/{digest}/memo", response_model=dto.Envelope[dto.MemoOut])
    def decision_memo(db: Db, digest: Digest) -> dict[str, Any]:
        row, view = scoped(db, digest)
        return envelope(db, views.memo(view), correlation_id=row.decision_hash)

    @api.get("/decisions/{digest}/structure", response_model=dto.Envelope[dto.StructureOut])
    def decision_structure(db: Db, digest: Digest) -> dict[str, Any]:
        row, view = scoped(db, digest)
        return envelope(db, views.structure(view), correlation_id=row.decision_hash)

    @api.get("/decisions/{digest}/risk", response_model=dto.Envelope[dto.RiskOut])
    def decision_risk(db: Db, digest: Digest) -> dict[str, Any]:
        row, view = scoped(db, digest)
        return envelope(db, views.risk(view), correlation_id=row.decision_hash)

    @api.get("/decisions/{digest}/lifecycle", response_model=dto.Envelope[dto.LifecycleOut])
    def decision_lifecycle(db: Db, digest: Digest) -> dict[str, Any]:
        row, view = scoped(db, digest)
        return envelope(db, views.lifecycle(db, view, root=root), correlation_id=row.decision_hash)

    @api.get("/incidents", response_model=dto.Envelope[list[dto.IncidentOut]])
    def incidents(
        db: Db, state: Annotated[str, Query(pattern="^(open|all)$")] = "open"
    ) -> dict[str, Any]:
        rows = book.incidents(db, open_only=state == "open")
        return envelope(db, [views.incident(i) for i in rows])

    @api.get("/tour", response_model=dto.Envelope[list[dto.SceneOut]])
    def guided_tour(db: Db) -> dict[str, Any]:
        out = []
        for item in tour.SCENES:
            row = tour.resolve(db, item)
            out.append(dto.SceneOut(
                number=item.number, title=item.title, narration=item.narration, tab=item.tab,
                snapshot_id=item.snapshot_id,
                decision_id=row.decision_hash.removeprefix("sha256:") if row else None,
            ))
        return envelope(db, out)

    @api.get("/decisions/{digest}/proof", response_model=dto.Envelope[dto.ProofOut])
    def decision_proof(db: Db, digest: Digest) -> dict[str, Any]:
        row = found(db, digest)
        view = decision.load(db, row)
        return envelope(db,
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
        return envelope(db, dto.ActivityPage(
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
            return envelope(db, dto.WorkerEventsOut(
                available=False,
                reason="this source predates worker event recording (migration 0004)",
                items=[],
            ))
        read = activity.worker_faults if faults_only else activity.worker_events
        out = []
        for e in read(db, limit=limit):
            # dto.scalar also keeps the no-float rule for any numeric detail value.
            detail = {
                k: dto.scalar(v) for k, v in e.detail.items() if k in dto.WORKER_DETAIL_ALLOWLIST
            }
            out.append(dto.WorkerEventOut(
                event=e.event, kind=e.kind, occurred_at=dto.utc(e.occurred_at),
                detail=detail,
                withheld=sorted(k for k in e.detail if k not in dto.WORKER_DETAIL_ALLOWLIST),
            ))
        return envelope(db, dto.WorkerEventsOut(available=True, reason=None, items=out))

    app.include_router(api)
    return app


def build_app() -> FastAPI:
    """The deployed configuration: the dashboard's SELECT-only credential.

    `RUI-VAL-002`. The API reads `DASHBOARD_DATABASE_URL`, the same read-only role
    the dashboard uses, and never `DATABASE_URL`, which is the worker's.
    """
    live_url = os.environ.get("DASHBOARD_DATABASE_URL", "").strip()
    return create_app(Resolver(live_url, COMMITTED))
