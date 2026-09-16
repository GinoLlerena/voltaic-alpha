"""Resolve decision outcomes from the command line.

`CIIP-008`. The worker reviews on its own slow clock; this is the same work,
runnable on demand, and it is how decisions recorded before the reviewer existed
get their review jobs.

Back-filling jobs is offered but not automatic, and the distinction matters. A
job's *horizon* is derived from `decided_at` and completed sessions, so a job
created late still measures the right window -- nothing is fabricated by asking
now about a decision made last week. What a late job cannot claim is that the
question was asked at the time, so `--backfill` is a deliberate flag with a
record, rather than something that quietly happens on first run.

Reads and appends only. It writes review jobs and outcome rows, touches no
decision, position or order, and reaches no broker except the read-only calendar
endpoint the horizon arithmetic needs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calendar import TradingCalendar
from .config import load_settings, resolved_env
from .outcomes import ensure_jobs, review
from .persistence.models import Decision, DecisionOutcomeRecord, ReviewJob
from .persistence.repository import build_engine
from .providers.alpaca_readonly import ReadOnlyAlpacaClient


def _calendar(symbol: str) -> TradingCalendar:
    env = resolved_env()
    client = ReadOnlyAlpacaClient(
        env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")
    )
    try:
        today = datetime.now(UTC).date()
        # Wide enough that a horizon never falls outside the window: the
        # arithmetic counts sessions, and a missing session would undercount.
        return TradingCalendar.from_payload(
            client.calendar(
                (today - timedelta(days=120)).isoformat(),
                (today + timedelta(days=30)).isoformat(),
            ).payload
        )
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve decision outcomes at their horizons")
    parser.add_argument(
        "--backfill", action="store_true",
        help="create review jobs for decisions that have none, then review",
    )
    parser.add_argument("--symbol", default="SPY", help="symbol whose calendar is used")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would be done, write nothing"
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    engine = build_engine(settings)
    calendar = _calendar(args.symbol)

    created = 0
    with Session(engine) as session:
        decisions = session.scalars(select(Decision)).all()
        without = [
            decision
            for decision in decisions
            if not session.scalars(
                select(ReviewJob).where(ReviewJob.decision_id == decision.id)
            ).first()
        ]
        if args.backfill and not args.dry_run:
            for decision in without:
                created += len(ensure_jobs(session, decision))
            session.commit()

        if args.dry_run:
            summary = {
                "dry_run": True,
                "decisions": len(decisions),
                "decisions_without_jobs": len(without),
                "jobs_that_would_be_created": len(without) * 2 if args.backfill else 0,
                "sessions_in_calendar": len(calendar),
            }
            print(json.dumps(summary, indent=2))
            return 0

        resolved = review(session, calendar)
        session.commit()
        outcomes_total = len(session.scalars(select(DecisionOutcomeRecord)).all())
        pending_total = len(
            session.scalars(select(ReviewJob).where(ReviewJob.state == "PENDING")).all()
        )

    print(json.dumps({
        "decisions": len(decisions),
        "jobs_created": created,
        "resolved_now": resolved.completed,
        "still_pending": pending_total,
        "outcomes_total": outcomes_total,
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
