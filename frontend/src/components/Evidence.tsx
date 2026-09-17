import type { Schemas } from "../api/client";
import { Fact, Matrix, Panel } from "./Panel";

type Market = Schemas["MarketOut"];

/**
 * Why now: what was observed, and which signals were cited.
 *
 * `role` is the server's, not a filter applied here. Counter-evidence and
 * signals that were observed and unused are shown alongside the cited ones,
 * because a page that displays only the supporting signals is an argument
 * rather than a record.
 */
export function Evidence({ market }: { market: Market | null }) {
  const observation = market?.observation ?? null;
  const signals = market?.signals ?? [];

  return (
    <>
      <Panel
        testId="observation"
        title="What was observed"
        source="market_observations"
        present={observation !== null}
        absence="No market observation is recorded for this decision."
      >
        {observation ? (
          <dl className="ticket">
            <Fact label="Symbol" value={observation.symbol} />
            <Fact
              label="Underlying"
              value={observation.underlying_price ?? "—"}
              source="last completed daily close"
            />
            <Fact label="Observed at" value={observation.source_time ?? "—"} />
            <Fact
              label="Feed"
              value={`${observation.provider} · ${observation.feed}`}
              source={market?.observation_kind}
            />
            <Fact label="Payload hash" value={<span className="hash">{observation.payload_hash}</span>} />
          </dl>
        ) : null}
      </Panel>

      <Panel
        testId="signals"
        title="Signals"
        source="signals"
        present={signals.length > 0}
        absence="No signals are recorded for this decision."
      >
        <Matrix label="Signals considered">
        <table className="matrix">
          <thead>
            <tr>
              <th scope="col">Role</th>
              <th scope="col">Signal</th>
              <th scope="col">Direction</th>
              <th scope="col">Strength</th>
              <th scope="col">What it says</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((signal) => (
              <tr key={signal.signal_id} data-role={signal.role}>
                <td className="role">{signal.role}</td>
                <td>
                  {signal.family}
                  <span className="src">{signal.source}</span>
                </td>
                <td>{signal.direction}</td>
                <td className="num">{signal.strength ?? "—"}</td>
                <td className="prose">{signal.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </Matrix>
      </Panel>
    </>
  );
}
