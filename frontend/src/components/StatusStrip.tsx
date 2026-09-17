import type { Schemas } from "../api/client";

type Item = Schemas["StatusItemOut"];

/**
 * The status strip, rendered from the server's own tone and `known` flag.
 *
 * A client that decided tone itself could make an unknown look healthy, which is
 * the defect `CIIP-001` fixed on the dashboard. Unknown is rendered as unknown,
 * and carries the reason the server gave.
 */
export function StatusStrip({ items }: { items: Item[] }) {
  return (
    <ul className="status" data-testid="status-strip">
      {items.map((item) => (
        <li key={item.label} className={`tone-${item.tone}`} data-known={String(item.known)}>
          <span className="k">{item.label}</span>
          <span className="v">{item.value}</span>
          <span className="src">{item.source}</span>
          {item.reason ? <span className="why">{item.reason}</span> : null}
        </li>
      ))}
    </ul>
  );
}
