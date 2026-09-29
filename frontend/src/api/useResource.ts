import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, get, type ApiUrl, type Envelope } from "./client";

type Settled<T> =
  | { state: "loading" }
  | { state: "ready"; envelope: Envelope<T>; stale: false; fetchedAt: string }
  /** A refresh failed. The last verified response is still shown, and said to be old. */
  | {
      state: "stale";
      envelope: Envelope<T>;
      stale: true;
      reason: string;
      status: number | null;
      /** When the response still on screen was received. */
      fetchedAt: string;
    }
  /** Nothing verified to show. `notFound` only for the server's own 404. */
  | { state: "failed"; reason: string; status: number | null; notFound: boolean };

export type Resource<T> = Settled<T> & { retry: () => void };

/**
 * Fetch once, then refresh on an interval.
 *
 * A failed refresh never blanks the screen: the last verified response is kept
 * and marked stale, because a reader who is shown nothing cannot tell a quiet
 * system from a broken one. A first fetch that fails has nothing to keep, and
 * says so rather than rendering an empty shape that looks like real emptiness.
 *
 * `PUI-002`: what is held belongs to one path. When the path changes the hook
 * reports loading at once, so decision A is never shown under decision B's URL,
 * and a failure for B can never mark A's response as B's stale data. Within a
 * path, a response older than one already applied is dropped, so a slow refresh
 * cannot overwrite a newer answer.
 *
 * `paused` stops the interval without refetching, for a view the reader is
 * browsing and does not want to shift under them (`PUI-009`).
 */
export function useResource<T>(
  path: ApiUrl,
  refreshMs = 15_000,
  { paused = false }: { paused?: boolean } = {},
): Resource<T> {
  const [held, setHeld] = useState<{ path: ApiUrl; resource: Settled<T> }>({
    path,
    resource: { state: "loading" },
  });
  const [attempt, setAttempt] = useState(0);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    let issued = 0;
    let applied = 0;

    const load = async () => {
      const seq = ++issued;
      try {
        const envelope = await get<T>(path, controller.signal);
        if (cancelled || seq < applied) return;
        applied = seq;
        setHeld({
          path,
          resource: { state: "ready", envelope, stale: false, fetchedAt: new Date().toISOString() },
        });
      } catch (error) {
        if (cancelled || controller.signal.aborted || seq < applied) return;
        applied = seq;
        const reason = error instanceof Error ? error.message : "request failed";
        const status = error instanceof ApiError ? error.status : null;
        setHeld((previous) => {
          const mine = previous.path === path ? previous.resource : null;
          return {
            path,
            resource:
              mine && (mine.state === "ready" || mine.state === "stale")
                ? {
                    state: "stale",
                    envelope: mine.envelope,
                    stale: true,
                    reason,
                    status,
                    fetchedAt: mine.fetchedAt,
                  }
                : { state: "failed", reason, status, notFound: status === 404 },
          };
        });
      }
    };

    void load();
    const timer = window.setInterval(() => {
      if (!pausedRef.current) void load();
    }, refreshMs);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [path, refreshMs, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const resource: Settled<T> = held.path === path ? held.resource : { state: "loading" };
  return { ...resource, retry };
}

/** The data of a resource that has some, verified or last-known; otherwise null. */
export function dataOf<T>(resource: Resource<T>): T | null {
  return resource.state === "ready" || resource.state === "stale" ? resource.envelope.data : null;
}
