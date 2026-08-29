# Options Alpha

## Strategy Improvement and Runtime Cadence Implementation Plan

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Date | 29 August 2026 |
| Status | Approved planning baseline for the next implementation session |
| Primary objective | Turn trading observations into reproducible, governed strategy evidence without online self-modification |
| Trading environment | Alpaca Paper only |
| Governing timezone | `America/New_York`, using the authoritative exchange calendar |
| Related architecture | [Architecture Slice](./options_alpha_architecture_slice_v0_1.md) |
| Related bot plan | [Bot Implementation Plan](./options_alpha_bot_implementation_plan_v0_1.md) |
| Related lifecycle review | [Exit Policy and Position-Lifecycle Review](./options_alpha_exit_policy_review_v0_1.md) |

## 1. Decision and boundaries

The project will not implement an online learner that changes thresholds, prompts,
risk limits, entry rules, or exit rules during a trading session. Runtime code may
capture observations, calculate deterministic diagnostics, raise incidents, and
propose research hypotheses. Active policy changes require offline evaluation,
explicit approval, a versioned promotion record, and a rollback target.

The system will use different clocks for different responsibilities:

- the **strategy clock** follows the completed daily signal horizon;
- the **position clock** monitors a multi-session position at a moderate cadence;
- the **order clock** follows pending broker mutations fast enough to enforce their
  deadlines;
- the **review clock** enriches outcomes only after their declared horizons and
  performs learning work offline.

### 1.1 Non-goals

- No live-money execution path.
- No autonomous policy, prompt, or code mutation.
- No threshold change based on one trade or one recent losing streak.
- No requirement to introduce market-data streaming before polling is shown to be
  insufficient for the declared strategy horizon.
- No claim that Paper P&L or indicative quotes establish a live trading edge.
- No enabling of deployed `paper_execute` authority during the first implementation
  increment.

## 2. Current baseline

### 2.1 Implemented facts

The current code contains:

- REST observation of account, market clock, completed daily bars, and option-chain
  snapshots;
- deterministic setup, spread, risk, and exit evaluation;
- immutable decision snapshots, signals, theses, spread candidates, risk decisions,
  hashes, and workflow transitions;
- durable order intents, exact prepared requests, broker orders, per-leg fills,
  positions, and incidents;
- pre-submit persistence, actual-fill entry basis, startup and periodic
  reconciliation, post-submit deadlines, calendar-derived entry gating, and a
  database worker lease;
- a credentialed worker that the deployment runbook reports is running in
  `recommend` mode with order writes disabled;
- a read-only operational report for decisions, refusals, model calls, orders,
  fills, positions, and open incidents.

### 2.2 Capability gaps

The current system does not durably capture:

- position marks and option quotes used on every management tick;
- exit decisions and the exact observation that caused them;
- immutable post-decision outcomes;
- realized and stressed P&L, MFE, MAE, and exit efficiency;
- fixed-horizon results for `NO_TRADE` decisions;
- deterministic attribution across signal, option selection, execution, exit, data,
  and external causes;
- recommendations, evaluation runs, policy versions, promotions, shadow results, or
  rollback events.

The current runtime is polling, not event-driven real time. Its default five-minute
tick is too slow to enforce 90-second entry and 120-second close deadlines.

The underlying price used by the strategy is the last completed daily close, so
the structural invalidation is intentionally a completed-session rule rather than
an intraday trigger. **Corrected 29 August 2026:** that was true by consequence
rather than by enforcement. `parse_bars` dropped the forming bar only when the
clock reported the market open, and a clock payload without a usable `is_open`
fell through `bool(None)` to "closed", which silently promoted a partial session
to a completed close. Nothing downstream could tell the difference, because the
snapshot did not record what its price was. The snapshot now states its price
source, an unreadable clock is a provider error, and the exit policy refuses to
judge a completed-session rule against a price it cannot match. See `EV-023`.

### 2.3 Known engineering findings to resolve

Status as of 29 August 2026. Findings 1 to 8 are closed under `EV-023` and
`EV-024`; finding 4 turned out to be a crash rather than a data-fidelity issue.
Finding 9 is documentation work and remains open.

1. **Closed.** Separate order-deadline enforcement from the five-minute strategy
   loop. `TradingAgent.order_clock` reconciles and enforces deadlines on a
   five-second cadence, driven from the worker's wait loop alongside the lease
   heartbeat. It decides whether to contact the broker from a local read, and
   stands down ten minutes after a submission - an order still working past
   every declared deadline has something wrong with it that fast polling will
   not fix, and the strategy loop keeps reconciling it.
2. **Closed.** Reconcile even when a market-data observation fails.
   Reconciliation and deadline enforcement now precede observation.
3. **Closed.** Compare exact broker leg symbol, side, and quantity rather than
   symbol presence alone. Signed per-leg quantities are compared and a mismatch
   raises `leg_imbalance` and halts new risk.
4. **Closed.** Preserve nested Alpaca MLeg response structures; do not stringify
   the `legs` collection before reconciliation. This was more than a fidelity
   loss: `_leg_fills` iterated the resulting string character by character and
   raised `AttributeError`, which propagated out of `reconcile()` and would have
   killed the tick on the first genuine multi-leg fill.
5. **Closed.** Reconcile immediately after every submit, cancel, and ambiguous
   response.
6. **Closed.** Persist the observations and exit decisions used while a position
   is open. `position_observations` and `exit_decisions` are written by the
   management path: the mark before the policy runs, every evaluation including
   `HOLD` and `UNMEASURABLE` after it.
7. **Closed.** Pass deterministic risk-check details into live decision
   recording. The governor is held for the pass that used it rather than built
   inline and discarded.
8. **Closed.** Add versioned database migrations before changing the hosted
   schema. Alembic is configured with a baseline marker and the capture
   revision; `create_schema` stamps head. See runbook section 7.5, including the
   stated limitation that `upgrade head` does not build an empty database.
9. **Open.** Reconcile documents that still describe the older, process-local
   lifecycle and the deployment runbook sections that disagree about worker
   deployment.

## 3. Recommended operating cadence

All times are Eastern market time derived from `America/New_York`. Do not encode a
fixed UTC offset. The exchange calendar must govern holidays, early closes, and
daylight-saving changes.

| Process | Initial recommended cadence | Rationale |
|---|---|---|
| Worker startup and recovery | 08:45 ET and after every restart | Reconcile account, orders, positions, incidents, calendar, and policy before entry evaluation. |
| Daily signal calculation | 16:15 ET after the completed bar, or before the next session | EMA/retest inputs change once per completed daily session. |
| Entry opportunity scan | Every 15 minutes from 09:45 to 15:15 ET, only while flat | Option quotes and IV can change while the daily setup remains fixed; more frequent full decisions add correlated records rather than new signal information. |
| Immediate post-submit check | Immediately after submission | Establish accepted, rejected, filled, or ambiguous state without waiting for the strategy loop. |
| Pending entry monitoring | Every 5-10 seconds until terminal or the 90-second candidate deadline | The order clock must be faster than the deadline it enforces. |
| Position valuation | Every 60-120 seconds while exposure exists | Suitable starting cadence for a multi-session spread without claiming high-frequency reaction. |
| Structural invalidation | After the completed daily bar is finalized | The current invalidation is a completed-session close rule. |
| Broker reconciliation while flat | Every 15 minutes and immediately before an entry | Lower urgency when no order or exposure exists. |
| Broker reconciliation with an order or exposure | Every 60 seconds | Detect fills, leg imbalance, quantity drift, missing exposure, or broker/local disagreement. |
| Reconciliation after mutation | Immediately, then again after 30-60 seconds | Covers response ambiguity and cancel/fill races. |
| Pending close monitoring | Every 5-10 seconds until flat or the 120-second candidate deadline | A submitted close is not a closed position. |
| End-of-session report | 16:20-16:30 ET | Summarize decisions, refusals, fills, incidents, and unresolved responsibility. |
| Database backup | Nightly after reconciliation | Protect the authoritative lifecycle record. |
| Restore rehearsal | Monthly | A backup is not proven until restoration succeeds. |

These values are initial engineering parameters, not validated trading-policy
parameters. Provider rate limits, observed latency, feed entitlement, and Paper
evidence may justify changing them through the governed process in Section 7.

## 4. Delivery phases

### Phase 0 — Establish one authoritative baseline

**Objective:** make code, documents, deployed mode, and policy status agree.

Work:

1. Audit the current source against the exit review, traceability matrix,
   implementation plan, README, and deployment runbook.
2. Correct obsolete claims without declaring provisional trading thresholds
   approved.
3. Record the deployed worker mode and its actual write authority.
4. Freeze the current strategy, exit, prompt, model, runtime, feed, and schema
   versions as the control candidate.
5. Convert the findings in Section 2.3 into owned acceptance tests.

**Owners:** Product, Trading, Backend, Risk, QA.

**Exit gate:** one source-of-truth status exists and autonomous Paper entry remains
disabled.

### Phase 1 — Complete learning-quality capture

**Objective:** reconstruct every decision and managed position through its declared
outcome without console logs.

Add append-oriented records for:

- `position_observations` — position, snapshot/quote source time, long bid, short
  ask, conservative spread value, underlying observation, DTE, session count, data
  quality, and policy version;
- `exit_decisions` — evaluated triggers, governing trigger, precedence version,
  suggested limit, decision time, observation reference, order reference, and
  disposition;
- `decision_outcomes` — declared horizon, observed path, MFE, MAE, realized Paper
  P&L, stressed P&L, invalidation result, execution quality, and evaluator version;
- `review_jobs` — trigger, horizon, idempotency key, status, attempts, completion,
  and error;
- provider/broker activity times distinct from local detection times.

Implementation requirements:

1. Add versioned schema migrations and a rollback path.
2. Persist a management observation before evaluating an exit.
3. Persist every exit evaluation, including `HOLD` and `UNMEASURABLE`.
4. Link entry, management, exit, orders, fills, and outcome by durable identifiers.
5. Preserve the original decision and snapshot; outcome enrichment appends data and
   never edits the historical decision.
6. Pass the deterministic governor's risk checks to the live decision recorder.
7. Redact account/provider identifiers from derived public exports.

**Owners:** Backend, Trading, QA, Security.

**Exit gate:** one test lifecycle and one `NO_TRADE` case are reconstructable through
their outcomes with immutable original decisions.

### Phase 2 — Separate the runtime clocks

**Objective:** give order safety the cadence it needs without reevaluating a daily
strategy every few seconds.

Work:

1. Implement independent strategy, position, order, reconciliation, review, and
   heartbeat jobs.
2. Make all jobs idempotent and safe after restart.
3. Keep REST reconciliation as the authoritative watchdog. Streaming may later be
   added as a latency optimization, not as the only source of truth.
4. Reconcile before observation-dependent decision work so a data failure cannot
   suppress broker responsibility.
5. Normalize nested Alpaca order and leg responses recursively.
6. Reconcile exact leg symbols, signed quantities, and strategy quantities.
7. Reconcile immediately after submits/cancels and continue until terminal.
8. Keep one database-backed writer lease and prove two-worker contention.

**Owners:** Backend, Alpaca Integration, Risk, DevOps, QA.

**Exit gate:** the 90/120-second order deadlines are enforced within their declared
tolerance, a broken leg is detected, and observation failure cannot stop
reconciliation.

### Phase 3 — Deterministic outcome evaluation

**Objective:** measure process quality separately from outcome quality.

Implement:

- `OutcomeEnricher` for exit, one-session, three-session, and declared research
  horizons;
- `DecisionEvaluator` for data, setup, thesis, option selection, risk, execution,
  exit, and operational attribution;
- equivalent fixed-horizon enrichment for `NO_TRADE` decisions;
- MFE/MAE, fill/slippage, exit efficiency, actual Paper P&L, and conservative
  stressed P&L;
- reports grouped by setup, direction, regime, feed, DTE, delta, width,
  debit/width, quote spread, policy, prompt, model, and failure reason;
- paired deterministic-baseline versus bounded-model analysis on identical
  snapshots.

Required classifications:

1. good process, favorable outcome;
2. good process, unfavorable outcome;
3. defective process, favorable outcome;
4. defective process, unfavorable outcome;
5. correct refusal;
6. valid missed opportunity;
7. not yet measurable or not attributable.

**Owners:** Trading, Quant Research, Risk, QA.

**Exit gate:** the evaluator can explain which component contributed to an outcome
without equating profit with correctness.

### Phase 4 — Govern recommendations and promotion

**Objective:** allow evidence-backed improvement without runtime self-modification.

Add:

- immutable policy, prompt, model, feed, schema, and code versions;
- recommendation records with current/proposed behavior, supporting and
  contradicting evidence, uncertainty, owner, and rollback target;
- frozen replay, walk-forward, stress, regression, and hard-failure evaluation
  runs;
- sample-sufficiency, uncertainty, multiple-testing, and regime-coverage gates;
- manual Trading/Risk/QA approval;
- no-write champion/challenger shadow comparison;
- append-only promotion, rejection, activation, and rollback history.

Recommendation lifecycle:

```text
PROPOSED -> VALIDATING -> VALIDATED -> APPROVED -> SHADOW -> ACTIVE
     |            |           |           |          |
     +--------> REJECTED <-----+-----------+----------+
                                             |
                                             +-> ROLLED_BACK
```

**Owners:** Trading, Risk, QA, Product, Backend.

**Exit gate:** a candidate cannot change active behavior or reach the execution
gateway without reproducible evidence and recorded authorization.

### Phase 5 — Controlled Paper canary

**Objective:** validate the governed runtime with bounded Paper authority.

Prerequisites:

- Phases 0-4 gates pass;
- exit thresholds have named Trading-owner approval and sensitivity evidence;
- the worker has protected Paper-only credentials, durable PostgreSQL, migrations,
  lease, monitoring, backup, restore, and rollback evidence;
- restart, database outage, observation outage, ambiguous response, rejected,
  expired, partial, late-filled, imbalanced-leg, unfilled entry, and unfilled close
  tests pass.

Canary limits:

- SPY only;
- one open or pending strategy;
- fixed per-trade maximum loss;
- defined canary duration and rollback triggers;
- automatic `NO_NEW_RISK` on integrity failure;
- risk-reducing close authority retained only through the verified gateway;
- Paper results reported separately from stressed results;
- no live-money escalation path.

**Owners:** Risk, Trading, Backend, DevOps, QA.

**Exit gate:** the canary survives forced restart and broker ambiguity without
duplicate exposure, abandoned responsibility, or premature flat claims.

## 5. First implementation session — 29 August 2026

The first session begins at **10:00 GMT-5**. Because 29 August 2026 is a Saturday,
the session is for offline implementation and deterministic tests. Do not represent
it as market-hour Paper validation.

### 5.1 Must complete

| Time, GMT-5 | Work | Deliverable |
|---|---|---|
| 10:00-10:45 | Current-truth audit | Reviewed list of stale claims, implemented capabilities, open blockers, and authoritative source for each. |
| 10:45-11:30 | Freeze contracts | Approved schemas and invariants for `position_observations`, `exit_decisions`, and `decision_outcomes`. |
| 11:30-13:00 | Schema foundation | SQLAlchemy models plus a versioned migration and tested rollback for the three records. |
| 14:00-15:15 | Repository layer | Idempotent append/read methods with immutable-decision tests. |
| 15:15-16:30 | Runtime capture | Persist position observations and exit decisions without changing trading authority or trigger values. |
| 16:30-17:30 | Tests | Hold, unmeasurable, stop, profit, session, expiry, restart, and duplicate-job tests. |
| 17:30-18:00 | Verification and handoff | Focused suite, full offline validation, updated status, and next-session blockers. |

### 5.2 Should complete if the must-complete gate is green

1. Pass deterministic risk-check details from the live agent to `DecisionRecorder`.
2. Add one end-to-end test proving the mark that triggered a close is durable after
   restart.
3. Add a minimal read-only report over position observations and exit decisions.
4. Draft the order-clock interface without changing the current worker cadence.

### 5.3 Explicitly deferred from the first session

- Enabling `paper_execute` on the deployed worker.
- Changing entry or exit thresholds.
- Adding streaming providers.
- Building policy promotion or shadow execution.
- Claiming strategy improvement from the current Paper sample.
- Market-hour live validation; schedule it for the next eligible exchange session
  after offline gates pass.

## 6. Test and acceptance matrix

| Area | Minimum evidence |
|---|---|
| Observation capture | Every open-position evaluation stores the exact mark, source time, data quality, position quantity, and policy version. |
| Exit trace | `HOLD`, each closing trigger, and `UNMEASURABLE` persist evaluated and governing triggers before any mutation. |
| Immutability | Outcome enrichment cannot update or delete the original decision snapshot, thesis, risk result, or policy version. |
| Idempotency | Restarting or retrying a review job creates one outcome for the same decision, horizon, and evaluator version. |
| Time integrity | No post-decision outcome is visible to entry or thesis code; timestamps reject future leakage. |
| Reconciliation | Exact signed broker leg quantities match local strategy quantities; missing or extra exposure halts new risk. |
| Deadline | Entry and close deadlines are enforced by the order clock within declared tolerance. |
| Failure isolation | Market-data failure does not prevent broker reconciliation or retained position responsibility. |
| Outcome metrics | MFE/MAE, actual Paper P&L, stressed P&L, slippage, and exit efficiency reproduce from stored observations. |
| Refusal review | `NO_TRADE` outcomes use the same declared horizons and friction assumptions as traded decisions. |
| Promotion safety | Shadow candidates have no dependency path to the execution gateway. |
| Regression | Existing offline suite, lifecycle tests, lint, typing, replay determinism, firewall, secret scan, and dependency audit remain green. |

## 7. Review and promotion timing

| Trigger | Work | Authority |
|---|---|---|
| Immediately | Broker, data, risk, database, worker, or reconciliation incident handling | Deterministic runtime safety policy |
| Daily after the session | Operational, fill, refusal, unresolved-order, position, and incident report | Automatic report; human reviews exceptions |
| Weekly | Data quality, execution quality, fill/cancel rates, refusal distribution, and open findings | Trading, Backend, Risk, QA; no automatic policy change |
| Declared outcome horizon | Enrich each trade and refusal at exit, one session, and three sessions | Automatic idempotent job |
| Predeclared rolling sample gate | Strategy, exit, regime, feed, uncertainty, and multiple-testing evaluation | Quant, Trading, Risk, QA |
| After-hours approval window | Approve, reject, or request more evidence for a validated candidate | Authorized humans only |
| Shadow completion | Compare champion and challenger on identical observations | QA and Trading review; challenger remains no-write |
| Controlled Paper promotion | Activate an approved version with rollback alarms | Product, Trading, Risk, QA approval |
| Monthly | Restore rehearsal, access review, and rollback rehearsal | DevOps, Security, Backend |

Time alone never promotes a change. The rolling sample gate must be defined by power
analysis, regime coverage, independence, and materiality rather than an arbitrary
number of days or trades.

## 8. Recommended delivery order

1. Correct the current-truth documentation and freeze the control versions.
2. Persist position observations and exit decisions.
3. Add immutable trade and `NO_TRADE` outcomes.
4. Separate strategy, position, order, reconciliation, and review clocks.
5. Fix recursive Alpaca MLeg normalization and exact signed-quantity reconciliation.
6. Calculate MFE/MAE, execution metrics, realized Paper P&L, and stressed P&L.
7. Build deterministic process/outcome scoring and attribution.
8. Add policy registry, recommendations, evaluation runs, and manual approval.
9. Run candidates in technically no-write shadow mode.
10. Enable a controlled Paper canary only after every prerequisite gate passes.

## 9. Project conclusion

The runtime should be fast where uncertainty creates broker risk and deliberately
slow where the hypothesis is daily and the evidence is statistical. Order state
needs seconds, position valuation needs minutes, structure needs completed sessions,
and strategy improvement needs completed outcomes plus offline review. Treating all
four as “real time” would add complexity and encourage invalid adaptation without
improving the declared strategy.
