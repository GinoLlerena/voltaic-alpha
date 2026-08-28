"""One Paper open/close lifecycle, from frozen evidence to reconciled broker state.

Dry run is the default. Submitting requires an explicit flag, and the exact body
that will be sent is printed and hashed before anything is written, so the review
step is a real gate rather than a formality.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .architecture.contracts import DecisionAction
from .config import ConfigurationError, load_settings, resolved_env
from .execution.gateway import AlpacaBroker, ExecutionGateway, ExecutionRefused
from .execution.intent import build_close_intent, build_open_intent
from .execution.request import prepare_mleg_request
from .persistence.models import BrokerOrder, PreparedOrderRequest
from .persistence.models import OrderIntent as OrderIntentRow
from .persistence.repository import DecisionRecorder, build_engine, create_schema
from .replay import replay_paths


def _print_request(label: str, request: Any) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(request.body, indent=2, sort_keys=True))
    print(f"intent hash  {request.intent_hash}")
    print(f"request hash {request.request_hash}")
    print(f"client id    {request.client_order_id}")
    print(f"expires      {request.expires_at.isoformat()}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.lifecycle",
        description="Prepare, review, and optionally submit one Paper MLeg lifecycle.",
    )
    parser.add_argument("snapshot", help="Frozen snapshot JSON path")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Actually write to the Paper broker. Omit for a dry run.",
    )
    parser.add_argument("--close", action="store_true", help="Also close the position")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)

    env = dict(resolved_env())
    env.setdefault("DATABASE_URL", "sqlite+pysqlite:///lifecycle.db")
    env["BOT_MODE"] = "paper_execute" if args.submit else "observe"
    if args.submit:
        env["ALPACA_TRADING_ENABLED"] = "true"
    else:
        env["ALPACA_TRADING_ENABLED"] = "false"
    if args.database_url:
        env["DATABASE_URL"] = args.database_url

    try:
        settings = load_settings(env)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    results = replay_paths([args.snapshot], settings)
    result = results[0]
    outcome = result.outcome
    print(f"decision      {outcome.action.value} ({outcome.direction.value})")
    print(f"decision hash {result.recorded.decision_hash}")

    if outcome.action is not DecisionAction.OPTIONS_POSITION:
        print(f"no position to open: {', '.join(outcome.reason_codes) or 'refused'}")
        return 0

    assert outcome.risk is not None
    intent = build_open_intent(
        outcome,
        result.recorded.decision_hash,
        approval_reference=f"risk:{outcome.risk.policy_version}",
    )
    request = prepare_mleg_request(intent)
    _print_request("exact prepared request (open)", request)

    engine = build_engine(settings)
    create_schema(engine)
    recorder = DecisionRecorder(engine, settings)

    if not args.submit:
        print("\nDRY RUN: nothing was sent. Re-run with --submit to write.")
        return 0

    broker = AlpacaBroker(env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", ""))
    gateway = ExecutionGateway(broker, settings)
    print(f"\nresolved endpoint {broker.resolved_endpoint()}")

    try:
        submission = gateway.submit(
            intent, request, operator_approval=f"operator:cli:{datetime.now(UTC).date()}"
        )
    except ExecutionRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    print(f"submitted     {submission.client_order_id} -> {submission.broker_order_id}")
    print(f"status        {submission.status} (ambiguous={submission.ambiguous})")

    _persist(recorder, engine, result, intent, request, submission)

    reconciled = gateway.reconcile(submission.client_order_id)
    print(f"reconciled    {json.dumps(reconciled, default=str)[:400]}")

    if args.close:
        close_intent = build_close_intent(
            intent,
            approval_reference="exit:deterministic_demo_close",
            limit_price=(intent.limit_price * Decimal("0.90")).quantize(Decimal("0.01")),
        )
        close_request = prepare_mleg_request(close_intent)
        _print_request("exact prepared request (close)", close_request)
        try:
            # reduces_risk exempts the close from the one-strategy guard, the
            # halt state, and the approval requirement, all of which exist to
            # stop new risk rather than to trap existing risk.
            close_submission = gateway.submit(
                close_intent, close_request, reduces_risk=True
            )
            print(f"close submitted {close_submission.client_order_id}"
                  f" -> {close_submission.broker_order_id} ({close_submission.status})")
        except ExecutionRefused as exc:
            print(f"close refused: {exc}", file=sys.stderr)
            return 1

    return 0


def _persist(
    recorder: DecisionRecorder,
    engine: Any,
    result: Any,
    intent: Any,
    request: Any,
    submission: Any,
) -> None:
    import uuid

    from sqlalchemy.orm import sessionmaker

    from .persistence.models import Decision

    with sessionmaker(bind=engine, future=True)() as session:
        decision = (
            session.query(Decision)
            .filter(Decision.decision_hash == result.recorded.decision_hash)
            .one_or_none()
        )
        if decision is None:
            return
        intent_id = uuid.uuid4().hex
        session.add(
            OrderIntentRow(
                id=intent_id,
                decision_id=decision.id,
                intent_hash=intent.intent_hash,
                client_order_id=intent.client_order_id,
                legs=[
                    {
                        "symbol": leg.symbol,
                        "ratio_qty": leg.ratio_qty,
                        "side": leg.side,
                        "position_intent": leg.position_intent,
                    }
                    for leg in intent.legs
                ],
                desired_limit_price=intent.limit_price,
                approval_reference=intent.approval_reference,
                expires_at=intent.expires_at,
            )
        )
        # The prepared request and the broker order both reference this intent.
        session.flush()
        session.add(
            PreparedOrderRequest(
                id=uuid.uuid4().hex,
                order_intent_id=intent_id,
                adapter_version=request.adapter_version,
                request_schema_version=request.request_schema_version,
                serialized_request=request.body,
                request_hash=request.request_hash,
                intent_hash_match=request.matches(intent),
                dry_run_result="reviewed",
                prepared_at=request.prepared_at,
                expires_at=request.expires_at,
            )
        )
        session.add(
            BrokerOrder(
                id=uuid.uuid4().hex,
                order_intent_id=intent_id,
                broker_order_id=submission.broker_order_id,
                client_order_id=submission.client_order_id,
                status=submission.status,
                strategy_quantity=intent.strategy_quantity,
                filled_quantity=0,
                submitted_at=submission.submitted_at,
                reconciled_at=datetime.now(UTC) if submission.reconciled else None,
            )
        )
        session.commit()


if __name__ == "__main__":
    raise SystemExit(main())
