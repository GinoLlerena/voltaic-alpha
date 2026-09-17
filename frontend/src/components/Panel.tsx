import type { ReactNode } from "react";

/**
 * A section that says when it has nothing, and names where that would come from.
 *
 * `RUI-VAL-009` hid positions behind a default view; `RUI-VAL-012` dropped the
 * structure reading entirely when no record existed. Both were the same
 * mistake made twice, so absence is a shared component rather than a habit each
 * panel is trusted to remember.
 */
export function Panel({
  title,
  source,
  present,
  absence,
  children,
  testId,
}: {
  title: string;
  /** The record this panel reads, named even when it holds nothing. */
  source: string;
  present: boolean;
  /** What is missing, in the server's terms — never a guess at why. */
  absence: string;
  children?: ReactNode;
  testId: string;
}) {
  return (
    <section id={testId} data-testid={testId} data-present={String(present)}>
      <h3>{title}</h3>
      {present ? (
        children
      ) : (
        <p className="gate">
          <span className="t na">{absence}</span>
          <span className="src">{source}</span>
        </p>
      )}
    </section>
  );
}

/** A labelled value that carries where it came from, used across the panels. */
export function Fact({ label, value, source }: { label: string; value: ReactNode; source?: string | undefined }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        {value}
        {source ? <span className="src"> {source}</span> : null}
      </dd>
    </>
  );
}

/**
 * A table that scrolls itself rather than the page.
 *
 * The leg matrix has nine columns and cannot fit a phone. Letting the document
 * scroll sideways instead breaks every other screen, so the table gets its own
 * region — focusable and named, because a region a mouse can scroll and a
 * keyboard cannot is not reachable.
 */
export function Matrix({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="scroll" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
