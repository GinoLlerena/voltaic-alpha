import type { Schemas } from "../api/client";
import { Fact, Matrix, Panel } from "./Panel";

type Structure = Schemas["StructureOut"];
type Scalar = string | number | boolean | null;

const LEG_COLUMNS: { key: string; label: string; numeric?: boolean }[] = [
  { key: "contract_symbol", label: "Contract" },
  { key: "option_type", label: "Type" },
  { key: "strike", label: "Strike", numeric: true },
  { key: "expiration", label: "Expiry" },
  { key: "dte", label: "DTE", numeric: true },
  { key: "bid", label: "Bid", numeric: true },
  { key: "ask", label: "Ask", numeric: true },
  { key: "delta", label: "Delta", numeric: true },
  { key: "implied_volatility", label: "IV", numeric: true },
];

const show = (value: Scalar | undefined): string =>
  value === null || value === undefined || value === "" ? "—" : String(value);

/**
 * Why this structure, as the legs themselves.
 *
 * `RUI-4` asks for a leg matrix and a tabular alternative to any chart. This is
 * the table, and there is no chart: a payoff diagram drawn in the browser would
 * be the browser calculating, which authority rule 3 forbids.
 */
export function Structure({ structure }: { structure: Structure | null }) {
  const selected = structure?.selected ?? null;
  const rejected = (structure?.candidates ?? []).filter((candidate) => !candidate.selected);

  return (
    <>
      <Panel
        testId="structure-selected"
        title="Why this structure"
        source="spread_candidates"
        present={selected !== null}
        absence="No structure was selected, so no contracts were ever priced."
      >
        {selected ? (
          <>
            <dl className="ticket">
              <Fact label="Strategy" value={selected.strategy} />
              <Fact label="Quantity" value={selected.quantity} />
              <Fact label="Estimated debit" value={show(selected.estimated_debit)} />
              <Fact
                label="Maximum loss"
                value={show(selected.calculated_max_loss)}
                source="recomputed by the risk governor"
              />
            </dl>
            <Matrix label="Contract legs and their quotes">
            <table className="matrix">
              <thead>
                <tr>
                  {LEG_COLUMNS.map((column) => (
                    <th key={column.key} scope="col">
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {selected.leg_quotes.map((leg, index) => (
                  <tr key={show(leg["contract_symbol"]) + String(index)}>
                    {LEG_COLUMNS.map((column) => (
                      <td key={column.key} className={column.numeric ? "num" : undefined}>
                        {show(leg[column.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            </Matrix>
            <p className="caveat">
              Quotes are those recorded at decision time, on the feed named in the observation. They are
              not a current price.
            </p>
          </>
        ) : null}
      </Panel>

      <Panel
        testId="structure-rejected"
        title="Structures not taken"
        source="spread_candidates"
        present={rejected.length > 0}
        absence="No other candidate was recorded, so nothing was rejected at this stage."
      >
        <ul className="chk">
          {rejected.map((candidate) => (
            <li key={candidate.candidate_id}>
              <span className="m">{candidate.strategy}</span>
              <span className="prose">
                {candidate.rejection_reasons.join("; ") || "no reason recorded"}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
