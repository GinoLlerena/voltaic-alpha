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
import { asStateFilter, DEFAULT_STATE, type StateFilter } from "./components/positions";
import { Position } from "./routes/Position";
import { Positions } from "./routes/Positions";
import { asHorizon, DEFAULT_HORIZON, type Horizon, Review } from "./routes/Review";
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
          <Link to="/positions">Positions</Link>
          <Link to="/activity">Activity</Link>
          <Link to="/review">Review</Link>
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
  /** One New York market day (YYYY-MM-DD): what a review journal row links to. */
  day?: string | undefined;
}

const marketDate = (raw: unknown): string | undefined =>
  typeof raw === "string" && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : undefined;

const decisionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/decisions",
  validateSearch: (search: Record<string, unknown>): DecisionsSearch => ({
    view: asView(search["view"]),
    day: marketDate(search["day"]),
  }),
  component: function DecisionsRoute() {
    const { view, day } = useSearch({ from: "/decisions" });
    // Re-checked where it is used: a view the server rejects would turn a
    // mistyped link into an error panel instead of the default list.
    return <Decisions view={asView(view) ?? DEFAULT_VIEW} day={marketDate(day) ?? null} />;
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

export interface PositionsSearch {
  state?: StateFilter | undefined;
}

const positionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/positions",
  validateSearch: (search: Record<string, unknown>): PositionsSearch => ({
    state: asStateFilter(search["state"]),
  }),
  component: function PositionsRoute() {
    const { state } = useSearch({ from: "/positions" });
    return <Positions state={asStateFilter(state) ?? DEFAULT_STATE} />;
  },
});

const positionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/positions/$positionId",
  component: function PositionRoute() {
    const { positionId } = useParams({ from: "/positions/$positionId" });
    return <Position positionId={positionId} />;
  },
});

export interface ReviewSearch {
  horizon?: Horizon | undefined;
}

const reviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/review",
  validateSearch: (search: Record<string, unknown>): ReviewSearch => ({
    horizon: asHorizon(search["horizon"]),
  }),
  component: function ReviewRoute() {
    const { horizon } = useSearch({ from: "/review" });
    return <Review horizon={asHorizon(horizon) ?? DEFAULT_HORIZON} />;
  },
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  decisionsRoute,
  decisionRoute,
  positionsRoute,
  positionRoute,
  activityRoute,
  reviewRoute,
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
