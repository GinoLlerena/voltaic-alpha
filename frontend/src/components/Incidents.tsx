import { useState } from "react";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { Panel } from "./Panel";

type Incident = Schemas["IncidentOut"];

/**
 * Incidents, with their detail named rather than shown.
 *
 * `detail` is assembled from exception text at several call sites, so it is
 * free text a broker error chose. `withheld` names the fields held back, which
 * is the point: a withheld field must be visibly withheld, not silently
 * absent, or the page cannot be told apart from one that had nothing to hide.
 */
export function Incidents() {
  const [state, setState] = useState<"open" | "all">("open");
  const incidents = useResource<Incident[]>(api.incidents(state));
  const ready = incidents.state === "ready" || incidents.state === "stale";
  const rows = ready ? incidents.envelope.data : [];

  return (
    <Panel
      testId="incidents"
      title="Incidents"
      source="incidents"
      present={rows.length > 0}
      controls={
        <p className="filter">
          {(["open", "all"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={state === option}
              onClick={() => setState(option)}
              data-testid={`incidents-${option}`}
            >
              {option}
            </button>
          ))}
        </p>
      }
      absence={
        state === "open"
          ? "No incident is open. This is the source answering, not a filter hiding one."
          : "No incident has ever been recorded in this source."
      }
    >
      <ul className="chk">
        {rows.map((incident) => (
          <li
            key={`${incident.kind}-${incident.opened_at ?? ""}`}
            data-open={String(incident.open)}
            data-severity={incident.severity}
          >
            <span className="m">{incident.kind}</span>
            <span className="prose">
              {incident.severity}
              {incident.execution_state ? ` · ${incident.execution_state}` : ""}
              {incident.open ? " · open" : ` · resolved ${incident.resolved_at ?? ""}`}
            </span>
            <span className="src">
              opened {incident.opened_at ?? "—"}
              {incident.withheld.length > 0
                ? ` · withheld: ${incident.withheld.join(", ")}`
                : ""}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
