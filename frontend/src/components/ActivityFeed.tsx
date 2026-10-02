import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useCursorPage } from "../api/useCursorPage";
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
 *
 * `PUI-009`: page one refreshes on its own only while it is all that is shown.
 * Once older pages are appended, a refresh of page one could shift it past the
 * cursor they were fetched with and open a silent gap, so the view holds still
 * and offers to start again from the newest instead. The paging itself is
 * `useCursorPage`, shared with the decision history (`CSA-006`).
 */
export function ActivityFeed() {
  const list = useCursorPage<Page, Event>(api.activity);
  const { first, nextCursor, loading, failed, browsing, more, newest } = list;
  const items = list.items ?? [];
  const ready = list.items !== null;

  return (
    <Panel
      testId="activity"
      title="What the system did"
      source="audit_events"
      present={ready && items.length > 0}
      resource={first}
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
          <button type="button" onClick={more} disabled={loading} data-testid="activity-more">
            {loading ? "Loading…" : "Show more"}
          </button>
        )}
        {browsing ? (
          <button type="button" onClick={newest} data-testid="activity-newest">
            Paused while you browse older events — show the newest
          </button>
        ) : null}
        {failed === null ? null : (
          <span className="failed" role="alert">
            {failed}
          </span>
        )}
      </p>
    </Panel>
  );
}
