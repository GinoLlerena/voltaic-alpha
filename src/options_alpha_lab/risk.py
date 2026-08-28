from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR

from .models import (
    Direction,
    ExperimentCase,
    OptionQuote,
    RiskResult,
    SpreadProposal,
    Thesis,
)


class DeterministicRiskGate:
    name = "deterministic_risk_gate"

    def evaluate(
        self,
        case: ExperimentCase,
        thesis: Thesis,
        proposal: SpreadProposal | None,
    ) -> RiskResult:
        risk_budget = case.account_equity * case.policy.max_risk_pct
        reasons: list[str] = []

        if not Decimal("0") <= thesis.confidence <= Decimal("1"):
            reasons.append("confidence_outside_valid_range")
        elif thesis.confidence < case.policy.min_confidence:
            reasons.append("confidence_below_policy")
        usable_evidence = {item.strip() for item in thesis.evidence if item.strip()}
        if len(usable_evidence) < case.policy.min_evidence_items:
            reasons.append("insufficient_evidence")
        if not any(item.strip() for item in thesis.invalidation_conditions):
            reasons.append("missing_invalidation_conditions")

        if proposal is None:
            reasons.append("no_valid_spread")
            return RiskResult(
                approved=False,
                reasons=tuple(reasons),
                risk_budget=risk_budget,
                calculated_max_loss=Decimal("0"),
            )

        if not (
            case.policy.min_dte <= proposal.long_leg.dte <= case.policy.max_dte
            and case.policy.min_dte <= proposal.short_leg.dte <= case.policy.max_dte
        ):
            reasons.append("dte_outside_policy")
        self._validate_quote(
            proposal.long_leg,
            "long_leg",
            case.policy.max_bid_ask_ratio,
            reasons,
        )
        self._validate_quote(
            proposal.short_leg,
            "short_leg",
            case.policy.max_bid_ask_ratio,
            reasons,
        )
        self._validate_snapshot_leg(
            case,
            proposal.long_leg,
            "long_leg",
            reasons,
        )
        self._validate_snapshot_leg(
            case,
            proposal.short_leg,
            "short_leg",
            reasons,
        )
        if proposal.long_leg.symbol == proposal.short_leg.symbol:
            reasons.append("spread_uses_same_contract_twice")
        if proposal.long_leg.expiration != proposal.short_leg.expiration:
            reasons.append("legs_expiration_mismatch")
        if proposal.long_leg.dte != proposal.short_leg.dte:
            reasons.append("legs_dte_mismatch")

        expected_option_type = (
            "put" if thesis.direction is Direction.BEARISH else "call"
        )
        if (
            proposal.long_leg.option_type != expected_option_type
            or proposal.short_leg.option_type != expected_option_type
        ):
            reasons.append("legs_option_type_mismatch")

        expected_strategy = (
            "put_debit_spread"
            if thesis.direction is Direction.BEARISH
            else "call_debit_spread"
        )
        if proposal.strategy != expected_strategy:
            reasons.append("strategy_direction_mismatch")

        if thesis.direction is Direction.BEARISH:
            valid_shape = proposal.long_leg.strike > proposal.short_leg.strike
        else:
            valid_shape = proposal.long_leg.strike < proposal.short_leg.strike
        if not valid_shape:
            reasons.append("invalid_spread_shape")

        expected_debit = proposal.long_leg.ask - proposal.short_leg.bid
        if proposal.estimated_debit != expected_debit:
            reasons.append("estimated_debit_mismatch")
        if proposal.estimated_debit <= 0:
            reasons.append("non_positive_debit")
        spread_width = abs(proposal.long_leg.strike - proposal.short_leg.strike)
        if proposal.estimated_debit >= spread_width:
            reasons.append("debit_not_below_spread_width")

        if proposal.quantity < 1:
            reasons.append("quantity_below_policy")
        if proposal.quantity > case.policy.max_contracts:
            reasons.append("quantity_above_policy")

        suggested_quantity: int | None = None
        if proposal.quantity > 0 and proposal.max_loss > risk_budget:
            reasons.append("max_loss_above_risk_budget")
            per_contract_loss = proposal.estimated_debit * Decimal("100")
            resizable_reasons = {
                "max_loss_above_risk_budget",
                "quantity_above_policy",
            }
            if per_contract_loss > 0 and set(reasons) <= resizable_reasons:
                affordable = int(
                    (risk_budget / per_contract_loss).to_integral_value(
                        rounding=ROUND_FLOOR
                    )
                )
                if affordable >= 1:
                    suggested_quantity = min(affordable, case.policy.max_contracts)

        return RiskResult(
            approved=not reasons,
            reasons=tuple(reasons),
            risk_budget=risk_budget,
            calculated_max_loss=proposal.max_loss,
            suggested_quantity=suggested_quantity,
        )

    @staticmethod
    def _validate_quote(
        quote: OptionQuote,
        leg_name: str,
        max_bid_ask_ratio: Decimal,
        reasons: list[str],
    ) -> None:
        if not quote.has_two_sided_market:
            reasons.append(f"{leg_name}_quote_not_two_sided")
            return
        if quote.is_crossed:
            reasons.append(f"{leg_name}_quote_crossed")
            return
        if quote.spread_ratio > max_bid_ask_ratio:
            reasons.append(f"{leg_name}_spread_too_wide")

    @staticmethod
    def _validate_snapshot_leg(
        case: ExperimentCase,
        quote: OptionQuote,
        leg_name: str,
        reasons: list[str],
    ) -> None:
        observed = next(
            (item for item in case.option_chain if item.symbol == quote.symbol),
            None,
        )
        if observed is None:
            reasons.append(f"{leg_name}_not_in_option_chain")
        elif observed != quote:
            reasons.append(f"{leg_name}_quote_snapshot_mismatch")
