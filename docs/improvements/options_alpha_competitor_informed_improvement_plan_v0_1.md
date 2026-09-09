# Options Alpha

## Competitor-Informed Product and Portfolio Improvement Plan (`CIIP-`)

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Date | 9 September 2026 |
| Status | Implementation-ready planning baseline; no trading-authority change |
| Product direction | AI options research lab with a proof-carrying execution firewall |
| Code baseline | `2657a1ee17033b9f61c4008b31285f03f2b9a236` |
| Trading boundary | Alpaca Paper only; maximum one open or pending entry remains binding |
| Plan prefix | `CIIP-` |
| Portfolio dependency | [Multi-Position Task 2 — Portfolio Evidence and Cap Two](../implementation/options_alpha_multi_position_task_2_portfolio_entry_v0_1.md) |

## 1. Executive decision

The competitor reviews agree on one point strongly enough to act on: Options
Alpha did not lose on execution correctness. It lost perceptibility. Alpha
Hunter and TradePilot made an ambitious, running product understandable in the
first few seconds through a front door, named stages, visible activity, charts,
multiple product surfaces, and demo-specific choreography. Options Alpha built
the stronger options, evidence, lifecycle, reconciliation, and test foundation,
but required the viewer to assemble that value from forensic detail.

The next version should therefore do two things in this order:

1. make the existing proof-carrying system immediately legible, interactive,
   and demonstrable without weakening its authority boundary; and
2. extend it into a real research and portfolio-admission product, beginning in
   shadow mode and retaining the one-entry cap until Multi-Position Task 2 has
   earned permission to run a cap-two Paper canary.

The target statement is:

> **Options Alpha is an AI options research lab whose evidence firewall proves
> which strategies are allowed to reach Alpaca Paper—and why.**

This plan does **not** recommend rewriting the execution core, moving financial
authority into the model, adding fake activity or metrics, exposing public
trading controls, or raising the position cap as a presentation shortcut.

## 2. Inputs and synthesis method

This plan consolidates four independent competitor documents:

- [Codex winner analysis](../codex_winner_project_analysis_v0_1.md), findings
  `CWA-001` through `CWA-041`;
- [Codex TradePilot analysis](../codex_second_place_tradepilot_analysis_v0_1.md),
  findings `CTA-001` through `CTA-041`;
- [Claude winner analysis](../implementation/options_alpha_winner_analysis_v0_1.md),
  findings `WA-001` through `WA-018`; and
- [Claude TradePilot analysis](../implementation/options_alpha_runnerup_analysis_v0_1.md),
  findings `RA-001` through `RA-021`.

The current repository—not any analysis—is the source of truth for the
implementation status and sequence. The two analysis pairs sometimes use
different line-count conventions or count demo scenes differently. Those
differences do not affect this plan. Only findings that remain useful after a
direct current-code check are adopted.

No private judge feedback or scorecard is available. The recommendations below
are product and engineering inferences, not claims about an unpublished judging
formula.

## 3. What to take, keep, and reject

### 3.1 Adopt from Alpha Hunter

| Transferable strength | How Options Alpha should use it | Source findings |
|---|---|---|
| A positive, memorable product category | Lead with the AI options research-lab outcome before disclosures | `CWA-001`, `WA` §8.4 |
| One visible end-to-end lifecycle | Show one compact journey, then allow evidence drill-down | `CWA-002`, `CWA-027`, `WA-015` |
| Strategies as named product objects | Add real, versioned candidates and visible rejection/promotion states | `CWA-003`, `CWA-REC-006` |
| Progressive disclosure | Add a plain-language “Why this decision?” layer over the existing records | `CWA-004` |
| Safe interactivity and motion | Replay, compare, perturb, expand, and export recorded evidence | `CWA-005`, `WA-015` |
| Trading-native charts | Add only charts whose inputs and provenance are durable | `CWA-006`, `WA-015` |
| Concise lifecycle vocabulary | Name the stages and repeat the same story across product and pitch | `CWA-032`, `CWA-033`, `WA` §8.4 |

### 3.2 Adopt from TradePilot

| Transferable strength | How Options Alpha should use it | Source findings |
|---|---|---|
| Public product front door | Add a judge-first first viewport and credential-free guided path | `CTA-030`, `RA-018` |
| Dedicated cinematic demonstration | Build a deterministic read-only tour from frozen and observed records | `CTA-032`, `RA-019` |
| One idea repeated through several surfaces | Repeat Observe → Decide → Authorize → Reconcile across the shell, tour, README, and deck | `CTA-031`, `RA-018` |
| Visible running-agent state | Render durable events, lease ownership, reconciliation, and next scheduled work | `CTA-034` |
| Graceful partial failure | Report dependency-specific failure and fall back only to explicitly labeled evidence | `CTA-026` |
| Business-shaped workflows | Show operator, research, policy, incident, and proof-export jobs without inventing tenancy | `CTA-033` |
| Honest negative results | Turn the losing Paper lifecycle and no-effect ablation into a concise trust surface | `CTA-035`, `RA-016` |

### 3.3 Preserve from Options Alpha

- the model remains advisory and cannot choose direction, invalidation, size,
  policy, or broker action;
- option-chain provenance and completed-bar discipline;
- deterministic option selection and risk arithmetic;
- immutable intent, exact prepared request, derived client order ID, and
  ambiguous-submit lookup;
- `SUBMITTED` is never `FILLED`;
- durable position ownership, reconciliation, incidents, and restart recovery;
- one credentialed writer and a credential-free public dashboard;
- explicit `PAPER`, feed, replay, freshness, and no-alpha disclosures; and
- the test, type, lint, migration, secret, and execution-boundary gates.

### 3.4 Explicitly reject

- simulated, random, or hardcoded performance presented as observed;
- unlabeled synthetic market data or optimistic fallback state;
- model-provided risk scores as deterministic risk evidence;
- public or natural-language broker mutation;
- registration or API-key theater over one shared brokerage account;
- client-created trading events that are not in the durable record;
- treating broker acceptance as execution;
- breadth created by unsupported assets or metrics;
- a React rewrite before the existing read-only product has shipped its guided
  evidence journey; and
- multi-position entry before portfolio reservations, admission, fencing, and
  policy approval exist.

## 4. Current-code validation

Validation was performed against the code baseline named above while preserving
the existing dirty documentation worktree.

### 4.1 Reproduced baseline

| Check | Result on 9 September 2026 |
|---|---|
| Test inventory | 481 tests collected |
| Full offline suite | Exit code 0; one visible opt-in live-test skip |
| Ruff | Passed |
| Strict mypy | Passed across 41 source files |
| Dashboard suite | 16 passed |
| Multi-Position Task 1 suite | 18 passed |

These checks validate the local code baseline. They do not prove the current
health or configuration of a remote deployment.

### 4.2 Capability status

| Capability | Status | Current evidence | Planning consequence |
|---|---|---|---|
| Read-only judge surface | Implemented | [`app.py`](../../app.py) declares and tests a broker-free surface; [`test_dashboard.py`](../../tests/test_dashboard.py) rejects gateway/broker references | Preserve the boundary |
| Five evidence views | Implemented | Evidence, memo, lineage, outcome, and guards render as Streamlit tabs | Improve the entry journey rather than recreating all views |
| Visual authority rail | Implemented | `authority_rail()` renders seven stages and fences the model | Reuse it as the tour spine and make stages addressable |
| Labeled evidence fallback | Implemented, narrow | `_resolve_source()` labels committed evidence when the live database is empty or unavailable | Extend the same rule to every component and metric |
| Durable decision and lifecycle records | Implemented | Models exist from snapshots through orders, fills, positions, incidents, observations, exit decisions, and audit events | Build view models and exports on these records |
| Multi-position management | Implemented | `manage_positions()`, stable ordering, contested-symbol handling, and Task 1 tests are green | Treat Task 1 as a retained dependency, not new work |
| One-entry cap | Implemented | [`gateway.py`](../../src/options_alpha_lab/execution/gateway.py) refuses when `open_strategy_count() > 0` | Keep until a reservation-backed admission replaces it |
| Position and order clocks | Implemented | Worker drives independent order and position clocks | Extend health presentation; do not reimplement cadence |
| Strategy/research catalog | Missing | No persistent strategy candidate, evaluation run, or promotion record exists | Required before advertising a research lab |
| Immutable decision outcomes and review jobs | Missing | The architecture has an in-memory `DecisionOutcome` contract, but no `decision_outcomes` or `review_jobs` persistence tables | Required before statistical promotion or Task 2 research claims |
| Portfolio reservation/admission | Missing | No portfolio snapshot, risk reservation, or admission record/migration exists | Task 2 must begin in shadow mode |
| Broker execution identity | Missing | `Fill` has a generated local ID but no Alpaca activity/execution ID | Add before cap two |
| Close ownership claim | Missing | `prepare_close()` changes `OPEN` to `CLOSING` without compare-and-set or a versioned attempt | Add before concurrent cap-two lifecycle work |
| Lease fencing epoch | Missing | `WorkerLease` has owner and TTL but no monotonic epoch checked at every write | Add before cap-two canary |

### 4.3 Current presentation defects to correct first

These are implementation findings, not aesthetic preferences.

#### `CIIP-CV-001` — The global safety strip is hardcoded

`app.py` renders `Paper`, `Order writes: Disabled`, `Operator approval: Required`,
and `Live endpoint: None` as literals even when `DASHBOARD_DATABASE_URL` points
to a worker database. The dashboard cannot claim runtime truth without a
runtime-status record or health artifact tied to an observation time.

**Required disposition:** dynamic values come from a typed, timestamped status
view; unavailable values render `UNKNOWN`, never the safe-looking default.

#### `CIIP-CV-002` — One page can mix unrelated sources

The selected decision may come from the live database, while the realized Paper
receipt and ablation metrics are always loaded from committed JSON files. This
can make a historical result look like the outcome of the selected live
decision.

**Required disposition:** a view model may combine artifacts only when their
durable correlation IDs and provenance explicitly match. Otherwise render them
as separate, labeled evidence cards.

#### `CIIP-CV-003` — Outcome orders are not scoped to the selected decision

The Outcome tab queries all `BrokerOrder` rows. This happens to look coherent in
the small demo database, but becomes false as soon as several lifecycles or Task
2 shadow/canary evidence exists.

**Required disposition:** traverse
`Decision → OrderIntent → BrokerOrder → Fill → Position`, and test that selecting
one decision cannot display another decision's order or fill.

#### `CIIP-CV-004` — The simulated halt-state selector needs a stronger label

The Guards tab allows a viewer to select a state to read its semantics. It does
not change durable state, which is correct, but it can be mistaken for an
operator control.

**Required disposition:** label it `POLICY SIMULATOR · NO STATE CHANGE` and keep
it visually distinct from observed status.

#### `CIIP-CV-005` — Documentation describes several obsolete baselines

The README still contains an early “Deliberately out of scope” section saying
order submission, autonomous execution, and a production UI are absent, while
later sections describe deployed execution and the dashboard. The frontend
design names FastAPI/Jinja/HTMX and says templates and dashboard tests are not
implemented, while the current product is a 754-line Streamlit application with
16 tests. The Task 1 document header also predates the deployment disposition
recorded by Task 2 and the traceability matrix.

**Required disposition:** create one dated current-build statement and label
older sections as historical design decisions rather than current facts.

## 5. Target product experience

The public product remains credential-free and read-only. Its default journey is
designed for a reviewer who knows nothing about the repository.

```text
FIRST VIEWPORT
  AI options research lab + three verified proof tiles
                         |
                         v
90-SECOND GUIDED REPLAY: OBSERVE -> DECIDE -> AUTHORIZE -> RECONCILE
      |                       |                       |
      v                       v                       v
Why this decision?     Why was it refused?     What did Alpaca do?
      |                       |                       |
      +-----------------------+-----------------------+
                              |
                              v
         hashes, source records, policy versions, and proof export
```

### 5.1 First viewport

Show, without scrolling:

- **Outcome:** “AI options research, with execution authority kept in code.”
- **Proof 1:** the number of observed Paper MLeg lifecycles in the selected
  evidence set, derived from correlated records rather than a literal;
- **Proof 2:** the model/no-model result and sample size, read from the versioned
  ablation artifact;
- **Proof 3:** one authorized broker-write boundary, proven by the existing
  static execution-boundary test;
- source mode and timestamp: `OBSERVED PAPER`, `LIVE READ`, `FROZEN REPLAY`, or
  `DERIVED`; and
- `Start guided tour` plus `Inspect evidence` actions.

The four required disclosures remain visible but follow the positive product
promise instead of preceding it.

### 5.2 Guided tour

Use six deterministic scenes:

1. the product promise and authority split;
2. a qualified bullish or bearish options candidate;
3. bounded model review with citations and counter-evidence;
4. deterministic risk, immutable intent, exact MLeg request, and derived client
   order ID;
5. Alpaca acknowledgement, fills, close, reconciliation, and flat state; and
6. a refusal or ambiguity/restart case proving that safety also produces visible
   outcomes.

The tour may animate pacing and move between views, but every value must come
from a versioned fixture or correlated observed record. It must pause, skip,
restart, respect reduced motion, and clearly say `FROZEN REPLAY` when applicable.

### 5.3 Safe interactions

Implement these before considering any public mutation:

- select a recorded case;
- play or step through its event sequence;
- expand “Why this decision?”;
- compare deterministic and bounded-model paths on the same snapshot;
- perturb a threshold in a client/session-local simulation with no persistence
  or execution authority;
- inspect a portfolio-capacity refusal;
- copy stable record IDs and hashes; and
- download a redacted proof package.

### 5.4 Evidence-backed visualizations

Add only the following initial charts:

- completed daily bars with the forming bar excluded and the decision point
  identified;
- option-spread entry/exit lifecycle with limit, fill, and source timestamps;
- confirmed versus reserved portfolio risk against the applicable limit;
- strategy-candidate funnel by durable lifecycle state; and
- decisions/refusals by reason code and evidence mode.

Every chart must have a tabular alternative, source badge, observed range,
sample size, and empty/error state. Do not add Sharpe, win rate, cumulative P&L,
or strategy ranking until stored observations and evaluation methods support
them.

## 6. Delivery sequence

Only the product-truth correction and presentation work may proceed
independently. Research promotion depends on outcome capture; cap-two admission
depends on shadow evidence and execution hardening.

```text
CIIP-0 Current truth
      |
      +--> CIIP-1 Judge experience --> CIIP-2 Proof/read model
      |
      +--> CIIP-3 Outcomes + research catalog
                                |
                                v
                    CIIP-4 Task 2 shadow evidence
                                |
                                v
                 CIIP-5 Reservation + hardening
                                |
                                v
                     CIIP-6 cap-two Paper canary
```

## 7. Work packages

### `CIIP-0` — Establish one truthful baseline

**Priority:** P0 · **Effort:** 1–2 engineer-days · **Authority change:** none

Work:

1. Correct `README.md`, the frontend design, Task 1 status, implementation index,
   and traceability notes against the current code and a separately verified
   deployment status.
2. Define a compact vocabulary for `LIVE READ`, `OBSERVED PAPER`, `FROZEN
   REPLAY`, `DERIVED`, `SIMULATION`, `STALE`, and `UNKNOWN`.
3. Add a typed `SystemStatusView` contract with value, source, observed time,
   age, and reason for unavailability.
4. Remove hardcoded operational claims from the dashboard shell.
5. Scope orders, fills, positions, receipts, and ablations to their real
   correlation IDs.
6. Label the halt-state selector as simulation.

Acceptance:

- no screen can mix a live selected decision with an unrelated committed result;
- a missing worker-status source renders `UNKNOWN`, not `Disabled`, `Healthy`, or
  `Paper verified`;
- every selected-decision view is isolated by lineage;
- current documentation has one non-contradictory capability statement; and
- all existing 481 tests, lint, and typing remain green.

### `CIIP-1` — Ship the judge-first experience on the current stack

**Priority:** P0 · **Effort:** 4–7 engineer-days · **Authority change:** none

Work:

1. Add the first viewport, three derived proof tiles, and positive product copy.
2. Turn the existing authority rail into the shared spine for the six-scene
   guided replay.
3. Add stable query parameters for case, view, and tour step so the README and
   deck can link to exact evidence.
4. Add a compact “Why this decision?” drawer before raw lineage detail.
5. Add the completed-bar and order-lifecycle charts with tabular alternatives.
6. Present the losing Paper lifecycle and no-effect ablation as a visible trust
   card with sample sizes and limitations.
7. Add project/team ownership roles only from verified contributor information;
   one person may hold several roles.
8. Verify 360, 736, 1024, and 1440-pixel layouts, keyboard order, reduced motion,
   readable focus, and non-color status meaning.

Stack decision:

> Keep Streamlit for `CIIP-1`. The current application and its 16-test suite are
> already a working asset. A React/Vite rewrite is not a prerequisite for a
> landing experience, guided replay, real charts, or deep-linked state.

Evaluate a thin React shell only after `CIIP-2` creates stable read-only view
models. Approve it only if measured Streamlit limitations block responsive
navigation, deterministic tour playback, accessibility, or load time. A React
client would consume a read-only API and would never import credentials or a
broker-capable component.

Acceptance:

- an unfamiliar reviewer can state the product, the model boundary, and the
  outcome of the selected case after the guided path;
- the tour completes in 90 seconds without provider or broker access;
- Back/Forward and shared URLs restore the same case and view;
- every animated number maps to a durable ID or versioned artifact;
- no public element resembles an order submission control; and
- dashboard render/boundary tests remain green with new responsive and source-
  truth cases.

### `CIIP-2` — Extract read models, durable activity, and proof export

**Priority:** P1 · **Effort:** 3–5 engineer-days · **Authority change:** none

The 754-line `app.py` currently owns styling, source selection, database queries,
view composition, and most presentation logic. Before adding product breadth,
move database interpretation into typed read models.

Add:

- `presentation/status.py` for system/dependency status;
- `presentation/decision.py` for selected-decision lineage;
- `presentation/portfolio.py` for aggregate risk and position summaries;
- `presentation/activity.py` for durable audit, reconcile, incident, and worker
  events; and
- `presentation/export.py` for a redacted, deterministic proof manifest.

The precise module names may change; the boundaries may not.

Rules:

- the dashboard renders view models, not provider payloads or ad hoc cross-table
  queries;
- every field carries provenance or is explicitly derived;
- activity is server/durable-record derived, never synthesized in the browser;
- dependency health is separate for database, worker lease, last reconcile,
  Alpaca read path, model path, and artifact fallback;
- proof export includes snapshot, evidence, memo or `NOT_CALLED`, risk decision,
  intent, request hash, broker order, fills, position, exit, incidents, and
  disclosure manifest; and
- secrets, authorization headers, full account IDs, raw hidden reasoning, and
  confidential payloads are excluded by schema, not post-hoc string masking.

Acceptance:

- selected-decision isolation is tested with at least two complete lifecycles;
- identical records produce byte-identical export manifests;
- redaction tests fail on seeded secret/account patterns;
- an unavailable dependency cannot be rendered as healthy; and
- the static no-write-path gate covers the extracted presentation package.

### `CIIP-3` — Build the real research catalog and outcome layer

**Priority:** P1 · **Effort:** 6–10 engineer-days plus evidence time ·
**Authority change:** none; all candidates remain no-write until separately approved

This work implements the still-missing portions of the existing
[Strategy Improvement Plan](../implementation/options_alpha_strategy_improvement_implementation_plan_v0_1.md)
and converts the competitors' useful strategy-lifecycle vocabulary into real
records.

Add append-oriented entities for:

- `strategy_candidates`: name, hypothesis, setup family, permitted instruments,
  parameter-set hash, proposer, created version, and state;
- `evaluation_runs`: frozen dataset manifest, folds, costs, stress, parameter
  perturbations, regime slices, code version, outputs, and uncertainty;
- `decision_outcomes`: declared horizon, MFE, MAE, actual Paper result, stressed
  result, execution/exit quality, and attribution;
- `review_jobs`: horizon, deterministic idempotency key, status, attempts, and
  completion evidence;
- `promotion_decisions`: evidence for and against, owner decisions, active
  policy version, rollback target, and disposition; and
- `policy_versions`: immutable thresholds, scope, approval state, effective
  time, and predecessor.

Use this honest lifecycle:

```text
PROPOSED -> TESTING -> CHALLENGED -> ELIGIBLE -> PAPER_SHADOW
    |           |            |            |
    +-------> REJECTED <------+------------+
                                      |
                                      +-> PAPER_ACTIVE -> PAUSED -> RETIRED
```

The model may propose hypotheses, extract counter-evidence, generate failure
scenarios, or summarize a rejection under strict schemas. Deterministic code
calculates metrics, validates samples, promotes versions, sizes risk, and creates
execution authority.

Acceptance:

- a rejected candidate is as inspectable as an eligible one;
- every metric reproduces from a frozen dataset and versioned evaluator;
- a candidate cannot reach the gateway by changing its state alone;
- outcome enrichment is append-only and cannot edit the original decision;
- `NO_TRADE` decisions use the same declared outcome horizons as trades; and
- no Edge Score or ranking is displayed until its formula, sample gate,
  uncertainty, and calibration are approved.

### `CIIP-4` — Multi-Position Task 2A: shadow capacity and portfolio evidence

**Priority:** P1, after `CIIP-3` outcome contracts exist · **Effort:** 3–5
engineer-days plus at least six trading weeks of evidence · **Authority change:**
none; cap remains one

The existing [Task 2](../implementation/options_alpha_multi_position_task_2_portfolio_entry_v0_1.md)
remains the normative starting point, with the amendments in Section 8 of this
plan.

When a current position occupies the slot, continue the complete candidate path
without preparing an order and persist:

- disposition `CAPACITY_BLOCKED`;
- stable completed-session cohort identity;
- candidate, contracts, expiry, approved maximum loss, feed, and policy versions;
- existing position IDs, direction, contract overlap, cluster, confirmed risk,
  and pending risk;
- every admission check and exact refusal reason;
- one- and three-session counterfactual outcomes; and
- whether the candidate was distinct, duplicate, overlapping, unfinanceable, or
  blocked only by count.

Productize this evidence immediately in read-only form. A judge can see a second
candidate earn a correct refusal before cap two exists. That creates the
competitors' perceived breadth without manufacturing execution breadth.

Acceptance:

- repeated 15-minute observations of one completed-session state create one
  cohort, not independent opportunities;
- no shadow object can construct an `ApprovedOrderIntent` or reach the gateway;
- the dashboard explains the capacity refusal and incremental risk from durable
  data;
- blocked outcomes enrich idempotently at both horizons; and
- the research report can distinguish “count-only blocked” from duplicate,
  overlap, data, policy, and affordability refusals.

### `CIIP-5` — Multi-Position Task 2B/2C: atomic admission and execution hardening

**Priority:** P2 · **Effort:** 9–16 engineer-days within Task 2's existing
12–21 day range · **Authority change:** schema and shadow governor first; cap
one remains the default

Add these durable records or equivalent contracts:

| Record | Minimum responsibility |
|---|---|
| `portfolio_snapshots` | Account/portfolio key, observed broker/account time, confirmed positions, working orders, confirmed risk, pending risk, marked loss, data quality, and hash |
| `risk_reservations` | Candidate/intent, cohort, cluster, state, approved maximum loss, confirmed exposure, policy version, reconciliation/release times |
| `portfolio_admissions` | Exact checks, totals before/after, decision, reason codes, approver/policy reference, and snapshot hash |
| `close_attempts` | Position, durable attempt number, claim/version, client order ID, state, owner, and timestamps |
| extended `fills` | Alpaca execution/activity identity when available, with an explicit fallback identity policy |
| fenced `worker_leases` | Monotonic epoch returned on acquisition and checked before lifecycle mutation and broker write |

#### Atomic entry protocol

```text
database transaction
  lock account/portfolio admission row
  verify fresh portfolio snapshot and policy version
  apply count, pending, total, cluster, daily-loss, cohort, and overlap gates
  reserve the approved maximum loss
  persist admission + intent + exact request + PENDING position
commit

verify current lease epoch + Paper endpoint + unchanged intent/reservation
submit once through the existing gateway
record response
reconcile immediately and retain reservation until terminal broker truth
```

Do not hold a database lock across the broker network call. Do not release a
reservation on `accepted`, timeout, local cancel request, or process restart.

The gateway must require an immutable approved portfolio-admission/reservation
reference for risk-increasing entries. Risk-reducing closes remain exempt from
entry capacity but still require valid position ownership, a close-attempt claim,
Paper endpoint proof, and current lease fencing.

Policy gates remain those in Task 2:

- maximum two `OPEN` strategies only after promotion;
- maximum one `PENDING` entry;
- unique completed-session cohort;
- unique option symbols across strategies;
- additive SPY cluster with no offset credit;
- no opposing-direction SPY strategies;
- no entry while any position is `CLOSING` or `INCIDENT`;
- deterministic total, cluster, daily-loss, and count limits; and
- cap one as the default and rollback target.

Acceptance:

- all original `T2-AC-01` through `T2-AC-13` pass;
- two concurrent admissions on PostgreSQL cannot oversubscribe count or risk;
- a stale worker cannot mutate lifecycle state or submit after lease takeover;
- two genuine same-symbol/same-price fills remain distinct by broker execution
  identity;
- exactly one close attempt owns an `OPEN → CLOSING` transition;
- partial fills conservatively retain confirmed plus unfilled reserved risk;
- restart reconstructs portfolio risk exactly; and
- cap reduction blocks new entries without abandoning existing management.

### `CIIP-6` — Multi-Position Task 2D/2E: operational surface and cap-two canary

**Priority:** P2, only after policy and research approval · **Effort:** 2–4
engineer-days plus canary/evidence calendar · **Authority change:** reversible
Paper cap two

Add a portfolio view showing:

- confirmed, pending-reserved, and unknown/conservative risk;
- total and SPY-cluster limits with policy version;
- daily realized plus conservative marked loss;
- each position's lifecycle, mark age, reconciliation age, next deadline,
  reservation, close attempt, incident, and lineage;
- capacity-blocked cohorts and reasons;
- cap-one/cap-two mode with its approval and rollback evidence; and
- alerts for unreserved, unmanaged, unvalued, overlapping, or unfenced exposure.

Use the Task 2 research gate without weakening it: at least 30 distinct blocked
cohorts across at least two declared regimes, material capacity blocking,
positive incremental return-per-defined-risk-day under the same aggregate risk
budget, a positive block-bootstrap lower bound, drawdown/expected-shortfall
tolerances, and conservative execution stress. If the evidence is insufficient,
the valid result is `CAP_ONE_RETAINED`.

After recorded Trading, Risk, QA, and Product approval, run the existing
maximum-two Paper canary for at least 20 overlapping-position lifecycle episodes.
Any duplicate, risk oversubscription, unowned leg, stale-worker write,
unreconciled reservation, deadline breach, or restart failure returns the system
to cap one immediately. Reducing the cap does not force-close existing exposure.

## 8. Required amendments to Multi-Position Task 2

Before Task 2 implementation begins, revise its document to v0.2 with these
changes. This plan records the changes now so the pending work benefits from the
competitor review without silently rewriting its original baseline.

| Amendment | Existing design retained | New finding incorporated |
|---|---|---|
| `CIIP-T2-01` Productize shadow refusals | Keep `CAPACITY_BLOCKED` and stable cohorts | Use refused second candidates as a judge-visible demonstration of portfolio intelligence |
| `CIIP-T2-02` Share the research catalog | Keep one/three-session outcomes | Link cohorts to real strategy candidates, evaluation runs, policy versions, and promotion decisions from `CIIP-3` |
| `CIIP-T2-03` Add a portfolio snapshot hash | Keep fresh account/portfolio checks | Make the admission decision reproducible and exportable through the same proof chain as an order |
| `CIIP-T2-04` Extend the authority rail | Keep immutable portfolio approval | Display `Portfolio admission` between deterministic risk and order intent when multi-entry evidence is selected |
| `CIIP-T2-05` Separate live and demo states | Keep the read-only dashboard | Guided cap-two scenes must be labeled shadow, frozen replay, or observed Paper and may never imply live authority |
| `CIIP-T2-06` Fix selected-position isolation first | Keep `T2-AC-13` | Correct the current global order query before multiple lifecycle records are shown |
| `CIIP-T2-07` Make reservations the gateway authority | Keep atomic admission | The gateway must accept a durable reservation/admission reference, not infer capacity from broker leg/order counts |
| `CIIP-T2-08` Add close-attempt identity | Keep close ownership requirement | Make attempts visible, exportable, retry-safe, and testable rather than only a position state mutation |
| `CIIP-T2-09` Add external fill identity | Keep exact fill persistence | Replace tuple-only deduplication when Alpaca provides an activity/execution identifier |
| `CIIP-T2-10` Fence every mutation | Keep one writer and lease heartbeat | Add monotonic epoch checks before both local lifecycle mutation and broker submission |
| `CIIP-T2-11` Do not add tenancy | Keep account/portfolio key | Be honest about one operator/account until accounts, records, policies, secrets, and workers can be isolated end to end |
| `CIIP-T2-12` Add proof export | Keep portfolio operational data | Include portfolio snapshot, admission, reservation transitions, fill identity, close attempts, and rollback state |

Task 2's original economic promotion thresholds, cap-two canary, overlapping-
symbol prohibition, no-offset rule, incident treatment, and cap-one rollback all
remain binding.

## 9. Prioritized implementation backlog

| Order | ID | Deliverable | Depends on | Done when |
|---:|---|---|---|---|
| 1 | `CIIP-001` | Correct dashboard source/lineage truth defects | None | `CIIP-CV-001` through `004` have regression tests |
| 2 | `CIIP-002` | Reconcile current-build documentation | Deployment status check | One dated baseline replaces contradictory current claims |
| 3 | `CIIP-003` | First viewport and derived proof tiles | `CIIP-001` | No operational tile is a literal masquerading as observed state |
| 4 | `CIIP-004` | Six-scene guided evidence replay | `CIIP-003` | 90-second offline replay, shareable step URLs, reduced-motion path |
| 5 | `CIIP-005` | Why-decision summary and two honest charts | `CIIP-001` | Summary/chart values resolve to selected lineage and provenance |
| 6 | `CIIP-006` | Typed read models and durable activity | `CIIP-001` | `app.py` no longer owns cross-table interpretation |
| 7 | `CIIP-007` | Redacted deterministic proof export | `CIIP-006` | Byte-stable manifest and redaction tests pass |
| 8 | `CIIP-008` | Outcomes, review jobs, and policy versions | `CIIP-0` | Trade and refusal outcomes enrich idempotently |
| 9 | `CIIP-009` | Strategy candidate/evaluation/promotion catalog | `CIIP-008` | Rejected and eligible candidates reproduce from frozen inputs |
| 10 | `CIIP-010` | Shadow capacity cohorts | `CIIP-008`, `CIIP-009` | Count-only blocks and their outcomes are queryable; cap stays one |
| 11 | `CIIP-011` | Portfolio snapshots, admissions, reservations | `CIIP-010` | PostgreSQL concurrency tests prevent oversubscription |
| 12 | `CIIP-012` | Close claims, fill IDs, lease fencing | `CIIP-011` | Race/restart/takeover matrix passes |
| 13 | `CIIP-013` | Portfolio operational view and export | `CIIP-011`, `CIIP-012` | Every exposure has risk, source, lineage, freshness, and ownership state |
| 14 | `CIIP-014` | Research disposition for cap two | Evidence horizon | Approved `CAP_TWO_CANARY` or retained `CAP_ONE_RETAINED` |
| 15 | `CIIP-015` | Reversible cap-two Paper canary | `CIIP-014` | 20 qualifying episodes with zero integrity failure |

The recommended first implementation slice is `CIIP-001` through `CIIP-005`.
It produces the largest visible improvement without changing trading authority
or waiting for market evidence.

## 10. Test and release strategy

### 10.1 Tests to add before implementation

| Area | Required tests |
|---|---|
| Source truth | Missing status is `UNKNOWN`; live and committed artifacts cannot merge without correlation; all derived fields expose provenance |
| Selected lineage | Two decisions with two lifecycles never show one another's orders, fills, positions, receipts, or events |
| Guided tour | Every step renders offline; URLs restore state; pause/skip/restart work; reduced-motion mode contains no automatic animation |
| Dashboard boundary | Presentation modules contain no gateway, broker client, submit, cancel, replace, or close capability |
| Proof export | Deterministic bytes, schema validation, correlation completeness, secret/account redaction, and explicit missing-field states |
| Outcomes | Idempotent horizons, no future leakage, immutable original decisions, equivalent trade/refusal treatment |
| Research promotion | No candidate or model output can self-promote or construct execution authority |
| Cohorts | Intraday rescans deduplicate; new completed-session evidence creates a new cohort; re-entry stays prohibited |
| Reservations | Atomic count/risk admission, partial-fill accounting, incident retention, terminal release, restart reconstruction |
| Close ownership | One claimant, deterministic retry identity, later attempt gets a new durable ID, accepted is not flat |
| Fill identity | Two genuine identical-price executions persist separately; replay is idempotent |
| Fencing | Expired owner fails before local mutation and before broker write after takeover |
| Rollback | Cap two to one manages existing positions and blocks additional entry |

PostgreSQL is mandatory for concurrency, row-locking, and fencing acceptance.
SQLite remains useful for fast offline tests but cannot establish those claims.

### 10.2 Existing gates retained

Every increment must pass:

```bash
uv run ruff check .
uv run mypy
uv run pytest -q
uv run python scripts/check_no_write_path.py src
uv run python -m options_alpha_lab.replay --database-url sqlite+pysqlite:///:memory:
```

Release candidates also run `bash scripts/run_h0_validation.sh`, migration
upgrade/downgrade rehearsal, the Task 1 and Task 2 acceptance suites on the
production PostgreSQL point release, secret scanning, dependency audit, and a
clean-session dashboard walkthrough.

### 10.3 Presentation release gate

Before publishing a demo:

- the public URL opens without credentials;
- the frozen path works when database, Alpaca, and OpenAI are unavailable;
- fallback mode is visible in the first viewport;
- every tour scene has a source and correlation manifest;
- no button or API route can express a broker write;
- the current deployment mode is not inferred from committed evidence;
- the mobile and keyboard paths complete;
- all team, metric, and business claims have an attributable source; and
- README, deck, video, and application use the same four-stage language.

## 11. Effort and sequencing

| Workstream | Directional engineering effort | Calendar dependency |
|---|---:|---|
| `CIIP-0` Truth baseline | 1–2 days | Deployment status must be checked separately |
| `CIIP-1` Judge experience | 4–7 days | None; use committed evidence |
| `CIIP-2` Read models/export | 3–5 days | None |
| `CIIP-3` Outcomes/research catalog | 6–10 days | Outcome observations accumulate over time |
| `CIIP-4` Task 2 shadow evidence | 3–5 days | Minimum six trading weeks; likely several months |
| `CIIP-5` Task 2 admission/hardening | 9–16 days | Trading/Risk policies and PostgreSQL tests |
| `CIIP-6` Surface/canary | 2–4 days | Research approval plus at least 20 canary episodes |

Total directional engineering effort is **28–49 engineer-days**, plus the
evidence calendar. Within that total, the original Task 2 estimate of 12–21 days
is retained; the additional work is the presentation, read-model, outcome, and
research-product layer learned from the competitor reviews.

Parallel work is safe only across boundaries:

- product design can proceed alongside `CIIP-0`, using committed records;
- view-model extraction can proceed alongside visual component work after the
  source/correlation contract is frozen;
- research schema and UI can proceed together after outcome contracts freeze;
- reservation, fencing, and close-claim work should share one lifecycle owner;
  and
- nobody changes the cap while shadow evidence or policy approval is pending.

## 12. Risk register

| Risk | Consequence | Mitigation / stop condition |
|---|---|---|
| Presentation begins to outrun truth | Options Alpha adopts the competitors' weakest habit | Schema-backed view models, provenance contract, selected-lineage tests |
| Streamlit expansion becomes monolithic | New UI becomes expensive to verify | Extract read models/components before product breadth; apply the React decision gate later |
| Research language precedes real evaluation | “Strategy lab” becomes theater | No score/ranking without stored run, formula, sample, and uncertainty |
| Cap two becomes a demo deadline | Aggregate risk can be oversubscribed | Cap-one default hardcoded until recorded gate; rollback test required |
| Sparse capacity evidence | False claim that a second slot improves results | Pre-register cohorts and thresholds; permit `CAP_ONE_RETAINED` |
| Netted option positions obscure ownership | Wrong lot can be closed or abandoned | Reject new symbol overlap; preserve Task 1 contested-symbol recovery |
| DB transaction spans broker latency | Locks and failure ambiguity compound | Commit reservation/intention before the external call, then reconcile |
| Stale worker continues after takeover | Duplicate or conflicting mutation | Monotonic fencing epoch checked at both mutation boundaries |
| UI claims a mode from old artifacts | Judge sees a safe state that is not current | Observed-time/status source required; otherwise `UNKNOWN` |
| Faux multi-tenancy enters scope | Users share authority over one account | Remain explicit single-account/single-operator until true isolation is funded |

## 13. Decisions requiring human ownership

Engineering can implement the measurement and enforcement machinery, but it
cannot approve trading policy. Before `CIIP-5` leaves shadow mode, named Trading
and Risk owners must decide and record:

- total defined-risk limit;
- SPY cluster limit;
- daily realized-plus-marked loss limit;
- maximum open and pending counts;
- re-entry and same-cohort policy;
- cap-two drawdown and expected-shortfall tolerances;
- minimum liquidity and quote-quality policy;
- exit thresholds still open under `DEC-008`;
- the 0.75% per-trade budget and delta-band pairing still open under `DEC-010`;
  and
- canary duration, rollback triggers, and authority owners.

Until those decisions exist, the dashboard may display proposed values only as
`PROVISIONAL · NOT ACTIVE`.

## 14. Definition of done

This plan is complete only when all of the following are true:

1. the product promise, guided replay, and progressive explanation make the
   existing lifecycle understandable without repository knowledge;
2. every visible value is observed, derived, simulated, or unavailable—and says
   which;
3. a public viewer can interact with evidence but cannot create trading
   authority;
4. strategy candidates, evaluations, rejections, and promotions are genuine,
   versioned research objects;
5. trade and `NO_TRADE` outcomes are enriched without future leakage or mutation
   of their original decisions;
6. Task 2 shadow evidence can determine whether capacity is actually binding;
7. portfolio risk is admitted and reserved atomically from fresh, hashed state;
8. close ownership, fill identity, and lease fencing survive concurrency,
   ambiguity, and restart;
9. cap two is either rejected with an honest evidence record or enabled only as
   a reversible Paper canary after every gate passes;
10. cap one remains the tested default and rollback target;
11. existing execution-firewall invariants and all quality gates remain green;
    and
12. no Paper result, model output, animation, or ranking is presented as
    established alpha.

## 15. Final priority call

Do not begin with a frontend rewrite or a second position. Begin by correcting
the current dashboard's truth and lineage defects, then make its existing proof
path cinematic, addressable, and exportable. In parallel, finish the outcome and
research records that let strategy breadth be real.

Only then should Multi-Position Task 2 progress from shadow evidence to a
reservation-backed portfolio governor and a cap-two Paper canary.

That order takes the competitors' best lesson—make ambition visible—without
importing their weakest one: making the interface look more certain than the
system underneath it.

## 16. Independent validation record — 9 September 2026

An independent pass re-ran every reproducible claim in this plan against the
named baseline and spot-checked each technical finding in the code. Recorded
here so the plan carries its own verification rather than asserting it.

### 16.1 Reproduced

| Claim | Result |
|---|---|
| Baseline `2657a1ee…` | Matches `HEAD` exactly |
| Test inventory 481 | 480 passed, 1 skipped, 167 subtests — the skip is the opt-in live test |
| Ruff | `All checks passed!` |
| Strict mypy, 41 source files | `Success: no issues found in 41 source files` |
| Dashboard suite 16 | 16 passed, 7 subtests |
| Task 1 suite 18 | 18 passed |
| `app.py` 754 lines | 754 |
| Referenced analyses | All four exist; `CWA` 41, `CTA` 41, `WA` 18, `RA` 21 — counts exact |
| Internal links | 10 of 10 resolve |
| Effort total 28–49 days | Package ranges sum to exactly 28–49 |
| Task 2 estimate 12–21 days, `T2-AC-01`–`13` | Both confirmed in the source document |
| Gate `check_no_write_path.py` | `no broker write path in src/`, exit 0 |
| Gate `replay` | `3 snapshot(s) replayed and persisted; no broker write path exists`, exit 0 |

Presentation defects confirmed in code: `CIIP-CV-001` at `app.py:295-299`
(literal status tuples); `CIIP-CV-003` at `app.py:594` (`rows(select(BrokerOrder))`,
unscoped); `CIIP-CV-005` at `README.md:80-86` (still lists Alpaca order
submission and autonomous execution as out of scope for a system that does
both). All ten records named `Missing` in §4.2 have zero occurrences in
`persistence/models.py`; `Fill` carries no Alpaca execution identity;
`WorkerLease` has no epoch column; `prepare_close` assigns `CLOSING` after a
plain `session.get` with no compare-and-set.

### 16.2 Corrected

`WA-008` was cited twice in §3.1 to support "a positive, memorable product
category" and "concise lifecycle vocabulary". `WA-008` is *"A ten-table schema
that is never written to"* and supports neither. Both citations now point to
`WA` §8.4, the unnumbered prose finding about named product concepts, which is
the material actually being drawn on. No other citation in this plan
mis-resolves.

### 16.3 Open findings against this plan

#### `CIIP-VAL-001` — The plan assumes infrastructure that no longer exists

On 9 September 2026, after this plan was written, the deployment was retired:
`options-alpha-worker` and its 40 GB disk were **released**, `options-alpha-demo`
was stopped, `http://47.236.50.157` returns nothing, and the live evidence
database — 209 decisions and 1,155 position observations — was destroyed with no
snapshot.

`CIIP-0` acceptance requires "a separately verified deployment status" and
`CIIP-4` requires "at least six trading weeks of evidence". Neither is reachable
until a worker, database and deployment exist again. That rebuild appears
nowhere in the §9 backlog or the §11 estimate.

**Required disposition:** add an infrastructure work package before `CIIP-4`,
and treat the evidence calendar as starting from redeployment, not from today.

**Disposition taken 9 September 2026:** written up as
[Infrastructure Redesign and Retention Standard](options_alpha_infrastructure_redesign_v0_1.md)
(`CIIP-I-`), which restores a single consolidated host on the retained Elastic
IP, moves archival off-host to OSS, and introduces the evidence/telemetry
retention split.

#### `CIIP-VAL-002` — `CIIP-2` acceptance is not satisfiable from committed evidence

`CIIP-2` requires selected-decision isolation "tested with at least two complete
lifecycles". `demo/h0_demo.db` contains exactly one: a single `CLOSED` position
with one entry and one close order.

**Required disposition:** either build a second lifecycle as a versioned fixture,
or defer that acceptance criterion until redeployment produces a second observed
lifecycle. Do not weaken the criterion to one lifecycle — isolation is untestable
against a single record.
