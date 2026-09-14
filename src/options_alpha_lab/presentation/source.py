"""Which evidence a read-only surface is showing, decided once.

`RUI-1`. The Streamlit dashboard resolved this inside `app.py`, behind a
Streamlit cache, so a second surface would have had to re-implement it — and two
implementations of "is this live?" drift on exactly the question the product
exists to answer honestly. The dashboard and the presentation API both call
`resolve` now, and so cannot disagree about where their data came from.

The rule is unchanged from the dashboard's: prefer the live worker database, but
never show an empty page, and never imply "live" when it is not true. A fallback
is labelled with *why* it fell back.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from ..persistence.models import Decision

#: `LIVE` reads the worker database. `FROZEN_REPLAY` reads committed evidence,
#: whether by configuration or by fallback; the label says which.
SourceMode = Literal["LIVE", "FROZEN_REPLAY"]


@dataclass(frozen=True)
class Source:
    engine: Engine
    mode: SourceMode
    label: str


def resolve(live_url: str, committed: Path) -> Source:
    """Prefer the live database; fall back to committed evidence, saying why."""
    frozen = create_engine(f"sqlite+pysqlite:///{committed}", future=True)
    if not live_url:
        return Source(frozen, "FROZEN_REPLAY", "committed evidence")
    try:
        live = create_engine(live_url, future=True, pool_pre_ping=True)
        with Session(live) as session:
            count = session.scalar(select(func.count()).select_from(Decision)) or 0
    except Exception as exc:  # noqa: BLE001 - a broken live source must not break the surface
        return Source(
            frozen,
            "FROZEN_REPLAY",
            f"committed evidence (live source unavailable: {type(exc).__name__})",
        )
    if count:
        return Source(live, "LIVE", f"live worker database ({count} decisions)")
    return Source(
        frozen, "FROZEN_REPLAY", "committed evidence (live worker has decided nothing yet)"
    )
