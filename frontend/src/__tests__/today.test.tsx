import { createMemoryHistory } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../router";
import {
  DIGEST,
  POSITION,
  at,
  envelope,
  openPosition,
  positionIn,
  positionsPage,
  respond,
} from "../test/fixtures";

/** Today: status, attention and the latest decision. */

afterEach(() => vi.unstubAllGlobals());

describe("the overview", () => {
  it("names its source rather than implying it", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const banner = await screen.findByTestId("source-banner");
    expect(banner).toHaveAttribute("data-mode", "LIVE");
  });

  it("keeps an unknown unknown, with the reason the server gave", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const strip = await screen.findByTestId("status-strip");
    const unknown = strip.querySelector('[data-known="false"]');
    expect(unknown).toHaveTextContent("no lease row");
  });

  it("shows an unavailable proof tile as unavailable", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/evidence"));
    const tilesEl = await screen.findByTestId("proof-tiles");
    expect(tilesEl.querySelector('[data-available="false"]')).not.toBeNull();
  });

  it("shows the server's caveat about what the outcomes do not measure", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/evidence"));
    expect(await screen.findByTestId("review-caveat")).toHaveTextContent("are refusals");
  });

  it("reports an unreachable API instead of an empty shell", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/system/status"])));
    render(at("/"));
    expect(await screen.findByRole("alert")).toHaveTextContent("unreachable");
    expect(screen.queryByTestId("status-strip")).toBeNull();
  });
});

describe("Today (PUI phase 2)", () => {
  const FAULTS = "/api/v1/worker/events?faults_only=true";

  it("puts status and attention first, then the latest decision, and no demo metrics", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const attention = await screen.findByTestId("attention");
    const latest = screen.getByTestId("latest-decision");
    const strip = await screen.findByTestId("status-strip");
    // DOM order is reading order: strip, attention, latest decision.
    expect(strip.compareDocumentPosition(attention) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(attention.compareDocumentPosition(latest) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByTestId("proof-tiles")).toBeNull();
    expect(screen.queryByTestId("tour-card")).toBeNull();
  });

  it("states a verified quiet, dated, only when every source answered", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const quiet = await screen.findByTestId("attention-quiet");
    expect(quiet).toHaveTextContent(
      "no incident is open, the worker has recorded no fault, and no position is held.",
    );
    expect(quiet).toHaveTextContent(/Checked \d{4}-\d\d-\d\d/);
  });

  it("stays quiet about a held position that needs nothing, and counts it", async () => {
    vi.stubGlobal("fetch", respond(new Set(), {
      "/api/v1/positions?state=": envelope(positionsPage([openPosition])),
    }));
    render(at("/"));
    expect(await screen.findByTestId("attention-quiet")).toHaveTextContent(
      "none of the 1 held position needs a look.",
    );
  });

  it("lists a held position that needs a look, with the server's reasons and a link", async () => {
    // PUI Phase 4, owner decision D4. The reasons are the server's rule, not the page's.
    const stale = positionIn({
      ...openPosition, mark_state: "stale", open_incidents: 1,
      attention: ["open_incident", "stale_mark"],
    });
    vi.stubGlobal("fetch", respond(new Set(), {
      "/api/v1/positions?state=": envelope(positionsPage([stale, openPosition])),
    }));
    render(at("/"));
    const attention = await screen.findByTestId("attention");
    await waitFor(() => expect(attention).toHaveAttribute("data-quiet", "false"));
    const rows = attention.querySelectorAll('[data-kind="position"]');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("held position · OPEN");
    expect(rows[0]).toHaveTextContent("an incident is open on it; its mark is stale");
    expect(within(rows[0] as HTMLElement).getByRole("link")).toHaveAttribute(
      "href",
      `/positions/${POSITION}`,
    );
    expect(screen.queryByTestId("attention-quiet")).toBeNull();
  });

  it("never reports a quiet system when the positions source failed", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/positions?state="])));
    render(at("/"));
    const attention = await screen.findByTestId("attention");
    await waitFor(() => expect(attention).toHaveTextContent("held positions unavailable"));
    expect(screen.queryByTestId("attention-quiet")).toBeNull();
  });

  it("says so when more positions are held than it read", async () => {
    vi.stubGlobal("fetch", respond(new Set(), {
      "/api/v1/positions?state=": envelope({
        ...positionsPage([openPosition]), next_cursor: "opaque-more",
      }),
    }));
    render(at("/"));
    const attention = await screen.findByTestId("attention");
    await waitFor(() => expect(attention).toHaveTextContent("More positions are held"));
    expect(screen.queryByTestId("attention-quiet")).toBeNull();
  });

  it("lists open incidents and recorded worker faults as attention", async () => {
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        "/api/v1/incidents?state=open": envelope([
          { kind: "broker_unreachable", severity: "critical", execution_state: null,
            opened_at: "2026-09-29T14:00:00+00:00", resolved_at: null, open: true, withheld: [] },
        ]),
        [FAULTS]: envelope({
          available: true, reason: null,
          items: [{ event: "tick_failed", kind: "fault", occurred_at: "2026-09-29T14:01:00+00:00",
            detail: {}, withheld: [] }],
        }),
      }),
    );
    render(at("/"));
    const attention = await screen.findByTestId("attention");
    await waitFor(() => expect(attention).toHaveAttribute("data-quiet", "false"));
    expect(attention).toHaveTextContent("broker_unreachable");
    expect(attention).toHaveTextContent("tick_failed");
    expect(screen.queryByTestId("attention-quiet")).toBeNull();
  });

  it("treats a fault record that cannot answer as attention, not quiet", async () => {
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        [FAULTS]: envelope({ available: false, reason: "the worker_events table is absent", items: [] }),
      }),
    );
    render(at("/"));
    const attention = await screen.findByTestId("attention");
    await waitFor(() => expect(attention).toHaveTextContent("monitor unavailable"));
    expect(attention).toHaveTextContent("the worker_events table is absent");
    expect(screen.queryByTestId("attention-quiet")).toBeNull();
  });

  it("never reports a quiet system when an attention source failed", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/incidents?state=open"])));
    render(at("/"));
    const attention = await screen.findByTestId("attention");
    await waitFor(() => expect(attention).toHaveTextContent("incidents unavailable"));
    expect(screen.queryByTestId("attention-quiet")).toBeNull();
  });

  it("shows the latest decision with its own times and a link to the record", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const ticket = await screen.findByTestId("latest-ticket");
    expect(ticket).toHaveTextContent("NO_TRADE");
    expect(ticket).toHaveTextContent("no_qualified_setup");
    expect(ticket).toHaveTextContent("2026-09-17T14:00:00+00:00");
    const latest = screen.getByTestId("latest-decision");
    expect(latest).toHaveTextContent("newest of 72 identical consecutive outcomes");
    expect(within(latest).getByRole("link", { name: "Open the full record" })).toHaveAttribute(
      "href",
      `/decisions/${DIGEST}`,
    );
  });

  it("offers Today, Decisions, Positions, Activity, Review and Evidence", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect([...nav.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      // Positions and Review joined in PUI Phase 4 (owner decision D5); Evidence
      // stays last, secondary.
      "/", "/decisions", "/positions", "/activity", "/review", "/evidence",
    ]);
  });

  it("sends a tour link shared before the move to Evidence", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/?tour=1"));
    expect(await screen.findByTestId("tour-card")).toHaveTextContent("What was observed");
    expect(screen.getByRole("heading", { name: "Evidence and proof" })).toBeInTheDocument();
  });

  it("returns to the same filtered list on back navigation", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    const history = createMemoryHistory({ initialEntries: ["/decisions?view=Refusals"] });
    render(<App history={history} />);
    await userEvent.click(await screen.findByRole("link", { name: /SPY.*No trade/ }));
    await screen.findByTestId("decision-ticket");
    // Going back re-renders the router; outside act() React logs a warning
    // for every component it updates (29 of them, the suite's entire stderr).
    act(() => history.back());
    const nav = await screen.findByRole("navigation", { name: "Decision views" });
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent("Refusals");
  });
});
