import { useEffect, useState } from "react";
import { get, type ApiUrl, type Envelope } from "./client";

export type Resource<T> =
  | { state: "loading" }
  | { state: "ready"; envelope: Envelope<T>; stale: false }
  /** A refresh failed. The last verified response is still shown, and said to be old. */
  | { state: "stale"; envelope: Envelope<T>; stale: true; reason: string }
  | { state: "failed"; reason: string };

/**
 * Fetch once, then refresh on an interval.
 *
 * A failed refresh never blanks the screen: the last verified response is kept
 * and marked stale, because a reader who is shown nothing cannot tell a quiet
 * system from a broken one. A first fetch that fails has nothing to keep, and
 * says so rather than rendering an empty shape that looks like real emptiness.
 */
export function useResource<T>(path: ApiUrl, refreshMs = 15_000): Resource<T> {
  const [resource, setResource] = useState<Resource<T>>({ state: "loading" });

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const load = async () => {
      try {
        const envelope = await get<T>(path, controller.signal);
        if (!cancelled) setResource({ state: "ready", envelope, stale: false });
      } catch (error) {
        if (cancelled || controller.signal.aborted) return;
        const reason = error instanceof Error ? error.message : "request failed";
        setResource((previous) =>
          previous.state === "ready" || previous.state === "stale"
            ? { state: "stale", envelope: previous.envelope, stale: true, reason }
            : { state: "failed", reason },
        );
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), refreshMs);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [path, refreshMs]);

  return resource;
}
