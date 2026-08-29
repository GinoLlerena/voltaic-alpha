"""Deterministic exit rules and their precedence.

Closes `CLR-020`. Until this existed the system could open a position and had no
logic to ever close it, which is a worse failure than never opening one: a stuck
position also blocks every future entry through the one-open-strategy guard.

Two properties matter more than the thresholds:

* **Precedence is explicit and total.** When several conditions fire at once the
  most urgent wins, and the order is written down rather than emerging from the
  order of `if` statements.
* **`UNMEASURABLE` is an integrity state, not a precedence winner** (`EXIT-004`).
  A missing option quote cannot suppress expiry, invalidation, or the session
  stop, because none of those depend on the premium. It is recorded, it halts new
  risk, and the rules that remain computable are still evaluated.
* **A rule is only evaluated against the price series it was written for**
  (`EXIT-AC-06`). A structural invalidation is a completed-session condition -
  "close below 631.63". Judged on a partial session it answers a different
  question and answers it wrongly both ways round, so when the observed price
  cannot be matched to the rule's source the rule is skipped, reported, and
  raised as an integrity finding rather than guessed at. Its direction comes
  from the stored rule, never from the position that happens to hold it.
* **The time stop counts completed trading sessions, not DTE** (`EXIT-003`). The
  declared thesis horizon is one to three sessions; a `DTE <= 10` rule on a
  45-DTE entry permits roughly 35 calendar days, which is an expiry control
  wearing a time-stop label. Both now exist, separately.

Every threshold is `PROVISIONAL` until replay evidence is attached.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from .architecture.contracts import Direction, PriceSource, TypedInvalidation

# --- PROVISIONAL policy values ----------------------------------------------
STOP_LOSS_FRACTION_OF_DEBIT = Decimal("0.50")
PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN = Decimal("0.60")
#: Completed trading sessions since the reconciled entry fill.
SESSION_STOP = 3
EXPIRY_GUARD_DTE = 7
CONTRACT_MULTIPLIER = Decimal("100")

#: Bumped from -0 when invalidation stopped being evaluated against a price whose
#: source had not been checked. The thresholds are unchanged; the behaviour when
#: the source cannot be matched is not, so the version has to move with it.
POLICY_VERSION = "h0-exit-provisional-1"


class ExitTrigger(str, Enum):  # noqa: UP042 - matches the str-Enum style used across contracts.py
    """Ordered most urgent first. The order in this class *is* the precedence."""

    EXPIRY_GUARD = "expiry_guard"
    INVALIDATION_BREACHED = "invalidation_breached"
    STOP_LOSS = "stop_loss"
    SESSION_STOP = "session_stop"
    PROFIT_CAPTURE = "profit_capture"
    UNMEASURABLE = "unmeasurable"
    HOLD = "hold"


#: Explicit precedence, written as data so a test asserts the order rather than
#: inferring it from control flow. Matches the review's section 5.2 for the rules
#: H0 implements; scheduled-event blackout is deferred, not silently dropped.
PRECEDENCE: tuple[ExitTrigger, ...] = (
    ExitTrigger.EXPIRY_GUARD,
    ExitTrigger.INVALIDATION_BREACHED,
    ExitTrigger.STOP_LOSS,
    ExitTrigger.SESSION_STOP,
    ExitTrigger.PROFIT_CAPTURE,
)

#: Triggers that need no option premium, so a missing quote cannot suppress them.
PREMIUM_INDEPENDENT: frozenset[ExitTrigger] = frozenset(
    {ExitTrigger.EXPIRY_GUARD, ExitTrigger.INVALIDATION_BREACHED, ExitTrigger.SESSION_STOP}
)


@dataclass(frozen=True)
class ExitInputs:
    """Everything the exit policy is allowed to look at.

    `entry_debit` must be the **actual reconciled average fill**, never an
    estimate or a limit price: every economic threshold is a fraction of it.
    """

    direction: Direction
    entry_debit: Decimal
    width: Decimal
    quantity: int
    dte: int
    underlying_price: Decimal
    #: What `underlying_price` is. A completed-session rule cannot be decided by
    #: an intraday print, and refusing to try is the point of carrying this.
    underlying_source: PriceSource
    #: The stored rule itself, so its own direction and source govern - not the
    #: position's direction, which can disagree with it.
    invalidation: TypedInvalidation | None
    #: Conservative mark: what the spread could be closed for right now.
    current_value: Decimal | None
    as_of: date
    #: Completed trading sessions since the reconciled entry fill.
    sessions_elapsed: int = 0


@dataclass(frozen=True)
class ExitDecision:
    should_close: bool
    trigger: ExitTrigger
    reason: str
    policy_version: str
    unrealized: Decimal | None = None
    #: Limit price for the closing order, when one should be placed.
    suggested_limit: Decimal | None = None
    #: True when the premium could not be read. Independent rules still ran.
    value_unmeasurable: bool = False
    #: True when an invalidation rule exists but its price source could not be
    #: matched, so the rule was not evaluated. Every other rule still was.
    invalidation_unverifiable: bool = False


def max_gain(state: ExitInputs) -> Decimal:
    return state.width - state.entry_debit


def unrealized(state: ExitInputs) -> Decimal | None:
    if state.current_value is None:
        return None
    return (
        (state.current_value - state.entry_debit) * CONTRACT_MULTIPLIER * state.quantity
    ).quantize(Decimal("0.01"))


def stop_level(state: ExitInputs) -> Decimal:
    return (state.entry_debit * STOP_LOSS_FRACTION_OF_DEBIT).quantize(Decimal("0.01"))


def profit_target(state: ExitInputs) -> Decimal:
    return (
        state.entry_debit + max_gain(state) * PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN
    ).quantize(Decimal("0.01"))


def invalidation_verifiable(state: ExitInputs) -> bool:
    """Whether the recorded rule can be judged against the observed price.

    A structural invalidation is written against completed daily closes. Judging
    it on a partial session answers a different question, so when the sources do
    not match the rule is skipped and reported rather than guessed at.
    """
    if state.invalidation is None:
        return False
    return state.invalidation.evaluable_against(state.underlying_source)


def invalidation_breached(state: ExitInputs) -> bool:
    """Evaluate the stored rule, using *its* direction and *its* source."""
    if state.invalidation is None or not invalidation_verifiable(state):
        return False
    if state.invalidation.direction is not state.direction:
        # The rule and the position disagree about which way the thesis runs.
        # Evaluating either one would manage the position against a condition
        # nobody approved, so it is a fault, not a branch.
        raise ValueError(
            f"invalidation direction {state.invalidation.direction.value} disagrees "
            f"with position direction {state.direction.value}"
        )
    return state.invalidation.breached(state.underlying_price)


def evaluate_exit(state: ExitInputs) -> ExitDecision:
    """Return the single governing exit decision for a position.

    Premium-independent rules are evaluated first and are never suppressed by a
    missing quote. Only after they decline does the policy consult the premium.
    """
    pnl = unrealized(state)
    unmeasurable = state.current_value is None
    unverifiable = state.invalidation is not None and not invalidation_verifiable(state)

    def close(trigger: ExitTrigger, reason: str) -> ExitDecision:
        # Closing a debit spread is a sell. Cross the spread deliberately rather
        # than posting at the mark and hoping: an exit that does not fill is not
        # an exit. With no readable premium there is no limit to suggest, and the
        # caller must price the close from a fresh quote.
        limit = None
        if state.current_value is not None:
            limit = max(
                (state.current_value * Decimal("0.90")).quantize(Decimal("0.01")),
                Decimal("0.01"),
            )
        return ExitDecision(
            True, trigger, reason, POLICY_VERSION, pnl, limit, unmeasurable, unverifiable
        )

    # 1. Expiry guard. Overrides everything, including a profitable position:
    #    holding into expiry risks assignment and pin risk for a gain already
    #    mostly captured. Needs no premium.
    if state.dte <= EXPIRY_GUARD_DTE:
        return close(
            ExitTrigger.EXPIRY_GUARD,
            f"{state.dte} DTE is at or below the {EXPIRY_GUARD_DTE}-day expiry guard",
        )

    # 2. Invalidation. The thesis that justified the position is no longer true.
    #    Depends only on the underlying, so a missing option quote must not
    #    suppress it (EXIT-004).
    if invalidation_breached(state):
        return close(
            ExitTrigger.INVALIDATION_BREACHED,
            f"{state.underlying_source.value} {state.underlying_price} breached the "
            f"recorded invalidation level "
            f"{state.invalidation.level if state.invalidation else None}",
        )

    # 3. Stop loss. Premium-dependent; skipped, not assumed safe, when unreadable.
    stop = stop_level(state)
    if state.current_value is not None and state.current_value <= stop:
        return close(
            ExitTrigger.STOP_LOSS,
            f"value {state.current_value} is at or below the {stop} stop "
            f"({STOP_LOSS_FRACTION_OF_DEBIT} of the {state.entry_debit} filled debit)",
        )

    # 4. Session stop. Implements the declared 1-3 session horizon. Needs no premium.
    if state.sessions_elapsed >= SESSION_STOP:
        return close(
            ExitTrigger.SESSION_STOP,
            f"{state.sessions_elapsed} completed trading sessions since the entry fill "
            f"reached the {SESSION_STOP}-session horizon",
        )

    # 5. Profit capture. Premium-dependent.
    target = profit_target(state)
    if state.current_value is not None and state.current_value >= target:
        return close(
            ExitTrigger.PROFIT_CAPTURE,
            f"value {state.current_value} reached the {target} target "
            f"({PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN} of maximum gain from the filled debit)",
        )

    # 6. Nothing fired. If the premium was unreadable, say so: it is an integrity
    #    finding that must raise an incident and halt new risk, not a quiet hold.
    if unmeasurable or unverifiable:
        missing = []
        if unmeasurable:
            missing.append("the spread value could not be computed from the current chain")
        if unverifiable:
            assert state.invalidation is not None
            missing.append(
                f"the invalidation rule reads {state.invalidation.source.value} but the "
                f"observed price is {state.underlying_source.value}, so it was not evaluated"
            )
        return ExitDecision(
            False,
            ExitTrigger.UNMEASURABLE,
            "; ".join(missing)
            + ". Every rule that remained computable was evaluated and did not "
            "fire, so the position is retained under a durable integrity incident",
            POLICY_VERSION,
            pnl,
            None,
            unmeasurable,
            unverifiable,
        )

    return ExitDecision(
        False,
        ExitTrigger.HOLD,
        f"value {state.current_value} is between the {stop} stop and the "
        f"{target} target, and {state.sessions_elapsed} of {SESSION_STOP} sessions "
        "have elapsed",
        POLICY_VERSION,
        pnl,
        None,
        False,
        False,
    )


def evaluate_triggers(state: ExitInputs) -> tuple[dict[str, object], ...]:
    """Every rule in `PRECEDENCE` order with what it returned on this pass.

    `evaluate_exit` returns the winner, which is the right answer for acting and
    the wrong record for tuning. A threshold is judged by how often it nearly
    fired and on what, and a policy that stores only the evaluations that acted
    looks decisive because its silences were discarded.

    `fired` is `None` where a rule could not be evaluated at all - an unreadable
    premium, an unmatched price source - which is deliberately distinct from
    `False`. Recording those as "did not fire" is how a missing value becomes
    indistinguishable from a healthy one.
    """
    rows: list[dict[str, object]] = []

    def row(trigger: ExitTrigger, fired: bool | None, observed: str | None,
            threshold: str | None, skipped: str | None = None) -> None:
        rows.append({
            "trigger": trigger.value, "fired": fired, "observed": observed,
            "threshold": threshold, "skipped": skipped,
        })

    row(ExitTrigger.EXPIRY_GUARD, state.dte <= EXPIRY_GUARD_DTE,
        str(state.dte), str(EXPIRY_GUARD_DTE))

    if state.invalidation is None:
        row(ExitTrigger.INVALIDATION_BREACHED, False, str(state.underlying_price), None,
            "no invalidation rule is recorded for this position")
    elif not invalidation_verifiable(state):
        row(ExitTrigger.INVALIDATION_BREACHED, None, str(state.underlying_price),
            str(state.invalidation.level),
            f"rule reads {state.invalidation.source.value}; observed price is "
            f"{state.underlying_source.value}")
    else:
        row(ExitTrigger.INVALIDATION_BREACHED, invalidation_breached(state),
            str(state.underlying_price), str(state.invalidation.level))

    if state.current_value is None:
        row(ExitTrigger.STOP_LOSS, None, None, str(stop_level(state)),
            "no readable premium")
    else:
        row(ExitTrigger.STOP_LOSS, state.current_value <= stop_level(state),
            str(state.current_value), str(stop_level(state)))

    row(ExitTrigger.SESSION_STOP, state.sessions_elapsed >= SESSION_STOP,
        str(state.sessions_elapsed), str(SESSION_STOP))

    if state.current_value is None:
        row(ExitTrigger.PROFIT_CAPTURE, None, None, str(profit_target(state)),
            "no readable premium")
    else:
        row(ExitTrigger.PROFIT_CAPTURE, state.current_value >= profit_target(state),
            str(state.current_value), str(profit_target(state)))

    return tuple(rows)
