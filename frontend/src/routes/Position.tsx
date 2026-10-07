import { Link } from "@tanstack/react-router";
import { useCallback } from "react";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useCursorPage } from "../api/useCursorPage";
import { useResource } from "../api/useResource";
import { Fact, Matrix } from "../components/Panel";
import { MARK_STATE } from "../components/positions";
import { Loaded } from "../components/ResourceState";
import { SourceBanner } from "../components/SourceBanner";
import { marketTime, plain, signed } from "../components/time";

type Detail = Schemas["PositionDetailOut"];
type Summary = Schemas["PositionSummaryOut"];
type Marks = Schemas["ObservationPage"];
type Mark = Schemas["MarkOut"];

const when = (iso: string | null, absent: string) =>
  iso === null ? (
    absent
  ) : (
    <>
      {marketTime(iso)} <span className="utc">{iso}</span>
    </>
  );

/**
 * One position: its state, what it cost, what could be lost, and the records
 * behind each (PUI Phase 4).
 *
 * Order follows what a holder asks first: is exposure confirmed, what is the
 * risk, when was it last looked at, and has anything gone wrong. Only the
 * server's 404 says the position does not exist; a failed request does not.
 */
export function Position({ positionId }: { positionId: string }) {
  const detail = useResource<Detail>(api.position(positionId));

  if (detail.state === "failed") {
    return detail.notFound ? (
      <p role="alert" className="failed" data-testid="position-missing">
        This source holds no position with that id. <Link to="/positions">Back to positions</Link>
      </p>
    ) : (
      <p role="alert" className="failed" data-testid="position-unavailable">
        This position could not be loaded ({detail.reason}). That is a failed request, not a
        missing record.{" "}
        <button type="button" onClick={detail.retry}>
          Retry
        </button>{" "}
        <Link to="/positions">Back to positions</Link>
      </p>
    );
  }
  if (detail.state === "loading") {
    return (
      <p role="status" data-testid="decision-loading">
        Loading the position…
      </p>
    );
  }

  const { position: p, exits, incidents, observations_recorded: recorded } = detail.envelope.data;
  const open = incidents.filter((i) => i.open);
  return (
    <>
      <SourceBanner
        envelope={detail.envelope}
        stale={detail.stale}
        {...(detail.state === "stale" ? { reason: detail.reason } : {})}
      />
      <p>
        <Link to="/positions" search={p.open ? {} : { state: "closed" }}>
          ← Positions
        </Link>
      </p>
      <article data-testid="position-summary" data-state={p.state} data-open={String(p.open)}>
        <h2>
          {p.instrument ?? "Instrument not recorded"} · {p.strategy.replaceAll("_", " ")} ·{" "}
          {p.direction}
        </h2>
        <p className="state-line">
          <strong>{p.state}</strong> — {p.state_meaning}
        </p>
        {open.length > 0 ? (
          <p className="stale-note" role="status" data-testid="position-incidents-open">
            {open.length} incident{open.length === 1 ? " is" : "s are"} open on this position:{" "}
            {open.map((i) => i.kind.replaceAll("_", " ")).join(", ")}.
          </p>
        ) : null}
        <dl className="ticket">
          <Fact
            label="Quantity"
            value={`filled ${p.filled_quantity} of ${p.requested_quantity} requested`}
          />
          <Fact
            label="Entry debit"
            value={p.entry_debit === null ? "not yet reconciled" : plain(p.entry_debit)}
            source={
              p.entry_debit === null
                ? "set only by reconciled fills, never the estimate"
                : "per share, from reconciled fills"
            }
          />
          <Fact
            // A position no longer held has no open risk; what was at risk while
            // it was held is still a fact about it.
            label={p.open ? "Open risk" : "Risk while held"}
            value={p.open_risk === null ? "not recorded" : `${plain(p.open_risk)} USD`}
            source="whole structure"
          />
          <Fact label="Legs" value={`${p.long_symbol} / ${p.short_symbol}`} />
          <Fact
            label="Expiry · width"
            value={`${p.expiration?.slice(0, 10) ?? "not recorded"} · ${
              p.width === null ? "—" : plain(p.width)
            }`}
          />
          <Fact
            label="Invalidation"
            value={
              p.invalidation_level === null
                ? "none recorded"
                : `${plain(p.invalidation_level)} (${p.invalidation_direction ?? "direction not recorded"})`
            }
            source={p.invalidation_source ?? undefined}
          />
          <Fact label="Opened" value={when(p.opened_at, "not opened: no confirmed fill")} />
          <Fact
            label="Closed"
            value={when(p.closed_at, p.open ? "still held or unconfirmed" : "not recorded")}
            source={p.close_reason ? p.close_reason.replaceAll("_", " ") : undefined}
          />
          {p.open ? (
            <Fact
              label="Unrealized"
              value={p.unrealized === null ? "not measurable" : `${signed(p.unrealized)} USD`}
              source="as the exit logic recorded it on its own mark"
            />
          ) : null}
          <Fact
            label="Realized"
            value={p.realized === null ? "no result" : `${signed(p.realized)} USD`}
            source={
              p.realized === null
                ? "a result exists only once the entry and the close have both filled"
                : "whole structure, from reconciled fills"
            }
          />
        </dl>
        {p.decision_id ? (
          <p>
            <Link to="/decisions/$digest" params={{ digest: p.decision_id }}>
              Open the decision that opened this position
            </Link>
          </p>
        ) : null}
      </article>

      <LatestMark position={p} />

      <section data-testid="position-exits">
        <h3>Exit evaluations</h3>
        {exits.length === 0 ? (
          <p className="empty">No exit evaluation has been recorded for this position.</p>
        ) : (
          <ul className="chk">
            {exits.map((e, index) => (
              <li key={`${e.decided_at ?? ""}-${String(index)}`} data-close={String(e.should_close)}>
                <span className="m">
                  {e.should_close ? "close" : "hold"} · {e.trigger.replaceAll("_", " ")}
                </span>
                <span className="prose">{e.reason}</span>
                <span className="src">
                  {e.decided_at ? marketTime(e.decided_at) : "time not recorded"}
                  {e.unrealized === null ? "" : ` · unrealized ${signed(e.unrealized)} USD`}
                  {e.value_unmeasurable ? " · value unmeasurable" : ""}
                  {e.invalidation_unverifiable ? " · invalidation unverifiable" : ""}
                  {e.disposition ? ` · ${e.disposition.replaceAll("_", " ")}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section data-testid="position-incidents">
        <h3>Incidents</h3>
        {incidents.length === 0 ? (
          <p className="empty">No incident has been recorded against this position.</p>
        ) : (
          <ul className="chk">
            {incidents.map((i, index) => (
              <li key={`${i.kind}-${String(index)}`} data-open={String(i.open)}>
                <span className="m">
                  {i.open ? "open" : "resolved"} · {i.kind.replaceAll("_", " ")}
                </span>
                <span className="src">
                  {i.severity} · opened {i.opened_at ? marketTime(i.opened_at) : "time not recorded"}
                  {i.withheld.length > 0 ? " · detail withheld" : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Observations positionId={positionId} recorded={recorded} />
    </>
  );
}

function LatestMark({ position: p }: { position: Summary }) {
  const state = MARK_STATE[p.mark_state];
  const mark = p.latest_mark;
  return (
    <section data-testid="position-mark" data-mark={p.mark_state}>
      <h3>Latest mark</h3>
      <p className="state-line">
        <strong>{state.label}</strong> — {state.meaning}
      </p>
      {mark === null ? null : (
        <dl className="ticket">
          <Fact
            label="Spread value"
            value={mark.spread_value === null ? "unreadable" : plain(mark.spread_value)}
            source="per share: what the spread could conservatively be closed for"
          />
          <Fact label="Observed" value={when(mark.observed_at, "not recorded")} />
          <Fact label="Provider time" value={when(mark.source_time, "not recorded")} />
          <Fact
            label="Underlying"
            value={mark.underlying_price === null ? "—" : plain(mark.underlying_price)}
            source={mark.underlying_source.replaceAll("_", " ")}
          />
          <Fact
            label="Days to expiry · sessions held"
            value={`${mark.dte} · ${mark.sessions_elapsed}`}
          />
          {mark.data_quality.length > 0 ? (
            <Fact label="Data quality" value={mark.data_quality.join(", ").replaceAll("_", " ")} />
          ) : null}
        </dl>
      )}
      <p className="caveat">A mark is a recorded observation. It is never a live price.</p>
    </section>
  );
}

function Observations({ positionId, recorded }: { positionId: string; recorded: number }) {
  const urlFor = useCallback(
    (cursor: string | null) => api.positionObservations(positionId, cursor),
    [positionId],
  );
  const { first, items, nextCursor, loading, failed, more } = useCursorPage<Marks, Mark>(urlFor);
  return (
    <section data-testid="position-observations">
      <h3>
        Recorded marks <small>{recorded} recorded</small>
      </h3>
      {recorded === 0 ? (
        <p className="empty">No mark has been recorded for this position.</p>
      ) : (
        <Loaded what="recorded marks" resources={{ first }}>
          {(d) => {
            const rows = items ?? d.first.items;
            return (
              <>
                <Matrix label="Recorded marks, newest first">
                  <table className="matrix wide">
                    <thead>
                      <tr>
                        <th scope="col">Observed</th>
                        <th scope="col">Spread value</th>
                        <th scope="col">Long bid / short ask</th>
                        <th scope="col">Underlying</th>
                        <th scope="col">Data quality</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((m, index) => (
                        <tr key={`${m.observed_at ?? ""}-${String(index)}`}>
                          <td>{m.observed_at ? marketTime(m.observed_at) : "not recorded"}</td>
                          <td className="num">
                            {m.spread_value === null ? (
                              <span className="t na">unreadable</span>
                            ) : (
                              plain(m.spread_value)
                            )}
                          </td>
                          <td className="num">
                            {m.long_bid === null ? "—" : plain(m.long_bid)} /{" "}
                            {m.short_ask === null ? "—" : plain(m.short_ask)}
                          </td>
                          <td className="num">
                            {m.underlying_price === null ? "—" : plain(m.underlying_price)}
                          </td>
                          <td>
                            {m.data_quality.length === 0
                              ? "—"
                              : m.data_quality.join(", ").replaceAll("_", " ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Matrix>
                <p className="gate">
                  <span className="src">
                    {rows.length} of {d.first.total} shown
                    {nextCursor === null ? "" : "; older marks are available"}
                  </span>
                  {nextCursor === null ? null : (
                    <button type="button" onClick={more} disabled={loading} data-testid="marks-more">
                      {loading ? "Loading…" : "Show older"}
                    </button>
                  )}
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
      )}
    </section>
  );
}
