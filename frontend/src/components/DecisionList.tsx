import type { Schemas } from "../api/client";

type Entry = Schemas["ListEntryOut"];

/**
 * The decision list, grouped by the server.
 *
 * The grouping, the label and the run count come from `/decisions/grouped`, not
 * from arithmetic here: `RUI-VAL-009` was a grouping rule that hid positions,
 * and a second implementation in the browser could hide different ones.
 */
export function DecisionList({
  entries,
  selected,
  onSelect,
}: {
  entries: Entry[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  if (entries.length === 0) {
    return <p className="empty">This source holds no decisions.</p>;
  }
  return (
    <ul className="decisions" data-testid="decision-list">
      {entries.map((entry) => {
        const [name, summary] = entry.label.split("\n");
        return (
          <li key={entry.decision_id}>
            <button
              type="button"
              aria-current={entry.decision_id === selected}
              onClick={() => onSelect(entry.decision_id)}
            >
              <span className="name">{name}</span>
              <span className="summary">{summary}</span>
              {entry.count > 1 ? (
                <span className="count" title={`${entry.count} identical consecutive outcomes`}>
                  ×{entry.count}
                </span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
