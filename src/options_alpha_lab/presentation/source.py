"""Which evidence a read-only surface is showing, decided per request.

`RUI-1`. The Streamlit dashboard resolved this inside `app.py`, behind a
Streamlit cache, so a second surface would have had to re-implement it — and two
implementations of "is this live?" drift on exactly the question the product
exists to answer honestly. The dashboard and the presentation API both use
`Resolver` now, and so cannot disagree about where their data came from.

The rule is unchanged from the dashboard's: prefer the live worker database, but
never show an empty page, and never imply "live" when it is not true. A fallback
is labelled with *why* it fell back.

`RUI-VAL-006`. The first version resolved once per process, so the label's
decision count froze at startup and a dashboard started before the worker's
first decision stayed on committed evidence forever. Engines are expensive and
are built once; the *answer* is cheap -- one `COUNT` -- and is recomputed every
time it is asked for.
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


class Resolver:
    """Holds the engines; answers "which source, right now?" on every call."""

    def __init__(self, live_url: str, committed: Path) -> None:
        self._frozen = create_engine(f"sqlite+pysqlite:///{committed}", future=True)
        self._configured = bool(live_url)
        self._live: Engine | None = None
        self._live_error: str | None = None
        if live_url:
            try:
                self._live = create_engine(live_url, future=True, pool_pre_ping=True)
            except Exception as exc:  # noqa: BLE001 - a malformed URL must not break the surface
                self._live_error = type(exc).__name__

    def _fallback(self, why: str) -> Source:
        return Source(self._frozen, "FROZEN_REPLAY", f"committed evidence ({why})")

    def current(self) -> Source:
        if not self._configured:
            return Source(self._frozen, "FROZEN_REPLAY", "committed evidence")
        if self._live is None:
            return self._fallback(f"live source unavailable: {self._live_error}")
        try:
            with Session(self._live) as session:
                count = session.scalar(select(func.count()).select_from(Decision)) or 0
        except Exception as exc:  # noqa: BLE001 - a broken live source must not break the surface
            return self._fallback(f"live source unavailable: {type(exc).__name__}")
        if count:
            return Source(self._live, "LIVE", f"live worker database ({count} decisions)")
        return self._fallback("live worker has decided nothing yet")


def resolve(live_url: str, committed: Path) -> Source:
    """A one-off answer. Long-lived surfaces should hold a `Resolver`."""
    return Resolver(live_url, committed).current()
