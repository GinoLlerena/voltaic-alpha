import type { Schemas } from "../api/client";
import { AuthoritySpine } from "./AuthoritySpine";

type Summary = Schemas["DecisionSummary"];
type Market = Schemas["MarketOut"];
type Horizon = Schemas["DecisionHorizonOut"];

/**
 * One decision, answered in the order authority runs.
 *
 * Everything shown is the server's: the `why` lines come from
 * `presentation/explain`, the structure reading from `CIIP-VAL-012`, the
 * horizons from `CIIP-008`. The browser orders and labels; it derives nothing.
 */
export function DecisionTicket({
  summary,
  market,
  horizons,
}: {
  summary: Summary;
  market: Market | null;
  horizons: Horizon[];
}) {
  const structure = market?.structure ?? null;
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
        <dt>Decision hash</dt>
        <dd className="hash">{summary.decision_hash}</dd>
        <dt>Policy</dt>
        <dd>{summary.policy_version}</dd>
      </dl>

      {structure ? (
        <section data-testid="structure-reading">
          <h3>Why the setup did not qualify</h3>
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
      ) : null}

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

      <section data-testid="horizons">
        <h3>Review horizons</h3>
        {horizons.length === 0 ? (
          <p className="empty">No horizons were scheduled for this decision.</p>
        ) : (
          <ul className="chk">
            {horizons.map((horizon) => (
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
