/**
 * Freeze the real API's responses so the browser gate needs no server.
 *
 * The frontend CI job deliberately runs without Python and without a database;
 * its types come from the committed OpenAPI document for exactly that reason.
 * The browser gate keeps that property by replaying these envelopes instead of
 * standing the API up, and freezing `observed_at` is what makes a screenshot
 * diff mean "the page changed" rather than "time passed".
 *
 * Run against a local API serving the committed evidence:
 *   python -m options_alpha_lab.api &   # port 8600
 *   pnpm fixtures:capture
 */
import { writeFileSync } from "node:fs";

const API = process.env.API_BASE ?? "http://127.0.0.1:8600";
/** Any fixed instant. It is displayed, so it must not move between runs. */
const FROZEN = "2026-09-17T12:00:00+00:00";

async function envelope(path) {
  const response = await fetch(API + path, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`${path} -> ${response.status} ${response.statusText}`);
  const body = await response.json();
  // `correlation_id` is a decision hash where present, so it is left alone.
  return { ...body, observed_at: FROZEN };
}

const paths = [
  "/api/v1/system/status",
  "/api/v1/system/proof",
  "/api/v1/outcomes",
  "/api/v1/tour",
  "/api/v1/copy",
  "/api/v1/decisions/grouped?view=Notable",
];

const captured = {};
for (const path of paths) captured[path] = await envelope(path);

// Every decision the listing offers, so each ticket renders from a record.
const walk = (node, out = []) => {
  if (Array.isArray(node)) node.forEach((n) => walk(n, out));
  else if (node && typeof node === "object") {
    if (typeof node.decision_id === "string") out.push(node.decision_id);
    Object.values(node).forEach((n) => walk(n, out));
  }
  return out;
};

const digests = [...new Set(walk(captured["/api/v1/decisions/grouped?view=Notable"].data))];
for (const digest of digests) {
  for (const leaf of ["summary", "market", "outcomes"]) {
    const path = `/api/v1/decisions/${digest}/${leaf}`;
    captured[path] = await envelope(path);
  }
}

writeFileSync("fixtures/api.json", JSON.stringify(captured, null, 1) + "\n");
console.log(`captured ${Object.keys(captured).length} responses for ${digests.length} decisions`);
