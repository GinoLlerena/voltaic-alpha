import { expect, test } from "@playwright/test";
import { digests, replayApi } from "./fixtures";

/**
 * What the page actually renders, asserted against a real cascade.
 *
 * These are the three `RUI-VAL-012` defects turned into checks. Each one had
 * correct markup — the unit tests passed throughout — and was wrong only once a
 * stylesheet was applied. Computed styles are used rather than pixels because
 * they are identical on every platform, so this can gate a pull request without
 * a font-rendering argument.
 */

const REFUSAL = "8374de98a8af7fa09bdfb2bbcb0423fe6279879b5c53650acbda4e2affdcd8b2";
const MODEL_WROTE_THE_MEMO = "ab04de4520ee8b1da53e54a2b8f1dcc0850109b69170b313a83f23c52b9992d5";

const WARM = "rgb(232, 163, 61)";
const DIM = "rgb(134, 153, 178)";

test.describe("the proof tiles", () => {
  test("are laid out, rather than a bulleted list of same-sized text", async ({ page }) => {
    await replayApi(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const tiles = await page.evaluate(() => {
      const list = document.querySelector(".proof");
      if (!list) return null;
      const size = (el: Element | null) => (el ? getComputedStyle(el).fontSize : null);
      return {
        display: getComputedStyle(list).display,
        listStyle: getComputedStyle(list).listStyleType,
        items: [...list.querySelectorAll("li")].map((li) => ({
          mode: li.getAttribute("data-mode"),
          value: size(li.querySelector(".n")),
          label: size(li.querySelector(".l")),
          chip: size(li.querySelector(".mode")),
          source: size(li.querySelector(".src")),
          chipColour: li.querySelector(".mode")
            ? getComputedStyle(li.querySelector(".mode") as Element).color
            : null,
        })),
      };
    });

    expect(tiles, ".proof rendered nothing").not.toBeNull();
    expect(tiles!.display, ".proof had no layout — it shipped once with no styles at all").toBe("grid");
    expect(tiles!.listStyle).toBe("none");
    expect(tiles!.items.length).toBeGreaterThan(0);

    for (const tile of tiles!.items) {
      // The value, the label, the mode and the provenance each say a different
      // kind of thing, and once all rendered at 15px in the same colour.
      const sizes = new Set([tile.value, tile.label, tile.chip, tile.source]);
      expect(sizes.size, `"${tile.mode}" tile renders its four parts at one size`).toBe(4);
    }
  });

  test("distinguish an observed value from a derived one", async ({ page }) => {
    // Authority rule 6: observed, read, replayed and derived stay visibly
    // different. The mode is carried on `data-mode`, not inferred here.
    await replayApi(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const byMode = await page.evaluate(() => {
      const entries: [string, string][] = [];
      for (const li of document.querySelectorAll(".proof li")) {
        const chip = li.querySelector(".mode");
        if (chip) entries.push([li.getAttribute("data-mode") ?? "?", getComputedStyle(chip).color]);
      }
      return entries;
    });

    const modes = new Set(byMode.map(([mode]) => mode));
    const colours = new Set(byMode.map(([, colour]) => colour));
    expect(modes.size).toBeGreaterThan(1);
    expect(colours.size, `modes share one colour: ${JSON.stringify(byMode)}`).toBe(modes.size);
  });
});

test.describe("the authority spine", () => {
  test("gives the model's stage the model's colour only when it ran", async ({ page }) => {
    await replayApi(page);

    const memo = async (digest: string) => {
      await page.goto(`/decisions/${digest}`);
      await page.waitForLoadState("networkidle");
      return page.evaluate(() => {
        const li = document.querySelector('[data-stage="03"]');
        const label = li?.querySelector(".l");
        if (!li || !label) throw new Error("the spine did not render stage 03");
        return {
          lit: li.getAttribute("data-lit"),
          colour: getComputedStyle(label).color,
          spoken: li.querySelector(".sr")?.textContent ?? null,
        };
      });
    };

    const called = await memo(MODEL_WROTE_THE_MEMO);
    expect(called.lit).toBe("true");
    expect(called.colour, "the stage the model wrote must carry the model's colour").toBe(WARM);

    const never = await memo(REFUSAL);
    expect(never.lit).toBe("false");
    // This was the inversion: a refusal that never called the model showed the
    // memo stage warm, and a decision it had written showed it cool.
    expect(never.colour, "a stage the model never reached must not look like the model's").toBe(DIM);
    expect(never.spoken, "a fade alone tells a screen reader nothing").toContain("not reached");
  });

  test("never expresses a stage's state through opacity", async ({ page }) => {
    await replayApi(page);
    await page.goto(`/decisions/${REFUSAL}`);
    await page.waitForLoadState("networkidle");
    const faded = await page.evaluate(() =>
      [...document.querySelectorAll(".spine li")]
        .filter((li) => Number(getComputedStyle(li).opacity) < 1)
        .map((li) => li.getAttribute("data-stage")),
    );
    // Opacity scales text and background together: the old `.45` rendered at
    // 2.02:1 and could not be reasoned about from the palette.
    expect(faded).toEqual([]);
  });
});

test.describe("the decision ticket", () => {
  test("says a structure reading is absent rather than dropping the section", async ({ page }) => {
    await replayApi(page);
    for (const digest of digests) {
      await page.goto(`/decisions/${digest}`);
      await page.waitForLoadState("networkidle");
      const section = page.getByTestId("structure-reading");
      await expect(section, `${digest.slice(0, 12)} dropped the section entirely`).toBeVisible();
      if ((await section.getAttribute("data-present")) === "false") {
        await expect(section).toContainText("No structure reading was recorded");
        await expect(section).toContainText("structure_readings");
      }
    }
  });

  test("gives every reason a source", async ({ page }) => {
    await replayApi(page);
    for (const digest of digests) {
      await page.goto(`/decisions/${digest}`);
      await page.waitForLoadState("networkidle");
      const missing = await page.evaluate(() =>
        [...document.querySelectorAll('[data-testid="why-decision"] li')]
          .filter((li) => !li.querySelector(".src")?.textContent?.trim())
          .map((li) => li.querySelector(".s")?.textContent ?? "?"),
      );
      expect(missing, `${digest.slice(0, 12)} has a claim with no source`).toEqual([]);
    }
  });
});

test.describe("the depth panels (RUI-4)", () => {
  test("render their tables as tables, not as runs of text", async ({ page }) => {
    // The proof tiles shipped with no styles at all and a green suite. Every
    // table added since is checked the same way: laid out, with a header row
    // that does not look like a data row.
    await replayApi(page);
    await page.goto(`/decisions/${MODEL_WROTE_THE_MEMO}`);
    await page.waitForLoadState("networkidle");

    const tables = await page.evaluate(() =>
      [...document.querySelectorAll("table.matrix")].map((table) => {
        const th = table.querySelector("th");
        const td = table.querySelector("td");
        const cs = getComputedStyle(table);
        return {
          panel: table.closest("section")?.getAttribute("data-testid") ?? "?",
          collapsed: cs.borderCollapse,
          headerSize: th ? getComputedStyle(th).fontSize : null,
          headerColour: th ? getComputedStyle(th).color : null,
          cellSize: td ? getComputedStyle(td).fontSize : null,
          cellColour: td ? getComputedStyle(td).color : null,
        };
      }),
    );

    expect(tables.length, "no leg or check matrix rendered").toBeGreaterThan(0);
    for (const table of tables) {
      expect(table.collapsed, `${table.panel} table is not laid out`).toBe("collapse");
      expect(
        table.headerSize === table.cellSize && table.headerColour === table.cellColour,
        `${table.panel}: header row is indistinguishable from a data row`,
      ).toBe(false);
    }
  });

  test("answer the five questions, and link each to its evidence", async ({ page }) => {
    await replayApi(page);
    await page.goto(`/decisions/${MODEL_WROTE_THE_MEMO}`);
    await page.waitForLoadState("networkidle");

    const summary = await page.evaluate(() => {
      const rows = [...document.querySelectorAll(".five > div")];
      return rows.map((row) => ({
        question: row.querySelector("dt")?.textContent?.trim() ?? "?",
        answered: row.getAttribute("data-answered"),
        // The anchor must land on a panel that exists and is on the page.
        targetExists: (() => {
          const href = row.querySelector("a")?.getAttribute("href") ?? "";
          const target = document.getElementById(href.slice(1));
          return target !== null && target.getBoundingClientRect().height > 0;
        })(),
      }));
    });

    expect(summary).toHaveLength(5);
    for (const row of summary) {
      expect(row.targetExists, `${row.question} links nowhere`).toBe(true);
    }
    expect(summary.filter((row) => row.answered === "true").length).toBeGreaterThan(0);
  });

  test("a refusal answers none of them, and says so in every panel", async ({ page }) => {
    await replayApi(page);
    await page.goto(`/decisions/${REFUSAL}`);
    await page.waitForLoadState("networkidle");

    const state = await page.evaluate(() => ({
      unanswered: document.querySelectorAll('.five > div[data-answered="false"]').length,
      // Absent panels must still be on the page, with a heading and a source.
      absent: [...document.querySelectorAll('section[data-present="false"]')].map((s) => ({
        id: s.getAttribute("data-testid"),
        heading: (s.querySelector("h3")?.textContent ?? "").length > 0,
        source: (s.querySelector(".src")?.textContent ?? "").length > 0,
      })),
    }));

    expect(state.unanswered).toBe(5);
    expect(state.absent.length).toBeGreaterThan(0);
    expect(state.absent.filter((panel) => !panel.heading || !panel.source)).toEqual([]);
  });

  test("marks evidence that belongs to another decision", async ({ page }) => {
    // Selected-decision isolation. The committed receipt describes a different
    // evaluation of the same snapshot, and the page must not imply otherwise.
    await replayApi(page);
    await page.goto(`/decisions/${MODEL_WROTE_THE_MEMO}`);
    await page.waitForLoadState("networkidle");
    const lineage = page.getByTestId("proof-lineage");
    await expect(lineage).toBeVisible();
    const foreign = lineage.locator('[data-belongs="false"]');
    expect(await foreign.count()).toBeGreaterThan(0);
    await expect(foreign.first()).toContainText(/DECISION/);
  });
});
