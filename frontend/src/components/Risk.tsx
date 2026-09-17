import type { Schemas } from "../api/client";
import { Fact, Matrix, Panel } from "./Panel";

type Risk = Schemas["RiskOut"];
type Scalar = string | number | boolean | null;

const show = (value: Scalar | undefined): string =>
  value === null || value === undefined || value === "" ? "—" : String(value);

/**
 * Maximum loss, and the arithmetic that approved it.
 *
 * Every check is shown, passing ones included. A panel that listed only
 * failures would make an approved decision look unexamined, and the recomputed
 * maximum loss beside the claimed one is the whole argument: the governor did
 * not take the structure's word for it.
 */
export function Risk({ risk }: { risk: Risk | null }) {
  const decisions = risk?.decisions ?? [];
  const accounting = risk?.accounting ?? null;

  return (
    <>
      <Panel
        testId="risk-accounting"
        title="What it could lose"
        source="risk_decisions · accounts"
        present={accounting !== null}
        absence="No risk arithmetic was recorded: nothing reached the governor."
      >
        {accounting ? (
          <dl className="ticket">
            <Fact label="Maximum loss" value={<strong>{show(accounting.maximum_loss)}</strong>} />
            <Fact label="Risk budget" value={show(accounting.risk_budget)} />
            <Fact
              label="Budget used"
              value={accounting.budget_used_percent === null ? "—" : `${accounting.budget_used_percent}%`}
              source="derived by the server"
            />
            <Fact label="Account equity" value={show(accounting.account_equity)} />
          </dl>
        ) : null}
      </Panel>

      <Panel
        testId="risk-checks"
        title="Risk checks"
        source="risk_decisions.checks"
        present={decisions.length > 0}
        absence="No governor ran, because no structure was ever proposed."
      >
        {decisions.map((decision) => (
          <div key={decision.governor_name + decision.policy_version}>
            <p className="gate">
              <strong data-approved={String(decision.approved)}>
                {decision.approved ? "Approved" : "Refused"}
              </strong>{" "}
              by {decision.governor_name}
              {decision.reason_codes.length > 0 ? ` — ${decision.reason_codes.join(", ")}` : ""}
              <span className="src">policy {decision.policy_version}</span>
            </p>
            <Matrix label="Risk checks and their values">
            <table className="matrix">
              <thead>
                <tr>
                  <th scope="col">Check</th>
                  <th scope="col">Result</th>
                  <th scope="col">Values</th>
                </tr>
              </thead>
              <tbody>
                {decision.checks.map((check, index) => {
                  const { check: name, passed, ...rest } = check;
                  return (
                    <tr key={show(name) + String(index)} data-passed={String(passed)}>
                      <td>{show(name)}</td>
                      <td className="verdict">{passed === true ? "passed" : "FAILED"}</td>
                      <td className="num">
                        {Object.entries(rest)
                          .map(([key, value]) => `${key} ${show(value)}`)
                          .join(" · ") || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </Matrix>
          </div>
        ))}
      </Panel>
    </>
  );
}
