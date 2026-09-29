import { Link } from "@tanstack/react-router";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { dataOf, useResource, type Resource } from "../api/useResource";
import { Matrix } from "../components/Panel";
import { Loaded, Pending, StaleNote } from "../components/ResourceState";
import { StatusHeader } from "../components/StatusHeader";
import { checkedAt } from "../components/time";

type Status = Schemas["StatusItemOut"][];
type Incident = Schemas["IncidentOut"];
type WorkerEvents = Schemas["WorkerEventsOut"];
type Listing = Schemas["DecisionListOut"];
type Summary = Schemas["DecisionSummary"];
type Market = Schemas["MarketOut"];
type Page = Schemas["ActivityPage"];

/**
 * Today: is it operating correctly, what changed, and do I need to look?
 *
 * PUI Phase 2. The order is the order of the owner's questions: the strip
 * (mode, writes, worker, source), then anything needing attention, then the
 * latest decision, then recent changes. Demonstration material - proof tiles,
 * the guided tour - lives under Evidence, not here.
 */
export function Today() {
  const status = useResource<Status>(api.status());
  const incidents = useResource<Incident[]>(api.incidents("open"));
  const faults = useResource<WorkerEvents>(api.workerFaults());
  const listing = useResource<Listing>(api.groupedDecisions("Notable"));
  const activity = useResource<Page>(api.activity());

  return (
    <>
      <StatusHeader status={status} />
      <Attention incidents={incidents} faults={faults} />
      <LatestDecision listing={listing} />
      <RecentChanges activity={activity} />
      <nav className="shortcuts" aria-label="More">
        <Link to="/decisions">All decisions</Link>
        <Link to="/activity">Full activity</Link>
        <Link to="/evidence">Evidence and proof</Link>
      </nav>
    </>
  );
}

/**
 * Open incidents and the worker's recorded faults, straight from the server.
 *
 * No severity is computed here and no threshold is invented: the list is what
 * the two sources returned. If either could not answer, the section says so and
 * does not report a quiet system - an unreadable monitor is itself attention.
 */
function Attention({
  incidents,
  faults,
}: {
  incidents: Resource<Incident[]>;
  faults: Resource<WorkerEvents>;
}) {
  const open = dataOf(incidents);
  const faultData = dataOf(faults);
  const faultSourceDown = faultData !== null && !faultData.available;
  const faultItems = faultData?.available ? faultData.items.slice(0, 3) : [];
  const settled = open !== null && faultData !== null;
  const quiet = settled && open.length === 0 && !faultSourceDown && faultItems.length === 0;
  const checked = [incidents, faults].flatMap((r) => (r.state === "ready" ? [r.fetchedAt] : []));

  return (
    <section className="attention" data-testid="attention" data-quiet={String(quiet)}>
      <h2>Needs attention</h2>
      {open === null ? <Pending what="incidents" resources={[incidents]} /> : null}
      {faultData === null ? <Pending what="worker faults" resources={[faults]} /> : null}
      <StaleNote what="attention sources" resources={[incidents, faults]} />
      {quiet ? (
        <p className="quiet" data-testid="attention-quiet">
          Nothing needs attention: no incident is open and the worker has recorded no fault.
          {checked.length > 0 ? ` Checked ${checkedAt(checked.sort()[0] ?? "")}.` : ""}
        </p>
      ) : null}
      {settled && !quiet ? (
        <ul className="chk">
          {open.map((incident) => (
            <li key={`${incident.kind}-${incident.opened_at ?? ""}`} data-kind="incident">
              <span className="m">open incident · {incident.severity}</span>
              <span className="prose">
                {incident.kind}
                {incident.execution_state ? ` · ${incident.execution_state}` : ""} · opened{" "}
                {incident.opened_at ?? "at an unrecorded time"}
              </span>
            </li>
          ))}
          {faultSourceDown ? (
            <li data-kind="monitor">
              <span className="m">monitor unavailable</span>
              <span className="prose">
                The worker's fault record cannot answer: {faultData?.reason ?? "no reason given"}
              </span>
            </li>
          ) : null}
          {faultItems.map((fault, index) => (
            <li key={`${fault.event}-${fault.occurred_at ?? ""}-${index}`} data-kind="fault">
              <span className="m">recorded worker fault</span>
              <span className="prose">
                {fault.event} · {fault.occurred_at ?? "at an unrecorded time"}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {settled && !quiet ? (
        <p>
          <Link to="/activity">Open Activity for the full record</Link>
        </p>
      ) : null}
    </section>
  );
}

/** The newest entry in the server's Notable view, with its own record's times. */
function LatestDecision({ listing }: { listing: Resource<Listing> }) {
  return (
    <section data-testid="latest-decision">
      <h2>Latest decision</h2>
      <Loaded what="latest decision" resources={{ listing }}>
        {(d) => {
          const entry = d.listing.entries[0];
          if (!entry) {
            return <p className="empty">This source holds no decisions yet.</p>;
          }
          return <LatestDetail entry={entry} />;
        }}
      </Loaded>
    </section>
  );
}

function LatestDetail({ entry }: { entry: Listing["entries"][number] }) {
  const summary = useResource<Summary>(api.summary(entry.decision_id));
  const market = useResource<Market>(api.market(entry.decision_id));
  return (
    <Loaded what="latest decision record" resources={{ summary, market }}>
      {(d) => (
        <>
          <dl className="ticket" data-testid="latest-ticket">
            <dt>Instrument</dt>
            <dd>{d.market.observation?.symbol ?? "not recorded"}</dd>
            <dt>Recorded action</dt>
            <dd>
              {d.summary.action} · {d.summary.direction}
            </dd>
            <dt>Reason</dt>
            <dd>{d.summary.reason_codes.join(", ") || "none recorded"}</dd>
            <dt>Decided</dt>
            <dd>{d.summary.decided_at ?? "not recorded"}</dd>
            <dt>Market data as of</dt>
            <dd>{d.market.observation?.source_time ?? "not recorded for this decision"}</dd>
          </dl>
          <p className="note">
            {entry.count > 1
              ? `The newest of ${entry.count} identical consecutive outcomes, as the Notable view groups them. `
              : "The newest entry in the Notable view. "}
            <Link to="/decisions/$digest" params={{ digest: entry.decision_id }}>
              Open the full record
            </Link>
          </p>
        </>
      )}
    </Loaded>
  );
}

/** The five newest audit events, in the server's order. */
function RecentChanges({ activity }: { activity: Resource<Page> }) {
  return (
    <section data-testid="recent-changes">
      <h2>Recent changes</h2>
      <Loaded what="recent activity" resources={{ activity }}>
        {(d) =>
          d.activity.items.length === 0 ? (
            <p className="empty">No activity is recorded in this source.</p>
          ) : (
            <Matrix label="Recent audit events">
              <table className="matrix">
                <thead>
                  <tr>
                    <th scope="col">When</th>
                    <th scope="col">Decision</th>
                    <th scope="col">Stage</th>
                    <th scope="col">Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {d.activity.items.slice(0, 5).map((event) => (
                    <tr key={`${event.correlation_id}-${event.sequence}-${event.occurred_at ?? ""}`}>
                      <td className="num">{event.occurred_at ?? "—"}</td>
                      <td>{event.correlation_id}</td>
                      <td className="role">{event.stage}</td>
                      <td className="verdict">{event.outcome}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Matrix>
          )
        }
      </Loaded>
    </section>
  );
}
