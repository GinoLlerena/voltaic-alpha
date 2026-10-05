import "@testing-library/jest-dom/vitest";

/**
 * A React `act(...)` warning fails the test that caused it.
 *
 * `CSA-010`: the suite passed with 29 of these on stderr, all from one test
 * that navigated back outside `act`. A warning nobody reads is how the next
 * real one gets missed, so it is an error here rather than a log line.
 */
const reportError = console.error.bind(console);
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
    const text = args.map(String).join(" ");
    if (text.includes("not wrapped in act(")) {
      throw new Error(`React act() warning: ${text.split("\n")[0] ?? text}`);
    }
    reportError(...args);
  });
});
afterEach(() => {
  vi.restoreAllMocks();
});
