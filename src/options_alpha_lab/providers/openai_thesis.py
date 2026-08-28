"""The bounded model memo.

The model is given evidence and asked to reason about it. It is never given the
answer, and four things are structurally out of its reach:

* **Direction.** The deterministic setup supplies the envelope. The model may
  agree or abstain; a reversal is coerced to abstention and recorded (`CLR-008`).
* **Invalidation.** The model never sees the invalidation conditions and never
  emits them. They are copied from the setup in code, so there is no path by
  which a memo could soften a stop.
* **Sizing and eligibility.** Neither appears in the schema.
* **Execution.** No broker tool is reachable from this module.

Every failure mode - timeout, transport error, refusal, malformed output,
hallucinated evidence - resolves to a neutral thesis, which the workflow
terminates as `NO_TRADE`. Failing closed is the only safe default when the
component that failed is the one that was supposed to be persuasive.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from ..architecture.contracts import (
    DecisionSnapshot,
    Direction,
    SetupCandidate,
    Thesis,
)
from ..hashing import payload_hash

PROMPT_VERSION = "thesis.v1"
OUTPUT_SCHEMA_VERSION = "thesis_memo.v1"
DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 700

DEVELOPER_INSTRUCTIONS = (
    "You are a research analyst writing a short memo about a US equity index ETF "
    "setup that deterministic code has already qualified. You are not a trader and "
    "you have no authority.\n"
    "\n"
    "Rules:\n"
    "1. You may AGREE with the supplied directional envelope, or ABSTAIN by "
    "returning direction 'neutral'. You may not return the opposite direction. "
    "Abstaining is a correct and expected answer when the evidence is weak or "
    "conflicting.\n"
    "2. Every id in evidence_ids and counter_evidence_ids must be one of the "
    "supplied signal ids. Never invent an id, a number, or a fact that is not in "
    "the supplied evidence.\n"
    "3. Identify genuine counter-evidence. A memo that lists only supporting "
    "evidence is a worse memo, not a more confident one.\n"
    "4. confidence is your assessment of the evidence, between 0 and 1. It is not "
    "a probability of profit and it does not size anything.\n"
    "5. Do not give investment advice, price targets, or recommendations."
)

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "counter_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string", "maxLength": 900},
    },
    "required": [
        "direction",
        "confidence",
        "evidence_ids",
        "counter_evidence_ids",
        "reasoning_summary",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ModelCall:
    """Metadata for the `model_calls` table. Carries no prompt text or reasoning."""

    provider: str
    model: str
    prompt_version: str
    output_schema_version: str
    status: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    input_hash: str
    reason_codes: tuple[str, ...] = ()


class ModelTransport:
    """Minimal seam so tests can drive every failure mode without a network."""

    def create(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIResponsesTransport(ModelTransport):
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def create(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        import httpx

        response = httpx.post(
            f"{self._base_url}/responses",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"model returned {response.status_code}: {response.text[:200]}")
        result: dict[str, Any] = response.json()
        return result


def _output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise ValueError("model refused")
                if content.get("type") == "output_text":
                    return str(content.get("text", ""))
    raise ValueError("no structured output in response")


class BoundedThesisSynthesizer:
    """A `ThesisSynthesizer` the model cannot use to change a decision."""

    name = "bounded_model_memo_v1"

    def __init__(
        self,
        transport: ModelTransport,
        *,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self.model = model
        self.timeout = timeout
        self.last_call: ModelCall | None = None

    # -- prompt ------------------------------------------------------------
    def build_input(self, snapshot: DecisionSnapshot, setup: SetupCandidate) -> dict[str, Any]:
        """The exact evidence shown to the model. No answer, no invalidation."""
        return {
            "symbol": snapshot.symbol,
            "as_of": snapshot.as_of.isoformat(),
            "underlying_price": str(snapshot.underlying_price),
            "directional_envelope": setup.direction.value,
            "setup_family": setup.family.value,
            "signals": [
                {
                    "signal_id": signal.signal_id,
                    "family": signal.family.value,
                    "direction": signal.direction.value,
                    "strength": str(signal.strength),
                    "summary": signal.summary,
                }
                for signal in snapshot.signals
            ],
        }

    def _payload(self, model_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.model,
            # Never retain project evidence on the provider side.
            "store": False,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "input": [
                {"role": "developer", "content": DEVELOPER_INSTRUCTIONS},
                {"role": "user", "content": json.dumps(model_input, sort_keys=True)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "thesis_memo",
                    "strict": True,
                    "schema": RESPONSE_SCHEMA,
                }
            },
        }

    # -- synthesis ---------------------------------------------------------
    def synthesize(self, snapshot: DecisionSnapshot, setup: SetupCandidate) -> Thesis:
        model_input = self.build_input(snapshot, setup)
        input_hash = payload_hash(model_input)
        started = time.monotonic()

        try:
            response = self._transport.create(self._payload(model_input), self.timeout)
            raw = _output_text(response)
            generated = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 - every failure resolves the same way
            return self._abstain(
                setup,
                input_hash,
                started,
                status="failed",
                reasons=(f"model_error:{type(exc).__name__}",),
            )

        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        known_ids = {signal.signal_id for signal in snapshot.signals}
        reasons: list[str] = []

        raw_direction = str(generated.get("direction", "neutral"))
        try:
            direction = Direction(raw_direction)
        except ValueError:
            direction = Direction.NEUTRAL
            reasons.append("unknown_direction")

        if direction is not Direction.NEUTRAL and direction is not setup.direction:
            # A reversal is not an error to argue with; it is coerced and recorded.
            reasons.append("model_attempted_direction_reversal")
            direction = Direction.NEUTRAL

        evidence = tuple(dict.fromkeys(str(x) for x in generated.get("evidence_ids", [])))
        counter = tuple(dict.fromkeys(str(x) for x in generated.get("counter_evidence_ids", [])))
        hallucinated = sorted((set(evidence) | set(counter)) - known_ids)
        if hallucinated:
            reasons.append("hallucinated_evidence")
            direction = Direction.NEUTRAL
            evidence = tuple(x for x in evidence if x in known_ids)
            counter = tuple(x for x in counter if x in known_ids)

        try:
            confidence = Decimal(str(generated.get("confidence", 0)))
        except (InvalidOperation, ValueError):
            confidence = Decimal("0")
            reasons.append("unparseable_confidence")
        if not (Decimal("0") <= confidence <= Decimal("1")):
            confidence = Decimal("0")
            reasons.append("confidence_out_of_range")

        summary = str(generated.get("reasoning_summary", "")).strip()
        if not summary:
            summary = "Model returned no summary; treated as abstention."
            direction = Direction.NEUTRAL
            reasons.append("empty_summary")

        if direction is not Direction.NEUTRAL and not evidence:
            reasons.append("no_supported_evidence")
            direction = Direction.NEUTRAL

        self.last_call = ModelCall(
            provider="openai",
            model=self.model,
            prompt_version=PROMPT_VERSION,
            output_schema_version=OUTPUT_SCHEMA_VERSION,
            status="ok" if not reasons else "constrained",
            latency_ms=int((time.monotonic() - started) * 1000),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            input_hash=input_hash,
            reason_codes=tuple(reasons),
        )

        return Thesis(
            direction=direction,
            confidence=confidence if direction is not Direction.NEUTRAL else Decimal("0"),
            evidence_ids=evidence if direction is not Direction.NEUTRAL else (),
            counter_evidence_ids=counter,
            # Copied in code. The model never saw these and cannot alter them.
            invalidation_conditions=setup.invalidation_conditions,
            reasoning_summary=summary[:900],
        )

    def _abstain(
        self,
        setup: SetupCandidate,
        input_hash: str,
        started: float,
        *,
        status: str,
        reasons: tuple[str, ...],
    ) -> Thesis:
        self.last_call = ModelCall(
            provider="openai",
            model=self.model,
            prompt_version=PROMPT_VERSION,
            output_schema_version=OUTPUT_SCHEMA_VERSION,
            status=status,
            latency_ms=int((time.monotonic() - started) * 1000),
            input_tokens=None,
            output_tokens=None,
            input_hash=input_hash,
            reason_codes=reasons,
        )
        return Thesis(
            direction=Direction.NEUTRAL,
            confidence=Decimal("0"),
            evidence_ids=(),
            counter_evidence_ids=(),
            invalidation_conditions=setup.invalidation_conditions,
            reasoning_summary=(
                "Model path failed closed: " + ", ".join(reasons) + ". No memo was produced."
            ),
        )
