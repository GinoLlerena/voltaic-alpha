import { Link } from "@tanstack/react-router";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { dataOf, useResource } from "../api/useResource";
import { ProofTiles } from "../components/ProofTiles";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";

type Tiles = Schemas["ProofTileOut"][];
type Review = Schemas["ReviewOverviewOut"];
type Scenes = Schemas["SceneOut"][];

/**
 * Evidence and proof: the corpus-level measurements and the guided tour.
 *
 * PUI Phase 2 moved these off the daily screen. They verify the record; they
 * are not what the owner needs first each morning.
 */
export function Evidence({ tourStep }: { tourStep: number | null }) {
  const tiles = useResource<Tiles>(api.proofTiles());
  const review = useResource<Review>(api.reviewOverview());
  const scenes = useResource<Scenes>(api.tour());

  const sceneList = dataOf(scenes);
  const scene =
    tourStep !== null && sceneList
      ? (sceneList[Math.min(tourStep, sceneList.length) - 1] ?? null)
      : null;

  return (
    <>
      <h2>Evidence and proof</h2>
      <p className="sub">auditable execution firewall</p>
      {tiles.state === "ready" || tiles.state === "stale" ? (
        <SourceBanner envelope={tiles.envelope} />
      ) : null}

      {scene ? (
        <section className="tour" data-testid="tour-card">
          <p className="hd">GUIDED PATH · STEP {scene.number}</p>
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
      ) : (
        <p>
          <Link to="/evidence" search={{ tour: 1 }}>
            Start the guided path
          </Link>
        </p>
      )}

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
    </>
  );
}
