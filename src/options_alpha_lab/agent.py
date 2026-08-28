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
    DecisionSnapshot,
    Direction,
    ExecutionState,
)
from .architecture.workflow import DecisionWorkflow
from .components import (
    DeterministicBaselineThesis,
    DeterministicRiskGovernor,
    DeterministicSetupClassifier,
    DeterministicSpreadSelector,
)
from .config import Settings
from .evidence import build_snapshot, parse_occ_symbol
from .execution.gateway import ExecutionGateway, ExecutionRefused
from .execution.intent import OrderIntent, build_close_intent, build_open_intent
from .execution.request import prepare_mleg_request
from .exits import ExitDecision, ExitTrigger, PositionState, evaluate_exit
from .providers.alpaca_readonly import ProviderError, ReadOnlyAlpacaClient

DEFAULT_TICK_SECONDS = 300
CHAIN_DTE_LOW = 10
CHAIN_DTE_HIGH = 60


@dataclass
class OpenPosition:
    """What the agent needs to manage a position it opened."""

    intent: OrderIntent
    direction: Direction
    entry_debit: Decimal
    width: Decimal
    quantity: int
    invalidation_level: Decimal | None
    expiration: date


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
        symbol: str = "SPY",
        clock: Callable[[], datetime] | None = None,
        operator_approval: str | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.gateway = gateway
        self.synthesizer = synthesizer
        self.recorder = recorder
        self.symbol = symbol
        self.operator_approval = operator_approval
        self._clock = clock or (lambda: datetime.now(UTC))
        self.open_position: OpenPosition | None = None
        self.history: list[TickResult] = []
        self.run_id: str | None = None

    # -- observation -------------------------------------------------------
    def observe(self) -> tuple[DecisionSnapshot, bool]:
        today = date.today()
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

        # Exits before entries, always.
        if self.open_position is not None:
            return self._record(self._manage_open_position(snapshot, now))

        return self._record(self._consider_entry(snapshot, now))

    def _manage_open_position(self, snapshot: DecisionSnapshot, now: datetime) -> TickResult:
        position = self.open_position
        assert position is not None
        value = spread_value(
            snapshot,
            position.intent.legs[0].symbol,
            position.intent.legs[1].symbol,
        )
        state = PositionState(
            direction=position.direction,
            entry_debit=position.entry_debit,
            width=position.width,
            quantity=position.quantity,
            dte=(position.expiration - now.date()).days,
            underlying_price=snapshot.underlying_price,
            invalidation_level=position.invalidation_level,
            current_value=value,
            as_of=now.date(),
        )
        decision = evaluate_exit(state)

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
                now,
                "EXIT_SIGNALLED",
                f"{decision.trigger.value}: {decision.reason} (no write authority)",
                snapshot.snapshot_id,
                exit=decision,
            )

        close_intent = build_close_intent(
            position.intent,
            approval_reference=f"exit:{decision.trigger.value}",
            limit_price=decision.suggested_limit or Decimal("0.01"),
            now=now,
        )
        request = prepare_mleg_request(close_intent, now=now)
        try:
            # reduces_risk: a close must not be blocked by the guards that exist
            # to prevent new risk.
            submission = self.gateway.submit(close_intent, request, reduces_risk=True)
        except ExecutionRefused as exc:
            return TickResult(
                now, "EXIT_REFUSED", str(exc), snapshot.snapshot_id, exit=decision
            )

        self.open_position = None
        return TickResult(
            now,
            "POSITION_CLOSED",
            f"{decision.trigger.value}: {decision.reason}",
            snapshot.snapshot_id,
            exit=decision,
            submitted=submission.client_order_id,
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
        try:
            submission = self.gateway.submit(
                intent, request, operator_approval=self.operator_approval
            )
        except ExecutionRefused as exc:
            return TickResult(
                now, "ENTRY_REFUSED", str(exc), snapshot.snapshot_id, recorded_hash
            )

        quotes = {q.contract_symbol: q for q in snapshot.option_chain}
        long_leg = quotes[outcome.spread.long_contract_symbol]
        short_leg = quotes[outcome.spread.short_contract_symbol]
        self.open_position = OpenPosition(
            intent=intent,
            direction=outcome.direction,
            entry_debit=outcome.spread.estimated_debit,
            width=abs(long_leg.strike - short_leg.strike),
            quantity=outcome.spread.quantity,
            invalidation_level=invalidation_level_from(
                outcome.setup.invalidation_conditions if outcome.setup else ()
            ),
            expiration=long_leg.expiration,
        )
        return TickResult(
            now,
            "POSITION_OPENED",
            f"{outcome.spread.strategy.value} debit {outcome.spread.estimated_debit}",
            snapshot.snapshot_id,
            recorded_hash,
            submitted=submission.client_order_id,
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

    from .config import ConfigurationError, load_env_file, load_settings
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

    env = dict(load_env_file(".env"))
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

    synthesizer = None
    if settings.bot_mode is not BotMode.OBSERVE and env.get("OPENAI_API_KEY"):
        from .providers.openai_thesis import BoundedThesisSynthesizer, OpenAIResponsesTransport

        synthesizer = BoundedThesisSynthesizer(
            OpenAIResponsesTransport(env["OPENAI_API_KEY"]),
            model=env.get("OPENAI_MODEL", "gpt-5.6-terra"),
        )

    gateway = None
    if settings.may_write_orders:
        from .execution.gateway import AlpacaBroker

        gateway = ExecutionGateway(
            AlpacaBroker(env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")),
            settings,
        )

    engine = build_engine(settings)
    create_schema(engine)
    recorder = DecisionRecorder(engine, settings)

    agent = TradingAgent(
        settings,
        client=client,
        gateway=gateway,
        synthesizer=synthesizer,
        recorder=recorder,
        symbol=args.symbol,
        operator_approval=args.approve,
    )
    agent.run_id = recorder.start_run()

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
    "OpenPosition",
    "TickResult",
    "TradingAgent",
    "halt_state_for",
    "invalidation_level_from",
    "parse_occ_symbol",
    "spread_value",
]


if __name__ == "__main__":
    raise SystemExit(main())
