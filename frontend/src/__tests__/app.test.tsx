import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { VIEWS } from "../api/views";
import { App } from "../router";

const DIGEST = "a".repeat(64);

const envelope = <T,>(data: T, over: Record<string, unknown> = {}) => ({
  schema_version: "public.v1",
  source_mode: "LIVE",
  source_id: "live",
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
    decision_id: DIGEST, snapshot_id: "spy-agent-1", instrument: "SPY", outcome: "refusal",
    action: "NO_TRADE", direction: "neutral", reason_codes: ["no_qualified_setup"],
    decided_at: "2026-09-29T19:45:00+00:00", first_decided_at: "2026-09-29T13:45:00+00:00",
    label: "SPY agent 1\nno_qualified_setup", count: 72, member_ids: [],
  }],
  shown: 1, total: 201, grouped: true, pin_missing: false,
  window: 201, window_since: "2026-09-01T13:45:00+00:00", bounded: false,
};

const historyItem = (id: string, at: string) => ({
  decision_id: id, snapshot_id: `spy-agent-${id.slice(0, 4)}`, instrument: "SPY",
  outcome: "refusal", action: "NO_TRADE", direction: "neutral",
  reason_codes: ["no_qualified_setup"], policy_version: "h0-provisional-1", decided_at: at,
});
const historyPage1 = {
  items: [historyItem(DIGEST, "2026-09-29T19:45:00+00:00")],
  next_cursor: "opaque-history-2", total: 2,
};
const historyPage2 = {
  items: [historyItem("c".repeat(64), "2026-09-28T19:45:00+00:00")],
  next_cursor: null, total: 2,
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

// What the server actually returns for a refusal's depth panels: 200 with empty
// records (checked against the demo database, 29 Sep 2026). These used to be
// left unrouted, so the panels were fed failed requests - the PUI-001 mistake.
const refusalMemo = { produced: false, thesis: null, model_call: null };
const refusalStructure = { selected: null, candidates: [] };
const refusalRisk = { decisions: [], accounting: null };
const refusalLifecycle = { ...lifecycle, receipt: lifecycle.receipt, trail: { complete: true, gaps: [], events: [] } };
const refusalProof = { manifest_digest: "sha256:refusal-manifest", manifest: { manifest_version: "proof-manifest-2", disclosures: [] } };

const routes: Record<string, unknown> = {
  "/api/v1/system/status": envelope(status),
  "/api/v1/system/proof": envelope(tiles),
  "/api/v1/decisions/grouped": envelope(listing),
  "/api/v1/outcomes": envelope(review),
  "/api/v1/tour": envelope(scenes),
  [`/api/v1/decisions/${DIGEST}/summary`]: envelope(summary),
  [`/api/v1/decisions/${DIGEST}/market`]: envelope(market),
  [`/api/v1/decisions/${DIGEST}/outcomes`]: envelope(horizons),
  [`/api/v1/decisions/${DIGEST}/memo`]: envelope(refusalMemo),
  [`/api/v1/decisions/${DIGEST}/structure`]: envelope(refusalStructure),
  [`/api/v1/decisions/${DIGEST}/risk`]: envelope(refusalRisk),
  [`/api/v1/decisions/${DIGEST}/lifecycle`]: envelope(refusalLifecycle),
  [`/api/v1/decisions/${DIGEST}/proof`]: envelope(refusalProof),
  [`/api/v1/decisions/${QUALIFIED}/summary`]: envelope(qualifiedSummary),
  [`/api/v1/decisions/${QUALIFIED}/market`]: envelope(qualifiedMarket),
  [`/api/v1/decisions/${QUALIFIED}/memo`]: envelope(memo),
  [`/api/v1/decisions/${QUALIFIED}/structure`]: envelope(structure),
  [`/api/v1/decisions/${QUALIFIED}/risk`]: envelope(risk),
  [`/api/v1/decisions/${QUALIFIED}/lifecycle`]: envelope(lifecycle),
  [`/api/v1/decisions/${QUALIFIED}/proof`]: envelope(proof),
  [`/api/v1/decisions/${QUALIFIED}/outcomes`]: envelope(horizons),
  "/api/v1/decisions?outcome=refusal&limit=50&cursor=opaque-history-2": envelope(historyPage2),
  "/api/v1/decisions?": envelope(historyPage1),
  "/api/v1/activity?cursor=opaque-page-2": envelope(activityPage2),
  "/api/v1/activity": envelope(activityPage1),
  "/api/v1/incidents?state=open": envelope(incidentsOpen),
  "/api/v1/incidents?state=all": envelope(incidentsAll),
  "/api/v1/worker/events": envelope(workerEvents),
};

function respond(
  failing: Set<string> = new Set(),
  over: Record<string, unknown> = {},
  statuses: Record<string, number> = {},
  pending: Set<string> = new Set(),
) {
  const map = { ...routes, ...over };
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    // Longest match first: /decisions/{d}/outcomes must not be served by /outcomes.
    const key = Object.keys(map).sort((a, b) => b.length - a.length).find((k) => url.startsWith(k));
    if (key && pending.has(key)) return new Promise<Response>(() => undefined);
    if (key && statuses[key] !== undefined) {
      const code = statuses[key];
      return Promise.resolve({
        ok: false, status: code, statusText: code === 404 ? "Not Found" : "Server Error",
        json: () => Promise.resolve({ detail: "x" }),
      } as Response);
    }
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

describe("a decision is addressable", () => {
  it("opens from its own URL without going through the list", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    expect(await screen.findByTestId("decision-ticket")).toHaveTextContent("spy-agent-1");
  });

  it("is reachable by following the list", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: /SPY.*No trade/ }));
    await waitFor(() => expect(screen.getByTestId("decision-ticket")).toBeInTheDocument());
  });

  it("says so when the source holds no such decision", async () => {
    vi.stubGlobal("fetch", respond(new Set(), {}, { [`/api/v1/decisions/${DIGEST}/summary`]: 404 }));
    render(at(`/decisions/${DIGEST}`));
    expect(await screen.findByTestId("decision-missing")).toBeInTheDocument();
  });

  it("does not call a failed request a missing decision (PUI-001)", async () => {
    for (const fetcher of [
      respond(new Set([`/api/v1/decisions/${DIGEST}/summary`])),
      respond(new Set(), {}, { [`/api/v1/decisions/${DIGEST}/summary`]: 500 }),
    ]) {
      vi.stubGlobal("fetch", fetcher);
      const { unmount } = render(at(`/decisions/${DIGEST}`));
      expect(await screen.findByTestId("decision-unavailable")).toHaveTextContent("not a missing record");
      expect(screen.queryByTestId("decision-missing")).toBeNull();
      unmount();
    }
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
    expect(five).toHaveTextContent("bull_call_debit_spread ×1, debit 3.500000 per share");
    expect(five).toHaveTextContent("$350.000000 of a $750.000000 budget");
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

  it("says the proof is unavailable when its request fails, not that nothing exists", async () => {
    // The server returns a manifest for every decision it holds, so "nothing to
    // export" was only ever reachable through a failed request (PUI-003).
    vi.stubGlobal("fetch", respond(new Set([`/api/v1/decisions/${QUALIFIED}/proof`])));
    render(at(`/decisions/${QUALIFIED}`));
    const state = await screen.findByText(/proof lineage unavailable/);
    expect(state).toHaveTextContent("not an empty record");
    expect(screen.queryByTestId("proof-export")).toBeNull();
    expect(screen.queryByText(/nothing to export/)).toBeNull();
    // The other panels are unaffected by one panel's failure.
    expect(await screen.findByTestId("risk-accounting")).toBeInTheDocument();
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

describe("the decision views", () => {
  const requested = (fetchMock: ReturnType<typeof respond>) =>
    fetchMock.mock.calls
      .map(([input]) => String(input))
      .filter((u) => u.includes("/decisions/grouped") || u.startsWith("/api/v1/decisions?"));

  it("asks for the Notable view by default", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions"));
    await screen.findByTestId("decision-list");
    expect(requested(fetchMock)).toEqual(["/api/v1/decisions/grouped?view=Notable"]);
  });

  it("honours a link shared before the list moved (/?view=…), and marks it current", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/?view=Refusals"));
    await screen.findByTestId("decision-list");
    // An ungrouped view pages the full history (PUI-008), filtered on the server.
    expect(requested(fetchMock)).toEqual(["/api/v1/decisions?outcome=refusal&limit=50"]);
    const nav = screen.getByRole("navigation", { name: "Decision views" });
    const current = nav.querySelector('[aria-current="page"]');
    expect(current).toHaveTextContent("Refusals");
  });

  it("treats an unknown view as the default rather than sending it", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions?view=Bogus"));
    await screen.findByTestId("decision-list");
    expect(requested(fetchMock)).toEqual(["/api/v1/decisions/grouped?view=Notable"]);
  });

  it("offers every view as a shareable link", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const nav = await screen.findByRole("navigation", { name: "Decision views" });
    const links = [...nav.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")]);
    expect(links).toEqual([
      ["Notable", "/decisions"],
      ["Positions", "/decisions?view=Positions"],
      ["Refusals", "/decisions?view=Refusals"],
      ["Everything", "/decisions?view=Everything"],
    ]);
  });

  it("offers exactly the views the server accepts", () => {
    interface Spec {
      paths: Record<string, { get: { parameters: { name: string; schema: { pattern?: string } }[] } }>;
    }
    // jsdom gives import.meta.url an http: scheme; the suite runs from frontend/.
    const spec = JSON.parse(readFileSync(`${process.cwd()}/openapi.json`, "utf8")) as Spec;
    const param = spec.paths["/api/v1/decisions/grouped"]?.get.parameters.find((p) => p.name === "view");
    const pattern = param?.schema.pattern ?? "";
    const server = /^\^\((.*)\)\$$/.exec(pattern)?.[1]?.split("|");
    expect(server, "the view parameter must carry an enumerating pattern").toBeDefined();
    expect([...VIEWS]).toEqual(server);
  });
});

// PUI Phase 1 (docs/improvements/options_alpha_personal_ui_redesign_v0_1.md):
// no failed or unanswered request may render an invented zero, a healthy
// state, or a business absence.
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

  it("states a verified quiet, dated, only when both sources answered", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const quiet = await screen.findByTestId("attention-quiet");
    expect(quiet).toHaveTextContent("no incident is open and the worker has recorded no fault");
    expect(quiet).toHaveTextContent(/Checked \d{4}-\d\d-\d\d/);
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

  it("offers Today, Decisions, Activity and Evidence", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/"));
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect([...nav.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      "/", "/decisions", "/activity", "/evidence",
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
    history.back();
    const nav = await screen.findByRole("navigation", { name: "Decision views" });
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent("Refusals");
  });
});

describe("the decision workflow (PUI phase 3)", () => {
  it("lists a decision by instrument, outcome, reason and New York time, not by snapshot ID", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const row = await screen.findByRole("link", { name: /SPY.*No trade/ });
    expect(row).toHaveTextContent("no qualified setup");
    // A run of 72 spans its first and last member, in ET with the zone named.
    expect(row).toHaveTextContent("Tue, Sep 29, 2026, 09:45–15:45 ET");
    expect(row).toHaveTextContent("×72");
    expect(row).not.toHaveTextContent("spy-agent-1");
    expect(row.querySelector("time")).toHaveAttribute("dateTime", "2026-09-29T19:45:00+00:00");
  });

  it("states the grouping window, and says nothing is outside it when nothing is", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const scope = await screen.findByTestId("decision-scope");
    expect(scope).toHaveTextContent("1 entry for the newest 201 of 201 decisions, since Tue, Sep 1, 2026");
    expect(scope).not.toHaveTextContent("outside this window");
  });

  it("says how many decisions a bounded window leaves out and links the full history", async () => {
    // 29 Sep 2026: Notable grouped 400 of 718 and read as the whole history.
    vi.stubGlobal("fetch", respond(new Set(), {
      "/api/v1/decisions/grouped": envelope({ ...listing, total: 718, window: 400, bounded: true }),
    }));
    render(at("/decisions"));
    const scope = await screen.findByTestId("decision-scope");
    expect(scope).toHaveTextContent("newest 400 of 718 decisions");
    expect(scope).toHaveTextContent("318 older decisions are outside this window.");
    expect(within(scope).getByRole("link", { name: "Browse the full history" }))
      .toHaveAttribute("href", "/decisions?view=Everything");
  });

  it("pages the full history on the server's cursor and holds still while browsing", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions?view=Refusals"));
    expect(await screen.findByTestId("decision-scope")).toHaveTextContent("1 of 2 decisions");
    await userEvent.click(screen.getByTestId("history-more"));
    expect(await screen.findByTestId("history-end")).toHaveTextContent("The history ends here.");
    expect(screen.getByTestId("decision-scope")).toHaveTextContent("2 of 2 decisions");
    expect(screen.getAllByRole("link", { name: /SPY.*No trade/ })).toHaveLength(2);
    // The cursor is passed back exactly as served, never built.
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain(
      "/api/v1/decisions?outcome=refusal&limit=50&cursor=opaque-history-2",
    );
    expect(screen.getByTestId("history-newest")).toBeInTheDocument();
  });

  it("says a failed history request failed rather than that there are no decisions", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/decisions?"])));
    render(at("/decisions?view=Everything"));
    expect(await screen.findByText(/unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/holds no/)).toBeNull();
  });

  it("opens with a concise summary, then three linked sections", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const ticket = await screen.findByTestId("decision-ticket");
    expect(ticket).toHaveTextContent("Opened a Paper position");
    expect(ticket).not.toHaveTextContent("sha256:");
    const nav = screen.getByRole("navigation", { name: "Decision sections" });
    expect([...nav.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      "#setup", "#execution", "#evidence",
    ]);
    const setup = screen.getByTestId("part-setup");
    await waitFor(() => expect(within(setup).getByTestId("structure-selected")).toBeInTheDocument());
    expect(within(setup).getByTestId("structure-reading")).toBeInTheDocument();
    expect(within(setup).getByTestId("risk-accounting")).toBeInTheDocument();
    expect(within(screen.getByTestId("part-execution")).getByTestId("lifecycle-orders")).toBeInTheDocument();
    const evidence = screen.getByTestId("part-evidence");
    expect(within(evidence).getByTestId("memo")).toBeInTheDocument();
    expect(within(evidence).getByTestId("identifiers")).toHaveTextContent(`sha256:${QUALIFIED}`);
    expect(within(evidence).getByTestId("horizons")).toHaveTextContent("not the position's profit or loss");
  });

  it("calls a refusal a valid outcome, with its reason in words", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const ticket = await screen.findByTestId("decision-ticket");
    // This fixture records no observation: the instrument is said to be missing, not guessed.
    expect(ticket).toHaveTextContent("Instrument not recorded · No trade");
    expect(ticket).toHaveTextContent("No trade: no qualified setup");
    expect(ticket).toHaveTextContent("a valid outcome, not a system error");
  });

  it("never answers 'why this structure' with a candidate that was not selected", async () => {
    const fallback = { ...structure.candidates[0], selected: false };
    vi.stubGlobal("fetch", respond(new Set(), {
      [`/api/v1/decisions/${QUALIFIED}/structure`]: envelope({ selected: fallback, candidates: [fallback] }),
    }));
    render(at(`/decisions/${QUALIFIED}`));
    const five = await screen.findByTestId("trader-summary");
    const row = within(five).getByRole("link", { name: "Why this structure" }).closest("div");
    expect(row).toHaveAttribute("data-answered", "false");
    expect(five).not.toHaveTextContent("SPY260911C00790000");
  });

  it("labels money with its unit", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const selected = await screen.findByTestId("structure-selected");
    expect(selected).toHaveTextContent("per share, as quoted; a contract is 100 shares");
    expect(selected).toHaveTextContent("$350.000000");
    expect(screen.getByTestId("risk-accounting")).toHaveTextContent("USD, whole structure");
  });
});
