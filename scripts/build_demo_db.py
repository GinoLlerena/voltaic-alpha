#!/usr/bin/env python3
"""Build the committed evidence database the judge dashboard reads.

PostgreSQL is authoritative in production. The hosted judge view runs on
Streamlit, which cannot reach a private database, so the demo replays committed
fixtures into a SQLite file. Nothing is invented here: the decision rows are
produced by the same workflow the tests exercise, and the execution rows are the
recorded result of the real Paper lifecycle in artifacts/h0_paper_lifecycle.json.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from options_alpha_lab.config import load_settings  # noqa: E402
from options_alpha_lab.persistence.models import (  # noqa: E402
    BrokerOrder,
    Decision,
    Fill,
    OrderIntent,
    Position,
    PreparedOrderRequest,
)
from options_alpha_lab.persistence.repository import build_engine, create_schema  # noqa: E402
from options_alpha_lab.replay import replay_paths  # noqa: E402

DEFAULT_OUTPUT = Path("demo/h0_demo.db")
FIXTURES = [
    Path("fixtures/h0/spy_qualified.snapshot.json"),
    Path("fixtures/h0/spy_bearish_qualified.snapshot.json"),
    Path("fixtures/h0/spy_refusal.snapshot.json"),
]
RECEIPT = Path("artifacts/h0_paper_lifecycle.json")


def main() -> int:
    # Validation must not rewrite the committed artifact: the rebuilt file
    # differs by row ids and timestamps every run, which would leave the working
    # tree permanently dirty and make the release freeze digest unstable.
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    settings = load_settings(
        {
            "BOT_MODE": "observe",
            "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{output}",
        }
    )
    frozen = sorted(Path("fixtures/h0/frozen").glob("*.snapshot.json"))
    results = replay_paths(FIXTURES + frozen, settings)
    print(f"replayed {len(results)} snapshot(s)")

    engine = build_engine(settings)
    create_schema(engine)

    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    from sqlalchemy.orm import sessionmaker

    with sessionmaker(bind=engine, future=True)() as session:
        decision = (
            session.query(Decision)
            .filter(Decision.snapshot_id == receipt["snapshot_id"])
            .one_or_none()
        )
        if decision is None:
            # The lifecycle snapshot may not be committed; attach to the qualified case.
            decision = (
                session.query(Decision)
                .filter(Decision.action == "OPTIONS_POSITION")
                .order_by(Decision.recorded_at)
                .first()
            )
        if decision is None:
            print("no approved decision to attach execution evidence to", file=sys.stderr)
            return 1

        # Execution evidence now carries the durable lifecycle: the broker's own
        # status, our local state, and the actual filled price rather than the
        # limit. The recorded run reconciled to flat, so the position is CLOSED.
        entry_order_id = None
        for phase in ("open", "close"):
            leg_data = receipt[phase]
            intent_id = uuid.uuid4().hex
            order_id = uuid.uuid4().hex
            if phase == "open":
                entry_order_id = order_id
            session.add(
                OrderIntent(
                    id=intent_id,
                    decision_id=decision.id,
                    intent_hash=leg_data["intent_hash"],
                    client_order_id=leg_data["client_order_id"],
                    legs=leg_data["legs"],
                    desired_limit_price=Decimal(leg_data["limit_price"]),
                    approval_reference=f"risk:h0-provisional-1:{phase}",
                    expires_at=datetime.fromisoformat(receipt["recorded_at"]),
                )
            )
            session.flush()
            session.add(
                PreparedOrderRequest(
                    id=uuid.uuid4().hex,
                    order_intent_id=intent_id,
                    adapter_version="alpaca-py-0.44-mleg",
                    request_schema_version="mleg_limit.v1",
                    serialized_request={
                        "order_class": leg_data["order_class"],
                        "qty": str(leg_data["qty"]),
                        "type": "limit",
                        "time_in_force": "day",
                        "limit_price": leg_data["limit_price"],
                        "client_order_id": leg_data["client_order_id"],
                        "legs": leg_data["legs"],
                    },
                    request_hash=leg_data["request_hash"],
                    intent_hash_match=True,
                    dry_run_result="reviewed",
                    prepared_at=datetime.fromisoformat(receipt["recorded_at"]),
                    expires_at=datetime.fromisoformat(receipt["recorded_at"]),
                )
            )
            session.add(
                BrokerOrder(
                    id=order_id,
                    order_intent_id=intent_id,
                    broker_order_id=leg_data.get("broker_order_id"),
                    client_order_id=leg_data["client_order_id"],
                    role="entry" if phase == "open" else "close",
                    status=leg_data["status"],
                    local_state="FILLED",
                    terminal=True,
                    strategy_quantity=int(leg_data["qty"]),
                    filled_quantity=int(leg_data["qty"]),
                    filled_avg_price=Decimal(leg_data["filled_avg_price"]),
                    prepared_at=datetime.fromisoformat(receipt["recorded_at"]),
                    submitted_at=datetime.fromisoformat(receipt["recorded_at"]),
                    reconciled_at=datetime.now(UTC),
                )
            )
            session.flush()
            for leg in leg_data["legs"]:
                session.add(
                    Fill(
                        id=uuid.uuid4().hex,
                        broker_order_id=order_id,
                        leg_symbol=leg["symbol"],
                        quantity=int(leg["filled_qty"]),
                        price=Decimal(leg["filled_avg_price"]),
                        filled_at=datetime.fromisoformat(receipt["recorded_at"]),
                    )
                )

        legs = receipt["open"]["legs"]
        session.add(
            Position(
                id=uuid.uuid4().hex,
                decision_id=decision.id,
                entry_order_id=entry_order_id,
                close_order_id=None,
                strategy="bull_call_debit_spread",
                direction="bullish",
                lifecycle_status="CLOSED",
                long_symbol=legs[0]["symbol"],
                short_symbol=legs[1]["symbol"],
                expiration=datetime.fromisoformat(receipt["recorded_at"]),
                width=Decimal("6.00"),
                requested_quantity=1,
                filled_quantity=0,
                avg_entry_debit=Decimal(receipt["open"]["filled_avg_price"]),
                open_risk=Decimal("339.00"),
                entry_filled_at=datetime.fromisoformat(receipt["recorded_at"]),
                opened_at=datetime.fromisoformat(receipt["recorded_at"]),
                closed_at=datetime.fromisoformat(receipt["recorded_at"]),
                close_reason="manual_demo_close",
            )
        )
        session.commit()

    print(f"wrote {output} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
