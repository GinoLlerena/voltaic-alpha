"""Phase 4: duplicates and ambiguity cannot create a second strategy."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from options_alpha_lab.architecture.contracts import ExecutionState, SpreadStrategy
from options_alpha_lab.config import load_settings
from options_alpha_lab.execution.gateway import (
    BrokerPort,
    ExecutionGateway,
    ExecutionRefused,
    SubmissionResult,
)
from options_alpha_lab.execution.intent import (
    INTENT_TTL,
    IntentError,
    IntentLeg,
    OrderIntent,
    build_close_intent,
    build_open_intent,
)
from options_alpha_lab.execution.request import RequestError, prepare_mleg_request

NOW = datetime(2026, 8, 28, 15, 40, tzinfo=UTC)

PAPER_ENV = {
    "BOT_MODE": "paper_execute",
    "ALPACA_PAPER_TRADE": "true",
    "ALPACA_TRADING_ENABLED": "true",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
}


def intent(**overrides: Any) -> OrderIntent:
    base = {
        "decision_hash": "sha256:abc",
        "strategy": SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        "legs": (
            IntentLeg("SPY260918C00640000", 1, "buy", "buy_to_open"),
            IntentLeg("SPY260918C00645000", 1, "sell", "sell_to_open"),
        ),
        "strategy_quantity": 1,
        "limit_price": Decimal("3.00"),
        "approval_reference": "risk:approved",
        "created_at": NOW,
        "expires_at": NOW + INTENT_TTL,
    }
    base.update(overrides)
    return OrderIntent(**base)  # type: ignore[arg-type]


class FakeBroker(BrokerPort):
    def __init__(self, *, endpoint: str = "https://paper-api.alpaca.markets",
                 open_strategies: int = 0, fail: Exception | None = None,
                 existing: dict[str, Any] | None = None) -> None:
        self.endpoint = endpoint
        self.open_strategies = open_strategies
        self.fail = fail
        self.orders: dict[str, dict[str, Any]] = dict(existing or {})
        self.submits: list[dict[str, Any]] = []

    def resolved_endpoint(self) -> str:
        return self.endpoint

    def open_strategy_count(self) -> int:
        return self.open_strategies

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        self.submits.append(body)
        if self.fail is not None:
            # The broker may still have accepted it; that is what makes it ambiguous.
            self.orders[body["client_order_id"]] = {"id": "brk-1", "status": "accepted"}
            raise self.fail
        if body["client_order_id"] in self.orders:
            raise RuntimeError("duplicate client_order_id")
        self.orders[body["client_order_id"]] = {"id": "brk-1", "status": "accepted"}
        return self.orders[body["client_order_id"]]

    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        return self.orders.get(client_order_id)


def gateway(broker: FakeBroker, **kwargs: Any) -> ExecutionGateway:
    return ExecutionGateway(
        broker, load_settings(PAPER_ENV), clock=lambda: NOW, **kwargs
    )


class IdempotencyTests(unittest.TestCase):
    def test_client_order_id_is_derived_not_random(self) -> None:
        self.assertEqual(intent().client_order_id, intent().client_order_id)

    def test_any_change_to_the_intent_changes_the_id(self) -> None:
        base = intent().client_order_id
        self.assertNotEqual(base, intent(limit_price=Decimal("3.01")).client_order_id)
        self.assertNotEqual(base, intent(strategy_quantity=2).client_order_id)
        self.assertNotEqual(base, intent(decision_hash="sha256:other").client_order_id)

    def test_a_duplicate_submit_cannot_open_a_second_strategy(self) -> None:
        broker = FakeBroker()
        first = gateway(broker).submit(intent(), prepare_mleg_request(intent(), now=NOW))
        self.assertEqual(first.status, "accepted")
        # The same approved intent produces the same id, so the broker collides.
        with self.assertRaises(RuntimeError):
            broker.submit(prepare_mleg_request(intent(), now=NOW).body)
        self.assertEqual(len(broker.orders), 1)


class AmbiguityTests(unittest.TestCase):
    def test_ambiguous_submit_is_resolved_by_lookup_not_retry(self) -> None:
        broker = FakeBroker(fail=TimeoutError("connection reset"))
        result = gateway(broker).submit(intent(), prepare_mleg_request(intent(), now=NOW))
        self.assertIsInstance(result, SubmissionResult)
        self.assertTrue(result.ambiguous)
        self.assertTrue(result.reconciled)
        self.assertEqual(result.broker_order_id, "brk-1")
        # Exactly one submit attempt was made.
        self.assertEqual(len(broker.submits), 1)
        self.assertEqual(len(broker.orders), 1)

    def test_failure_with_no_order_present_refuses_rather_than_guessing(self) -> None:
        class Vanishing(FakeBroker):
            def submit(self, body: dict[str, Any]) -> dict[str, Any]:
                raise TimeoutError("never arrived")

        with self.assertRaises(ExecutionRefused):
            gateway(Vanishing()).submit(intent(), prepare_mleg_request(intent(), now=NOW))


class PreflightTests(unittest.TestCase):
    def refuse(self, message: str, **kwargs: Any) -> None:
        broker_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in {"endpoint", "open_strategies", "fail", "existing"}
        }
        now = kwargs.get("now", NOW)
        broker = FakeBroker(**broker_kwargs)
        gw = ExecutionGateway(
            broker,
            load_settings(kwargs.get("env", PAPER_ENV)),
            execution_state=kwargs.get("state", ExecutionState.NORMAL),
            clock=lambda: now,
        )
        with self.assertRaises(ExecutionRefused) as ctx:
            gw.submit(kwargs.get("intent", intent()), prepare_mleg_request(intent(), now=NOW))
        self.assertIn(message, str(ctx.exception).lower())
        self.assertEqual(broker.submits, [])

    def test_refuses_when_configuration_forbids_writes(self) -> None:
        env = dict(PAPER_ENV, ALPACA_TRADING_ENABLED="false")
        self.refuse("does not permit", env=env)

    def test_refuses_a_non_paper_endpoint(self) -> None:
        self.refuse("paper endpoint", endpoint="https://api.alpaca.markets")

    def test_refuses_when_execution_state_blocks_new_risk(self) -> None:
        self.refuse("blocks new risk", state=ExecutionState.NO_NEW_RISK)
        self.refuse("blocks new risk", state=ExecutionState.FREEZE_ALL_WRITES)

    def test_refuses_a_second_concurrent_strategy(self) -> None:
        self.refuse("one open or pending", open_strategies=1)

    def test_refuses_an_expired_intent(self) -> None:
        self.refuse("expired", now=NOW + INTENT_TTL + timedelta(seconds=1))

    def test_refuses_when_the_request_does_not_match_the_intent(self) -> None:
        broker = FakeBroker()
        mismatched = prepare_mleg_request(intent(limit_price=Decimal("9.99")), now=NOW)
        with self.assertRaises(ExecutionRefused) as ctx:
            gateway(broker).submit(intent(), mismatched)
        self.assertIn("does not match", str(ctx.exception))
        self.assertEqual(broker.submits, [])


class EndpointResolutionTests(unittest.TestCase):
    def test_enum_valued_base_url_resolves_to_its_url(self) -> None:
        # alpaca-py stores the base URL as an enum whose str() is the member name.
        # Comparing against the member name would check the wrong string.
        from enum import Enum

        from options_alpha_lab.execution.gateway import AlpacaBroker

        class BaseURL(Enum):
            TRADING_PAPER = "https://paper-api.alpaca.markets"

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = type("C", (), {"_base_url": BaseURL.TRADING_PAPER})()
        self.assertEqual(broker.resolved_endpoint(), "https://paper-api.alpaca.markets")


class RequestMappingTests(unittest.TestCase):
    def test_body_is_the_native_mleg_contract(self) -> None:
        body = prepare_mleg_request(intent(), now=NOW).body
        self.assertEqual(body["order_class"], "mleg")
        self.assertEqual(body["type"], "limit")
        self.assertEqual(body["time_in_force"], "day")
        self.assertEqual(body["qty"], "1")
        self.assertEqual(body["limit_price"], "3.00")
        self.assertEqual(
            [(leg["side"], leg["position_intent"]) for leg in body["legs"]],
            [("buy", "buy_to_open"), ("sell", "sell_to_open")],
        )

    def test_request_hash_is_stable_and_input_sensitive(self) -> None:
        a = prepare_mleg_request(intent(), now=NOW)
        b = prepare_mleg_request(intent(), now=NOW + timedelta(seconds=5))
        self.assertEqual(a.request_hash, b.request_hash)
        c = prepare_mleg_request(intent(strategy_quantity=2), now=NOW)
        self.assertNotEqual(a.request_hash, c.request_hash)

    def test_body_carries_no_credentials(self) -> None:
        serialized = str(prepare_mleg_request(intent(), now=NOW).body).lower()
        for secret in ("authorization", "apca", "secret", "bearer", "key"):
            self.assertNotIn(secret, serialized)

    def test_invalid_intents_are_refused(self) -> None:
        with self.assertRaises(RequestError):
            prepare_mleg_request(intent(limit_price=Decimal("0.00")))
        with self.assertRaises(RequestError):
            prepare_mleg_request(intent(legs=(IntentLeg("A", 1, "buy", "buy_to_open"),)))


class CloseIntentTests(unittest.TestCase):
    def test_close_mirrors_the_open_without_widening_it(self) -> None:
        opening = intent()
        closing = build_close_intent(
            opening, approval_reference="exit:deterministic",
            limit_price=Decimal("3.40"), now=NOW,
        )
        self.assertEqual(closing.strategy_quantity, opening.strategy_quantity)
        self.assertEqual(len(closing.legs), len(opening.legs))
        self.assertEqual(
            [(leg.side, leg.position_intent) for leg in closing.legs],
            [("sell", "sell_to_close"), ("buy", "buy_to_close")],
        )

    def test_close_has_a_different_client_order_id_than_the_open(self) -> None:
        opening = intent()
        closing = build_close_intent(
            opening, approval_reference="exit", limit_price=Decimal("3.40"), now=NOW
        )
        self.assertNotEqual(opening.client_order_id, closing.client_order_id)


class ApprovalRequiredTests(unittest.TestCase):
    def test_an_unapproved_decision_cannot_produce_an_intent(self) -> None:
        from options_alpha_lab.replay import replay_paths

        settings = load_settings(
            dict(PAPER_ENV, BOT_MODE="observe", ALPACA_TRADING_ENABLED="false")
        )
        results = replay_paths([Path("fixtures/h0/spy_refusal.snapshot.json")], settings)
        with self.assertRaises(IntentError):
            build_open_intent(
                results[0].outcome, results[0].recorded.decision_hash,
                approval_reference="none",
            )


class GuardScopeTests(unittest.TestCase):
    def test_only_the_gateway_may_express_a_broker_write(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "guard", Path("scripts/check_no_write_path.py")
        )
        assert spec is not None and spec.loader is not None
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        self.assertEqual(guard.offenders(Path("src")), [])
        # The allowance is one named file, not a directory.
        self.assertEqual(guard.GATEWAY.name, "gateway.py")


if __name__ == "__main__":
    unittest.main()
