import { createMemoryHistory } from "@tanstack/react-router";
import { vi } from "vitest";
import { App } from "../router";

/**
 * Shared fixtures for the application's component tests.
 *
 * `CSA-010`: these lived at the top of one 1,100-line `app.test.tsx` that held
 * every screen's tests. The tests are now one file per screen; the recorded
 * envelopes, the route table and the fetch stub they share live here. Nothing
 * in this file is a test.
 */

export const DIGEST = "a".repeat(64);

export const envelope = <T,>(data: T, over: Record<string, unknown> = {}) => ({
  schema_version: "public.v1",
  source_mode: "LIVE",
  source_id: "live",
  source_label: "live worker database (201 decisions)",
  observed_at: "2026-09-17T08:00:00+00:00",
  correlation_id: null,
  data,
  ...over,
});

export const status = [
  { label: "Order writes", value: "DISABLED", tone: "ok", known: true,
    source: "runs.trading_enabled", observed_at: null, reason: null },
  { label: "Worker", value: "UNKNOWN", tone: "unknown", known: false,
    source: "worker_leases", observed_at: null, reason: "no lease row" },
];

export const listing = {
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

export const historyItem = (id: string, at: string) => ({
  decision_id: id, snapshot_id: `spy-agent-${id.slice(0, 4)}`, instrument: "SPY",
  outcome: "refusal", action: "NO_TRADE", direction: "neutral",
  reason_codes: ["no_qualified_setup"], policy_version: "h0-provisional-1", decided_at: at,
});
export const historyPage1 = {
  items: [historyItem(DIGEST, "2026-09-29T19:45:00+00:00")],
  next_cursor: "opaque-history-2", total: 2,
};
export const historyPage2 = {
  items: [historyItem("c".repeat(64), "2026-09-28T19:45:00+00:00")],
  next_cursor: null, total: 2,
};

export const summary = {
  decision_id: DIGEST, snapshot_id: "spy-agent-1", action: "NO_TRADE", direction: "neutral",
  reason_codes: ["no_qualified_setup"], input_hash: "sha256:in",
  decision_hash: `sha256:${DIGEST}`, policy_version: "h0-provisional-1",
  decided_at: "2026-09-17T14:00:00+00:00", observation: null,
  reached_the_broker: false, model_was_called: false,
  why: [{ stage: "01 evidence", text: "no setup qualified", source: "evidence_packs", present: true }],
};

export const market = {
  observation: null, observation_kind: "provider", signals: [], qualification: null,
  structure: {
    gate: "separation_or_side", bars_considered: 120, bars_required: 70,
    fast_ema: "640.100000", slow_ema: "639.900000", separation: "0.00031250",
    last_close: "640.500000", close_side: "above", retest_touched: null,
    separation_shortfall: "-0.00168750",
  },
};

export const horizons = [
  { horizon: "T+1", sessions: 1, state: "COMPLETE", resolved: true,
    underlying_at_decision: "640.50", underlying_at_horizon: "646.00", change: "5.50",
    direction_agreed: null, realized: null, observed_snapshot_id: "spy-agent-2" },
  { horizon: "T+3", sessions: 3, state: "PENDING", resolved: false,
    underlying_at_decision: null, underlying_at_horizon: null, change: null,
    direction_agreed: null, realized: null, observed_snapshot_id: null },
];

export const tiles = [
  { value: "0", label: "reconciled Paper lifecycles", mode: "UNAVAILABLE", available: false,
    source: "positions joined through decisions", detail: "no position has both ends" },
];

export const review = {
  horizons: [], decisions: 201, decisions_reviewed: 136, positions_ever: 0,
  resolved: 160, pending: 242,
  caveat: "All 136 reviewed decisions are refusals: no position has ever been opened.",
};

export const scenes = [
  { number: 1, title: "What was observed", narration: "The system reads a completed close.",
    tab: 0, snapshot_id: "spy-qualified-2026-08-27", decision_id: DIGEST },
  { number: 2, title: "A case this source lacks", narration: "Never shown.",
    tab: 0, snapshot_id: "spy-lifecycle-2026", decision_id: null },
];

// RUI-4. A second decision that qualified, so the depth panels have records;
// DIGEST stays a refusal, which is the case that must keep rendering absences.
export const QUALIFIED = "b".repeat(64);

export const qualifiedSummary = {
  ...summary, decision_id: QUALIFIED, snapshot_id: "spy-qualified-1",
  action: "OPTIONS_POSITION", direction: "bullish", reason_codes: [],
  decision_hash: `sha256:${QUALIFIED}`, model_was_called: true, reached_the_broker: false,
};

export const qualifiedMarket = {
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

export const memo = {
  produced: true,
  thesis: {
    synthesizer_name: "deterministic_baseline_v0", direction: "bullish", confidence: "0.7050",
    evidence_ids: ["sig-structure"], counter_evidence_ids: ["sig-breadth"],
    invalidation_conditions: ["close below 759.53 invalidates the retest"],
    reasoning_summary: "Deterministic baseline: qualified bullish from 1 aligned signal.",
  },
  model_call: null,
};

export const structure = {
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

export const risk = {
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

export const lifecycle = {
  reached_the_broker: false, intents: [], orders: [], positions: [], exits: [],
  trail: { complete: true, gaps: [], events: [] },
  receipt: { relation: "OTHER_DECISION", belongs: false, matched_on: "decision_hash",
    reason: "this receipt records a different evaluation of the same snapshot", facts: {} },
  ablation: { relation: "NOT_DECISION_SCOPED", belongs: false, matched_on: null,
    reason: "a corpus-level result over 5 frozen cases", facts: {} },
};

export const proof = {
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
export const activityPage1 = {
  items: [
    { correlation_id: "spy-agent-1", sequence: 2, stage: "DECIDED", outcome: "NO_TRADE",
      component: "decision_workflow", reason_codes: ["no_qualified_setup"],
      occurred_at: "2026-09-17T14:00:01+00:00", refused: true },
  ],
  next_cursor: "opaque-page-2",
};

export const activityPage2 = {
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

export const incidentsOpen: unknown[] = [];
export const incidentsAll = [
  { kind: "broker_timeout", severity: "warning", execution_state: "RECONCILING",
    opened_at: "2026-09-16T10:00:00+00:00", resolved_at: "2026-09-16T10:05:00+00:00",
    open: false, withheld: ["detail"] },
];

export const workerEvents = { available: true, reason: null, items: [] };

// What the server actually returns for a refusal's depth panels: 200 with empty
// records (checked against the demo database, 29 Sep 2026). These used to be
// left unrouted, so the panels were fed failed requests - the PUI-001 mistake.
export const refusalMemo = { produced: false, thesis: null, model_call: null };
export const refusalStructure = { selected: null, candidates: [] };
export const refusalRisk = { decisions: [], accounting: null };
export const refusalLifecycle = { ...lifecycle, receipt: lifecycle.receipt, trail: { complete: true, gaps: [], events: [] } };
export const refusalProof = { manifest_digest: "sha256:refusal-manifest", manifest: { manifest_version: "proof-manifest-2", disclosures: [] } };

export const routes: Record<string, unknown> = {
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

export function respond(
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

export const at = (path: string) => <App history={createMemoryHistory({ initialEntries: [path] })} />;
