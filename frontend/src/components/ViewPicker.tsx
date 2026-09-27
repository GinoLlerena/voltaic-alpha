import { Link } from "@tanstack/react-router";
import { DEFAULT_VIEW, VIEWS, type View } from "../api/views";

/**
 * Which decisions the list shows. Links rather than buttons: the chosen view is
 * part of the URL, so "the refusals" can be sent to someone - the same rule as
 * a selected decision (`RUI-3`: every selection is shareable).
 *
 * Parity with the dashboard's "Show" control. Without it, the React list was
 * fixed to the Notable view: on 26 September 2026 that was 1 row of 654.
 */
export function ViewPicker({ current }: { current: View }) {
  return (
    <nav className="views" aria-label="Decision views">
      {VIEWS.map((view) => (
        <Link
          key={view}
          to="/"
          search={view === DEFAULT_VIEW ? {} : { view }}
          // The router marks a Link current on a path match alone, and every
          // view shares the path "/" - so without an exact search comparison it
          // announced Notable as current whatever the view. Exact matching makes
          // its marker agree with ours; ours covers URLs that carry other params.
          activeOptions={{ exact: true, includeSearch: true }}
          aria-current={view === current ? "page" : undefined}
        >
          {view}
        </Link>
      ))}
    </nav>
  );
}
