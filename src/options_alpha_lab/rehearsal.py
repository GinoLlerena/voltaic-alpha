"""Run the real agent loop against committed evidence, outside market hours.

The worker is only interesting while the exchange is open. Every other hour of
the week it prints `MARKET_CLOSED` and stops, which is correct behaviour and a
useless demonstration: the reconciliation, the decision workflow, the risk
governor and the execution firewall never get to run where anyone can see them.

Rehearsal drives `TradingAgent.tick()` - the same method the worker calls, not a
copy of it - from committed snapshots instead of live provider reads. Nothing
tells the agent to pretend the market is open. The observation simply comes from
a recording that was taken while it was, which is what a rehearsal is.

Three properties keep this from becoming a way to trade:

* **No gateway is constructed.** A qualified setup reaches `TRADE_CANDIDATE` and
  stops there, which is exactly what the deployed `recommend` worker does.
* **No provider client exists.** `RehearsalClient` raises on every read. If the
  observation path ever changed to reach past the observer, it would fail loudly
  rather than quietly go live.
* **The production database cannot be addressed.** Rehearsal accepts SQLite only
  and ignores the ambient `DATABASE_URL`, so running this on the worker host
  cannot append rehearsal rows to the authoritative store. The rows it does
  write identify themselves anyway: their snapshot ids are the committed fixture
  ids, not the `spy-agent-<stamp>` ids the live agent mints.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agent import Observation, TradingAgent
from .config import ConfigurationError, load_settings, resolved_env
from .execution.lifecycle import LifecycleStore
from .persistence.repository import DecisionRecorder, build_engine, create_schema
from .providers.alpaca_readonly import ProviderError
from .snapshot_io import load_snapshot

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///rehearsal/rehearsal.db"
DEFAULT_SNAPSHOTS = (
    "fixtures/h0/spy_qualified.snapshot.json",
    "fixtures/h0/spy_bearish_qualified.snapshot.json",
    "fixtures/h0/spy_refusal.snapshot.json",
)


class RehearsalClient:
    """The provider surface the agent holds, with every read refused.

    The agent reads `option_feed` when it records a decision, so the attribute
    has to exist and has to be truthful: these quotes came from the indicative
    feed when the snapshot was frozen. Everything else raises, because a
    rehearsal that could fall back to a live read would not be a rehearsal.
    """

    def __init__(self, *, option_feed: str = "indicative", stock_feed: str = "sip") -> None:
        self.option_feed = option_feed
        self.stock_feed = stock_feed

    def _refuse(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ProviderError("rehearsal has no provider: observations come from committed evidence")

    account = clock = calendar = daily_bars = option_chain = option_contracts = _refuse


class SnapshotSource:
    """Serve committed snapshots in order, one per tick, then repeat.

    Reports the market open because the recording was taken during a session.
    Sessions are left empty: `sessions_since` falls back to zero, and a
    rehearsal holds no position for a session count to mean anything about.
    """

    def __init__(self, paths: Sequence[str | Path]) -> None:
        if not paths:
            raise ValueError("a rehearsal needs at least one snapshot")
        self.snapshots = [load_snapshot(path) for path in paths]
        self._next = 0

    def __call__(self, _now: datetime) -> Observation:
        snapshot = self.snapshots[self._next % len(self.snapshots)]
        self._next += 1
        return Observation(snapshot=snapshot, market_open=True, sessions=[])


def _emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.rehearsal",
        description=(
            "Drive the real agent tick from committed snapshots, for a demonstration "
            "recorded outside market hours. No broker, no provider, no write authority."
        ),
    )
    parser.add_argument(
        "snapshots", nargs="*", default=list(DEFAULT_SNAPSHOTS),
        help="Snapshot JSON paths (default: the three H0 fixtures)",
    )
    parser.add_argument(
        "--mode", choices=("observe", "recommend"), default="recommend",
        help="recommend runs the full decision path with writes disabled, as deployed",
    )
    parser.add_argument(
        "--arm", choices=("baseline", "model"), default="baseline",
        help="baseline runs the deterministic thesis; model runs the bounded memo",
    )
    parser.add_argument(
        "--ticks", type=int, default=0,
        help="number of ticks (default 0: one per snapshot)",
    )
    parser.add_argument(
        "--interval", type=float, default=2.0,
        help="seconds between ticks, so a recording is readable",
    )
    parser.add_argument(
        "--database-url", default=DEFAULT_DATABASE_URL,
        help=f"SQLite only (default: {DEFAULT_DATABASE_URL})",
    )
    args = parser.parse_args(argv)

    if not args.database_url.startswith("sqlite"):
        # PostgreSQL is the authoritative production store. A rehearsal that
        # cannot address it cannot contaminate it, and that is a property of the
        # tool rather than of the operator's care at 2am before a deadline.
        print("rehearsal writes SQLite only; the production database is not addressable",
              file=sys.stderr)
        return 2

    path = args.database_url.split("///", 1)[-1]
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Deliberately not `resolved_env()` for the database: the ambient
    # DATABASE_URL on the worker host points at production.
    source: dict[str, str] = dict(resolved_env() if env is None else env)
    # An operator rehearsing on the worker host inherits that host's
    # configuration, which may well be write-capable. Overriding is right - a
    # rehearsal has no business submitting anything - but a silent downgrade is
    # how someone comes to believe they were watching the armed system.
    overridden = (
        source.get("BOT_MODE") != args.mode
        or source.get("ALPACA_TRADING_ENABLED", "false").lower() == "true"
    )
    source["BOT_MODE"] = args.mode
    source["ALPACA_TRADING_ENABLED"] = "false"
    source["DATABASE_URL"] = args.database_url

    try:
        settings = load_settings(source)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if settings.may_write_orders:
        print("refusing to rehearse with order-write authority enabled", file=sys.stderr)
        return 2

    synthesizer = None
    if args.arm == "model":
        from .providers.openai_thesis import BoundedThesisSynthesizer, OpenAIResponsesTransport

        api_key = source.get("OPENAI_API_KEY", "")
        if not api_key:
            print("OPENAI_API_KEY is not set; cannot run the model arm", file=sys.stderr)
            return 2
        synthesizer = BoundedThesisSynthesizer(
            OpenAIResponsesTransport(api_key),
            model=source.get("OPENAI_MODEL", "gpt-5.6-terra"),
            reasoning_effort=source.get("OPENAI_REASONING_EFFORT", "medium"),
        )

    try:
        observer = SnapshotSource(args.snapshots)
    except (OSError, ValueError) as exc:
        print(f"cannot load snapshots: {exc}", file=sys.stderr)
        return 2
    for snapshot in observer.snapshots:
        settings.require_allowed_underlying(snapshot.symbol)

    engine = build_engine(settings)
    create_schema(engine)
    recorder = DecisionRecorder(engine, settings)

    agent = TradingAgent(
        settings,
        client=RehearsalClient(),
        gateway=None,
        synthesizer=synthesizer,
        recorder=recorder,
        store=LifecycleStore(engine),
        observer=observer,
        symbol=observer.snapshots[0].symbol,
    )
    agent.run_id = recorder.start_run()

    ticks = args.ticks if args.ticks > 0 else len(observer.snapshots)
    _emit(
        "rehearsal_started",
        mode=settings.bot_mode.value,
        arm=args.arm,
        writes="disabled",
        broker="none",
        provider="none",
        inherited_config="overridden" if overridden else "unchanged",
        snapshots=len(observer.snapshots),
        ticks=ticks,
        database=args.database_url,
    )

    health = "ok"
    try:
        for index in range(ticks):
            if index and args.interval > 0:
                time.sleep(args.interval)
            result = agent.tick()
            _emit(
                "tick",
                at=result.at.isoformat(),
                action=result.action,
                detail=result.detail,
                snapshot=result.snapshot_id,
                decision_hash=result.decision_hash,
                reason_codes=result.reason_codes,
            )
    except KeyboardInterrupt:
        health = "interrupted"
    finally:
        recorder.end_run(agent.run_id, health)

    _emit(
        "rehearsal_finished",
        ticks=len(agent.history),
        health=health,
        at=datetime.now(UTC).isoformat(),
        note="rehearsal only: committed evidence, no broker contact, no trading claim",
    )
    return 0


def _entrypoint() -> Any:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
