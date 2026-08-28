from __future__ import annotations

from decimal import Decimal

from .models import (
    Decision,
    Direction,
    ExperimentCase,
    OptionQuote,
    RiskResult,
    SpreadProposal,
    Thesis,
)


class EventThesisAgent:
    """Produces the event thesis contract.

    The experiment uses fixture evidence. A later version can replace this
    implementation with an LLM while preserving the same output contract.
    """

    name = "event_thesis_agent"

    def analyze(self, case: ExperimentCase) -> Thesis:
        return Thesis(
            symbol=case.symbol,
            event_type=case.event_type,
            direction=case.expected_direction,
            confidence=case.confidence,
            evidence=case.evidence,
            invalidation_conditions=case.invalidation_conditions,
        )


class OptionsStructureAgent:
    """Builds one risk-defined directional debit spread."""

    name = "options_structure_agent"

    def propose(
        self,
        case: ExperimentCase,
        thesis: Thesis,
        quantity: int | None = None,
    ) -> SpreadProposal | None:
        option_type = "put" if thesis.direction is Direction.BEARISH else "call"
        eligible = [
            quote
            for quote in case.option_chain
            if quote.option_type == option_type
            and case.policy.min_dte <= quote.dte <= case.policy.max_dte
        ]
        if len(eligible) < 2:
            return None

        pair = self._select_pair(
            eligible,
            thesis.direction,
            case.underlying_price,
        )
        if pair is None:
            return None

        long_leg, short_leg = pair
        estimated_debit = long_leg.ask - short_leg.bid
        if estimated_debit <= Decimal("0"):
            return None

        chosen_quantity = case.policy.max_contracts if quantity is None else quantity
        strategy = "put_debit_spread" if option_type == "put" else "call_debit_spread"
        return SpreadProposal(
            strategy=strategy,
            long_leg=long_leg,
            short_leg=short_leg,
            quantity=chosen_quantity,
            estimated_debit=estimated_debit,
            rationale=(
                f"Express the {thesis.direction.value} event thesis with defined risk "
                f"and {long_leg.dte} DTE."
            ),
        )

    @staticmethod
    def _select_pair(
        quotes: list[OptionQuote],
        direction: Direction,
        underlying_price: Decimal,
    ) -> tuple[OptionQuote, OptionQuote] | None:
        candidates: list[tuple[OptionQuote, OptionQuote]] = []
        for index, first in enumerate(quotes):
            for second in quotes[index + 1 :]:
                if first.expiration != second.expiration or first.dte != second.dte:
                    continue
                if first.strike == second.strike:
                    continue

                higher, lower = sorted(
                    (first, second), key=lambda quote: quote.strike, reverse=True
                )
                if direction is Direction.BEARISH:
                    candidates.append((higher, lower))
                else:
                    candidates.append((lower, higher))

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda pair: (
                abs(pair[0].strike - underlying_price)
                + abs(pair[1].strike - underlying_price),
                abs(pair[0].strike - underlying_price),
                pair[0].dte,
                pair[0].expiration,
                pair[0].strike,
                pair[1].strike,
            ),
        )


class DecisionArbiter:
    """Maps the validated state to a final experiment decision."""

    name = "decision_arbiter"

    def decide(self, risk: RiskResult) -> Decision:
        if risk.approved:
            return Decision.TRADE_CANDIDATE
        return Decision.NO_TRADE
