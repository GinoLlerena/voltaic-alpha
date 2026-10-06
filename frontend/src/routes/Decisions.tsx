import { Link } from "@tanstack/react-router";
import { useCallback } from "react";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useCursorPage } from "../api/useCursorPage";
import { useResource } from "../api/useResource";
import { DEFAULT_VIEW, type View } from "../api/views";
import { DecisionList } from "../components/DecisionList";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";
import { marketDay, marketTime } from "../components/time";
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
export function Decisions({
  view = DEFAULT_VIEW,
  day = null,
}: {
  view?: View;
  /** One market day, from a review journal row. It applies to the ungrouped views. */
  day?: string | null;
}) {
  // A day asks for that session's decisions, which only the full history can
  // answer: the grouped view covers a window, not a day.
  const shown: View = day !== null && view === "Notable" ? "Everything" : view;
  return (
    <section>
      <h2>Recorded decisions</h2>
      <ViewPicker current={shown} />
      {shown === "Notable" ? (
        <Grouped />
      ) : (
        <History key={`${shown}-${day ?? ""}`} outcome={OUTCOME[shown]} day={day} />
      )}
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
 * Full history, page by page, in the server's order, through the same
 * `useCursorPage` as the activity feed (`CSA-006`): page one holds still while
 * older pages are shown, and the reader is offered the newest instead.
 */
function History({ outcome, day }: { outcome: Item["outcome"] | null; day: string | null }) {
  const urlFor = useCallback(
    (cursor: string | null) => api.decisions(outcome, cursor, day),
    [outcome, day],
  );
  const { first, items, nextCursor, loading, failed, browsing, more, newest } = useCursorPage<
    Page,
    Item
  >(urlFor);

  return (
    <Loaded what="decision history" resources={{ first }}>
      {(d) => {
        const rows = items ?? d.first.items;
        return (
          <>
            {first.state === "ready" || first.state === "stale" ? (
              <SourceBanner envelope={first.envelope} />
            ) : null}
            <p className="scope" data-testid="decision-scope">
              {rows.length} of {d.first.total} decisions
              {day === null ? "" : ` on ${marketDay(day)} (New York market day)`}, newest first,
              ungrouped.
              {day === null ? null : (
                <>
                  {" "}
                  <Link to="/decisions" search={{ view: "Everything" }}>
                    Show every day
                  </Link>
                </>
              )}
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
                <button type="button" onClick={more} disabled={loading} data-testid="history-more">
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
