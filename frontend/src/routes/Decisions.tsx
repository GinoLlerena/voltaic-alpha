import { Link } from "@tanstack/react-router";
import { useState } from "react";
import type { Schemas } from "../api/client";
import { api, get } from "../api/client";
import { dataOf, useResource } from "../api/useResource";
import { DEFAULT_VIEW, type View } from "../api/views";
import { DecisionList } from "../components/DecisionList";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";
import { marketTime } from "../components/time";
import { ViewPicker } from "../components/ViewPicker";

type Listing = Schemas["DecisionListOut"];
type Page = Schemas["DecisionPage"];
type Item = Schemas["DecisionListItem"];

/** The history filter each ungrouped view stands for. */
const OUTCOME: Record<Exclude<View, "Notable">, Item["outcome"] | null> = {
  Positions: "position",
  Refusals: "refusal",
  Everything: null,
};

/**
 * Decision history. The view is in the URL, so a filtered list is a link and
 * back navigation returns to the same filter.
 *
 * `PUI-008`: Notable groups the newest decisions the server considers and says
 * how many that is and since when; on 29 September it grouped 400 of 718 while
 * reading as the whole history. Every other view pages through the full
 * history on the server's cursor.
 */
export function Decisions({ view = DEFAULT_VIEW }: { view?: View }) {
  return (
    <section>
      <h2>Recorded decisions</h2>
      <ViewPicker current={view} />
      {view === "Notable" ? <Grouped /> : <History key={view} outcome={OUTCOME[view]} />}
    </section>
  );
}

function Grouped() {
  const listing = useResource<Listing>(api.groupedDecisions("Notable"));
  return (
    <Loaded what="recorded decisions" resources={{ listing }}>
      {(d) => (
        <>
          {listing.state === "ready" || listing.state === "stale" ? (
            <SourceBanner envelope={listing.envelope} />
          ) : null}
          <p className="scope" data-testid="decision-scope">
            {d.listing.shown} entr{d.listing.shown === 1 ? "y" : "ies"} for the newest{" "}
            {d.listing.window} of {d.listing.total} decisions
            {d.listing.window_since ? `, since ${marketTime(d.listing.window_since)}` : ""}.
            {d.listing.grouped ? " Identical consecutive refusals are grouped; every position is listed." : ""}
            {d.listing.bounded ? (
              <>
                {" "}
                {d.listing.total - d.listing.window} older decisions are outside this window.{" "}
                <Link to="/decisions" search={{ view: "Everything" }}>
                  Browse the full history
                </Link>
              </>
            ) : null}
          </p>
          <DecisionList rows={d.listing.entries} />
        </>
      )}
    </Loaded>
  );
}

/**
 * Full history, page by page, in the server's order.
 *
 * The same rule as the activity feed (`PUI-009`): page one refreshes on its own
 * only while it is all that is shown. Once older pages are appended the list
 * holds still, because a refreshed page one could shift past the cursor they
 * were fetched with and open a silent gap; the reader is offered the newest instead.
 */
function History({ outcome }: { outcome: Item["outcome"] | null }) {
  const [extra, setExtra] = useState<Item[]>([]);
  const browsing = extra.length > 0;
  const first = useResource<Page>(api.decisions(outcome), 15_000, { paused: browsing });
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const page = dataOf(first);
  const nextCursor = cursor === undefined ? (page ? page.next_cursor : null) : cursor;

  function newest(): void {
    setExtra([]);
    setCursor(undefined);
    setFailed(null);
    first.retry();
  }

  async function more(): Promise<void> {
    if (nextCursor === null || loading) return;
    setLoading(true);
    setFailed(null);
    try {
      const older = await get<Page>(api.decisions(outcome, nextCursor));
      setExtra((seen) => [...seen, ...older.data.items]);
      setCursor(older.data.next_cursor);
    } catch (error) {
      setFailed(error instanceof Error ? error.message : "the request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Loaded what="decision history" resources={{ first }}>
      {(d) => {
        const rows = [...d.first.items, ...extra];
        return (
          <>
            {first.state === "ready" || first.state === "stale" ? (
              <SourceBanner envelope={first.envelope} />
            ) : null}
            <p className="scope" data-testid="decision-scope">
              {rows.length} of {d.first.total} decisions, newest first, ungrouped.
            </p>
            <DecisionList
              rows={rows}
              empty={
                outcome === "position"
                  ? "This source holds no position decisions."
                  : outcome === "refusal"
                    ? "This source holds no refusals."
                    : "This source holds no decisions."
              }
            />
            <p className="gate">
              <span className="src" data-testid="history-end">
                {nextCursor === null ? "The history ends here." : "Older decisions are available."}
              </span>
              {nextCursor === null ? null : (
                <button type="button" onClick={() => void more()} disabled={loading} data-testid="history-more">
                  {loading ? "Loading…" : "Show older"}
                </button>
              )}
              {browsing ? (
                <button type="button" onClick={newest} data-testid="history-newest">
                  Paused while you browse older decisions — show the newest
                </button>
              ) : null}
              {failed === null ? null : (
                <span className="failed" role="alert">
                  {failed}
                </span>
              )}
            </p>
          </>
        );
      }}
    </Loaded>
  );
}
