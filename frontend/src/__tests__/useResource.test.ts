import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiUrl } from "../api/client";
import { useResource, type Resource } from "../api/useResource";

/**
 * `PUI-002`: what the hook holds belongs to one path, and a late answer never
 * overwrites a newer one. Driven by hand-resolved fetches so the order of
 * answers is the test's choice, not the scheduler's.
 */

const A = "/api/v1/decisions/aaaa/summary" as ApiUrl;
const B = "/api/v1/decisions/bbbb/summary" as ApiUrl;

const body = (label: string) => ({
  schema_version: "public.v1", source_mode: "LIVE", source_label: "live",
  observed_at: "2026-09-29T12:00:00+00:00", correlation_id: null, data: { label },
});

interface Call { url: string; resolve: (label: string) => void; reject: (status?: number) => void }

function manualFetch() {
  const calls: Call[] = [];
  const fetcher = vi.fn((input: RequestInfo | URL) =>
    new Promise<Response>((resolve, reject) => {
      calls.push({
        url: String(input),
        resolve: (label) =>
          resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(body(label)) } as Response),
        reject: (status) =>
          status === undefined
            ? reject(new Error("network down"))
            : resolve({ ok: false, status, statusText: "Err", json: () => Promise.resolve({}) } as Response),
      });
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  return { calls, fetcher };
}

/** Run a step, then let the promise callbacks it released finish inside act(). */
const settle = (step: () => unknown) =>
  act(async () => {
    step();
    await Promise.resolve();
  });

const label = (r: Resource<{ label: string }>) =>
  r.state === "ready" || r.state === "stale" ? r.envelope.data.label : null;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useResource keeps each answer with its own request", () => {
  it("reports loading at once when the path changes, never the old record", async () => {
    const { calls } = manualFetch();
    const { result, rerender } = renderHook(({ path }) => useResource<{ label: string }>(path), {
      initialProps: { path: A },
    });
    await settle(() => calls[0]!.resolve("decision A"));
    expect(label(result.current)).toBe("decision A");

    rerender({ path: B });
    expect(result.current.state).toBe("loading");
    expect(label(result.current)).toBeNull();
  });

  it("does not show A's record as B's stale data when B fails", async () => {
    const { calls } = manualFetch();
    const { result, rerender } = renderHook(({ path }) => useResource<{ label: string }>(path), {
      initialProps: { path: A },
    });
    await settle(() => calls[0]!.resolve("decision A"));
    rerender({ path: B });
    await waitFor(() => expect(calls.some((c) => c.url === B)).toBe(true));
    await settle(() => calls.find((c) => c.url === B)!.reject());
    expect(result.current.state).toBe("failed");
    expect(label(result.current)).toBeNull();
  });

  it("drops an older answer that arrives after a newer one", async () => {
    vi.useFakeTimers();
    const { calls } = manualFetch();
    const { result } = renderHook(() => useResource<{ label: string }>(A, 1000));
    await settle(() => calls[0]!.resolve("first"));
    await settle(() => vi.advanceTimersByTime(1000)); // refresh #2 in flight
    await settle(() => vi.advanceTimersByTime(1000)); // refresh #3 in flight
    await settle(() => calls[2]!.resolve("newest"));
    await settle(() => calls[1]!.resolve("older, but late"));
    expect(label(result.current)).toBe("newest");
  });

  it("keeps the last verified record, marked stale with when it was received", async () => {
    vi.useFakeTimers();
    const { calls } = manualFetch();
    const { result } = renderHook(() => useResource<{ label: string }>(A, 1000));
    await settle(() => calls[0]!.resolve("verified"));
    const received = result.current.state === "ready" ? result.current.fetchedAt : "";
    await settle(() => vi.advanceTimersByTime(1000));
    await settle(() => calls[1]!.reject(503));
    expect(result.current.state).toBe("stale");
    expect(label(result.current)).toBe("verified");
    if (result.current.state === "stale") {
      expect(result.current.fetchedAt).toBe(received);
      expect(result.current.status).toBe(503);
    }
  });

  it("marks only the server's 404 as not found", async () => {
    const { calls } = manualFetch();
    const missing = renderHook(() => useResource<{ label: string }>(A));
    await settle(() => calls[0]!.reject(404));
    expect(missing.result.current).toMatchObject({ state: "failed", notFound: true, status: 404 });

    const broken = renderHook(() => useResource<{ label: string }>(B));
    await settle(() => calls[1]!.reject(500));
    expect(broken.result.current).toMatchObject({ state: "failed", notFound: false, status: 500 });
  });

  it("does not refresh while paused, and refetches on retry", async () => {
    vi.useFakeTimers();
    const { calls, fetcher } = manualFetch();
    const { result } = renderHook(() => useResource<{ label: string }>(A, 1000, { paused: true }));
    await settle(() => calls[0]!.resolve("held still"));
    await settle(() => vi.advanceTimersByTime(5000));
    expect(fetcher).toHaveBeenCalledTimes(1);
    act(() => result.current.retry());
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});
