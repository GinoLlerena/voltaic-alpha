"""The autonomous decision cycle.

One `tick` is the whole agent: observe, then either manage the open position or
consider a new one. It is a plain method with injected collaborators so the
entire loop is testable offline, and the scheduler is a thin wrapper around it.

Ordering inside a tick is deliberate. **Exits are evaluated before entries**,
always. A tick that opened a position before checking whether the existing one
needed closing could hold a losing position through its own stop while spending
the single strategy slot on a new one.

Nothing here can bypass the gateway: the agent constructs intents and asks, and
every guard still runs immediately before the write.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .architecture.contracts import (
    BotMode,
    DecisionAction,
    DecisionOutcome,
    DecisionSnapshot,
    ExecutionState,
    SpreadStrategy,
    TypedInvalidation,
)
from .architecture.workflow import DecisionWorkflow
from .calendar import TradingCalendar
from .components import (
    DeterministicBaselineThesis,
    DeterministicRiskGovernor,
    DeterministicSetupClassifier,
    DeterministicSpreadSelector,
)
from .config import Settings
from .evidence import build_snapshot, parse_bars, parse_occ_symbol
from .execution.deadline import DeadlineEnforcer, DeadlineOutcome, deadline_for
from .execution.gateway import AmbiguousSubmission, ExecutionGateway, ExecutionRefused
from .execution.intent import IntentLeg, OrderIntent, build_close_intent, build_open_intent
from .execution.lifecycle import (
    DuplicateIntent,
    LifecycleStore,
    ManagedPosition,
    OrderState,
    PositionState,
)
from .execution.reconcile import Reconciler, ReconciliationReport
from .execution.request import prepare_mleg_request
from .exits import (
    POLICY_VERSION as EXIT_POLICY_VERSION,
)
from .exits import (
    PRECEDENCE,
    ExitDecision,
    ExitInputs,
    ExitTrigger,
    evaluate_exit,
    evaluate_triggers,
)
from .providers.alpaca_readonly import ProviderError, ReadOnlyAlpacaClient

DEFAULT_TICK_SECONDS = 300
CHAIN_DTE_LOW = 10
CHAIN_DTE_HIGH = 60


@dataclass
class TickResult:
    at: datetime
    action: str
    detail: str
    snapshot_id: str | None = None
    decision_hash: str | None = None
    exit: ExitDecision | None = None
    submitted: str | None = None
    reason_codes: list[str] = field(default_factory=list)

    def line(self) -> str:
        parts = [self.at.strftime("%H:%M:%SZ"), f"{self.action:16}", self.detail]
        if self.submitted:
            parts.append(f"order={self.submitted}")
        return "  ".join(parts)


def spread_value(snapshot: DecisionSnapshot, long_symbol: str, short_symbol: str) -> Decimal | None:
    """Conservative closing value: sell the long at the bid, buy the short at the ask."""
    quotes = {q.contract_symbol: q for q in snapshot.option_chain}
    long_leg, short_leg = quotes.get(long_symbol), quotes.get(short_symbol)
    if long_leg is None or short_leg is None:
        return None
    if long_leg.bid <= 0 or short_leg.ask <= 0:
        return None
    return long_leg.bid - short_leg.ask


class TradingAgent:
    """Observe, manage, decide. One position at a time, exits first."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: ReadOnlyAlpacaClient,
        gateway: ExecutionGateway | None = None,
        synthesizer: Any = None,
        recorder: Any = None,
        reconciler: Reconciler | None = None,
        store: LifecycleStore | None = None,
        deadlines: DeadlineEnforcer | None = None,
        calendar: TradingCalendar | None = None,
        symbol: str = "SPY",
        clock: Callable[[], datetime] | None = None,
        operator_approval: str | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.gateway = gateway
        self.synthesizer = synthesizer
        self.recorder = recorder
        self.reconciler = reconciler
        self.store = store
        self.deadlines = deadlines
        self.calendar = calendar
        self.symbol = symbol
        self.operator_approval = operator_approval
        self._clock = clock or (lambda: datetime.now(UTC))
        self.history: list[TickResult] = []
        self.run_id: str | None = None
        self.decision_row_id: str | None = None
        self.last_reconciliation: ReconciliationReport | None = None
        self.last_deadline_outcome: DeadlineOutcome | None = None
        #: Completed trading sessions observed in the most recent bar read.
        self._sessions: list[date] = []
        #: Set by reconciliation. Entries are refused while this is not NORMAL.
        self.execution_state: ExecutionState = ExecutionState.NORMAL
        #: Rebuilt by `workflow()` on every evaluation; holds that pass's checks.
        self.risk_governor = DeterministicRiskGovernor(self.settings.policy_version)

    # -- reconciliation ----------------------------------------------------
    def reconcile(self) -> ReconciliationReport | None:
        """Compare durable records with the broker. Mismatches halt new risk.

        Runs at startup and on every tick. A failure to *read* the broker halts
        new risk too: not knowing what we hold is not the same as holding
        nothing.
        """
        if self.reconciler is None:
            return None
        report = self.reconciler.reconcile(run_id=self.run_id, now=self._clock())
        self.last_reconciliation = report
        self.execution_state = report.execution_state
        if self.gateway is not None:
            # The gateway is the thing that must actually refuse.
            self.gateway.execution_state = report.execution_state
        return report

    def startup(self) -> ReconciliationReport | None:
        """Reconcile before the agent is allowed to consider any new risk."""
        report = self.reconcile()
        if report is not None:
            self._record(
                TickResult(
                    self._clock(),
                    "STARTUP_RECONCILE" if report.clean else "STARTUP_HALTED",
                    report.summary(),
                )
            )
        return report

    # -- observation -------------------------------------------------------
    def observe(self) -> tuple[DecisionSnapshot, bool]:
        # EXIT-009: the injected clock, not the host date. Two time sources in
        # one method means replay and production disagree.
        today = self._clock().date()
        clock_read = self.client.clock()
        account = self.client.account()
        bars = self.client.daily_bars(self.symbol)
        chain = self.client.option_chain(
            self.symbol,
            expiration_gte=(today + timedelta(days=CHAIN_DTE_LOW)).isoformat(),
            expiration_lte=(today + timedelta(days=CHAIN_DTE_HIGH)).isoformat(),
        )
        is_open = bool(
            isinstance(clock_read.payload, dict) and clock_read.payload.get("is_open")
        )
        self._sessions = [
            bar.session
            for bar in parse_bars(bars, as_of=self._clock(), market_open=is_open)
        ]
        stamp = self._clock().strftime("%Y%m%dT%H%M%SZ")
        snapshot = build_snapshot(
            snapshot_id=f"{self.symbol.lower()}-agent-{stamp}",
            symbol=self.symbol,
            account_read=account,
            clock_read=clock_read,
            bars_read=bars,
            chain_read=chain,
            as_of=self._clock(),
        )
        return snapshot, is_open

    def workflow(self) -> DecisionWorkflow:
        # Held rather than discarded: the governor accumulates the individual
        # risk checks it ran, and building it inline threw them away before the
        # recorder could store them. A refusal whose reason codes survive but
        # whose checks do not cannot be re-argued later.
        self.risk_governor = DeterministicRiskGovernor(self.settings.policy_version)
        return DecisionWorkflow(
            setup_classifier=DeterministicSetupClassifier(),
            thesis_synthesizer=(
                self.synthesizer
                if self.synthesizer is not None and self.settings.bot_mode is not BotMode.OBSERVE
                else DeterministicBaselineThesis()
            ),
            options_selector=DeterministicSpreadSelector(),
            risk_governor=self.risk_governor,
        )

    # -- the cycle ---------------------------------------------------------
    def tick(self) -> TickResult:
        now = self._clock()

        # Broker responsibility comes first, because it depends on nothing else.
        # Reconciliation is a read, and broker state does not stop changing at
        # the close: an order that expired at 16:00, or a fill that landed at
        # 15:59:59, must not go unnoticed until the next open - 65 hours over a
        # long weekend. Nor may an options-chain outage suppress it. Observing
        # first made a market-data failure silently abandon every open order and
        # position until the provider recovered (EXIT-002).
        report = self.reconcile()

        # Deadlines next, for that reason and one more: they are measured in
        # seconds against a tick measured in minutes, so anything that defers
        # them defers a cancel that is already late. A deadline that expires
        # after the close is still enforced - an order left working overnight is
        # abandoned responsibility, not paused responsibility - and cancelling
        # only ever reduces risk.
        deadline_result = self._enforce_deadlines(now)
        if deadline_result is not None:
            return self._record(deadline_result)

        try:
            snapshot, market_open = self.observe()
        except (ProviderError, ValueError) as exc:
            detail = f"{type(exc).__name__}: {exc}"
            if report is not None:
                detail = f"{detail}; reconciled: {report.summary()}"
            return self._record(TickResult(now, "OBSERVE_FAILED", detail))

        if not market_open:
            detail = "no action taken"
            if report is not None:
                detail = f"reconciled: {report.summary()}"
            return self._record(TickResult(now, "MARKET_CLOSED", detail))

        # Exits before entries, always.
        managed = self.active_position()
        if managed is not None:
            return self._record(self._manage_open_position(managed, snapshot, now))

        # An entry already in flight blocks another. active_position() above
        # deliberately ignores PENDING because there is nothing to manage, but a
        # pending entry still owns the single strategy slot.
        in_flight = self.unresolved_position()
        if in_flight is not None:
            return self._record(
                TickResult(
                    now,
                    "ENTRY_IN_FLIGHT",
                    f"position {in_flight.position_id} is {in_flight.state.value}; "
                    "awaiting reconciliation before any new entry",
                    snapshot.snapshot_id,
                )
            )

        if report is not None and not report.clean:
            # New risk is halted, but management above still ran: a mismatch
            # must not also stop us managing what we may still own.
            return self._record(
                TickResult(now, "ENTRY_HALTED", report.summary(), snapshot.snapshot_id)
            )

        # The market being open is not the same as the entry window being open
        # (EXIT-012). Monitoring and risk reduction above already ran.
        if self.calendar is not None:
            window = self.calendar.evaluate_entry(now)
            if not window.entry_permitted:
                return self._record(
                    TickResult(
                        now, "OUTSIDE_ENTRY_WINDOW", window.reason, snapshot.snapshot_id
                    )
                )

        # Data quality governs the halt state too (EXIT-010).
        data_state = halt_state_for(snapshot)
        if data_state is not ExecutionState.NORMAL:
            self.execution_state = data_state
            if self.gateway is not None:
                self.gateway.execution_state = data_state
            return self._record(
                TickResult(
                    now,
                    "ENTRY_HALTED",
                    "unusable observation: "
                    + ", ".join(snapshot.data_quality.reason_codes[:3]),
                    snapshot.snapshot_id,
                )
            )

        return self._record(self._consider_entry(snapshot, now))

    def _halt_new_risk(self) -> None:
        """Stop new risk here *and* at the gateway, which is what must refuse."""
        self.execution_state = ExecutionState.NO_NEW_RISK
        if self.gateway is not None:
            self.gateway.execution_state = ExecutionState.NO_NEW_RISK

    def _enforce_deadlines(self, now: datetime) -> TickResult | None:
        """Cancel anything past its post-submission deadline. Needs no market data."""
        if self.deadlines is None or not self.settings.may_write_orders:
            return None
        outcome = self.deadlines.enforce(run_id=self.run_id, now=now)
        self.last_deadline_outcome = outcome
        if outcome.late_fills or outcome.failures:
            self._halt_new_risk()
        if not outcome.acted:
            return None
        # A requested cancel is not a confirmed one, and it can still lose a race
        # with a fill. Establish the terminal state now rather than leaving the
        # single strategy slot occupied until the next tick.
        after = self.reconcile()
        detail = outcome.summary()
        if after is not None:
            detail = f"{detail}; reconciled: {after.summary()}"
        return TickResult(now, "DEADLINE_ACTION", detail)

    def unresolved_position(self) -> ManagedPosition | None:
        """Any position that is not finished, including one whose entry is in flight.

        Distinct from `active_position`, which answers "what do I manage exits
        for". A PENDING entry has nothing to manage, but it absolutely blocks a
        second entry: the strategy slot is already spoken for, and preparing
        another intent from the same decision would collide on the deterministic
        client order id.
        """
        if self.store is None:
            return None
        unresolved = [
            position
            for position in self.store.active_positions()
            if position.state
            in {
                PositionState.PENDING,
                PositionState.OPEN,
                PositionState.CLOSING,
                PositionState.INCIDENT,
            }
        ]
        return unresolved[0] if unresolved else None

    def active_position(self) -> ManagedPosition | None:
        """The position we are responsible for, read from durable records.

        A `PENDING` position is deliberately not returned: its entry has not been
        confirmed, so there is nothing to manage and nothing to price an exit
        from. Reconciliation resolves it.
        """
        if self.store is None:
            return None
        for position in self.store.active_positions():
            if position.state in {PositionState.OPEN, PositionState.CLOSING}:
                return position
        return None

    def sessions_since(self, filled_at: datetime | None) -> int:
        """Completed trading sessions since the entry fill (`EXIT-003`).

        Counted from observed daily bars, which exist once per trading session,
        so weekends and market holidays are excluded without a separate calendar.
        """
        if filled_at is None:
            return 0
        if self.calendar is not None and len(self.calendar):
            # The authoritative source: it knows holidays and early closes.
            return self.calendar.completed_sessions_between(filled_at, self._clock())
        if not self._sessions:
            return 0
        entry_day = filled_at.astimezone(UTC).date()
        return sum(1 for session in self._sessions if session > entry_day)

    def _manage_open_position(
        self, position: ManagedPosition, snapshot: DecisionSnapshot, now: datetime
    ) -> TickResult:
        if position.avg_entry_debit is None:
            # OPEN without a reconciled basis should be impossible; refuse to
            # invent one rather than pricing exits off a limit.
            if self.store is not None:
                self.store.open_incident(
                    kind="missing_fill_basis",
                    detail=f"position {position.position_id} is OPEN with no average debit",
                    position_id=position.position_id, run_id=self.run_id, now=now,
                )
            return TickResult(
                now, "POSITION_REVIEW",
                "position is OPEN without a reconciled entry debit; incident raised",
                snapshot.snapshot_id,
            )

        value = spread_value(snapshot, position.long_symbol, position.short_symbol)
        inputs = ExitInputs(
            direction=position.direction,
            # The actual reconciled fill, never the estimate.
            entry_debit=position.avg_entry_debit,
            width=position.width,
            quantity=position.filled_quantity,
            dte=(position.expiration.astimezone(UTC).date() - now.date()).days,
            underlying_price=snapshot.underlying_price,
            underlying_source=snapshot.underlying_source,
            invalidation=position.invalidation,
            current_value=value,
            as_of=now.date(),
            sessions_elapsed=self.sessions_since(position.entry_filled_at),
        )

        # The mark is persisted *before* the policy runs, so it exists whether or
        # not the decision that follows does anything, and whether or not the
        # process survives to write the decision. Without it "stop loss at 1.40"
        # is a console line with nothing behind it to check.
        observation_id = self._record_observation(position, snapshot, inputs, now)

        # A close is already working. Evaluating the exit policy again here would
        # submit a second close for the same exposure; responsibility is retained
        # by monitoring, not by re-submitting (EXIT-006). The observation above
        # still ran: a position under a working close is still worth marking.
        if position.state is PositionState.CLOSING:
            return TickResult(
                now,
                "CLOSE_WORKING",
                f"close order is working for {position.long_symbol}/"
                f"{position.short_symbol}; ownership retained until the broker "
                "confirms flat",
                snapshot.snapshot_id,
            )

        try:
            decision = evaluate_exit(inputs)
        except ValueError as exc:
            # The stored rule and the position disagree about direction. Managing
            # the position against either would be acting on a condition nobody
            # approved, so nothing is decided and the disagreement is durable.
            if self.store is not None:
                self.store.open_incident(
                    kind="invalidation_direction_conflict", severity="high",
                    detail=f"position {position.position_id}: {exc}",
                    position_id=position.position_id, run_id=self.run_id, now=now,
                )
            self._halt_new_risk()
            return TickResult(
                now, "POSITION_REVIEW", str(exc), snapshot.snapshot_id
            )

        # A premium we cannot read is an integrity finding, whether or not an
        # independent rule fired (EXIT-004).
        if decision.value_unmeasurable and self.store is not None:
            self.store.open_incident(
                kind="unmeasurable_position_value", severity="medium",
                detail=(
                    f"spread value unavailable for {position.long_symbol}/"
                    f"{position.short_symbol}; premium-independent rules were evaluated"
                ),
                position_id=position.position_id, run_id=self.run_id, now=now,
            )
            self._halt_new_risk()

        # So is an invalidation we hold but cannot judge. The position stays
        # managed by every rule that does not need the underlying (EXIT-AC-06).
        if decision.invalidation_unverifiable and self.store is not None:
            assert position.invalidation is not None
            self.store.open_incident(
                kind="unverifiable_invalidation_source", severity="medium",
                detail=(
                    f"position {position.position_id} holds a "
                    f"{position.invalidation.source.value} invalidation rule but the "
                    f"observed price is {snapshot.underlying_source.value}; the rule "
                    "was not evaluated and new risk is halted"
                ),
                position_id=position.position_id, run_id=self.run_id, now=now,
            )
            self._halt_new_risk()

        def record(disposition: str, close_order_id: str | None = None) -> None:
            """Persist this evaluation, whatever the agent goes on to do.

            `disposition` is what happens next, which is not always what the
            decision said: write authority, an unpriceable close, and a failed
            reconstruction all diverge from it. Every branch below records
            before it acts.
            """
            if self.store is None or observation_id is None:
                return
            self.store.record_exit_decision(
                position_id=position.position_id, observation_id=observation_id,
                run_id=self.run_id, trigger=decision.trigger.value,
                should_close=decision.should_close, reason=decision.reason,
                evaluated=evaluate_triggers(inputs),
                precedence=[trigger.value for trigger in PRECEDENCE],
                value_unmeasurable=decision.value_unmeasurable,
                invalidation_unverifiable=decision.invalidation_unverifiable,
                unrealized=decision.unrealized,
                suggested_limit=decision.suggested_limit,
                disposition=disposition, close_order_id=close_order_id,
                policy_version=decision.policy_version, decided_at=now,
            )

        if not decision.should_close:
            unmeasurable = decision.trigger is ExitTrigger.UNMEASURABLE
            record("review" if unmeasurable else "held")
            return TickResult(
                now, "POSITION_REVIEW" if unmeasurable else "POSITION_HELD",
                decision.reason, snapshot.snapshot_id, exit=decision,
            )

        if self.gateway is None or not self.settings.may_write_orders:
            record("signalled_without_authority")
            return TickResult(
                now, "EXIT_SIGNALLED",
                f"{decision.trigger.value}: {decision.reason} (no write authority)",
                snapshot.snapshot_id, exit=decision,
            )
        if decision.suggested_limit is None:
            record("blocked_unpriced")
            return TickResult(
                now, "EXIT_BLOCKED",
                f"{decision.trigger.value} fired but the close cannot be priced from "
                "the current chain; position retained and incident raised",
                snapshot.snapshot_id, exit=decision,
            )

        entry_intent = self._entry_intent_for(position)
        if entry_intent is None:
            record("blocked_unreconstructable")
            return TickResult(
                now, "EXIT_BLOCKED",
                "close intent cannot be reconstructed from durable records",
                snapshot.snapshot_id, exit=decision,
            )
        close_intent = build_close_intent(
            entry_intent,
            approval_reference=f"exit:{decision.trigger.value}",
            limit_price=decision.suggested_limit,
            now=now,
        )
        request = prepare_mleg_request(close_intent, now=now)

        # Persist before the mutation.
        close_order_id = None
        if self.store is not None:
            close_order_id = self.store.prepare_close(
                position_id=position.position_id, decision_id=position.decision_id,
                intent=close_intent, request=request,
                reason=decision.trigger.value, now=now,
            )
        # Recorded before the mutation, and linked to the order it authorises, so
        # a crash between here and the response still leaves the reason a close
        # was attempted.
        record("close_submitting", close_order_id)
        try:
            submission = self.gateway.submit(close_intent, request, reduces_risk=True)
        except ExecutionRefused as exc:
            if self.store is not None and close_order_id is not None:
                self.store.record_submission(
                    close_order_id, broker_order_id=None, broker_status="refused",
                    error=str(exc), now=now,
                )
            return TickResult(
                now, "EXIT_REFUSED", str(exc), snapshot.snapshot_id, exit=decision
            )

        # Persist after the mutation. The close is SUBMITTED, not done: ownership
        # is retained until reconciliation reports the broker flat.
        if self.store is not None and close_order_id is not None:
            self.store.record_submission(
                close_order_id, broker_order_id=submission.broker_order_id,
                broker_status=submission.status, ambiguous=submission.ambiguous, now=now,
            )
        # A submitted close is not a closed position. Reconcile immediately so
        # the broker, not the acknowledgement, decides whether we are flat.
        self.reconcile()
        return TickResult(
            now, "CLOSE_SUBMITTED",
            f"{decision.trigger.value}: {decision.reason}",
            snapshot.snapshot_id, exit=decision,
            submitted=submission.client_order_id,
        )

    def _record_observation(
        self, position: ManagedPosition, snapshot: DecisionSnapshot,
        inputs: ExitInputs, now: datetime,
    ) -> str | None:
        if self.store is None:
            return None
        quotes = {quote.contract_symbol: quote for quote in snapshot.option_chain}
        long_leg = quotes.get(position.long_symbol)
        short_leg = quotes.get(position.short_symbol)
        session = snapshot.underlying_session
        return self.store.record_observation(
            position_id=position.position_id, run_id=self.run_id,
            snapshot_id=snapshot.snapshot_id, observed_at=now,
            source_time=snapshot.as_of,
            long_bid=long_leg.bid if long_leg is not None else None,
            short_ask=short_leg.ask if short_leg is not None else None,
            spread_value=inputs.current_value,
            underlying_price=snapshot.underlying_price,
            underlying_source=snapshot.underlying_source.value,
            underlying_session=(
                datetime.combine(session, datetime.min.time(), tzinfo=UTC)
                if session is not None
                else None
            ),
            dte=inputs.dte, sessions_elapsed=inputs.sessions_elapsed,
            quantity=position.filled_quantity,
            data_quality=snapshot.data_quality.reason_codes,
            policy_version=EXIT_POLICY_VERSION,
        )

    def _entry_intent_for(self, position: ManagedPosition) -> OrderIntent | None:
        """Rebuild the opening intent so a close can mirror it exactly."""
        if self.store is None:
            return None
        client_order_id = self.store.client_order_id_for(position.entry_order_id)
        if client_order_id is None:
            return None
        strategy = SpreadStrategy(position.strategy)
        return OrderIntent(
            decision_hash=position.decision_id,
            strategy=strategy,
            legs=(
                IntentLeg(position.long_symbol, 1, "buy", "buy_to_open"),
                IntentLeg(position.short_symbol, 1, "sell", "sell_to_open"),
            ),
            strategy_quantity=max(position.filled_quantity, 1),
            limit_price=position.avg_entry_debit or Decimal("0.01"),
            approval_reference="reconstructed",
            created_at=self._clock(),
            expires_at=self._clock() + timedelta(seconds=90),
        )

    def _consider_entry(self, snapshot: DecisionSnapshot, now: datetime) -> TickResult:
        if self.synthesizer is not None:
            self.synthesizer.last_call = None
        outcome = self.workflow().evaluate(snapshot)

        recorded_hash = None
        if self.recorder is not None and self.run_id is not None:
            recorded = self.recorder.record_decision(
                run_id=self.run_id,
                snapshot=snapshot,
                outcome=outcome,
                provider="alpaca",
                feed=self.client.option_feed,
                risk_checks=[dict(check) for check in self.risk_governor.last_checks],
                classifier_name=DeterministicSetupClassifier.name,
                synthesizer_name=getattr(self.synthesizer, "name", None)
                or DeterministicBaselineThesis.name,
                model_call=getattr(self.synthesizer, "last_call", None),
            )
            recorded_hash = recorded.decision_hash
            self.decision_row_id = recorded.decision_id

        if outcome.action is not DecisionAction.OPTIONS_POSITION:
            return TickResult(
                now,
                "NO_TRADE",
                ", ".join(outcome.reason_codes) or "no qualified setup",
                snapshot.snapshot_id,
                recorded_hash,
                reason_codes=list(outcome.reason_codes),
            )

        assert outcome.spread is not None and outcome.risk is not None
        if self.gateway is None or not self.settings.may_write_orders:
            return TickResult(
                now,
                "TRADE_CANDIDATE",
                f"{outcome.spread.strategy.value} "
                f"{outcome.spread.long_contract_symbol}/{outcome.spread.short_contract_symbol} "
                f"debit {outcome.spread.estimated_debit} (no write authority)",
                snapshot.snapshot_id,
                recorded_hash,
            )

        intent = build_open_intent(
            outcome,
            recorded_hash or "unrecorded",
            approval_reference=f"risk:{outcome.risk.policy_version}",
            now=now,
        )
        request = prepare_mleg_request(intent, now=now)
        quotes = {q.contract_symbol: q for q in snapshot.option_chain}
        long_leg = quotes[outcome.spread.long_contract_symbol]
        short_leg = quotes[outcome.spread.short_contract_symbol]

        # Persist intent, request, order, and a PENDING position BEFORE sending,
        # so a crash between send and response is recoverable from the database.
        order_id = position_id = None
        if self.store is not None and self.decision_row_id is not None:
            try:
                    order_id, position_id = self.store.prepare_entry(
                    decision_id=self.decision_row_id,
                    intent=intent,
                    request=request,
                    direction=outcome.direction,
                    long_symbol=long_leg.contract_symbol,
                    short_symbol=short_leg.contract_symbol,
                    expiration=datetime.combine(
                    long_leg.expiration, datetime.min.time(), tzinfo=UTC
                    ),
                    width=abs(long_leg.strike - short_leg.strike),
                    max_loss=outcome.risk.calculated_max_loss,
                    invalidation=self._typed_invalidation(outcome),
                    deadline_at=deadline_for("entry", now),
                    now=now,
                    )
            except DuplicateIntent as exc:
                # The derived client order id already exists, so this authority
                # was used. Refusing is the idempotency guard working.
                return TickResult(
                    now, "ENTRY_REFUSED", str(exc), snapshot.snapshot_id, recorded_hash
                )

        try:
            submission = self.gateway.submit(
                intent, request, operator_approval=self.operator_approval
            )
        except AmbiguousSubmission as exc:
            # Sent, outcome unknown. Responsibility is retained and new risk
            # halts until reconciliation establishes what the broker holds.
            if self.store is not None and order_id is not None:
                self.store.record_submission(
                    order_id, broker_order_id=None, broker_status=None,
                    ambiguous=True, error=str(exc), now=now,
                )
                self.store.open_incident(
                    kind="ambiguous_entry_submission",
                    detail=f"entry submission outcome unknown: {exc}",
                    position_id=position_id, run_id=self.run_id, now=now,
                )
            self._halt_new_risk()
            # The request was sent and the outcome is unknown, so ask the broker
            # now instead of waiting a tick. Reconciliation either locates the
            # order by our derived client id and resolves the ambiguity, or
            # fails to and keeps new risk halted. Its report governs either way.
            self.reconcile()
            return TickResult(
                now, "ENTRY_AMBIGUOUS", str(exc), snapshot.snapshot_id, recorded_hash
            )
        except ExecutionRefused as exc:
            if self.store is not None and order_id is not None and position_id is not None:
                self.store.record_submission(
                    order_id, broker_order_id=None, broker_status="refused",
                    error=str(exc), now=now,
                )
                # Refused before anything was sent: no exposure can exist.
                self.store.apply_entry_outcome(
                    position_id, state=OrderState.REJECTED, filled_quantity=0,
                    avg_debit=None, now=now,
                )
            return TickResult(
                now, "ENTRY_REFUSED", str(exc), snapshot.snapshot_id, recorded_hash
            )

        # Persist after the mutation. Acceptance is SUBMITTED, never FILLED, so
        # no position is opened here: reconciliation does that, from real fills.
        if self.store is not None and order_id is not None:
            self.store.record_submission(
                order_id, broker_order_id=submission.broker_order_id,
                broker_status=submission.status, ambiguous=submission.ambiguous, now=now,
            )
        # Accepted is not filled. Reconcile now so a same-second fill, or an
        # immediate rejection, is established from broker state rather than
        # inferred from the acknowledgement.
        self.reconcile()
        return TickResult(
            now,
            "ENTRY_SUBMITTED",
            f"{outcome.spread.strategy.value} debit {outcome.spread.estimated_debit} "
            "submitted; awaiting fill reconciliation",
            snapshot.snapshot_id,
            recorded_hash,
            submitted=submission.client_order_id,
        )

    @staticmethod
    def _typed_invalidation(outcome: DecisionOutcome) -> TypedInvalidation | None:
        """The rule the classifier built, carried through unchanged (`EXIT-005`).

        This used to regex a level back out of the English sentence the
        classifier had just formatted it into, which made the first decimal in an
        arbitrary string the thing a live position was managed against. The
        classifier now emits the typed rule and writes the prose from it.
        """
        return outcome.setup.invalidation if outcome.setup is not None else None

    def _record(self, result: TickResult) -> TickResult:
        self.history.append(result)
        return result

    # -- scheduling --------------------------------------------------------
    def run(
        self,
        *,
        interval_seconds: int = DEFAULT_TICK_SECONDS,
        max_ticks: int | None = None,
    ) -> Any:
        """Run the cycle on a fixed cadence until interrupted."""
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(timezone="UTC")
        ticks = {"n": 0}

        def job() -> None:
            result = self.tick()
            print(result.line(), flush=True)
            ticks["n"] += 1
            if max_ticks is not None and ticks["n"] >= max_ticks:
                scheduler.shutdown(wait=False)

        scheduler.add_job(
            job, "interval", seconds=interval_seconds, next_run_time=datetime.now(UTC)
        )
        scheduler.start()
        return scheduler


def halt_state_for(snapshot: DecisionSnapshot) -> ExecutionState:
    """Stale or unusable data halts new risk without trapping an open position."""
    if not snapshot.data_quality.is_usable:
        return ExecutionState.NO_NEW_RISK
    return ExecutionState.NORMAL


def main(argv: Any = None) -> int:
    import argparse
    import sys

    from .config import ConfigurationError, load_settings, resolved_env
    from .persistence.repository import DecisionRecorder, build_engine, create_schema

    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.agent",
        description="Run the autonomous decision cycle. Writes require paper_execute "
        "mode AND an explicit --approve token unless approval is disabled.",
    )
    parser.add_argument("--mode", choices=[m.value for m in BotMode], default="recommend")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--interval", type=int, default=DEFAULT_TICK_SECONDS)
    parser.add_argument("--ticks", type=int, default=1, help="0 runs until interrupted")
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--approve",
        default=None,
        metavar="TOKEN",
        help="Operator approval for opening risk. Without it, entries are refused "
        "whenever REQUIRE_OPERATOR_APPROVAL is set.",
    )
    args = parser.parse_args(argv)

    env = dict(resolved_env())
    env["BOT_MODE"] = args.mode
    if args.mode != BotMode.PAPER_EXECUTE.value:
        # Write authority cannot exist outside paper_execute; make that explicit
        # rather than relying on the caller's .env.
        env["ALPACA_TRADING_ENABLED"] = "false"
    env.setdefault("DATABASE_URL", "sqlite+pysqlite:///agent.db")
    if args.database_url:
        env["DATABASE_URL"] = args.database_url

    try:
        settings = load_settings(env)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    client = ReadOnlyAlpacaClient(
        env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")
    )
    client.option_feed = client.detect_option_feed(args.symbol)
    client.stock_feed = client.detect_stock_feed(args.symbol)

    today = datetime.now(UTC).date()
    calendar = TradingCalendar.from_payload(
        client.calendar(
            (today - timedelta(days=30)).isoformat(), (today + timedelta(days=90)).isoformat()
        ).payload
    )

    synthesizer = None
    if settings.bot_mode is not BotMode.OBSERVE and env.get("OPENAI_API_KEY"):
        from .providers.openai_thesis import BoundedThesisSynthesizer, OpenAIResponsesTransport

        synthesizer = BoundedThesisSynthesizer(
            OpenAIResponsesTransport(env["OPENAI_API_KEY"]),
            model=env.get("OPENAI_MODEL", "gpt-5.6-terra"),
        )

    # The broker is constructed for reconciliation in every mode, not only when
    # writes are permitted. Knowing what we hold is a read, and a position opened
    # by an earlier paper_execute run must still be reconciled and managed by a
    # recommend-mode process. Write authority remains governed by the gateway.
    from .execution.gateway import AlpacaBroker

    gateway_broker = AlpacaBroker(
        env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")
    )
    gateway = ExecutionGateway(gateway_broker, settings) if settings.may_write_orders else None

    engine = build_engine(settings)
    create_schema(engine)
    recorder = DecisionRecorder(engine, settings)

    store = LifecycleStore(engine)
    reconciler = Reconciler(gateway_broker, store)
    deadlines = DeadlineEnforcer(gateway, store) if gateway is not None else None

    agent = TradingAgent(
        settings,
        client=client,
        gateway=gateway,
        synthesizer=synthesizer,
        recorder=recorder,
        store=store,
        reconciler=reconciler,
        deadlines=deadlines,
        calendar=calendar,
        symbol=args.symbol,
        operator_approval=args.approve,
    )
    agent.run_id = recorder.start_run()

    # Reconcile before the agent is permitted to consider any new risk.
    startup = agent.startup()
    if startup is not None:
        print(f"startup: {startup.summary()}")

    print(
        f"mode={settings.bot_mode.value}  writes="
        f"{'ENABLED' if settings.may_write_orders else 'disabled'}  "
        f"approval={'required' if settings.require_operator_approval else 'not required'}  "
        f"feed={client.option_feed}"
    )
    if settings.may_write_orders and not settings.require_operator_approval:
        print("WARNING: fully autonomous writes are enabled for this run.")

    try:
        if args.ticks == 0:
            scheduler = agent.run(interval_seconds=args.interval)
            try:
                import time

                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                scheduler.shutdown(wait=False)
        else:
            for _ in range(args.ticks):
                print(agent.tick().line(), flush=True)
    finally:
        recorder.end_run(agent.run_id, "ok")
        client.close()
    return 0


__all__ = [
    "TickResult",
    "TradingAgent",
    "halt_state_for",
    "parse_occ_symbol",
    "spread_value",
]


if __name__ == "__main__":
    raise SystemExit(main())
