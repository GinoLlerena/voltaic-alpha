/** @vitest-environment node */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * A live axe scan found `--dim` failing at 3.09:1 and the authority spine
 * dimming unreached stages with `opacity: .45`, which no palette review would
 * have caught by eye. A browser is the only place axe can measure contrast, so
 * this asserts the same arithmetic against the declared tokens instead: every
 * colour text is drawn in, against every surface it can be drawn on.
 */
const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

function token(name: string): string {
  const found = css.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, "i"));
  if (!found?.[1]) throw new Error(`no ${name} in styles.css`);
  return found[1];
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(hex.slice(i, i + 2), 16))) as [
    number,
    number,
    number,
  ];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const x = luminance(a);
  const y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

/**
 * Surfaces text is painted on.
 *
 * `--edge` was left out of this list once, on the reasoning that it only shows
 * as the 1px rules between cells and every child paints over it. Within a day
 * `RUI-4`'s panels put text on it and axe found `--dim` there at 3.77:1. It is
 * the lightest surface in the palette and therefore the binding one, so it is
 * listed: an ink that clears `--edge` clears everything.
 */
const surfaces = {
  "--ink": token("--ink"),
  "--panel": token("--panel"),
  "--edge": token("--edge"),
  "panel2 (.spine li)": "#1b222c",
  "the current decision": "#101923",
  "the model's stage": "#1f1808",
};

const inks = {
  "--text": token("--text"),
  "--muted": token("--muted"),
  "--dim": token("--dim"),
  "--cool": token("--cool"),
  "--warm": token("--warm"),
  "--affirm": token("--affirm"),
  "--alarm": token("--alarm"),
};

describe("every token pair clears WCAG AA", () => {
  for (const [inkName, ink] of Object.entries(inks)) {
    for (const [surfaceName, surface] of Object.entries(surfaces)) {
      it(`${inkName} on ${surfaceName}`, () => {
        expect(contrast(ink, surface)).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});

describe("the spine says whose stage actually ran", () => {
  // jsdom applies no stylesheet, so the cascade is asserted on the source. The
  // bug this guards was invisible to every DOM test: the classes were right and
  // the colours were wrong, because `.on` followed `.model` at equal
  // specificity and silently won.
  const at = (selector: string) => css.indexOf(selector);

  it("keeps the model's colour on the model's stage when it ran", () => {
    expect(at(".spine li.model.on .l")).toBeGreaterThan(-1);
    expect(at(".spine li.model.on .l")).toBeGreaterThan(at(".spine li.on .l"));
  });

  it("recedes the model's stage when the model was never called", () => {
    expect(at(".spine li.off .l")).toBeGreaterThan(at(".spine li.model .l"));
  });
});

describe("state is never carried by opacity alone", () => {
  it("does not fade the stages a decision never reached", () => {
    // `opacity` scales foreground and background together, so it cannot be
    // reasoned about from the tokens above, and it reaches no screen reader.
    const spineOff = css.match(/\.spine li\.off\s*\{[^}]*\}/)?.[0] ?? "";
    expect(spineOff).not.toMatch(/opacity/);
  });

  it("keeps a visually-hidden helper for saying so in words", () => {
    expect(css).toMatch(/\.sr\s*\{[^}]*clip-path:\s*inset\(50%\)/);
  });
});
