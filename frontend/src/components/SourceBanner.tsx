import type { Envelope } from "../api/client";

/**
 * Says where the data came from, on every screen.
 *
 * The dashboard's rule, carried over: "live" is never implied when it is not
 * true, and a stale view says so rather than looking current.
 */
export function SourceBanner({
  envelope,
  stale,
  reason,
}: {
  envelope: Envelope<unknown>;
  stale?: boolean;
  reason?: string;
}) {
  const live = envelope.source_mode === "LIVE";
  return (
    <div className="source" data-testid="source-banner" data-mode={envelope.source_mode}>
      <span className={live ? "dot live" : "dot frozen"} aria-hidden="true" />
      <span className="mode">{live ? "LIVE" : "COMMITTED EVIDENCE"}</span>
      <span className="label">{envelope.source_label}</span>
      <time dateTime={envelope.observed_at}>
        observed {new Date(envelope.observed_at).toISOString().replace("T", " ").slice(0, 19)} UTC
      </time>
      {stale ? (
        <strong className="stale" role="status">
          Showing last verified state — refresh failed ({reason})
        </strong>
      ) : null}
    </div>
  );
}
