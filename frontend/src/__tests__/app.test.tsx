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

// RUI-4. A second decision that qualified, so the depth panels have records;
// DIGEST stays a refusal, which is the case that must keep rendering absences.
const QUALIFIED = "b".repeat(64);

const qualifiedSummary = {
  ...summary, decision_id: QUALIFIED, snapshot_id: "spy-qualified-1",
  action: "OPTIONS_POSITION", direction: "bullish", reason_codes: [],
  decision_hash: `sha256:${QUALIFIED}`, model_was_called: true, reached_the_broker: false,
};

const qualifiedMarket = {
  observation: {
    symbol: "SPY", provider: "alpaca", feed: "indicative",
    source_time: "2026-08-28T15:47:47+00:00", received_time: "2026-08-28T15:48:00+00:00",
    underlying_price: "771.100000", payload_hash: "sha256:obs",
  },
  observation_kind: "provider",
  signals: [
    { signal_id: "sig-structure", family: "structure", direction: "bullish", strength: "0.6500",
      as_of: "2026-08-28T15:47:47+00:00", source: "alpaca:daily_bars", role: "cited",
      summary: "EMA20 is 0.0130 from EMA50 in the bullish direction." },
    { signal_id: "sig-breadth", family: "breadth", direction: "bearish", strength: "0.2000",
      as_of: "2026-08-28T15:47:47+00:00", source: "alpaca:daily_bars", role: "counter-evidence",
      summary: "Breadth is narrowing." },
  ],
  qualification: {
    setup_id: "spy-trend-retest-1", setup_family: "trend_continuation_retest",
    direction: "bullish", classifier_name: "deterministic_trend_retest_v0",
    evidence_ids: ["sig-structure"], payload_hash: "sha256:setup",
    invalidation_conditions: ["close below 759.53 invalidates the retest", "loss of structure"],
  },
  structure: null,
};

const memo = {
  produced: true,
  thesis: {
    synthesizer_name: "deterministic_baseline_v0", direction: "bullish", confidence: "0.7050",
    evidence_ids: ["sig-structure"], counter_evidence_ids: ["sig-breadth"],
    invalidation_conditions: ["close below 759.53 invalidates the retest"],
    reasoning_summary: "Deterministic baseline: qualified bullish from 1 aligned signal.",
  },
  model_call: null,
};

const structure = {
  selected: {
    candidate_id: "cand-vertical", strategy: "bull_call_debit_spread",
    long_contract_symbol: "SPY260911C00772000", short_contract_symbol: "SPY260911C00778000",
    quantity: 1, estimated_debit: "3.500000", calculated_max_loss: "350.000000",
    selected: true, rejection_reasons: [],
    leg_quotes: [
      { contract_symbol: "SPY260911C00772000", option_type: "call", expiration: "2026-09-11",
        dte: 14, strike: "772", bid: "7.17", ask: "7.35", delta: "0.5518",
        implied_volatility: "0.104" },
    ],
  },
  candidates: [
    { candidate_id: "cand-wide", strategy: "bull_call_debit_spread",
      long_contract_symbol: "SPY260911C00772000", short_contract_symbol: "SPY260911C00790000",
      quantity: 1, estimated_debit: "6.000000", calculated_max_loss: "600.000000",
      selected: false, rejection_reasons: ["max loss exceeds the risk budget"], leg_quotes: [] },
  ],
};

const risk = {
  decisions: [{
    governor_name: "deterministic_risk_governor_v0", approved: true, reason_codes: [],
    checks: [
      { check: "max_loss_recomputed", passed: true, recomputed: "350.00", claimed: "350.00" },
      { check: "within_risk_budget", passed: true, budget: "750.00", max_loss: "350.00" },
    ],
    risk_budget: "750.000000", calculated_max_loss: "350.000000",
    policy_version: "h0-provisional-1", intent_ttl_seconds: null,
  }],
  accounting: {
    account_equity: "100000", risk_budget: "750.000000", maximum_loss: "350.000000",
    budget_used_percent: "46.67",
  },
};

const lifecycle = {
  reached_the_broker: false, intents: [], orders: [], positions: [], exits: [],
  trail: { complete: true, gaps: [], events: [] },
  receipt: { relation: "OTHER_DECISION", belongs: false, matched_on: "decision_hash",
    reason: "this receipt records a different evaluation of the same snapshot", facts: {} },
  ablation: { relation: "NOT_DECISION_SCOPED", belongs: false, matched_on: null,
    reason: "a corpus-level result over 5 frozen cases", facts: {} },
};

const proof = {
  manifest_digest: "sha256:manifest",
  manifest: {
    manifest_version: "proof-manifest-2",
    disclosures: ["Alpaca Paper only. No live endpoint exists in this build.", "Nothing here is investment advice."],
  },
};

// RUI-5. Two pages, and the FIRST one is deliberately shorter than the second:
// the end of the feed is `next_cursor === null` and nothing else. A client that
// inferred "short page, therefore finished" would stop here with a third of the
// events and no sign that it had.
const activityPage1 = {
  items: [
    { correlation_id: "spy-agent-1", sequence: 2, stage: "DECIDED", outcome: "NO_TRADE",
      component: "decision_workflow", reason_codes: ["no_qualified_setup"],
      occurred_at: "2026-09-17T14:00:01+00:00", refused: true },
  ],
  next_cursor: "opaque-page-2",
};

const activityPage2 = {
  items: [
    { correlation_id: "spy-agent-1", sequence: 1, stage: "OBSERVED", outcome: "accepted",
      component: "decision_workflow", reason_codes: [], occurred_at: "2026-09-17T14:00:00+00:00",
      refused: false },
    { correlation_id: "spy-agent-2", sequence: 1, stage: "OBSERVED", outcome: "accepted",
      component: "decision_workflow", reason_codes: [], occurred_at: "2026-09-17T15:00:00+00:00",
      refused: false },
  ],
  next_cursor: null,
};

const incidentsOpen: unknown[] = [];
const incidentsAll = [
  { kind: "broker_timeout", severity: "warning", execution_state: "RECONCILING",
    opened_at: "2026-09-16T10:00:00+00:00", resolved_at: "2026-09-16T10:05:00+00:00",
    open: false, withheld: ["detail"] },
];

const workerEvents = { available: true, reason: null, items: [] };

const routes: Record<string, unknown> = {
  "/api/v1/system/status": envelope(status),
  "/api/v1/system/proof": envelope(tiles),
  "/api/v1/decisions/grouped": envelope(listing),
  "/api/v1/outcomes": envelope(review),
  "/api/v1/tour": envelope(scenes),
  [`/api/v1/decisions/${DIGEST}/summary`]: envelope(summary),
  [`/api/v1/decisions/${DIGEST}/market`]: envelope(market),
  [`/api/v1/decisions/${DIGEST}/outcomes`]: envelope(horizons),
  [`/api/v1/decisions/${QUALIFIED}/summary`]: envelope(qualifiedSummary),
  [`/api/v1/decisions/${QUALIFIED}/market`]: envelope(qualifiedMarket),
  [`/api/v1/decisions/${QUALIFIED}/memo`]: envelope(memo),
  [`/api/v1/decisions/${QUALIFIED}/structure`]: envelope(structure),
  [`/api/v1/decisions/${QUALIFIED}/risk`]: envelope(risk),
  [`/api/v1/decisions/${QUALIFIED}/lifecycle`]: envelope(lifecycle),
  [`/api/v1/decisions/${QUALIFIED}/proof`]: envelope(proof),
  [`/api/v1/decisions/${QUALIFIED}/outcomes`]: envelope(horizons),
  "/api/v1/activity?cursor=opaque-page-2": envelope(activityPage2),
  "/api/v1/activity": envelope(activityPage1),
  "/api/v1/incidents?state=open": envelope(incidentsOpen),
  "/api/v1/incidents?state=all": envelope(incidentsAll),
  "/api/v1/worker/events": envelope(workerEvents),
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


describe("a trader's five questions", () => {
  // RUI-4's exit. Each answer must come from a record, and a question this
  // decision cannot answer must say so: an omitted row reads as though the
  // question did not apply, which for a refusal is the opposite of the truth.
  it("answers all five from the decision's own records", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const five = await screen.findByTestId("trader-summary");
    expect(five).toHaveTextContent("bullish, by deterministic_trend_retest_v0");
    expect(five).toHaveTextContent("1 signal(s) cited at 771.100000");
    expect(five).toHaveTextContent("bull_call_debit_spread ×1, debit 3.500000");
    expect(five).toHaveTextContent("350.000000 of 750.000000");
    expect(five).toHaveTextContent("close below 759.53 invalidates the retest");
    expect(five.querySelectorAll('[data-answered="true"]')).toHaveLength(5);
  });

  it("says which questions a refusal cannot answer", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const five = await screen.findByTestId("trader-summary");
    expect(five.querySelectorAll('[data-answered="false"]')).toHaveLength(5);
    expect(five).toHaveTextContent("not answerable from this decision's records");
  });

  it("links each question to the panel that evidences it", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const five = await screen.findByTestId("trader-summary");
    const targets = [...five.querySelectorAll("a")].map((a) => a.getAttribute("href")?.slice(1));
    expect(targets).toEqual([
      "qualification", "signals", "structure-selected", "risk-accounting", "invalidation",
    ]);
    for (const id of targets) {
      expect(document.getElementById(id ?? ""), `no panel with id ${id}`).not.toBeNull();
    }
  });
});

describe("the depth panels", () => {
  it("shows counter-evidence rather than only the signals that agreed", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const signals = await screen.findByTestId("signals");
    expect(signals).toHaveTextContent("counter-evidence");
    expect(signals).toHaveTextContent("Breadth is narrowing.");
  });

  it("shows the recomputed maximum loss beside the claimed one", async () => {
    // The governor not taking the structure's word for it is the whole check.
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const checks = await screen.findByTestId("risk-checks");
    expect(checks).toHaveTextContent("max_loss_recomputed");
    expect(checks).toHaveTextContent("recomputed 350.00");
    expect(checks).toHaveTextContent("claimed 350.00");
  });

  it("keeps the classifier's invalidation conditions apart from the memo's", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const panel = await screen.findByTestId("invalidation");
    expect(panel).toHaveTextContent("binding · setups");
    expect(panel).toHaveTextContent("advisory · theses");
  });

  it("names a structure that was rejected, with the reason", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const rejected = await screen.findByTestId("structure-rejected");
    expect(rejected).toHaveAttribute("data-present", "true");
    expect(rejected).toHaveTextContent("max loss exceeds the risk budget");
  });

  it("marks an artifact that belongs to another decision", async () => {
    // Selected-decision isolation: RUI-4's exit requires it to hold throughout,
    // and the receipt in this source describes a different evaluation.
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const lineage = await screen.findByTestId("proof-lineage");
    const receipt = lineage.querySelector('[data-relation="OTHER_DECISION"]');
    expect(receipt).not.toBeNull();
    expect(receipt).toHaveAttribute("data-belongs", "false");
    expect(lineage).toHaveTextContent("a different evaluation of the same snapshot");
  });

  it("offers the manifest as a file, and says how to verify it", async () => {
    // The digest shown is over the bytes the API serves, so the downloaded file
    // hashes to it. A hash nobody is told how to check is decoration.
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const panel = await screen.findByTestId("proof-export");
    const link = screen.getByTestId("proof-download");
    expect(link).toHaveAttribute("href", `/api/v1/proof/${QUALIFIED}.json`);
    expect(link).toHaveAttribute("download");
    expect(panel).toHaveTextContent("sha256:manifest");
    expect(panel).toHaveTextContent("shasum -a 256");
  });

  it("quotes the manifest's own disclosures rather than restating them", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const panel = await screen.findByTestId("proof-export");
    expect(panel).toHaveTextContent("Alpaca Paper only");
    expect(panel).toHaveTextContent("Nothing here is investment advice");
  });

  it("says there is nothing to export when no manifest exists", async () => {
    vi.stubGlobal("fetch", respond(new Set([`/api/v1/decisions/${QUALIFIED}/proof`])));
    render(at(`/decisions/${QUALIFIED}`));
    const panel = await screen.findByTestId("proof-export");
    expect(panel).toHaveAttribute("data-present", "false");
    expect(panel).toHaveTextContent("nothing to export");
  });

  it("says nothing reached the broker when nothing did", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const orders = await screen.findByTestId("lifecycle-orders");
    expect(orders).toHaveAttribute("data-present", "false");
    expect(orders).toHaveTextContent("Nothing reached the broker");
    expect(orders).toHaveTextContent("broker_orders");
  });

  it("renders every panel as an absence for a refusal, never as a blank", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    await screen.findByTestId("trader-summary");
    for (const id of [
      "qualification", "memo", "observation", "signals", "structure-selected",
      "structure-rejected", "risk-accounting", "risk-checks", "invalidation",
      "lifecycle-orders", "lifecycle-position", "lifecycle-exits", "proof-lineage",
    ]) {
      const panel = screen.getByTestId(id);
      expect(panel, `${id} vanished`).toBeInTheDocument();
      expect(panel.querySelector("h3"), `${id} lost its heading`).not.toBeNull();
    }
  });
});


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
