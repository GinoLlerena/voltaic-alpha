import { useCallback, useEffect, useRef, useState } from "react";
import { get, type ApiUrl } from "./client";
import { dataOf, useResource, type Resource } from "./useResource";

interface CursorPage<Item> {
  items: Item[];
  next_cursor: string | null;
}

interface Browsing<Page, Item> {
  /** The first-page URL this state belongs to. */
  key: ApiUrl;
  /** Page one as it was when the reader asked for older items, held still. */
  frozen: Page | null;
  extra: Item[];
  /** `undefined` until a further page is fetched: the server's first cursor stands. */
  cursor: string | null | undefined;
  loading: boolean;
  failed: string | null;
}

export interface CursorList<Page, Item> {
  /** Page one's request: its state, envelope and retry. */
  first: Resource<Page>;
  /** Everything shown, in the server's order; null until page one has answered. */
  items: Item[] | null;
  /** Where the next page starts, exactly as served; null when the list ends. */
  nextCursor: string | null;
  loading: boolean;
  failed: string | null;
  /** Older pages are shown, so page one is held still rather than refreshed. */
  browsing: boolean;
  more: () => void;
  newest: () => void;
}

function start<Page, Item>(key: ApiUrl): Browsing<Page, Item> {
  return { key, frozen: null, extra: [], cursor: undefined, loading: false, failed: null };
}

/**
 * A server-ordered list, page one refreshed, older pages appended on request.
 *
 * `CSA-006`: the activity feed and the decision history each carried a copy of
 * this, and both copies shared two races. A "show older" request still in
 * flight when the reader pressed "show the newest" appended its stale page to
 * the reset list; and a page-one refresh already issued when browsing began
 * could replace page one under the older pages fetched from its cursor,
 * opening a silent gap. Here every continuation belongs to a generation that a
 * reset ends (and aborts), and page one is frozen the moment browsing starts.
 *
 * The browser never sorts, merges or builds a cursor (`RUI-5`): pages are
 * appended in the order given and `next_cursor` is passed back untouched.
 */
export function useCursorPage<Page extends CursorPage<Item>, Item>(
  urlFor: (cursor: string | null) => ApiUrl,
  refreshMs = 15_000,
): CursorList<Page, Item> {
  const key = urlFor(null);
  const [held, setHeld] = useState<Browsing<Page, Item>>(() => start(key));
  // A list for another first-page URL starts over: nothing carries across.
  const state = held.key === key ? held : start<Page, Item>(key);
  const browsing = state.frozen !== null;

  const first = useResource<Page>(key, refreshMs, { paused: browsing });
  const live = dataOf(first);
  const page = state.frozen ?? live;

  const generation = useRef(0);
  const inflight = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      generation.current += 1;
      inflight.current?.abort();
    },
    [key],
  );

  const nextCursor = state.cursor === undefined ? (page ? page.next_cursor : null) : state.cursor;

  const more = useCallback(() => {
    if (nextCursor === null || state.loading || page === null) return;
    const mine = generation.current;
    const controller = new AbortController();
    inflight.current = controller;
    const snapshot = page;
    setHeld({ ...state, frozen: state.frozen ?? snapshot, loading: true, failed: null });
    get<Page>(urlFor(nextCursor), controller.signal).then(
      (older) => {
        if (generation.current !== mine) return;
        setHeld((s) =>
          s.key !== key
            ? s
            : { ...s, extra: [...s.extra, ...older.data.items], cursor: older.data.next_cursor, loading: false },
        );
      },
      (error: unknown) => {
        if (generation.current !== mine || controller.signal.aborted) return;
        const reason = error instanceof Error ? error.message : "the request failed";
        setHeld((s) => (s.key !== key ? s : { ...s, loading: false, failed: reason }));
      },
    );
  }, [key, nextCursor, page, state, urlFor]);

  const newest = useCallback(() => {
    generation.current += 1;
    inflight.current?.abort();
    inflight.current = null;
    setHeld(start(key));
    first.retry();
  }, [key, first]);

  return {
    first,
    items: page ? [...page.items, ...state.extra] : null,
    nextCursor,
    loading: state.loading,
    failed: state.failed,
    browsing,
    more,
    newest,
  };
}
