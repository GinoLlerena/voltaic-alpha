"""The strategy catalog: candidates, the policy versions they run under, and the
promotion decisions that move them.

`CIIP-009`. The competitors' strategy-lifecycle vocabulary, made into records
rather than adopted as language. A candidate that exists only as a name in a
README cannot be argued with; one with a hypothesis, a parameter-set hash and a
state that only moves by a recorded decision can.

Two rules give the lifecycle its meaning, and both are enforced here rather than
described:

**A state change is a decision, not an assignment.** `promote` refuses a
transition the lifecycle does not allow, and every accepted transition returns
the `PromotionDecision` that justified it. A candidate cannot drift forward
because some code set a field.

**State grants nothing.** Reaching `PAPER_ACTIVE` does not create execution
authority: the gateway consults approved intents and its own guards, and has
never heard of this module. A test asserts the import graph, because the sentence
is worth nothing if a later change quietly wires the two together.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CandidateState(str, Enum):  # noqa: UP042 - matches the str-Enum style used project-wide
    PROPOSED = "PROPOSED"
    TESTING = "TESTING"
    CHALLENGED = "CHALLENGED"
    ELIGIBLE = "ELIGIBLE"
    PAPER_SHADOW = "PAPER_SHADOW"
    PAPER_ACTIVE = "PAPER_ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


#: The lifecycle, exactly as `CIIP-3` draws it. Rejection is reachable from every
#: state before paper trading, because a candidate that cannot be rejected late
#: is a candidate nobody can argue against once it has momentum.
TRANSITIONS: dict[CandidateState, frozenset[CandidateState]] = {
    CandidateState.PROPOSED: frozenset({CandidateState.TESTING, CandidateState.REJECTED}),
    CandidateState.TESTING: frozenset({CandidateState.CHALLENGED, CandidateState.REJECTED}),
    CandidateState.CHALLENGED: frozenset({CandidateState.ELIGIBLE, CandidateState.REJECTED}),
    CandidateState.ELIGIBLE: frozenset({CandidateState.PAPER_SHADOW, CandidateState.REJECTED}),
    CandidateState.PAPER_SHADOW: frozenset(
        {CandidateState.PAPER_ACTIVE, CandidateState.PAUSED, CandidateState.REJECTED}
    ),
    CandidateState.PAPER_ACTIVE: frozenset({CandidateState.PAUSED, CandidateState.RETIRED}),
    CandidateState.PAUSED: frozenset({CandidateState.PAPER_ACTIVE, CandidateState.RETIRED}),
    #: Terminal. A retired or rejected candidate is re-proposed as a new one, so
    #: its record keeps saying what was decided about it and when.
    CandidateState.RETIRED: frozenset(),
    CandidateState.REJECTED: frozenset(),
}

#: States in which a candidate may inform Paper trading at all. Being here is
#: necessary and nowhere near sufficient: the gateway's own guards still apply,
#: and nothing in this module can produce an approved intent.
TRADING_STATES = frozenset({CandidateState.PAPER_SHADOW, CandidateState.PAPER_ACTIVE})


class TransitionError(Exception):
    """A transition the lifecycle does not allow."""


@dataclass(frozen=True)
class Transition:
    """An accepted move, and the decision that justified it."""

    candidate_id: str
    from_state: CandidateState
    to_state: CandidateState
    rationale: str
    decided_by: str
    policy_version: str


def allowed(current: CandidateState) -> frozenset[CandidateState]:
    return TRANSITIONS[current]


def check(current: CandidateState, target: CandidateState) -> None:
    """Raise unless the lifecycle allows `current -> target`."""
    if target == current:
        raise TransitionError(f"{current.value} is already the state")
    permitted = TRANSITIONS[current]
    if target not in permitted:
        allowed_names = ", ".join(sorted(s.value for s in permitted)) or "nothing"
        raise TransitionError(
            f"{current.value} may move to {allowed_names}, not {target.value}"
        )


def promote(
    *,
    candidate_id: str,
    current: CandidateState,
    target: CandidateState,
    rationale: str,
    decided_by: str,
    policy_version: str,
) -> Transition:
    """Accept a transition, or refuse it.

    Every argument is required, including the rationale and who decided: a
    promotion without a reason recorded beside it is the thing this catalog
    exists to prevent.
    """
    check(current, target)
    if not rationale.strip():
        raise TransitionError("a promotion must record why")
    if not decided_by.strip():
        raise TransitionError("a promotion must record who decided")
    return Transition(
        candidate_id=candidate_id,
        from_state=current,
        to_state=target,
        rationale=rationale.strip(),
        decided_by=decided_by.strip(),
        policy_version=policy_version,
    )
