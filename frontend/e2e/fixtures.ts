import { readFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";

type Captured = Record<string, unknown>;

const captured = JSON.parse(
  readFileSync(new URL("../fixtures/api.json", import.meta.url), "utf8"),
) as Captured;

/** Decision digests the listing offers, in the order it offers them. */
export const digests: string[] = [
  ...new Set(
    Object.keys(captured)
      .map((path) => /^\/api\/v1\/decisions\/([0-9a-f]{64})\/summary$/.exec(path)?.[1])
      .filter((d): d is string => typeof d === "string"),
  ),
];

/**
 * Serve the frozen envelopes. An unrecognised path fails loudly rather than
 * 404ing quietly: a page that renders its own error state would otherwise scan
 * clean and screenshot consistently while showing nothing.
 */
export async function replayApi(page: Page): Promise<string[]> {
  const missed: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname + new URL(route.request().url()).search;
    const body = captured[path];
    if (body === undefined) {
      missed.push(path);
      return route.fulfill({ status: 599, body: "no fixture" });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  return missed;
}

/** Routes the gate walks: Today, the list, the full history, Evidence with two tour steps, activity, and every decision. */
export const routes = [
  "/",
  "/decisions",
  "/decisions?view=Everything",
  "/evidence",
  "/evidence?tour=1",
  "/evidence?tour=4",
  "/activity",
  "/review",
  ...digests.map((d) => `/decisions/${d}`),
];

export const names = [
  "today",
  "decisions",
  "history",
  "evidence",
  "tour-1",
  "tour-4",
  "activity",
  "review",
  ...digests.map((d) => `decision-${d.slice(0, 12)}`),
];

/** Every cursor the fixtures hand out, so a client-invented one is detectable. */
export const servedCursors: string[] = Object.entries(captured)
  .filter(([path]) => path.startsWith("/api/v1/activity"))
  .map(([, body]) => (body as { data?: { next_cursor?: string | null } }).data?.next_cursor)
  .filter((cursor): cursor is string => typeof cursor === "string");

/**
 * Wait until the page has finished answering, not merely gone quiet.
 *
 * `networkidle` alone is not that: it can pass between two of a page's
 * requests, and a client-side navigation does not reset it. A decision page
 * makes eight requests, and on 5 October 2026 a screenshot was taken with one
 * panel still loading (about 1% of pixels different; it passed on rerun). The
 * app marks every unanswered panel, so the wait is for none to remain.
 */
export async function settled(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  await expect(
    page.locator('[data-state="loading"], [data-testid="decision-loading"]'),
  ).toHaveCount(0);
}
