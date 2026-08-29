"""The credentialed worker: a single-writer, restart-recovering agent host.

Addresses `EXIT-016`/`EXIT-AC-16`. Three properties distinguish this from
running the agent in a terminal:

* **Exactly one writer.** A lease is acquired before any work and heartbeated
  while running. Two workers reconciling the same position against the same
  broker would fight, and both could submit.
* **Startup reconciliation precedes entries.** The agent is not permitted to
  consider new risk until it has established what the broker holds.
* **Restart is a normal event.** Nothing lives in process memory, so a crash and
  restart resumes management of the same position rather than forgetting it.

The dashboard reads the same database and holds no credentials. The surface a
judge browses is not the surface that trades.
"""

from __future__ import annotations

import os
import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from .persistence.models import WorkerLease

DEFAULT_LEASE = "options-alpha-worker"
LEASE_TTL = timedelta(seconds=90)
#: The lease must be renewed several times within its own TTL. Heartbeating once
#: per tick would leave it expired between ticks whenever the tick interval
#: exceeds the TTL, and an expired lease is exactly what another worker takes
#: over - while the first is still alive and mid-tick.
HEARTBEAT_INTERVAL_SECONDS = 20


class LeaseUnavailable(RuntimeError):
    """Another worker holds a live lease. Starting anyway would be the bug."""


@dataclass(frozen=True)
class LeaseInfo:
    name: str
    owner: str
    host: str
    acquired_at: datetime
    expires_at: datetime


class LeaseManager:
    """A database-backed single-writer lease with a heartbeat and TTL."""

    def __init__(self, engine: Engine, *, name: str = DEFAULT_LEASE,
                 ttl: timedelta = LEASE_TTL) -> None:
        self._engine = engine
        self._factory = sessionmaker(bind=engine, future=True)
        self.name = name
        self.ttl = ttl
        self.owner = uuid.uuid4().hex[:16]
        self.host = socket.gethostname()

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def acquire(self, *, now: datetime | None = None) -> LeaseInfo:
        """Take the lease, or refuse to start.

        An expired lease is taken over: a worker that died without releasing must
        not block its own replacement forever.
        """
        stamp = now or datetime.now(UTC)
        with self._session() as session:
            existing = session.get(WorkerLease, self.name, with_for_update=True)
            if existing is not None:
                live = (
                    existing.released_at is None
                    and self._aware(existing.expires_at) > stamp
                )
                if live and existing.owner != self.owner:
                    raise LeaseUnavailable(
                        f"lease {self.name!r} is held by {existing.owner} on "
                        f"{existing.host} until "
                        f"{self._aware(existing.expires_at).isoformat()}"
                    )
                existing.owner = self.owner
                existing.host = self.host
                existing.acquired_at = stamp
                existing.heartbeat_at = stamp
                existing.expires_at = stamp + self.ttl
                existing.released_at = None
            else:
                session.add(
                    WorkerLease(
                        name=self.name, owner=self.owner, host=self.host,
                        acquired_at=stamp, heartbeat_at=stamp,
                        expires_at=stamp + self.ttl,
                    )
                )
        return LeaseInfo(self.name, self.owner, self.host, stamp, stamp + self.ttl)

    def heartbeat(self, *, now: datetime | None = None) -> bool:
        """Extend the lease. Returns False if it was lost, which must stop work."""
        stamp = now or datetime.now(UTC)
        with self._session() as session:
            existing = session.get(WorkerLease, self.name, with_for_update=True)
            if existing is None or existing.owner != self.owner:
                return False
            existing.heartbeat_at = stamp
            existing.expires_at = stamp + self.ttl
            return True

    def release(self, *, now: datetime | None = None) -> None:
        stamp = now or datetime.now(UTC)
        with self._session() as session:
            existing = session.get(WorkerLease, self.name, with_for_update=True)
            if existing is not None and existing.owner == self.owner:
                existing.released_at = stamp
                existing.expires_at = stamp

    def current(self) -> LeaseInfo | None:
        with self._session() as session:
            row = session.scalar(select(WorkerLease).where(WorkerLease.name == self.name))
            if row is None or row.released_at is not None:
                return None
            return LeaseInfo(
                row.name, row.owner, row.host,
                self._aware(row.acquired_at), self._aware(row.expires_at),
            )


@dataclass
class WorkerHealth:
    """What a monitor needs to answer "is this thing alive and sane?"."""

    started_at: datetime
    ticks: int = 0
    #: Deadline actions taken by the fast clock between strategy ticks. A worker
    #: that looks idle at tick granularity may have been busy at order
    #: granularity, and a monitor should be able to see that.
    order_clock_actions: int = 0
    last_tick_at: datetime | None = None
    last_action: str | None = None
    last_error: str | None = None
    lease_lost: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at.isoformat(),
            "ticks": self.ticks,
            "order_clock_actions": self.order_clock_actions,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_action": self.last_action,
            "last_error": self.last_error,
            "lease_lost": self.lease_lost,
            "healthy": not self.lease_lost and self.last_error is None,
        }

    def write(self, path: str) -> None:
        import json
        from pathlib import Path

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - linear startup sequence
    import argparse
    import json
    import signal
    import sys
    import time
    from datetime import timedelta as _td
    from types import FrameType

    from .agent import DEFAULT_ORDER_CLOCK_SECONDS, TradingAgent
    from .architecture.contracts import BotMode
    from .calendar import TradingCalendar
    from .config import ConfigurationError, load_settings, resolved_env
    from .execution.deadline import DeadlineEnforcer
    from .execution.gateway import ExecutionGateway
    from .execution.lifecycle import LifecycleStore
    from .execution.reconcile import Reconciler
    from .persistence.repository import DecisionRecorder, build_engine, create_schema
    from .providers.alpaca_readonly import ReadOnlyAlpacaClient

    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.worker",
        description="Run the credentialed single-writer worker.",
    )
    parser.add_argument("--mode", choices=[m.value for m in BotMode], default="recommend")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument(
        "--order-clock-interval", type=int, default=DEFAULT_ORDER_CLOCK_SECONDS,
        help="seconds between deadline checks while a broker mutation is outstanding",
    )
    parser.add_argument("--approve", default=None, metavar="TOKEN")
    parser.add_argument("--health-file", default="/var/run/options-alpha/health.json")
    parser.add_argument("--lease", default=DEFAULT_LEASE)
    parser.add_argument("--max-ticks", type=int, default=0, help="0 runs until stopped")
    args = parser.parse_args(argv)

    env = dict(resolved_env())
    env["BOT_MODE"] = args.mode
    if args.mode != BotMode.PAPER_EXECUTE.value:
        env["ALPACA_TRADING_ENABLED"] = "false"
    if not env.get("DATABASE_URL"):
        print("DATABASE_URL must be set for the worker", file=sys.stderr)
        return 2

    try:
        settings = load_settings(env)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    engine = build_engine(settings)
    create_schema(engine)

    lease = LeaseManager(engine, name=args.lease)
    try:
        held = lease.acquire()
    except LeaseUnavailable as exc:
        # Refusing to start is the correct outcome, not an error to work around.
        print(f"not starting: {exc}", file=sys.stderr)
        return 3

    client = ReadOnlyAlpacaClient(
        env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")
    )
    client.option_feed = client.detect_option_feed(args.symbol)
    client.stock_feed = client.detect_stock_feed(args.symbol)

    today = datetime.now(UTC).date()
    calendar = TradingCalendar.from_payload(
        client.calendar(
            (today - _td(days=30)).isoformat(), (today + _td(days=90)).isoformat()
        ).payload
    )

    synthesizer = None
    if settings.bot_mode is not BotMode.OBSERVE and env.get("OPENAI_API_KEY"):
        from .providers.openai_thesis import (
            BoundedThesisSynthesizer,
            OpenAIResponsesTransport,
        )

        synthesizer = BoundedThesisSynthesizer(
            OpenAIResponsesTransport(env["OPENAI_API_KEY"]),
            model=env.get("OPENAI_MODEL", "gpt-5.6-terra"),
        )

    # Constructed in every mode: reconciliation is a read, and a position opened
    # by an earlier paper_execute run must still be managed by a recommend-mode
    # process. The gateway, not the broker, governs write authority.
    from .execution.gateway import AlpacaBroker

    broker = AlpacaBroker(env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", ""))
    gateway = ExecutionGateway(broker, settings) if settings.may_write_orders else None

    store = LifecycleStore(engine)
    recorder = DecisionRecorder(engine, settings)
    agent = TradingAgent(
        settings, client=client, gateway=gateway, synthesizer=synthesizer,
        recorder=recorder, store=store,
        reconciler=Reconciler(broker, store),
        deadlines=DeadlineEnforcer(gateway, store) if gateway is not None else None,
        calendar=calendar, symbol=args.symbol, operator_approval=args.approve,
    )
    agent.run_id = recorder.start_run()

    health = WorkerHealth(started_at=datetime.now(UTC))
    stopping = {"now": False}

    def stop(signum: int, _frame: FrameType | None) -> None:
        print(f"signal {signum}: finishing the current tick then releasing the lease",
              flush=True)
        stopping["now"] = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    print(json.dumps({
        "event": "worker_started", "lease_owner": held.owner, "host": held.host,
        "mode": settings.bot_mode.value,
        "writes": "enabled" if settings.may_write_orders else "disabled",
        "approval": "required" if settings.require_operator_approval else "not required",
        "feed": client.option_feed, "sessions_loaded": len(calendar),
        "interval_seconds": args.interval,
        "order_clock_seconds": args.order_clock_interval,
    }), flush=True)

    # Reconcile before the agent is permitted to consider any new risk.
    startup = agent.startup()
    if startup is not None:
        print(json.dumps({"event": "startup_reconcile", "summary": startup.summary(),
                          "clean": startup.clean}), flush=True)

    try:
        while not stopping["now"]:
            if not lease.heartbeat():
                # Another worker took over. Stop immediately rather than write
                # against a position we no longer own.
                health.lease_lost = True
                health.write(args.health_file)
                print(json.dumps({"event": "lease_lost", "action": "stopping"}), flush=True)
                return 4
            try:
                result = agent.tick()
                health.ticks += 1
                health.last_tick_at = result.at
                health.last_action = result.action
                health.last_error = None
                print(json.dumps({
                    "event": "tick", "at": result.at.isoformat(), "action": result.action,
                    "detail": result.detail, "snapshot": result.snapshot_id,
                    "order": result.submitted,
                }), flush=True)
            except Exception as exc:  # noqa: BLE001 - a tick failure must not kill the worker
                health.last_error = f"{type(exc).__name__}: {exc}"
                print(json.dumps({"event": "tick_failed", "error": health.last_error}),
                      file=sys.stderr, flush=True)
            health.write(args.health_file)

            if args.max_ticks and health.ticks >= args.max_ticks:
                break

            # Heartbeat through the wait, not just once per tick. The lease must
            # never lapse while this process is alive and holding a position.
            # The order clock runs through it too: a ninety-second deadline
            # cannot be enforced by a loop that sleeps for five minutes.
            waited = 0
            while waited < args.interval and not stopping["now"]:
                time.sleep(1)
                waited += 1
                if waited % HEARTBEAT_INTERVAL_SECONDS == 0 and not lease.heartbeat():
                    health.lease_lost = True
                    health.write(args.health_file)
                    print(json.dumps({"event": "lease_lost", "action": "stopping"}),
                          flush=True)
                    return 4
                # 0 disables the fast clock, and guards the modulo below.
                if args.order_clock_interval <= 0:
                    continue
                if waited % args.order_clock_interval:
                    continue
                try:
                    fast = agent.order_clock()
                except Exception as exc:  # noqa: BLE001 - as for a tick, never fatal
                    health.last_error = f"order_clock: {type(exc).__name__}: {exc}"
                    print(json.dumps({"event": "order_clock_failed",
                                      "error": health.last_error}),
                          file=sys.stderr, flush=True)
                    continue
                if fast is None:
                    continue
                health.order_clock_actions += 1
                health.last_action = fast.action
                print(json.dumps({
                    "event": "order_clock", "at": fast.at.isoformat(),
                    "action": fast.action, "detail": fast.detail,
                }), flush=True)
                health.write(args.health_file)
    finally:
        recorder.end_run(agent.run_id, "ok" if not health.last_error else "degraded")
        lease.release()
        client.close()
        health.write(args.health_file)
        print(json.dumps({"event": "worker_stopped", "ticks": health.ticks}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
