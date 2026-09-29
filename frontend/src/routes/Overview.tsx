import { Link } from "@tanstack/react-router";
import { DEFAULT_VIEW, type View } from "../api/views";
import { ViewPicker } from "../components/ViewPicker";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { DecisionList } from "../components/DecisionList";
import { ProofTiles } from "../components/ProofTiles";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";
import { StatusStrip } from "../components/StatusStrip";

type Status = Schemas["StatusItemOut"][];
type Listing = Schemas["DecisionListOut"];
type Tiles = Schemas["ProofTileOut"][];
type Review = Schemas["ReviewOverviewOut"];
type Scenes = Schemas["SceneOut"][];

/** The ten-second read: what this is, where it came from, and what it decided. */
export function Overview({
  tourStep,
  view = DEFAULT_VIEW,
}: {
  tourStep: number | null;
  view?: View;
}) {
  const status = useResource<Status>(api.status());
  const tiles = useResource<Tiles>(api.proofTiles());
  const listing = useResource<Listing>(api.groupedDecisions(view));
  const review = useResource<Review>(api.reviewOverview());
  const scenes = useResource<Scenes>(api.tour());

  const scene =
    tourStep !== null && (scenes.state === "ready" || scenes.state === "stale")
      ? (scenes.envelope.data[Math.min(tourStep, scenes.envelope.data.length) - 1] ?? null)
      : null;

  return (
    <>
      {status.state === "failed" ? (
        <p role="alert" className="failed">
          The presentation API is unreachable ({status.reason}). Nothing is shown rather than
          something that might be old.
        </p>
      ) : null}
      {status.state === "ready" || status.state === "stale" ? (
        <>
          <SourceBanner
            envelope={status.envelope}
            stale={status.stale}
            {...(status.state === "stale" ? { reason: status.reason } : {})}
          />
          <StatusStrip items={status.envelope.data} />
        </>
      ) : null}

      {scene ? (
        <section className="tour" data-testid="tour-card">
          <p className="hd">
            GUIDED PATH · STEP {scene.number}
          </p>
          <h3>{scene.title}</h3>
          {scene.decision_id === null ? (
            // RUI-VAL-009's lesson, carried into the client: admit the absence
            // rather than narrate over whichever decision happens to be first.
            <p data-testid="scene-absent">
              <strong>
                This step&rsquo;s decision ({scene.snapshot_id}) is not in this source.
              </strong>{" "}
              The guided path is written against the committed evidence.
            </p>
          ) : (
            <>
              <p>{scene.narration}</p>
              <Link to="/decisions/$digest" params={{ digest: scene.decision_id }}>
                Open this step&rsquo;s decision
              </Link>
            </>
          )}
        </section>
      ) : null}

      {/* PUI-001: each block below says it is loading or unavailable rather
          than vanishing, which would read as "nothing to show". */}
      <Loaded what="proof tiles" resources={{ tiles }}>
        {(d) => <ProofTiles tiles={d.tiles} />}
      </Loaded>

      <Loaded what="review summary" resources={{ review }}>
        {(d) => (
          <p className="caveat" data-testid="review-caveat">
            {d.review.caveat}{" "}
            <span className="note">
              {d.review.resolved} horizons resolved, {d.review.pending} waiting.
            </span>
          </p>
        )}
      </Loaded>

      <section>
        <Loaded what="recorded decisions" resources={{ listing }}>
          {(d) => (
            <>
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
    </>
  );
}
