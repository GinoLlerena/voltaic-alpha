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

from .architecture.contracts import Direction

# --- PROVISIONAL policy values ----------------------------------------------
STOP_LOSS_FRACTION_OF_DEBIT = Decimal("0.50")
PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN = Decimal("0.60")
#: Completed trading sessions since the reconciled entry fill.
SESSION_STOP = 3
EXPIRY_GUARD_DTE = 7
CONTRACT_MULTIPLIER = Decimal("100")

POLICY_VERSION = "h0-exit-provisional-0"


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
    invalidation_level: Decimal | None
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


def max_gain(state: ExitInputs) -> Decimal:
    return state.width - state.entry_debit


def unrealized(state: ExitInputs) -> Decimal | None:
    if state.current_value is None:
        return None
    return (
        (state.current_value - state.entry_debit) * CONTRACT_MULTIPLIER * state.quantity
    ).quantize(Decimal("0.01"))


def invalidation_breached(state: ExitInputs) -> bool:
    if state.invalidation_level is None:
        return False
    if state.direction is Direction.BULLISH:
        return state.underlying_price <= state.invalidation_level
    return state.underlying_price >= state.invalidation_level


def evaluate_exit(state: ExitInputs) -> ExitDecision:
    """Return the single governing exit decision for a position.

    Premium-independent rules are evaluated first and are never suppressed by a
    missing quote. Only after they decline does the policy consult the premium.
    """
    pnl = unrealized(state)
    unmeasurable = state.current_value is None

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
        return ExitDecision(True, trigger, reason, POLICY_VERSION, pnl, limit, unmeasurable)

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
            f"underlying {state.underlying_price} breached the recorded "
            f"invalidation level {state.invalidation_level}",
        )

    # 3. Stop loss. Premium-dependent; skipped, not assumed safe, when unreadable.
    stop_level = (state.entry_debit * STOP_LOSS_FRACTION_OF_DEBIT).quantize(Decimal("0.01"))
    if state.current_value is not None and state.current_value <= stop_level:
        return close(
            ExitTrigger.STOP_LOSS,
            f"value {state.current_value} is at or below the {stop_level} stop "
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
    target = (
        state.entry_debit + max_gain(state) * PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN
    ).quantize(Decimal("0.01"))
    if state.current_value is not None and state.current_value >= target:
        return close(
            ExitTrigger.PROFIT_CAPTURE,
            f"value {state.current_value} reached the {target} target "
            f"({PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN} of maximum gain from the filled debit)",
        )

    # 6. Nothing fired. If the premium was unreadable, say so: it is an integrity
    #    finding that must raise an incident and halt new risk, not a quiet hold.
    if unmeasurable:
        return ExitDecision(
            False,
            ExitTrigger.UNMEASURABLE,
            "spread value could not be computed from the current chain; expiry, "
            "invalidation, and session rules were evaluated and did not fire, so "
            "the position is retained under a durable integrity incident",
            POLICY_VERSION,
            None,
            None,
            True,
        )

    return ExitDecision(
        False,
        ExitTrigger.HOLD,
        f"value {state.current_value} is between the {stop_level} stop and the "
        f"{target} target, and {state.sessions_elapsed} of {SESSION_STOP} sessions "
        "have elapsed",
        POLICY_VERSION,
        pnl,
        None,
        False,
    )
