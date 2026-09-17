import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";

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

/** Routes the gate walks: the overview, two tour steps, activity, and every decision. */
export const routes = [
  "/",
  "/?tour=1",
  "/?tour=4",
  "/activity",
  ...digests.map((d) => `/decisions/${d}`),
];

export const names = [
  "overview",
  "tour-1",
  "tour-4",
  "activity",
  ...digests.map((d) => `decision-${d.slice(0, 12)}`),
];

/** Every cursor the fixtures hand out, so a client-invented one is detectable. */
export const servedCursors: string[] = Object.entries(captured)
  .filter(([path]) => path.startsWith("/api/v1/activity"))
  .map(([, body]) => (body as { data?: { next_cursor?: string | null } }).data?.next_cursor)
  .filter((cursor): cursor is string => typeof cursor === "string");
