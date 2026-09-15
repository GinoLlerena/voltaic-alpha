# CODEX Winner Project Analysis — Alpha Hunter

**Analysis prefix:** `CWA-` (Codex Winner Analysis)  
**Document filename prefix:** `codex_`  
**Prepared for:** Voltaic Alpha / Options Alpha  
**Analysis date:** 9 September 2026  
**Winner repository:** `SUMANSHAKTI/alpaca`  
**Winner commit inspected:** `5a56a9de0ccb76297b3195fb1048f0fad46e7fd5`  
**Options Alpha commit compared:** `2657a1ee17033b9f61c4008b31285f03f2b9a236`

## 1. Executive conclusion

Alpha Hunter's decisive advantage is not stronger engineering. It is stronger
**perceptibility**: within seconds, a judge can understand an ambitious product,
see a complete research-to-execution loop, navigate seven product workspaces,
and watch named strategies compete for capital. The official archived event
dashboard lists Alpha Hunter as the number-one submission among 428 entries, and
the submission page provides a public demo and an 11-slide pitch deck.[^official-results]
[^official-submission]

Options Alpha is materially stronger in the parts that are hardest to fake and
most important in a real trading system: real bounded model use, data provenance,
options-specific contracts, durable persistence, exact order intent, idempotency,
broker reconciliation, restart safety, source labeling, negative-result
disclosure, and test depth.

The strategic lesson is therefore:

> Borrow Alpha Hunter's product story, visible lifecycle, progressive disclosure,
> and demo ergonomics. Keep Options Alpha's execution firewall, evidence model,
> truth labeling, and fail-closed behavior.

The best next version is not an imitation of Alpha Hunter. It is an
**AI Options Research Lab whose promotion and execution boundary is the existing
proof-carrying firewall**.

## 2. Scope, method, and confidence

The analysis used four parallel workstreams:

- architecture, agents, data flow, trading, risk, persistence, security, and
  deployment;
- frontend, information architecture, interaction design, and judge experience;
- independent product/rubric comparison and gap prioritization;
- direct verification through repository history, isolated builds/tests, the
  public submission page, pitch deck, archived scoreboard, and read-only public
  deployment endpoints.

The winner repository was cloned with full history and pinned to the commit above.
No winner code was changed. The comparison against Options Alpha used the current
workspace while preserving all pre-existing local changes.

Every numbered finding uses the `CWA-` prefix requested for this analysis.

### Evidence labels

| Label | Meaning |
|---|---|
| `VERIFIED-CODE` | Confirmed directly in the pinned source or Git history |
| `VERIFIED-RUN` | Reproduced through a build, test, database inspection, or read-only endpoint |
| `OFFICIAL` | Supported by the official event, submission, or presentation artifact |
| `INFERENCE` | A reasoned explanation, not judge feedback or a published scorecard |

### Important limitation

The repository's final commit is dated 4 September 2026 and may not perfectly
match the exact build shown to judges. The current deployment can also differ from
the judged state. No written judge feedback or private scoring sheet was available.
Accordingly, statements about *why* it ranked first are explicitly presented as
inference, not fact.

## 3. Comparative scorecard

| Dimension | Alpha Hunter | Options Alpha | Assessment |
|---|---|---|---|
| First impression | Immediate “Autonomous AI Trading Scientist” category and memorable thesis | Precise execution-firewall claim, but opens defensively | Alpha Hunter stronger |
| Product breadth | Strategies, regimes, equities/ETFs/crypto, allocation, charts, commands, analytics | One SPY setup and one defined-risk options family | Alpha Hunter looks broader |
| Actual AI integration | No model invocation in the inspected repository | Real bounded OpenAI call with strict schema and fail-closed validation | Options Alpha decisively stronger |
| Quant evaluation | Compelling OOS/robustness/Edge Score vocabulary, mostly simulated | Honest ablation, threshold sensitivity, lifecycle friction, no alpha claim | Options Alpha stronger evidence |
| Market-data provenance | Alpaca → Yahoo → synthetic fallback without downstream provenance | Provider/feed/times/pages/payload/hash and frozen manifests | Options Alpha decisively stronger |
| Storage | Broad ORM schema, but runtime state is in memory and database is empty | Durable linked records from snapshot through position and incident | Options Alpha decisively stronger |
| Frontend | Polished React/Vite dashboard with seven workspaces | Focused Streamlit forensic viewer with five evidence views | Alpha Hunter stronger presentation |
| Broker lifecycle | Direct order submission; failures may become simulated fills | Immutable intent, exact request, deterministic ID, ambiguity lookup, reconciliation | Options Alpha decisively stronger |
| Operations | Familiar Render/Vercel/Docker packaging | Separate dashboard/worker, lease, health, backup, startup reconciliation | Options Alpha stronger safety |
| Reproducibility | Loose Python ranges, unseeded results, shallow tests | Locked environment, frozen fixtures, hashes, replay, 481 collected tests | Options Alpha decisively stronger |
| Business legibility | A trader can imagine the product immediately | Strong compliance/audit buyer case, but more abstract in the UI | Alpha Hunter more visceral |

## 4. What Alpha Hunter did that Options Alpha did not

### `CWA-001` — It named a memorable product category (`OFFICIAL`, `VERIFIED-CODE`)

Alpha Hunter leads with “Autonomous AI Trading Scientist” and a single contrast:
other systems choose trades; Alpha Hunter discovers which strategies deserve to
trade. Its README then presents the complete loop before discussing setup.[^winner-readme]

The deck is equally disciplined. It frames one missing layer—continuous strategy
judgment—and reduces the solution to `DISCOVER → CHALLENGE → SCORE → ALLOCATE →
EXECUTE`.[^winner-deck]

Options Alpha has a stronger and more original sentence—“the model may write the
memo, but it cannot trade”—but its README immediately emphasizes what the project
is *not* and presents disclosures before a visual or interactive product story.
That is technically responsible but less effective during a fast review.[^ours-readme]

**Lesson:** lead with the positive product outcome, then prove the constraints.

### `CWA-002` — It made the entire lifecycle visible (`VERIFIED-CODE`)

The winner exposes seven named workspaces:

1. Dashboard
2. Live Trading Chart
3. Strategy Lab
4. Trade Explorer
5. P&L Analytics
6. AI Council
7. Command Center

Those workspaces are visible in one navigation bar and are rendered as distinct
product surfaces.[^winner-header][^winner-app]

Options Alpha's five views are deeper and more trustworthy, but they are all
variations of forensic evidence inspection. Alpha Hunter gives judges multiple
ways to understand the same idea: portfolio summary, strategy cards, lifecycle
labels, charts, activity events, trade explanations, and command responses.

**Lesson:** repeat the value proposition through different visual forms, without
repeating unsupported claims.

### `CWA-003` — It turned strategies into product objects (`VERIFIED-CODE`)

Four seeded strategies have names, hypotheses, rule summaries, target regimes,
Edge Scores, allocations, and lifecycle states. One deliberately flawed strategy
is visibly `KILLED`, making negative selection part of the product story.[^winner-orchestrator]

Options Alpha deliberately proves one SPY setup and two mirrored debit-spread
structures. That narrowness makes the execution evidence rigorous, but it does not
create the impression of a research platform.

**Lesson:** show several research candidates—including rejected ones—while
keeping the execution scope narrow.

### `CWA-004` — It used progressive disclosure (`VERIFIED-CODE`)

Strategy cards provide a scan-friendly summary; a modal reveals entry, exit,
stop, sizing, train/OOS, and adversarial details. The trade table uses a direct
“WHY THIS TRADE?” action before revealing the thesis, evidence checklist, risk
metrics, and council signatures.[^winner-strategy-ui][^winner-explain-ui]

Options Alpha exposes stronger evidence, but a judge has to understand labels such
as “approval lineage” and assemble the story across multiple panels.

**Lesson:** add one evidence-backed “Why this decision?” summary before the full
forensic record.

### `CWA-005` — It made the system feel alive (`VERIFIED-CODE`)

The frontend polls account, strategy, position, order, and event endpoints; its
chart opens a WebSocket; the interface offers filters, timeframes, quick command
chips, discovery, optimization preview, confirmation, and status transitions.
These interactions make the system feel like a running product.[^winner-app]
[^winner-chart][^winner-command]

Options Alpha correctly prevents the public dashboard from controlling execution.
It can still offer safe interactions: select a frozen case, run a local replay,
compare model/no-model output, perturb a threshold, expand a hash chain, or export
a redacted proof package.

### `CWA-006` — It created a clear visual identity (`VERIFIED-CODE`)

The dark terminal palette, emerald accent, glass cards, monospaced quantitative
labels, status chips, subtle motion, and glow are applied consistently through
central CSS utilities.[^winner-css]

Options Alpha's amber-for-model and blue-for-deterministic semantic colors are
more meaningful and should not be replaced. The opportunity is to apply them
with the same consistency and visual confidence.

### `CWA-007` — It used a familiar full-stack package (`VERIFIED-CODE`)

React + TypeScript + Vite sits in front of FastAPI. Docker, Compose, Render, and
Vercel manifests make the deployment shape easy to recognize. The frontend has a
single API configuration module and the repository has a one-command local
launcher.[^winner-deploy]

This simplicity is good communication even though the runtime has serious
operational weaknesses discussed later.

### `CWA-008` — It optimized late work for the demo surface (`VERIFIED-CODE`)

The 16-commit history spans roughly 34 hours. After a large initial import, the
team added adaptive allocation and command interactions, synchronized the live
Alpaca portfolio, added the interactive chart, configured production URLs and
Render deployment, then added portfolio performance and simplified the final
README.[^winner-history]

The sequence reveals a clear hackathon priority: make the product visible,
interactive, deployable, and legible before deepening correctness. That is risky
engineering, but effective presentation triage.

## 5. Architecture: claim versus implementation

The advertised architecture is an excellent story:

```text
Market data
    ↓
Market regime
    ↓
Strategy discovery
    ↓
Out-of-sample backtest
    ↓
Adversarial challenge
    ↓
Edge score + lifecycle
    ↓
Capital allocation
    ↓
Deterministic risk
    ↓
Alpaca Paper execution
    ↓
Performance monitoring
```

The actual implementation is one synchronous Python orchestrator containing
mutable in-memory lists and calling module-level singleton services. It is a
pipeline, not an agent debate or consensus system.[^winner-orchestrator]

### `CWA-009` — The “agents” are useful product taxonomy, not model agents (`VERIFIED-CODE`)

`LLM_PROVIDER`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` exist in configuration, but
the dependency list contains no OpenAI or Gemini SDK and no provider invocation,
prompt, or response schema exists in the backend.[^winner-config][^winner-deps]

Discovery randomly selects one of five predefined dictionaries. The adversary
uses conditional branches and static narrative output. The portfolio manager and
evolution engine use explicit arithmetic. This can still be described as a
multi-component agent architecture in a broad sense, but the inspected repository
does not contain a language-model-powered multi-agent implementation.[^winner-discovery]

This matters because the official submission is tagged with ChatGPT and describes
an adversarial AI layer.[^official-submission] The finding is about the pinned
repository, not an allegation about what may have run in another judged build.

### `CWA-010` — Component-by-component reality check (`VERIFIED-CODE`)

| Stage | What is real | What is simulated, static, or missing |
|---|---|---|
| Market Intelligence | SMA20/SMA50, volatility, momentum, and volume calculations over returned bars | Fixed confidence thresholds; no model |
| Discovery | Structured strategy dictionaries and regime labels | Random choice from predefined templates; rules are free text |
| Backtest | Chronological 70/30 split and an explicit cost deduction | Strategy rules never execute; returns and metrics are random draws |
| Adversary | Clear `PASS/WATCH/REJECT` vocabulary | Monte Carlo, concentration, and parameter-perturbation claims are static strings |
| Evolution | Explicit weighted Edge Score and lifecycle thresholds | Inputs inherit simulated metrics |
| Portfolio Manager | Edge-weighted allocation with cash reserve | No portfolio covariance or actual optimization |
| Adaptive Allocator | Heuristics for asset class, concentration, sector, and crypto | Several assumptions are fixed, including a bullish regime in one path |
| Risk | Strategy-state, buying-power, size, daily-loss, and recent-order checks | Conflicting limits; incomplete validation; in-memory duplicate guard |
| Execution | Real Alpaca Paper request path when configured | Broker exceptions silently fall through to a simulated filled order |
| Performance Monitor | Simple loss-streak response exists | Imported but not used in the live loop; demo step mutates score manually |
| Explainability | Consistent structured presentation | Several claims and approvals are fixed regardless of complete evidence |

The market-regime calculation and Edge Score formula are understandable and
transferable as presentation patterns.[^winner-market-intel][^winner-evolution]
The backtest and adversary outputs are not valid quantitative evidence.

### `CWA-011` — The backtest does not test the strategies (`VERIFIED-CODE`)

The backtest reads closing prices only to determine the number of generated
returns. For “healthy” strategies it samples returns, win rate, profit factor,
Sharpe, and drawdown from favorable random distributions. A strategy whose name
contains “RSI Extreme Reversal” is routed to a pre-defined failure distribution
and forced to fail OOS.[^winner-backtest]

Consequences:

- entry and exit rules are never evaluated;
- the same strategy can report different metrics across runs;
- the 70/30 split is structurally chronological but scientifically meaningless;
- the presentation's OOS and Edge Score values cannot establish strategy quality.

### `CWA-012` — The adversary narrates tests it does not run (`VERIFIED-CODE`)

The adversary returns phrases such as “Monte Carlo 1,000 run survival rate” and
“parameter drift maintains Positive Expectancy,” but no corresponding simulation
or perturbation loop exists. The rejected score attempts to call NumPy only if
`np` exists in globals; NumPy is not imported, so that path always returns the
constant `31.0`.[^winner-adversary]

The *concept* is excellent: strategies should be attacked before promotion. The
implementation should be replaced with deterministic, recorded experiments.

### `CWA-013` — The advertised autonomous scan cannot select a buy (`VERIFIED-CODE`)

`run_autonomous_scan` is defined twice; Python keeps the second definition. The
active implementation reads `rec.get("score", 0)`, but the allocator emits the
field as `allocation_score`. The score therefore defaults to zero, making the
`score >= 75` buy condition unreachable for allocator-produced recommendations.
[^winner-orchestrator][^winner-allocator]

The background loop still starts automatically every 15 seconds and calls this
method, so the system can look active while the intended automated entry branch
remains disabled by an integration mismatch.

### `CWA-014` — The MCP adapter is a label, not an integration (`VERIFIED-RUN`)

The single file under `backend/app/mcp_tools` contains
`def get_account((self)`, which is invalid Python. It is not imported by the
runtime and there is no MCP server wiring. Static compilation fails on this file.
[^winner-mcp]

## 6. Market data and provenance

### `CWA-015` — Demo resilience was prioritized over source truth (`VERIFIED-CODE`)

The market-data service uses three tiers:

1. Alpaca IEX for stocks when credentials are live;
2. Yahoo Finance through a raw chart endpoint;
3. synthetic seeded historical bars or randomly moving fallback quotes.

This is pragmatic for keeping a demo populated, but the returned quote does not
carry `source`, `feed`, `as_of`, `quality`, or `is_synthetic` fields. Downstream
risk and execution cannot distinguish real broker data from a fallback.[^winner-market-data]

The watchlist API adds random volume jitter “to demonstrate real-time feed
updates,” and the WebSocket polls the quote service every second while emitting
OHLC values that are all equal with a fixed volume of 500.[^winner-market-routes]

**Do adopt:** graceful availability and explicit fixture/demo modes.

**Do not adopt:** silent fallback or synthetic motion labeled as live.

### `CWA-016` — Options Alpha's existing provenance is a product advantage (`VERIFIED-CODE`)

Options Alpha's read adapter records provider, endpoint, feed, source time,
receipt time, pagination, payload, and hash. It also handles option-chain
pagination and feed entitlement explicitly.[^ours-read-adapter]

That provenance should move from the forensic layer into the visible product UI:
every metric and chart should carry a badge such as `LIVE ALPACA`, `FROZEN ALPACA`,
`REPLAY`, `INDICATIVE`, `STALE`, or `UNAVAILABLE`.

## 7. Storage, state, and auditability

### `CWA-017` — The database schema is broad but unused (`VERIFIED-CODE`, `VERIFIED-RUN`)

The winner defines tables for market regimes, strategies, backtests, adversary
reports, portfolio snapshots, positions, orders, trades, agent events, and audit
logs. That domain vocabulary is useful.[^winner-models]

However:

- the committed `backend/alpha_hunter.db` is a zero-byte file;
- no runtime service inserts or queries the ORM models;
- routes never inject `get_db`;
- the model module is not imported before `create_all`, so metadata registration
  is not assured;
- discovered strategies, trades, events, and audit records remain Python lists.

The schema is therefore design intent, not implemented persistence.

### `CWA-018` — The audit trail is ephemeral (`VERIFIED-CODE`, `VERIFIED-RUN`)

Every agent event receives the literal timestamp `15:36:20`. The audit list is
process memory and disappears on restart.[^winner-orchestrator]

A read-only query to the public deployment on 9 September confirmed one agent
event with that fixed timestamp and an empty audit-log response. The live account
endpoint also exposes the Paper account number publicly; the identifier is not
reproduced here because it is unnecessary to the analysis.

### `CWA-019` — Options Alpha's persistence is much closer to a real audit product (`VERIFIED-CODE`)

Options Alpha stores the exact observation, signals, evidence pack, model-call
metadata, thesis, structure, risk result, decision hash, immutable intent,
prepared request, broker order, fill, position, and incident. Broker status and
local lifecycle state are deliberately separate, and ordered transitions are
recorded rather than reconstructed from UI state.[^ours-models][^ours-repository]

If the winner's strategy/backtest/adversary catalog is adopted, it should use
Options Alpha's existing foreign keys, hashes, timestamps, schema versions,
migrations, and append-oriented evidence.

## 8. Alpaca integration, execution, and risk

### `CWA-020` — Alpaca is visibly integrated (`VERIFIED-CODE`, `VERIFIED-RUN`)

The winner creates a Paper `TradingClient`, verifies the account, reads live
account and position state, normalizes symbols, and recursively inspects open
orders and bracket legs for stop-loss, trailing-stop, and take-profit values.
[^winner-client][^winner-portfolio]

This visible broker state is a genuine presentation strength. The public account,
strategies, and event endpoints were responsive during the analysis.

### `CWA-021` — A broker error can become a phantom success (`VERIFIED-CODE`)

If Alpaca submission raises any exception, the trading service silently falls
through to its simulation branch and returns a synthetic `alpaca-paper-*` order
with status `filled`. If Alpaca accepts an order without a fill price, the code
uses the current quote as `filled_price`.[^winner-trading]

This destroys the distinction among rejection, ambiguity, acceptance, and fill.
It is precisely the class of failure Options Alpha's intent/request/order/fill
lifecycle prevents.

### `CWA-022` — Execution lacks durable idempotency and reconciliation (`VERIFIED-CODE`)

No deterministic `client_order_id` is supplied. The duplicate guard is an
in-memory list of the last few `symbol-side-qty` strings and resets with the
process. There is no ambiguous-submit lookup, pending/partial lifecycle, startup
reconstruction, or durable concurrency control.[^winner-risk][^winner-trading]

By contrast, Options Alpha derives order identity from approved evidence, records
state before broker mutation, looks up ambiguous submissions rather than blindly
retrying, and reconciles broker state before taking new risk.[^ours-gateway]

### `CWA-023` — Risk controls exist but disagree (`VERIFIED-CODE`)

The risk module enforces several real checks: strategy must be `ALIVE`, buying
power must cover the order, value must fit a single-position cap, the daily-loss
circuit breaker must remain clear, and a recent-order cache must not match.
[^winner-risk]

The limits conflict across layers:

- configuration states a 25% single-position cap and 5% daily loss;
- the active risk code permits 35% for non-BTC positions;
- the adaptive allocator uses 25%, 3% daily loss, and 10% drawdown;
- the command center advertises the allocator values rather than the active gate;
- trade execution supplies a hard-coded positive daily P&L value;
- quantity, price positivity, and legal side values are not fully validated;
- an unknown strategy ID falls back to the first strategy.

The code also describes stock quantities as “option lots” in comments but never
submits option contracts or multi-leg orders.

### `CWA-024` — The public mutation boundary is unsafe (`VERIFIED-CODE`)

CORS allows every origin, method, and header, while no route has authentication or
authorization. Public endpoints can scale positions, increase all lots, execute
an allocation plan, toggle or trigger the autonomous loop, submit a Paper trade,
kill a strategy, and interpret natural-language buy commands.[^winner-main]
[^winner-routes]

Paper trading limits financial loss, but it does not make unauthenticated mutation
acceptable. Options Alpha's separation between a credential-free read-only judge
surface and a credentialed worker is categorically stronger.

### `CWA-025` — Repository history shows speed-over-hygiene tradeoffs (`VERIFIED-CODE`)

The initial repository included installed frontend dependencies, compiled Python
bytecode, build outputs, and a tracked `.env`; later commits removed those files
and added proper ignores.[^winner-history]

Deleting a secret file from the current tree does not remove it from Git history.
Without reproducing or inspecting any secret, the safe operational conclusion is:
any credential ever committed should be treated as compromised and rotated.

## 9. Frontend and judge experience

### `CWA-026` — The frontend's primary achievement is completeness (`VERIFIED-CODE`)

The main dashboard combines account KPIs, a watchlist, portfolio performance,
market regime, agent activity, strategy laboratory, and active positions. Dedicated
views then expand charts, trades, analytics, council activity, and commands.
[^winner-app]

The page gives the viewer three levels:

1. **status:** account, cash, buying power, P&L, connectivity;
2. **decision:** regime, strategy status, Edge Score, allocation;
3. **explanation:** rules, OOS view, adversarial findings, trade thesis, risk.

This hierarchy is the strongest frontend lesson for Options Alpha.

### `CWA-027` — The AI Council is excellent information design (`VERIFIED-CODE`)

Seven named stages each display a compact result: regime, proposed strategy, OOS
metric, robustness, allocation, risk approval, and execution. The implementation
is static, but the visual model makes the pipeline understandable immediately.
[^winner-council]

Options Alpha's authority rail is more accurate because it distinguishes model
authority from deterministic authority. It should add the winner's compact
“output of every stage for this case” view without implying consensus where none
exists.

### `CWA-028` — Important UI evidence is hard-coded (`VERIFIED-CODE`)

Examples include:

- fixed “live” and “connected” statuses in the header;
- sample strategy equity curves;
- fixed robustness findings and Monte Carlo claims;
- a default all-pass explainability checklist;
- fixed AI Council outcomes;
- canned P&L and risk metrics;
- static strategy/backtest/adversary values passed into the chart council panel;
- watchlist prices retained silently when requests fail.

These choices create demo confidence at the cost of evidentiary confidence.
[^winner-header][^winner-strategy-ui][^winner-explain-ui][^winner-council]

### `CWA-029` — Some attractive controls are incomplete (`VERIFIED-CODE`)

- The landing page exists but normal navigation cannot reach it.
- The demo walkthrough component is never imported or rendered.
- Demo Mode suppresses the WebSocket rather than producing a labeled demo stream.
- Several chart checkboxes update state without changing chart series.
- The chart trade-detail modal has no path that sets its selected trade.
- The walkthrough says command text mutates take-profit, stop-loss, and quantity,
  while current API branches only read and report them.

The lesson is not to avoid interaction. It is to run every judge-visible control
end to end and label the source of every resulting state.

### `CWA-030` — Failure can be rendered as health (`VERIFIED-CODE`)

If a command request throws, the frontend inserts a reassuring message saying the
system is operating within deterministic limits. A network or server failure can
therefore look like a healthy answer.[^winner-command]

Options Alpha must retain the opposite rule: show failure, freshness, and the last
known-good source explicitly. Never synthesize a healthy state.

### `CWA-031` — Visual polish has accessibility costs (`VERIFIED-CODE`)

The winner uses many 10–12 pixel uppercase labels, glow, pulsing indicators, and
monospaced body text. Modals do not visibly implement focus trapping, Escape
handling, or complete accessible naming. Options Alpha's semantic color intent,
focus treatment, and reduced-motion support should remain non-negotiable.

## 10. Pitch deck and submission strategy

### `CWA-032` — The deck sells one idea repeatedly (`OFFICIAL`)

The 11 slides follow a clean progression:

1. product thesis;
2. problem: static strategies, overfitting, blind allocation;
3. five-step solution;
4. AI research loop;
5. one surviving strategy;
6. Edge Score ranking;
7. broker execution;
8. risk stack;
9. portfolio intelligence;
10. command center;
11. final contrast: bots execute, Alpha Hunter reasons.

The deck uses large headlines, little prose, and one repeated lifecycle. It also
carefully calls values “current application states” rather than promises of future
return.[^winner-deck]

The technical caveat is that the deck says to use application-derived metrics,
while the application derives key metrics from random or static outputs. The
presentation pattern is worth adopting; the evidence practice is not.

### `CWA-033` — The official submission is concise and outcome-oriented (`OFFICIAL`)

The submission describes a complete loop—Discover, Test, Challenge, Score,
Allocate, Execute, Monitor, Learn—and explains the purpose of each layer in
business language. It links directly to GitHub, the presentation, and the public
demo, and it lists four team members.[^official-submission]

Options Alpha's submission package is more rigorous and includes a deck, cover,
video script, checklist, narrative, rubric mapping, disclosures, and freeze
process. Its remaining weakness is discoverability: the README should become a
judge launchpad with direct links to the live app, video, deck, and 90-second path.
[^ours-submission]

### `CWA-034` — Why it likely ranked first (`INFERENCE`)

The available evidence supports five likely factors:

1. **Immediate category clarity.** The first sentence establishes a larger product
   than a trade picker.
2. **Perceived completeness.** Seven workspaces, live-looking state, strategies,
   capital, and execution imply an end-to-end company, not a technical slice.
3. **Memorable lifecycle.** `Discover → Challenge → Score → Allocate → Execute`
   is easier to retain than a database-centered audit explanation.
4. **Interactive demo moments.** Discovery, optimization, command input, charts,
   and broker state create visible motion.
5. **Broad future value.** Multiple asset classes and strategies make the product
   feel commercially extensible.

This is not a claim that judges rewarded weak code or that the ranking was based
on the repository alone. It is an inference from the official artifacts and
shipped presentation surface.

## 11. Reproducibility and verification results

### `CWA-035` — Winner validation results (`VERIFIED-RUN`)

All checks used isolated temporary environments and the declared dependency files.

| Check | Result | Interpretation |
|---|---|---|
| Full Git history | 16 commits, one listed author, 2–4 Sep 2026 | A very compressed build window |
| SQLite inspection | `backend/alpha_hunter.db` is 0 bytes; no tables | Committed database stores no data |
| Python static compilation | Failed on `mcp_tools/tools.py` malformed function signature | Unused MCP adapter does not parse |
| Winner risk tests | 4 passed | Basic strategy-state, buying-power, oversize, and approval checks work |
| Winner lifecycle tests | 1 passed, 2 failed | Offline fallback crashes on `Generator.randint` |
| Full winner test collection | Error | Import-time market fetch falls to the same synthetic-data bug |
| Frontend dependency install | Succeeded from lockfile | Frontend is reproducible enough to install |
| Frontend production build | Succeeded | 2,294 modules; output generated successfully |
| Frontend bundle | 840.72 kB JavaScript, 239.46 kB gzip | Vite emitted a >500 kB chunk warning |
| Package audit at install | 1 moderate and 1 high vulnerability reported | Requires separate dependency remediation |
| Public read-only endpoints | Health, strategies, events, audit log, and account responded | Deployment was online during analysis |

The synthetic fallback calls `rng.randint`, but NumPy's `Generator` API uses
`integers`; this is a repository defect, not merely a network restriction. It is
triggered when live/Yahoo data is unavailable.[^winner-market-data]

The winner's walkthrough says its own environment achieved 10/10 tests and a
successful frontend build. Both statements can coexist with our result if its
test environment had network access and did not enter the broken fallback.
[^winner-walkthrough]

### `CWA-036` — Options Alpha validation result (`VERIFIED-RUN`)

The current Options Alpha suite collected 481 tests and completed successfully in
the analysis environment, with one visible skip and no failure. This does not
prove product success, but it makes the architecture and lifecycle claims much
more reproducible than the winner's current repository.

## 12. What Options Alpha already does better

### `CWA-037` — Real bounded model use

Options Alpha makes a real Responses API call, disables provider-side storage,
uses a strict schema, constrains direction, validates evidence references, and
fails closed.[^ours-model]

### `CWA-038` — Genuine options depth

Options Alpha models and executes a native multi-leg defined-risk option spread,
persists exact legs and request bytes, and records the open/close lifecycle. The
winner submits simple single-symbol market or limit orders and does not implement
an option chain, Greeks, expiry, assignment, or multi-leg order.

### `CWA-039` — Proof-carrying execution authority

The only write path accepts an immutable approved intent, verifies execution mode
and the resolved Paper endpoint immediately before submission, checks exact
request identity, and resolves ambiguous submissions using deterministic broker
identity. The public dashboard cannot import or reach that gateway.[^ours-gateway]

### `CWA-040` — Durable lifecycle and restart behavior

Options Alpha persists approval, request, broker status, fills, positions,
incidents, leases, and observations. Startup and every worker cycle reconcile
before opening new risk. Accepted is never treated as filled.

### `CWA-041` — Honest negative results

The project publishes the losing Paper round trip, the indicative-feed limitation,
the tiny sample, the unproven thresholds, the absence of established alpha, and
an ablation where the model changed no action. This is unusually strong evidence
discipline and should remain a central trust signal—after the positive value
proposition, not before it.[^ours-readme][^ours-submission]

## 13. Prioritized adoption plan

### P0 — Before the next major presentation

#### `CWA-REC-001` — Create a judge-first first viewport

Lead with:

> The model can write the memo. It cannot trade.

Add three proof tiles sourced from real artifacts:

- `1` completed Paper MLeg lifecycle;
- `5/5` model/no-model action agreement;
- `1` code path permitted to express a broker write.

Include a source/freshness badge and a “Start 90-second evidence tour” action.

#### `CWA-REC-002` — Make the README internally current

The README still contains a historical “out of scope” section saying there is no
order submission, autonomous execution, production UI, or trading bot, while
later sections describe the deployed worker and Paper execution. Replace this
with one authoritative “Current build” section and move historical architecture
increments to implementation notes.[^ours-readme]

Also correct the stale “three frozen cases” statement if the final ablation has
five cases.

#### `CWA-REC-003` — Add a read-only guided tour

The tour should only navigate recorded evidence:

1. Authority boundary
2. Qualified case
3. Deterministic refusal before model call
4. Risk approval and exact broker request
5. Broker fill, close, reconciliation, and flat state
6. Model/no-model ablation and limitations

No tour action may call the worker, approve intent, or express a broker mutation.

#### `CWA-REC-004` — Add a “Why this decision?” drawer

For the selected case, summarize:

- observed evidence and source;
- deterministic qualification or refusal;
- bounded model contribution, if any;
- risk decision;
- final action;
- broker outcome;
- reproducibility hash.

Then link to the existing detailed views.

#### `CWA-REC-005` — Turn the README into a judge launchpad

Place live app, five-minute video, deck PDF, 90-second route, clean-clone
validation command, and a one-line disclosure summary near the top.

### P1 — Next product iteration

#### `CWA-REC-006` — Add a real research catalog

Introduce versioned entities for:

- strategy hypothesis;
- parameter set;
- dataset/snapshot manifest;
- walk-forward run;
- adversarial test;
- promotion decision;
- deployment version;
- deterioration/retirement event.

Use lifecycle labels such as `PROPOSED`, `TESTING`, `CHALLENGED`, `ELIGIBLE`,
`PAPER_ACTIVE`, `PAUSED`, and `RETIRED`.

#### `CWA-REC-007` — Implement genuine walk-forward and adversarial evaluation

Use frozen Alpaca bars, deterministic seeds, realistic costs, repeated
chronological folds, parameter perturbation, return concentration, regime slices,
minimum-sample thresholds, and explicit uncertainty. Store every input, parameter,
result, and code version with hashes.

Do not expose an Edge Score until its formula, sample requirements, and calibration
are defensible.

#### `CWA-REC-008` — Give the model bounded research jobs

The model can add visible value without execution authority by:

- proposing candidate hypotheses in a strict schema;
- extracting counter-evidence;
- generating failure scenarios for deterministic testing;
- comparing explanations;
- summarizing why a candidate was rejected.

Deterministic code must calculate metrics, promote strategies, size risk, and
authorize execution. Evaluate research usefulness separately from action
agreement.

#### `CWA-REC-009` — Add honest visualizations

Useful evidence-backed charts include:

- qualified versus refused decisions by reason;
- model versus deterministic action across ablation cases;
- order lifecycle timeline;
- risk budget used versus available;
- evidence → decision → intent → request → broker hash chain;
- strategy-candidate funnel from proposed to rejected/deployed.

Do not add Sharpe, win rate, cumulative P&L, or strategy rankings until the sample
and calculation support them.

#### `CWA-REC-010` — Add downloadable redacted proof

Export the selected snapshot metadata, hashes, memo or explicit “not called,” risk
record, intent, request hash, broker state, fills, and disclosure block. This turns
auditability into a tangible user workflow.

#### `CWA-REC-011` — Add URL-addressable scenarios

Give the refusal, lifecycle, lineage, and ablation stable links so the README and
deck can open the exact evidence view.

### P2 — After the evidence model is extended

#### `CWA-REC-012` — Consider a React read-only frontend

React would make cards, modals, charts, deep links, responsive navigation, and
guided tours easier. It should consume a read-only audit API or database replica,
never a public broker-capable API.

Preserve these non-negotiable rules:

- explicit live/frozen/replay/synthetic source labels;
- no healthy-state fabrication;
- every displayed number linked to evidence;
- semantic model-versus-deterministic authority colors;
- focus, keyboard, and reduced-motion accessibility;
- no unauthenticated mutation route;
- no broker client or credentials in the judge surface.

#### `CWA-REC-013` — Expand execution only behind portfolio-wide controls

Multiple strategies and positions should arrive only after portfolio risk,
correlation, concentration, liquidity, expiration, and concurrent lifecycle
controls are durable and tested. Perceived breadth can be created in research
mode before execution breadth is safe.

## 14. Proposed synthesis

```text
AI OPTIONS RESEARCH LAB
    ├── generate hypotheses
    ├── collect counter-evidence
    ├── run real walk-forward tests
    ├── perturb parameters and regimes
    └── publish candidate lifecycle
                    │
                    ▼
DETERMINISTIC PROMOTION GATE
    ├── evidence completeness
    ├── minimum sample
    ├── robustness thresholds
    └── deployment eligibility
                    │
                    ▼
PROOF-CARRYING EXECUTION FIREWALL
    ├── immutable approved intent
    ├── Paper-only resolved endpoint
    ├── deterministic risk and identity
    └── ambiguity-safe submission
                    │
                    ▼
ALPACA PAPER + DURABLE RECONCILIATION
    ├── order/fill/position lifecycle
    ├── restart recovery
    ├── exit precedence
    └── evidence-backed monitoring
```

This combines the winner's best idea—a strategy earns the right to trade—with
Options Alpha's best idea—a model can never manufacture trading authority.

## 15. Suggested 90-second judge journey

| Time | View | Judge takeaway |
|---|---|---|
| 0–10s | Hero + three proof tiles | “I understand what this is.” |
| 10–25s | Authority pipeline | “The model is useful but structurally unable to trade.” |
| 25–40s | Qualified case / Why this decision | “Evidence and risk produce one exact candidate.” |
| 40–55s | Refusal | “The model is not called when deterministic evidence fails.” |
| 55–70s | Hash-linked order lifecycle | “I can reconstruct intent, request, broker state, fill, and close.” |
| 70–82s | Ablation + limitations | “The team measured the model honestly.” |
| 82–90s | Business workflow | “A reviewer can verify and export the decision package.” |

## 16. Final decision register

| Decision | Recommendation | Rationale |
|---|---|---|
| Copy the winner's backend architecture | **No** | It is less safe, less durable, and less reproducible |
| Copy the winner's visual style exactly | **No** | Preserve Options Alpha's semantic authority colors and accessibility |
| Adopt a strategy lifecycle | **Yes** | It creates understandable breadth without broadening execution |
| Add a strategy lab | **Yes** | Use real recorded research artifacts and rejected candidates |
| Add an AI Council view | **Yes, renamed accurately** | Show stage outputs and authority, not fictional consensus |
| Add a natural-language trading console | **No** | A public query must never create execution authority |
| Add a read-only audit query | **Yes** | Explanation/search can improve discoverability safely |
| Add demo fallbacks | **Yes, explicitly labeled** | Availability is useful only when provenance remains visible |
| Add real walk-forward/adversarial tests | **Yes** | This converts compelling vocabulary into defensible evidence |
| Rewrite the execution core | **No** | The current firewall is the project's strongest asset |
| Improve first-90-second storytelling | **Yes, highest priority** | Correctness currently takes too long to perceive |

## 17. Bottom line

Alpha Hunter made an ambitious product obvious. Options Alpha made a difficult
safety property true.

The next competitive step is to make Options Alpha's truth as easy to perceive as
Alpha Hunter's ambition: a judge-first overview, a visible strategy lifecycle, a
read-only guided tour, progressive explanation, and evidence-backed visualizations.
The engineering foundation should remain the existing proof-carrying execution
firewall.

## Sources

### Official event and submission artifacts

[^official-results]: [Alpaca AI Trading Agents Hackathon — archived live dashboard and final standings](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/live)

[^official-submission]: [Alpha Hunter — official lablab.ai submission page](https://lablab.ai/submissions/dfdw7wkv91cnyhglp84gx6vm)

[^winner-deck]: [Alpha Hunter — official 11-slide presentation PDF](https://storage.googleapis.com/lablab-static-eu/submissions/mpjpv4pjrl5b9gh6ebv57591/dfdw7wkv91cnyhglp84gx6vm/presentation/presentation_ql0hg2pqlufejmq0mpm24j4q.pdf)

### Winner repository, pinned commit

[^winner-readme]: [Winner README, lines 1–119](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/README.md#L1-L119)

[^winner-history]: [Winner repository commit history](https://github.com/SUMANSHAKTI/alpaca/commits/main/)

[^winner-deps]: [Winner Python dependencies](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/requirements.txt#L1-L13)

[^winner-config]: [Winner configuration](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/config.py#L11-L38)

[^winner-orchestrator]: [Winner orchestrator](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/orchestrator.py#L20-L644)

[^winner-discovery]: [Winner discovery agent](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/discovery.py#L5-L138)

[^winner-market-intel]: [Winner market-intelligence agent](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/market_intel.py#L7-L89)

[^winner-backtest]: [Winner backtest agent](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/backtest.py#L8-L126)

[^winner-adversary]: [Winner adversary agent](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/adversary.py#L4-L90)

[^winner-evolution]: [Winner evolution engine](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/evolution.py#L4-L39)

[^winner-allocator]: [Winner adaptive allocator](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/adaptive_allocator.py#L14-L257)

[^winner-risk]: [Winner deterministic risk agent](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/agents/risk_agent.py#L7-L99)

[^winner-market-data]: [Winner market-data service](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/alpaca/market_data.py#L13-L581)

[^winner-market-routes]: [Winner market-data API and WebSocket](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/api/market_data_routes.py#L17-L247)

[^winner-client]: [Winner Alpaca client manager](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/alpaca/client.py#L7-L56)

[^winner-portfolio]: [Winner portfolio and protection reconciliation](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/alpaca/portfolio.py#L9-L283)

[^winner-trading]: [Winner Alpaca trading service](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/alpaca/trading.py#L10-L88)

[^winner-models]: [Winner SQLAlchemy models](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/db/models.py#L6-L169)

[^winner-main]: [Winner FastAPI app, CORS, and background loop](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/main.py#L31-L146)

[^winner-routes]: [Winner API routes](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/api/routes.py#L132-L405)

[^winner-mcp]: [Winner MCP tools adapter](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/backend/app/mcp_tools/tools.py#L1-L38)

[^winner-header]: [Winner frontend header and navigation](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/components/Header.tsx#L21-L130)

[^winner-app]: [Winner frontend application shell](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/App.tsx#L50-L620)

[^winner-strategy-ui]: [Winner strategy detail modal](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/components/StrategyDetailModal.tsx#L16-L180)

[^winner-explain-ui]: [Winner explainability modal](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/components/ExplainabilityModal.tsx#L13-L132)

[^winner-council]: [Winner AI Council view](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/components/AICouncilView.tsx#L5-L131)

[^winner-command]: [Winner command center](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/components/CommandCenter.tsx#L20-L118)

[^winner-chart]: [Winner live trading chart](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/components/trading/LiveTradingChart.tsx#L264-L569)

[^winner-css]: [Winner frontend visual tokens and effects](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/frontend/src/index.css#L10-L98)

[^winner-deploy]: [Winner Render deployment blueprint](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/render.yaml#L1-L42)

[^winner-walkthrough]: [Winner implementation walkthrough](https://github.com/SUMANSHAKTI/alpaca/blob/5a56a9de0ccb76297b3195fb1048f0fad46e7fd5/walkthrough.md#L1-L22)

### Options Alpha sources

[^ours-readme]: [Options Alpha README](../README.md)

[^ours-submission]: [Options Alpha submission narrative](options_alpha_submission_narrative_v0_1.md) and [submission checklist](options_alpha_submission_checklist_v0_1.md)

[^ours-read-adapter]: [Options Alpha Alpaca read-only adapter](../src/options_alpha_lab/providers/alpaca_readonly.py)

[^ours-model]: [Options Alpha bounded model provider](../src/options_alpha_lab/providers/openai_thesis.py)

[^ours-models]: [Options Alpha persistence models](../src/options_alpha_lab/persistence/models.py)

[^ours-repository]: [Options Alpha persistence repository](../src/options_alpha_lab/persistence/repository.py)

[^ours-gateway]: [Options Alpha execution gateway](../src/options_alpha_lab/execution/gateway.py)
