import { Link } from "@tanstack/react-router";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { DecisionList } from "../components/DecisionList";
import { ProofTiles } from "../components/ProofTiles";
import { SourceBanner } from "../components/SourceBanner";
import { StatusStrip } from "../components/StatusStrip";

type Status = Schemas["StatusItemOut"][];
type Listing = Schemas["DecisionListOut"];
type Tiles = Schemas["ProofTileOut"][];
type Review = Schemas["ReviewOverviewOut"];
type Scenes = Schemas["SceneOut"][];

/** The ten-second read: what this is, where it came from, and what it decided. */
export function Overview({ tourStep }: { tourStep: number | null }) {
  const status = useResource<Status>(api.status());
  const tiles = useResource<Tiles>(api.proofTiles());
  const listing = useResource<Listing>(api.groupedDecisions("Notable"));
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

      {tiles.state === "ready" || tiles.state === "stale" ? (
        <ProofTiles tiles={tiles.envelope.data} />
      ) : null}

      {review.state === "ready" || review.state === "stale" ? (
        <p className="caveat" data-testid="review-caveat">
          {review.envelope.data.caveat}{" "}
          <span className="note">
            {review.envelope.data.resolved} horizons resolved, {review.envelope.data.pending}{" "}
            waiting.
          </span>
        </p>
      ) : null}

      {listing.state === "ready" || listing.state === "stale" ? (
        <section>
          <h2>
            Recorded decisions{" "}
            <small>
              {listing.envelope.data.shown} of {listing.envelope.data.total}
              {listing.envelope.data.grouped
                ? " · identical consecutive outcomes are grouped"
                : ""}
            </small>
          </h2>
          <DecisionList entries={listing.envelope.data.entries} />
        </section>
      ) : null}
    </>
  );
}
