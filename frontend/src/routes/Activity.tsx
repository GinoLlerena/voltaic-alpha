import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { ActivityFeed } from "../components/ActivityFeed";
import { Incidents } from "../components/Incidents";
import { SourceBanner } from "../components/SourceBanner";
import { WorkerEvents } from "../components/WorkerEvents";

type Page = Schemas["ActivityPage"];

/**
 * `RUI-5`, less the half its own rule forbids building yet.
 *
 * The increment's scope is position attention, activity and incidents, and it
 * says position attention may only be built once accepted position
 * observations *and* exit decisions exist. This source holds one position, two
 * broker orders and no exit decision, so the position workspace is not here.
 * Activity and incidents have no such precondition and are.
 */
export function Activity() {
  // Only to give the page its source banner; the feed reads its own pages.
  const page = useResource<Page>(api.activity());

  return (
    <>
      {page.state === "ready" || page.state === "stale" ? (
        <SourceBanner
          envelope={page.envelope}
          stale={page.stale}
          {...(page.state === "stale" ? { reason: page.reason } : {})}
        />
      ) : null}
      <h2>Activity</h2>
      <p className="caveat">
        Every row below is a durable record the server paged. Nothing on this
        screen is assembled, ordered or de-duplicated in the browser.
      </p>
      <ActivityFeed />
      <Incidents />
      <WorkerEvents />
    </>
  );
}
