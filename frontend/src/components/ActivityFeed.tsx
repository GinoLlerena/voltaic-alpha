import { useState } from "react";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { get } from "../api/client";
import { useResource } from "../api/useResource";
import { Matrix, Panel } from "./Panel";

type Page = Schemas["ActivityPage"];
type Event = Schemas["ActivityEventOut"];

/**
 * The audit feed, page by page, in the server's order.
 *
 * `RUI-5`'s exit says no activity may be browser-created, and paging is where
 * that is usually lost: a client that sorts, merges or de-duplicates is
 * deciding what happened. This appends the server's pages in the order given
 * and passes `next_cursor` back untouched. When the cursor runs out, the feed
 * is over — the browser never infers that from a short page.
 */
export function ActivityFeed() {
  const first = useResource<Page>(api.activity());
  const [extra, setExtra] = useState<Event[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const ready = first.state === "ready" || first.state === "stale";
  const items = ready ? [...first.envelope.data.items, ...extra] : [];
  // `undefined` means "not paged yet", so the server's own first cursor stands.
  const nextCursor = cursor === undefined ? (ready ? first.envelope.data.next_cursor : null) : cursor;

  async function more(): Promise<void> {
    if (nextCursor === null || loading) return;
    setLoading(true);
    setFailed(null);
    try {
      const page = await get<Page>(api.activity(nextCursor));
      setExtra((seen) => [...seen, ...page.data.items]);
      setCursor(page.data.next_cursor);
    } catch (error) {
      setFailed(error instanceof Error ? error.message : "the request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Panel
      testId="activity"
      title="What the system did"
      source="audit_events"
      present={ready && items.length > 0}
      absence="No activity is recorded in this source."
    >
      <Matrix label="Audit events">
        <table className="matrix">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Decision</th>
              <th scope="col">Stage</th>
              <th scope="col">Outcome</th>
              <th scope="col">By</th>
            </tr>
          </thead>
          <tbody>
            {items.map((event) => (
              <tr
                key={`${event.correlation_id}-${event.sequence}-${event.occurred_at ?? ""}`}
                data-refused={String(event.refused)}
              >
                <td className="num">{event.occurred_at ?? "—"}</td>
                <td>{event.correlation_id}</td>
                <td className="role">{event.stage}</td>
                <td className="verdict">
                  {event.outcome}
                  {event.reason_codes.length > 0 ? (
                    <span className="src">{event.reason_codes.join(", ")}</span>
                  ) : null}
                </td>
                <td>{event.component}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Matrix>
      <p className="gate">
        <span className="src" data-testid="activity-count">
          {items.length} event(s) shown
          {nextCursor === null ? ", and the feed ends here" : ", more available"}
        </span>
        {nextCursor === null ? null : (
          <button type="button" onClick={() => void more()} disabled={loading} data-testid="activity-more">
            {loading ? "Loading…" : "Show more"}
          </button>
        )}
        {failed === null ? null : (
          <span className="failed" role="alert">
            {failed}
          </span>
        )}
      </p>
    </Panel>
  );
}
