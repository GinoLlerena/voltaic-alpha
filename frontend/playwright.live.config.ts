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
  // One retry: the operator machine reaches the host through Cloudflare WARP,
  // which dropped some connections on 28 September 2026. A real defect fails
  // twice - the 10.8 MB list did - and a retried pass is reported as flaky.
  retries: 1,
  reporter: [["list"]],
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
