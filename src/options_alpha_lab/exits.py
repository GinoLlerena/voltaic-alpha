"""Deterministic exit rules and their precedence.

Closes `CLR-020`. Until this existed the system could open a position and had no
logic to ever close it, which is a worse failure than never opening one: a stuck
position also blocks every future entry through the one-open-strategy guard.

Two properties matter more than the thresholds:

* **Precedence is explicit and total.** When several conditions fire at once the
  most urgent wins, and the order is written down rather than emerging from the
  order of `if` statements.
* **A missing input never means "hold".** If the current value of the spread
  cannot be computed, the position is marked for review rather than silently
  left open, because "we could not measure it" and "it is fine" are different
  answers.

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
TIME_STOP_DTE = 10
EXPIRY_GUARD_DTE = 7
CONTRACT_MULTIPLIER = Decimal("100")

POLICY_VERSION = "h0-exit-provisional-0"


class ExitTrigger(str, Enum):  # noqa: UP042 - matches the str-Enum style used across contracts.py
    """Ordered most urgent first. The order in this class *is* the precedence."""

    EXPIRY_GUARD = "expiry_guard"
    UNMEASURABLE = "unmeasurable"
    STOP_LOSS = "stop_loss"
    INVALIDATION_BREACHED = "invalidation_breached"
    PROFIT_CAPTURE = "profit_capture"
    TIME_STOP = "time_stop"
    HOLD = "hold"


#: Explicit precedence. Written as data so a test can assert the order rather
#: than inferring it from control flow.
PRECEDENCE: tuple[ExitTrigger, ...] = (
    ExitTrigger.EXPIRY_GUARD,
    ExitTrigger.UNMEASURABLE,
    ExitTrigger.STOP_LOSS,
    ExitTrigger.INVALIDATION_BREACHED,
    ExitTrigger.PROFIT_CAPTURE,
    ExitTrigger.TIME_STOP,
)


@dataclass(frozen=True)
class PositionState:
    """Everything the exit policy is allowed to look at."""

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


@dataclass(frozen=True)
class ExitDecision:
    should_close: bool
    trigger: ExitTrigger
    reason: str
    policy_version: str
    unrealized: Decimal | None = None
    #: Limit price for the closing order, when one should be placed.
    suggested_limit: Decimal | None = None


def max_gain(state: PositionState) -> Decimal:
    return state.width - state.entry_debit


def unrealized(state: PositionState) -> Decimal | None:
    if state.current_value is None:
        return None
    return (
        (state.current_value - state.entry_debit) * CONTRACT_MULTIPLIER * state.quantity
    ).quantize(Decimal("0.01"))


def invalidation_breached(state: PositionState) -> bool:
    if state.invalidation_level is None:
        return False
    if state.direction is Direction.BULLISH:
        return state.underlying_price <= state.invalidation_level
    return state.underlying_price >= state.invalidation_level


def evaluate_exit(state: PositionState) -> ExitDecision:
    """Return the single governing exit decision for a position."""
    pnl = unrealized(state)

    def close(trigger: ExitTrigger, reason: str) -> ExitDecision:
        # Closing a debit spread is a sell. Cross the spread deliberately rather
        # than posting at the mark and hoping: an exit that does not fill is not
        # an exit.
        limit = None
        if state.current_value is not None:
            limit = max(
                (state.current_value * Decimal("0.90")).quantize(Decimal("0.01")),
                Decimal("0.01"),
            )
        return ExitDecision(True, trigger, reason, POLICY_VERSION, pnl, limit)

    # 1. Expiry guard. Overrides everything, including a profitable position:
    #    holding a spread into expiry risks assignment and pin risk for a gain
    #    that is already mostly captured.
    if state.dte <= EXPIRY_GUARD_DTE:
        return close(
            ExitTrigger.EXPIRY_GUARD,
            f"{state.dte} DTE is at or below the {EXPIRY_GUARD_DTE}-day expiry guard",
        )

    # 2. Unmeasurable. Ranked above the profit and loss rules on purpose: not
    #    knowing the value is a reason to act, not a reason to wait.
    if state.current_value is None:
        return ExitDecision(
            False,
            ExitTrigger.UNMEASURABLE,
            "spread value could not be computed from the current chain; "
            "position flagged for operator review rather than assumed healthy",
            POLICY_VERSION,
            None,
            None,
        )

    # 3. Stop loss.
    stop_level = (state.entry_debit * STOP_LOSS_FRACTION_OF_DEBIT).quantize(Decimal("0.01"))
    if state.current_value <= stop_level:
        return close(
            ExitTrigger.STOP_LOSS,
            f"value {state.current_value} is at or below the {stop_level} stop "
            f"({STOP_LOSS_FRACTION_OF_DEBIT} of the {state.entry_debit} entry debit)",
        )

    # 4. Invalidation. The thesis that justified the position is no longer true.
    if invalidation_breached(state):
        return close(
            ExitTrigger.INVALIDATION_BREACHED,
            f"underlying {state.underlying_price} breached the recorded "
            f"invalidation level {state.invalidation_level}",
        )

    # 5. Profit capture.
    target = (
        state.entry_debit + max_gain(state) * PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN
    ).quantize(Decimal("0.01"))
    if state.current_value >= target:
        return close(
            ExitTrigger.PROFIT_CAPTURE,
            f"value {state.current_value} reached the {target} target "
            f"({PROFIT_CAPTURE_FRACTION_OF_MAX_GAIN} of maximum gain)",
        )

    # 6. Time stop.
    if state.dte <= TIME_STOP_DTE:
        return close(
            ExitTrigger.TIME_STOP,
            f"{state.dte} DTE is at or below the {TIME_STOP_DTE}-day time stop",
        )

    return ExitDecision(
        False,
        ExitTrigger.HOLD,
        f"value {state.current_value} is between the {stop_level} stop and the "
        f"{target} target, and {state.dte} DTE is above the {TIME_STOP_DTE}-day stop",
        POLICY_VERSION,
        pnl,
        None,
    )
