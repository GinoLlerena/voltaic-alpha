import { defineConfig, devices } from "@playwright/test";

/**
 * The browser half of the gate.
 *
 * `RUI-VAL-011` and `RUI-VAL-012` were three rendering defects that a green
 * vitest suite could not see, because jsdom applies no stylesheet: the palette
 * failed contrast, the spine painted the model's stage backwards through a
 * cascade accident, and an absent record rendered as nothing at all. Those need
 * a real engine with real layout, so this runs the built app in Chromium.
 *
 * It stays true to the frontend job's design — no Python, no database — by
 * serving `dist` and replaying `fixtures/api.json` instead of standing the API
 * up. A failure here is therefore always the page's fault.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  // Font rasterisation differs between macOS and CI's Linux, so a pixel
  // baseline is only meaningful against the platform that produced it.
  snapshotPathTemplate: "{testDir}/__screenshots__/{platform}/{arg}{ext}",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // `--host 127.0.0.1` on purpose: left to itself, preview binds ::1 only
    // and the health check below never answers.
    command: "pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
