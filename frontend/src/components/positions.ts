import type { Schemas } from "../api/client";

type MarkState = Schemas["PositionSummaryOut"]["mark_state"];

/**
 * What each served mark state means, in a reader's words.
 *
 * A mark is a recorded observation, never a live price (PUI4 §3.5). The state
 * comes from the server; this names it. A test holds the keys to the contract,
 * so a state the server adds cannot be shown as nothing.
 */
export const MARK_STATE: Record<MarkState, { label: string; meaning: string }> = {
  never_observed: {
    label: "never observed",
    meaning: "No mark has been recorded for this position.",
  },
  unreadable: {
    label: "last mark unreadable",
    meaning: "The newest observation could not read the spread's value. That is recorded, not zero.",
  },
  current: {
    label: "current mark",
    meaning: "Observed within the last five minutes, while the market is open.",
  },
  last_session: {
    label: "last session's mark",
    meaning: "The market is closed. This is the last mark of the latest session.",
  },
  stale: {
    label: "stale mark",
    meaning: "The market is open and this mark is more than five minutes old.",
  },
  final: {
    label: "final mark",
    meaning: "The position is no longer held, so it is no longer marked.",
  },
};

/** Mark states that need the owner's attention on a position still held. */
export const MARK_NEEDS_ATTENTION: readonly MarkState[] = ["stale", "unreadable"];

export const STATE_FILTERS = ["open", "closed", "all"] as const;
export type StateFilter = (typeof STATE_FILTERS)[number];
export const DEFAULT_STATE: StateFilter = "open";

export function asStateFilter(raw: unknown): StateFilter | undefined {
  return (STATE_FILTERS as readonly unknown[]).includes(raw) ? (raw as StateFilter) : undefined;
}
