import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { Matrix, Panel } from "./Panel";

type WorkerEvents = Schemas["WorkerEventsOut"];

/**
 * What the worker recorded about itself.
 *
 * The payload distinguishes two things a single empty list would blur:
 * `available: true` with no items means the source works and holds nothing,
 * while `available: false` carries the server's reason for not knowing. The
 * second is not an empty feed and must not read as one.
 */
export function WorkerEvents() {
  const resource = useResource<WorkerEvents>(api.workerEvents());
  const ready = resource.state === "ready" || resource.state === "stale";
  const data = ready ? resource.envelope.data : null;
  const unavailable = data !== null && !data.available;

  return (
    <Panel
      testId="worker-events"
      title="What the worker recorded about itself"
      source="worker_events"
      present={data !== null && data.available && data.items.length > 0}
      absence={
        unavailable
          ? `This source cannot answer: ${data?.reason ?? "no reason given"}`
          : "The source holds no worker events. Nothing has run against this database."
      }
    >
      <Matrix label="Worker events">
        <table className="matrix">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Event</th>
              <th scope="col">Kind</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((event, index) => (
              <tr key={`${event.event}-${event.occurred_at ?? ""}-${index}`} data-kind={event.kind}>
                <td className="num">{event.occurred_at ?? "—"}</td>
                <td>{event.event}</td>
                <td className="role">{event.kind}</td>
                <td className="prose">
                  {Object.entries(event.detail)
                    .map(([key, value]) => `${key} ${String(value)}`)
                    .join(" · ") || "—"}
                  {event.withheld.length > 0 ? (
                    <span className="src">withheld: {event.withheld.join(", ")}</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Matrix>
    </Panel>
  );
}
