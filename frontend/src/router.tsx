import {
  Link,
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import type { RouterHistory } from "@tanstack/react-router";
import { asView, DEFAULT_VIEW, type View } from "./api/views";
import { Activity } from "./routes/Activity";
import { Decision } from "./routes/Decision";
import { Overview } from "./routes/Overview";

/**
 * Routing exists so a selection is a link.
 *
 * `CIIP-004` made the dashboard's tour steps shareable and found the defect that
 * mattered: a step that cannot address its own decision silently shows another.
 * Here the decision is in the path and the tour step in the search, so both
 * survive a copied URL.
 */
const rootRoute = createRootRoute({
  component: () => (
    <main>
      <header>
        <Link to="/">
          <h1>Options Alpha</h1>
        </Link>
        <p className="sub">auditable execution firewall</p>
        <nav>
          <Link to="/">Decisions</Link>
          <Link to="/activity">Activity</Link>
        </nav>
      </header>
      <Outlet />
    </main>
  ),
});

export interface TourSearch {
  // `| undefined` is deliberate: validation returns a rejected value as an
  // explicit undefined so it overrides the raw search merged from the root.
  tour?: number | undefined;
  view?: View | undefined;
}

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: (search: Record<string, unknown>): TourSearch => {
    const raw = Number(search["tour"]);
    const view = asView(search["view"]);
    // Clamped, never raised on: a hand-edited step or view is a typo, not an error.
    // Both keys are always returned, even as undefined: the root route keeps the
    // raw search and the router merges it underneath, so omitting a rejected
    // value would let the raw one - `?view=Bogus` - show through.
    return {
      tour: Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : undefined,
      view,
    };
  },
  component: function IndexRoute() {
    const { tour, view } = useSearch({ from: "/" });
    // Re-checked where it is used: a view the server rejects would turn a
    // mistyped link into an error panel instead of the default list.
    return <Overview tourStep={tour ?? null} view={asView(view) ?? DEFAULT_VIEW} />;
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

const routeTree = rootRoute.addChildren([indexRoute, decisionRoute, activityRoute]);

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
