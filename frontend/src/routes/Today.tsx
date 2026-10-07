import { Link } from "@tanstack/react-router";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { dataOf, useResource, type Resource } from "../api/useResource";
import { Matrix } from "../components/Panel";
import { ATTENTION } from "../components/positions";
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
type PositionPage = Schemas["PositionPage"];

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
  const held = useResource<PositionPage>(api.positions("open"));
  const listing = useResource<Listing>(api.groupedDecisions("Notable"));
  const activity = useResource<Page>(api.activity());

  return (
    <>
      <StatusHeader status={status} />
      <Attention incidents={incidents} faults={faults} held={held} />
      <LatestDecision listing={listing} />
      <RecentChanges activity={activity} />
      <nav className="shortcuts" aria-label="More">
        <Link to="/decisions">All decisions</Link>
        <Link to="/positions">Positions</Link>
        <Link to="/activity">Full activity</Link>
        <Link to="/evidence">Evidence and proof</Link>
      </nav>
    </>
  );
}

/**
 * Open incidents, the worker's recorded faults, and held positions that need a
 * look, straight from the server.
 *
 * No severity is computed here and no threshold is invented: the list is what
 * the three sources returned. Which positions need a look, and why, is the
 * server's rule (PUI Phase 4, owner decision D4: an open incident, a stale or
 * unreadable mark, or exposure never marked); this only shows its answer. If a
 * source could not answer, the section says so and does not report a quiet
 * system - an unreadable monitor is itself attention.
 */
function Attention({
  incidents,
  faults,
  held,
}: {
  incidents: Resource<Incident[]>;
  faults: Resource<WorkerEvents>;
  held: Resource<PositionPage>;
}) {
  const heldData = dataOf(held);
  const flagged = heldData ? heldData.items.filter((p) => p.attention.length > 0) : [];
  // More open positions than one page holds: the rest were not checked here.
  const heldUnchecked = heldData !== null && heldData.next_cursor !== null;
  const open = dataOf(incidents);
  const faultData = dataOf(faults);
  const faultSourceDown = faultData !== null && !faultData.available;
  const faultItems = faultData?.available ? faultData.items.slice(0, 3) : [];
  const settled = open !== null && faultData !== null && heldData !== null;
  const quiet =
    settled &&
    open.length === 0 &&
    !faultSourceDown &&
    faultItems.length === 0 &&
    flagged.length === 0 &&
    !heldUnchecked;
  const checked = [incidents, faults, held].flatMap((r) =>
    r.state === "ready" ? [r.fetchedAt] : [],
  );

  return (
    <section className="attention" data-testid="attention" data-quiet={String(quiet)}>
      <h2>Needs attention</h2>
      {open === null ? <Pending what="incidents" resources={[incidents]} /> : null}
      {faultData === null ? <Pending what="worker faults" resources={[faults]} /> : null}
      {heldData === null ? <Pending what="held positions" resources={[held]} /> : null}
      <StaleNote what="attention sources" resources={[incidents, faults, held]} />
      {quiet ? (
        <p className="quiet" data-testid="attention-quiet">
          Nothing needs attention: no incident is open, the worker has recorded no fault, and
          {heldData && heldData.items.length > 0
            ? ` none of the ${heldData.items.length} held position${
                heldData.items.length === 1 ? "" : "s"
              } needs a look.`
            : " no position is held."}
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
          {flagged.map((p) => (
            <li key={p.position_id} data-kind="position">
              <span className="m">held position · {p.state}</span>
              <span className="prose">
                <Link to="/positions/$positionId" params={{ positionId: p.position_id }}>
                  {p.instrument ?? "instrument not recorded"} {p.strategy.replaceAll("_", " ")}
                </Link>
                : {p.attention.map((reason) => ATTENTION[reason]).join("; ")}
              </span>
            </li>
          ))}
          {heldUnchecked ? (
            <li data-kind="monitor">
              <span className="m">not all checked</span>
              <span className="prose">
                More positions are held than this list reads. <Link to="/positions">Open Positions</Link>
              </span>
            </li>
          ) : null}
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
