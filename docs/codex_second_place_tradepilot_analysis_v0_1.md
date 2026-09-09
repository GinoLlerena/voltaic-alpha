# CODEX Second-Place Project Analysis - TradePilot AI

**Analysis prefix:** `CTA-` (Codex TradePilot Analysis)  
**Document filename prefix:** `codex_`  
**Prepared for:** Voltaic Alpha / Options Alpha  
**Analysis date:** 9 September 2026  
**TradePilot backend inspected:** `divine308/Tradepilot` at `ec22f13abac8c04b61f29b531c07f3255f72d42a`  
**TradePilot frontend inspected:** `divine308/TradepilotAi` at `b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d`  
**Options Alpha commit compared:** `2657a1ee17033b9f61c4008b31285f03f2b9a236`

## 1. Executive conclusion

TradePilot's advantage was not merely polish. Unlike Alpha Hunter, TradePilot
contains a genuine OpenAI model call, real Alpaca market-data and order paths,
deterministic corroboration and exposure gates, broker-side protective stops,
fill polling, and a continuous position-management loop. Its core proposition -
AI proposes a direction, deterministic code confirms and constrains it - is a
credible agent design and is much closer to Options Alpha's thesis than the
winner's implementation.

Its larger competitive advantage, however, was **product legibility**. TradePilot
shipped a public landing page, registration and login, ten routed product pages,
a familiar SaaS workspace, a live Vercel deployment, a 14-slide pitch, and a
purpose-built nine-scene cinematic demo. A judge could understand the product in
seconds and could imagine it as a business without reading its source. The
official archived event page lists it second among 428 submitted projects, while
the official submission identifies a four-person team and links the application,
presentation, and repositories.[^official-standings][^official-submission]

Options Alpha is substantially stronger where trading correctness becomes hard:
options-specific execution, completed-bar discipline, data provenance, durable
decision and order records, idempotency, ambiguous-submit resolution, restart
reconciliation, Paper endpoint proof, single-writer control, recovery evidence,
and automated tests. TradePilot's database stores users, internal API keys, and
one global `enabled` flag, but it never writes its declared `trades` table. Its
trading history and activity trail therefore live primarily at Alpaca or in 100
in-memory UI events.

The most important conclusion is:

> The execution-firewall idea was not the problem. TradePilot used a looser
> version of the same idea and made it feel like a complete product. For the next
> presentation, keep Options Alpha's authority boundary and evidence model, but
> package them with TradePilot's front door, guided lifecycle, product language,
> and dedicated demo choreography.

TradePilot should not be copied literally. Several verified defects would be
unsafe to import: authenticated users share one global Alpaca account; manual
orders are not Paper-gated; the dashboard always claims Paper mode; timed-out
buy orders are not canceled; the take-profit path cannot reach its sell logic;
sell-side risk is calculated as if an exit increases exposure; no order uses a
deterministic `client_order_id`; and an application restart or multi-worker
deployment can lose or duplicate responsibility.

## 2. Scope, evidence standard, and limitations

This review covers:

- the official event listing, submission page, and 14-page presentation;
- the complete backend and frontend Git histories;
- agents, market-data derivation, model integration, risk, execution, position
  management, storage, authentication, and deployment;
- the public frontend and demo route;
- an isolated backend install/startup check and a pinned frontend build/lint
  check; and
- a component-by-component comparison with the current Options Alpha workspace.

Every numbered finding uses the requested `CTA-` prefix.

### Evidence labels

| Label | Meaning |
|---|---|
| `OFFICIAL` | Supported by the event, submission, or presentation artifact |
| `VERIFIED-CODE` | Confirmed in the pinned source or Git history |
| `VERIFIED-RUN` | Reproduced by an isolated build, startup, database, or read-only deployment check |
| `INFERENCE` | A reasoned interpretation, not private judge feedback |

### Important ranking caveat

The archived event page labels its list “Final standings” and places TradePilot
second with 135, but the same page still contains stale text saying judging is
in progress and community voting remains open. The submission page showed a
different count when crawled. This report therefore treats **the displayed
second position as official**, but does not interpret the adjacent number as a
private jury score or claim to know why the judges ranked it there. No written
judge feedback or private scorecard was available.[^official-standings]

The public Vercel root and `/demo` route both returned HTTP 200 during this audit.
The deployed JavaScript bundle referenced `tradepilot-h7kw.onrender.com`, but
that backend returned no bytes within two read-only checks of 20 and 50 seconds.
This proves the frontend was reachable at the audit time; it does **not** prove
that the end-to-end application was then operational. Render sleep, deployment
drift, or an outage are all possible.

## 3. Comparative scorecard

| Dimension | TradePilot | Options Alpha | Assessment |
|---|---|---|---|
| First ten seconds | Landing page, product tagline, signup, polished workspace | Technical README and forensic dashboard | TradePilot stronger |
| AI integration | Real Responses API call; model chooses BUY/SELL/HOLD | Real bounded call; model cannot choose direction or financial values | Both real; Options Alpha has the safer boundary |
| Asset/strategy scope | Seven mega-cap equities, long entries and position exits | One SPY setup mapped to defined-risk call/put debit spreads | TradePilot broader visually; Options Alpha matches the options track |
| Quant layer | Many indicators and a transparent 0-100 heuristic score | Frozen H0 rule, oracle separation, sensitivity analysis, ablation | Options Alpha stronger evidence |
| Market-data integrity | Alpaca IEX; latest daily bar; limited provenance | Provider/feed/source/receive times, payload hashes, completed-bar rule | Options Alpha decisively stronger |
| Risk | 5% position, 50% exposure, 70% confidence, 50% model-risk caps | Deterministic option, portfolio, authority, freshness, and lifecycle gates | Options Alpha stronger and model-independent |
| Execution | Real market orders, stop orders, fill polling, emergency close | Native MLeg intent/request hash, deterministic client ID, ambiguity lookup, reconciliation | Options Alpha decisively stronger |
| Persistence | Four tables; trade table unused; activity in memory | Durable linked records from snapshot through fills, positions, exits, incidents, and audit events | Options Alpha decisively stronger |
| Frontend | Ten React routes, motion, charts, product/demo surfaces | Focused Streamlit judge viewer with five evidence views | TradePilot stronger presentation |
| Honesty | Explicitly says formal backtesting is unfinished | Publishes negative friction, ablation, limits, and no-alpha claim | Both unusually candid; Options Alpha provides stronger artifacts |
| Reproducibility | Frontend builds; no tests; lint fails; sparse setup/deploy docs | Locked environment, migrations, fixtures, validation scripts, extensive tests | Options Alpha decisively stronger |
| Business legibility | Familiar retail-trading SaaS and developer-platform shape | Specialized execution/audit layer for agent builders | TradePilot easier to imagine; Options Alpha more differentiated |

## 4. Architecture and actual data flow

TradePilot's implemented topology is compact:

```text
React/Vite browser
  |-- JWT login/register
  |-- Dashboard / Agents / Markets / Portfolio
  |-- Start / stop autonomous agent
  `-- Manual analysis and trading calls
             |
             v
FastAPI process
  |-- MarketAgent -> Alpaca IEX daily bars -> pandas indicators + score
  |-- AIService -> OpenAI Responses API -> strict BUY/SELL/HOLD JSON
  |-- StrategyAgent -> quantitative corroboration -> final direction/HOLD
  |-- RiskAgent -> position/exposure/confidence/model-risk gates
  |-- Supervisor -> manual execution path
  `-- AutonomousTradingAgent -> scan/manage loop -> Alpaca orders
             |
             +-- Alpaca TradingClient (one account from environment)
             `-- SQLite/PostgreSQL (users, app keys, global enabled flag)
```

This is a **single-process orchestrated pipeline**, not a distributed network of
independently persistent agents. The names “Market Agent,” “Strategy Agent,”
“Risk Agent,” and “Supervisor Agent” are useful product taxonomy; only the
strategy stage invokes a language model. The remaining agents are deterministic
Python classes and one module-level autonomous singleton.[^backend-readme]
[^autonomous-agent]

### `CTA-001` - The central AI path is genuine (`VERIFIED-CODE`)

`AIService` calls `client.responses.create`, supplies a detailed trading system
prompt, and requests a strict JSON schema with exactly four required fields:
`decision`, `confidence`, `risk_score`, and `reasoning`. The direction enum is
limited to `BUY`, `SELL`, or `HOLD`, numeric ranges are constrained to 0-1, and
additional properties are rejected.[^ai-service]

This is materially better than a dashboard that labels hardcoded rules as AI.
The prompt also tells the model not to invent unavailable indicators, to prefer
HOLD on conflicting evidence, and not to claim certainty.

Tradeoffs remain:

- the model is allowed to choose the direction;
- `risk_score` is also model-generated rather than independently calculated;
- the OpenAI request has no application-specific timeout or bounded retry
  policy;
- `store=False` is not specified;
- the model call, model version, prompt version, token use, latency, response ID,
  and raw validated output are not persisted; and
- a successful JSON result is not linked to a durable market snapshot.

Options Alpha's bounded memo is less agentically dramatic, but its model cannot
reverse direction, invent contracts, change size, calculate loss, or obtain
execution authority. That remains the safer and more auditable design.

### `CTA-002` - AI and quantitative corroboration must agree (`VERIFIED-CODE`)

TradePilot does not send the model's answer directly to Alpaca. The
`StrategyAgent` first obtains a deterministic quantitative score and then
requires:

- AI `BUY` plus score at least 70;
- AI `SELL` plus score at most 30;
- confidence at least 0.70; and
- model-reported risk at most 0.50.

Every failed condition becomes `HOLD`; exceptions and malformed values also
fail closed to `HOLD`, confidence 0, and risk 1.[^strategy-agent]

This is a strong, simple story for a hackathon: **model proposes, measurable
features corroborate, deterministic risk sizes and vetoes**. It is easier to
explain than Options Alpha's full proof chain, even though our chain provides
stronger guarantees.

### `CTA-003` - The market feature engine is real and unusually broad (`VERIFIED-CODE`)

The Market Agent requests Alpaca IEX daily bars and computes SMA20, SMA50,
SMA200, EMA12/26, moving-average slopes, RSI14, MACD and histogram momentum,
5- and 20-day returns, annualized volatility, ATR14, volume ratio, recent range
position, breakouts/breakdowns, and pullback conditions. A transparent additive
heuristic maps these to a bounded 0-100 score.[^market-agent]

That is more visibly “quant” than Options Alpha's deliberately narrow H0 rule.
It gives the UI many human-readable reasons and makes the AI input concrete.

There are three significant data-quality weaknesses:

1. The request covers only 90 calendar days, so it cannot contain 200 daily
   observations. `SMA200` is therefore null by construction and its long-term
   score contribution is dead code.
2. `end=datetime.now()` and the absence of an Alpaca market-clock or completed-
   session rule allow the current, still-forming daily bar to enter RSI, MACD,
   ATR, and the final score while the market is open.
3. The returned analysis includes `data_feed: IEX` and the number of points, but
   not the exact source window, latest bar timestamp, receive timestamp, request
   parameters, payload hash, or immutable snapshot identifier.

Options Alpha's completed-daily-close rule and frozen provenance manifests solve
precisely these problems.[^ours-readme][^ours-provider]

### `CTA-004` - The autonomous loop is an actual loop (`VERIFIED-CODE`)

The background agent scans AAPL, NVDA, MSFT, AMZN, META, GOOGL, and TSLA every
300 seconds. It manages existing positions before searching for a new entry,
permits at most one executed trade per scan and ten per in-memory session, sizes
new entries at 5% of current equity, and stops opening a symbol already held.
The enabled flag is persisted and restored at FastAPI startup when Paper mode is
true.[^autonomous-agent]

This is more operationally vivid than Options Alpha's judge-facing experience:
the system appears to observe, decide, act, and continue managing positions.
The frontend polls status and activity every five seconds, reinforcing that
perception.[^frontend-api][^frontend-agents]

The implementation is one module-level singleton with no distributed lease.
The one database row says only whether the agent should run. If the application
is deployed with multiple workers or replicas, each process can restore its own
loop and act against the same account. The session-trade counter and all local
sets also reset on process restart. Options Alpha's single-writer lease and
durable position responsibility are the patterns to preserve.

### `CTA-005` - Risk limits are simple and visible (`VERIFIED-CODE`)

The risk layer rejects invalid values, positions larger than 5% of equity,
combined long exposure above 50%, confidence below 70%, and model-risk scores
above 50%. It returns the exact rule that failed plus stop, target, and
breakeven configuration when approved.[^risk-agent]

That simplicity has presentation value: a judge can remember four thresholds.
It also has real limitations:

- the risk score comes from the same model proposing the trade;
- exposure counts only positive market value;
- there is no daily-loss, drawdown, correlation, volatility-adjusted sizing,
  available-cash, buying-power, liquidity, slippage, spread, or market-hours
  gate;
- the ten-trade session cap resets on restart; and
- the fixed 4% stop and 30% target are not supported by backtesting or
  sensitivity evidence.

### `CTA-006` - Exit risk is applied in the wrong direction (`VERIFIED-CODE`)

`RiskAgent.evaluate` receives no order side. It always calculates:

```text
total_exposure = existing_exposure + proposed_trade_exposure
```

The autonomous agent uses that same calculation for a SELL that reduces an
existing long position. A portfolio at 49% exposure can therefore reject a 5%
risk-reducing sale because the calculation becomes 54%. The manual supervisor
has the same issue.[^risk-agent][^supervisor-agent]

Options Alpha separates new-risk authority from risk-reducing close authority.
That distinction should remain explicit in every future version.

## 5. Execution and position management

### `CTA-007` - TradePilot contains genuine broker-race defenses (`VERIFIED-CODE`)

The order service does more than call `submit_order`:

- sell availability subtracts quantities reserved by active sell orders;
- protective-stop creation refuses a second active stop;
- stop movement uses Alpaca order replacement;
- exits cancel a protective stop and wait for confirmed cancellation before
  selling;
- fills are polled with explicit timeouts;
- partial exits attempt to restore protection; and
- if a buy fills but stop creation throws, the code attempts an emergency market
  close.[^alpaca-service][^autonomous-agent]

These are serious engineering decisions, not demo-only labels. They likely made
the system credible in a live walkthrough.

### `CTA-008` - The take-profit path is unreachable (`VERIFIED-CODE`)

`_handle_take_profit` first adds the symbol to `exit_in_progress`, then calls
`_execute_sell`. The first condition in `_execute_sell` is:

```python
if symbol in self.exit_in_progress:
    return False
```

The +30% take-profit path therefore always logs or returns as an exit already in
progress and never submits its intended sell. The surrounding `finally` removes
the marker, so the same ineffective attempt can repeat on every scan.[^autonomous-agent]

This is exactly the kind of cross-function lifecycle bug that a single unit test
would catch. The repository contains no tests.

### `CTA-009` - A timed-out buy can later fill without protection (`VERIFIED-CODE`)

After submitting a market buy, the agent polls for at most 15 seconds. If the
last status is not `filled`, it logs a rejection and returns. It does **not**
cancel the order, persist responsibility for it, or continue reconciliation.
Because there is no market-hours gate, an after-hours DAY market order can be
queued for the next session, outlive the 15-second wait, and later fill without
the code placing the intended stop.[^autonomous-agent]

The same branch also ignores partial-fill responsibility. By contrast, Options
Alpha treats acceptance as `SUBMITTED`, distinguishes partial and terminal
states, owns ambiguous submissions by deterministic client ID, and does not open
a local position until reconciled fills establish actual quantity and basis.
[^ours-lifecycle][^ours-gateway]

### `CTA-010` - No order is idempotent (`VERIFIED-CODE`)

None of the market or stop requests supplies a `client_order_id`. A lost response
or retried logical action can therefore submit a duplicate with no stable local
identifier for lookup. Alpaca explicitly recommends client order IDs for
organizing and tracking algorithmic orders, and exposes retrieval by that ID.
[^alpaca-orders]

TradePilot's active-order checks reduce some duplicate sell/stop cases, but they
are not equivalent to request-level idempotency. Options Alpha's deterministic
client ID derived from an immutable intent hash is the stronger pattern.

### `CTA-011` - Protection is asymmetrical and partly process-dependent (`VERIFIED-CODE`)

The 4% stop is a real broker-side `StopOrderRequest`; the 30% take-profit is
software-polled; and the +10% breakeven trigger modifies the stop to +0.5% only
when the process observes it. Every order uses `TimeInForce.DAY`. Alpaca states
that unfilled DAY orders are automatically canceled after the closing auction,
whereas GTC orders remain active until canceled.[^alpaca-orders-at-alpaca]

Consequences:

- a stopped process cannot apply the software take-profit or move to breakeven;
- the DAY stop must be rediscovered as missing and recreated by a later loop;
- a process outage around a new session creates an unprotected interval; and
- even when running, position checks occur only every five minutes.

Alpaca supports bracket and OCO orders that bind stop-loss and take-profit exits
as a broker-recognized group. Those primitives would be safer than separately
polled take-profit logic for an equities strategy.[^alpaca-orders-at-alpaca]

### `CTA-012` - The loop assumes ownership of every account position (`VERIFIED-CODE`)

`manage_positions` loads all Alpaca positions and applies TradePilot's stop,
breakeven, and take-profit policy without checking whether TradePilot opened the
position. Because the local `trades` table is unused, there is no durable origin
record to make that distinction.[^autonomous-agent][^trade-model]

On a shared or reused Paper account, starting the agent can therefore attach a
4% stop to unrelated manual holdings. This is a more serious ownership problem
than merely having incomplete history.

### `CTA-013` - Paper-only enforcement is incomplete and the UI can misstate mode (`VERIFIED-CODE`)

The autonomous `start`, `scan`, and final pre-submit branch correctly refuse
when `ALPACA_PAPER` is false. However:

- `TradingClient` accepts the configured boolean and can construct a live
  client;
- `/api/trading/execute`, manual sells, order cancellation, and close-all have
  no independent Paper guard;
- the manual supervisor submits immediately when model and risk agree; and
- `/api/dashboard/overview` returns `paper_trading: True` unconditionally,
  regardless of configuration.[^config][^trading-router][^dashboard-router]

This is not evidence that TradePilot traded live. It is evidence that the code's
Paper-only claim is enforced on only one execution path and can be contradicted
by its own status display. Options Alpha's gateway refuses to construct or use a
non-Paper endpoint immediately before every write; retain that invariant.

## 6. Storage, auditability, and security

### `CTA-014` - The database is an account shell, not a trading ledger (`VERIFIED-CODE`, `VERIFIED-RUN`)

FastAPI creates four tables:

| Table | Runtime use |
|---|---|
| `users` | Registration and JWT login |
| `api_keys` | Creates and lists internal app keys |
| `autonomous_agent_state` | Stores one global `enabled` boolean |
| `trades` | Declared but never inserted, selected, or updated |

The isolated startup check installed all pinned backend dependencies, entered the
FastAPI lifespan, created these four tables, and returned HTTP 200 from `/` and
`/health` using fake credentials and an isolated SQLite database. Python
compilation also passed. No broker or model call was made.

The `Trade` model anticipates `user_id`, symbol, side, quantity, price, status,
Alpaca order ID, and AI reasoning, but a repository-wide search finds no use
outside table creation.[^database][^trade-model]

TradePilot therefore cannot reconstruct which market evidence, AI output, risk
decision, order request, response, fill, stop, or exit belonged to a trade.
Options Alpha's linked snapshot-to-outcome schema is not just more detailed; it
supports a fundamentally different claim: that authority and responsibility can
be audited after a restart.

### `CTA-015` - The visible activity stream is transient (`VERIFIED-CODE`)

Autonomous activity is inserted at the front of a Python list, truncated to 100
items, and wiped when the process restarts. The frontend can also synthesize an
activity feed from its latest analysis responses using the browser's current
timestamp. Neither is a durable audit record.[^autonomous-agent][^frontend-agents]

This creates a useful visual feeling of motion, but not evidence. The lesson for
Options Alpha is to render its durable audit events with the same liveliness,
not replace them with client-generated events.

### `CTA-016` - Multi-user authentication controls one shared Alpaca account (`VERIFIED-CODE`)

Registration and login are real. Passwords use Argon2, JWT decoding pins HS256,
and CORS is restricted to the Vercel deployment and local development. Those
are good baseline choices.[^security][^auth-router]

The Alpaca client, however, is a module-level singleton created from server
environment variables. User identity is never passed to account, position,
order, autonomous-agent, or close-all operations. Any user who can register and
authenticate can therefore view and act on the same connected account, cancel
its orders, stop/start its global agent, or close all positions.[^alpaca-service]
[^trading-router]

This is a single-account demo wrapped in a multi-user interface, not true
multi-tenancy. Options Alpha is safer to remain explicitly single-tenant until
broker credentials, positions, agent state, limits, and audit records are scoped
per principal.

### `CTA-017` - “Developer infrastructure” is mostly a demonstrative surface (`VERIFIED-CODE`)

The backend can mint high-entropy `mk_live_...` app keys, stores only their
SHA-256 hashes, and lists per-user metadata. But no endpoint authenticates those
keys, there is no revoke route, `requests_used` is never incremented, and the
first router-level auth dependency is overwritten by a second router
declaration. Individual key routes still decode JWTs, so this duplication is
dead code rather than a direct bypass.[^api-key-router][^security]

The frontend does not call those implemented key functions. Its API Keys page is
explicitly labeled `MOCK API KEYS` in source and hardcodes:

- test and live-looking credentials;
- 18.4K monthly requests;
- a 99.8% success rate;
- 142 ms latency;
- test and production environments; and
- a local-only revoke interaction.[^frontend-api-keys]

The pitch repeats 18.4K, 99.8%, 142 ms, “scoped credentials,” and two
environments as developer-platform evidence, but the inspected repositories
contain no request authentication, metrics collection, environment scoping, or
measurement artifacts supporting those numbers.[^official-presentation]

### `CTA-018` - The example JWT signing key is unsafe as a deployment default (`VERIFIED-CODE`)

`.env.example` contains a concrete 64-hex-character `SECRET_KEY` rather than an
obvious placeholder or generated-at-install instruction. The real `.env` is
correctly ignored and no Alpaca/OpenAI secret was found in Git, but copying the
example unchanged would make the HS256 signing secret public.[^env-example]

The frontend stores the bearer token in `localStorage`, a common hackathon choice
that expands the impact of an XSS defect. There is no refresh token, session
revocation, role, email verification, rate limit, or `is_active` enforcement on
login. These are acceptable prototype deferrals only if the product is described
as a single-account Paper demo.

## 7. Frontend and judge experience

### `CTA-019` - TradePilot looks like a complete product (`VERIFIED-CODE`)

The React application exposes ten routed experiences:

1. Landing
2. Register
3. Login
4. Dashboard
5. Agents
6. Markets
7. Portfolio
8. API Keys
9. Settings
10. Demo

Protected routes, JWT interception, global navigation, error handling, loading
states, responsive Tailwind classes, Lucide icons, a coherent cream/violet/mint
palette, Framer Motion, custom SVG charts, and direct API service functions make
it feel like a commercial workspace.[^frontend-app][^frontend-api]

This is the clearest answer to “what did they do that we did not?” Options Alpha
made judges enter through the audit mechanism. TradePilot gave them a front door,
a product category, a signup journey, and several ways to see the same value.

### `CTA-020` - The demo is a separate storytelling product (`VERIFIED-CODE`)

`Demo.jsx` is 2,988 lines plus a 726-line stylesheet. It advances every 6.2
seconds through nine scenes:

```text
Opening -> Live Market -> Scanner -> AI Reasoning -> Multi-Agent Intelligence
        -> Risk Engine -> Execution -> Portfolio -> Closing
```

It supports play/pause, keyboard navigation, progress, animation, and a strong
visual system. It contains no API import, fetch, Axios call, or broker action.
It is a scripted product film implemented as a public route.[^frontend-demo]

That was a smart hackathon decision. A five-minute video is a different medium
from an application, and a choreographed tour avoids loading delays and demo
variance. The ethical requirement is to label such a route “scripted product
tour” or “sample scenario” and make the real connected workflow available
separately. Options Alpha should copy the separation of concerns, not blur the
evidence boundary.

### `CTA-021` - Connected and demonstrative data are mixed without a strong label (`VERIFIED-CODE`)

| Surface | Real/connected behavior | Static, derived, or demonstrative behavior |
|---|---|---|
| Dashboard | Account/position endpoints, partial failure handling | Several derived summaries and UI-only chart elements |
| Agents | Seven real analysis calls; real global agent status/activity | Client-synthesized fallback events; “four active agents” inferred from any successful analysis |
| Markets | Real Alpaca bars for the selected chart | Hardcoded universe signals/strengths and static index values |
| Portfolio | Real account positions from dashboard overview | Client-derived concentration/risk labels |
| API Keys | Backend functions exist in `api.js` | Page uses mock keys and mock operational metrics instead |
| Settings | None | Profile, Paper toggle, AI toggle, notifications, session count, and security actions are local/static |
| Demo | None | Entire nine-scene product film |

Mixing can be acceptable in a prototype if each card carries a visible source
badge such as `LIVE ALPACA`, `DERIVED`, `FROZEN CASE`, or `SCRIPTED DEMO`. Options
Alpha already has source-label semantics; TradePilot demonstrates how much more
prominently they could be presented.

### `CTA-022` - The pitch criticizes the exact decorative metric the UI hardcodes (`OFFICIAL`, `VERIFIED-CODE`)

The deck opens by arguing that a dashboard showing “Strong Buy - 96” is
authoritative decoration unless it is benchmarked, calibrated, and traceable.
The Markets page then hardcodes NVDA as `Strong Buy` with `strength: 96`, without
a live derivation or visible source distinction.[^official-presentation]
[^frontend-markets]

This is the sharpest narrative inconsistency in the submission. It does not
erase the real quantitative score produced elsewhere, but it weakens the claim
that every displayed strength is evidence-backed.

### `CTA-023` - The pitch is excellent even where the implementation is incomplete (`OFFICIAL`, `INFERENCE`)

The 14-slide deck has an unusually mature arc:

- “Don't automate the clicks. Automate the thinking.”
- a problem framed around untested confidence;
- a five-step product loop: Scan, Assess, Control, Execute, Track;
- an independent risk gate;
- live Paper-account evidence, including a negative unrealized result;
- developer-platform expansion;
- honest limitations;
- a proposed random-entry benchmark, trial register, pre-registered criteria,
  and leakage audit; and
- a future roadmap that explicitly postpones advanced agents until the first
  honest benchmark exists.[^official-presentation]

This presentation does three things Options Alpha's technical documents do less
efficiently: it converts constraints into a memorable product, shows a business
expansion path, and makes negative evidence part of the trust story.

The deck also overstates current implementation in places. It says every
decision is logged and measured against benchmarks, other agents can use scoped
credentials, and operational API metrics have been achieved. The code does not
support those claims. Its later admission that formal backtesting is unfinished
is accurate and commendable, but does not reconcile the earlier statements.

### `CTA-024` - The Settings page contains controls without authority (`VERIFIED-CODE`)

The Paper-trading and AI-execution toggles change only React component state.
They do not call the backend, alter `ALPACA_PAPER`, or constrain an order path.
Profile fields, notifications, password changes, active-session display, and
“sign out everywhere” are likewise static or unconnected.[^frontend-settings]

These controls improve product shape but create a dangerous mental model: a user
can appear to turn Paper mode off or on while the actual broker mode remains a
server secret. In a trading UI, any control that implies authority must either
work end to end or be visibly disabled and labeled as a roadmap preview.

### `CTA-025` - The frontend builds, but its quality gate fails (`VERIFIED-RUN`)

With the pinned lockfile:

- `npm ci` installed 182 packages and reported zero known vulnerabilities;
- `npm run build` succeeded;
- Vite emitted a 730.43 kB minified JavaScript chunk (197.31 kB gzip) and warned
  that it exceeded 500 kB; and
- `npm run lint` failed with 28 errors and 5 warnings.

The lint failures include unused imports/components, effect-driven synchronous
state updates, missing dependencies, and the demo's keyboard handlers referring
to callback variables before declaration. There are no frontend tests.

The page sizes explain the bundle and maintenance cost: Dashboard is 3,876
lines, Demo 2,988, Agents 2,641, Markets 2,070, and Portfolio 1,959. The source
contains 21,418 JavaScript/JSX/CSS lines. It is visually ambitious but highly
monolithic.

### `CTA-026` - Failure handling is stronger than the mock surfaces suggest (`VERIFIED-CODE`)

The API layer uses `Promise.allSettled` for dashboard and multi-symbol analysis,
returns source-specific errors, clears expired JWTs on protected 401 responses,
and derives a `healthy` flag instead of silently presenting failed calls as
success. This is a useful pattern for a demo that depends on several remote
services.[^frontend-api]

Options Alpha should adopt this graceful-degradation style while keeping its
stronger truth labels: a failed live provider should produce a clearly labeled
frozen replay, not an unlabeled fallback.

## 8. Documentation, history, and team decisions

### `CTA-027` - The team optimized for an end-to-end demo in five days (`VERIFIED-CODE`, `INFERENCE`)

The backend has 17 commits and the frontend 11, all dated 31 August through 4
September 2026. The initial commits imported most of each application. Subsequent
backend commits concentrated on deployment, then repeatedly expanded and rewrote
autonomous execution, Alpaca order handling, market analysis, strategy filtering,
and position protection. The README was added only on 3 September and expanded
on the final day.[^backend-history]

Frontend follow-ups concentrated on deployment, dashboard/API integration,
login, the cinematic demo, and final dashboard/portfolio changes. Every frontend
commit message after the initial import is a variation of “deploy.” The separate
demo route arrived on 2 September as a single 3,786-line net addition.
[^frontend-history]

This history supports a reasonable inference: the team prioritized a complete
public experience and iterated directly against deployment. That is effective
hackathon triage, although generic commit messages make design intent and
regression diagnosis harder.

### `CTA-028` - Four people are named, but repository attribution is not role evidence (`OFFICIAL`, `VERIFIED-CODE`)

The official submission names Divine Okechukwu, Esther Olinya, Peace Sossa, and
Jethro Ibebuike. The deck assigns full-stack/ML automation, AI logic, data
analysis, and research roles.[^official-submission][^official-presentation]

Both Git histories contain a single email identity under two backend author
names and one frontend author name. That does not prove the other members did
not contribute; research, presentation, pair programming, and uncredited work
will not necessarily appear in Git. It does mean the repository cannot be used
to validate the division of labor.

The strategic lesson is still sound: named roles made the submission look like a
team and a business. Options Alpha should state ownership of engineering,
strategy/research, validation, product/design, and presentation, even when one
person holds multiple roles.

### `CTA-029` - Reproduction is possible but not well documented (`VERIFIED-RUN`)

The backend contains fully pinned dependencies, though `requirements.txt` is
unusually encoded as UTF-16LE. The dependencies installed and FastAPI started in
an isolated environment, but `cryptography` required a local source build. The
backend's `run.py` is empty, and the repository has no Dockerfile, Render
manifest, migration system, CI workflow, license, or test file. The README
describes architecture but provides no complete setup/run/deploy procedure.

The frontend has a lockfile, Vercel rewrite, and build scripts, but its README is
the untouched React/Vite template. `src/.env` is committed with a localhost API
URL; the live Vercel bundle must rely on separately configured deployment
environment variables.[^backend-readme][^frontend-readme]

Options Alpha's runbooks, migrations, freeze artifact, release gates, and test
commands are far stronger. The opportunity is to surface them more simply, not
reduce their rigor.

## 9. What TradePilot did that Options Alpha did not

### `CTA-030` - It led with a positive product outcome (`VERIFIED-CODE`, `OFFICIAL`)

“Don't automate the clicks. Automate the thinking.” is short, affirmative, and
memorable. “Observe, analyze, decide, validate, execute, monitor, repeat” makes
the autonomous loop intuitive. Options Alpha's “the model may write the memo,
but it cannot trade” is more distinctive, but the surrounding presentation leads
with caveats and architecture before a judge sees the product outcome.

**Adopt:** lead with “An AI options research lab whose evidence firewall proves
what is allowed to trade.” Put the negative constraints underneath the positive
promise.

### `CTA-031` - It repeated one story through many product surfaces (`VERIFIED-CODE`)

Market cards, agent cards, the activity stream, portfolio panels, risk badges,
API infrastructure, the presentation, and the cinematic route all repeat the
same four ideas: observe, reason, control, act. Repetition reduces the amount a
judge must infer.

Options Alpha's five views are precise but all demand forensic reading. We should
add a high-level lifecycle surface before the evidence detail:

```text
Observed -> Qualified/Refused -> Model reviewed -> Risk decided
         -> Intent authorized -> Submitted -> Reconciled -> Closed/Learning
```

Every stage can remain clickable and backed by the existing durable record.

### `CTA-032` - It built a video-native artifact (`VERIFIED-CODE`)

The dedicated demo route is the largest transferable presentation lesson. It
lets a video tell the ideal sequence at a stable pace without risking network
latency, market closure, or a weak live signal. Options Alpha currently makes
the product itself carry both operational truth and cinematic pacing.

**Adopt with disclosure:** create a public, read-only “Guided H0 Tour” using the
real frozen qualified, refusal, recovery, and completed Paper lifecycle records.
Animate them, but do not invent metrics or imply the replay is live.

### `CTA-033` - It made a business visible (`OFFICIAL`, `VERIFIED-CODE`)

Registration, workspaces, settings, developer API access, two environment labels,
and team roles make the prototype read as a company rather than a research
artifact. Several of those features are only visual, but the business direction
is instantly legible.

Options Alpha's stronger business is an execution/audit control plane for teams
building financial agents. It should show:

- an operator workspace;
- a policy/version workspace;
- a decision and incident journal;
- a redacted proof export;
- a strategy/research workspace with promotion status; and
- a developer integration panel generated from actual API/auth capabilities.

### `CTA-034` - It made the agent feel alive (`VERIFIED-CODE`)

Start/stop controls, five-second polling, current stage, current symbol, scan
counts, signal counts, rejection counts, named agent actions, and recent events
create a sense of ongoing work. Options Alpha has richer durable state but
presents it more like a report.

**Adopt:** animate state transitions sourced from the audit table, show the
current owner/lease and next scheduled check, and let judges replay a completed
run event by event. Do not add execution controls to the public dashboard.

### `CTA-035` - It showed negative performance without apologizing (`OFFICIAL`)

The deck presents a Paper account with -1.14% unrealized return and says a system
that can be trusted only while winning cannot be trusted. It separately admits
that formal backtesting and independent validation remain future work.
[^official-presentation][^backend-readme]

Options Alpha already has the stronger version of this principle: negative
friction, model ablation, threshold sensitivity, and no-alpha claim. The lesson
is to turn those into one memorable slide and product card rather than leaving
them primarily in technical prose.

## 10. What Options Alpha must not copy

### `CTA-036` - Do not copy breadth without provenance (`VERIFIED-CODE`)

Ten pages and dozens of metrics create product presence, but hardcoded market
signals, API metrics, environments, settings, and security actions damage trust
when they are indistinguishable from live state. Every Options Alpha visual must
retain a source label and a record ID.

### `CTA-037` - Do not put multi-user UX over a shared account (`VERIFIED-CODE`)

Authentication is not tenancy. If a user cannot be mapped to broker authority,
positions, limits, agent state, and records, use a single-tenant operator model
or a credential-free public viewer.

### `CTA-038` - Do not let model confidence become a risk fact (`VERIFIED-CODE`)

The model's self-reported `risk_score` is one of TradePilot's execution gates.
That value may be useful as commentary, but it is not independent risk evidence.
Options Alpha should keep confidence, maximum loss, spread width, quote quality,
portfolio exposure, and authority as separately calculated fields.

### `CTA-039` - Do not trade code quality for line count (`VERIFIED-RUN`)

TradePilot's roughly 29,000 backend-Python plus frontend-source lines helped
produce an expansive interface quickly, but also hid unreachable exits, pending-
order responsibility gaps, mock surfaces, 28 lint errors, and no tests. A thinner
frontend over Options Alpha's existing view models can achieve the same judge
clarity with much less regression surface.

### `CTA-040` - Do not collapse broker truth into UI truth (`VERIFIED-CODE`)

A hardcoded Paper badge, an “executed” response immediately after manual order
submission, or a client-created event can tell a cleaner story than the broker.
Options Alpha's rule that `SUBMITTED` is not `FILLED` and that only reconciliation
changes position responsibility is a core competitive advantage. Make it more
visible; never weaken it.

### `CTA-041` - TradePilot did not implement options (`OFFICIAL`, `VERIFIED-CODE`)

TradePilot was submitted to the `Options Alpha Agents` track, but its inspected
implementation is an equities system. It uses Alpaca stock bars, stock symbols,
share quantities, market orders, and stop orders. There is no option-chain read,
contract selection, strike, expiry, Greek, option position intent, or multi-leg
order. The frontend Settings page explicitly names `US Equities` as the market.
[^official-submission][^market-agent][^alpaca-service][^frontend-settings]

The winner and runner-up both presented broad autonomous stock-trading products,
while Options Alpha built the harder options-specific path. The result does not
prove options work was irrelevant to judges, but it does show that literal
options coverage was not required to occupy the first two displayed standings.
For future events, verify what the judges can perceive and score; do not assume
that additional domain complexity will explain itself.
[^official-standings][^ours-provider][^ours-lifecycle]

## 11. Prioritized action plan for Options Alpha

### P0 - Presentation fixes before the next judging session

| Priority | Action | Why it matters | Preserve |
|---|---|---|---|
| `CTA-P0-01` | Add a visual front door with one positive sentence, three proof points, and a “Start guided tour” button | Fixes the first-ten-seconds gap | Paper/no-alpha disclosures remain visible |
| `CTA-P0-02` | Build a scripted, read-only H0 tour from committed artifacts | Stable video pacing and zero live-market dependence | Label every scene `FROZEN REPLAY` or `OBSERVED PAPER` |
| `CTA-P0-03` | Add a single lifecycle ribbon from snapshot to reconciled close | Makes the whole product graspable at once | Every node links to the durable record/hash |
| `CTA-P0-04` | Add “Why this decision?” progressive disclosure | Gives nontechnical judges a summary before forensic detail | The summary is derived, not a second source of truth |
| `CTA-P0-05` | Turn the negative evidence into a prominent trust card | Differentiates us and makes candor memorable | Publish sample size, method, and limitation |
| `CTA-P0-06` | Show named team roles and ownership | Makes delivery capacity and business shape visible | Do not invent contributors or roles |
| `CTA-P0-07` | Verify the public URL and add a credential-free fallback | Removes deployment friction | Public UI remains read-only |

### P1 - Product experience after submission

| Priority | Action | Acceptance criterion |
|---|---|---|
| `CTA-P1-01` | Add a thin React/Vite judge shell or substantially restyle the existing dashboard | Fast landing page, mobile layout, accessible navigation, under-budget bundle |
| `CTA-P1-02` | Stream durable audit events into an agent-activity view | No client-synthesized trading events; each event has run/record/source IDs |
| `CTA-P1-03` | Create distinct Live, Paper-observed, Frozen replay, and Derived badges | No displayed market/order metric lacks a provenance label |
| `CTA-P1-04` | Add safe interactions: replay, threshold perturbation, model/no-model comparison, proof export | No public control can reach a broker write |
| `CTA-P1-05` | Expose health by dependency, not a static “healthy” response | Database, provider, worker lease, last reconcile, and frozen fallback shown separately |
| `CTA-P1-06` | Generate developer docs from real endpoints and authentication | Every example is integration-tested; no mock request counts |

### P2 - Broader product thesis

| Priority | Action | Decision rule |
|---|---|---|
| `CTA-P2-01` | Turn strategy candidates into first-class research objects | Candidates can be proposed/rejected without expanding execution authority |
| `CTA-P2-02` | Add several options hypotheses and visible promotion states | Only a validated champion may reach the existing firewall |
| `CTA-P2-03` | Add adversarial research review and counter-evidence panels | Model roles remain bounded; risk and execution stay deterministic |
| `CTA-P2-04` | Add true tenancy only if required | No launch until broker accounts, records, policies, secrets, and agent leases are isolated per tenant |
| `CTA-P2-05` | Preserve a purpose-built video route as a release artifact | Every scene is generated from versioned fixtures or observed redacted records |

## 12. Recommended next-demo narrative

The following combines TradePilot's clarity with Options Alpha's evidence:

1. **Outcome:** “An AI options research lab with an execution firewall.”
2. **Live shape:** one screen shows Observe -> Decide -> Authorize -> Reconcile.
3. **Qualified case:** deterministic code establishes direction and two exact
   spread candidates.
4. **Bounded AI:** the model reviews evidence, cites record IDs, and may select
   only an allowed candidate or abstain.
5. **Veto:** risk code independently recomputes max loss, freshness, liquidity,
   exposure, mode, and authority.
6. **Broker proof:** show the exact native MLeg request, intent hash, deterministic
   client ID, observed Paper fill, and reconciled flat outcome.
7. **Failure case:** replay a stale/contradictory refusal or ambiguous-submit
   recovery.
8. **Uncomfortable result:** show model ablation and Paper execution friction.
9. **Business:** show how a strategy team integrates the firewall and exports a
   redacted proof package.
10. **Limits:** one clean closing card - Paper only, one setup, indicative options
    data, no demonstrated alpha.

That story is just as memorable as TradePilot's “Scan, Assess, Control, Execute,
Track,” while remaining uniquely ours.

## 13. Final assessment

### What likely made TradePilot competitive (`INFERENCE`)

1. A judge-ready public product, not only a repository.
2. A real model-to-risk-to-broker path that could be demonstrated end to end.
3. A familiar multi-agent vocabulary with simple, visible thresholds.
4. Strong visual consistency and a cinematic route built specifically for video.
5. A business-shaped interface: signup, portfolio, agents, API access, settings.
6. A concise story and an unusually polished, candid presentation.
7. A named four-person team with complementary roles.

### What the result does not prove

It does not prove that TradePilot had validated alpha, true multi-tenancy, a
production-grade audit trail, reliable developer infrastructure, or a safe live-
trading boundary. The repository and presentation explicitly acknowledge that
formal historical validation is unfinished, and this audit found several
execution defects that the absence of tests allowed to survive.

### Decision for Options Alpha

Do **not** move the model closer to financial authority merely to look more
agentic. Do **not** replace durable evidence with animated mock state. Do **not**
broaden instruments until the existing proof chain stays intact.

Instead:

> Make the current proof-carrying system feel alive, progressive, and
> commercially legible. Let judges see the whole loop first, then let them drill
> into the evidence that TradePilot did not persist.

That is the most defensible way to learn from second place without giving up the
engineering advantages we already earned.

## Sources

### Official event and submission artifacts

[^official-standings]: [Alpaca AI Trading Agents Hackathon - archived live dashboard and standings](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/live)
[^official-submission]: [TradePilot AI - official lablab.ai submission](https://lablab.ai/submissions/tpyjss8emfl37zk4jq9jz16t)
[^official-presentation]: [TradePilot - official 14-page submission presentation](https://storage.googleapis.com/lablab-static-eu/submissions/lexxviocpicsryejq31nhf4q/tpyjss8emfl37zk4jq9jz16t/presentation/presentation_vng30njbdqd76s1rzj17rb2k.pdf)

### TradePilot backend - pinned source

[^backend-readme]: [Backend README at `ec22f13`](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/README.md)
[^ai-service]: [`app/services/ai_service.py` - OpenAI call and schema](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/services/ai_service.py)
[^strategy-agent]: [`app/agents/strategy_agent.py` - model validation and quantitative corroboration](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/agents/strategy_agent.py)
[^market-agent]: [`app/agents/market_agent.py` - market data, indicators, and score](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/agents/market_agent.py)
[^risk-agent]: [`app/agents/risk_agent.py` - position, exposure, confidence, and model-risk gates](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/agents/risk_agent.py)
[^supervisor-agent]: [`app/agents/supervisor.py` - manual analysis and execution](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/agents/supervisor.py)
[^autonomous-agent]: [`app/agents/autonomous_agent.py` - scan, execution, protection, and in-memory state](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/agents/autonomous_agent.py)
[^alpaca-service]: [`app/services/alpaca_service.py` - Alpaca clients and order methods](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/services/alpaca_service.py)
[^trading-router]: [`app/routers/trading.py` - account, agent, order, and close-all endpoints](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/routers/trading.py)
[^dashboard-router]: [`app/routers/dashboard.py` - dashboard serialization and hardcoded Paper flag](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/routers/dashboard.py)
[^database]: [`app/database/database.py` - database initialization](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/database/database.py)
[^trade-model]: [`app/models/trade.py` - unused trade model](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/models/trade.py)
[^config]: [`app/core/config.py` - environment and broker-mode settings](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/core/config.py)
[^security]: [`app/core/security.py` - password, JWT, and app-key helpers](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/core/security.py)
[^auth-router]: [`app/routers/auth.py` - registration and login](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/routers/auth.py)
[^api-key-router]: [`app/routers/api_keys.py` - internal key creation/listing](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/app/routers/api_keys.py)
[^env-example]: [`.env.example` - example signing and service configuration](https://github.com/divine308/Tradepilot/blob/ec22f13abac8c04b61f29b531c07f3255f72d42a/.env.example)
[^backend-history]: [Backend commit history](https://github.com/divine308/Tradepilot/commits/main/)

### TradePilot frontend - pinned source

[^frontend-app]: [`src/App.jsx` - ten public/protected routes](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/src/App.jsx)
[^frontend-api]: [`src/services/api.js` - authentication, APIs, partial failure, and polling helpers](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/src/services/api.js)
[^frontend-agents]: [`src/pages/Agents.jsx` - analysis, autonomous controls, polling, and derived events](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/src/pages/Agents.jsx)
[^frontend-demo]: [`src/pages/Demo.jsx` - nine-scene scripted product film](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/src/pages/Demo.jsx)
[^frontend-markets]: [`src/pages/Markets.jsx` - real bars plus hardcoded market signals](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/src/pages/Markets.jsx)
[^frontend-api-keys]: [`src/pages/ApiKeys.jsx` - mock credentials and operational metrics](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/src/pages/ApiKeys.jsx)
[^frontend-settings]: [`src/pages/Settings.jsx` - local-only product controls](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/src/pages/Settings.jsx)
[^frontend-readme]: [Frontend README at `b1acfdf`](https://github.com/divine308/TradepilotAi/blob/b1acfdf3beee11ebd5fae6feeff7cd8cd0433f7d/README.md)
[^frontend-history]: [Frontend commit history](https://github.com/divine308/TradepilotAi/commits/main/)

### Alpaca reference documentation

[^alpaca-orders]: [Alpaca - Working with orders and client order IDs](https://docs.alpaca.markets/us/docs/working-with-orders)
[^alpaca-orders-at-alpaca]: [Alpaca - order classes, bracket/OCO behavior, and time in force](https://docs.alpaca.markets/us/docs/orders-at-alpaca)

### Options Alpha comparison sources

[^ours-readme]: [Options Alpha README](../README.md)
[^ours-provider]: [Options Alpha read-only Alpaca provider](../src/options_alpha_lab/providers/alpaca_readonly.py)
[^ours-lifecycle]: [Options Alpha durable execution lifecycle](../src/options_alpha_lab/execution/lifecycle.py)
[^ours-gateway]: [Options Alpha Paper-only execution gateway](../src/options_alpha_lab/execution/gateway.py)
