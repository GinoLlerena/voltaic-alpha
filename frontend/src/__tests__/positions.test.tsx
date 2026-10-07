import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ATTENTION, MARK_STATE } from "../components/positions";
import {
  at,
  currentMark,
  envelope,
  executionRow,
  openPosition,
  POSITION,
  positionDetail,
  positionIn,
  positionsPage,
  QUALIFIED,
  respond,
} from "../test/fixtures";

/** Positions: what exposure exists, in which state, and what needs a look (PUI phase 4). */

afterEach(() => vi.unstubAllGlobals());

const listOf = (items: unknown[], ever?: number) => ({
  "/api/v1/positions?state=": envelope(positionsPage(items, ever)),
});

describe("the positions list (PUI phase 4)", () => {
  it("says so when no position has ever been opened, and lists nothing", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/positions"));
    expect(await screen.findByTestId("position-scope")).toHaveTextContent(
      "No position has ever been opened in this source.",
    );
    expect(screen.queryByTestId("position-list")).toBeNull();
    expect(screen.queryByTestId("positions-empty")).toBeNull();
  });

  it("asks for open and unconfirmed positions by default, and keeps the filter in the URL", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    const first = render(at("/positions"));
    await screen.findByTestId("position-scope");
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain("/api/v1/positions?state=open");
    const nav = screen.getByRole("navigation", { name: "Position states" });
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent("Open or unconfirmed");
    expect([...nav.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      "/positions", "/positions?state=closed", "/positions?state=all",
    ]);
    first.unmount();

    render(at("/positions?state=closed"));
    await screen.findByTestId("position-scope");
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain(
      "/api/v1/positions?state=closed",
    );
  });

  it("treats an unknown state as the default rather than sending it", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/positions?state=flat"));
    await screen.findByTestId("position-scope");
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain("/api/v1/positions?state=open");
  });

  it("shows an open position: state in words, quantity, entry with its unit, risk, mark", async () => {
    vi.stubGlobal("fetch", respond(new Set(), listOf([openPosition])));
    render(at("/positions"));
    const row = within(await screen.findByTestId("position-list")).getByRole("link");
    expect(row).toHaveAttribute("href", `/positions/${POSITION}`);
    expect(row).toHaveTextContent("SPY");
    expect(row).toHaveTextContent("bull call debit spread · bullish");
    expect(row).toHaveTextContent("OPEN Reconciled fills establish this exposure.");
    expect(row).toHaveTextContent("filled 1 of 1");
    expect(row).toHaveTextContent("entry 3.13 per share");
    expect(row).toHaveTextContent("risk 339.00 USD");
    expect(row).toHaveTextContent("current mark");
    expect(row).toHaveAttribute("data-attention", "false");
  });

  it("never shows an estimate for a pending entry", async () => {
    const pending = positionIn({
      state: "PENDING", open: true, filled_quantity: 0, entry_debit: null, realized: null,
      state_meaning: "Entry submitted; no confirmed fill. Exposure is unknown, not zero.",
      mark_state: "never_observed", closed_at: null, close_reason: null,
    });
    vi.stubGlobal("fetch", respond(new Set(), listOf([pending])));
    render(at("/positions"));
    const row = within(await screen.findByTestId("position-list")).getByRole("link");
    expect(row).toHaveTextContent("Exposure is unknown, not zero.");
    expect(row).toHaveTextContent("filled 0 of 1");
    expect(row).toHaveTextContent("entry not yet reconciled");
    expect(row).toHaveTextContent("never observed");
  });

  it("marks a held position that needs a look, and says why in words", async () => {
    const stale = positionIn({
      ...openPosition, position_id: "s".repeat(32), mark_state: "stale",
      attention: ["stale_mark"],
    });
    const incident = positionIn({
      ...openPosition, position_id: "i".repeat(32), state: "INCIDENT", open_incidents: 1,
      attention: ["open_incident"],
      state_meaning: "Local records and the broker disagree. Treat exposure as unknown.",
    });
    const closed = executionRow.position;
    vi.stubGlobal("fetch", respond(new Set(), listOf([stale, incident, closed])));
    render(at("/positions?state=all"));
    const rows = within(await screen.findByTestId("position-list")).getAllByRole("link");
    expect(rows[0]).toHaveAttribute("data-attention", "true");
    expect(rows[0]).toHaveTextContent("stale mark");
    expect(rows[1]).toHaveAttribute("data-attention", "true");
    expect(rows[1]).toHaveTextContent("1 open incident");
    expect(rows[1]).toHaveTextContent("Treat exposure as unknown.");
    // A closed position's old mark is final, not something to chase.
    expect(rows[2]).toHaveAttribute("data-attention", "false");
    expect(rows[2]).toHaveTextContent("final mark");
  });

  it("with positions recorded but none open, says so and points to the closed ones", async () => {
    vi.stubGlobal("fetch", respond(new Set(), listOf([], 3)));
    render(at("/positions"));
    const empty = await screen.findByTestId("positions-empty");
    expect(empty).toHaveTextContent("No position is open or unconfirmed.");
    expect(within(empty).getByRole("link")).toHaveAttribute("href", "/positions?state=closed");
    expect(screen.getByTestId("position-scope")).toHaveTextContent(
      "3 positions recorded in this source in any state",
    );
  });

  it("says a failed request failed, never that there are no positions", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/positions?state="])));
    render(at("/positions"));
    expect(await screen.findByText(/unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/No position/)).toBeNull();
  });

  it("is in the primary navigation", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Positions" })).toHaveAttribute(
      "href",
      "/positions",
    );
  });
});

describe("one position (PUI phase 4)", () => {
  it("leads with the state in words, then cost, risk and results with their units", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/positions/${POSITION}`));
    const summary = await screen.findByTestId("position-summary");
    expect(summary).toHaveTextContent("SPY · bull call debit spread · bullish");
    expect(summary).toHaveTextContent("OPEN — Reconciled fills establish this exposure.");
    expect(summary).toHaveTextContent("filled 1 of 1 requested");
    expect(summary).toHaveTextContent("per share, from reconciled fills");
    expect(summary).toHaveTextContent("339.00 USD");
    expect(summary).toHaveTextContent("+27.00 USD");
    // Open: no result yet, and that is said rather than shown as zero.
    expect(summary).toHaveTextContent("no result");
    expect(summary).toHaveTextContent("only once the entry and the close have both filled");
    expect(within(summary).getByRole("link", { name: /decision that opened/ })).toHaveAttribute(
      "href",
      `/decisions/${QUALIFIED}`,
    );
  });

  it("shows the latest mark as a recorded observation with both of its times", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/positions/${POSITION}`));
    const mark = await screen.findByTestId("position-mark");
    expect(mark).toHaveAttribute("data-mark", "current");
    expect(mark).toHaveTextContent("current mark");
    expect(mark).toHaveTextContent("3.40");
    expect(mark).toHaveTextContent("2026-08-28T15:29:00+00:00");
    expect(mark).toHaveTextContent("2026-08-28T15:28:58+00:00");
    expect(mark).toHaveTextContent("It is never a live price.");
  });

  it("says an unreadable mark is unreadable, with the recorded reason", async () => {
    const unreadable = positionIn({
      ...openPosition, mark_state: "unreadable", unrealized: null,
      latest_mark: {
        ...currentMark, spread_value: null, long_bid: null, short_ask: null,
        data_quality: ["long_leg_no_bid"],
      },
    });
    vi.stubGlobal("fetch", respond(new Set(), {
      [`/api/v1/positions/${POSITION}`]: envelope(positionDetail(unreadable)),
    }));
    render(at(`/positions/${POSITION}`));
    const mark = await screen.findByTestId("position-mark");
    expect(mark).toHaveTextContent("That is recorded, not zero.");
    expect(mark).toHaveTextContent("unreadable");
    expect(mark).toHaveTextContent("long leg no bid");
    expect(screen.getByTestId("position-summary")).toHaveTextContent("not measurable");
  });

  it("lists exit evaluations, including the ones that held", async () => {
    const exits = [{
      trigger: "none", should_close: false, disposition: "held", reason: "no trigger met",
      unrealized: "27.00", suggested_limit: null, value_unmeasurable: false,
      invalidation_unverifiable: false, policy_version: "h0", decided_at: "2026-08-28T15:30:00+00:00",
    }];
    vi.stubGlobal("fetch", respond(new Set(), {
      [`/api/v1/positions/${POSITION}`]: envelope(positionDetail(openPosition, { exits })),
    }));
    render(at(`/positions/${POSITION}`));
    const section = await screen.findByTestId("position-exits");
    expect(section).toHaveTextContent("hold · none");
    expect(section).toHaveTextContent("no trigger met");
    expect(section).toHaveTextContent("unrealized +27.00 USD");
  });

  it("raises an open incident above the figures and withholds its free text", async () => {
    const incidents = [{
      kind: "position_mismatch", severity: "high", execution_state: "NO_NEW_RISK",
      opened_at: "2026-08-28T15:30:00+00:00", resolved_at: null, open: true, withheld: ["detail"],
    }];
    const position = positionIn({ ...openPosition, state: "INCIDENT", open_incidents: 1 });
    vi.stubGlobal("fetch", respond(new Set(), {
      [`/api/v1/positions/${POSITION}`]: envelope(positionDetail(position, { incidents })),
    }));
    render(at(`/positions/${POSITION}`));
    expect(await screen.findByTestId("position-incidents-open")).toHaveTextContent(
      "1 incident is open on this position: position mismatch.",
    );
    expect(screen.getByTestId("position-incidents")).toHaveTextContent("detail withheld");
  });

  it("shows a closed round trip's result from the fills", async () => {
    vi.stubGlobal("fetch", respond(new Set(), {
      [`/api/v1/positions/${POSITION}`]: envelope(positionDetail(executionRow.position)),
    }));
    render(at(`/positions/${POSITION}`));
    const summary = await screen.findByTestId("position-summary");
    expect(summary).toHaveTextContent("-33.00 USD");
    expect(summary).toHaveTextContent("whole structure, from reconciled fills");
    expect(summary).toHaveTextContent("stop loss");
    // No longer held: no open risk and nothing unrealized to report.
    expect(summary).toHaveTextContent("Risk while held");
    expect(summary).not.toHaveTextContent("Open risk");
    expect(summary).not.toHaveTextContent("Unrealized");
    expect(screen.getByTestId("position-mark")).toHaveTextContent("final mark");
  });

  it("tells a missing position from a failed request", async () => {
    vi.stubGlobal("fetch", respond(new Set(), {}, { [`/api/v1/positions/${POSITION}`]: 404 }));
    const missing = render(at(`/positions/${POSITION}`));
    expect(await screen.findByTestId("position-missing")).toHaveTextContent("no position with that id");
    missing.unmount();

    vi.stubGlobal("fetch", respond(new Set(), {}, { [`/api/v1/positions/${POSITION}`]: 500 }));
    render(at(`/positions/${POSITION}`));
    expect(await screen.findByTestId("position-unavailable")).toHaveTextContent(
      "a failed request, not a missing record",
    );
  });
});

describe("mark states", () => {
  it("names every attention reason the contract can serve", () => {
    interface Spec {
      components: {
        schemas: {
          PositionSummaryOut: { properties: { attention: { items: { enum: string[] } } } };
        };
      };
    }
    const spec = JSON.parse(readFileSync("openapi.json", "utf8")) as Spec;
    const served = spec.components.schemas.PositionSummaryOut.properties.attention.items.enum;
    expect(Object.keys(ATTENTION).sort()).toEqual([...served].sort());
  });

  it("names every state the contract can serve", () => {
    interface Spec {
      components: { schemas: { PositionSummaryOut: { properties: { mark_state: { enum: string[] } } } } };
    }
    // jsdom gives import.meta.url an http: scheme; the suite runs from frontend/.
    const spec = JSON.parse(readFileSync("openapi.json", "utf8")) as Spec;
    const served = spec.components.schemas.PositionSummaryOut.properties.mark_state.enum;
    expect(Object.keys(MARK_STATE).sort()).toEqual([...served].sort());
  });
});
