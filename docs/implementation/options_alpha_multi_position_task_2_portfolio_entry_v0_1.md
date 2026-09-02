# Options Alpha Agent

## Multi-Position Task 2 — Portfolio Evidence and Cap Two

*Post-hackathon portfolio work. Implementation begins in shadow mode; cap two is
not authorized by this document.*

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Date | 31 August 2026 |
| Status | Deferred until after the hackathon. **Task 1 is complete and deployed as of 1 September 2026**, so that half of the dependency is discharged |
| Directional engineering effort | 12-21 engineer-days |
| Evidence duration | Absolute minimum about six trading weeks; realistically several months |
| Entry capacity during implementation | One open or pending strategy |
| Dependency | [Task 1 — Manage Many, Enter One](options_alpha_multi_position_task_1_manage_many_v0_1.md) |
| Master handoff | [Multi-Position Scaling Handoff](options_alpha_multi_position_scaling_handoff_v0_1.md) |

## 1. Outcome

Determine whether the one-entry limit blocks economically material, genuinely
distinct opportunities. If it does, add a deterministic, atomic portfolio-admission
system and run a reversible maximum-two-position Paper canary.

The implementation must separate three claims:

1. the software can manage multiple exposures;
2. the portfolio governor can prevent risk oversubscription;
3. a second position improves results under the same aggregate risk budget.

Task 1 addresses claim 1. Task 2 must validate claims 2 and 3 before changing entry
authority.

## 2. Preconditions

Status as of 1 September 2026. Four of six are met; the two that are not are
organizational rather than technical, which is the correct shape for this to be
blocked on.

| # | Precondition | Status |
|---|---|---|
| 1 | Task 1 deployed and its acceptance matrix passes | **Met.** Deployed 1 September; 18 acceptance tests pass on SQLite and on PostgreSQL 16.15, the same point release the worker runs (`EV-038`, `EV-039`, `EV-040`) |
| 2 | The worker reconstructs and manages the complete attributable active set | **Met.** `manage_positions()` reconciles once, re-reads, fans one snapshot across every position and isolates per-position failure; `T1-AC-05` covers restart reconstruction |
| 3 | Inherited overlapping symbols have a tested fail-closed/operator path | **Met.** Contested symbols are held out of the per-position path entirely and answered in aggregate, with no lot allocation and no lifecycle state change; `T1-AC-09` and `T1-AC-09b` |
| 4 | The gateway still permits only one open or pending strategy | **Met and unchanged.** `T1-AC-12` asserts the refusal, and the gateway states the cap itself rather than letting the caller infer it from a count |
| 5 | Trading/Risk names owners for total, cluster, daily-loss and re-entry risk | **Not met.** Organizational, not technical. `RISK-007` to `RISK-010`, `RISK-012`, `RISK-013` and `CLR-013` all remain open and are prerequisites, not cleanup |
| 6 | Policy changes remain offline, versioned, approved, and reversible | **Partly met.** Versioning and reversibility exist - `POLICY_VERSION` moved to `h0-provisional-1` when the risk budget changed, and every threshold is `PROVISIONAL` - but *approved* is exactly what `DEC-008` and `DEC-010` still lack |

## 3. Non-goals

- Live-money trading.
- Three or more positions in the first release.
- Multiple tradeable underlyings.
- Automatic lot allocation for overlapping option symbols.
- Simultaneous opposing SPY strategies.
- Offset credit between SPY positions.
- Horizontal worker partitioning.
- Online learning or threshold mutation.
- Treating Paper profit or raw trade count as validated alpha.

## 4. Phase 2A — Shadow capacity measurement

While an existing position occupies the entry slot, continue the candidate workflow
without broker write authority and persist:

- disposition `CAPACITY_BLOCKED`;
- stable completed-session cohort ID;
- candidate direction, contracts, expiration, debit, and approved maximum loss;
- existing position and contract overlap;
- total and cluster risk the candidate would add;
- exact reason the candidate would be refused;
- data, feed, strategy, risk, and exit policy versions;
- one- and three-session counterfactual outcomes after their horizons complete.

One completed-session signal state is one cohort. Repeated 15-minute scans of that
state are observations of one opportunity, not independent samples.

### 4.1 Stable cohort identity

The cohort key must exclude intraday `snapshot_id` and include at least:

- underlying;
- setup family;
- direction;
- completed-session date whose evidence changed;
- strategy-policy version.

A database constraint or deterministic admission check must prevent more than one
risk-increasing intent from the same cohort. Re-entry after exit is forbidden until
Trading/Risk approves a separate rule.

## 5. Phase 2B — Portfolio-risk ledger

Add a transactional `risk_reservations` ledger or an equivalent model containing:

- account/portfolio key;
- position and entry-order identity;
- cohort and cluster keys;
- reservation state;
- approved maximum loss;
- confirmed exposure risk;
- created, reconciled, released, and policy-version timestamps;
- immutable approval reference.

Reserve the approved maximum loss from the risk decision. Do not recompute it as
`long.ask - short.bid`: the approved debit already contains the execution allowance,
and recomputing from the raw crossing would silently under-reserve.

### 5.1 Lifecycle accounting

| State | Portfolio treatment |
|---|---|
| `PENDING` | Reserve full approved maximum loss and one pending slot |
| Partial fill | Count confirmed exposure and retain the remaining reservation until cancel is terminal |
| `OPEN` | Count actual confirmed defined risk; no offset credit |
| `CLOSING` | Retain risk and slot until broker-flat reconciliation |
| `INCIDENT` | Treat exposure as unknown, halt new risk, and retain the conservative reservation |
| `ABANDONED` | Release ordinary reservation only after terminal confirmation; continue late-fill surveillance |
| `CLOSED` | Release after broker-flat confirmation |

### 5.2 Atomic admission

```text
lock portfolio/account risk state
-> verify fresh broker, account, and policy state
-> calculate confirmed plus pending risk
-> apply total, SPY-cluster, daily-loss, count, cohort, and overlap gates
-> reserve approved maximum loss
-> persist intent, exact request, order, and PENDING position
-> commit
-> submit through the existing Paper-only gateway
```

The gateway must require an immutable portfolio-approval/reservation reference. It
must not infer strategy capacity from the number of broker orders plus option legs.

## 6. Phase 2C — Execution hardening

### 6.1 Close ownership

- Claim `OPEN -> CLOSING` with row locking, compare-and-set, or optimistic versioning.
- Permit only one active close attempt per position.
- Reuse one deterministic client order ID for retries of the same attempt.
- Give a legitimate later attempt a new durable attempt identity.
- Release no risk because an order was merely accepted.

### 6.2 Fill identity

Persist Alpaca execution/activity identity when available. Two genuine fills sharing
symbol, quantity, and price must remain two fills.

### 6.3 Lease fencing

- heartbeat independently during long work;
- add a monotonic lease epoch/fencing token;
- check ownership and epoch immediately before lifecycle mutations and broker
  writes;
- prove a stale worker cannot submit after takeover.

### 6.4 Contract overlap

The first cap-two release rejects a candidate before reservation if either option
symbol appears in any unresolved local strategy. Task 1's inherited-overlap
operator path remains active. Automatic overlapping-lot allocation is a separate
future project and is not required for cap two.

## 7. Phase 2D — Portfolio operational surface

Add:

- confirmed open risk and pending reserved risk;
- SPY-cluster risk and applicable limit;
- daily realized and conservative marked loss;
- count by lifecycle state;
- per-position mark age, reconciliation age, next deadline, risk, current value,
  exit state, and incident state;
- position-scoped intent/order/fill/observation/exit lineage;
- capacity-blocked cohort counts and reasons;
- the active admission-policy version;
- cap-one/cap-two mode and rollback control evidence;
- alerts for unmanaged, unvalued, overlapping, or unreserved exposure.

The dashboard remains read-only and credential-free.

## 8. Research promotion gate

The values below are provisional research recommendations, not approved trading
policy. Pre-register them before examining the completed sample.

1. At least 30 distinct blocked cohorts across at least two declared regimes, with
   at least 10 in each.
2. Capacity blocks at least 15% of otherwise eligible cohorts.
3. Walk-forward cap two improves net return per defined-risk-day over cap one under
   the same aggregate risk budget.
4. The lower bound of a 95% block-bootstrap interval for incremental return per
   risk-day exceeds zero.
5. Maximum drawdown and 95% expected shortfall stay within a pre-approved relative
   tolerance.
6. The direction of the result survives conservative indicative-feed execution
   stress.
7. Whole overlapping episodes, not position rows, are the resampling unit.

The absolute theoretical minimum for 30 cohorts is approximately 30 trading days,
or six calendar weeks, if every session qualifies and is blocked. Because only
otherwise eligible and blocked sessions count, and two regimes cannot be produced
on demand, several months is the more realistic expectation.

If two indivisible one-contract spreads cannot fit under the same aggregate budget,
that is evidence of a capital-granularity constraint. It is not evidence that the
risk budget should be increased.

## 9. Paper cap-two canary

Only after the portfolio governor and research gate receive recorded approval:

- maximum two `OPEN` strategies;
- maximum one `PENDING` entry;
- unique option symbols across strategies;
- unique completed-session cohort;
- every SPY position belongs to one additive cluster;
- no offset credit;
- no opposing-direction SPY strategies;
- no entry while any position is `CLOSING` or `INCIDENT`;
- pending risk remains reserved until terminal reconciliation;
- default and rollback configuration remains cap one.

Exercise at least 20 overlapping-position lifecycle episodes with zero duplicate
orders, incorrect closes, risk oversubscriptions, unowned legs, stale-worker writes,
or restart/reconciliation failures. This validates mechanics, not profitability.

## 10. Acceptance matrix

| ID | Scenario | Required result |
|---|---|---|
| `T2-AC-01` | Candidate overlaps an unresolved option symbol | Refused before reservation and submission |
| `T2-AC-02` | Two admission attempts race | Atomic reservation prevents count or risk oversubscription |
| `T2-AC-03` | Pending order partially fills | Confirmed and reserved risk sum conservatively until terminal cancel |
| `T2-AC-04` | Close is accepted but not filled | Position and risk allocation remain owned |
| `T2-AC-05` | Same cohort is scanned repeatedly | At most one risk-increasing intent is admitted |
| `T2-AC-06` | Two genuine identical-price fills occur | Both persist by broker execution identity |
| `T2-AC-07` | Lease expires during an operation | Stale worker is fenced before another mutation |
| `T2-AC-08` | Restart with reservations and positions | Open plus pending risk reconstructs exactly |
| `T2-AC-09` | Position enters incident | New risk halts and conservative risk remains reserved |
| `T2-AC-10` | Candidate would exceed total or SPY-cluster risk | Deterministic refusal with versioned reason |
| `T2-AC-11` | Daily-loss stop is reached | New entries halt across restart |
| `T2-AC-12` | Cap is rolled from two to one with positions open | No forced abandonment; management continues and no additional entry occurs |
| `T2-AC-13` | Dashboard selects one position | Only its lineage appears while portfolio totals remain consistent |

## 11. Rollout and rollback

1. Deploy schema and code with cap one.
2. Run the portfolio governor in shadow mode.
3. Reconcile shadow reservations against every lifecycle transition.
4. Complete and approve the research gate.
5. Rehearse cap-two rollback and worker restart.
6. Enable cap two only through explicit versioned Paper configuration.
7. Return immediately to cap one after any attribution, reservation, duplicate,
   deadline, fencing, or reconciliation defect.

Reducing the cap never automatically closes existing positions. It blocks further
entries while Task 1 continues managing every attributable position.

## 12. Effort and ownership

| Work | Owner | Directional effort |
|---|---|---:|
| Shadow cohorts and outcome enrichment | Quant + Backend | 1-3 engineer-days plus evidence time |
| Portfolio schema, reservations, and admission | Backend + Trading/Risk | 4-7 engineer-days |
| Close claims, fill identity, and fencing | Backend + DevOps | 3-5 engineer-days |
| Operational portfolio surface | UX/UI + Backend | 2-3 engineer-days |
| Failure matrix, deployment, and Paper proof | QA + Backend + Trading | 2-3 engineer-days plus market sessions |

Some work can overlap; the planning range is **12-21 engineer-days**. The evidence
calendar, not staffing, controls when cap two may be authorized.

## 13. Definition of done

Task 2 is complete only when:

- Task 1 remains green;
- all `T2-AC-*` cases pass in a production-shaped environment;
- portfolio risk and reservations reconcile through fills, cancels, closes,
  incidents, restarts, and rollback;
- Trading/Risk approves versioned total, cluster, daily-loss, count, and re-entry
  policies;
- the research gate has a recorded disposition;
- the cap-two Paper canary completes without an integrity failure;
- cap one remains the tested default and rollback target;
- no result is presented as live-market or strategy-alpha validation.
