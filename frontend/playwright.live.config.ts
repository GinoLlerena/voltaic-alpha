import { defineConfig, devices } from "@playwright/test";

/**
 * The live suite: the real API serving the real built UI, from one origin, over
 * real records - no recorded responses. Point it at any deployment:
 *
 *   LIVE_URL=http://127.0.0.1:18700 pnpm exec playwright test -c playwright.live.config.ts
 *
 * Not part of CI, which has no server with data; it is how a deployment is
 * verified before and after port 80 is cut over to it.
 */
const baseURL = process.env.LIVE_URL;
if (!baseURL) throw new Error("set LIVE_URL to the deployment under test");

export default defineConfig({
  testDir: "./e2e-live",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
