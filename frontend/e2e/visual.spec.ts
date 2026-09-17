import { expect, test } from "@playwright/test";
import { replayApi } from "./fixtures";

/**
 * Visual regression over the screens an evaluator actually sees.
 *
 * This is deliberately narrow. The accessibility and rendering specs assert
 * properties — contrast, layout, which stage carries the model's colour — and a
 * property says why it failed. A pixel diff cannot, so it is kept for the thing
 * properties miss: unintended drift in a screen nobody was editing.
 *
 * Baselines are per-platform (`snapshotPathTemplate`), because font
 * rasterisation on macOS and on CI's Linux are not the same image. Regenerate
 * with `pnpm test:visual:update` on the platform whose baseline changed; the CI
 * job uploads the images it produced so a Linux baseline can be taken from a
 * run rather than guessed at.
 */

const SCREENS = [
  { name: "overview", path: "/" },
  { name: "tour-step", path: "/?tour=4" },
  { name: "activity", path: "/activity" },
  {
    name: "decision-refusal",
    path: "/decisions/8374de98a8af7fa09bdfb2bbcb0423fe6279879b5c53650acbda4e2affdcd8b2",
  },
  {
    name: "decision-with-memo",
    path: "/decisions/ab04de4520ee8b1da53e54a2b8f1dcc0850109b69170b313a83f23c52b9992d5",
  },
];

for (const screen of SCREENS) {
  for (const width of [1280, 400]) {
    test(`${screen.name} at ${width}px looks as it did`, async ({ page }) => {
      await replayApi(page);
      await page.setViewportSize({ width, height: 900 });
      await page.goto(screen.path);
      await page.waitForLoadState("networkidle");
      // Web fonts are not used, but layout still settles a frame late at 400px.
      await page.evaluate(async () => {
        await document.fonts.ready;
      });
      await expect(page).toHaveScreenshot(`${screen.name}-${width}.png`, {
        fullPage: true,
        animations: "disabled",
      });
    });
  }
}
