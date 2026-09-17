# Options Alpha React UI/UX Redesign v0.1

*Trader-readable decisions with proof-carrying execution authority*

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Date | 10 September 2026 |
| Status | Recommended implementation baseline; presentation-layer change only |
| Product direction | AI options research and decision workspace with a proof-carrying execution firewall |
| Primary users | Options trader/operator, reviewer, hackathon judge |
| Recommended frontend | React + TypeScript + Vite, behind a GET-only FastAPI presentation API |
| Migration model | Incremental strangler; Streamlit remains the reference/fallback until parity |
| Trading boundary | Unchanged: Paper only, deterministic authority, no browser-to-broker path |
| Work prefix | `RUI-` |

## 1. Executive decision

Move the presentation layer to React now, but do not rewrite the execution core
or translate `app.py` directly into React components.

The correct sequence is:

1. freeze typed, redacted, read-only presentation contracts in Python;
2. expose those contracts through a versioned FastAPI `GET` API;
3. build a React application around trader and reviewer tasks;
4. run React and Streamlit against the same fixtures until parity gates pass;
5. cut over only when truth, safety, accessibility, responsiveness, and proof
   export are at least as strong as the existing dashboard.

This is now a better decision than the earlier recommendation to defer React.
The deferral condition was stable read models. The current codebase has since
added focused presentation services for status, selected-decision lineage,
proof tiles, explanation, tour scenes, activity, artifact correlation, and
redacted export. They are not yet public API contracts, but they are enough to
make contract extraction the next bounded step rather than a speculative rewrite.

The target promise is:

> **Understand the trade in 30 seconds. Verify every authority decision in one click.**

The public surface remains credential-free and read-only. React improves
perceptibility, workflow, routing, charts, responsive behavior, and testability;
it does not gain financial authority.

## 2. Scope and review method

This recommendation combines three specialist reviews:

- **UI/UX:** information hierarchy, interaction, responsive behavior,
  accessibility, progressive disclosure, and presentation-system quality;
- **options trading/product:** decision speed, structure comprehension,
  risk units, position attention, data quality, and honest performance context;
- **React/frontend architecture:** contracts, routing, server state, component
  boundaries, testing, delivery risk, and incremental migration.

The review covered:

- the 919-line Streamlit application in [`app.py`](../../app.py);
- the current presentation services under
  [`src/options_alpha_lab/presentation`](../../src/options_alpha_lab/presentation);
- the persistence schema and committed evidence database;
- the current README, frontend design, trading design, infrastructure plan, and
  competitor-informed improvement plan;
- both Alpha Hunter winner analyses and both TradePilot runner-up analyses;
- the dashboard, presentation, isolation, proof, and export tests; and
- the locked Python environment in `uv.lock`.

A rendered browser session was unavailable during this review. Visual findings
are therefore derived from the rendered structure, CSS, Streamlit component
tree, and existing render tests rather than claimed as a pixel-level browser
audit. Browser and device inspection is a mandatory release gate.

## 3. Current-state verdict

The current dashboard is a credible forensic evidence viewer. It is not yet a
practical trader workspace.

### 3.1 What is already strong and must survive

- A positive product promise and three proof tiles derived from records or
  versioned artifacts rather than typed marketing values.
- Dynamic, source-aware status with `UNKNOWN` behavior instead of safe-looking
  hardcoded defaults.
- A seven-stage authority rail that visually fences the model into the memo.
- Five detailed evidence views: evidence/setup, model memo, approval lineage,
  outcome, and guards/state.
- A six-scene, URL-addressable guided path over recorded evidence.
- A derived “Why this decision?” explanation in authority order.
- Selected-decision lineage isolation across intent, request, order, fill, and
  position records.
- Explicit correlation behavior when a lifecycle artifact and selected decision
  do not describe the same evaluation.
- Run-length grouping of repetitive refusals and a bounded 400-decision query.
- Redacted deterministic proof export.
- Honest disclosure of Paper, indicative quotes, the tiny sample, negative
  execution friction, and a no-effect model ablation.
- A tested absence of broker or execution controls in the public dashboard.

React must preserve these as requirements, not reinterpret them as implementation
details of Streamlit.

### 3.2 What prevents it from being a trader workspace

| Current behavior | Trader/UX consequence | Redesign disposition |
|---|---|---|
| The interface begins with proof and then five forensic tabs | The user must reconstruct the actual trade before understanding the proof | Add a human-readable Decision Ticket and task-oriented workspaces |
| Decisions are labeled from snapshot IDs and multiline outcome text | Slow triage; hard to compare direction, structure, risk, age, and state | Use a dense, filterable decision table with trader fields |
| The selected tab is widget state rather than a durable route | Details are difficult to share, restore, bookmark, or open in a new tab | Put decision, section, source, filters, and tour step in the URL |
| The selected structure shows raw contract symbols, quantity, debit, and max loss | A trader must parse OCC symbols and infer units and payoff | Add a leg matrix, payoff, breakeven, max gain, return on risk, DTE, and quote quality |
| Debit is not consistently labeled per-share versus per-spread | `$3.20` can be mistaken for `$3.20` total rather than `$320` per contract | Show both units and multiplier everywhere |
| Quote fields in `leg_quotes` are not surfaced as a coherent decision panel | Liquidity and freshness are harder to assess than they should be | Show bid/ask, relative spread, delta, IV, OI, volume, feed, and quote age |
| No chart is currently rendered | The product reads as a report, and option risk is harder to grasp | Ship only evidence-supported payoff/lifecycle visuals; persist bars before OHLC |
| The authority rail repeats in every tab as the dominant spatial device | Strong audit cue, but it displaces the trader's setup/structure/risk mental model | Retain as a compact trust spine and expand it in Audit/Proof |
| Amber represents model output, counter-evidence, and warning states | Meaning is overloaded and can be misread | Use violet for model, amber for attention, blue/teal for deterministic/verified |
| Raw `str(datetime)` values appear in several places | Market-session meaning and timezone are ambiguous | Render New York market time first and UTC in details |
| The application is dark-only despite the design specification | Accessibility and environment preference are not fully implemented | Support tested light and dark semantic tokens |
| `--accent`, `--fg`, `--line`, and `--bad` are referenced but never defined | Several tour, proof, heading, and critical-border declarations are invalid and fall back inconsistently | Make tokens typed/documented and fail visual tests when a semantic token is missing |
| `--dim` is about 3.39:1 on the main background, 3.10:1 on panels, and 2.86:1 on secondary panels | Normal metadata text misses the 4.5:1 WCAG AA target | Raise contrast at the token level and test every token pairing |
| Many labels use `0.58–0.72rem` (roughly 9–12 px) | Provenance and authority labels become difficult to read | Use 12 px as an absolute metadata floor and 14 px for dense operational data |
| The only media query handles reduced motion; the authority flow keeps `min-width: 820px` | Key content overflows rather than transforming for tablet/mobile | Implement explicit 360/736/1024/1440 layouts and vertical mobile structures |
| Custom section headings are styled `<div>` elements and many rails/cards lack structural semantics | Visual hierarchy is not reliably exposed to assistive technology | Use semantic headings, lists, tables, figures, progress descriptions, and landmarks |
| Google fonts are fetched at runtime | Offline/fallback rendering and the previous system-font requirement diverge | Use a local/system-first type stack; external fonts are noncritical and optional |
| Guided scenes identify a target tab, but `active_scene.tab` is never applied | The right decision can open on the wrong explanatory section | Make every scene a real route that selects both record and section |
| Hero, proof tiles, system status, disclosure, tour, export, and explanation precede every detail tab | Task content is pushed far below the fold and repeated on every inspection | Keep global status compact; place context-specific proof beside the relevant task |
| CSS, queries, navigation, data selection, and rendering share one 51.5 KB file | Change risk and visual QA cost rise with every new workspace | Separate API DTOs, route features, design primitives, and data adapters |
| Streamlit sidebar/tabs constrain mobile transformation and keyboard flows | Responsive behavior cannot meet the previous redlines reliably | Build explicit responsive navigation and focus behavior in React |

### 3.3 Product distinction to retain

The winner and runner-up looked more complete because their product surface was
immediately legible. Options Alpha has the stronger proof, options structure,
durable lifecycle, and broker-truth boundary. The redesign should combine these
advantages rather than imitate a retail terminal.

The product is not “an AI that trades for you.” It is:

> An options decision and audit workspace where AI contributes bounded research,
> deterministic policy owns risk and authority, and every broker outcome remains
> traceable to evidence.

## 4. Notes retained from the hackathon winner analyses

### 4.1 Alpha Hunter — adopt

| Lesson | Prior findings | Application here |
|---|---|---|
| Name a memorable product category | `CWA-001`, `WA` §8 | Lead with an AI options decision workspace, not an architecture disclaimer |
| Make the full lifecycle visible | `CWA-002`, `CWA-027`, `WA-015` | Use one compact Observe → Qualify → Review → Risk → Authorize → Reconcile spine |
| Make strategies product objects | `CWA-003`, `CWA-REC-006` | Introduce research candidates only after durable catalog and outcome records exist |
| Use progressive disclosure | `CWA-004`, `CWA-REC-004` | Put plain-language trade understanding above hashes and raw records |
| Make the system feel alive | `CWA-005` | Render durable worker/audit activity, current owner, next check, and incidents |
| Use trading-native visuals | `CWA-006`, `WA-015` | Add payoff and lifecycle visuals now; add candles only after the bars are persisted |
| Use a familiar React stack | `CWA-007`, `WA-015` | Adopt React/TypeScript/Vite with a disciplined component and test architecture |
| Optimize the demo surface | `CWA-008`, `CWA-032` | Keep a purpose-built, deterministic guided route backed by recorded evidence |

### 4.2 Alpha Hunter — reject

- No hardcoded backtest, robustness, health, or AI-council metric.
- No synthetic market fallback without a source-mode label.
- No attractive control that is unimplemented or lacks real authority semantics.
- No broker acceptance rendered as a fill.
- No in-memory audit trail presented as durable history.
- No inaccessible glassmorphism, low contrast, or color-only state.
- No natural-language public mutation path.

The reusable lesson is presentation clarity, not Alpha Hunter's backend or
execution semantics.

### 4.3 TradePilot — adopt

| Lesson | Prior findings | Application here |
|---|---|---|
| Lead with a positive outcome | `CTA-030` | Product promise first; limitations remain visible immediately below |
| Repeat one story across surfaces | `CTA-031` | Use the same lifecycle vocabulary in Overview, Decisions, Activity, Tour, README, and deck |
| Build a video-native artifact | `CTA-032`, `RA-019` | Keep `/tour/:scene` stable, deterministic, pauseable, and visibly labeled |
| Make the business workflow legible | `CTA-033` | Show Decisions, Positions, Activity/Incidents, Audit/Proof, and future Research without fake tenancy |
| Show the agent working | `CTA-034` | Stream only durable server events; never synthesize a “thinking” animation in the browser |
| Be candid about negative results | `CTA-035` | Present the losing Paper round trip and no-effect ablation as concise trust evidence |
| Handle partial failure gracefully | `CTA-026` | Preserve the last verified state and identify the unavailable dependency/source |

### 4.4 TradePilot — reject

- No mixing connected, demonstrative, derived, and hardcoded values without
  prominent provenance.
- No decorative API, environment, security, or settings controls.
- No shared broker account hidden beneath multi-user product theater.
- No model self-confidence treated as independent risk evidence.
- No browser-created trade event or optimistic lifecycle update.
- No untested frontend expansion or accepted lint failures.
- No equities-shaped UI that hides the actual options legs, expiry, liquidity,
  assignment, multiplier, and defined-risk payoff.

### 4.5 Synthesis

The previous analyses all converge on one priority:

> Make Options Alpha's existing truth as easy to perceive as the winners'
> ambition, without copying their fabricated breadth or weaker authority model.

## 5. Users, jobs, and access boundaries

### 5.1 Trader/operator

Primary jobs:

1. find what requires attention;
2. understand why a setup qualified or refused;
3. understand the exact options structure and its units;
4. assess defined risk, liquidity, invalidation, and exit state;
5. monitor broker/local lifecycle and ambiguity;
6. inspect provenance when a number or state is questioned.

This version remains read-only. Authenticated mutations are a separate product
and security design task after protected control endpoints exist.

### 5.2 Reviewer/risk owner

Primary jobs:

- reconstruct evidence, memo, policy, intent, request, broker state, and fill;
- verify selected-decision isolation and artifact correlation;
- inspect data freshness, reason codes, policy/formula/schema versions, and
  reconciliation completeness;
- download a redacted proof package.

### 5.3 Judge/evaluator

Primary jobs:

- understand the product within ten seconds;
- complete a qualified, refusal, and recovery journey within 90 seconds;
- see one memorable distinction: the model can advise but cannot authorize;
- verify that every visible claim carries a source and mode.

### 5.4 Authority rules

1. Public routes use `GET`, `HEAD`, and `OPTIONS` only.
2. The frontend contains no Alpaca client, credential, order serializer, or
   execution-gateway import.
3. The browser never calculates approval, freshness, reconciliation, P&L,
   hashes, or risk authority.
4. Local exploration—payoff, replay position, or threshold perturbation—is
   labeled `SIMULATION · NO STATE CHANGE` and is never persisted.
5. A network timeout during observed broker activity becomes `Result unknown ·
   reconciling`; it never offers a blind retry.
6. Frozen replay, observed Paper, current read, derived, and simulated values
   remain visibly different in every workspace.

## 6. Target information architecture

Use six primary workspaces rather than five implementation-shaped tabs.

| Route | Workspace | Primary question |
|---|---|---|
| `/overview` | Overview | What needs attention, and is the system safe/current? |
| `/decisions` | Decisions | What qualified or refused, and which record should I inspect? |
| `/positions` | Positions | What exposure or lifecycle state needs attention? |
| `/activity` | Activity & incidents | What is the worker doing, and what changed or failed? |
| `/audit` | Audit & proof | Can I reconstruct and export the authority chain? |
| `/tour/:scene` | Guided demonstration | Can a new viewer understand the product in 90 seconds? |

A decision detail uses the nested route
`/decisions/:decisionId/:section` with this order:

1. `summary` — Decision Ticket and “why now”;
2. `market` — observed evidence, quality, counter-evidence, and model memo;
3. `structure` — readable legs, liquidity, payoff, and candidate choice;
4. `risk` — budget, max loss/gain, invalidation, checks, and policy;
5. `lifecycle` — intent, request, order, fills, position, and close;
6. `proof` — hashes, versions, audit events, correlation, and export.

The authority rail becomes a compact global trust spine. Selecting a stage
opens the corresponding decision section; the full hash lineage remains in
Proof.

URL search state contains source/demo mode, list filters, sort, selected time
window, comparison mode, and tour step. Browser Back/Forward, refresh, bookmark,
and shared links must restore the same public state.

## 7. Application shell

### 7.1 Always-visible status bar

Above any trade, memo, or P&L, show:

- environment: `PAPER · endpoint verified` or explicit `UNKNOWN`;
- source mode: `LIVE READ`, `OBSERVED PAPER`, `FROZEN REPLAY`, `DERIVED`, or
  `SIMULATION`;
- data age and absolute observation time;
- bot mode and public access mode;
- durable execution state;
- reconciliation state and last completed time;
- unresolved incident count.

Each item is a link or disclosure to its proof. Status uses a word, icon/shape,
and color; never color alone.

### 7.2 Desktop concept

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Options Alpha     PAPER VERIFIED · LIVE READ · 02m old · NORMAL · MATCHED   │
├──────────────┬───────────────────────────────────────────────────────────────┤
│ Overview     │ SPY · BULLISH · OPTIONS POSITION                 10:35 ET    │
│ Decisions    │ Trend continuation / retest · current source and freshness   │
│ Positions    ├───────────────────────────────────────────────────────────────┤
│ Activity     │ WHY NOW                     │ STRUCTURE & DEFINED RISK         │
│ Audit        │ 2 aligned signals           │ 18 Sep · 640/645 call vertical  │
│ Guided demo  │ 1 counter-signal            │ $3.20/share · $320/spread        │
│              │ Invalidate below ...        │ max loss / gain / breakeven      │
│              ├─────────────────────────────┴─────────────────────────────────┤
│              │ Observe → Qualify → AI review → Risk → Authorize → Reconcile │
│              ├───────────────────────────────────────────────────────────────┤
│              │ Summary | Market | Structure | Risk | Lifecycle | Proof      │
└──────────────┴───────────────────────────────────────────────────────────────┘
```

This is a hierarchy specification, not a visual mockup. Exact layout and spacing
must be validated in a browser.

### 7.3 Responsive behavior

- **1440/1024 px:** persistent 224 px navigation, two-column Decision Ticket,
  dense but readable tables, horizontal compact authority spine.
- **736 px:** collapsible navigation, stacked ticket, two-column safety facts,
  vertical authority lineage.
- **360 px:** product/status stack, bottom-free navigation, record cards instead
  of wide tables, 44 px targets, no essential horizontal scroll.
- On small screens, preserve source, age, execution state, max loss, and
  invalidation before memo prose or hashes.

## 8. Workspace specifications

### 8.1 Overview and attention queue

First viewport order:

1. positive product promise;
2. status bar;
3. derived proof tiles;
4. attention queue;
5. recent decision/lifecycle summary;
6. guided demonstration entry;
7. limitations and disclosures.

Attention priority is deterministic:

`integrity incident → ambiguous order → reconciliation mismatch → closing →
pending → stale/unmeasurable position → open → recent decision → grouped refusal`

Do not use a generic “success” hero. Use process truth such as `reconciled`,
`closed`, `refused`, `ambiguous`, or `mismatch`.

### 8.2 Decisions

The default table columns are:

- symbol;
- action/refusal and lifecycle;
- direction with text and icon;
- setup family;
- readable structure and DTE when present;
- theoretical maximum risk;
- source mode and age;
- decision time in ET;
- incident/reconciliation state.

Filters: notable/all, action, lifecycle, direction, reason code, source mode,
time range, and current/stale. Refusal groups show count, first time, last time,
and the representative record. Filters and sort remain in the URL.

### 8.3 Decision Summary — the Decision Ticket

Above forensic detail, answer:

- **What:** SPY, action/refusal, direction, setup, intended horizon.
- **When:** decision time in `America/New_York`; UTC in details.
- **Source:** provider, feed, source mode, source time, receipt time, quote age,
  and data-quality result.
- **Why now:** a one-sentence deterministic setup summary, aligned evidence,
  counter-evidence, and exact invalidation.
- **What structure:** strategy, expiry/DTE, long and short legs, width, quantity.
- **What risk:** debit, maximum loss, maximum gain, breakeven, return on maximum
  risk, percent of account equity, and percent of risk budget.
- **What happened:** refused, approved, submitted, filled, closing, closed,
  ambiguous, mismatch, or reconciled.

The model memo appears as a subordinate violet advisory card. Confidence is
`uncalibrated model metadata`, never a probability or a green conviction gauge.

### 8.4 Market and evidence

- Data-quality result precedes every signal.
- Evidence and counter-evidence use stable IDs and link to provenance.
- Surface source, as-of time, age, completed-bar cutoff, and missing fields.
- Show deterministic baseline versus model-assisted outcome on the same snapshot.
- Do not render a candlestick chart until the exact decision bar window is
  persisted. When available, exclude/formally mark the forming bar and show the
  earliest eligible execution point.

### 8.5 Structure

Translate contract identifiers into readable legs while preserving a copyable
OCC symbol in details.

Example:

| Side | Contract | Bid | Ask | Spread | Delta | IV | OI | Volume | Quote age |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Long | 18 Sep 2026 640 Call | source | source | derived/server | source | source | source | source | source |
| Short | 18 Sep 2026 645 Call | source | source | derived/server | source | source | source | source | source |

Required structure facts:

- expiration and DTE;
- strike/type for each leg;
- width and contract multiplier;
- debit in dollars per share and dollars per spread;
- quantity and total debit;
- maximum loss, maximum gain, breakeven, and maximum return on risk;
- theoretical-at-expiration payoff diagram;
- indicative-feed and pre-expiry limitations adjacent to the diagram.

Gamma, theta, and vega are not stored in the current evidence and render
`UNKNOWN`; they are never estimated silently in the browser. Net delta or other
derived fields require a named server formula/version and complete inputs.

### 8.6 Risk

Show three separate concepts:

1. **trade risk:** server-calculated maximum loss and every deterministic check;
2. **account context:** equity, buying power, risk budget, and percent consumed;
3. **portfolio context:** confirmed, reserved, and available capacity plus
   concentration/correlation only after those records exist.

The current one-position cap remains explicit. Portfolio reservations and
cluster exposure are `NOT AVAILABLE` until persistent admission/reservation
records exist; proposed values are not rendered as facts.

Vertical-spread formulas are server-owned and covered by tests:

```text
maximum loss       = net debit × 100 × quantity
maximum gain       = (spread width − net debit) × 100 × quantity
bull breakeven     = long call strike + net debit
bear breakeven     = long put strike − net debit
maximum return/risk = maximum gain ÷ maximum loss
```

Every displayed currency value names its unit and multiplier.

### 8.7 Positions

The intended monitor shows:

- lifecycle/attention state;
- readable legs, expiry/DTE, and filled quantity;
- actual entry debit;
- conservative executable liquidation value: long bid minus short ask;
- unrealized P&L and remaining theoretical risk;
- underlying value and invalidation distance;
- stop/target distance and governing exit check;
- sessions held, last observation, data age, and next scheduled check;
- reconciliation and incident state.

The committed evidence currently contains zero `position_observations` and zero
`exit_decisions`. Until observed records exist, the Positions workspace must
show a truthful prerequisite/empty state rather than midpoint P&L, a flat line,
or a fabricated exit timeline.

### 8.8 Activity and incidents

- Render durable audit/worker events only.
- Every event carries run/correlation ID, sequence, component, stage, outcome,
  reason codes, source, and occurrence time.
- Highlight sequence gaps instead of rendering an apparently complete stream.
- Show lease owner/heartbeat, last reconciliation, next scheduled check, and
  dependency-specific health when available.
- Use cursor pagination first. Add Server-Sent Events only after the durable
  cursor contract is stable.

`WorkerEvent` exists in the current working tree but is not yet a stable public
presentation contract. Treat its migration, retention behavior, and cursor
semantics as an API dependency, not as permission to synthesize activity.

### 8.9 Audit and proof

- Full evidence → decision → risk → intent → request → broker → fill/position
  lineage.
- Explicit deterministic gateway boundary between intent and request.
- IDs, hashes, timestamps, schema/policy/formula/adapter versions, and copyable
  redacted values.
- Reconciliation matrix for local order, broker order, activities, fills,
  positions, and selected-decision correlation.
- Refusal renders absent-by-design downstream nodes.
- Mismatch and ambiguity remain visible after recovery.
- Existing redacted proof manifest remains downloadable and deterministic.

### 8.10 Guided demonstration

Use the current six-scene structure, updated for the Decision Ticket:

1. product promise and authority boundary;
2. qualified setup and readable structure;
3. bounded model memo with citations/counter-evidence;
4. deterministic risk and exact authorized request;
5. broker fill, close, reconciliation, and flat state;
6. refusal or ambiguity/restart proof plus limitations.

Every scene is directly addressable, pauseable, skippable, restartable, and
usable with reduced motion. A frozen scene never polls or looks live.

## 9. Evidence-backed visualizations

### 9.1 Can ship from current records

| Visualization | Source | Required qualification |
|---|---|---|
| Expiration payoff | spread legs, width, debit, quantity | Theoretical expiration result; show tabular breakpoints |
| Two-leg quote/liquidity matrix | `spread_candidates.leg_quotes` | Provider/feed/as-of/age; missing is `UNKNOWN` |
| Evidence vs counter-evidence | signals, evidence pack, thesis references | Stable evidence IDs and non-color roles |
| Order lifecycle | intents, prepared requests, broker orders, fills, position | Acceptance remains separate from fill; include source times |
| Refusals by reason | decisions and reason codes | Show evidence mode, observed range, and sample size |
| Risk budget used | risk decision plus snapshot account facts | Trade budget only; do not imply portfolio reservation |

### 9.2 Blocked by missing durable evidence

| Visualization | Missing prerequisite | Disposition |
|---|---|---|
| Completed-bar candlestick chart | Exact decision bar window is not persisted | Add a hashed bar-window record before chart implementation |
| Spread mark/P&L/exit timeline | Observed position marks and exit decisions are absent from committed evidence | Populate accepted observations; never substitute midpoint or zero |
| Confirmed/reserved portfolio risk | Portfolio snapshot, reservation, and admission records | Defer until Task 2 evidence exists |
| Strategy candidate funnel | Durable research candidate and promotion lifecycle | Defer until research catalog exists |
| Sharpe, win rate, equity curve, ranking, probability of profit | Sufficient samples, methodology, costs, and uncertainty | Explicitly out of scope |

Every chart needs a text/table alternative, source badge, observed range, sample
size, empty/error state, keyboard access, and non-color distinction.

## 10. Visual and interaction system

### 10.1 Semantic color

| Role | Direction |
|---|---|
| Canvas/surface | neutral ink/slate in dark mode; off-white/slate in light mode |
| Observed data | blue |
| Deterministic policy/verified process | teal |
| Model advisory output | violet |
| Attention, stale, pending | amber |
| Integrity failure/frozen writes | red |
| Positive/negative P&L | neutral text plus signed value; never global success/failure color |

Bullish/bearish always includes text and arrow/shape. Color roles are never
reused for semantic opposites.

### 10.2 Typography and numbers

- UI/narrative: local/system sans, 14–16 px base.
- Prices, quantities, times, symbols, reason codes, IDs, and hashes: tabular
  system monospace.
- Use tabular numerals and right alignment in numeric table columns.
- Do not download a critical font at runtime; local/system fallback must be
  layout-safe.
- Truncate identifiers only visually; full redacted values remain in details
  and copy controls.

### 10.3 Interaction

- One primary action per page; on public pages it is navigation, replay,
  comparison, inspection, or export—not trading.
- Tooltips supplement visible risk/state copy and never contain the only
  explanation.
- Focus moves to the new `h1` after route changes and returns correctly after
  dialogs/disclosures.
- Existing verified content stays visible during refresh.
- Critical state changes announce once; unchanged polling does not repeatedly
  announce.
- No pulsing prices, confetti, gamified streaks, parallax, or decorative AI
  “thinking” animation.

## 11. Recommended React stack

Use current stable releases at implementation time, verify compatibility, then
commit exact versions in `frontend/package.json` and `pnpm-lock.yaml`. There is
no tracked JavaScript manifest today, so exact frontend versions cannot honestly
be called repository-verified in this design.

| Concern | Recommendation | Why it fits |
|---|---|---|
| Runtime | React + TypeScript strict mode | Component model and compile-time contracts for a state-dense interface |
| Build | Vite with the official React plugin | Thin static application; no need for a second server runtime |
| Routing/URL state | `@tanstack/react-router` | Typed nested routes and validated shareable search state |
| Server state | `@tanstack/react-query` | Caching, visibility-aware refresh, preserved verified data, and request status |
| Dense tables | `@tanstack/react-table` | Headless sorting/filtering/column behavior without imposing a retail-terminal skin |
| API types | `openapi-typescript` + `openapi-fetch` | Generate the browser contract from FastAPI OpenAPI |
| Boundary validation | Zod | Validate URL/search state and explicitly external/untrusted payloads |
| Accessible primitives | Radix UI, wrapped in local components using shadcn-style ownership | Focus, keyboard, dialog, tabs, select, tooltip, and disclosure foundations |
| Styling | Tailwind CSS over semantic CSS variables; `class-variance-authority`, `clsx`, `tailwind-merge` | Fast composition while retaining project-owned tokens and variants |
| Icons | `lucide-react` | Consistent accessible icon set; icons never replace text for risk/state |
| Market chart | TradingView `lightweight-charts`, lazy-loaded | Purpose-built OHLC rendering after bars are persisted |
| Aggregate/payoff charts | Semantic SVG first; Apache ECharts only where interaction/scale justifies it | Avoid a large generic chart dependency for simple proof structures |
| Unit/component tests | Vitest + React Testing Library + `jest-dom` + MSW | User-visible behavior and deterministic API states |
| Browser/a11y tests | Playwright + `@axe-core/playwright` | Responsive, keyboard, route, visual, and automated accessibility coverage |
| Component states | Storybook with accessibility checks | Review qualified/refused/stale/mismatch/unknown states in isolation |

Official documentation checked for this decision:

- [React application guidance](https://react.dev/learn/creating-a-react-app) and
  [React with TypeScript](https://react.dev/learn/typescript);
- [Vite React/TypeScript templates](https://vite.dev/guide/);
- [TanStack Router typed search parameters](https://tanstack.com/router/latest/docs/guide/search-params),
  [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/reference/index),
  and [TanStack Table](https://tanstack.com/table/latest/docs/overview);
- [FastAPI response models and output filtering](https://fastapi.tiangolo.com/tutorial/response-model/);
- [Radix accessibility behavior](https://www.radix-ui.com/primitives/docs/overview/accessibility);
- [Lightweight Charts documentation](https://tradingview.github.io/lightweight-charts/docs)
  and its [accessibility guidance](https://tradingview.github.io/lightweight-charts/tutorials/a11y/intro);
- [Apache ECharts ARIA guidance](https://echarts.apache.org/handbook/en/best-practices/aria/);
- [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing).

Lightweight Charts requires TradingView attribution and does not provide a
complete accessibility experience automatically. Budget attribution, keyboard/
ARIA support, and a tabular alternative in the component definition.

### 11.1 Do not add initially

- Redux or another global client store: URL state, query state, and local state
  cover the current product.
- Axios: platform `fetch` through the generated client is sufficient.
- Next.js or another full-stack React runtime: FastAPI already owns the server
  boundary and the app does not need SSR to prove the initial value.
- MUI/Ant Design: their visual and component abstraction cost works against the
  project-specific forensic/trading language.
- Framer Motion: CSS transitions and a small replay reducer meet the motion need.
- WebSocket/Socket.IO: the activity flow is one-way; cursor polling comes first,
  then native SSE if justified.
- XState: use a reducer for the read-only tour; the browser does not own the
  execution state machine.

## 12. Target frontend/backend architecture

```text
Browser
  React/Vite static application
    ├── URL state: decision, section, filters, source, tour step
    ├── TanStack Query: server truth and freshness
    ├── local state: dialog/disclosure/simulation only
    └── no broker capability
              │
              │ same-origin GET /api/v1/*
              ▼
Read-only FastAPI presentation service
    ├── Pydantic public DTOs and output allowlists
    ├── presentation/status, decision, explain, proof, activity, export
    ├── server-owned formulas, correlation, freshness, and reconciliation
    └── no execution gateway/provider credentials
              │
              ▼
SELECT-only database role or committed evidence artifacts

Credentialed worker → deterministic gateway → Alpaca Paper
        (separate process and authority boundary; never reachable from UI)
```

The existing locked backend already contains FastAPI, Pydantic, Uvicorn,
SQLAlchemy, and Streamlit. React changes the presentation client, not the
authority or persistence core.

## 13. Public API contract

### 13.1 Initial endpoints

```text
GET /api/v1/system/status
GET /api/v1/decisions?view=&action=&reason=&source=&cursor=&limit=
GET /api/v1/decisions/{id}/summary
GET /api/v1/decisions/{id}/market
GET /api/v1/decisions/{id}/structure
GET /api/v1/decisions/{id}/risk
GET /api/v1/decisions/{id}/lifecycle
GET /api/v1/decisions/{id}/proof
GET /api/v1/activity?after_sequence=&limit=
GET /api/v1/incidents?state=open
GET /api/v1/proof/{decision_id}.json
```

Later, after cursor behavior is proven:

```text
GET /api/v1/activity/stream
```

SSE is appropriate only for this server-to-browser durable event stream. Event
IDs map to a stable cursor/sequence; reconnect must resume without inventing or
duplicating displayed events.

### 13.2 Response envelope

Every response includes:

```json
{
  "schema_version": "public.v1",
  "source_mode": "FROZEN_REPLAY",
  "source_label": "committed evidence",
  "observed_at": "2026-09-10T14:30:00Z",
  "correlation_id": "redacted-stable-id",
  "data": {}
}
```

Rules:

- money and ratios cross JSON as decimal strings, never binary floats;
- timestamps cross as timezone-aware UTC ISO-8601 strings;
- market-time formatting happens in the browser with the absolute UTC value
  available;
- missing is `null` plus an availability/reason state, never zero or empty-safe;
- reason-code public copy is server-owned and allowlisted;
- raw provider payloads, prompts, hidden reasoning, credentials, private hosts,
  and full account identifiers never cross the boundary;
- the response model filters output to the public DTO;
- the OpenAPI document and import graph are tested to contain no public mutation
  method or broker-capable module.

### 13.3 State ownership

| State | Owner |
|---|---|
| Approval, risk, hash, P&L, reconciliation, freshness | Python/server |
| Selected decision/section/filter/source/tour step | URL |
| Server data, loading, refresh, stale cache | TanStack Query |
| Dialog, disclosure, table-column visibility | Local React state |
| Guided replay playback | Local reducer over immutable server scenes |
| Payoff cursor/local perturbation | Local simulation, visibly labeled |

There are no optimistic updates for trading, lifecycle, reconciliation, worker,
or incident state.

### 13.4 Refresh behavior

- Frozen records: no polling and effectively immutable cache.
- Current read-only records: start with 15-second polling, paused while the
  document is hidden; refresh immediately when visible again.
- Failed refresh: retain the last verified timestamped response and show
  `Showing last verified state` with the failing dependency.
- Activity: cursor polling first; SSE only after correctness and proxy behavior
  are tested.

## 14. Component boundaries

### 14.1 Project-owned primitives

- `SourceBadge`
- `StatusLabel`
- `MoneyValue`
- `Timestamp`
- `ReasonCode`
- `RecordId`
- `FreshnessState`
- `EmptyEvidence`
- `ProvenanceDrawer`
- `SimulationBanner`

### 14.2 Domain components

- `SafetyBar`
- `AttentionQueue`
- `DecisionTable`
- `DecisionTicket`
- `AuthoritySpine`
- `EvidenceMatrix`
- `ModelAdvisoryCard`
- `LegMatrix`
- `ExpirationPayoff`
- `RiskBudgetPanel`
- `LifecycleTimeline`
- `PositionAttentionCard`
- `ActivityStream`
- `IncidentPanel`
- `HashLineage`
- `ReconciliationMatrix`
- `ProofExport`
- `GuidedReplay`

Components may format and disclose values. They may not infer business state or
perform financial authority calculations.

## 15. Incremental migration plan

### `RUI-0` — Freeze truth and evidence prerequisites

- Record the current Streamlit behavior as the parity baseline.
- Define which fields are `AVAILABLE`, `DERIVABLE SERVER-SIDE`, `UNKNOWN`, or
  `BLOCKED BY PERSISTENCE`.
- Add accepted fixtures for qualified, refusal, recovery, stale, unavailable,
  mismatch, disconnected, and a second lifecycle isolation case.
- Decide whether WorkerEvent changes in the current worktree belong to this
  release before designing the public activity contract.

**Exit:** no planned chart or metric lacks an identified durable source.

### `RUI-1` — Typed read-only presentation API

- Add Pydantic public DTOs and `/api/v1` GET routes.
- Move remaining ad hoc `app.py` queries behind selected-decision and list read
  services.
- Add response filtering, redaction, Decimal, time, provenance, correlation,
  pagination, and OpenAPI method tests.
- Extend the no-write-path gate to the API package and generated OpenAPI.

**Exit:** React could render the full existing dashboard without ORM knowledge.

### `RUI-2` — Frontend foundation

- Create `frontend/` with strict TypeScript, Vite, pnpm lockfile, generated API
  types, lint/type/unit/browser scripts, and route splitting.
- Implement semantic tokens, project primitives, Storybook state matrix, and
  light/dark themes.
- Implement shell, status bar, routing, error boundaries, source/freshness
  behavior, and analytics-free privacy defaults.

**Exit:** shell passes keyboard, axe, responsive, and visual-regression checks.

### `RUI-3` — First vertical slice

- Overview, proof tiles, attention queue, decision list, Decision Ticket, compact
  authority spine, and guided route.
- Use the same accepted fixtures as Streamlit.
- Make every selection and tour scene shareable.

**Exit:** ten-second and 90-second evaluator journeys pass with no missing source.

### `RUI-4` — Trader decision depth

- Market/evidence, bounded memo, leg matrix, payoff, risk checks, lifecycle,
  proof lineage, reconciliation, and export.
- Add tabular chart alternatives and unit/formula tests.
- Add OHLC only if the hashed bar-window persistence prerequisite is complete.

**Exit:** a trader answers why direction, why now, why structure, max loss, and
invalidation in 30 seconds; selected-decision isolation holds throughout.

### `RUI-5` — Position and activity workspaces

- Build position attention only after accepted position observations and exit
  decisions exist.
- Build durable activity and incidents on cursor pagination; add SSE later if
  measured latency or demo requirements justify it.
- Add portfolio-risk presentation only after admission/reservation contracts
  exist.

**Exit:** no position value is midpoint theater, no activity is browser-created,
and unavailable portfolio concepts are visibly unavailable.

### `RUI-6` — Parity, cutover, and retirement

- Run Streamlit and React side by side against the same fixtures.
- Compare semantic results, source labels, hashes, exports, screenshots,
  accessibility, performance, and no-write boundaries.
- Cut the default route to React only after all release gates pass.
- Retain Streamlit for one release as a rollback/reference path, then remove it
  and its inline CSS/query layer in a separate change.

**Exit:** rollback is documented; React has no truth or safety regression.

## 16. Acceptance and release gates

### 16.1 Trader comprehension

- In ten seconds, a new user can identify Paper environment, source mode, data
  age, execution state, write authority, and any incident.
- In 30 seconds, a trader can answer why this direction, why now, why this
  vertical, maximum loss, breakeven, and invalidation/exit state.
- Raw OCC symbols never stand alone as the primary leg description.
- Every cash value includes unit, multiplier, and quantity context.
- The payoff math exactly matches server tests for bullish and bearish debit
  verticals.

### 16.2 Truth and provenance

- No displayed number lacks source mode, record path, or derivation metadata.
- Stale, missing, or unavailable quotes never appear current or as `$0`.
- Indicative quotes are labeled beside structure and outcome values.
- `SUBMITTED`, `ACKNOWLEDGED`, `PARTIAL`, `FILLED`, and `RECONCILED` remain
  distinct.
- `NO_TRADE` proves the absence of intent, request, and order.
- An ambiguous result never suggests blind retry.
- Selecting a decision cannot expose another decision's memo, request, order,
  fill, position, receipt, or result.
- Frozen, live, observed, derived, and simulated values never share an
  unlabeled visual treatment.

### 16.3 Security and authority

- Public OpenAPI contains only `GET`, `HEAD`, and `OPTIONS`.
- API and frontend import graphs contain no broker write capability.
- The deployed UI/API has no Alpaca or OpenAI credential.
- Production database access uses a `SELECT`-only role.
- Response allowlists and proof exports pass confidentiality/secret scans.
- No browser state is a source of execution or lifecycle truth.

### 16.4 Accessibility and responsive QA

- WCAG 2.2 AA target for contrast, semantics, focus, keyboard, and motion.
- Automated axe scans plus manual keyboard and screen-reader review.
- Playwright coverage at 360, 736, 1024, and 1440 px in light and dark.
- Every chart has a table/text alternative and never relies on color alone.
- Focus and announcements remain correct across route, dialog, refresh, and
  critical-state changes.
- No essential horizontal scroll on mobile.

### 16.5 Engineering quality

- Generated TypeScript types cannot drift from FastAPI OpenAPI in CI.
- Lint, strict type check, unit, component, browser, accessibility, dependency
  audit, license inventory, and production build all pass.
- Initial route target: 150–180 KB gzip or less excluding lazy chart chunks;
  actual budget is frozen after the first production measurement.
- Charts and evidence-heavy routes are lazy-loaded.
- Browser tests assert user-visible behavior, not component internals.
- Streamlit parity and rollback remain available through the first React release.

## 17. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Big-bang rewrite | Loss of evidence correctness hidden by visual polish | Strangler migration and shared fixtures |
| API mirrors ORM | Leaks fields and freezes internal schema into the browser | Public DTO allowlists and presentation services |
| Financial math moves client-side | Decimal drift or altered authority facts | Server-owned formulas and decimal strings |
| React creates fake liveness | Attractive but untrue event stream | Durable cursor events only; no browser synthesis |
| Chart pressure invents data | Repeat of competitor provenance defects | Data-readiness gate and explicit blocked states |
| Source modes become decorative badges | Mixed live/frozen truth | Source mode in every API envelope and component contract |
| Dense trader UI harms accessibility | Keyboard/mobile/screen-reader exclusion | Headless accessible primitives, table alternatives, manual QA |
| Chart bundles dominate initial load | Slow first viewport | Route-level lazy loading and performance budget |
| Public monitor grows mutation controls | Expanded financial authority | Separate authenticated control design and OpenAPI method gate |
| Streamlit is removed too early | No reference or rollback | Retain for one release after cutover |

## 18. Decision register

| Decision | Disposition | Rationale |
|---|---|---|
| Move the UI to React | **Yes** | Trader workflows, routing, charts, dense tables, responsive behavior, and testability now justify it |
| Rewrite `app.py` one component at a time | **No** | Extract typed read contracts first; do not preserve monolithic query/render coupling |
| Rewrite the execution core | **No** | It is the project's strongest and safest asset |
| Keep Streamlit during migration | **Yes** | Reference behavior, fixture parity, fallback, and rollback |
| Make the authority rail the main screen | **No** | Keep it as a trust spine; lead with the Decision Ticket |
| Add a trader-readable options structure | **Yes, P0** | Current raw symbols and units slow comprehension and invite costly ambiguity |
| Add payoff and lifecycle visuals | **Yes** | Current records support them when labeled correctly |
| Add candlesticks now | **No** | The exact decision bar series is not persisted |
| Add position P&L timeline now | **No** | Accepted position observations and exit decisions are absent from committed evidence |
| Add model confidence gauge | **No** | Confidence is uncalibrated advisory metadata, not risk evidence |
| Add public order controls | **No** | Violates the credential-free read-only boundary |
| Add authenticated operator controls in this project | **Deferred** | Requires separate auth, CSRF, reauthentication, state-machine, audit, and ambiguity design |
| Add WebSockets | **No initially** | Cursor polling, then SSE, matches a one-way durable event flow |
| Add Next.js/Redux/Framer Motion | **No initially** | They do not solve a current requirement and increase regression surface |
| Copy winner visual style | **No** | Adopt clarity and choreography while preserving semantic authority colors and accessibility |

## 19. Definition of done

This redesign is complete when:

1. React is the default credential-free public surface over a versioned GET-only
   presentation API;
2. the qualified, refusal, and recovery stories retain all current proof and
   source semantics;
3. a trader can understand the decision, vertical, units, max loss, breakeven,
   invalidation, lifecycle, and data quality without parsing hashes or OCC
   symbols;
4. every advanced claim is traceable to a selected record and source mode;
5. no missing time series has been replaced with invented or unlabeled data;
6. public frontend and API code cannot express a broker write;
7. responsive, keyboard, screen-reader, visual, performance, contract, and
   confidentiality gates pass; and
8. Streamlit remains available for one release with a tested rollback before
   its separate retirement change.

The governing product principle is unchanged:

> **The model may improve the memo. Only deterministic, evidence-linked code may
> create trading authority. The UI must make both facts obvious.**

## 20. Validation record — 14 September 2026

Reviewed against the codebase rather than read. The document holds up: every
checkable claim in it is accurate, and its epistemic discipline is unusual for a
design of this size — it declines to call frontend versions repository-verified
because no JavaScript manifest is tracked, and it states plainly that no rendered
browser session backed the visual findings. Both are true.

### Verified

| Claim | Result |
|---|---|
| "the 919-line Streamlit application" | exact |
| Presentation services named in §1 | all eight modules exist |
| Every relative link | 0 broken, 0 empty |
| §9.1 payoff inputs | `spread_candidates` carries `estimated_debit`, `calculated_max_loss`, `quantity`, both leg symbols; `positions` carries `width` |
| §9.1 quote matrix source | `spread_candidates.leg_quotes` exists |
| §9.2 "observations and exit decisions absent" | precise — `position_observations` and `exit_decisions` exist in the schema and hold **0** committed rows |
| §13.1 `incidents` endpoint | table exists (0 committed rows) |
| §13 authority model | consistent with the project's rules: GET-only, server owns approval/risk/hash, no optimistic updates for trading state |

The §9.2 wording deserves credit for precision. "Absent from committed evidence"
is exactly right and is not the same as "no schema", which a looser document
would have conflated — and which would have sent someone to write a migration
that already exists.

### `RUI-VAL-001` — §11.1 rests on a premise that is a plan, not a fact

The rejection of Next.js reads "FastAPI already owns the server boundary". It
does not. `fastapi`, `uvicorn[standard]` and `starlette` are declared in
`pyproject.toml`, `requirements.txt` and `uv.lock`, but **no source file imports
any of them** — the only matches in the tree are egg-info metadata. Streamlit
owns the server boundary today.

The conclusion survives: §12 and §13 propose exactly that boundary, so declining
a second full-stack runtime is right. Only the justification needs restating as
forward-looking, because a reader checking the premise will find it false and
discount the rest.

~~A second observation falls out of it. Three transitive-heavy packages ship in the
locked environment and are never imported.~~ **Corrected 14 September:** wrong for
two of the three. `starlette` and `uvicorn` are required by Streamlit itself
(`streamlit` declares `starlette<2,>=0.46.0` and `uvicorn<1,>=0.30.0`) — the
dashboard journal reports "Uvicorn server started" on every boot. Removing them
would have broken the running dashboard. "No source file imports it" was the
wrong test for "unused"; the installed dependency graph was the right one, and it
was not checked. Only `fastapi` was genuinely unused, and `RUI-1` below now uses
it, which closes the rest of this finding.

### `RUI-VAL-002` — §16.3's database gate is already met

"Production database access uses a `SELECT`-only role" was a release gate when
this was written on 10 September. It was implemented on 11 September as
`CIIP-I-017`: `options_alpha_ro` holds `SELECT` and nothing else,
`DASHBOARD_DATABASE_URL` points at it, and `deploy/verify_readonly_role.sh`
proves it by attempting six destructive statements and exiting non-zero if any
succeeds.

Recorded so `RUI-0` does not re-scope work that is done. What remains for the API
is narrower: the FastAPI process must use that same role rather than the
worker's.

### `RUI-VAL-003` — §8.8's `WorkerEvent` caveat has partly discharged

§8.8 says `WorkerEvent` "exists in the current working tree but is not yet a
stable public presentation contract". Accurate when written, mid-flight.

`CIIP-I-008` landed on 11 September: migration `0004_worker_events` creates the
table, and `presentation/activity.py` exposes `worker_events()` and
`worker_faults()` with `kind` as a column so faults are selectable without
parsing prose. So it is now a read model with a migration — still not a *public
API* contract, which is what §8.8 actually gates on.

The paragraph's instruction is unchanged and still right: treat retention and
cursor semantics as an API dependency, and never as permission to synthesize
activity.

### Not assessed

The UX judgements in §3.2, §8 and §10 — hierarchy, comprehension speed, colour
semantics, choreography. They are design positions, not factual claims, and the
document already concedes that a rendered browser audit is a mandatory release
gate rather than something this review can stand in for.

### `RUI-VAL-004` — §13.1's activity cursor cannot work as specified

`GET /api/v1/activity?after_sequence=` assumes `audit_events.sequence` orders the
system-wide feed. It does not: the repository assigns it with
`enumerate(outcome.transitions)`, so it restarts at zero for every decision. The
committed evidence holds 26 events sharing **six** sequence values. A cursor of
`after_sequence=3` names no position in a feed that spans decisions, and paging
by it would silently skip or repeat most events. §13.1's SSE note ("Event IDs map
to a stable cursor/sequence") inherits the same flaw.

`sequence` is still exactly right for what it already does — the per-decision
gap check in `presentation/activity.for_decision`. The feed needs a different key.
Resolved in `RUI-1`: an opaque cursor over `(occurred_at, id)`, which is total and
stable. `tests/test_api.py` pages all 26 events seven at a time and asserts every
event is seen exactly once — the test a sequence cursor would fail.

### `RUI-VAL-005` — a decision's public identity must be its hash

§13.1's `/decisions/{id}` leaves `id` unspecified, and the dashboard selects by
`snapshot_id`, which reads like a natural key. It is not one: `decisions.snapshot_id`
is indexed but **not unique**, because one snapshot can replay into several
decisions (the case `CIIP-VAL-004` turned on). `decisions.id` is unique but an
internal row key. `decision_hash` carries a unique constraint and is already
public — on the dashboard, in receipts, in proof manifests.

Resolved in `RUI-1`: the path identifier is the 64-character `decision_hash` hex.
A malformed identifier is a 422 and an unknown one a 404, never a guess.

### `RUI-VAL-006` — the live source label freezes its count at process start

Found while extracting source resolution, and it applies to the existing
dashboard, not only to the API. The label reads "live worker database (24
decisions)", but the count is taken once: `app.py` wraps resolution in
`@st.cache_resource`, and the API resolves once at startup. As the worker records
decisions the label keeps the startup number. The mode (`LIVE`) stays true; the
parenthetical becomes stale within five minutes of a market session.

Recorded, not fixed here — fixing it in one surface would make the two disagree,
which is the exact failure the shared resolver exists to prevent. The fix belongs
in `presentation/source.py`: separate the cached engine from a label computed per
request.

## 21. `RUI-1` progress — 14 September 2026

First increment landed. The API is built, tested, served over real HTTP on
loopback, and **not deployed** — nothing listens on the host.

### Built

| Route | Serves |
|---|---|
| `GET /api/v1/system/status` | `presentation/status` |
| `GET /api/v1/system/proof` | `presentation/proof` tiles |
| `GET /api/v1/decisions` | keyset-paged list, `action` filter |
| `GET /api/v1/decisions/{hash}/summary` | identity, observation, broker/model flags, `why` in authority order |
| `GET /api/v1/decisions/{hash}/proof` | enveloped manifest plus its digest |
| `GET /api/v1/proof/{hash}.json` | the exact manifest bytes, `X-Proof-Digest` header — deliberately unenveloped, since wrapping would change the digest a reviewer checks |
| `GET /api/v1/activity` | keyset-paged audit feed (`RUI-VAL-004`) |
| `GET /api/v1/worker/events` | allowlisted worker events, `faults_only` |

`presentation/source.py` now holds the one source rule; `app.py` delegates to it,
so the dashboard and the API cannot disagree about where their data came from.

### Boundary, as tests rather than claims

`tests/test_api.py`, 22 tests. The ones that matter most were each shown to fail
against an injected violation, with the source restored afterwards:

- OpenAPI publishes only `get`, and a walk of every mounted route finds no write
  method. Injecting a `POST` route fails both. The walk asserts it found every
  API route, because this FastAPI release nests included routers and a naive walk
  passes having checked nothing — which the first version of the test did.
- A clean interpreter importing the API loads no `alpaca`, `openai`,
  `execution.*`, `providers.*`, `worker`, `agent`, `config`, `secrets_setup` or
  `lifecycle`. Injecting one import of the execution gateway fails it.
- Worker event detail is allowlisted; `host`, `error` and `summary` are withheld
  and **named** in `withheld`, so a held-back field is visible as held back.
  Adding `host` to the allowlist fails it.
- `build_app` reads `DASHBOARD_DATABASE_URL`, the `SELECT`-only role, and ignores
  the worker's `DATABASE_URL` (`RUI-VAL-002`).
- Every response carries the envelope; timestamps are UTC with an offset even from
  SQLite's naive values; prices are decimal strings; the proof file is
  byte-identical to `export.render`.

A source without the `worker_events` table returns `available: false` with the
reason, not an empty feed (which would read as a worker that did nothing) and
not a 500. The committed evidence is such a source — see below.

### Remaining for `RUI-1`'s exit

~~Superseded the same day by §22.~~

## 22. `RUI-1` second increment — 14 September 2026

### What is now served

Seven decision workspaces, one per area of the dashboard, plus incidents and the
tour:

| Route | Dashboard area |
|---|---|
| `…/{hash}/market` | Evidence & setup: observation, signals with their **role**, qualification |
| `…/{hash}/memo` | Model memo and provider call — kept apart from structure so the model's advisory output and deterministic structure never share a payload |
| `…/{hash}/structure` | Selected spread and candidates, with allowlisted leg quotes |
| `…/{hash}/risk` | Risk decisions, checks, and accounting (equity lifted out of the payload, which stays behind) |
| `…/{hash}/lifecycle` | Intents, allowlisted requests, orders and fills, positions, exits, the audit trail with its gap check, and receipt/ablation correlation |
| `GET /api/v1/incidents?state=open\|all` | Guards & state: open incidents |
| `GET /api/v1/tour` | Guided scenes, each resolved to a decision hash or `null` |

### `app.py` no longer queries

Every ad hoc query left the page: the decision list and count, positions and
incidents (`presentation/book.py`), and four re-queries of rows the decision
view had already loaded — snapshot, spreads, model call and prepared requests.
The signal role (cited / counter-evidence / observed, unused) moved out of the
render function into `presentation.decision.signal_role`, so the dashboard and
the API classify evidence with one rule.

Rendered parity was checked, not assumed: every view × decision combination
rendered before and after the refactor — 13 combinations, 643 rendered elements
— with **zero** differences and no exceptions. The committed evidence holds no
incident, so the incident change below was verified separately.

### Deployed, loopback only

`options-alpha-api.service` runs on the host on `127.0.0.1:8600` with the
dashboard's `SELECT`-only credential. Against live PostgreSQL: `LIVE` mode, 72
decisions, 29 routes probed with no non-200, **no float and no naive timestamp
anywhere**, `POST` refused, the read-only gate passing, and port 8600 not
answering from outside the host. The public dashboard was reloaded on the
refactored code and checked by reading the rendered page: five tabs, no
exception, and the same 72-decision label the API reports.

### Findings closed

**`RUI-VAL-006` — resolved.** `presentation/source.Resolver` holds the engines
and answers "which source?" on every call. Both surfaces use it. Tested by
deleting a live decision between two requests (label 5 → 4) and by a live source
that gains its first decision moving from `FROZEN_REPLAY` to `LIVE` without a
restart.

**`RUI-VAL-007` — incident detail was published verbatim.** Several incident
call sites build `detail` from exception text (`"reconciliation could not read
broker state: {exc}"`), and the public dashboard printed it. The live database
holds no incident, so nothing leaked; the exposure was latent. The dashboard now
shows kind, severity, the execution state imposed and "detail withheld from the
public page"; the API names `detail` in `withheld`. Both tested with an incident
carrying a credential-shaped canary.

**`RUI-VAL-008` — the committed evidence displayed bytes that were never
approved.** The most serious finding of the day, because hash lineage is the
product's central claim. `build_demo_db.py` built each prepared request from the
receipt's *filled* legs (fill price and quantity, no `ratio_qty`), stored it
under the real request hash, and hardcoded `intent_hash_match=True`. The
dashboard rendered those bodies as "the bytes that were approved" beside a green
"Request hash matches the approved intent" that nothing computed. Neither stored
body hashed to its recorded hash.

The genuine bodies turned out to be recoverable: rebuilt in the adapter's exact
shape (`execution/request.prepare_mleg_request`), both reproduce the recorded
hashes. The builder now does that, **refuses to write a body that does not
reproduce its hash**, and computes the match. `export.py`'s comment that the
body "includes headers" was also wrong — the adapter writes seven order fields
and four per leg — and the API's request allowlist is exactly that shape, so a
key a future adapter adds is named and withheld.

This reversed a decision recorded in §21. The demo database was left for the
owner because rebuilding changes its freeze digest; a fixture showing unapproved
bytes under an approval label outweighs that, and a rebuild is the only fix. It
was rebuilt locally and on the host:

- schema `0003_reasoning_effort` → `0004_worker_events`;
- decision rows identical, every table's row count identical;
- both request bodies reproduce their hashes;
- `tests/test_demo_db_provenance.py` now requires head schema and hash-reproducing
  request bodies — all three new assertions fail against the pre-rebuild file and
  pass against the rebuilt one. The `expectedFailure` marker is gone.

### What still stands between `RUI-1` and its exit

The records are fully served. What is not served is **copy and presentation
logic that is not a record**, and a React client would otherwise re-create it:

- the decision list's run-length grouping (`collapse_runs`) and its four filter
  views (Notable, Positions, Refusals, Everything);
- static explanatory copy: the write-guard sequence, "what the model cannot do",
  the halt-state explanations, and the disclosures.

The doc's rule is that reason-code public copy is server-owned, so both belong
behind the API. They are the last `RUI-1` items.

### Operational note

A Cloud Assistant call failed on a network reset during the demo-database
transfer, and the Alibaba CLI printed the failed request's full URL — including
the account's **AccessKey ID** — into the working session. The AccessKey secret
was not printed, and the request signature is single-use and time-bound, but the
key ID is now outside the account. **Rotate the Alibaba AccessKey pair.** The
local helper that makes these calls now captures CLI stderr and emits only an
error code and a redacted message, and ships files in idempotent parts that are
checksum-verified and swapped atomically, so a partial transfer cannot replace a
working file. That design is why the interrupted transfer left the host
untouched.

## 23. `RUI-1` closing increment — 14 September 2026

The last two `RUI-1` items were presentation logic and authority copy still
living in `app.py`. Moving them exposed two defects in the page that had been
there since before the redesign began.

### `RUI-VAL-009` — the default view hid positions, and the tour narrated the wrong decision

**The list.** Runs of identical outcomes were keyed on `(action, reason codes)`.
A position carries no reason codes, so every position shared one key, and the
default "Notable" view merged consecutive positions — contradicting its own
comment, "every position, plus one representative of each run of identical
refusals". On the committed evidence Notable listed **three entries for five
decisions**: the bullish and bearish qualified cases collapsed into a single
"bearish ×2", joining opposite directions and hiding the bullish case; and the
lifecycle decision, the one carrying the real Paper round trip, was hidden behind
"live ×2". This dates from 28 August, when grouping was introduced.

**The tour.** A scene selected its decision only if the current view listed it,
and otherwise fell back silently to the first entry. With the list defect, **five
of six scenes rendered a different decision under their narration**: scenes 1–3
narrated the bullish qualified case over the bearish one, and scenes 4–5
narrated the Paper lifecycle over the bearish qualified case. Only the refusal
scene was right. On the live database, where no scene's decision exists, every
step narrated over whatever came first, with nothing saying so. The tour tests
proved each scene's decision *exists*; none proved the page *shows* it. This
dates from `CIIP-004` on 9 September.

**Fixed in `presentation/listing.py`.** A position's run key is its own hash, so
positions are never grouped; identical refusals still are. A tour scene's
decision is pinned into the list in every view — replacing its run's
representative in Notable, or listed despite a filter that excludes it. A scene
whose decision the source does not hold renders an explicit notice instead of
its narration. Entries are newest first in every view; the previous order was an
accident of grouping ("Everything" listed bearish, qualified, refusal, live,
lifecycle).

Tests that would have caught each defect, each shown to fail against the
reintroduced defect:

- the old run key fails the listing tests and the Notable-lists-every-position
  test;
- removing the pin fails a new test that opens every position scene under the
  "Refusals" filter. The default-view tour test alone could not catch that once
  Notable listed every position, which is why the filter test exists;
- every scene is checked for the decision it *renders*, and a source missing a
  scene's case must show the notice and not the narration.

That last test also caught a bug in the first version of the fix: a missing
scene resolved to no decision, so nothing was pinned and the listing could not
know a pin had been wanted. "Missing" is now derived from the scene.

### Authority copy is server-owned

`presentation/copy.py` holds, word for word, the copy that makes a checkable
claim about the system: what this is, the disclosures, the seven write guards and
their note, the five model limits, and the three halt states — which a test
requires to cover every `ExecutionState`. The page renders from it; the API
serves it at `GET /api/v1/copy`, and a test requires every served rule to appear
on the rendered page. Interface microcopy stays with the client.

The disclosure test previously grepped `app.py`'s source. It now asserts on the
rendered sidebar, since a disclosure that exists in a file but is not rendered
discloses nothing.

### `RUI-VAL-010` — two disclosure texts disagree — **resolved 15 September 2026**

The page called the P&L sample "one round trip"; the proof manifest
(`export.DISCLOSURES`) said "the sample is two trades". Neither was derived, and
they could not both be right.

Counted, they are not: `proof.completed_round_trips` — extracted from the tile
that already did this correctly, joining positions through decisions to broker
orders and requiring both a reconciled entry and close — returns **1** on the
committed evidence. The page's number was right; the manifest's was wrong.

Fixed by deriving rather than by picking a winner. The page reports the counted
number and pluralises from it. The manifest stops asserting a sample size at all
and points at the tile that counts it, because a per-decision manifest has no
corpus to count. `MANIFEST_VERSION` is bumped to `proof-manifest-2`: the bytes
change, so every digest does, and a reviewer holding an older manifest should see
a different version rather than an unexplained digest.

Guarded three ways, each shown to fail against the reintroduced claim: the
derived count must agree with the tile it backs; no manifest disclosure may
assert a sample size (`sample is one|two|three|<n>`); and the rendered page must
name the numbers the records yield.

**Corrected on deployment.** Deriving the count from the *current source* made
the live page read "0 completed round trips" beside a realized −7.10 taken from
the committed receipt — two numbers counting different things, which together
read as a contradiction. The note now names both and says which is which: the
committed receipt the P&L came from, and this source's reconciled round trips.
The test renders both shapes, including the live-like source with no closed
position, which is where the first fix went wrong.

### A test-order dependency, removed

`app.py` cached its resolver with `@st.cache_resource` and no key, so every
`AppTest` run in a process received the first resolver built regardless of
`DASHBOARD_DATABASE_URL`. The suite passed only because the API tests happened to
run first. The cache is now keyed on the URL, and the affected suites pass in
both orders.

### Served

`GET /api/v1/decisions/grouped?view=&pin=` returns the sidebar list exactly as
the page builds it — entries, labels, counts, member ids, whether grouping hid
anything, and whether a requested pin is absent. A test requires the served
labels to equal the rendered radio options in all four views.

### `RUI-1` exit

"React could render the full existing dashboard without ORM knowledge" now
holds for everything the page derives from records or states as a rule. What a
React client still owns is layout, styling, interface microcopy and interaction
— which is what a presentation client is for.

## 24. `RUI-2` first increment — 17 September 2026

The frontend exists, builds, is tested, and runs against the real API. It is a
shell, not the dashboard: source banner, status strip, decision list, and one
decision's identity. The workspaces are `RUI-3` onward, and a half-built tab that
looks finished is worse than an absent one.

### The contract is generated, and cannot drift quietly

`scripts/export_openapi.py` writes the API's own schema to
`frontend/openapi.json`; `openapi-typescript` generates `src/api/schema.ts` from
it. Neither the type check nor CI needs Python or a running server.

Two guards keep that trustworthy. `tests/test_openapi_contract.py` regenerates
the document and fails if the committed copy has drifted — shown to fail by
adding a route without regenerating. CI regenerates the types and fails on any
diff.

`get` accepts only URLs built by `api.*`, each checked against the generated
paths. The first version took `Path | string`, which made the union decorative:
any typo would have type-checked. The lint rule that flagged it was right.

### The read-only boundary, in the browser

The client has no write helper, no `method:`, no body and no credentials, and a
test asserts that against the source **with comments stripped** — for the reason
`check_no_write_path.py` gives: a guard that cannot tell a call from prose
explaining why we never make that call punishes documentation and gets deleted.
Adding a `submit()` helper fails it.

The contract test also proves the document a client generates from publishes only
`get`, and that every JSON response carries an envelope except the kept proof
bytes.

### What the shell refuses to invent

Tone, `known`, the grouping, the labels and the run counts all come from the
server. A second implementation in the browser is how two surfaces come to
disagree, which `RUI-VAL-009` demonstrated once already.

A failed refresh keeps the last verified response and says *"Showing last
verified state"*; a first load that fails says the API is unreachable rather than
rendering an empty shell that looks like real emptiness. Both are tested.

### Verified end to end

Built app, real API, real browser: the banner reads `COMMITTED EVIDENCE`, the
status strip shows `Worker UNKNOWN — no worker has ever held the lease` with the
unknown intact, **five** decisions are listed (`RUI-VAL-009`'s fix, visible), and
selecting the lifecycle case renders its action, direction, decision hash and
both authority flags. No exception, and the only console error is a missing
favicon.

### Not in this increment

Storybook, the axe accessibility pass, visual-regression and responsive QA — all
part of `RUI-2`'s stated exit. Routing is not here either: with one screen there
is nothing to route between, and `@tanstack/react-router` arrives with `RUI-3`'s
second screen rather than as scaffolding for it.
