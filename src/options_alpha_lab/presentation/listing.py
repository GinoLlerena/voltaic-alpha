"""The decision list: which decisions a reader is shown, grouped how, pinned why.

`RUI-1`. This was presentation logic inside `app.py`, where only one surface
could perform it. Extracting it exposed two defects the page had carried.

`RUI-VAL-009`. Runs were keyed on `(action, reason codes)`, and a position has
no reason codes, so consecutive positions shared a key. The default "Notable"
view -- documented as "every position, plus one representative of each run of
identical refusals" -- merged them. On the committed evidence it listed three
entries instead of five: the bullish and bearish qualified cases collapsed into
one "bearish x2", and the lifecycle decision, the one carrying the real Paper
round trip, was hidden behind "live x2". A position is its own story; only
identical refusals are one fact repeated.

`RUI-VAL-009` also broke the guided tour. A scene selected its decision only if
the current view listed it and otherwise fell back to the first entry, so five
of six scenes narrated one decision over another. A scene's decision is now
pinned into every view, and `Listing.pin_missing` reports a scene whose decision
the source does not contain at all, so the page can say so instead of
substituting.

Entries are newest first in every view. The previous order was an accident of
run grouping and was neither chronological nor intended.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

View = Literal["Notable", "Positions", "Refusals", "Everything"]
VIEWS: tuple[View, ...] = ("Notable", "Positions", "Refusals", "Everything")

POSITION = "OPTIONS_POSITION"


def outcome_key(decision: Any) -> tuple[str, str]:
    """What makes two decisions the same story.

    Identical refusals are one fact repeated. Two positions never are: each has
    its own structure, risk and lifecycle, so its key is its own hash.
    """
    if decision.action == POSITION:
        return decision.action, decision.decision_hash
    return decision.action, ", ".join(decision.reason_codes or [])


@dataclass(frozen=True)
class Entry:
    decision: Any
    #: How many consecutive identical outcomes this entry stands for.
    count: int
    #: Every member of the run, oldest first. `decision` is one of them.
    members: tuple[Any, ...]

    @property
    def label(self) -> str:
        d = self.decision
        name = d.snapshot_id.replace("spy-", "SPY ").replace("-", " ")
        if d.action == POSITION:
            summary = f"position · {d.direction}"
        else:
            summary = ", ".join(d.reason_codes or ["refused"])
        repeat = f"  ×{self.count}" if self.count > 1 else ""
        return f"{name}\n{summary}{repeat}"


@dataclass(frozen=True)
class Listing:
    entries: tuple[Entry, ...]
    #: Decisions the view considered, before grouping.
    candidates: int
    #: True when grouping hid at least one decision.
    grouped: bool
    #: A pin was requested and the source holds no such decision.
    pin_missing: bool


def _runs(items: Sequence[Any]) -> list[list[Any]]:
    runs: list[list[Any]] = []
    for decision in items:
        if runs and outcome_key(runs[-1][-1]) == outcome_key(decision):
            runs[-1].append(decision)
        else:
            runs.append([decision])
    return runs


def build(
    decisions: Sequence[Any], view: View = "Notable", *, pin: Any = None
) -> Listing:
    """Group `decisions` (oldest first) for `view`, keeping `pin` visible.

    `pin` is a decision the reader must be able to see -- a tour scene's case.
    In "Notable" it replaces its run's representative; under a filter that
    excludes it, it is listed anyway, because a scene that cannot show its own
    decision is the failure this exists to prevent.
    """
    if view == "Positions":
        candidates = [d for d in decisions if d.action == POSITION]
    elif view == "Refusals":
        candidates = [d for d in decisions if d.action != POSITION]
    else:
        candidates = list(decisions)

    entries: list[Entry] = []
    for run in _runs(candidates):
        members = tuple(run)
        if view == "Notable":
            shown = pin if pin is not None and pin in members else members[-1]
            entries.append(Entry(shown, len(members), members))
        else:
            entries.extend(Entry(m, 1, members) for m in members)

    pin_missing = False
    if pin is not None and all(e.decision is not pin for e in entries):
        if pin in decisions:
            entries.append(Entry(pin, 1, (pin,)))
        else:
            pin_missing = True

    order = {id(d): i for i, d in enumerate(decisions)}
    entries.sort(key=lambda e: order.get(id(e.decision), -1), reverse=True)
    return Listing(
        entries=tuple(entries),
        candidates=len(candidates),
        grouped=any(e.count > 1 for e in entries),
        pin_missing=pin_missing,
    )
