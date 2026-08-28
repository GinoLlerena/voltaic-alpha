"""Exit rules and their precedence. Closes CLR-020."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from options_alpha_lab.architecture.contracts import Direction
from options_alpha_lab.exits import (
    EXPIRY_GUARD_DTE,
    PRECEDENCE,
    ExitTrigger,
    PositionState,
    evaluate_exit,
    unrealized,
)

TODAY = date(2026, 8, 28)


def position(**overrides: object) -> PositionState:
    base = dict(
        direction=Direction.BULLISH,
        entry_debit=Decimal("3.00"),
        width=Decimal("5.00"),
        quantity=1,
        dte=25,
        underlying_price=Decimal("641.25"),
        invalidation_level=Decimal("631.63"),
        current_value=Decimal("3.10"),
        as_of=TODAY,
    )
    base.update(overrides)
    return PositionState(**base)  # type: ignore[arg-type]


class PrecedenceTests(unittest.TestCase):
    def test_precedence_is_declared_as_data(self) -> None:
        # Written down rather than emerging from the order of if statements.
        self.assertEqual(
            PRECEDENCE,
            (
                ExitTrigger.EXPIRY_GUARD,
                ExitTrigger.UNMEASURABLE,
                ExitTrigger.STOP_LOSS,
                ExitTrigger.INVALIDATION_BREACHED,
                ExitTrigger.PROFIT_CAPTURE,
                ExitTrigger.TIME_STOP,
            ),
        )

    def test_expiry_guard_beats_a_profitable_position(self) -> None:
        # Holding into expiry for a gain already mostly captured adds assignment
        # and pin risk for very little.
        decision = evaluate_exit(position(dte=EXPIRY_GUARD_DTE, current_value=Decimal("4.90")))
        self.assertIs(decision.trigger, ExitTrigger.EXPIRY_GUARD)
        self.assertTrue(decision.should_close)

    def test_expiry_guard_beats_a_stop_loss(self) -> None:
        decision = evaluate_exit(position(dte=3, current_value=Decimal("0.50")))
        self.assertIs(decision.trigger, ExitTrigger.EXPIRY_GUARD)

    def test_stop_loss_beats_profit_capture_when_both_are_expressible(self) -> None:
        # Ordering check: a value at the stop can never be read as a target.
        decision = evaluate_exit(position(current_value=Decimal("1.50")))
        self.assertIs(decision.trigger, ExitTrigger.STOP_LOSS)


class TriggerTests(unittest.TestCase):
    def test_stop_loss_at_half_the_entry_debit(self) -> None:
        self.assertIs(
            evaluate_exit(position(current_value=Decimal("1.50"))).trigger,
            ExitTrigger.STOP_LOSS,
        )
        self.assertIs(
            evaluate_exit(position(current_value=Decimal("1.51"))).trigger, ExitTrigger.HOLD
        )

    def test_profit_capture_at_sixty_percent_of_max_gain(self) -> None:
        # max gain = 5.00 - 3.00 = 2.00; target = 3.00 + 1.20 = 4.20
        self.assertIs(
            evaluate_exit(position(current_value=Decimal("4.20"))).trigger,
            ExitTrigger.PROFIT_CAPTURE,
        )
        self.assertIs(
            evaluate_exit(position(current_value=Decimal("4.19"))).trigger, ExitTrigger.HOLD
        )

    def test_time_stop_fires_before_the_expiry_guard_range(self) -> None:
        self.assertIs(evaluate_exit(position(dte=10)).trigger, ExitTrigger.TIME_STOP)
        self.assertIs(evaluate_exit(position(dte=11)).trigger, ExitTrigger.HOLD)

    def test_invalidation_breach_closes_a_bullish_position(self) -> None:
        decision = evaluate_exit(position(underlying_price=Decimal("631.00")))
        self.assertIs(decision.trigger, ExitTrigger.INVALIDATION_BREACHED)

    def test_invalidation_breach_is_mirrored_for_a_bearish_position(self) -> None:
        decision = evaluate_exit(
            position(
                direction=Direction.BEARISH,
                invalidation_level=Decimal("650.00"),
                underlying_price=Decimal("651.00"),
            )
        )
        self.assertIs(decision.trigger, ExitTrigger.INVALIDATION_BREACHED)
        # The same price must NOT trigger for a bullish position.
        self.assertIs(
            evaluate_exit(
                position(invalidation_level=Decimal("650.00"), underlying_price=Decimal("651.00"))
            ).trigger,
            ExitTrigger.HOLD,
        )

    def test_hold_when_nothing_fires(self) -> None:
        decision = evaluate_exit(position())
        self.assertFalse(decision.should_close)
        self.assertIs(decision.trigger, ExitTrigger.HOLD)


class UnmeasurableTests(unittest.TestCase):
    def test_missing_value_flags_for_review_rather_than_assuming_health(self) -> None:
        decision = evaluate_exit(position(current_value=None))
        self.assertIs(decision.trigger, ExitTrigger.UNMEASURABLE)
        self.assertFalse(decision.should_close)
        self.assertIn("review", decision.reason)

    def test_expiry_guard_still_closes_even_when_unmeasurable(self) -> None:
        # Not knowing the value is not a reason to hold into expiry.
        decision = evaluate_exit(position(dte=2, current_value=None))
        self.assertIs(decision.trigger, ExitTrigger.EXPIRY_GUARD)
        self.assertTrue(decision.should_close)


class ArithmeticTests(unittest.TestCase):
    def test_unrealized_is_in_dollars_not_points(self) -> None:
        self.assertEqual(unrealized(position(current_value=Decimal("3.50"))), Decimal("50.00"))
        self.assertEqual(unrealized(position(current_value=Decimal("2.50"))), Decimal("-50.00"))

    def test_unrealized_scales_with_quantity(self) -> None:
        self.assertEqual(
            unrealized(position(current_value=Decimal("3.50"), quantity=3)), Decimal("150.00")
        )

    def test_closing_limit_crosses_the_spread_rather_than_posting_at_the_mark(self) -> None:
        decision = evaluate_exit(position(current_value=Decimal("1.00")))
        assert decision.suggested_limit is not None
        self.assertLess(decision.suggested_limit, Decimal("1.00"))

    def test_closing_limit_never_goes_to_zero(self) -> None:
        decision = evaluate_exit(position(dte=2, current_value=Decimal("0.01")))
        assert decision.suggested_limit is not None
        self.assertGreaterEqual(decision.suggested_limit, Decimal("0.01"))


if __name__ == "__main__":
    unittest.main()
