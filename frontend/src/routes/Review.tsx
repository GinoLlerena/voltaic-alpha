import { Link } from "@tanstack/react-router";
import { useCallback } from "react";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useCursorPage } from "../api/useCursorPage";
import { useResource } from "../api/useResource";
import { reasonText } from "../components/DecisionList";
import { Matrix } from "../components/Panel";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";
import { duration, marketDay, plain, signed } from "../components/time";

type Overview = Schemas["ReviewOverviewOut"];
type Executions = Schemas["ExecutionPage"];
type Execution = Schemas["ExecutionOutcomeOut"];
type Journal = Schemas["ReviewSessionPage"];
type Session = Schemas["ReviewSessionOut"];
type Verdict = Schemas["VerdictCountOut"];

export const HORIZONS = ["T+1", "T+3"] as const;
export type Horizon = (typeof HORIZONS)[number];
export const DEFAULT_HORIZON: Horizon = "T+1";

export function asHorizon(raw: unknown): Horizon | undefined {
  return (HORIZONS as readonly unknown[]).includes(raw) ? (raw as Horizon) : undefined;
}

/**
 * Review: what can be learned from recorded outcomes (PUI Phase 4).
 *
 * Two sections that are never mixed. Execution outcomes are positions that
 * were closed; research horizons are what the underlying did after a decision,
 * traded or not, and say nothing about trading. The caveat comes first because
 * it says which of the two this source can speak about at all.
 *
 * Counts only (owner decision D3): there is no rate, average or score on this
 * screen, and nothing here is computed in the browser.
 */
export function Review({ horizon = DEFAULT_HORIZON }: { horizon?: Horizon }) {
  const overview = useResource<Overview>(api.reviewOverview());
  return (
    <section>
      {overview.state === "ready" || overview.state === "stale" ? (
        <SourceBanner
          envelope={overview.envelope}
          stale={overview.stale}
          {...(overview.state === "stale" ? { reason: overview.reason } : {})}
        />
      ) : null}
      <h2>Review</h2>
      <Loaded what="review summary" resources={{ overview }}>
        {(d) => (
          <p className="caveat" data-testid="review-caveat">
            {d.overview.caveat}{" "}
            <span className="note">
              {d.overview.decisions_reviewed} of {d.overview.decisions} decisions reviewed;{" "}
              {d.overview.resolved} horizons resolved, {d.overview.pending} waiting.
            </span>
          </p>
        )}
      </Loaded>
      <ExecutionOutcomes />
      <ResearchJournal key={horizon} horizon={horizon} />
    </section>
  );
}

function ExecutionOutcomes() {
  const closed = useResource<Executions>(api.reviewExecutions("closed"));
  const abandoned = useResource<Executions>(api.reviewExecutions("abandoned"));
  return (
    <section data-testid="review-executions" aria-labelledby="executions-heading">
      <h3 id="executions-heading">Execution outcomes</h3>
      <p className="note">
        Positions that were closed. The result is computed by the server from the
        broker&apos;s reconciled fills.
      </p>
      <Loaded what="execution outcomes" resources={{ closed }}>
        {(d) =>
          d.closed.items.length === 0 ? (
            <p className="empty" data-testid="executions-empty">
              No position has been closed in this source, so there is no execution outcome to
              review.
            </p>
          ) : (
            <Matrix label="Closed positions">
              <table className="matrix wide">
                <thead>
                  <tr>
                    <th scope="col">Position</th>
                    <th scope="col">Entry → close</th>
                    <th scope="col">Result</th>
                    <th scope="col">Held</th>
                    <th scope="col">Closed because</th>
                  </tr>
                </thead>
                <tbody>
                  {d.closed.items.map((row) => (
                    <ExecutionRow key={row.position.position_id} row={row} />
                  ))}
                </tbody>
              </table>
            </Matrix>
          )
        }
      </Loaded>
      <Loaded what="abandoned entries" resources={{ abandoned }}>
        {(d) =>
          d.abandoned.items.length === 0 ? null : (
            <div data-testid="executions-abandoned">
              <p className="note">
                {d.abandoned.abandoned} entr{d.abandoned.abandoned === 1 ? "y" : "ies"} ended
                without a fill. There was never exposure, so there is no result: these are not
                zero results.
              </p>
              <ul className="chk">
                {d.abandoned.items.map((row) => (
                  <li key={row.position.position_id}>
                    <span>
                      <PositionName row={row} /> · requested {row.position.requested_quantity},
                      filled {row.position.filled_quantity}
                    </span>
                    <span className="m">no exposure</span>
                  </li>
                ))}
              </ul>
            </div>
          )
        }
      </Loaded>
    </section>
  );
}

function PositionName({ row }: { row: Execution }) {
  const p = row.position;
  const label = `${p.instrument ?? "instrument not recorded"} · ${p.strategy.replaceAll("_", " ")}`;
  return p.decision_id ? (
    <Link to="/decisions/$digest" params={{ digest: p.decision_id }}>
      {label}
    </Link>
  ) : (
    <>{label}</>
  );
}

function ExecutionRow({ row }: { row: Execution }) {
  const p = row.position;
  return (
    <tr data-testid="execution-row">
      <td>
        <PositionName row={row} />
        <span className="src">
          {p.direction} · filled {p.filled_quantity} of {p.requested_quantity}
        </span>
      </td>
      <td className="num">
        {p.entry_debit === null ? "not reconciled" : plain(p.entry_debit)} →{" "}
        {row.close_price === null ? "not recorded" : plain(row.close_price)}
        <span className="src">per share</span>
      </td>
      <td className="num">
        {p.realized === null ? "not available" : `${signed(p.realized)} USD`}
        <span className="src">whole structure, from fills</span>
      </td>
      <td className="num">
        {row.held_seconds === null ? "—" : duration(row.held_seconds)}
        {row.sessions_held === null ? null : (
          <span className="src">
            {row.sessions_held} completed session{row.sessions_held === 1 ? "" : "s"}
          </span>
        )}
      </td>
      <td>
        {p.close_reason ? p.close_reason.replaceAll("_", " ") : "not recorded"}
        {row.exit_trigger ? (
          <span className="src">exit trigger: {row.exit_trigger.replaceAll("_", " ")}</span>
        ) : null}
      </td>
    </tr>
  );
}

function verdictText(v: Verdict): string {
  const what =
    v.outcome === "position"
      ? `Position · ${v.direction}`
      : `No trade: ${reasonText(v.reason_codes)}`;
  return `${v.count} × ${what}`;
}

/** What the horizon recorded for one session, or why it recorded nothing. */
function HorizonCell({ session }: { session: Session }) {
  const h = session.horizon;
  if (h === null) return <span className="t na">no decision was recorded</span>;
  if (h.resolved === 0) {
    const waiting = h.pending + h.unresolvable + h.unscheduled;
    return (
      <span className="t na">
        {h.unresolvable > 0
          ? `unresolvable (${h.unresolvable})`
          : h.pending > 0
            ? `waiting (${h.pending})`
            : `not scheduled (${waiting})`}
      </span>
    );
  }
  const move =
    h.smallest_move === null || h.largest_move === null
      ? null
      : h.smallest_move === h.largest_move
        ? signed(h.smallest_move)
        : `${signed(h.smallest_move)} to ${signed(h.largest_move)}`;
  return (
    <>
      {h.at_horizon.map(plain).join(", ")}
      {move === null ? null : ` (${move})`}
      <span className="src">
        {h.resolved} resolved
        {h.pending > 0 ? `, ${h.pending} waiting` : ""}
        {h.unresolvable > 0 ? `, ${h.unresolvable} unresolvable` : ""}
      </span>
    </>
  );
}

function AgreementCell({ session }: { session: Session }) {
  const h = session.horizon;
  if (h === null || h.resolved === 0) return <span className="t na">—</span>;
  if (h.agreed + h.disagreed === 0) {
    return <span className="t na">no direction was stated</span>;
  }
  return (
    <>
      {h.agreed} agreed · {h.disagreed} did not
      {h.unanswerable > 0 ? <span className="src">{h.unanswerable} stated no direction</span> : null}
    </>
  );
}

function ResearchJournal({ horizon }: { horizon: Horizon }) {
  const urlFor = useCallback(
    (before: string | null) => api.reviewSessions(horizon, before),
    [horizon],
  );
  const { first, items, nextCursor, loading, failed, browsing, more, newest } = useCursorPage<
    Journal,
    Session
  >(urlFor);

  return (
    <section data-testid="review-journal" aria-labelledby="journal-heading">
      <h3 id="journal-heading">Research horizons, by market session</h3>
      <p className="note">
        What the underlying did after each session&apos;s decisions. This is research, not a
        trading result. One row per session: the decisions of a day read the same completed
        close, so they are one evaluation recorded many times.
      </p>
      <nav className="views" aria-label="Review horizon">
        {HORIZONS.map((h) => (
          <Link
            key={h}
            to="/review"
            search={h === DEFAULT_HORIZON ? {} : { horizon: h }}
            activeOptions={{ exact: true, includeSearch: true }}
            aria-current={h === horizon ? "page" : undefined}
          >
            {h}
          </Link>
        ))}
      </nav>
      <Loaded what="research journal" resources={{ first }}>
        {(d) => {
          const rows = items ?? d.first.items;
          // How many sessions the horizon spans, as the server states it.
          const after = rows.find((r) => r.horizon !== null)?.horizon?.sessions;
          if (d.first.total === 0) {
            return <p className="empty">This source holds no decisions, so there is no journal.</p>;
          }
          return (
            <>
              <p className="scope" data-testid="journal-scope">
                {rows.length} of {d.first.total} market sessions since the first recorded
                decision, newest first.
                {after === undefined
                  ? ""
                  : ` Horizon ${horizon}: ${after} completed session${after === 1 ? "" : "s"} later.`}
              </p>
              <Matrix label="Research horizons by market session">
                <table className="matrix wide">
                  <thead>
                    <tr>
                      <th scope="col">Session</th>
                      <th scope="col">Decisions</th>
                      <th scope="col">Close read</th>
                      <th scope="col">Underlying at {horizon}</th>
                      <th scope="col">Stated direction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => (
                      <tr key={s.day} data-testid="journal-row" data-decisions={s.decisions}>
                        <td>{marketDay(s.day)}</td>
                        <td>
                          {s.decisions === 0 ? (
                            <span className="t na">none recorded</span>
                          ) : (
                            <>
                              <Link to="/decisions" search={{ view: "Everything", day: s.day }}>
                                {s.decisions} decision{s.decisions === 1 ? "" : "s"}
                              </Link>
                              {s.verdicts.map((v) => (
                                <span className="src" key={verdictText(v)}>
                                  {verdictText(v)}
                                </span>
                              ))}
                            </>
                          )}
                        </td>
                        <td className="num">
                          {s.closes_read.length === 0 ? "—" : s.closes_read.map(plain).join(", ")}
                        </td>
                        <td className="num">
                          <HorizonCell session={s} />
                        </td>
                        <td>
                          <AgreementCell session={s} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Matrix>
              <p className="gate">
                <span className="src" data-testid="journal-end">
                  {nextCursor === null
                    ? "The journal ends here, at the first recorded decision."
                    : "Earlier sessions are available."}
                </span>
                {nextCursor === null ? null : (
                  <button type="button" onClick={more} disabled={loading} data-testid="journal-more">
                    {loading ? "Loading…" : "Show earlier"}
                  </button>
                )}
                {browsing ? (
                  <button type="button" onClick={newest} data-testid="journal-newest">
                    Paused while you browse earlier sessions — show the newest
                  </button>
                ) : null}
                {failed === null ? null : (
                  <span className="failed" role="alert">
                    {failed}
                  </span>
                )}
              </p>
            </>
          );
        }}
      </Loaded>
    </section>
  );
}
