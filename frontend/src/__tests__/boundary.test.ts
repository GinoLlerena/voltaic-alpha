/** @vitest-environment node */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import schema from "../../openapi.json";

/** Source with comments removed, so prose about a verb is not read as the verb. */
function code(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/**
 * The browser half of the read-only boundary. The server refuses writes; this
 * asserts the client cannot express one, so the two cannot drift apart.
 */
describe("the client cannot write", () => {
  it("is generated from a contract that publishes only GET", () => {
    const methods = new Set(
      Object.values(schema.paths as Record<string, Record<string, unknown>>).flatMap((ops) =>
        Object.keys(ops),
      ),
    );
    expect([...methods].sort()).toEqual(["get"]);
  });

  it("exposes no helper for a write method", () => {
    // Comments are stripped first, for the reason check_no_write_path.py gives:
    // a guard that cannot tell a call from a docstring explaining why we never
    // make that call punishes documentation, and gets deleted the first time it
    // is inconvenient.
    const client = code("../api/client.ts");
    for (const verb of ["POST", "PUT", "PATCH", "DELETE"]) {
      expect(client).not.toContain(verb);
    }
    expect(client).not.toMatch(/method\s*:/);
    expect(client).not.toMatch(/\bbody\b/);
  });

  it("sends no credentials with a request", () => {
    const client = code("../api/client.ts");
    expect(client).not.toMatch(/Authorization|api[_-]?key|token/i);
    expect(client).not.toMatch(/credentials\s*:/);
  });
});
