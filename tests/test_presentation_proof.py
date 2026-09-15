"""Regression tests for `CIIP-003`: no headline tile may be a typed literal.

The acceptance criterion is "no operational tile is a literal masquerading as
observed state". That is hard to assert directly, so these tests attack it from
the side that actually catches regressions: a tile must change when the records
change, and must degrade to `UNAVAILABLE` when the records are absent. A
hardcoded value fails both.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from options_alpha_lab.persistence.models import (
    Base,
    BrokerOrder,
    OrderIntent,
    Position,
)
from options_alpha_lab.presentation.proof import (
    model_effect,
    paper_lifecycles,
    write_boundary,
)

NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _lifecycle(session: Session, *, decision_id: str, closed: bool) -> None:
    """One decision's orders plus its position.

    No `Decision` row is created: `paper_lifecycles` correlates through
    `order_intents.decision_id`, and never reads the decisions table. Building
    one would only add required columns the assertion does not depend on.
    """
    for role in ("entry", "close") if closed else ("entry",):
        intent_id, order_id = f"i-{decision_id}-{role}", f"o-{decision_id}-{role}"
        session.add(
            OrderIntent(
                id=intent_id,
                decision_id=decision_id,
                intent_hash=f"ih-{decision_id}-{role}",
                client_order_id=f"c-{decision_id}-{role}",
                legs=[],
                desired_limit_price=3,
                approval_reference="test",
                expires_at=NOW + timedelta(minutes=5),
            )
        )
        session.add(
            BrokerOrder(
                id=order_id,
                order_intent_id=intent_id,
                client_order_id=f"c-{decision_id}-{role}",
                role=role,
                status="filled",
                local_state="FILLED",
                terminal=True,
                strategy_quantity=1,
                prepared_at=NOW,
            )
        )
    session.add(
        Position(
            id=f"p-{decision_id}",
            decision_id=decision_id,
            entry_order_id=f"o-{decision_id}-entry",
            strategy="bull_call_debit_spread",
            direction="bullish",
            lifecycle_status="CLOSED" if closed else "OPEN",
            long_symbol="L",
            short_symbol="S",
            expiration=NOW + timedelta(days=12),
            width=6,
            requested_quantity=1,
            open_risk=339,
        )
    )
    session.commit()


class PaperLifecycleTileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _session()

    def tearDown(self) -> None:
        self.session.close()

    def test_empty_database_is_unavailable_not_one(self) -> None:
        tile = paper_lifecycles(self.session)
        self.assertEqual(tile.value, "0")
        self.assertEqual(tile.mode, "UNAVAILABLE")
        self.assertFalse(tile.available)

    def test_open_position_alone_does_not_count(self) -> None:
        _lifecycle(self.session, decision_id="d1", closed=False)
        self.assertEqual(paper_lifecycles(self.session).mode, "UNAVAILABLE")

    def test_closed_round_trip_counts_once(self) -> None:
        _lifecycle(self.session, decision_id="d1", closed=True)
        tile = paper_lifecycles(self.session)
        self.assertEqual(tile.value, "1")
        self.assertEqual(tile.mode, "OBSERVED PAPER")
        self.assertIn("lifecycle", tile.label)

    def test_the_count_tracks_the_records(self) -> None:
        """The tile is derived, so a second round trip must move it to 2."""
        _lifecycle(self.session, decision_id="d1", closed=True)
        _lifecycle(self.session, decision_id="d2", closed=True)
        self.assertEqual(paper_lifecycles(self.session).value, "2")

    def test_correlation_does_not_leak_across_decisions(self) -> None:
        """An entry on one decision and a close on another is not a round trip."""
        _lifecycle(self.session, decision_id="d1", closed=False)
        _lifecycle(self.session, decision_id="d2", closed=False)
        self.assertEqual(paper_lifecycles(self.session).mode, "UNAVAILABLE")


class ArtifactTileTests(unittest.TestCase):
    def test_model_effect_reads_the_artifact(self) -> None:
        tile = model_effect(ROOT / "artifacts" / "ablation_h0.json")
        self.assertEqual(tile.mode, "DERIVED")
        self.assertEqual(tile.value, "0")
        self.assertIn("5 cases", tile.label)
        # The uncomfortable half must travel with the number.
        self.assertIn("not evidence about returns", tile.detail)

    def test_model_effect_degrades_when_the_artifact_is_gone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tile = model_effect(Path(tmp) / "absent.json")
        self.assertEqual(tile.mode, "UNAVAILABLE")
        self.assertNotEqual(tile.value, "0")

    def test_model_effect_tracks_a_different_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ablation.json"
            path.write_text(
                json.dumps(
                    {"metrics": {"decisions_changed_by_model": 3, "cases_compared": 9}}
                ),
                encoding="utf-8",
            )
            tile = model_effect(path)
        self.assertEqual(tile.value, "3")
        self.assertIn("9 cases", tile.label)

    def test_write_boundary_requires_the_gate_to_exist(self) -> None:
        self.assertEqual(
            write_boundary(ROOT / "scripts" / "check_no_write_path.py").mode, "DERIVED"
        )
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                write_boundary(Path(tmp) / "absent.py").mode, "UNAVAILABLE"
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
