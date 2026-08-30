# Options Alpha Agent

## Exit Policy and Position-Lifecycle Review v0.1

*Adversarial review of the provisional H0 exit implementation; this is a remediation specification, not release approval or evidence of strategy profitability*

| Field | Value |
|---|---|
| Version | 0.1.1 |
| Date | 28 August 2026 |
| Status | Required remediation; candidate policy values remain provisional |
| Scope | Exit evaluation, autonomous agent, execution gateway, persistence models/repository, manual lifecycle artifact, related tests, entry timing, and deployed worker boundary |
| Governing requirements | `CLR-020`, `RISK-017` to `RISK-021`, `OPS-001` to `OPS-005`, `QA-009`, `QA-010`, `QA-014` |

## 0. Disposition as of 29 August 2026

**This review is a historical record and is deliberately not rewritten.** Its
findings were accurate when written on 28 August 2026; the prose below still
describes the code as it was that day. What follows is the current status of
each finding, so a reader does not have to infer it from a document that was
correct about a version that no longer exists.

| ID | Disposition | Where it closed |
|---|---|---|
| `EXIT-001` | **Closed.** Broker acceptance is recorded as `SUBMITTED`, never as `FILLED`. Only reconciled fills establish the position basis or release monitoring responsibility. | `EV-020` to `EV-022` |
| `EXIT-002` | **Closed.** Position ownership is durable and reconstructed from the database and the broker at startup; a mismatch raises an incident and halts new risk. | `EV-020` to `EV-022` |
| `EXIT-003` | **Closed.** The time stop counts completed trading sessions from the first reconciled fill using the authoritative calendar; DTE remains a separate expiry control. | `EV-021`, `EV-023` |
| `EXIT-004` | **Closed.** Every rule is evaluated independently; one that cannot be evaluated stores `fired: null` rather than `false`, raises a durable incident, halts new risk, and retains exit ownership. | `EV-023`, `EV-024` |
| `EXIT-005` | **Closed.** The invalidation is a typed rule carrying level, direction and price source, persisted before entry; the prose is written from the rule rather than parsed back out of it, and a completed-session rule is refused against a price it cannot match. | `EV-023` |
| `EXIT-006` | **Partial, by decision.** The close has a bounded submit/deadline/cancel/reconcile lifecycle with an enforced 120-second deadline and a fast order clock. Limit staging, maximum concession and an attempt budget are deliberately **not** implemented: replace-and-chase has real economic cost and stays provisional until there is evidence for its parameters. | `EV-024`; see `exits.py` header |
| `EXIT-007` | **Open.** Early-close and calendar handling closed with `EXIT-012`. Scheduled-event disposition, unexpected-exposure policy beyond the incident path, and assignment risk have no explicit rule; expiry safety is handled only by the DTE guard. | - |
| `EXIT-008` | **Closed as a documentation action.** The status correction was applied and has been maintained: thresholds remain `PROVISIONAL` and `DEC-008` remains open. | this section |
| `EXIT-009` | **Closed.** `observe()` uses the injected clock throughout; replay and production share temporal semantics. | `EV-021` |
| `EXIT-010` | **Closed.** Data-quality and reconciliation state drive a durable execution-state transition, and entries halt while reconciled risk-reducing closes remain available. | `EV-023` |
| `EXIT-011` | **Closed.** Accepted entry orders are reconciled until terminal, partial fills are managed, and an owner-approved deadline cancels rather than replaces. A separate five-second order clock enforces the deadline on its own timescale. | `EV-024` |
| `EXIT-012` | **Closed.** The entry window is derived from the authoritative calendar, including a market holiday and an early close. | `EV-023` |
| `EXIT-013` | **Partial.** A credentialed worker with hosted PostgreSQL, a single-writer lease, startup reconciliation and migrations is deployed on a host separate from the public dashboard, with forced-restart evidence. Monitoring, alerting, backup and restore are **not** done, so `EXIT-AC-16` is unmet. | `EV-024`, runbook section 7 |

The lifecycle machinery this review demanded now exists. What is missing is
policy evidence - threshold sensitivity and `DEC-008` - and hosted backup and
alerting.

**Armed 30 August 2026.** Autonomous Paper entry was enabled deliberately, on
the owner's instruction, to produce live decision evidence for the hackathon
demonstration. It was **not** enabled because these conditions were met: the
thresholds remain `PROVISIONAL` without sensitivity evidence and `DEC-008` is
open. Disarm with `scripts/disarm_worker.sh`. The findings below are closed on their own terms; arming does
not close them, and nothing in this review should be read as approving the
threshold values.

## 1. Strongest argument against enabling autonomous entry

The strongest objection is not that the numerical thresholds might be suboptimal. It is that the agent does not have a reliable fact model for whether it owns a position at all.

On an ordinary broker response, the gateway returns `reconciled=False`. The agent immediately creates an in-memory `OpenPosition` and reports `POSITION_OPENED`. On a close response, it immediately deletes that object and reports `POSITION_CLOSED`. Neither transition is conditioned on a filled strategy quantity or a reconciled broker position. A restart also initializes `open_position` to `None` and does not reconstruct it from durable records or Alpaca.

The failure modes are direct:

1. An accepted but unfilled entry is monitored as if filled, using an estimated debit.
2. A partially filled entry is represented as a complete strategy with the requested quantity.
3. An accepted but unfilled close causes monitoring to stop while exposure may remain.
4. A restart forgets an existing spread; the broker-side one-strategy guard may prevent another entry, but it does not cause the old position to be managed.

For an autonomous trading agent, losing the mapping between broker exposure and local responsibility is a release-blocking defect. Better stop-loss percentages cannot compensate for it.

## 2. Review question and conclusion

**Hypothesis:** the autonomous agent now has sufficiently defined and tested exit rules to open and manage one H0 Paper position safely.

**Conclusion:** the hypothesis is not validated. Deterministic exit evaluation and close-intent construction now exist, which is useful progress. The autonomous position lifecycle is still unsafe to call complete because order acceptance is treated as a fill, position state is process-local, the entry basis is estimated rather than filled, and a submitted close is treated as a closed position before reconciliation. The code can therefore lose responsibility for real Paper exposure even while reporting `POSITION_OPENED` or `POSITION_CLOSED`.

This conclusion does not invalidate the separate manual Paper MLeg transport proof. It limits what that proof establishes: exact request mapping, guarded submission, observed broker fills, and an observed broker-flat result. The current command does not persist fills or positions, does not apply its printed reconciliation result to durable lifecycle records, and does not reconcile the close before returning. It therefore does not prove local durable reconciliation or autonomous position ownership.

## 3. Facts, reasonable inferences, and speculation

### 3.1 Facts observed in the repository

- `exits.py` defines provisional stop-loss, profit-capture, time-stop, expiry, invalidation, and unmeasurable-value outcomes with an explicit precedence tuple.
- `agent.py` evaluates an existing in-memory position before considering a new entry and can construct a risk-reducing close intent.
- The normal gateway submit result is explicitly `reconciled=False`.
- The agent creates `OpenPosition` immediately after submission and labels the tick `POSITION_OPENED`; it uses the selected spread's `estimated_debit` rather than a broker fill price.
- The agent clears `open_position` immediately after close submission and labels the tick `POSITION_CLOSED`.
- `open_position` and tick history are held in process memory. Startup does not reconstruct managed positions from Alpaca or the repository.
- `Position` and `Fill` tables are declared but are not read or written by the repository or agent. The manual lifecycle persists an intent, prepared request, and initial broker-order row with `filled_quantity=0`; it prints one open-order lookup but does not persist that result, any fills, a position, or a reconciled close.
- The normal observation cycle does not query open orders, fills, activities, or positions. The gateway counts open orders and positions only when a new-risk request reaches preflight; that guard can refuse a second strategy but cannot restore management of the first.
- The 90-second `INTENT_TTL` expires authority before submission. It is not a post-submission order deadline. Submitted orders use `day` time-in-force, but the gateway has no cancel, replace, partial-fill, rejected-order, or day-expiry lifecycle.
- Entry timing checks only whether Alpaca reports the market open. The 09:45-15:15 ET window in the implementation plan is a provisional candidate and is not implemented or owner-approved.
- The Alibaba ECS deployment runs only the credential-free dashboard. It deliberately omits the decision worker, execution gateway, provider credentials, and a hosted durable lifecycle database.
- The implemented time stop is `DTE <= 10`; the trading design states an intended 1–3 session horizon.
- Invalidation is recovered from free-form text by parsing a decimal and is evaluated against the current underlying snapshot, not a typed completed-session rule.
- If spread value is unavailable above the expiry-guard range, `UNMEASURABLE` returns `should_close=False` before invalidation is evaluated. The agent reports `POSITION_REVIEW`, but the path does not create a durable incident or change the gateway halt state.
- The suggested close limit is 90% of the computed conservative spread value. No bounded cancel/replace or close-fill reconciliation is part of the autonomous cycle.
- Unit tests cover the current trigger arithmetic, precedence tuple, submission guards, and immediate in-memory transitions. They do not prove fills, partial fills, restart reconstruction, or continued ownership after an unfilled close.

### 3.2 Reasonable inferences

- A 45-DTE entry governed only by `DTE <= 10` could remain open for roughly 35 calendar days, so the implemented rule is not a time stop for a 1–3 session thesis.
- Because `UNMEASURABLE` is evaluated before structural invalidation, missing option quotes can suppress a non-option-price exit signal unless the position is already inside the expiry guard.
- Because the entry basis is estimated, profit and loss thresholds can diverge from actual economics even when the order later fills completely.
- A broker count that blocks a second entry reduces duplicate exposure, but it is not a position manager and does not restore exit responsibility after restart.
- Reporting broker acceptance as opened or closed can mislead both operators and the judge interface about actual exposure.
- After restart, a qualifying new entry produces `ENTRY_REFUSED` while Alpaca still reports an order or position, but that refusal is console/in-memory state rather than a durable reconciliation incident. Calling the failure entirely silent is too strong; calling the exposure unmanaged is accurate.
- A `day` order will not remain at the broker indefinitely, but the same-process agent can retain a phantom `OpenPosition` after the order is canceled, rejected, or expires because no terminal broker state is consumed.

### 3.3 Speculation that is not established

- The provisional 50% debit stop and 60% maximum-gain capture may or may not be robust for this setup. The repository contains no adequate replay or sensitivity evidence to establish that.
- A 10% price concession may improve fill probability, but no current evidence shows it is an acceptable or sufficient close algorithm across spread widths and market states.
- Conviction-decay exits may add value, but the current project has no validated maintenance score. Adding a narrative score now could create churn rather than safety.
- Paper fill behavior does not establish live execution quality, assignment handling, or real-world slippage.
- The estimate that durable state, reconciliation, and actual-fill economics require half a day is unsupported. It may describe a mock-backed skeleton, not production-worthy unattended behavior; implementation duration depends on partial-fill semantics, database changes, failure tests, and access to market-hour Paper validation.

## 4. Finding register

| ID | Severity | Finding | Required disposition |
|---|---|---|---|
| `EXIT-001` | Critical | Submission acceptance is treated as a completed entry or exit. | Introduce durable pending/open/closing states. Only reconciled fills may establish the filled position basis or release monitoring responsibility. |
| `EXIT-002` | Critical | Position ownership is process-local and is not reconstructed after restart. | Reconcile broker orders, fills, activities, and positions at startup; rebuild the exact managed strategy or enter `NO_NEW_RISK` with a durable incident. |
| `EXIT-003` | High | The DTE-based time stop contradicts the declared 1–3 session thesis horizon. | Measure completed trading sessions from the first reconciled fill; keep DTE as a separate expiry control. |
| `EXIT-004` | High | Missing spread value can suppress structural invalidation and creates only an ephemeral review result. | Evaluate non-premium triggers independently, raise a durable incident, enter `NO_NEW_RISK`, and retain exit ownership until reconciliation. |
| `EXIT-005` | High | Invalidation is parsed from free text and evaluated on an unspecified instantaneous price. | Persist a typed invalidation rule, direction, level, observation source, and evaluation cadence before entry. |
| `EXIT-006` | High | Close pricing has no bounded submit/replace/cancel/reconcile lifecycle. | Define limit stages, timing, maximum concession, attempt budget, cancel handling, ambiguous-write recovery, and terminal escalation. |
| `EXIT-007` | Medium | Scheduled-event, unexpected-exposure, early-close/calendar, and assignment-risk paths are absent. | Add explicit policy dispositions or explicitly exclude them with a fail-closed operational rule. |
| `EXIT-008` | High | Prior documentation marked `CLR-020` and Phase 4 complete while thresholds remained provisional and lifecycle acceptance was unmet. | The status correction is applied; keep the policy/lifecycle evidence partial and `DEC-008` open until owner approval and the acceptance suite below are complete. |
| `EXIT-009` | Medium | `observe()` uses the host date rather than the injected clock and market calendar. | Derive dates and session counts from the authoritative market clock/calendar so replay and production use the same temporal semantics. |
| `EXIT-010` | High | The stale/unusable-data helper is tested but is not shown governing the gateway state in the autonomous cycle. | Wire data-quality and reconciliation state into a durable execution-state transition and prove that entries halt while reconciled risk-reducing actions remain available. |
| `EXIT-011` | Critical | Intent expiry exists, but accepted entry orders have no post-submission fill/cancel/replace/expiry lifecycle. | Persist `ENTRY_SUBMITTED`, reconcile until terminal, manage partial fills, and apply an owner-approved deadline with cancel-only behavior before any bounded replacement policy is enabled. |
| `EXIT-012` | High | An open market is treated as an eligible entry window, including the final minute and early-close edge cases. | Freeze an entry-window policy and derive it from the authoritative market calendar. Reject entries after the earlier of the approved cutoff and the session-relative close buffer. |
| `EXIT-013` | High | No credentialed autonomous worker or durable hosted lifecycle store is deployed. | Make worker hosting a separate release gate covering secrets, database durability, lease, startup reconciliation, monitoring, restart, backup, and rollback. Do not add credentials to the public dashboard service. |

## 5. Candidate H0 exit policy

These rules are a coherent implementation target, not a claim that their numerical values are optimal. The Trading owner must approve them, and replay/sensitivity results must remain attached to the policy version.

### 5.1 Required inputs

Every managed position must be reconstructed from authoritative records and contain:

- broker order and fill identifiers, filled strategy quantity, average filled net debit, and fill time;
- immutable entry decision, policy version, structure, legs, expiration, and maximum loss;
- typed structural invalidation rule with direction, level, source field, and cadence;
- completed trading-session count from the reconciled entry fill;
- current reconciled broker position and open-order state;
- conservative executable spread value with source time and quality state;
- scheduled-event disposition and the next market-calendar boundary.

If these facts cannot be established, the system must not invent a position state. It enters `NO_NEW_RISK`, records an incident, continues broker reconciliation, and preserves a safe operator path for risk reduction.

### 5.2 Decision precedence

| Order | Condition | H0 action |
|---:|---|---|
| 1 | Broker/local mismatch, unexpected or partial exposure, duplicate/ambiguous close, or adapter-integrity failure | Enter the applicable halt state, reconcile, and execute only a verified risk-reducing disposition. Do not report flat until Alpaca confirms it. |
| 2 | Expiry guard at or below 7 DTE, or an earlier calendar/assignment boundary | Begin the bounded close lifecycle. Expiry safety overrides profit optimization. |
| 3 | A prohibited scheduled event falls inside the holding window or the pre-event blackout begins | Begin the bounded close lifecycle before the blackout. |
| 4 | Typed structural invalidation is confirmed on the configured completed-session observation | Begin the bounded close lifecycle. Missing option value must not suppress this rule. |
| 5 | Conservative executable value is at or below 50% of the actual filled net debit | Begin the bounded close lifecycle. The value remains provisional pending sensitivity analysis. |
| 6 | Three completed trading sessions have elapsed without the expected move | Begin the bounded close lifecycle. This implements the stated 1–3 session horizon; it is not an expiry rule. |
| 7 | Conservative executable value has captured at least 60% of maximum spread gain, calculated from actual fill | Begin the bounded close lifecycle. The value remains provisional pending sensitivity analysis. |
| 8 | No trigger is present and every required input is current and reconciled | Continue monitoring. |

`UNMEASURABLE` is an integrity state, not an economic precedence winner and not a synonym for `HOLD`. It must not prevent evaluation of expiry, event, completed-session invalidation, or broker-exposure conditions. If a premium-dependent rule cannot be evaluated, the system records that fact and continues evaluating independent rules.

Conviction decay is not an H0 automatic exit trigger. Until a deterministic, independently validated maintenance score exists, it may be displayed as diagnostic evidence but must not create or suppress a broker write.

### 5.3 Entry-order lifecycle

1. Persist the approved intent, exact prepared request, and `ENTRY_SUBMITTED` state atomically **before** sending the request.
2. Treat broker acknowledgement as submitted, not filled. Reconcile by deterministic client order ID and broker order ID until a terminal status is known.
3. Persist actual filled strategy quantity, per-leg fills, average net debit, and first/last fill times. A partial fill creates managed exposure for only the filled quantity and keeps the remainder pending or canceled by policy.
4. Apply an owner-approved post-submission deadline. The plan's 90-second/three-attempt replacement proposal remains provisional; the minimum safe H0 policy is cancel-only at the deadline unless bounded replacement economics and tests are approved.
5. On cancel, reject, expiry, or zero fill, record the terminal state and create no `OpenPosition`. On ambiguity or local/broker mismatch, enter `NO_NEW_RISK`, retain responsibility, and continue reconciliation.
6. Reconcile at startup, before every new-risk write, after every order mutation or ambiguous response, and periodically while any order or exposure exists.

### 5.4 Close lifecycle

1. Freeze the governing exit decision and create one idempotent close intent for the currently reconciled filled quantity.
2. Submit once and persist the prepared request, intent hash, client order ID, broker response, and state `CLOSE_SUBMITTED`.
3. Reconcile order, fills, and remaining position. Partial fills reduce the managed quantity; they do not release the remaining exposure.
4. If the order remains open, apply only an owner-approved bounded replacement schedule. Cancel and replace by reconciliation, never by blind duplicate submission.
5. Report `POSITION_CLOSED` only when the broker position is flat and the close fills reconcile to the local lifecycle.
6. On timeout, ambiguity, rejection, or mismatch, enter `NO_NEW_RISK`, retain position ownership, and open a durable incident with an operator escalation path.

## 6. Acceptance evidence required before autonomous entry

| Evidence ID | Test or artifact | Pass condition |
|---|---|---|
| `EXIT-AC-01` | Accepted-but-unfilled entry | State remains pending; no filled basis, P&L exit, or `POSITION_OPENED` claim is created. |
| `EXIT-AC-02` | Partial and complete entry fills | Filled quantity and actual average debit reconcile exactly; only filled exposure is managed. |
| `EXIT-AC-03` | Accepted-but-unfilled and partially filled close | Monitoring continues for remaining quantity; the agent never reports flat early. |
| `EXIT-AC-04` | Restart with open, pending, partially filled, and flat broker states | Startup reconstructs the same lifecycle or enters a durable halt/incident without opening new risk. |
| `EXIT-AC-05` | Local/broker mismatch and unexpected exposure | New entries halt; reconciliation and verified risk reduction remain possible; every transition is audited. |
| `EXIT-AC-06` | Typed bullish and bearish invalidation | Correct completed-session source and direction are enforced without parsing free text. |
| `EXIT-AC-07` | Session-based time stop across weekends and market holidays | The third completed trading session triggers independently of DTE. |
| `EXIT-AC-08` | Missing, stale, crossed, and one-sided option quotes | Integrity incident is durable; independent exit rules still evaluate; no missing value is interpreted as healthy. |
| `EXIT-AC-09` | Pairwise and multi-trigger precedence matrix | Emergency, expiry, event, invalidation, loss, time, and profit outcomes are deterministic and match the approved table. |
| `EXIT-AC-10` | Bounded close replacement and ambiguous-response scenarios | No duplicate close, no price beyond approved economics, and no release of responsibility before reconciliation. |
| `EXIT-AC-11` | Expiry, early-close, and assignment-risk calendar cases | Policy produces a safe explicit disposition for each boundary. |
| `EXIT-AC-12` | Threshold replay and sensitivity report | 50% loss, three sessions, 60% gain, and 7 DTE are labelled provisional or approved with named evidence and owner. |
| `EXIT-AC-13` | End-to-end autonomous Paper lifecycle | Entry and close are both fill-reconciled, durable across restart, and reconstructable from one audit query. |
| `EXIT-AC-14` | Unfilled, rejected, canceled, expired, late-filled, and partially filled entry orders | Every state is durable; no phantom position is created; the post-submission deadline cancels safely; a late fill is detected and managed. |
| `EXIT-AC-15` | Normal session, final minute, early close, holiday, and timezone cases | Entry is permitted only inside the owner-approved calendar-derived window; monitoring and risk reduction remain available outside it. |
| `EXIT-AC-16` | Credentialed worker deployment and forced restart | Dashboard remains credential-free; worker uses protected Paper secrets and a durable database; one active lease exists; startup reconciliation completes before entries; health, alert, backup, and rollback evidence pass. |

Passing unit tests for trigger arithmetic is necessary but insufficient. `CLR-020`, `RISK-017`, `RISK-020`, `RISK-021`, `OPS-001` to `OPS-005`, `QA-010`, `QA-014`, and the autonomous portion of `G2` remain incomplete until the applicable evidence above exists.

## 7. Document disposition

- Keep the trading design's exit categories and 1–3 session intent, but identify the table in Section 5 as the candidate H0 operational interpretation.
- Keep the manual Paper MLeg lifecycle as valid execution-transport evidence.
- Describe the lifecycle artifact as observed broker transport/fills/flat state, not durable local reconciliation.
- Split Phase 4 into a completed transport proof and an incomplete autonomous position-lifecycle proof.
- Mark `CLR-020` and `OPS-005` `PARTIAL`; keep `DEC-008` open.
- Treat the current `exits.py` values as provisional implementation evidence, not as frozen policy approval.
- Keep the dashboard host credential-free and add a separate worker/deployment acceptance gate rather than treating worker enablement as a copy step.

## 8. External constraint

Alpaca's [options trading overview](https://docs.alpaca.markets/us/docs/options-trading-overview) documents expiration, exercise, and assignment behavior that makes broker/calendar reconciliation material to an options exit policy. Paper behavior remains simulation evidence and is not a substitute for live-execution validation.
