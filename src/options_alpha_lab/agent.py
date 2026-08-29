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
    LifecycleStore,
    ManagedPosition,
    OrderState,
    PositionState,
    TypedInvalidation,
)
from .execution.reconcile import Reconciler, ReconciliationReport
from .execution.request import prepare_mleg_request
from .exits import ExitDecision, ExitInputs, ExitTrigger, evaluate_exit
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


def invalidation_level_from(conditions: tuple[str, ...]) -> Decimal | None:
    """Recover the numeric level the deterministic classifier wrote."""
    import re

    for condition in conditions:
        match = re.search(r"(\d+\.\d+)", condition)
        if match:
            return Decimal(match.group(1))
    return None


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
        return DecisionWorkflow(
            setup_classifier=DeterministicSetupClassifier(),
            thesis_synthesizer=(
                self.synthesizer
                if self.synthesizer is not None and self.settings.bot_mode is not BotMode.OBSERVE
                else DeterministicBaselineThesis()
            ),
            options_selector=DeterministicSpreadSelector(),
            risk_governor=DeterministicRiskGovernor(self.settings.policy_version),
        )

    # -- the cycle ---------------------------------------------------------
    def tick(self) -> TickResult:
        now = self._clock()
        try:
            snapshot, market_open = self.observe()
        except (ProviderError, ValueError) as exc:
            return self._record(
                TickResult(now, "OBSERVE_FAILED", f"{type(exc).__name__}: {exc}")
            )

        if not market_open:
            return self._record(TickResult(now, "MARKET_CLOSED", "no action taken"))

        # Reconcile before deciding anything. Stale beliefs about what we hold
        # are the failure this whole cycle exists to prevent.
        report = self.reconcile()

        # Then enforce post-submission deadlines, so an unfilled order is
        # cancelled rather than left occupying the single strategy slot.
        if self.deadlines is not None and self.settings.may_write_orders:
            outcome = self.deadlines.enforce(run_id=self.run_id, now=now)
            self.last_deadline_outcome = outcome
            if outcome.late_fills or outcome.failures:
                self.execution_state = ExecutionState.NO_NEW_RISK
                if self.gateway is not None:
                    self.gateway.execution_state = ExecutionState.NO_NEW_RISK
            if outcome.acted:
                return self._record(
                    TickResult(now, "DEADLINE_ACTION", outcome.summary(),
                               snapshot.snapshot_id)
                )

        # Exits before entries, always.
        managed = self.active_position()
        if managed is not None:
            return self._record(self._manage_open_position(managed, snapshot, now))

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

        # A close is already working. Evaluating the exit policy again here would
        # submit a second close for the same exposure; responsibility is retained
        # by monitoring, not by re-submitting (EXIT-006).
        if position.state is PositionState.CLOSING:
            return TickResult(
                now,
                "CLOSE_WORKING",
                f"close order is working for {position.long_symbol}/"
                f"{position.short_symbol}; ownership retained until the broker "
                "confirms flat",
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
            invalidation_level=(
                position.invalidation.level if position.invalidation else None
            ),
            current_value=value,
            as_of=now.date(),
            sessions_elapsed=self.sessions_since(position.entry_filled_at),
        )
        decision = evaluate_exit(inputs)

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
            self.execution_state = ExecutionState.NO_NEW_RISK
            if self.gateway is not None:
                self.gateway.execution_state = ExecutionState.NO_NEW_RISK

        if not decision.should_close:
            action = (
                "POSITION_REVIEW"
                if decision.trigger is ExitTrigger.UNMEASURABLE
                else "POSITION_HELD"
            )
            return TickResult(
                now, action, decision.reason, snapshot.snapshot_id, exit=decision
            )

        if self.gateway is None or not self.settings.may_write_orders:
            return TickResult(
                now, "EXIT_SIGNALLED",
                f"{decision.trigger.value}: {decision.reason} (no write authority)",
                snapshot.snapshot_id, exit=decision,
            )
        if decision.suggested_limit is None:
            return TickResult(
                now, "EXIT_BLOCKED",
                f"{decision.trigger.value} fired but the close cannot be priced from "
                "the current chain; position retained and incident raised",
                snapshot.snapshot_id, exit=decision,
            )

        entry_intent = self._entry_intent_for(position)
        if entry_intent is None:
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
        return TickResult(
            now, "CLOSE_SUBMITTED",
            f"{decision.trigger.value}: {decision.reason}",
            snapshot.snapshot_id, exit=decision,
            submitted=submission.client_order_id,
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
            self.execution_state = ExecutionState.NO_NEW_RISK
            if self.gateway is not None:
                self.gateway.execution_state = ExecutionState.NO_NEW_RISK
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
        """Store invalidation as a typed rule rather than prose (`EXIT-005`)."""
        if outcome.setup is None:
            return None
        level = invalidation_level_from(outcome.setup.invalidation_conditions)
        if level is None:
            return None
        return TypedInvalidation(
            level=level, direction=outcome.setup.direction, source="daily_close"
        )

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

    gateway = None
    gateway_broker = None
    if settings.may_write_orders:
        from .execution.gateway import AlpacaBroker

        gateway_broker = AlpacaBroker(
            env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")
        )
        gateway = ExecutionGateway(gateway_broker, settings)

    engine = build_engine(settings)
    create_schema(engine)
    recorder = DecisionRecorder(engine, settings)

    store = LifecycleStore(engine)
    reconciler = Reconciler(gateway_broker, store) if gateway_broker is not None else None
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
    "invalidation_level_from",
    "parse_occ_symbol",
    "spread_value",
]


if __name__ == "__main__":
    raise SystemExit(main())
