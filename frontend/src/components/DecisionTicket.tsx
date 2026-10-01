import type { Schemas } from "../api/client";
import { dataOf, type Resource } from "../api/useResource";
import { reasonText } from "./DecisionList";
import { Pending, StaleNote } from "./ResourceState";
import { marketTime } from "./time";

type Summary = Schemas["DecisionSummary"];
type Market = Schemas["MarketOut"];
type Horizon = Schemas["DecisionHorizonOut"];

/**
 * One decision: its summary first, its supporting records in named parts.
 *
 * Everything shown is the server's: the `why` lines come from
 * `presentation/explain`, the structure reading from `CIIP-VAL-012`, the
 * horizons from `CIIP-008`. The browser orders and labels; it derives nothing.
 *
 * `PUI-005`: headings follow the recorded outcome. A position is not explained
 * as a setup that "did not qualify", and a missing reading is not a refusal.
 *
 * `PUI-007`: the summary answers what, why and when in a few lines. Hashes,
 * policy and the stage-by-stage account moved to the Evidence section rather
 * than preceding the answer.
 */

/** The heading for the setup reading, from what the decision recorded. */
export function setupHeading(summary: Summary): string {
  if (summary.action === "OPTIONS_POSITION") return "How the setup qualified";
  if (summary.reason_codes.includes("no_qualified_setup")) return "Why the setup did not qualify";
  return "The setup reading";
}

/** A timestamp in New York time with its precise UTC value beside it. */
function Stamp({ iso }: { iso: string }) {
  return (
    <>
      {marketTime(iso)} <span className="utc">{iso}</span>
    </>
  );
}

export function DecisionTicket({ summary, market }: { summary: Summary; market: Resource<Market> }) {
  const marketData = dataOf(market);
  const observedAt = marketData?.observation?.source_time ?? null;
  const instrument = summary.observation?.symbol ?? marketData?.observation?.symbol ?? null;
  const position = summary.action === "OPTIONS_POSITION";
  return (
    <article data-testid="decision-ticket" data-outcome={position ? "position" : "refusal"}>
      <h2>
        {instrument ?? "Instrument not recorded"} ·{" "}
        {position ? `Position, ${summary.direction}` : "No trade"}
      </h2>
      <p className="snapshot">{summary.snapshot_id}</p>
      <dl className="ticket">
        <dt>Outcome</dt>
        <dd>
          {position
            ? "Opened a Paper position"
            : `No trade: ${reasonText(summary.reason_codes)}`}
          {position ? null : (
            <span className="note"> a valid outcome, not a system error</span>
          )}
        </dd>
        <dt>Decided</dt>
        <dd>{summary.decided_at ? <Stamp iso={summary.decided_at} /> : "not recorded"}</dd>
        <dt>Market data as of</dt>
        <dd data-testid="market-as-of">
          {marketData === null ? (
            market.state === "failed" ? (
              "unavailable — the market request failed"
            ) : (
              "loading…"
            )
          ) : observedAt ? (
            <Stamp iso={observedAt} />
          ) : (
            "not recorded for this decision"
          )}
          <span className="note"> the input&apos;s own time, not when this page refreshed</span>
        </dd>
      </dl>
    </article>
  );
}

/** How near the setup came to qualifying, or how it did. */
export function SetupReading({ summary, market }: { summary: Summary; market: Resource<Market> }) {
  const marketData = dataOf(market);
  const structure = marketData?.structure ?? null;
  const heading = setupHeading(summary);
  return (
    <>
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
    </>
  );
}

/** The account of each authority stage, in the order they ran. */
export function WhyDecision({ summary }: { summary: Summary }) {
  return (
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
  );
}

/** Research horizons: later underlying moves, not the position's P&L. */
export function Horizons({ horizons }: { horizons: Resource<Horizon[]> }) {
  const horizonRows = dataOf(horizons);
  return (
    <section data-testid="horizons" data-state={horizons.state}>
      <h3>Review horizons</h3>
      <p className="note">
        How the underlying moved after the decision. Research, not the position&apos;s profit or loss.
      </p>
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
  );
}

/** The record's identity, for checking it rather than reading it. */
export function Identifiers({ summary }: { summary: Summary }) {
  return (
    <section data-testid="identifiers">
      <h3>Identifiers</h3>
      <dl className="ticket">
        <dt>Decision hash</dt>
        <dd className="hash">{summary.decision_hash}</dd>
        <dt>Input hash</dt>
        <dd className="hash">{summary.input_hash}</dd>
        <dt>Policy</dt>
        <dd>{summary.policy_version}</dd>
        <dt>Snapshot</dt>
        <dd>{summary.snapshot_id}</dd>
      </dl>
    </section>
  );
}
