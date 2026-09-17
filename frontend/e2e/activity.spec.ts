import { expect, test } from "@playwright/test";
import { replayApi, servedCursors } from "./fixtures";

/**
 * The audit feed, paged the way the server says and no other way.
 *
 * `RUI-VAL-004` found that `audit_events.sequence` restarts at zero for every
 * decision, so a cursor built from it would skip or repeat most of a feed that
 * spans decisions. The fixtures deliberately page seven at a time — the whole
 * corpus fits one default page, so a default-limit fixture would exercise none
 * of this.
 */
test("pages the whole feed without inventing a cursor", async ({ page }) => {
  await replayApi(page);

  const requested: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/activity") requested.push(url.searchParams.get("cursor") ?? "");
  });

  await page.goto("/activity");
  await page.waitForLoadState("networkidle");

  const more = page.getByTestId("activity-more");
  let clicks = 0;
  while ((await more.count()) > 0 && clicks < 20) {
    await more.click();
    await page.waitForTimeout(150);
    clicks += 1;
  }

  const rows = await page.evaluate(() =>
    [...document.querySelectorAll('[data-testid="activity"] tbody tr')].map(
      (row) =>
        [...row.querySelectorAll("td")]
          .slice(0, 3)
          .map((cell) => cell.textContent)
          .join("|"),
    ),
  );

  // Every event exactly once, which is the assertion a sequence cursor fails.
  expect(rows.length).toBe(26);
  expect(new Set(rows).size, "an event was shown twice").toBe(26);
  expect(clicks, "the feed never paged").toBeGreaterThan(0);

  // Every cursor sent was one the server handed out; the first request sends none.
  const sent = requested.filter((cursor) => cursor !== "");
  expect(sent.length).toBeGreaterThan(0);
  for (const cursor of sent) {
    expect(servedCursors, `client sent a cursor the server never issued: ${cursor}`).toContain(cursor);
  }

  await expect(page.getByTestId("activity-count")).toContainText("the feed ends here");
  await expect(more).toHaveCount(0);
});

test("tells an empty source apart from one that cannot answer", async ({ page }) => {
  // `available: true` with no items means the source works and holds nothing.
  // `available: false` carries a reason and is not an empty feed.
  await replayApi(page);
  await page.goto("/activity");
  await page.waitForLoadState("networkidle");

  const worker = page.getByTestId("worker-events");
  await expect(worker).toHaveAttribute("data-present", "false");
  await expect(worker).toContainText("holds no worker events");

  const incidents = page.getByTestId("incidents");
  await expect(incidents).toHaveAttribute("data-present", "false");
  // An empty open list must read as the source answering, not a filter hiding.
  await expect(incidents).toContainText("This is the source answering");
});

test("keeps the incident filter usable when the list is empty", async ({ page }) => {
  await replayApi(page);
  await page.goto("/activity");
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("incidents-open")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("incidents-all").click();
  await expect(page.getByTestId("incidents-all")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("incidents")).toContainText("No incident has ever been recorded");
});
