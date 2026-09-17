import type { Schemas } from "../api/client";
import { Panel } from "./Panel";

type Market = Schemas["MarketOut"];
type Memo = Schemas["MemoOut"];

/**
 * What would prove this decision wrong.
 *
 * The classifier's conditions and the memo's are listed separately and never
 * merged. They have different authority: the classifier's are binding and the
 * model has no schema field to receive them, so a combined list would imply an
 * agreement that the records do not contain.
 */
export function Invalidation({ market, memo }: { market: Market | null; memo: Memo | null }) {
  const setupConditions = market?.qualification?.invalidation_conditions ?? [];
  const memoConditions = memo?.thesis?.invalidation_conditions ?? [];

  return (
    <Panel
      testId="invalidation"
      title="What would invalidate it"
      source="setups.invalidation_conditions · theses.invalidation_conditions"
      present={setupConditions.length > 0 || memoConditions.length > 0}
      absence="No invalidation conditions are recorded, because no setup qualified."
    >
      <dl className="ticket">
        <dt>Set by the classifier</dt>
        <dd>
          {setupConditions.length > 0 ? (
            <ul className="plain">
              {setupConditions.map((condition) => (
                <li key={condition}>{condition}</li>
              ))}
            </ul>
          ) : (
            <span className="t na">none recorded</span>
          )}
          <span className="src">binding · setups</span>
        </dd>
        <dt>Restated in the memo</dt>
        <dd>
          {memoConditions.length > 0 ? (
            <ul className="plain">
              {memoConditions.map((condition) => (
                <li key={condition}>{condition}</li>
              ))}
            </ul>
          ) : (
            <span className="t na">none recorded</span>
          )}
          <span className="src">advisory · theses</span>
        </dd>
      </dl>
    </Panel>
  );
}
