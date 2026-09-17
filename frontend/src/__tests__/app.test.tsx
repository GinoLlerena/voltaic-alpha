import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

const envelope = <T,>(data: T, over: Partial<Record<string, unknown>> = {}) => ({
  schema_version: "public.v1",
  source_mode: "LIVE",
  source_label: "live worker database (201 decisions)",
  observed_at: "2026-09-17T08:00:00+00:00",
  correlation_id: null,
  data,
  ...over,
});

const status = [
  { label: "Order writes", value: "DISABLED", tone: "ok", known: true,
    source: "runs.trading_enabled", observed_at: null, reason: null },
  { label: "Worker", value: "UNKNOWN", tone: "unknown", known: false,
    source: "worker_leases", observed_at: null, reason: "no lease row" },
];

const listing = {
  view: "Notable",
  entries: [
    { decision_id: "a".repeat(64), snapshot_id: "spy-agent-1", action: "NO_TRADE",
      direction: "neutral", label: "SPY agent 1\nno_qualified_setup", count: 72,
      member_ids: [] },
  ],
  shown: 1, total: 201, grouped: true, pin_missing: false,
};

const summary = {
  decision_id: "a".repeat(64), snapshot_id: "spy-agent-1", action: "NO_TRADE",
  direction: "neutral", reason_codes: ["no_qualified_setup"], input_hash: "sha256:in",
  decision_hash: `sha256:${"a".repeat(64)}`, policy_version: "h0", decided_at: null,
  observation: null, reached_the_broker: false, model_was_called: false, why: [],
};

function respond(map: Record<string, unknown>, failing: Set<string> = new Set()) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const key = Object.keys(map).find((k) => url.startsWith(k));
    if (!key || failing.has(key)) {
      return Promise.reject(new Error("network down"));
    }
    return Promise.resolve({
      ok: true, status: 200, statusText: "OK",
      json: () => Promise.resolve(map[key]),
    } as Response);
  });
}

const healthy = {
  "/api/v1/system/status": envelope(status),
  "/api/v1/decisions/grouped": envelope(listing),
  [`/api/v1/decisions/${"a".repeat(64)}/summary`]: envelope(summary),
};

afterEach(() => vi.unstubAllGlobals());

describe("the shell says where its data came from", () => {
  it("names the live source rather than implying it", async () => {
    vi.stubGlobal("fetch", respond(healthy));
    render(<App />);
    const banner = await screen.findByTestId("source-banner");
    expect(banner).toHaveAttribute("data-mode", "LIVE");
    expect(banner).toHaveTextContent("live worker database (201 decisions)");
  });

  it("marks committed evidence as committed, not live", async () => {
    vi.stubGlobal("fetch", respond({
      ...healthy,
      "/api/v1/system/status": envelope(status, {
        source_mode: "FROZEN_REPLAY", source_label: "committed evidence",
      }),
    }));
    render(<App />);
    const banner = await screen.findByTestId("source-banner");
    expect(banner).toHaveTextContent("COMMITTED EVIDENCE");
    expect(banner).not.toHaveTextContent("LIVE");
  });
});

describe("the shell renders the server's judgement, not its own", () => {
  it("keeps an unknown unknown and shows the reason given", async () => {
    vi.stubGlobal("fetch", respond(healthy));
    render(<App />);
    const strip = await screen.findByTestId("status-strip");
    const unknown = strip.querySelector('[data-known="false"]');
    expect(unknown).not.toBeNull();
    expect(unknown).toHaveTextContent("UNKNOWN");
    expect(unknown).toHaveTextContent("no lease row");
  });

  it("shows the grouped count the server computed", async () => {
    vi.stubGlobal("fetch", respond(healthy));
    render(<App />);
    expect(await screen.findByText(/1 of 201/)).toBeInTheDocument();
    expect(screen.getByText("×72")).toBeInTheDocument();
  });
});

describe("a failure never turns into a blank screen", () => {
  it("reports an unreachable API instead of rendering an empty shell", async () => {
    vi.stubGlobal("fetch", respond(healthy, new Set(["/api/v1/system/status"])));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("unreachable");
    expect(screen.queryByTestId("status-strip")).toBeNull();
  });

  it("keeps the last verified response when a refresh fails, and says it is old", async () => {
    vi.useFakeTimers();
    const fetcher = respond(healthy);
    vi.stubGlobal("fetch", fetcher);
    render(<App />);
    await vi.waitFor(() => expect(screen.getByTestId("status-strip")).toBeInTheDocument());

    vi.stubGlobal("fetch", respond(healthy, new Set(["/api/v1/system/status"])));
    await vi.advanceTimersByTimeAsync(16_000);
    await vi.waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Showing last verified state"),
    );
    // The data it had is still on screen: a reader can tell old from broken.
    expect(screen.getByTestId("status-strip")).toBeInTheDocument();
    vi.useRealTimers();
  });
});

describe("selecting a decision", () => {
  it("shows the identity the server reports for it", async () => {
    vi.stubGlobal("fetch", respond(healthy));
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /SPY agent 1/ }));
    await waitFor(() =>
      expect(screen.getByTestId("selected-decision")).toHaveTextContent("NO_TRADE"),
    );
  });
});
