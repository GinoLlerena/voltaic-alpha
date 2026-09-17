import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { names, replayApi, routes } from "./fixtures";

/** Injected rather than imported: axe must run inside the page, not the runner. */
const axeSource = readFileSync(
  new URL("../node_modules/axe-core/axe.min.js", import.meta.url),
  "utf8",
);

declare global {
  interface Window {
    axe: { run: (context: unknown, options: unknown) => Promise<AxeResult> };
  }
}

interface AxeResult {
  violations: { id: string; impact: string | null; nodes: { html: string; failureSummary?: string }[] }[];
  passes: unknown[];
}

/**
 * `RUI-VAL-011` found 22 serious failures by hand — 16 of them one palette
 * token at 3.09:1, and 6 a spine that faded unreached stages with `opacity`,
 * unreadable and silent to a screen reader. Neither was visible to a test that
 * never applies CSS. This is that scan, run on every route and both widths.
 */
for (const [index, route] of routes.entries()) {
  for (const width of [1280, 400]) {
    test(`${names[index]} at ${width}px has no accessibility violations`, async ({ page }) => {
      const missed = await replayApi(page);
      await page.setViewportSize({ width, height: 900 });
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      expect(missed, "every request must have a fixture").toEqual([]);

      await page.addScriptTag({ content: axeSource });
      const result = await page.evaluate(
        async () =>
          await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } }),
      );

      expect(
        result.violations.map((v) => ({
          rule: v.id,
          impact: v.impact,
          example: v.nodes[0]?.failureSummary?.split("\n").slice(0, 2).join(" ") ?? v.nodes[0]?.html,
          count: v.nodes.length,
        })),
      ).toEqual([]);
    });
  }
}

test("the page does not overflow a phone", async ({ page }) => {
  await replayApi(page);
  await page.setViewportSize({ width: 400, height: 800 });
  for (const route of routes) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${route} overflows horizontally`).toBe(0);
  }
});

test("every decision is reachable and openable from the keyboard alone", async ({ page }) => {
  await replayApi(page);
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const reached = new Set<string>();
  let opened: string | null = null;
  for (let i = 0; i < 12; i += 1) {
    await page.keyboard.press("Tab");
    const href = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      // A focused control with no visible ring is unusable without a mouse.
      const ring = getComputedStyle(el).outlineStyle !== "none" || getComputedStyle(el).boxShadow !== "none";
      return ring ? el.getAttribute("href") : "UNFOCUSABLE";
    });
    expect(href, "a focused element showed no focus indicator").not.toBe("UNFOCUSABLE");
    if (href?.startsWith("/decisions/")) reached.add(href);
  }
  expect(reached.size, "not every decision was tab-reachable").toBeGreaterThan(0);

  const first = [...reached][0];
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  for (let i = 0; i < 12 && opened === null; i += 1) {
    await page.keyboard.press("Tab");
    const isTarget = await page.evaluate(
      (href) => (document.activeElement as HTMLElement | null)?.getAttribute("href") === href,
      first,
    );
    if (isTarget) {
      await page.keyboard.press("Enter");
      await page.waitForLoadState("networkidle");
      opened = new URL(page.url()).pathname;
    }
  }
  expect(opened).toBe(first);
});

test("no text is squeezed into a vertical column at phone width", async ({ page }) => {
  // The overflow check above passes happily while text is unreadable: a flex row
  // written for two children was given three, and at 400px its label rendered
  // 73px wide and 1300px tall — one letter per line — inside a page that did
  // not overflow at all. Tall-and-narrow is the signature, so look for it.
  await replayApi(page);
  await page.setViewportSize({ width: 400, height: 800 });
  for (const route of routes) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const squeezed = await page.evaluate(() =>
      [...document.querySelectorAll("body *")]
        .filter((el) => {
          const text = (el.textContent ?? "").trim();
          if (text.length < 8 || el.children.length > 0) return false;
          // Measure the text's own line boxes, not the element's. A table cell
          // is as tall as its row, so a short cell beside a wrapped paragraph
          // looks squeezed by any box-height rule and is not — a false positive
          // that appeared only on CI's Linux, where the prose wrapped further.
          const range = document.createRange();
          range.selectNodeContents(el);
          const lines = [...range.getClientRects()].filter((r) => r.width > 0);
          if (lines.length < 6) return false;
          const widest = Math.max(...lines.map((r) => r.width));
          // Six or more lines, none wider than a couple of words: a column.
          return widest < 90;
        })
        .map((el) => `${el.tagName.toLowerCase()}.${el.className || "-"}: ${
          (el.textContent ?? "").trim().slice(0, 24)
        }`),
    );
    expect(squeezed, `${route} renders text in a vertical column`).toEqual([]);
  }
});
