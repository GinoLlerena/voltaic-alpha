import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiUrl } from "../api/client";
import { useCursorPage } from "../api/useCursorPage";

/**
 * `CSA-006`: the paging state the activity feed and decision history share.
 * Fetches are resolved by hand, so the order of answers is the test's choice.
 */

interface Page {
  items: string[];
  next_cursor: string | null;
}

const urlFor = (cursor: string | null) =>
  (cursor ? `/api/v1/activity?cursor=${cursor}` : "/api/v1/activity") as ApiUrl;

const envelope = (data: Page) => ({
  schema_version: "public.v1", source_mode: "LIVE", source_id: "live", source_label: "live",
  observed_at: "2026-10-02T12:00:00+00:00", correlation_id: null, data,
});

interface Call {
  url: string;
  signal: AbortSignal | null | undefined;
  resolve: (page: Page) => void;
}

function manualFetch() {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          calls.push({
            url: String(input),
            signal: init?.signal,
            resolve: (page) =>
              resolve({
                ok: true, status: 200, statusText: "OK",
                json: () => Promise.resolve(envelope(page)),
              } as Response),
          });
        }),
    ),
  );
  return calls;
}

const settle = (step: () => unknown) =>
  act(async () => {
    step();
    await Promise.resolve();
    await Promise.resolve();
  });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useCursorPage", () => {
  it("appends pages in the server's order and passes the cursor back untouched", async () => {
    const calls = manualFetch();
    const { result } = renderHook(() => useCursorPage<Page, string>(urlFor));
    await settle(() => calls[0]!.resolve({ items: ["a", "b"], next_cursor: "opaque=2" }));
    expect(result.current.items).toEqual(["a", "b"]);

    await settle(() => result.current.more());
    expect(calls[1]!.url).toBe("/api/v1/activity?cursor=opaque=2");
    await settle(() => calls[1]!.resolve({ items: ["c"], next_cursor: null }));
    expect(result.current.items).toEqual(["a", "b", "c"]);
    expect(result.current.nextCursor).toBeNull();
  });

  it("drops an older page that answers after the reader asked for the newest", async () => {
    const calls = manualFetch();
    const { result } = renderHook(() => useCursorPage<Page, string>(urlFor));
    await settle(() => calls[0]!.resolve({ items: ["a"], next_cursor: "p2" }));

    await settle(() => result.current.more());
    const older = calls[1]!;
    await settle(() => result.current.newest());
    expect(older.signal?.aborted).toBe(true);

    // The reset's page one, then the stale continuation arriving late anyway.
    const reset = calls.find((c, i) => i > 1 && c.url === "/api/v1/activity")!;
    await settle(() => reset.resolve({ items: ["z", "a"], next_cursor: "p2b" }));
    await settle(() => older.resolve({ items: ["stale"], next_cursor: null }));

    expect(result.current.items).toEqual(["z", "a"]);
    expect(result.current.browsing).toBe(false);
    expect(result.current.nextCursor).toBe("p2b");
  });

  it("holds page one still once browsing begins, even if a refresh was already in flight", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const calls = manualFetch();
    const { result } = renderHook(() => useCursorPage<Page, string>(urlFor, 1_000));
    await settle(() => calls[0]!.resolve({ items: ["a", "b"], next_cursor: "p2" }));

    // A page-one refresh is issued and has not answered...
    await act(async () => {
      vi.advanceTimersByTime(1_000);
      await Promise.resolve();
    });
    const refresh = calls[1]!;
    expect(refresh.url).toBe("/api/v1/activity");

    // ...when the reader asks for older items, fetched from page one's cursor.
    await settle(() => result.current.more());
    await settle(() => calls[2]!.resolve({ items: ["c"], next_cursor: null }));
    // The refresh lands with a newer page one. Showing it above "c" would hide
    // whatever fell between the two pages.
    await settle(() => refresh.resolve({ items: ["new", "a"], next_cursor: "p2x" }));

    await waitFor(() => expect(result.current.items).toEqual(["a", "b", "c"]));
    expect(result.current.browsing).toBe(true);
  });

  it("does not page past the end, or twice at once", async () => {
    const calls = manualFetch();
    const { result } = renderHook(() => useCursorPage<Page, string>(urlFor));
    await settle(() => calls[0]!.resolve({ items: ["a"], next_cursor: "p2" }));
    await settle(() => result.current.more());
    await settle(() => result.current.more());
    expect(calls.filter((c) => c.url.includes("cursor="))).toHaveLength(1);
  });
});
