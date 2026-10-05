import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  at,
  envelope,
  respond,
} from "../test/fixtures";

/** The activity workspace: the audit feed, incidents and worker events. */

afterEach(() => vi.unstubAllGlobals());

describe("the activity workspace", () => {
  it("pages with the server's cursor and shows every event once", async () => {
    // RUI-VAL-004: `sequence` restarts per decision, so the feed is paged by an
    // opaque cursor over (occurred_at, id). The client passes it back untouched.
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/activity"));

    const feed = await screen.findByTestId("activity");
    expect(feed.querySelectorAll("tbody tr")).toHaveLength(1);
    // One item and a cursor: still more, however short the page was.
    expect(screen.getByTestId("activity-count")).toHaveTextContent("more available");

    await userEvent.click(screen.getByTestId("activity-more"));
    await waitFor(() => expect(feed.querySelectorAll("tbody tr")).toHaveLength(3));
    expect(screen.getByTestId("activity-count")).toHaveTextContent("the feed ends here");
    expect(screen.queryByTestId("activity-more")).toBeNull();

    const asked = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(asked).toContain("/api/v1/activity?cursor=opaque-page-2");
    // Never a cursor of its own devising, and never the per-decision sequence.
    expect(asked.filter((url) => url.includes("sequence"))).toEqual([]);
  });

  it("keeps a refusal legible as a refusal", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/activity"));
    const feed = await screen.findByTestId("activity");
    const refused = feed.querySelector('tr[data-refused="true"]');
    expect(refused).not.toBeNull();
    expect(refused).toHaveTextContent("no_qualified_setup");
  });

  it("says an empty open list is the source answering, not a filter hiding", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/activity"));
    const incidents = await screen.findByTestId("incidents");
    expect(incidents).toHaveAttribute("data-present", "false");
    expect(incidents).toHaveTextContent("This is the source answering");
  });

  it("keeps the filter usable while the list is empty, and names withheld detail", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/activity"));
    await screen.findByTestId("incidents");
    await userEvent.click(screen.getByTestId("incidents-all"));
    await waitFor(() =>
      expect(screen.getByTestId("incidents")).toHaveAttribute("data-present", "true"),
    );
    const incidents = screen.getByTestId("incidents");
    expect(incidents).toHaveTextContent("broker_timeout");
    // `detail` is free text a broker error chose: named, never shown.
    expect(incidents).toHaveTextContent("withheld: detail");
  });

  it("tells an empty worker source apart from one that cannot answer", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/activity"));
    const panel = await screen.findByTestId("worker-events");
    expect(panel).toHaveTextContent("holds no worker events");

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        "/api/v1/worker/events": envelope({
          available: false, reason: "the worker_events table is absent", items: [],
        }),
      }),
    );
    render(at("/activity"));
    await waitFor(() =>
      expect(screen.getAllByTestId("worker-events")[1]).toHaveTextContent("cannot answer"),
    );
    expect(screen.getAllByTestId("worker-events")[1]).toHaveTextContent(
      "the worker_events table is absent",
    );
  });
});
