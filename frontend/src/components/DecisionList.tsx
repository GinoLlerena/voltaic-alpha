import { Link } from "@tanstack/react-router";
import type { Schemas } from "../api/client";
import { marketSpan, marketTime } from "./time";

type Entry = Schemas["ListEntryOut"];
type Item = Schemas["DecisionListItem"];

/** What a row needs, whether it came from the grouped list or a history page. */
export type Row = Pick<
  Item,
  "decision_id" | "instrument" | "outcome" | "direction" | "reason_codes" | "decided_at"
> &
  Partial<Pick<Entry, "count" | "first_decided_at">>;

/** A reason code as words. The code itself is in the decision's evidence. */
export const reasonText = (codes: string[]): string =>
  codes.length === 0 ? "no reason recorded" : codes.map((c) => c.replaceAll("_", " ")).join(", ");

/**
 * One decision as a row: instrument, what it did, why, and when.
 *
 * `PUI-008`: every value is a typed field from the server. The row used to
 * split the dashboard's two-line label, so the reader parsed a snapshot ID to
 * learn what and when. The grouping and run count still come from the server:
 * `RUI-VAL-009` was a grouping rule that hid positions, and a second
 * implementation here could hide different ones.
 */
export function DecisionRow({ row }: { row: Row }) {
  const count = row.count ?? 1;
  const when =
    row.decided_at === null
      ? "time not recorded"
      : count > 1 && row.first_decided_at
        ? marketSpan(row.first_decided_at, row.decided_at)
        : marketTime(row.decided_at);
  return (
    // A link, not a button: a decision a reader can send to someone else is
    // the point of `CIIP-004`'s shareable steps.
    <Link to="/decisions/$digest" params={{ digest: row.decision_id }} data-outcome={row.outcome}>
      <span className="name">
        {row.instrument ?? "instrument not recorded"}
        <span className="outcome">
          {row.outcome === "position" ? `Position · ${row.direction}` : "No trade"}
        </span>
      </span>
      <span className="summary">
        {row.outcome === "position" ? "opened a Paper position" : reasonText(row.reason_codes)}
      </span>
      <time className="when" {...(row.decided_at ? { dateTime: row.decided_at, title: row.decided_at } : {})}>
        {when}
      </time>
      {count > 1 ? (
        <span className="count" title={`${count} identical consecutive outcomes`}>
          ×{count}
        </span>
      ) : null}
    </Link>
  );
}

export function DecisionList({ rows, empty }: { rows: Row[]; empty?: string }) {
  if (rows.length === 0) {
    return <p className="empty">{empty ?? "This source holds no decisions."}</p>;
  }
  return (
    <ul className="decisions" data-testid="decision-list">
      {rows.map((row) => (
        <li key={row.decision_id}>
          <DecisionRow row={row} />
        </li>
      ))}
    </ul>
  );
}
