import type { Schemas } from "../api/client";
import { dataOf, type Resource } from "../api/useResource";
import { AuthoritySpine } from "./AuthoritySpine";
import { Pending, StaleNote } from "./ResourceState";

type Summary = Schemas["DecisionSummary"];
type Market = Schemas["MarketOut"];
type Horizon = Schemas["DecisionHorizonOut"];

/**
 * One decision, answered in the order authority runs.
 *
 * Everything shown is the server's: the `why` lines come from
 * `presentation/explain`, the structure reading from `CIIP-VAL-012`, the
 * horizons from `CIIP-008`. The browser orders and labels; it derives nothing.
 *
 * `PUI-005`: headings follow the recorded outcome. A position is not explained
 * as a setup that "did not qualify", and a missing reading is not a refusal.
 */

/** The heading for the setup reading, from what the decision recorded. */
export function setupHeading(summary: Summary): string {
  if (summary.action === "OPTIONS_POSITION") return "How the setup qualified";
  if (summary.reason_codes.includes("no_qualified_setup")) return "Why the setup did not qualify";
  return "The setup reading";
}

export function DecisionTicket({
  summary,
  market,
  horizons,
}: {
  summary: Summary;
  market: Resource<Market>;
  horizons: Resource<Horizon[]>;
}) {
  const marketData = dataOf(market);
  const structure = marketData?.structure ?? null;
  const observedAt = marketData?.observation?.source_time ?? null;
  const heading = setupHeading(summary);
  const horizonRows = dataOf(horizons);
  return (
    <article data-testid="decision-ticket">
      <h2>{summary.snapshot_id}</h2>
      <AuthoritySpine
        modelWasCalled={summary.model_was_called}
        reachedTheBroker={summary.reached_the_broker}
      />

      <dl className="ticket">
        <dt>Action</dt>
        <dd>{summary.action}</dd>
        <dt>Direction</dt>
        <dd>{summary.direction}</dd>
        {summary.reason_codes.length > 0 ? (
          <>
            <dt>Reason</dt>
            <dd>{summary.reason_codes.join(", ")}</dd>
          </>
        ) : null}
        <dt>Decided</dt>
        <dd>{summary.decided_at ?? "—"}</dd>
        <dt>Market data as of</dt>
        <dd data-testid="market-as-of">
          {marketData === null
            ? market.state === "failed"
              ? "unavailable — the market request failed"
              : "loading…"
            : (observedAt ?? "not recorded for this decision")}
          <span className="note"> the input's own time, not when this page refreshed</span>
        </dd>
        <dt>Decision hash</dt>
        <dd className="hash">{summary.decision_hash}</dd>
        <dt>Policy</dt>
        <dd>{summary.policy_version}</dd>
      </dl>

      {marketData === null ? (
        <section data-testid="structure-reading" data-present="false" data-state={market.state}>
          <h3>{heading}</h3>
          <Pending what="setup reading" resources={[market]} />
        </section>
      ) : structure ? (
        <section data-testid="structure-reading" data-present="true">
          <h3>{heading}</h3>
          <StaleNote what="setup reading" resources={[market]} />
          <p className="gate">
            Gate: <strong>{structure.gate}</strong>
          </p>
          <dl className="ticket">
            {structure.separation !== null ? (
              <>
                <dt>EMA separation</dt>
                <dd>{structure.separation}</dd>
                <dt>Shortfall</dt>
                <dd>
                  {structure.separation_shortfall}
                  <span className="note">
                    {" "}
                    {Number(structure.separation_shortfall) < 0
                      ? "short of the threshold"
                      : "cleared the threshold"}
                  </span>
                </dd>
              </>
            ) : null}
            {structure.close_side ? (
              <>
                <dt>Close</dt>
                <dd>
                  {structure.last_close} ({structure.close_side} EMA20)
                </dd>
              </>
            ) : null}
            {structure.retest_touched !== null ? (
              <>
                <dt>Retest</dt>
                <dd>{structure.retest_touched ? "touched" : "not touched"}</dd>
              </>
            ) : null}
            <dt>Bars</dt>
            <dd>
              {structure.bars_considered} of {structure.bars_required} required
            </dd>
          </dl>
        </section>
      ) : (
        /* A missing reading is itself worth saying. Rendering nothing put the
           refusal's central question — how nearly did it qualify? — off the page
           with no account of why, which is the omission `RUI-VAL-009` found in
           the dashboard. The client states that the record is absent and names
           where it would come from; it does not guess at a reason. */
        <section data-testid="structure-reading" data-present="false">
          <h3>{heading}</h3>
          <p className="gate">
            <span className="t na">No structure reading was recorded for this decision.</span>
            <span className="src">structure_readings</span>
          </p>
        </section>
      )}

      <section data-testid="why-decision">
        <h3>Why this decision?</h3>
        <ol className="why">
          {summary.why.map((line) => (
            <li key={line.stage} data-present={String(line.present)}>
              <span className="s">{line.stage}</span>
              <span className={line.present ? "t" : "t na"}>{line.text}</span>
              <span className="src">{line.source}</span>
            </li>
          ))}
        </ol>
      </section>

      <section data-testid="horizons" data-state={horizons.state}>
        <h3>Review horizons</h3>
        <StaleNote what="review horizons" resources={[horizons]} />
        {horizonRows === null ? (
          <Pending what="review horizons" resources={[horizons]} />
        ) : horizonRows.length === 0 ? (
          <p className="empty">No horizons were scheduled for this decision.</p>
        ) : (
          <ul className="chk">
            {horizonRows.map((horizon) => (
              <li key={horizon.horizon} data-resolved={String(horizon.resolved)}>
                <span>
                  {horizon.horizon} · {horizon.sessions} completed session
                  {horizon.sessions === 1 ? "" : "s"}
                </span>
                <span className="m">
                  {horizon.resolved
                    ? `${horizon.underlying_at_decision} → ${horizon.underlying_at_horizon} (${horizon.change})`
                    : "WAITING"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
