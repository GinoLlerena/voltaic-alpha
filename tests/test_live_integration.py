from __future__ import annotations

import json
import os
import ssl
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from options_alpha_lab.models import Decision, ExperimentCase, Thesis, case_from_dict
from options_alpha_lab.orchestrator import run_experiment


PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE = PROJECT_ROOT / "fixtures" / "nvda_earnings_bearish.json"
LIVE_ENABLED = os.environ.get("RUN_LIVE_API_TESTS", "").lower() in {
    "1",
    "true",
    "yes",
}


def tls_context() -> ssl.SSLContext:
    configured_bundle = os.environ.get("SSL_CERT_FILE")
    if configured_bundle and Path(configured_bundle).is_file():
        return ssl.create_default_context(cafile=configured_bundle)
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def load_generated_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        if isinstance(value, bool):
            values[key] = str(value).lower()
        else:
            values[key] = str(value)
    return values


def request_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers=headers,
        method="GET" if payload is None else "POST",
    )
    try:
        with urlopen(request, timeout=timeout, context=tls_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        endpoint = urlsplit(url)
        raise AssertionError(
            f"{endpoint.netloc}{endpoint.path} returned HTTP {error.code}."
        ) from None
    except URLError as error:
        endpoint = urlsplit(url)
        raise AssertionError(
            f"Could not reach {endpoint.netloc}{endpoint.path}: {error.reason}"
        ) from None


def response_output_text(response: dict[str, Any]) -> str:
    if response.get("status") != "completed":
        raise AssertionError(
            f"OpenAI response did not complete: {response.get('status', 'unknown')}"
        )
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise AssertionError("OpenAI refused the thesis contract request.")
            if content.get("type") == "output_text":
                return str(content["text"])
    raise AssertionError("OpenAI response did not contain structured output text.")


class OpenAIThesisAgent:
    name = "openai_thesis_agent"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        api_context: dict[str, Any],
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.api_context = api_context

    def analyze(self, case: ExperimentCase) -> Thesis:
        schema = {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["bullish", "bearish"],
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "invalidation_conditions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "api_context_acknowledged": {"type": "boolean"},
            },
            "required": [
                "direction",
                "confidence",
                "evidence",
                "invalidation_conditions",
                "api_context_acknowledged",
            ],
            "additionalProperties": False,
        }
        supplied_contract = {
            "direction": case.expected_direction.value,
            "confidence": str(case.confidence),
            "evidence": list(case.evidence),
            "invalidation_conditions": list(case.invalidation_conditions),
            "api_context": self.api_context,
        }
        response = request_json(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.model,
                "store": False,
                "reasoning": {"effort": "none"},
                "max_output_tokens": 600,
                "input": [
                    {
                        "role": "developer",
                        "content": (
                            "Act only as a schema-preserving thesis adapter for an "
                            "integration test. Copy direction, confidence, evidence, "
                            "and invalidation conditions exactly. The API context only "
                            "confirms read-only connectivity and must not change the "
                            "thesis. Set api_context_acknowledged to true. Do not add "
                            "facts or make an investment recommendation."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(supplied_contract),
                    },
                ],
                "text": {
                    "verbosity": "low",
                    "format": {
                        "type": "json_schema",
                        "name": "options_thesis_contract",
                        "strict": True,
                        "schema": schema,
                    },
                },
            },
        )
        generated = json.loads(response_output_text(response))

        if generated["direction"] != case.expected_direction.value:
            raise AssertionError("LLM changed the supplied thesis direction.")
        if Decimal(str(generated["confidence"])) != case.confidence:
            raise AssertionError("LLM changed the supplied thesis confidence.")
        if generated["evidence"] != list(case.evidence):
            raise AssertionError("LLM changed the supplied evidence contract.")
        if generated["invalidation_conditions"] != list(
            case.invalidation_conditions
        ):
            raise AssertionError("LLM changed the supplied invalidation contract.")
        if generated["api_context_acknowledged"] is not True:
            raise AssertionError("LLM did not acknowledge the API context.")

        return Thesis(
            symbol=case.symbol,
            event_type=case.event_type,
            direction=case.expected_direction,
            confidence=Decimal(str(generated["confidence"])),
            evidence=tuple(generated["evidence"]),
            invalidation_conditions=tuple(generated["invalidation_conditions"]),
        )


@unittest.skipUnless(
    LIVE_ENABLED,
    "Set RUN_LIVE_API_TESTS=1 to allow billable OpenAI and read-only Alpaca calls.",
)
class LiveAgentIntegrationTests(unittest.TestCase):
    def test_llm_thesis_flows_through_read_only_api_context_and_risk_gate(
        self,
    ) -> None:
        credentials = load_generated_env(PROJECT_ROOT / ".env")
        required = ("OPENAI_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")
        missing = [key for key in required if not credentials.get(key)]
        self.assertFalse(missing, f"Missing required credentials: {', '.join(missing)}")
        self.assertEqual(credentials.get("ALPACA_PAPER_TRADE"), "true")

        alpaca_headers = {
            "APCA-API-KEY-ID": credentials["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": credentials["ALPACA_SECRET_KEY"],
        }
        account = request_json(
            "https://paper-api.alpaca.markets/v2/account",
            headers=alpaca_headers,
        )
        stock_snapshot = request_json(
            "https://data.alpaca.markets/v2/stocks/NVDA/snapshot?feed=iex",
            headers=alpaca_headers,
        )
        option_chain = request_json(
            "https://data.alpaca.markets/v1beta1/options/snapshots/NVDA"
            "?feed=indicative&limit=10",
            headers=alpaca_headers,
        )

        self.assertEqual(account.get("status"), "ACTIVE")
        self.assertTrue(stock_snapshot)
        option_snapshots = option_chain.get("snapshots", {})
        self.assertIsInstance(option_snapshots, dict)
        self.assertGreater(len(option_snapshots), 0)

        api_context = {
            "paper_account_status": account["status"],
            "underlying": "NVDA",
            "stock_snapshot_received": True,
            "option_snapshots_received": len(option_snapshots),
            "option_feed": "indicative",
        }
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        case = case_from_dict(raw)
        thesis_agent = OpenAIThesisAgent(
            api_key=credentials["OPENAI_API_KEY"],
            model=os.environ.get("OPENAI_MODEL", "gpt-5.6-terra"),
            api_context=api_context,
        )

        result = run_experiment(case, thesis_agent=thesis_agent)

        self.assertEqual(result.decision, Decision.TRADE_CANDIDATE)
        self.assertEqual(result.proposal.quantity, 1)
        self.assertEqual(result.trace[0].sender, "openai_thesis_agent")
        self.assertEqual(result.trace[0].payload["evidence"], raw["evidence"])


if __name__ == "__main__":
    unittest.main()
