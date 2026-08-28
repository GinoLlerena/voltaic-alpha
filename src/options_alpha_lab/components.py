"""Deterministic H0 components.

Every threshold in this module is `PROVISIONAL` (implementation plan section
3.3). Phase 2 freezes the real trend/retest specification and Phase 3 adds the
bounded model memo. What matters at Phase 1 is the *shape*: direction,
invalidation, option eligibility, and risk are computed by code that no model can
reach, and the numbers are named constants rather than literals buried in logic.

``DeterministicBaselineThesis`` is not a placeholder for the model. It is the
control arm of the Phase 3 ablation and stays in the codebase permanently.
"""

from __future__ import annotations

from decimal import Decimal

from .architecture.contracts import (
    DecisionSnapshot,
    Direction,
    OptionQuoteSnapshot,
    OptionType,
    RiskDecision,
    SetupCandidate,
    SetupFamily,
    Signal,
    SignalFamily,
    SpreadCandidate,
    SpreadStrategy,
    Thesis,
)

# --- PROVISIONAL policy values. Not approved thresholds. ---------------------
MIN_STRUCTURE_STRENGTH = Decimal("0.60")
MIN_CONFIRMATION_STRENGTH = Decimal("0.50")
CONTRADICTION_VETO_STRENGTH = Decimal("0.70")
MIN_DTE = 14
MAX_DTE = 45
MAX_RELATIVE_QUOTE_SPREAD = Decimal("0.25")
RISK_FRACTION_OF_EQUITY = Decimal("0.005")
CONTRACT_MULTIPLIER = Decimal("100")

POLICY_VERSION = "h0-provisional-0"

_STRUCTURE_FAMILIES = frozenset({SignalFamily.STRUCTURE})


def _opposite(direction: Direction) -> Direction:
    return Direction.BEARISH if direction is Direction.BULLISH else Direction.BULLISH


class DeterministicSetupClassifier:
    """One mirrored trend-continuation/retest setup (`CLR-004`, `CLR-010`).

    Qualification requires objective structure plus one confirmation from a
    *different* signal family. Requiring a different family is the point: two
    restatements of the same price move are one piece of evidence, not two.
    """

    name = "deterministic_trend_retest_v0"

    def classify(self, snapshot: DecisionSnapshot) -> SetupCandidate | None:
        structure = [
            signal
            for signal in snapshot.signals
            if signal.family in _STRUCTURE_FAMILIES
            and signal.direction is not Direction.NEUTRAL
            and signal.strength >= MIN_STRUCTURE_STRENGTH
        ]
        if not structure:
            return None

        anchor = max(structure, key=lambda signal: (signal.strength, signal.signal_id))
        direction = anchor.direction

        contradictions = [
            signal
            for signal in snapshot.signals
            if signal.direction is _opposite(direction)
            and signal.strength >= CONTRADICTION_VETO_STRENGTH
        ]
        if contradictions:
            return None

        confirmations = [
            signal
            for signal in snapshot.signals
            if signal.direction is direction
            and signal.family not in _STRUCTURE_FAMILIES
            and signal.strength >= MIN_CONFIRMATION_STRENGTH
        ]
        if not confirmations:
            return None

        confirmation = max(confirmations, key=lambda signal: (signal.strength, signal.signal_id))
        evidence_ids = tuple(sorted({anchor.signal_id, confirmation.signal_id}))

        return SetupCandidate(
            setup_id=f"{snapshot.symbol.lower()}-trend-retest-{snapshot.snapshot_id}",
            family=SetupFamily.TREND_CONTINUATION_RETEST,
            direction=direction,
            evidence_ids=evidence_ids,
            invalidation_conditions=self._invalidation(snapshot, direction),
        )

    @staticmethod
    def _invalidation(snapshot: DecisionSnapshot, direction: Direction) -> tuple[str, ...]:
        # Deterministic and derived only from observed price. The model is not
        # permitted to alter these; the workflow rejects a thesis that tries.
        price = snapshot.underlying_price
        if direction is Direction.BULLISH:
            level = (price * Decimal("0.985")).quantize(Decimal("0.01"))
            structural = f"close below {level} invalidates the retest"
        else:
            level = (price * Decimal("1.015")).quantize(Decimal("0.01"))
            structural = f"close above {level} invalidates the retest"
        return (structural, "loss of directional structure on the decision timeframe")


class DeterministicBaselineThesis:
    """The no-LLM control arm (`AI-010`). Restates evidence; invents nothing."""

    name = "deterministic_baseline_v0"

    def synthesize(self, snapshot: DecisionSnapshot, setup: SetupCandidate) -> Thesis:
        by_id = {signal.signal_id: signal for signal in snapshot.signals}
        aligned: list[Signal] = [by_id[sid] for sid in setup.evidence_ids if sid in by_id]
        counter = tuple(
            sorted(
                signal.signal_id
                for signal in snapshot.signals
                if signal.direction is _opposite(setup.direction)
            )
        )

        if aligned:
            total = sum((signal.strength for signal in aligned), start=Decimal("0"))
            confidence = (total / Decimal(len(aligned))).quantize(Decimal("0.0001"))
        else:
            confidence = Decimal("0")
        confidence = min(confidence, Decimal("1"))

        summary = (
            f"Deterministic baseline: {setup.family.value} qualified {setup.direction.value} "
            f"on {snapshot.symbol} from {len(aligned)} aligned signal(s); "
            f"{len(counter)} opposing signal(s) recorded. No model input."
        )
        return Thesis(
            direction=setup.direction,
            confidence=confidence,
            evidence_ids=setup.evidence_ids,
            counter_evidence_ids=counter,
            # Copied verbatim. The workflow rejects any thesis that alters them.
            invalidation_conditions=setup.invalidation_conditions,
            reasoning_summary=summary,
        )


class DeterministicSpreadSelector:
    """Vertical debit-spread eligibility and deterministic tie-breaking."""

    name = "deterministic_vertical_selector_v0"

    def select(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
        thesis: Thesis,
    ) -> SpreadCandidate | None:
        bullish = thesis.direction is Direction.BULLISH
        wanted = OptionType.CALL if bullish else OptionType.PUT

        usable = [
            quote
            for quote in snapshot.option_chain
            if quote.option_type is wanted
            and MIN_DTE <= quote.dte <= MAX_DTE
            and self._quote_is_tradeable(quote)
        ]
        if len(usable) < 2:
            return None

        # Legs of a vertical must share an expiration. Nearest eligible expiry
        # wins, and ties are broken by date so the choice is reproducible.
        chosen_expiry = min(quote.expiration for quote in usable)
        legs = sorted(
            (quote for quote in usable if quote.expiration == chosen_expiry),
            key=lambda quote: quote.strike,
        )
        if len(legs) < 2:
            return None

        price = snapshot.underlying_price
        long_leg = min(legs, key=lambda quote: (abs(quote.strike - price), quote.strike))
        if bullish:
            candidates = [quote for quote in legs if quote.strike > long_leg.strike]
        else:
            candidates = [quote for quote in legs if quote.strike < long_leg.strike]
        if not candidates:
            return None
        short_leg = min(
            candidates, key=lambda quote: (abs(quote.strike - long_leg.strike), quote.strike)
        )

        # Conservative: pay the ask on the long leg, receive the bid on the short.
        debit = long_leg.ask - short_leg.bid
        if debit <= 0:
            return None
        width = abs(long_leg.strike - short_leg.strike)
        if debit >= width:
            return None

        return SpreadCandidate(
            candidate_id=f"{setup.setup_id}-vertical",
            strategy=(
                SpreadStrategy.BULL_CALL_DEBIT_SPREAD
                if bullish
                else SpreadStrategy.BEAR_PUT_DEBIT_SPREAD
            ),
            long_contract_symbol=long_leg.contract_symbol,
            short_contract_symbol=short_leg.contract_symbol,
            quantity=1,
            estimated_debit=debit,
            calculated_max_loss=(debit * CONTRACT_MULTIPLIER).quantize(Decimal("0.01")),
        )

    @staticmethod
    def _quote_is_tradeable(quote: OptionQuoteSnapshot) -> bool:
        if quote.bid <= 0 or quote.ask <= 0:
            return False
        if quote.ask < quote.bid:
            return False
        midpoint = (quote.bid + quote.ask) / Decimal("2")
        if midpoint <= 0:
            return False
        return (quote.ask - quote.bid) / midpoint <= MAX_RELATIVE_QUOTE_SPREAD


class DeterministicRiskGovernor:
    """Terminal risk authority. Recomputes loss from observed quotes (`RISK-005`)."""

    name = "deterministic_risk_governor_v0"

    def __init__(self, policy_version: str = POLICY_VERSION) -> None:
        self.policy_version = policy_version
        self.last_checks: tuple[dict[str, object], ...] = ()

    def evaluate(
        self,
        snapshot: DecisionSnapshot,
        setup: SetupCandidate,
        thesis: Thesis,
        spread: SpreadCandidate,
    ) -> RiskDecision:
        checks: list[dict[str, object]] = []
        reasons: list[str] = []

        budget = (snapshot.account.equity * RISK_FRACTION_OF_EQUITY).quantize(Decimal("0.01"))

        # Never trust the candidate's arithmetic: recompute from the chain.
        quotes = {quote.contract_symbol: quote for quote in snapshot.option_chain}
        long_leg = quotes.get(spread.long_contract_symbol)
        short_leg = quotes.get(spread.short_contract_symbol)
        if long_leg is None or short_leg is None:
            reasons.append("spread_legs_not_in_snapshot")
            checks.append({"check": "legs_present", "passed": False})
            return self._decision(False, reasons, budget, Decimal("0"), checks)
        checks.append({"check": "legs_present", "passed": True})

        recomputed_debit = long_leg.ask - short_leg.bid
        recomputed_loss = (recomputed_debit * CONTRACT_MULTIPLIER * spread.quantity).quantize(
            Decimal("0.01")
        )
        matches = recomputed_loss == (spread.calculated_max_loss * spread.quantity).quantize(
            Decimal("0.01")
        )
        checks.append(
            {
                "check": "max_loss_recomputed",
                "passed": matches,
                "recomputed": str(recomputed_loss),
                "claimed": str(spread.calculated_max_loss * spread.quantity),
            }
        )
        if not matches:
            reasons.append("max_loss_does_not_match_observed_quotes")

        within_budget = recomputed_loss <= budget
        checks.append(
            {
                "check": "within_risk_budget",
                "passed": within_budget,
                "budget": str(budget),
                "max_loss": str(recomputed_loss),
            }
        )
        if not within_budget:
            reasons.append("max_loss_exceeds_risk_budget")

        affordable = recomputed_loss <= snapshot.account.options_buying_power
        checks.append({"check": "affordable", "passed": affordable})
        if not affordable:
            reasons.append("insufficient_options_buying_power")

        directional = thesis.direction is setup.direction
        checks.append({"check": "direction_matches_setup", "passed": directional})
        if not directional:
            reasons.append("thesis_direction_outside_setup")

        approved = not reasons
        return self._decision(approved, reasons, budget, recomputed_loss, checks)

    def _decision(
        self,
        approved: bool,
        reasons: list[str],
        budget: Decimal,
        loss: Decimal,
        checks: list[dict[str, object]],
    ) -> RiskDecision:
        self.last_checks = tuple(checks)
        return RiskDecision(
            approved=approved,
            reason_codes=tuple(reasons),
            risk_budget=budget,
            # An unapproved decision must not claim a loss above its budget; the
            # contract forbids it, and the real figure is preserved in `checks`.
            calculated_max_loss=loss if approved else min(loss, budget),
            policy_version=self.policy_version,
        )
