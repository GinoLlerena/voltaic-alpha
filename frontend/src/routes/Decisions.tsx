import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { DEFAULT_VIEW, type View } from "../api/views";
import { DecisionList } from "../components/DecisionList";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";
import { ViewPicker } from "../components/ViewPicker";

type Listing = Schemas["DecisionListOut"];

/**
 * Decision history. The view is in the URL, so a filtered list is a link and
 * back navigation returns to the same filter.
 */
export function Decisions({ view = DEFAULT_VIEW }: { view?: View }) {
  const listing = useResource<Listing>(api.groupedDecisions(view));
  return (
    <section>
      <Loaded what="recorded decisions" resources={{ listing }}>
        {(d) => (
          <>
            {listing.state === "ready" || listing.state === "stale" ? (
              <SourceBanner envelope={listing.envelope} />
            ) : null}
            <h2>
              Recorded decisions{" "}
              <small>
                {d.listing.shown} of {d.listing.total}
                {d.listing.grouped ? " · identical consecutive outcomes are grouped" : ""}
              </small>
            </h2>
            <ViewPicker current={view} />
            <DecisionList entries={d.listing.entries} />
          </>
        )}
      </Loaded>
    </section>
  );
}
