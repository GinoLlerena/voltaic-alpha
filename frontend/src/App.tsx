import { useState } from "react";
import { api, type Schemas } from "./api/client";
import { useResource } from "./api/useResource";
import { DecisionList } from "./components/DecisionList";
import { SourceBanner } from "./components/SourceBanner";
import { StatusStrip } from "./components/StatusStrip";

type Status = Schemas["StatusItemOut"][];
type Listing = Schemas["DecisionListOut"];
type Summary = Schemas["DecisionSummary"];

/**
 * `RUI-2`'s shell: source, status, the decision list, and one decision's
 * identity. Deliberately not the whole dashboard -- the remaining workspaces are
 * `RUI-3` onward, and a half-built tab that looks finished is worse than an
 * absent one.
 */
export default function App() {
  const [selected, setSelected] = useState<string | null>(null);
  const status = useResource<Status>(api.status());
  const listing = useResource<Listing>(api.groupedDecisions("Notable"));
  // A hook cannot be called conditionally, so with nothing selected this asks
  // for the status again -- already cached by the browser, and never a decision
  // the reader did not choose.
  const summary = useResource<Summary>(selected ? api.summary(selected) : api.status());

  return (
    <main>
      <header>
        <h1>Options Alpha</h1>
        <p className="sub">auditable execution firewall</p>
      </header>

      {status.state === "loading" ? <p>Loading…</p> : null}
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

      {listing.state === "ready" || listing.state === "stale" ? (
        <section>
          <h2>
            Recorded decisions{" "}
            <small>
              {listing.envelope.data.shown} of {listing.envelope.data.total}
              {listing.envelope.data.grouped ? " · identical consecutive outcomes are grouped" : ""}
            </small>
          </h2>
          <DecisionList
            entries={listing.envelope.data.entries}
            selected={selected}
            onSelect={setSelected}
          />
        </section>
      ) : null}

      {selected && (summary.state === "ready" || summary.state === "stale") ? (
        <section data-testid="selected-decision">
          <h2>{summary.envelope.data.snapshot_id}</h2>
          <dl>
            <dt>Action</dt>
            <dd>{summary.envelope.data.action}</dd>
            <dt>Direction</dt>
            <dd>{summary.envelope.data.direction}</dd>
            <dt>Decision hash</dt>
            <dd className="hash">{summary.envelope.data.decision_hash}</dd>
            <dt>Reached the broker</dt>
            <dd>{summary.envelope.data.reached_the_broker ? "yes" : "no"}</dd>
            <dt>Model was called</dt>
            <dd>{summary.envelope.data.model_was_called ? "yes" : "no"}</dd>
          </dl>
        </section>
      ) : null}
    </main>
  );
}
