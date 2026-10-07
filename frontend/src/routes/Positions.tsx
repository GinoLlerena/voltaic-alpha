import { Link } from "@tanstack/react-router";
import { useCallback } from "react";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useCursorPage } from "../api/useCursorPage";
import {
  ATTENTION,
  DEFAULT_STATE,
  MARK_STATE,
  STATE_FILTERS,
  type StateFilter,
} from "../components/positions";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";
import { plain } from "../components/time";

type Page = Schemas["PositionPage"];
type Position = Schemas["PositionSummaryOut"];

const FILTER_LABEL: Record<StateFilter, string> = {
  open: "Open or unconfirmed",
  closed: "Closed or abandoned",
  all: "All",
};

/**
 * Positions across decisions: what exposure needs monitoring (PUI Phase 4).
 *
 * "Open" is every state in which exposure exists or is unconfirmed - pending,
 * open, closing, incident - because order writes being disabled says nothing
 * about exposure already held. The default view is those, so a position that
 * needs attention is never behind a filter.
 *
 * Every value is the server's. The page multiplies nothing and values nothing:
 * a result that is not recorded is said to be not recorded.
 */
export function Positions({ state = DEFAULT_STATE }: { state?: StateFilter }) {
  return (
    <section>
      <h2>Positions</h2>
      <nav className="views" aria-label="Position states">
        {STATE_FILTERS.map((s) => (
          <Link
            key={s}
            to="/positions"
            search={s === DEFAULT_STATE ? {} : { state: s }}
            activeOptions={{ exact: true, includeSearch: true }}
            aria-current={s === state ? "page" : undefined}
          >
            {FILTER_LABEL[s]}
          </Link>
        ))}
      </nav>
      <PositionList key={state} state={state} />
    </section>
  );
}

function PositionList({ state }: { state: StateFilter }) {
  const urlFor = useCallback((cursor: string | null) => api.positions(state, cursor), [state]);
  const { first, items, nextCursor, loading, failed, browsing, more, newest } = useCursorPage<
    Page,
    Position
  >(urlFor);

  return (
    <Loaded what="positions" resources={{ first }}>
      {(d) => {
        const rows = items ?? d.first.items;
        return (
          <>
            {first.state === "ready" || first.state === "stale" ? (
              <SourceBanner
                envelope={first.envelope}
                stale={first.stale}
                {...(first.state === "stale" ? { reason: first.reason } : {})}
              />
            ) : null}
            <p className="scope" data-testid="position-scope">
              {d.first.ever === 0
                ? "No position has ever been opened in this source."
                : `${rows.length} of ${d.first.total} shown; ${d.first.ever} position${
                    d.first.ever === 1 ? "" : "s"
                  } recorded in this source in any state.`}
            </p>
            {rows.length === 0 ? (
              d.first.ever === 0 ? null : (
                <p className="empty" data-testid="positions-empty">
                  {state === "open"
                    ? "No position is open or unconfirmed. "
                    : state === "closed"
                      ? "No position has been closed or abandoned. "
                      : ""}
                  {state === "open" ? (
                    <Link to="/positions" search={{ state: "closed" }}>
                      See closed and abandoned positions
                    </Link>
                  ) : null}
                </p>
              )
            ) : (
              <ul className="positions" data-testid="position-list">
                {rows.map((p) => (
                  <li key={p.position_id}>
                    <PositionRow position={p} />
                  </li>
                ))}
              </ul>
            )}
            {rows.length === 0 ? null : (
              <p className="gate">
                <span className="src" data-testid="positions-end">
                  {nextCursor === null ? "No more positions." : "More positions are available."}
                </span>
                {nextCursor === null ? null : (
                  <button type="button" onClick={more} disabled={loading} data-testid="positions-more">
                    {loading ? "Loading…" : "Show more"}
                  </button>
                )}
                {browsing ? (
                  <button type="button" onClick={newest} data-testid="positions-newest">
                    Paused while you browse — show the newest
                  </button>
                ) : null}
                {failed === null ? null : (
                  <span className="failed" role="alert">
                    {failed}
                  </span>
                )}
              </p>
            )}
          </>
        );
      }}
    </Loaded>
  );
}

/** One position as a row: what it is, its state in words, and what needs a look. */
export function PositionRow({ position: p }: { position: Position }) {
  const mark = MARK_STATE[p.mark_state];
  // The server decides whether a position needs a look, and why.
  const attention = p.attention.length > 0;
  return (
    <Link
      to="/positions/$positionId"
      params={{ positionId: p.position_id }}
      data-open={String(p.open)}
      data-state={p.state}
      data-attention={String(attention)}
    >
      <span className="name">
        {p.instrument ?? "instrument not recorded"}
        <span className="what">
          {p.strategy.replaceAll("_", " ")} · {p.direction}
        </span>
      </span>
      <span className="state">
        <strong>{p.state}</strong> <span className="meaning">{p.state_meaning}</span>
      </span>
      <span className="figures">
        <span>
          filled {p.filled_quantity} of {p.requested_quantity}
        </span>
        <span>
          entry {p.entry_debit === null ? "not yet reconciled" : `${plain(p.entry_debit)} per share`}
        </span>
        <span>risk {p.open_risk === null ? "not recorded" : `${plain(p.open_risk)} USD`}</span>
        <span data-mark={p.mark_state}>{mark.label}</span>
        {p.open_incidents > 0 ? (
          <span className="incident">
            {p.open_incidents} open incident{p.open_incidents === 1 ? "" : "s"}
          </span>
        ) : null}
        {p.attention.includes("never_marked") ? (
          <span className="incident">{ATTENTION.never_marked}</span>
        ) : null}
      </span>
    </Link>
  );
}
