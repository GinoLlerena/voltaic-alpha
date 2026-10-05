import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIGEST,
  QUALIFIED,
  at,
  envelope,
  market,
  respond,
} from "../test/fixtures";

/** One decision: its summary, the five questions and the depth panels. */

afterEach(() => vi.unstubAllGlobals());

describe("a decision is addressable", () => {
  it("opens from its own URL without going through the list", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    expect(await screen.findByTestId("decision-ticket")).toHaveTextContent("spy-agent-1");
  });

  it("is reachable by following the list", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/decisions"));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: /SPY.*No trade/ }));
    await waitFor(() => expect(screen.getByTestId("decision-ticket")).toBeInTheDocument());
  });

  it("says so when the source holds no such decision", async () => {
    vi.stubGlobal("fetch", respond(new Set(), {}, { [`/api/v1/decisions/${DIGEST}/summary`]: 404 }));
    render(at(`/decisions/${DIGEST}`));
    expect(await screen.findByTestId("decision-missing")).toBeInTheDocument();
  });

  it("does not call a failed request a missing decision (PUI-001)", async () => {
    for (const fetcher of [
      respond(new Set([`/api/v1/decisions/${DIGEST}/summary`])),
      respond(new Set(), {}, { [`/api/v1/decisions/${DIGEST}/summary`]: 500 }),
    ]) {
      vi.stubGlobal("fetch", fetcher);
      const { unmount } = render(at(`/decisions/${DIGEST}`));
      expect(await screen.findByTestId("decision-unavailable")).toHaveTextContent("not a missing record");
      expect(screen.queryByTestId("decision-missing")).toBeNull();
      unmount();
    }
  });
});

describe("the ticket shows the server's own reasoning", () => {
  it("marks the model's one stage and leaves the rest to code", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const spine = await screen.findByTestId("authority-spine");
    const memo = spine.querySelector('[data-stage="03"]');
    expect(memo).toHaveClass("model");
    expect(memo).toHaveAttribute("data-lit", "false");
    // The stage a refusal never reached must say so, not merely look faint.
    expect(spine.querySelector('[data-stage="07"]')?.textContent).toContain("not reached");
  });

  it("explains how nearly the setup qualified", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const structure = await screen.findByTestId("structure-reading");
    expect(structure).toHaveTextContent("separation_or_side");
    expect(structure).toHaveTextContent("-0.00168750");
    expect(structure).toHaveTextContent("short of the threshold");
  });

  it("says so when no structure reading was recorded, rather than dropping the section", async () => {
    // Every committed-evidence decision has `structure: null`, so this is the
    // case the demo actually shows. Silently omitting it put a refusal's
    // central question off the page with no account of why.
    vi.stubGlobal(
      "fetch",
      respond(new Set(), {
        [`/api/v1/decisions/${DIGEST}/market`]: envelope({ ...market, structure: null }),
      }),
    );
    render(at(`/decisions/${DIGEST}`));
    const structure = await screen.findByTestId("structure-reading");
    expect(structure).toHaveAttribute("data-present", "false");
    expect(structure).toHaveTextContent("No structure reading was recorded");
    expect(structure).toHaveTextContent("structure_readings");
  });

  it("shows a waiting horizon as waiting rather than hiding it", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const list = await screen.findByTestId("horizons");
    expect(list).toHaveTextContent("WAITING");
    expect(list).toHaveTextContent("T+1");
  });
});

describe("a trader's five questions", () => {
  // RUI-4's exit. Each answer must come from a record, and a question this
  // decision cannot answer must say so: an omitted row reads as though the
  // question did not apply, which for a refusal is the opposite of the truth.
  it("answers all five from the decision's own records", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const five = await screen.findByTestId("trader-summary");
    expect(five).toHaveTextContent("bullish, by deterministic_trend_retest_v0");
    expect(five).toHaveTextContent("1 signal(s) cited at 771.100000");
    expect(five).toHaveTextContent("bull_call_debit_spread ×1, debit 3.500000 per share");
    expect(five).toHaveTextContent("$350.000000 of a $750.000000 budget");
    expect(five).toHaveTextContent("close below 759.53 invalidates the retest");
    expect(five.querySelectorAll('[data-answered="true"]')).toHaveLength(5);
  });

  it("says which questions a refusal cannot answer", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    const five = await screen.findByTestId("trader-summary");
    expect(five.querySelectorAll('[data-answered="false"]')).toHaveLength(5);
    expect(five).toHaveTextContent("not answerable from this decision's records");
  });

  it("links each question to the panel that evidences it", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const five = await screen.findByTestId("trader-summary");
    const targets = [...five.querySelectorAll("a")].map((a) => a.getAttribute("href")?.slice(1));
    expect(targets).toEqual([
      "qualification", "signals", "structure-selected", "risk-accounting", "invalidation",
    ]);
    for (const id of targets) {
      expect(document.getElementById(id ?? ""), `no panel with id ${id}`).not.toBeNull();
    }
  });
});

describe("the depth panels", () => {
  it("shows counter-evidence rather than only the signals that agreed", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const signals = await screen.findByTestId("signals");
    expect(signals).toHaveTextContent("counter-evidence");
    expect(signals).toHaveTextContent("Breadth is narrowing.");
  });

  it("shows the recomputed maximum loss beside the claimed one", async () => {
    // The governor not taking the structure's word for it is the whole check.
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const checks = await screen.findByTestId("risk-checks");
    expect(checks).toHaveTextContent("max_loss_recomputed");
    expect(checks).toHaveTextContent("recomputed 350.00");
    expect(checks).toHaveTextContent("claimed 350.00");
  });

  it("keeps the classifier's invalidation conditions apart from the memo's", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const panel = await screen.findByTestId("invalidation");
    expect(panel).toHaveTextContent("binding · setups");
    expect(panel).toHaveTextContent("advisory · theses");
  });

  it("names a structure that was rejected, with the reason", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const rejected = await screen.findByTestId("structure-rejected");
    expect(rejected).toHaveAttribute("data-present", "true");
    expect(rejected).toHaveTextContent("max loss exceeds the risk budget");
  });

  it("marks an artifact that belongs to another decision", async () => {
    // Selected-decision isolation: RUI-4's exit requires it to hold throughout,
    // and the receipt in this source describes a different evaluation.
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const lineage = await screen.findByTestId("proof-lineage");
    const receipt = lineage.querySelector('[data-relation="OTHER_DECISION"]');
    expect(receipt).not.toBeNull();
    expect(receipt).toHaveAttribute("data-belongs", "false");
    expect(lineage).toHaveTextContent("a different evaluation of the same snapshot");
  });

  it("offers the manifest as a file, and says how to verify it", async () => {
    // The digest shown is over the bytes the API serves, so the downloaded file
    // hashes to it. A hash nobody is told how to check is decoration.
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const panel = await screen.findByTestId("proof-export");
    const link = screen.getByTestId("proof-download");
    expect(link).toHaveAttribute("href", `/api/v1/proof/${QUALIFIED}.json`);
    expect(link).toHaveAttribute("download");
    expect(panel).toHaveTextContent("sha256:manifest");
    expect(panel).toHaveTextContent("shasum -a 256");
  });

  it("quotes the manifest's own disclosures rather than restating them", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const panel = await screen.findByTestId("proof-export");
    expect(panel).toHaveTextContent("Alpaca Paper only");
    expect(panel).toHaveTextContent("Nothing here is investment advice");
  });

  it("says the proof is unavailable when its request fails, not that nothing exists", async () => {
    // The server returns a manifest for every decision it holds, so "nothing to
    // export" was only ever reachable through a failed request (PUI-003).
    vi.stubGlobal("fetch", respond(new Set([`/api/v1/decisions/${QUALIFIED}/proof`])));
    render(at(`/decisions/${QUALIFIED}`));
    const state = await screen.findByText(/proof lineage unavailable/);
    expect(state).toHaveTextContent("not an empty record");
    expect(screen.queryByTestId("proof-export")).toBeNull();
    expect(screen.queryByText(/nothing to export/)).toBeNull();
    // The other panels are unaffected by one panel's failure.
    expect(await screen.findByTestId("risk-accounting")).toBeInTheDocument();
  });

  it("says nothing reached the broker when nothing did", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${QUALIFIED}`));
    const orders = await screen.findByTestId("lifecycle-orders");
    expect(orders).toHaveAttribute("data-present", "false");
    expect(orders).toHaveTextContent("Nothing reached the broker");
    expect(orders).toHaveTextContent("broker_orders");
  });

  it("renders every panel as an absence for a refusal, never as a blank", async () => {
    vi.stubGlobal("fetch", respond());
    render(at(`/decisions/${DIGEST}`));
    await screen.findByTestId("trader-summary");
    for (const id of [
      "qualification", "memo", "observation", "signals", "structure-selected",
      "structure-rejected", "risk-accounting", "risk-checks", "invalidation",
      "lifecycle-orders", "lifecycle-position", "lifecycle-exits", "proof-lineage",
    ]) {
      const panel = screen.getByTestId(id);
      expect(panel, `${id} vanished`).toBeInTheDocument();
      expect(panel.querySelector("h3"), `${id} lost its heading`).not.toBeNull();
    }
  });
});
