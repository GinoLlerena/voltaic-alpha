import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  at,
  envelope,
  executionRow,
  journalPage1,
  noExecutions,
  QUALIFIED,
  respond,
} from "../test/fixtures";

/** Review: execution outcomes and research horizons, never mixed (PUI phase 4). */

afterEach(() => vi.unstubAllGlobals());

describe("Review (PUI phase 4)", () => {
  it("leads with the caveat and says there is no execution outcome when none exists", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/review"));
    expect(await screen.findByTestId("review-caveat")).toBeInTheDocument();
    const executions = screen.getByTestId("review-executions");
    expect(await within(executions).findByTestId("executions-empty")).toHaveTextContent(
      "No position has been closed in this source",
    );
    // The caveat precedes both sections: it says what this source can speak about.
    const page = screen.getByTestId("review-caveat").compareDocumentPosition(executions);
    expect(page & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows a session as one row: its decisions counted, its close, and the horizon", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/review"));
    const journal = await screen.findByTestId("review-journal");
    const rows = await within(journal).findAllByTestId("journal-row");
    const monday = rows[1]!;
    expect(monday).toHaveTextContent("Mon, Oct 5, 2026");
    expect(monday).toHaveTextContent("65 decisions");
    expect(monday).toHaveTextContent("65 × No trade: no qualified setup");
    expect(monday).toHaveTextContent("769.64");
    expect(monday).toHaveTextContent("774.83 (+5.19)");
    expect(monday).toHaveTextContent("65 resolved");
    // A refusal states no direction: that is said, not scored as a miss.
    expect(monday).toHaveTextContent("no direction was stated");
    expect(within(journal).getByTestId("journal-scope")).toHaveTextContent(
      "3 of 4 market sessions",
    );
  });

  it("says waiting for a horizon that has not elapsed, and nothing for an empty session", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/review"));
    const rows = await screen.findAllByTestId("journal-row");
    expect(rows[0]).toHaveTextContent("waiting (65)");
    expect(rows[0]).not.toHaveTextContent("+");
    const empty = rows[2]!;
    expect(empty).toHaveAttribute("data-decisions", "0");
    expect(empty).toHaveTextContent("none recorded");
    expect(empty).toHaveTextContent("no decision was recorded");
    expect(within(empty).queryByRole("link")).toBeNull();
  });

  it("links a session to exactly that day's decisions", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/review"));
    const rows = await screen.findAllByTestId("journal-row");
    expect(within(rows[1]!).getByRole("link", { name: "65 decisions" })).toHaveAttribute(
      "href",
      "/decisions?view=Everything&day=2026-10-05",
    );
  });

  it("pages to earlier sessions on the server's own value and counts agreement, not a rate", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/review"));
    await userEvent.click(await screen.findByTestId("journal-more"));
    await waitFor(() => expect(screen.getAllByTestId("journal-row")).toHaveLength(4));
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain(
      "/api/v1/review/sessions?horizon=T%2B1&before=2026-10-02",
    );
    const oldest = screen.getAllByTestId("journal-row")[3]!;
    expect(oldest).toHaveTextContent("1 × Position · bullish");
    expect(oldest).toHaveTextContent("1 agreed · 0 did not");
    expect(oldest).toHaveTextContent("1 stated no direction");
    expect(screen.getByTestId("journal-end")).toHaveTextContent("The journal ends here");
    expect(screen.getByTestId("review-journal")).not.toHaveTextContent("%");
  });

  it("keeps the horizon in the URL and asks the server for it", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/review?horizon=T%2B3"));
    const nav = await screen.findByRole("navigation", { name: "Review horizon" });
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent("T+3");
    await screen.findAllByTestId("journal-row");
    const asked = fetchMock.mock.calls.map(([u]) => String(u));
    expect(asked).toContain("/api/v1/review/sessions?horizon=T%2B3");
    expect(asked).not.toContain("/api/v1/review/sessions?horizon=T%2B1");
  });

  it("treats an unknown horizon as the default rather than sending it", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/review?horizon=T%2B9"));
    await screen.findAllByTestId("journal-row");
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain(
      "/api/v1/review/sessions?horizon=T%2B1",
    );
  });

  it("shows a closed round trip with its prices, units and a result from the fills", async () => {
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        "/api/v1/review/executions?kind=closed": envelope({
          items: [executionRow], next_cursor: null, kind: "closed", closed: 1, abandoned: 0,
        }),
      }),
    );
    render(at("/review"));
    const row = await screen.findByTestId("execution-row");
    expect(row).toHaveTextContent("SPY · bull call debit spread");
    expect(row).toHaveTextContent("3.13 → 2.80");
    expect(row).toHaveTextContent("per share");
    expect(row).toHaveTextContent("-33.00 USD");
    expect(row).toHaveTextContent("whole structure, from fills");
    expect(row).toHaveTextContent("1 h 0 min");
    expect(row).toHaveTextContent("stop loss");
    expect(within(row).getByRole("link")).toHaveAttribute("href", `/decisions/${QUALIFIED}`);
    expect(screen.queryByTestId("executions-empty")).toBeNull();
  });

  it("lists an abandoned entry apart, as no exposure and never as a zero result", async () => {
    const abandoned = {
      ...executionRow,
      result: "no_exposure", close_price: null, exit_trigger: null, exit_reason: null,
      held_seconds: null, sessions_held: null,
      position: {
        ...executionRow.position, state: "ABANDONED", filled_quantity: 0, entry_debit: null,
        realized: null, closed_at: null, close_reason: null,
      },
    };
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        "/api/v1/review/executions?kind=abandoned": envelope({
          items: [abandoned], next_cursor: null, kind: "abandoned", closed: 0, abandoned: 1,
        }),
      }),
    );
    render(at("/review"));
    const block = await screen.findByTestId("executions-abandoned");
    expect(block).toHaveTextContent("1 entry ended without a fill");
    expect(block).toHaveTextContent("these are not zero results");
    expect(block).toHaveTextContent("requested 1, filled 0");
    expect(block).not.toHaveTextContent("USD");
  });

  it("says a failed section failed, and keeps the other section", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/review/executions?kind=closed"])));
    render(at("/review"));
    expect(await screen.findAllByTestId("journal-row")).toHaveLength(3);
    const executions = screen.getByTestId("review-executions");
    expect(within(executions).getByText(/unavailable/)).toBeInTheDocument();
    expect(within(executions).queryByTestId("executions-empty")).toBeNull();
  });

  it("is reachable from the primary navigation", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Review" })).toHaveAttribute("href", "/review");
  });

  it("an empty source has no journal and says so", async () => {
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        "/api/v1/review/sessions?": envelope({ ...journalPage1, items: [], total: 0, next_cursor: null }),
        "/api/v1/review/executions?kind=closed": envelope(noExecutions("closed")),
      }),
    );
    render(at("/review"));
    expect(await screen.findByText(/holds no decisions, so there is no journal/)).toBeInTheDocument();
  });
});

describe("decisions for one market day (PUI phase 4)", () => {
  it("asks the full history for that day and says which day it is", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions?view=Everything&day=2026-10-05"));
    const scope = await screen.findByTestId("decision-scope");
    expect(scope).toHaveTextContent("on Mon, Oct 5, 2026 (New York market day)");
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain(
      "/api/v1/decisions?day=2026-10-05&limit=50",
    );
    expect(within(scope).getByRole("link", { name: "Show every day" })).toHaveAttribute(
      "href",
      "/decisions?view=Everything",
    );
  });

  it("ignores a malformed day rather than sending it", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions?view=Everything&day=yesterday"));
    await screen.findByTestId("decision-scope");
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain("/api/v1/decisions?limit=50");
  });
});
