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
  tour?: number;
}

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: (search: Record<string, unknown>): TourSearch => {
    const raw = Number(search["tour"]);
    // Clamped, never raised on: a hand-edited step is a typo, not an error.
    return Number.isFinite(raw) && raw > 0 ? { tour: Math.floor(raw) } : {};
  },
  component: function IndexRoute() {
    const { tour } = useSearch({ from: "/" });
    return <Overview tourStep={tour ?? null} />;
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
