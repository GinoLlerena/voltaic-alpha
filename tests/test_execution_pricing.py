"""The entry limit has to be a price the market will actually trade at.

On 2026-08-31 the live worker submitted a SPY 765/775 call debit spread at a
4.93 limit and the order sat untouched until its deadline cancelled it. The
quotes it priced from came from Alpaca's `indicative` feed, which the account
is limited to because it has not signed the OPRA agreement, and that feed had
the 765 call 8 cents below where it was trading and the 775 call 14 cents above.
Both errors push the computed debit down, so the order went out below the real
market and could not fill.

These tests pin the numbers from that session so the regression cannot come
back quietly, and hold the invariant that matters more than fillability: what
risk approves is still an upper bound on what can be paid.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from decimal import Decimal

from options_alpha_lab.architecture.contracts import OptionQuoteSnapshot, OptionType
from options_alpha_lab.components import (
    CONTRACT_MULTIPLIER,
    EXECUTION_ALLOWANCE_FRACTION,
    crossing_debit,
)

# The two legs as the indicative feed reported them at 13:51:49Z, the tick that
# produced the unfillable order.
AS_OF = datetime(2026, 8, 31, 13, 51, 49, tzinfo=UTC)


def quote(symbol: str, strike: str, bid: str, ask: str, delta: str) -> OptionQuoteSnapshot:
    return OptionQuoteSnapshot(
        contract_symbol=symbol,
        option_type=OptionType.CALL,
        expiration=date(2026, 9, 14),
        dte=14,
        strike=Decimal(strike),
        bid=Decimal(bid),
        ask=Decimal(ask),
        quote_as_of=AS_OF,
        feed="indicative",
        delta=Decimal(delta),
    )


LONG_765 = quote("SPY260914C00765000", "765", "7.27", "7.72", "0.5635")
SHORT_775 = quote("SPY260914C00775000", "775", "2.79", "2.81", "0.3042")

#: What the two contracts actually traded at in the same minute, from OPRA.
TRADED_LONG = Decimal("7.80")
TRADED_SHORT = Decimal("2.65")


class UnfillableLimitRegressionTests(unittest.TestCase):
    def test_crossing_the_quotes_alone_reproduces_the_order_that_never_filled(self) -> None:
        naive = LONG_765.ask - SHORT_775.bid
        self.assertEqual(naive, Decimal("4.93"))
        # The real market that minute, which is why 4.93 sat there.
        self.assertGreater(TRADED_LONG - TRADED_SHORT, naive)

    def test_the_allowance_lifts_the_limit_above_the_traded_market(self) -> None:
        debit = crossing_debit(LONG_765, SHORT_775)
        self.assertEqual(debit, Decimal("5.17"))
        self.assertGreaterEqual(debit, TRADED_LONG - TRADED_SHORT)

    def test_a_tight_quote_is_barely_padded_at_all(self) -> None:
        """The allowance scales itself to the feed, so OPRA would pay ~nothing."""
        tight_long = quote("SPY260914C00765000", "765", "6.92", "6.95", "0.55")
        tight_short = quote("SPY260914C00775000", "775", "2.37", "2.38", "0.30")
        naive = tight_long.ask - tight_short.bid
        self.assertEqual(crossing_debit(tight_long, tight_short) - naive, Decimal("0.02"))

    def test_the_allowance_is_never_negative_and_never_lowers_the_debit(self) -> None:
        for long_leg, short_leg in (
            (LONG_765, SHORT_775),
            (quote("A", "765", "6.92", "6.95", "0.55"), quote("B", "775", "2.37", "2.38", "0.30")),
        ):
            with self.subTest(long_leg.contract_symbol):
                self.assertGreaterEqual(
                    crossing_debit(long_leg, short_leg), long_leg.ask - short_leg.bid
                )

    def test_the_allowance_is_half_of_the_two_quoted_widths(self) -> None:
        widths = (LONG_765.ask - LONG_765.bid) + (SHORT_775.ask - SHORT_775.bid)
        allowance = crossing_debit(LONG_765, SHORT_775) - (LONG_765.ask - SHORT_775.bid)
        self.assertEqual(EXECUTION_ALLOWANCE_FRACTION, Decimal("0.5"))
        # Rounded up to the cent, so the approved loss never sits below the bid.
        self.assertEqual(allowance, (widths * EXECUTION_ALLOWANCE_FRACTION).quantize(
            Decimal("0.01"), rounding="ROUND_CEILING"
        ))

    def test_max_loss_bounds_the_price_the_order_is_submitted_at(self) -> None:
        """The invariant the firewall rests on: approved loss >= what we can pay.

        The limit sent to the broker is this debit quantized to the cent, so the
        loss risk signed off on must not be smaller than the limit it implies.
        """
        debit = crossing_debit(LONG_765, SHORT_775)
        limit = debit.quantize(Decimal("0.01"))
        approved_max_loss = (debit * CONTRACT_MULTIPLIER).quantize(Decimal("0.01"))
        self.assertGreaterEqual(approved_max_loss, limit * CONTRACT_MULTIPLIER)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
