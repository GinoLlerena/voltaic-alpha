import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIGEST,
  QUALIFIED,
  at,
  envelope,
  qualifiedMarket,
  respond,
  structure,
  summary,
} from "../test/fixtures";

/** Loading, failed, stale and empty are never confused (PUI phase 1). */

afterEach(() => vi.unstubAllGlobals());

describe("truthful state (PUI phase 1)", () => {
  const OPEN = "/api/v1/incidents?state=open";

  it("says incidents are loading, not that none is open, before the answer arrives", async () => {
    vi.stubGlobal("fetch", respond(new Set(), {}, {}, new Set([OPEN])));
    render(at("/activity"));
    const panel = await screen.findByTestId("incidents");
    await waitFor(() => expect(panel).toHaveTextContent("Loading incidents"));
    expect(panel).not.toHaveTextContent("No incident is open");
    expect(panel).toHaveAttribute("data-present", "false");
  });

  it("says incidents are unavailable when the request fails, and offers a retry", async () => {
    const fetchMock = respond(new Set([OPEN]));
    vi.stubGlobal("fetch", fetchMock);
    render(at("/activity"));
    const panel = await screen.findByTestId("incidents");
    await waitFor(() => expect(panel).toHaveTextContent("incidents unavailable"));
    expect(panel).not.toHaveTextContent("No incident is open");
    const before = fetchMock.mock.calls.filter((c) => String(c[0]) === OPEN).length;
    await userEvent.click(within(panel).getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter((c) => String(c[0]) === OPEN).length).toBe(before + 1),
    );
  });

  it("dates a verified empty incident list", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/activity"));
    const panel = await screen.findByTestId("incidents");
    await waitFor(() => expect(panel).toHaveTextContent(/No incident is open\..*Checked \d{4}-\d\d-\d\d/));
  });

  it("does not report an empty worker feed when the request fails", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/worker/events"])));
    render(at("/activity"));
    const panel = await screen.findByTestId("worker-events");
    await waitFor(() => expect(panel).toHaveTextContent("unavailable"));
    expect(panel).not.toHaveTextContent("holds no worker events");
  });

  it("does not turn failed horizons or market data into 'nothing scheduled/recorded'", async () => {
    vi.stubGlobal(
      "fetch",
      respond(new Set([`/api/v1/decisions/${DIGEST}/outcomes`, `/api/v1/decisions/${DIGEST}/market`])),
    );
    render(at(`/decisions/${DIGEST}`));
    const horizonsPanel = await screen.findByTestId("horizons");
    await waitFor(() => expect(horizonsPanel).toHaveTextContent("review horizons unavailable"));
    expect(horizonsPanel).not.toHaveTextContent("No horizons were scheduled");
    const reading = screen.getByTestId("structure-reading");
    expect(reading).toHaveTextContent("setup reading unavailable");
    expect(reading).not.toHaveTextContent("No structure reading was recorded");
    expect(screen.getByTestId("market-as-of")).toHaveTextContent("unavailable");
  });

  it("flags a panel answered from a different source than the decision", async () => {
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        [`/api/v1/decisions/${QUALIFIED}/market`]: envelope(qualifiedMarket, {
          source_id: "committed",
          source_label: "committed evidence (5 decisions)",
        }),
      }),
    );
    render(at(`/decisions/${QUALIFIED}`));
    const notes = await screen.findAllByTestId("source-mismatch");
    expect(notes[0]).toHaveTextContent("committed evidence (5 decisions)");
    expect(notes[0]).toHaveTextContent("live worker database (201 decisions)");
  });

  it("does not flag a panel refreshed after the worker's next decision (CSA-007)", async () => {
    // Same database, one more decision: the label's count moved, the source did not.
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        [`/api/v1/decisions/${QUALIFIED}/market`]: envelope(qualifiedMarket, {
          source_label: "live worker database (202 decisions)",
        }),
      }),
    );
    render(at(`/decisions/${QUALIFIED}`));
    await screen.findByTestId("structure-selected");
    await screen.findByTestId("observation");
    expect(screen.queryByTestId("source-mismatch")).toBeNull();
  });

  it("heads the setup reading by the recorded outcome", async () => {
    vi.stubGlobal("fetch", respond());
    const refused = render(at(`/decisions/${DIGEST}`));
    expect(await screen.findByTestId("structure-reading")).toHaveTextContent(
      "Why the setup did not qualify",
    );
    refused.unmount();

    render(at(`/decisions/${QUALIFIED}`));
    const reading = await screen.findByTestId("structure-reading");
    expect(reading).toHaveTextContent("How the setup qualified");
    expect(reading).not.toHaveTextContent("did not qualify");
  });

  it("does not call a refusal for another reason a setup that did not qualify", async () => {
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        [`/api/v1/decisions/${DIGEST}/summary`]: envelope({
          ...summary, reason_codes: ["risk_budget_exceeded"],
        }),
      }),
    );
    render(at(`/decisions/${DIGEST}`));
    const reading = await screen.findByTestId("structure-reading");
    expect(reading).toHaveTextContent("The setup reading");
    expect(reading).not.toHaveTextContent("did not qualify");
  });

  it("does not present an unselected fallback candidate as the structure taken", async () => {
    // The API's `selected` falls back to the first candidate when none is marked.
    const fallback = { ...structure.selected, selected: false, rejection_reasons: ["quote too wide"] };
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        [`/api/v1/decisions/${QUALIFIED}/structure`]: envelope({
          selected: fallback, candidates: [fallback],
        }),
      }),
    );
    render(at(`/decisions/${QUALIFIED}`));
    const taken = await screen.findByTestId("structure-selected");
    expect(taken).toHaveAttribute("data-present", "false");
    expect(taken).toHaveTextContent("No candidate was selected. 1 evaluated candidate(s)");
    expect(screen.getByTestId("structure-rejected")).toHaveTextContent("quote too wide");
  });

  it("labels the banner time as the API's answer, and shows the market input's own time", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    expect(await screen.findByTestId("api-answered")).toHaveTextContent("API answered");
    expect(screen.getByTestId("source-banner")).toHaveTextContent("not market-data time");
    expect(screen.getByTestId("market-as-of")).toHaveTextContent("2026-08-28T15:47:47+00:00");
  });

  it("holds the activity view still while older pages are shown, and offers the newest", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/activity"));
    const feed = await screen.findByTestId("activity");
    await waitFor(() => expect(feed.querySelectorAll("tbody tr")).toHaveLength(1));
    expect(screen.queryByTestId("activity-newest")).toBeNull();

    await userEvent.click(screen.getByTestId("activity-more"));
    await waitFor(() => expect(feed.querySelectorAll("tbody tr")).toHaveLength(3));
    await userEvent.click(screen.getByTestId("activity-newest"));
    await waitFor(() => expect(feed.querySelectorAll("tbody tr")).toHaveLength(1));
    expect(screen.getByTestId("activity-count")).toHaveTextContent("more available");
  });

  it("says the decision list is unavailable instead of dropping it", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/decisions/grouped"])));
    render(at("/decisions"));
    expect(await screen.findByText(/recorded decisions unavailable/)).toBeInTheDocument();
  });
});

// PUI Phase 2: the personal shell. `/` answers "does anything need attention?"
// before anything else, and demonstration material lives under Evidence.
