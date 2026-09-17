import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../router";

const DIGEST = "a".repeat(64);

const envelope = <T,>(data: T, over: Record<string, unknown> = {}) => ({
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
  entries: [{
    decision_id: DIGEST, snapshot_id: "spy-agent-1", action: "NO_TRADE",
    direction: "neutral", label: "SPY agent 1\nno_qualified_setup", count: 72, member_ids: [],
  }],
  shown: 1, total: 201, grouped: true, pin_missing: false,
};

const summary = {
  decision_id: DIGEST, snapshot_id: "spy-agent-1", action: "NO_TRADE", direction: "neutral",
  reason_codes: ["no_qualified_setup"], input_hash: "sha256:in",
  decision_hash: `sha256:${DIGEST}`, policy_version: "h0-provisional-1",
  decided_at: "2026-09-17T14:00:00+00:00", observation: null,
  reached_the_broker: false, model_was_called: false,
  why: [{ stage: "01 evidence", text: "no setup qualified", source: "evidence_packs", present: true }],
};

const market = {
  observation: null, observation_kind: "provider", signals: [], qualification: null,
  structure: {
    gate: "separation_or_side", bars_considered: 120, bars_required: 70,
    fast_ema: "640.100000", slow_ema: "639.900000", separation: "0.00031250",
    last_close: "640.500000", close_side: "above", retest_touched: null,
    separation_shortfall: "-0.00168750",
  },
};

const horizons = [
  { horizon: "T+1", sessions: 1, state: "COMPLETE", resolved: true,
    underlying_at_decision: "640.50", underlying_at_horizon: "646.00", change: "5.50",
    direction_agreed: null, realized: null, observed_snapshot_id: "spy-agent-2" },
  { horizon: "T+3", sessions: 3, state: "PENDING", resolved: false,
    underlying_at_decision: null, underlying_at_horizon: null, change: null,
    direction_agreed: null, realized: null, observed_snapshot_id: null },
];

const tiles = [
  { value: "0", label: "reconciled Paper lifecycles", mode: "UNAVAILABLE", available: false,
    source: "positions joined through decisions", detail: "no position has both ends" },
];

const review = {
  horizons: [], decisions: 201, decisions_reviewed: 136, positions_ever: 0,
  resolved: 160, pending: 242,
  caveat: "All 136 reviewed decisions are refusals: no position has ever been opened.",
};

const scenes = [
  { number: 1, title: "What was observed", narration: "The system reads a completed close.",
    tab: 0, snapshot_id: "spy-qualified-2026-08-27", decision_id: DIGEST },
  { number: 2, title: "A case this source lacks", narration: "Never shown.",
    tab: 0, snapshot_id: "spy-lifecycle-2026", decision_id: null },
];

const routes: Record<string, unknown> = {
  "/api/v1/system/status": envelope(status),
  "/api/v1/system/proof": envelope(tiles),
  "/api/v1/decisions/grouped": envelope(listing),
  "/api/v1/outcomes": envelope(review),
  "/api/v1/tour": envelope(scenes),
  [`/api/v1/decisions/${DIGEST}/summary`]: envelope(summary),
  [`/api/v1/decisions/${DIGEST}/market`]: envelope(market),
  [`/api/v1/decisions/${DIGEST}/outcomes`]: envelope(horizons),
};

function respond(failing: Set<string> = new Set(), over: Record<string, unknown> = {}) {
  const map = { ...routes, ...over };
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    // Longest match first: /decisions/{d}/outcomes must not be served by /outcomes.
    const key = Object.keys(map).sort((a, b) => b.length - a.length).find((k) => url.startsWith(k));
    if (!key || failing.has(key)) return Promise.reject(new Error("network down"));
    return Promise.resolve({
      ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(map[key]),
    } as Response);
  });
}

const at = (path: string) => <App history={createMemoryHistory({ initialEntries: [path] })} />;

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
    render(at("/"));
    const tilesEl = await screen.findByTestId("proof-tiles");
    expect(tilesEl.querySelector('[data-available="false"]')).not.toBeNull();
  });

  it("shows the server's caveat about what the outcomes do not measure", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    expect(await screen.findByTestId("review-caveat")).toHaveTextContent("are refusals");
  });

  it("reports an unreachable API instead of an empty shell", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/system/status"])));
    render(at("/"));
    expect(await screen.findByRole("alert")).toHaveTextContent("unreachable");
    expect(screen.queryByTestId("status-strip")).toBeNull();
  });
});

describe("a decision is addressable", () => {
  it("opens from its own URL without going through the list", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    expect(await screen.findByTestId("decision-ticket")).toHaveTextContent("spy-agent-1");
  });

  it("is reachable by following the list", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: /SPY agent 1/ }));
    await waitFor(() => expect(screen.getByTestId("decision-ticket")).toBeInTheDocument());
  });

  it("says so when the source holds no such decision", async () => {
    vi.stubGlobal("fetch", respond(new Set([`/api/v1/decisions/${DIGEST}/summary`])));
    render(at(`/decisions/${DIGEST}`));
    expect(await screen.findByTestId("decision-missing")).toBeInTheDocument();
  });
});

describe("the ticket shows the server's own reasoning", () => {
  it("marks the model's one stage and leaves the rest to code", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const spine = await screen.findByTestId("authority-spine");
    const memo = spine.querySelector('[data-stage="03"]');
    expect(memo).toHaveClass("model");
    expect(memo).toHaveAttribute("data-lit", "false");
    // The stage a refusal never reached must say so, not merely look faint.
    expect(spine.querySelector('[data-stage="07"]')?.textContent).toContain("not reached");
  });

  it("explains how nearly the setup qualified", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const structure = await screen.findByTestId("structure-reading");
    expect(structure).toHaveTextContent("separation_or_side");
    expect(structure).toHaveTextContent("-0.00168750");
    expect(structure).toHaveTextContent("short of the threshold");
  });

  it("says so when no structure reading was recorded, rather than dropping the section", async () => {
    // Every committed-evidence decision has `structure: null`, so this is the
    // case the demo actually shows. Silently omitting it put a refusal's
    // central question off the page with no account of why.
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        [`/api/v1/decisions/${DIGEST}/market`]: envelope({ ...market, structure: null }),
      }),
    );
    render(at(`/decisions/${DIGEST}`));
    const structure = await screen.findByTestId("structure-reading");
    expect(structure).toHaveAttribute("data-present", "false");
    expect(structure).toHaveTextContent("No structure reading was recorded");
    expect(structure).toHaveTextContent("structure_readings");
  });

  it("shows a waiting horizon as waiting rather than hiding it", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const list = await screen.findByTestId("horizons");
    expect(list).toHaveTextContent("WAITING");
    expect(list).toHaveTextContent("T+1");
  });
});

describe("the guided path", () => {
  it("is a shareable step, and opens its own decision", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/?tour=1"));
    const card = await screen.findByTestId("tour-card");
    expect(card).toHaveTextContent("What was observed");
    expect(card.querySelector("a")).toHaveAttribute("href", `/decisions/${DIGEST}`);
  });

  it("admits a step whose decision this source lacks", async () => {
    /* RUI-VAL-009: the dashboard narrated over another decision for weeks. */
    vi.stubGlobal("fetch", respond());
    render(at("/?tour=2"));
    expect(await screen.findByTestId("scene-absent")).toHaveTextContent("is not in this source");
    expect(screen.queryByText("Never shown.")).toBeNull();
  });

  it("clamps a hand-edited step rather than raising", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/?tour=99"));
    expect(await screen.findByTestId("tour-card")).toBeInTheDocument();
  });
});
