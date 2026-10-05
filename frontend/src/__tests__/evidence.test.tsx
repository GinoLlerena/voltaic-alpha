import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIGEST,
  at,
  respond,
} from "../test/fixtures";

/** Evidence: the guided tour. */

afterEach(() => vi.unstubAllGlobals());

describe("the guided path", () => {
  it("is a shareable step, and opens its own decision", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/?tour=1"));
    const card = await screen.findByTestId("tour-card");
    expect(card).toHaveTextContent("What was observed");
    expect(card.querySelector("a")).toHaveAttribute("href", `/decisions/${DIGEST}`);
  });

  it("admits a step whose decision this source lacks", async () => {
    /* RUI-VAL-009: the dashboard narrated over another decision for weeks. */
    vi.stubGlobal("fetch", respond());
    render(at("/?tour=2"));
    expect(await screen.findByTestId("scene-absent")).toHaveTextContent("is not in this source");
    expect(screen.queryByText("Never shown.")).toBeNull();
  });

  it("clamps a hand-edited step rather than raising", async () => {
    vi.stubGlobal("fetch", respond());
    render(at("/?tour=99"));
    expect(await screen.findByTestId("tour-card")).toBeInTheDocument();
  });
});
