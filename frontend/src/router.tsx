import {
  Link,
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import type { RouterHistory } from "@tanstack/react-router";
import { asView, DEFAULT_VIEW, type View } from "./api/views";
import { Activity } from "./routes/Activity";
import { Decision } from "./routes/Decision";
import { Decisions } from "./routes/Decisions";
import { Evidence } from "./routes/Evidence";
import { Today } from "./routes/Today";

/**
 * Routing exists so a selection is a link.
 *
 * `CIIP-004` made the dashboard's tour steps shareable and found the defect that
 * mattered: a step that cannot address its own decision silently shows another.
 * Here the decision is in the path and the tour step in the search, so both
 * survive a copied URL.
 *
 * PUI Phase 2: `/` is Today; the list moved to `/decisions` and the tour to
 * `/evidence`. Links shared before the move (`/?view=…`, `/?tour=…`) redirect
 * to where their content now lives rather than landing on a different page.
 */
const rootRoute = createRootRoute({
  component: () => (
    <main>
      <header>
        <Link to="/">
          <h1>Options Alpha</h1>
        </Link>
        <nav aria-label="Primary">
          <Link to="/" activeOptions={{ exact: true }}>
            Today
          </Link>
          <Link to="/decisions">Decisions</Link>
          <Link to="/activity">Activity</Link>
          <Link to="/evidence" className="secondary">
            Evidence
          </Link>
        </nav>
      </header>
      <Outlet />
    </main>
  ),
});

/** A positive whole step, or undefined: a hand-edited step is a typo, not an error. */
const tourStep = (raw: unknown): number | undefined => {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : undefined;
};

export interface LegacySearch {
  // `| undefined` is deliberate: validation returns a rejected value as an
  // explicit undefined so it overrides the raw search merged from the root.
  tour?: number | undefined;
  view?: View | undefined;
}

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: (search: Record<string, unknown>): LegacySearch => ({
    tour: tourStep(search["tour"]),
    view: asView(search["view"]),
  }),
  beforeLoad: ({ search }) => {
    if (search.tour !== undefined) {
      // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect idiom
      throw redirect({ to: "/evidence", search: { tour: search.tour } });
    }
    if (search.view !== undefined) {
      // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect idiom
      throw redirect({ to: "/decisions", search: { view: search.view } });
    }
  },
  component: Today,
});

export interface DecisionsSearch {
  view?: View | undefined;
}

const decisionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/decisions",
  validateSearch: (search: Record<string, unknown>): DecisionsSearch => ({
    view: asView(search["view"]),
  }),
  component: function DecisionsRoute() {
    const { view } = useSearch({ from: "/decisions" });
    // Re-checked where it is used: a view the server rejects would turn a
    // mistyped link into an error panel instead of the default list.
    return <Decisions view={asView(view) ?? DEFAULT_VIEW} />;
  },
});

const decisionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/decisions/$digest",
  component: function DecisionRoute() {
    const { digest } = useParams({ from: "/decisions/$digest" });
    return <Decision digest={digest} />;
  },
});

const activityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/activity",
  component: Activity,
});

export interface EvidenceSearch {
  tour?: number | undefined;
}

const evidenceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/evidence",
  validateSearch: (search: Record<string, unknown>): EvidenceSearch => ({
    tour: tourStep(search["tour"]),
  }),
  component: function EvidenceRoute() {
    const { tour } = useSearch({ from: "/evidence" });
    return <Evidence tourStep={tour ?? null} />;
  },
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  decisionsRoute,
  decisionRoute,
  activityRoute,
  evidenceRoute,
]);

export function buildRouter(history?: RouterHistory) {
  return createRouter({ routeTree, ...(history ? { history } : {}) });
}

export function App({ history }: { history?: RouterHistory }) {
  return <RouterProvider router={buildRouter(history)} />;
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof buildRouter>;
  }
}
