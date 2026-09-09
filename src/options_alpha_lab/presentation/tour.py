"""A six-scene guided path through recorded evidence.

`CIIP-004`. The plan asks for a guided replay that a reviewer can follow without
repository knowledge, and that can be linked to at an exact step.

What this deliberately is **not** is an auto-advancing animation. Every scene
resolves to a committed record and is navigated by the reader, which means the
tour is always paused, any step is directly reachable, restarting is free, and
there is no motion to reduce. The plan permits animated pacing rather than
requiring it, and a timed auto-advance in Streamlit would mean blocking reruns —
fragile machinery guarding a claim we would then have to keep true.

The last scene is the refusal, and that placement is the argument: a tour that
ends on a successful trade says the system works, while one that ends on a
refusal the model was never consulted for says *why* it works.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..persistence.models import Decision

#: The tab a scene wants open, by index into the dashboard's five views.
EVIDENCE, MEMO, LINEAGE, OUTCOME, GUARDS = range(5)


@dataclass(frozen=True)
class Scene:
    """One step: a case, a view, and what the reader should take from it."""

    number: int
    title: str
    snapshot_id: str
    tab: int
    narration: str


SCENES: tuple[Scene, ...] = (
    Scene(
        1,
        "What was observed",
        "spy-qualified-2026-08-27",
        EVIDENCE,
        "Every decision starts from a recorded observation carrying its provider, "
        "feed, source time and payload hash. The underlying price is the last "
        "completed daily close, never a forming bar — the system cannot see a "
        "price it would not have had.",
    ),
    Scene(
        2,
        "What the code decided before the model ran",
        "spy-qualified-2026-08-27",
        EVIDENCE,
        "A deterministic classifier chose the direction and set the invalidation "
        "conditions. Both were fixed before any model was called, and the model "
        "has no field in which to return either.",
    ),
    Scene(
        3,
        "What the model contributed",
        "spy-qualified-2026-08-27",
        MEMO,
        "The model returned a memo under a strict schema: direction, confidence, "
        "cited and counter-cited evidence, and a summary. A direction that "
        "disagrees with the setup is coerced to neutral and recorded as an "
        "attempt. This is its entire authority.",
    ),
    Scene(
        4,
        "What was authorized",
        "spy-lifecycle-20260828T154747Z",
        LINEAGE,
        "Deterministic risk sized the position and an immutable intent was "
        "recorded. The client order id is derived from the intent hash, so a "
        "duplicate submit collides at the broker instead of opening a second "
        "position.",
    ),
    Scene(
        5,
        "What Alpaca actually did",
        "spy-lifecycle-20260828T154747Z",
        OUTCOME,
        "One Paper round trip, reconciled to flat. Acknowledgement was recorded "
        "as SUBMITTED; the fills were written only from a reconciled broker "
        "record. The round trip lost money, which is on screen because a demo "
        "that shows only the winning trade is a brochure.",
    ),
    Scene(
        6,
        "What refusal looks like",
        "spy-refusal-2026-08-27",
        MEMO,
        "The setup did not qualify, so the model was never called. There is no "
        "memo to reject — the question never reached it. This costs one "
        "classifier and no tokens, and is recorded with the same evidence hashes "
        "as a trade.",
    ),
)


def scene(number: int) -> Scene:
    """Clamp to a real scene rather than raising on a hand-edited URL."""
    return SCENES[min(max(number, 1), len(SCENES)) - 1]


def resolve(session: Session, item: Scene) -> Decision | None:
    """The decision a scene points at, or `None` if the evidence set lacks it."""
    return session.scalars(
        select(Decision).where(Decision.snapshot_id == item.snapshot_id)
    ).first()


def missing_scenes(session: Session) -> list[Scene]:
    """Scenes with no backing record.

    A tour step that silently renders whatever happened to be selected is worse
    than one that admits its case is absent, so this is asserted in tests rather
    than discovered by a viewer.
    """
    return [item for item in SCENES if resolve(session, item) is None]
