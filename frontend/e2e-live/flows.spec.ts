import { createHash } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

/**
 * The main flows, against a live deployment. Every test also fails on any API
 * error response and on any console error: a page that renders while a panel
 * quietly failed to load is the failure this suite exists to catch.
 */
function watch(page: Page): { failures: string[] } {
  const failures: string[] = [];
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 400) failures.push(`${r.status()} ${r.url()}`);
  });
  page.on("console", (m) => {
    if (m.type() === "error") failures.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));
  return { failures };
}

async function firstDecision(page: Page): Promise<string> {
  await page.goto("/decisions");
  const link = page.getByTestId("decision-list").locator('a[href^="/decisions/"]').first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  const digest = /\/decisions\/([0-9a-f]{64})/.exec(href ?? "")?.[1];
  expect(digest, "the list links decisions by digest").toBeTruthy();
  return digest!;
}

test("today: status, attention and the latest decision render from live records", async ({ page }) => {
  const { failures } = watch(page);
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("source-banner")).toBeVisible();
  await expect(page.getByTestId("status-strip")).toBeVisible();
  // Settled one way or the other: a quiet statement or a list, never loading.
  await expect(page.getByTestId("attention")).not.toContainText("Loading");
  await expect(page.getByTestId("latest-ticket")).toBeVisible();
  await expect(page.getByTestId("latest-decision").locator('a[href^="/decisions/"]')).toBeVisible();
  expect(failures).toEqual([]);
});

test("evidence: proof tiles render, and old links reach their new pages", async ({ page }) => {
  const { failures } = watch(page);
  await page.goto("/evidence");
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("proof-tiles")).toBeVisible();
  // Links shared before the redesign keep working (PUI Phase 2).
  await page.goto("/?view=Everything");
  await expect(page).toHaveURL(/\/decisions\?view=Everything/);
  await page.goto("/?tour=1");
  await expect(page).toHaveURL(/\/evidence\?tour=1/);
  expect(failures).toEqual([]);
});

test("decision: the ticket, its depth panels and its authority spine render", async ({ page }) => {
  const { failures } = watch(page);
  const digest = await firstDecision(page);
  await page.getByTestId("decision-list").locator(`a[href="/decisions/${digest}"]`).first().click();
  await expect(page).toHaveURL(new RegExp(`/decisions/${digest}`));
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("decision-ticket")).toBeVisible();
  await expect(page.getByTestId("authority-spine")).toBeVisible();
  await expect(page.getByTestId("why-decision")).toBeVisible();
  expect(failures).toEqual([]);
});

test("decision: a deep link survives a fresh load (server-side fallback)", async ({ page }) => {
  const { failures } = watch(page);
  const digest = await firstDecision(page);
  await page.goto(`/decisions/${digest}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("decision-ticket")).toBeVisible();
  expect(failures).toEqual([]);
});

test("export: the manifest downloads and hashes to the digest the page shows", async ({ page, request }) => {
  const { failures } = watch(page);
  const digest = await firstDecision(page);
  await page.goto(`/decisions/${digest}`);
  await page.waitForLoadState("networkidle");
  const link = page.getByTestId("proof-download");
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  const body = await (await request.get(href!)).body();
  const sha = createHash("sha256").update(body).digest("hex");
  // The page tells the reader what the file should hash to; hold it to that.
  await expect(page.getByTestId("proof-export")).toContainText(sha);
  expect(failures).toEqual([]);
});

test("tour: the guided scenes render and step forward", async ({ page }) => {
  const { failures } = watch(page);
  await page.goto("/evidence?tour=1");
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("tour-card")).toBeVisible();
  await page.goto("/evidence?tour=2");
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("tour-card")).toBeVisible();
  expect(failures).toEqual([]);
});

test("activity: the durable feed renders", async ({ page }) => {
  const { failures } = watch(page);
  await page.goto("/activity");
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("activity-count")).toBeVisible();
  expect(failures).toEqual([]);
});

test("the boundary: unknown API paths 404, writes are refused", async ({ request }) => {
  expect((await request.get("/api/v1/no-such-route")).status()).toBe(404);
  for (const method of ["post", "put", "delete"] as const) {
    expect((await request[method]("/api/v1/decisions")).status(), method).toBe(405);
  }
});

test("views: switching the decision view changes the list and the URL", async ({ page }) => {
  const { failures } = watch(page);
  await page.goto("/decisions");
  await page.waitForLoadState("networkidle");
  const nav = page.getByRole("navigation", { name: "Decision views" });
  await expect(nav.locator('[aria-current="page"]')).toHaveText("Notable");
  const notable = await page.getByTestId("decision-list").locator("li").count();

  await nav.getByRole("link", { name: "Everything" }).click();
  await expect(page).toHaveURL(/\?view=Everything/);
  await page.waitForLoadState("networkidle");
  await expect(nav.locator('[aria-current="page"]')).toHaveText("Everything");
  const everything = await page.getByTestId("decision-list").locator("li").count();
  // On live data the default view groups most decisions away; Everything must
  // show at least as many rows, or the control changes nothing.
  expect(everything).toBeGreaterThanOrEqual(notable);

  // The view survives a fresh load: it lives in the URL, so it can be shared.
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(nav.locator('[aria-current="page"]')).toHaveText("Everything");
  expect(failures).toEqual([]);
});
