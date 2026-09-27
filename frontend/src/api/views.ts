/**
 * The decision-list views the server offers, in its order.
 *
 * Named here because the router validates `?view=` before any request is made,
 * so the list cannot be fetched from the server first. A test holds it to the
 * `view` pattern in the committed OpenAPI document: if the server's list
 * changes, this fails rather than quietly offering a view that 422s.
 */
export const VIEWS = ["Notable", "Positions", "Refusals", "Everything"] as const;
export type View = (typeof VIEWS)[number];
export const DEFAULT_VIEW: View = "Notable";

export function asView(raw: unknown): View | undefined {
  return (VIEWS as readonly unknown[]).includes(raw) ? (raw as View) : undefined;
}
