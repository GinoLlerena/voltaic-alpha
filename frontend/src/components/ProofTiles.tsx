import type { Schemas } from "../api/client";

type Tile = Schemas["ProofTileOut"];

/**
 * The first viewport's three claims, each derived by the server.
 *
 * `CIIP-003` made these derived rather than typed; the browser's job is to show
 * the mode and source the server attached, not to decide whether a number looks
 * impressive. An unavailable tile stays visibly unavailable.
 */
export function ProofTiles({ tiles }: { tiles: Tile[] }) {
  return (
    <ul className="proof" data-testid="proof-tiles">
      {tiles.map((tile) => (
        <li key={tile.label} className={tile.available ? "p" : "p na"} data-available={String(tile.available)}>
          <span className="n">{tile.value}</span>
          <span className="l">{tile.label}</span>
          <span className="mode">{tile.mode}</span>
          <span className="src">{tile.source}</span>
          {tile.detail ? <span className="src">{tile.detail}</span> : null}
        </li>
      ))}
    </ul>
  );
}
