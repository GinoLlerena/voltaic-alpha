import type { Schemas } from "../api/client";
import { Fact, Panel } from "./Panel";

type Memo = Schemas["MemoOut"];
type Market = Schemas["MarketOut"];

/**
 * Why direction, from both sides of the authority line.
 *
 * The classifier decides the direction; the memo is advisory and sizes nothing.
 * Showing them in one panel with the classifier first is the point: a reader
 * should be able to see that the model agreed without being able to conclude
 * that the model decided.
 */
export function Memo({ memo, market }: { memo: Memo | null; market: Market | null }) {
  const qualification = market?.qualification ?? null;
  const thesis = memo?.thesis ?? null;
  const call = memo?.model_call ?? null;

  return (
    <>
      <Panel
        testId="qualification"
        title="Why this direction"
        source="setups"
        present={qualification !== null}
        absence="No setup qualified, so no direction was ever established."
      >
        {qualification ? (
          <dl className="ticket">
            <Fact label="Direction" value={<strong>{qualification.direction}</strong>} />
            <Fact label="Setup" value={qualification.setup_family} />
            <Fact label="Decided by" value={qualification.classifier_name} source="deterministic" />
            <Fact label="Cited" value={qualification.evidence_ids.join(", ") || "—"} />
          </dl>
        ) : null}
      </Panel>

      <Panel
        testId="memo"
        title="What the model contributed"
        source="theses"
        present={memo?.produced === true && thesis !== null}
        absence="No memo exists. The model was never called."
      >
        {thesis ? (
          <>
            <dl className="ticket">
              <Fact label="Memo direction" value={thesis.direction} />
              <Fact label="Confidence" value={thesis.confidence ?? "—"} />
              <Fact label="Written by" value={thesis.synthesizer_name} />
              <Fact
                label="Counter-evidence"
                value={thesis.counter_evidence_ids.join(", ") || "none recorded"}
              />
              {call ? (
                <>
                  <Fact label="Model" value={`${call.provider} · ${call.model}`} />
                  <Fact
                    label="Call"
                    value={`${call.status}${call.latency_ms === null ? "" : ` · ${call.latency_ms}ms`}`}
                    source={`prompt ${call.prompt_version}`}
                  />
                  <Fact
                    label="Tokens"
                    value={
                      call.input_tokens === null && call.output_tokens === null
                        ? "—"
                        : `${call.input_tokens ?? "?"} in · ${call.output_tokens ?? "?"} out`
                    }
                  />
                </>
              ) : (
                <Fact label="Model call" value="none — the memo is deterministic" source="model_calls" />
              )}
            </dl>
            <p className="prose">{thesis.reasoning_summary}</p>
            <p className="fenced">
              Advisory only. A memo disagreeing with the setup is coerced to neutral and recorded as an
              attempt; it can neither size nor authorize.
            </p>
          </>
        ) : null}
      </Panel>
    </>
  );
}
