import type { ReactNode } from "react";
import type { Resource } from "../api/useResource";
import { checkedAt } from "./time";

type AnyResource = Resource<unknown>;
/** The data a resource carries once it has any, read from its ready state. */
type DataOf<R> = Extract<R, { state: "ready" }> extends { envelope: { data: infer T } } ? T : never;

/**
 * What a request that has not produced verified data says instead.
 *
 * `PUI-001`: loading and failure are not emptiness. A panel that renders its
 * "nothing here" text before the answer arrives, or after the request failed,
 * asserts something the source never said.
 */
export function Pending({ what, resources }: { what: string; resources: AnyResource[] }) {
  const failed = resources.filter((r) => r.state === "failed");
  if (failed.length > 0) {
    return (
      <p className="gate" data-testid="resource-state" data-state="failed" data-resource={what}>
        <span className="t failed" role="alert">
          {what} unavailable — the request failed (
          {failed.map((r) => (r.state === "failed" ? r.reason : "")).join("; ")}). This is not an
          empty record.
        </span>
        <button type="button" onClick={() => failed.forEach((r) => r.retry())}>
          Retry
        </button>
      </p>
    );
  }
  return (
    <p className="gate" data-testid="resource-state" data-state="loading" data-resource={what}>
      <span className="t na" role="status">
        Loading {what}…
      </span>
    </p>
  );
}

/** The local warning for a panel still showing its last verified response. */
export function StaleNote({ what, resources }: { what: string; resources: AnyResource[] }) {
  const stale = resources.flatMap((r) => (r.state === "stale" ? [r] : []));
  if (stale.length === 0) return null;
  const oldest = stale.map((r) => r.fetchedAt).sort()[0] ?? "";
  return (
    <p className="stale-note" role="status" data-testid="stale-note" data-resource={what}>
      Showing the last verified {what}, received {checkedAt(oldest)} — the latest refresh failed (
      {stale.map((r) => r.reason).join("; ")}).
    </p>
  );
}

/**
 * Render `children` only with verified (or last-known) data for every input.
 *
 * `PUI-003`: each decision panel keeps its own request state. One panel failing
 * shows that panel as unavailable; it does not turn into the panel's "nothing
 * recorded" text, and it does not blank the others.
 *
 * `expectedSource` names the source the page's primary record came from. A
 * panel answered from a different one says so rather than being read as part of
 * one coherent record: the API does not promise an atomic snapshot across calls.
 *
 * `CSA-007`: sources are compared by `source_id`. The label carries the live
 * decision count, so comparing labels reported a panel refreshed after the
 * worker's next decision as coming from another source. The label is still
 * what the warning shows a reader.
 */
export function Loaded<R extends Record<string, AnyResource>>({
  what,
  resources,
  expectedSource,
  children,
}: {
  what: string;
  resources: R;
  expectedSource?: { id: string; label: string } | undefined;
  children: (data: { [K in keyof R]: DataOf<R[K]> }) => ReactNode;
}) {
  const list = Object.values(resources);
  if (list.some((r) => r.state === "failed" || r.state === "loading")) {
    return <Pending what={what} resources={list} />;
  }
  const data = Object.fromEntries(
    Object.entries(resources).map(([key, r]) => [
      key,
      r.state === "ready" || r.state === "stale" ? r.envelope.data : null,
    ]),
  ) as { [K in keyof R]: DataOf<R[K]> };
  const foreign =
    expectedSource === undefined
      ? []
      : list.flatMap((r) =>
          (r.state === "ready" || r.state === "stale") && r.envelope.source_id !== expectedSource.id
            ? [r.envelope.source_label]
            : [],
        );
  return (
    <>
      {foreign.length > 0 ? (
        <p className="stale-note" role="status" data-testid="source-mismatch" data-resource={what}>
          The {what} came from a different source ({[...new Set(foreign)].join(", ")}) than this
          decision ({expectedSource?.label}). It may not describe the same record.
        </p>
      ) : null}
      <StaleNote what={what} resources={list} />
      {children(data)}
    </>
  );
}
