import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { VIEWS } from "../api/views";
import {
  DIGEST,
  QUALIFIED,
  at,
  envelope,
  listing,
  respond,
  structure,
} from "../test/fixtures";

/** The decision list, its views and the decision workflow (PUI phase 3). */

afterEach(() => vi.unstubAllGlobals());

describe("the decision views", () => {
  const requested = (fetchMock: ReturnType<typeof respond>) =>
    fetchMock.mock.calls
      .map(([input]) => String(input))
      .filter((u) => u.includes("/decisions/grouped") || u.startsWith("/api/v1/decisions?"));

  it("asks for the Notable view by default", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions"));
    await screen.findByTestId("decision-list");
    expect(requested(fetchMock)).toEqual(["/api/v1/decisions/grouped?view=Notable"]);
  });

  it("honours a link shared before the list moved (/?view=…), and marks it current", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/?view=Refusals"));
    await screen.findByTestId("decision-list");
    // An ungrouped view pages the full history (PUI-008), filtered on the server.
    expect(requested(fetchMock)).toEqual(["/api/v1/decisions?outcome=refusal&limit=50"]);
    const nav = screen.getByRole("navigation", { name: "Decision views" });
    const current = nav.querySelector('[aria-current="page"]');
    expect(current).toHaveTextContent("Refusals");
  });

  it("treats an unknown view as the default rather than sending it", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions?view=Bogus"));
    await screen.findByTestId("decision-list");
    expect(requested(fetchMock)).toEqual(["/api/v1/decisions/grouped?view=Notable"]);
  });

  it("offers every view as a shareable link", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const nav = await screen.findByRole("navigation", { name: "Decision views" });
    const links = [...nav.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")]);
    expect(links).toEqual([
      ["Notable", "/decisions"],
      ["Positions", "/decisions?view=Positions"],
      ["Refusals", "/decisions?view=Refusals"],
      ["Everything", "/decisions?view=Everything"],
    ]);
  });

  it("offers exactly the views the server accepts", () => {
    interface Spec {
      paths: Record<string, { get: { parameters: { name: string; schema: { pattern?: string } }[] } }>;
    }
    // jsdom gives import.meta.url an http: scheme; the suite runs from frontend/.
    const spec = JSON.parse(readFileSync(`${process.cwd()}/openapi.json`, "utf8")) as Spec;
    const param = spec.paths["/api/v1/decisions/grouped"]?.get.parameters.find((p) => p.name === "view");
    const pattern = param?.schema.pattern ?? "";
    const server = /^\^\((.*)\)\$$/.exec(pattern)?.[1]?.split("|");
    expect(server, "the view parameter must carry an enumerating pattern").toBeDefined();
    expect([...VIEWS]).toEqual(server);
  });
});

// PUI Phase 1 (docs/improvements/options_alpha_personal_ui_redesign_v0_1.md):
// no failed or unanswered request may render an invented zero, a healthy
// state, or a business absence.

describe("the decision workflow (PUI phase 3)", () => {
  it("lists a decision by instrument, outcome, reason and New York time, not by snapshot ID", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const row = await screen.findByRole("link", { name: /SPY.*No trade/ });
    expect(row).toHaveTextContent("no qualified setup");
    // A run of 72 spans its first and last member, in ET with the zone named.
    expect(row).toHaveTextContent("Tue, Sep 29, 2026, 09:45–15:45 ET");
    expect(row).toHaveTextContent("×72");
    expect(row).not.toHaveTextContent("spy-agent-1");
    expect(row.querySelector("time")).toHaveAttribute("dateTime", "2026-09-29T19:45:00+00:00");
  });

  it("states the grouping window, and says nothing is outside it when nothing is", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const scope = await screen.findByTestId("decision-scope");
    expect(scope).toHaveTextContent("1 entry for the newest 201 of 201 decisions, since Tue, Sep 1, 2026");
    expect(scope).not.toHaveTextContent("outside this window");
  });

  it("says how many decisions a bounded window leaves out and links the full history", async () => {
    // 29 Sep 2026: Notable grouped 400 of 718 and read as the whole history.
    vi.stubGlobal("fetch", respond(new Set(), {
      "/api/v1/decisions/grouped": envelope({ ...listing, total: 718, window: 400, bounded: true }),
    }));
    render(at("/decisions"));
    const scope = await screen.findByTestId("decision-scope");
    expect(scope).toHaveTextContent("newest 400 of 718 decisions");
    expect(scope).toHaveTextContent("318 older decisions are outside this window.");
    expect(within(scope).getByRole("link", { name: "Browse the full history" }))
      .toHaveAttribute("href", "/decisions?view=Everything");
  });

  it("pages the full history on the server's cursor and holds still while browsing", async () => {
    const fetchMock = respond();
    vi.stubGlobal("fetch", fetchMock);
    render(at("/decisions?view=Refusals"));
    expect(await screen.findByTestId("decision-scope")).toHaveTextContent("1 of 2 decisions");
    await userEvent.click(screen.getByTestId("history-more"));
    expect(await screen.findByTestId("history-end")).toHaveTextContent("The history ends here.");
    expect(screen.getByTestId("decision-scope")).toHaveTextContent("2 of 2 decisions");
    expect(screen.getAllByRole("link", { name: /SPY.*No trade/ })).toHaveLength(2);
    // The cursor is passed back exactly as served, never built.
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain(
      "/api/v1/decisions?outcome=refusal&limit=50&cursor=opaque-history-2",
    );
    expect(screen.getByTestId("history-newest")).toBeInTheDocument();
  });

  it("says a failed history request failed rather than that there are no decisions", async () => {
    vi.stubGlobal("fetch", respond(new Set(["/api/v1/decisions?"])));
    render(at("/decisions?view=Everything"));
    expect(await screen.findByText(/unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/holds no/)).toBeNull();
  });

  it("opens with a concise summary, then three linked sections", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const ticket = await screen.findByTestId("decision-ticket");
    expect(ticket).toHaveTextContent("Opened a Paper position");
    expect(ticket).not.toHaveTextContent("sha256:");
    const nav = screen.getByRole("navigation", { name: "Decision sections" });
    expect([...nav.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      "#setup", "#execution", "#evidence",
    ]);
    const setup = screen.getByTestId("part-setup");
    await waitFor(() => expect(within(setup).getByTestId("structure-selected")).toBeInTheDocument());
    expect(within(setup).getByTestId("structure-reading")).toBeInTheDocument();
    expect(within(setup).getByTestId("risk-accounting")).toBeInTheDocument();
    expect(within(screen.getByTestId("part-execution")).getByTestId("lifecycle-orders")).toBeInTheDocument();
    const evidence = screen.getByTestId("part-evidence");
    expect(within(evidence).getByTestId("memo")).toBeInTheDocument();
    expect(within(evidence).getByTestId("identifiers")).toHaveTextContent(`sha256:${QUALIFIED}`);
    expect(within(evidence).getByTestId("horizons")).toHaveTextContent("not the position's profit or loss");
  });

  it("calls a refusal a valid outcome, with its reason in words", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const ticket = await screen.findByTestId("decision-ticket");
    // This fixture records no observation: the instrument is said to be missing, not guessed.
    expect(ticket).toHaveTextContent("Instrument not recorded · No trade");
    expect(ticket).toHaveTextContent("No trade: no qualified setup");
    expect(ticket).toHaveTextContent("a valid outcome, not a system error");
  });

  it("never answers 'why this structure' with a candidate that was not selected", async () => {
    const fallback = { ...structure.candidates[0], selected: false };
    vi.stubGlobal("fetch", respond(new Set(), {
      [`/api/v1/decisions/${QUALIFIED}/structure`]: envelope({ selected: fallback, candidates: [fallback] }),
    }));
    render(at(`/decisions/${QUALIFIED}`));
    const five = await screen.findByTestId("trader-summary");
    const row = within(five).getByRole("link", { name: "Why this structure" }).closest("div");
    expect(row).toHaveAttribute("data-answered", "false");
    expect(five).not.toHaveTextContent("SPY260911C00790000");
  });

  it("labels money with its unit", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const selected = await screen.findByTestId("structure-selected");
    expect(selected).toHaveTextContent("per share, as quoted; a contract is 100 shares");
    expect(selected).toHaveTextContent("$350.000000");
    expect(screen.getByTestId("risk-accounting")).toHaveTextContent("USD, whole structure");
  });
});
