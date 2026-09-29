import type { Schemas } from "../api/client";
import type { Resource } from "../api/useResource";
import { SourceBanner } from "./SourceBanner";
import { StatusStrip } from "./StatusStrip";

type Status = Schemas["StatusItemOut"][];

/**
 * The compact persistent strip: mode, order writes, worker, source identity and
 * when the API last answered. Unknown stays unknown, in the server's words.
 *
 * If the status request itself fails, nothing is shown in its place except the
 * failure: a strip of last-resort defaults would be the invented healthy state
 * the redesign exists to remove.
 */
export function StatusHeader({ status }: { status: Resource<Status> }) {
  if (status.state === "failed") {
    return (
      <p role="alert" className="failed">
        The presentation API is unreachable ({status.reason}). Nothing is shown rather than
        something that might be old.
      </p>
    );
  }
  if (status.state === "loading") {
    return (
      <p className="gate" role="status">
        <span className="t na">Loading the system status…</span>
      </p>
    );
  }
  return (
    <>
      <SourceBanner
        envelope={status.envelope}
        stale={status.stale}
        {...(status.state === "stale" ? { reason: status.reason } : {})}
      />
      <StatusStrip items={status.envelope.data} />
    </>
  );
}
