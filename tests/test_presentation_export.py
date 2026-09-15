"""Regression tests for `CIIP-007`: byte-stable manifests, redacted by schema.

Two acceptance criteria, and they are tested differently on purpose.

Determinism is asserted by rendering twice and by rebuilding the view from a
fresh session, because the failure mode is subtle — a set iteration or an
insertion-ordered dict produces stable output within one process and diverges
across two.

Redaction is asserted adversarially. Secrets are seeded into the records the
exporter reads from, and the output must not contain them. That catches the
failure that post-hoc masking always eventually has: it protects the patterns
someone remembered and ships the rest. An allowlist passes this by construction,
which is the point of building one.
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from options_alpha_lab.persistence.models import (
    Base,
    Decision,
    MarketSnapshot,
    PreparedOrderRequest,
    Run,
    ThesisRecord,
)
from options_alpha_lab.persistence.models import OrderIntent as Intent
from options_alpha_lab.presentation import export
from options_alpha_lab.presentation.decision import load

DB = Path(__file__).resolve().parents[1] / "demo" / "h0_demo.db"
NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)

LIFECYCLE = "spy-lifecycle-20260828T154747Z"
REFUSAL = "spy-refusal-2026-08-27"

#: Values that must never reach a manifest. Shapes, not real credentials.
SECRETS = {
    "api_key": "PKTEST0000NEVEREXPORTED",
    "secret_key": "SKTESTsecretkeymustnotappear",
    "account": "PA9ZZZ00ACCOUNT",
    "bearer": "Bearer eyJhbGciOiJIUzI1NiJ9.must.not.ship",
}


def _committed() -> Session:
    return Session(create_engine(f"sqlite+pysqlite:///{DB}", future=True))


def _view(session: Session, snapshot_id: str):  # type: ignore[no-untyped-def]
    decision = session.scalars(
        select(Decision).where(Decision.snapshot_id == snapshot_id)
    ).one()
    return load(session, decision)


class DeterminismTests(unittest.TestCase):
    def test_two_renders_are_byte_identical(self) -> None:
        with _committed() as session:
            view = _view(session, LIFECYCLE)
            self.assertEqual(export.render(view), export.render(view))

    def test_a_fresh_session_produces_the_same_bytes(self) -> None:
        """The failure this catches only appears across processes."""
        with _committed() as first:
            a = export.render(_view(first, LIFECYCLE))
        with _committed() as second:
            b = export.render(_view(second, LIFECYCLE))
        self.assertEqual(a, b)

    def test_the_digest_is_stable(self) -> None:
        with _committed() as session:
            view = _view(session, LIFECYCLE)
            self.assertEqual(export.digest(view), export.digest(view))

    def test_different_decisions_produce_different_digests(self) -> None:
        with _committed() as session:
            self.assertNotEqual(
                export.digest(_view(session, LIFECYCLE)),
                export.digest(_view(session, REFUSAL)),
            )

    def test_keys_are_sorted_so_a_diff_is_readable(self) -> None:
        with _committed() as session:
            text = export.render(_view(session, LIFECYCLE)).decode()
        manifest = json.loads(text)
        self.assertEqual(list(manifest), sorted(manifest))

    def test_there_is_no_wall_clock_in_the_output(self) -> None:
        """A generated_at field would make every export differ from every other."""
        with _committed() as session:
            manifest = export.manifest(_view(session, LIFECYCLE))
        self.assertNotIn("generated_at", manifest)
        self.assertNotIn("exported_at", manifest)


class ContentTests(unittest.TestCase):
    def test_a_refusal_records_not_called_rather_than_an_empty_section(self) -> None:
        with _committed() as session:
            manifest = export.manifest(_view(session, REFUSAL))
        self.assertEqual(manifest["model_memo"], "NOT_CALLED")
        self.assertFalse(manifest["model_was_called"])
        self.assertFalse(manifest["reached_the_broker"])

    def test_the_chain_is_present_for_an_executed_decision(self) -> None:
        with _committed() as session:
            manifest = export.manifest(_view(session, LIFECYCLE))
        self.assertTrue(manifest["observation"]["payload_hash"])
        self.assertTrue(manifest["intents"][0]["intent_hash"])
        self.assertTrue(manifest["broker_orders"])
        self.assertTrue(manifest["broker_orders"][0]["fills"])
        self.assertTrue(manifest["positions"])

    def test_the_manifest_asserts_no_sample_size(self) -> None:
        """`RUI-VAL-010`. It claimed "two trades"; nothing counted them, and the
        page's own derived count is one."""
        import re

        with _committed() as session:
            manifest = export.manifest(_view(session, LIFECYCLE))
        self.assertEqual(manifest["manifest_version"], "proof-manifest-2")
        for line in manifest["disclosures"]:
            self.assertNotIn("two trades", line)
            self.assertIsNone(
                re.search(r"sample is (one|two|three|\d+)", line),
                f"a counted claim belongs in a derived tile, not in copy: {line}",
            )

    def test_disclosures_travel_with_the_proof(self) -> None:
        with _committed() as session:
            manifest = export.manifest(_view(session, LIFECYCLE))
        self.assertEqual(len(manifest["disclosures"]), 4)
        self.assertTrue(any("No alpha" in d for d in manifest["disclosures"]))


class RedactionTests(unittest.TestCase):
    """Seed secrets into the source records; the manifest must not carry them."""

    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.session.add(
            Run(
                id="r",
                runtime_version="t",
                policy_version="t",
                bot_mode="paper_execute",
                trading_enabled=True,
                started_at=NOW,
            )
        )
        self.session.add(
            MarketSnapshot(
                id="s",
                run_id="r",
                snapshot_id="spy-secret",
                symbol="SPY",
                provider="alpaca",
                feed="indicative",
                source_time=NOW,
                received_time=NOW,
                underlying_price=600,
                payload_hash="ph",
                # The account block lives here in production.
                payload={"account": {"account_id": SECRETS["account"]}},
                data_quality={},
            )
        )
        self.decision = Decision(
            id="d",
            run_id="r",
            market_snapshot_id="s",
            snapshot_id="spy-secret",
            action="OPTIONS_POSITION",
            direction="bullish",
            reason_codes=[],
            transitions=[],
            input_hash="ih",
            decision_hash="dh",
            policy_version="t",
            decided_at=NOW,
        )
        self.session.add(self.decision)
        self.session.add(
            ThesisRecord(
                id="t",
                decision_id="d",
                synthesizer_name="s",
                direction="bullish",
                confidence="0.7",
                evidence_ids=[],
                counter_evidence_ids=[],
                invalidation_conditions=[],
                # Raw model prose is the one field nobody controls.
                reasoning_summary=f"leaked {SECRETS['secret_key']}",
            )
        )
        self.session.add(
            Intent(
                id="i",
                decision_id="d",
                intent_hash="ihx",
                client_order_id="oa-x",
                legs=[],
                desired_limit_price=3,
                approval_reference="t",
                expires_at=NOW + timedelta(minutes=5),
            )
        )
        self.session.add(
            PreparedOrderRequest(
                id="pr",
                order_intent_id="i",
                adapter_version="v",
                request_schema_version="v",
                # The exact bytes sent to the broker, headers included.
                serialized_request={
                    "headers": {"Authorization": SECRETS["bearer"]},
                    "APCA-API-KEY-ID": SECRETS["api_key"],
                },
                request_hash="rh",
                intent_hash_match=True,
                prepared_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
            )
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_no_seeded_secret_appears_anywhere_in_the_manifest(self) -> None:
        body = export.render(load(self.session, self.decision)).decode()
        for name, value in SECRETS.items():
            self.assertNotIn(value, body, f"{name} reached the proof manifest")

    def test_the_serialized_request_is_represented_by_its_hash(self) -> None:
        manifest = export.manifest(load(self.session, self.decision))
        request = manifest["prepared_requests"][0]
        self.assertEqual(request["request_hash"], "rh")
        self.assertNotIn("serialized_request", request)

    def test_the_snapshot_payload_is_not_shipped(self) -> None:
        manifest = export.manifest(load(self.session, self.decision))
        self.assertNotIn("payload", manifest["observation"])
        self.assertEqual(manifest["observation"]["payload_hash"], "ph")

    def test_raw_model_prose_is_not_shipped(self) -> None:
        manifest = export.manifest(load(self.session, self.decision))
        self.assertNotIn("reasoning_summary", manifest["model_memo"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
