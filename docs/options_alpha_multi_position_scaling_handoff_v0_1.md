# Options Alpha Agent

## Multi-Position Scaling Handoff v0.1

*Developer handoff for safely separating multi-position management from
multi-position entry. This document is not authorization to raise the entry cap.*

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Date | 31 August 2026 |
| Status | Implementation handoff; portfolio-entry policy remains unapproved |
| Environment | Alpaca Paper only |
| Current scope | One tradeable underlying (`SPY`), one trend/retest setup, vertical debit spreads |
| Primary decision | Implement **manage many, enter one** before considering concurrent entry |
| Review disciplines | Options portfolio risk, trading-systems/backend architecture, quantitative strategy/capacity |
| Related design | [Trading Design](./options_alpha_trading_design_v0_1.md) |
| Related lifecycle review | [Exit Policy and Position-Lifecycle Review](./options_alpha_exit_policy_review_v0_1.md) |
| Requirement tracker | [Requirements Traceability Matrix](./options_alpha_requirements_traceability_v0_1.md) |

## 1. Executive decision

The one-position limit is a meaningful future product constraint, but the
repository does not establish that it is currently an economic bottleneck. H0
trades one daily SPY setup. A second simultaneous position would normally add
another expression of the same directional and volatility risk rather than an
independent opportunity.

The immediate safety defect is different: if the account contains two legitimate
positions for any reason, the runtime reconciles multiple rows but actively values
and manages only the first one selected from the database. The next implementation
target is therefore:

> Reconcile, observe, evaluate, and close every position the system owns, while
> retaining one open or pending new-entry strategy.

Concurrent entry may advance only after shadow evidence demonstrates distinct
blocked opportunities and a deterministic portfolio governor controls aggregate
and pending risk.

### 1.1 Binding boundaries

- Do not raise the gateway cap in the manage-many increment.
- Do not reinterpret broker option-leg counts as strategy counts.
- Do not allow repeated entries from the same completed-session signal cohort.
- Do not allow simultaneous strategies with overlapping option contract symbols
  in the first bounded multi-entry release.
- Do not grant offsetting-risk credit between bullish and bearish SPY spreads.
- Do not introduce one worker per position. Retain one credentialed writer.
- Do not change policy, thresholds, prompts, or risk limits during a trading
  session.
- Do not treat Paper profit as evidence of validated alpha.

## 2. Strongest argument against raising the cap now

The existing entry limit is a safety boundary, not merely a configuration value.
The risk governor grants each candidate its own equity-based allowance and checks
buying power, but it does not subtract open risk, pending reservations, daily
marked loss, or correlated exposure. Removing the cap could therefore multiply a
per-trade allowance across several highly correlated SPY positions.

There is also no durable signal-cohort uniqueness rule. `SetupCandidate.setup_id`
contains `snapshot_id`, and each changed observation produces a different decision
hash and client order ID. A simple cap increase could admit repeated observations
of the same daily trend/retest thesis every strategy cycle until all slots were
filled. That is accidental pyramiding, not increased strategy breadth.

Finally, Alpaca reports net quantity by option contract. If two local strategies
share the same legs, two local `+1/-1` positions appear at the broker as `+2/-2`.
The current reconciler compares that aggregate exposure with individual local rows.
It cannot reliably determine which local thesis remains after one unit closes.

## 3. Current repository facts

### 3.1 Foundations that can be retained

- `positions` is durable and can contain multiple rows.
- `LifecycleStore.active_positions()` returns a collection.
- startup and periodic reconciliation iterate managed rows;
- deadline enforcement iterates managed rows;
- positions retain reconciled fill quantity and actual average entry debit;
- observations and exit decisions are append-only and position-linked;
- the worker holds a database-backed single-writer lease;
- the dashboard can count multiple open rows;
- exits remain permitted under ordinary `NO_NEW_RISK`.

### 3.2 Single-position assumptions that must change

| Area | Current behavior | Required disposition |
|---|---|---|
| Strategy tick | `active_position()` returns one row; `tick()` manages it and returns | Evaluate all managed exposure before considering entry |
| Position clock | Values and manages one position per pass | Fan out one reusable market snapshot to every applicable position |
| Selection order | `active_positions()` issues no `ORDER BY`, so "the first row" is whatever the database returns and is not guaranteed stable between passes | Deterministic safety ordering per `MP-002`. Until then the defect is worse than singular management: with two `OPEN` rows the agent may value one this minute and the other the next, giving each intermittent management, which is far harder to notice than consistently managing one |
| Unresolved state | `unresolved_position()` returns the first unresolved row | Return and classify the complete unresolved set |
| Clock result | One `TickResult` represents one action | Add a cycle/batch result with per-position outcomes |
| Entry guard | Any broker order or leg position blocks entry | Retain for now; later replace with a portfolio-admission token |
| Risk | Candidate-local maximum loss and buying power | Add open, pending, cluster, daily-loss, overlap, and count checks |
| Reconciliation | Compares each local strategy with aggregate broker symbols | Reconcile aggregate exposure first; prohibit overlap in the first release |
| Close preparation | Mutates `OPEN` to `CLOSING` without a versioned claim | Add compare-and-set or optimistic versioning |
| Fill identity | Deduplicates by order, symbol, quantity, and price | Store broker execution/activity identity when available |
| Worker lease | Heartbeats before a tick and during the wait loop | Prevent lease expiry during a long management batch; add fencing before writes |
| Dashboard | Shows counts and decision-centric position stories | Add position-scoped lineage and portfolio risk/health summaries |

### 3.3 Requirements already open

The requirements matrix already marks these as unfinished:

- `RISK-007`: total open defined risk;
- `RISK-008`: correlation-cluster risk;
- `RISK-009`: daily realized plus marked-loss stop;
- `RISK-010`: concurrent positions and pending risk;
- `RISK-012`: averaging down and unintended increases;
- `RISK-013`: fresh portfolio state before approval;
- `CLR-013`: validation and approval of portfolio limits.

These requirements are prerequisites to multi-position entry, not cleanup after it.

## 4. Target architecture

```text
                        one credentialed writer
                                  |
                                  v
                    reconcile broker account once
                                  |
                   +--------------+--------------+
                   |                             |
                   v                             v
          aggregate exposure map        working-order/deadline map
                   |                             |
                   +--------------+--------------+
                                  |
                                  v
               fetch one reusable snapshot per underlying
                                  |
                                  v
          evaluate every PENDING / OPEN / CLOSING / INCIDENT row
                                  |
                       +----------+----------+
                       |                     |
                       v                     v
             persist per-position     claim and submit all
             mark and decision        eligible risk reductions
                       |                     |
                       +----------+----------+
                                  |
                                  v
                    portfolio admission decision
                 (entry remains capped at one initially)
```

### 4.1 Position lifecycle treatment

| State | Management and risk treatment |
|---|---|
| `PENDING` | Reserve full approved maximum loss and one slot until terminal reconciliation |
| Partial entry fill | Count confirmed exposure and retain a reservation for the unfilled remainder until cancel is confirmed |
| `OPEN` | Value, observe, evaluate, and count actual filled exposure |
| `CLOSING` | Continue valuation and ownership; retain risk and slot until broker-flat reconciliation |
| `INCIDENT` | Treat exposure as unknown, globally halt new risk, and continue management of every other position |
| `ABANDONED` | Allocate no ordinary slot, but continue late-fill surveillance |
| `CLOSED` | Release risk only after authoritative broker-flat reconciliation |

### 4.2 Failure isolation

- An account-wide integrity failure sets global `NO_NEW_RISK`.
- A position-specific valuation or reconstruction failure opens a position-linked
  incident and must not suppress management of other positions.
- Risk reductions are evaluated before any new entry.
- All positions whose exit rules fire in the same cycle retain the opportunity to
  submit a close. The first result must not terminate the cycle.
- `FREEZE_ALL_WRITES` remains the only state that may block every mutation,
  including closes.

## 5. Work packages

### MP-001 — Shadow capacity evidence

**Purpose:** establish whether the entry cap blocks material, distinct opportunities.

While exposure exists, run a no-write candidate evaluation at the entry cadence and
persist:

- disposition `CAPACITY_BLOCKED`;
- completed-session signal cohort ID;
- existing-position IDs, direction, expiration, and contract overlap;
- proposed contracts, expiration, debit, and defined risk;
- duplication/correlation reason;
- policy, feed, data, and strategy versions;
- counterfactual outcome after the declared one- and three-session horizons.

One completed-session signal state is one cohort. Repeated intraday scans of the
same state are not independent opportunities.

**Acceptance:** the database can answer how many otherwise eligible cohorts were
blocked, how many were duplicates, and what incremental risk each required.

### MP-002 — Collection-based lifecycle API

Replace singular lifecycle selectors with explicit collections, for example:

```python
managed_positions() -> list[ManagedPosition]
unresolved_positions() -> list[ManagedPosition]
```

Ordering must be deterministic and safety-based, not database-return order:

1. integrity and expiry exposure;
2. active risk-reducing closes;
3. invalidation and stop-loss candidates;
4. time and profit exits;
5. pending entries;
6. possible new entry.

Keep a temporary singular adapter only if existing callers require a staged
migration. New code must not call it.

### MP-003 — Batch position management

- Reconcile once at the start of the cycle.
- Re-read the complete managed set after reconciliation.
- Fetch one snapshot per underlying; H0 therefore fetches one SPY snapshot.
- Record an observation and exit decision independently for every `OPEN` or
  `CLOSING` position.
- Persist and submit every eligible close independently.
- Return `ManagementCycleResult` containing per-position results, incidents,
  submissions, and reconciliation state.
- Measure full-cycle latency and the age of the mark used for each position.

The strategy and position clocks must not create new entries from this method.

### MP-004 — Aggregate reconciliation

Build an aggregate expected-exposure map:

```text
expected[symbol] = sum(signed filled quantity across owned strategies)
observed[symbol] = broker net quantity
```

Compare those maps before assigning findings to individual rows. Order and fill
lineage may then explain position-level responsibility.

For the first multi-entry release, reject a candidate if either option symbol is
already named by a `PENDING`, `OPEN`, `CLOSING`, or unresolved incident position.
Supporting overlapping symbols requires a separate lot-allocation design and is
out of scope for the bounded release.

### MP-005 — Atomic close ownership and attempts

- Claim `OPEN -> CLOSING` using a row lock, compare-and-set state transition, or
  optimistic version.
- Permit only one active close attempt per position.
- Give each legitimate close attempt a durable attempt ID/number.
- Retries of the same attempt reuse its deterministic client order ID.
- A new attempt after a reconciled terminal failure receives a new identity.
- A terminal close order that did not flatten the position returns responsibility
  to `OPEN` without releasing portfolio risk.

### MP-006 — Portfolio-risk ledger in shadow mode

Introduce either a `risk_reservations` table or an equivalent transactional ledger.
The portfolio view must expose:

- confirmed open defined risk;
- pending reserved risk;
- risk by underlying and cluster;
- daily realized P&L;
- conservative marked P&L;
- open, pending, closing, and incident counts;
- overlapping contracts and signal cohorts;
- calculation time, source time, and policy version.

Reserve the **approved** maximum loss, not a freshly recomputed quoted one. As
of 31 August 2026 `crossing_debit()` folds an execution allowance into the debit
*before* the risk governor sees it, so the approved figure already includes it
(signal spec section 7.1). A ledger that re-derives risk from `long.ask -
short.bid` would under-reserve every position by the allowance, and would do so
silently, since both numbers look like defensible debits.

Admission must be atomic:

```text
lock portfolio risk state
-> verify fresh broker/account reconciliation
-> calculate open plus pending risk
-> apply total, cluster, loss, count, cohort, and overlap gates
-> reserve candidate risk
-> persist intent, request, order, and PENDING position
-> commit
-> submit through the existing gateway
```

The gateway should eventually require an immutable portfolio-approval or reservation
reference. It must not infer authorization from `len(open_orders) + len(positions)`.

### MP-007 — Signal-cohort uniqueness

Add a stable cohort key that does not contain the intraday snapshot ID. For H0 it
must include at least:

- underlying;
- setup family;
- direction;
- completed-session date whose evidence changed;
- strategy-policy version.

Persist the key and reject a second risk-increasing intent from the same cohort.
Re-entry after an exit requires an explicit Trading/Risk rule and is forbidden until
that rule is approved.

### MP-008 — Lease fencing and fill identity

- Heartbeat independently while a management batch is executing, or prove the
  worst-case batch time cannot approach the lease TTL.
- Add a monotonic lease epoch/fencing token.
- Check current ownership and epoch immediately before durable mutations and broker
  writes.
- Persist Alpaca execution/activity identity for fills when available.
- Do not collapse two genuine same-price, same-quantity fills into one record.

### MP-009 — Operator and dashboard surfaces

Add:

- portfolio open plus reserved risk;
- SPY-cluster risk;
- position count by lifecycle state;
- one row per owned position with mark age, reconciliation age, next deadline,
  entry basis, current value, risk, exit state, and incident state;
- position-scoped intent/order/fill/observation/exit lineage;
- number and reasons for capacity-blocked cohorts;
- explicit `manage-many / enter-one` operating mode;
- unmanaged or unvalued-position alarm.

Remove copy that says remaining per-trade budget is unavailable merely because H0
has one slot. Replace it with the actual portfolio admission result.

## 6. Minimum acceptance matrix

| ID | Scenario | Required result |
|---|---|---|
| `MP-AC-01` | Two disjoint `OPEN` spreads; one stop fires and one holds | Both receive persisted marks and decisions; only the first closes |
| `MP-AC-02` | Two exits fire in the same cycle | Both close claims are attempted; neither result suppresses the other |
| `MP-AC-03` | One close submission fails | Incident is position-linked; other eligible close still proceeds |
| `MP-AC-04` | One `OPEN` position and one pending order | Exit evaluation and order deadline both run on time |
| `MP-AC-05` | Restart with multiple `PENDING`/`OPEN`/`CLOSING` rows | Every row is reconstructed before entry evaluation |
| `MP-AC-06` | Broker exposure differs from aggregate expected quantities | Global `NO_NEW_RISK`, durable incident, continued risk-reduction management |
| `MP-AC-07` | Candidate overlaps one active option symbol | Refused before reservation or broker submission |
| `MP-AC-08` | Two concurrent admission attempts | Atomic reservation prevents count or aggregate-risk oversubscription |
| `MP-AC-09` | Partial fill and cancel race | Filled exposure remains managed; remainder stays reserved until terminal |
| `MP-AC-10` | Late fill after abandonment, **with no live position naming those contracts** | Exposure is reinstated, incident recorded, new risk halted |
| `MP-AC-11` | Same completed-session cohort evaluated repeatedly | At most one risk-increasing intent is admitted |
| `MP-AC-12` | Two genuine fills share symbol, quantity, and price | Both remain distinct by broker execution identity |
| `MP-AC-13` | Lease expires during a long batch | Stale worker is fenced from further writes |
| `MP-AC-14` | One position cannot be valued | It raises an incident; other positions are still valued and managed |
| `MP-AC-15` | `NO_NEW_RISK` with several positions | Entries blocked; cancels and reconciled risk-reducing closes remain available |
| `MP-AC-16` | Dashboard selects a position | Only that position's complete lifecycle lineage is shown |

`MP-AC-10`'s qualifier is load-bearing and was added after 31 August 2026, when
the reconciler was changed so that live positions **claim** broker exposure
before a terminal one is judged against the residue. An abandoned position whose
legs are fully explained by a live position now correctly raises nothing, so the
obvious way to write this scenario — abandon a spread, leave the broker holding
those contracts — passes without exercising anything if another owned position
names the same symbols. Construct it with no live claimant. The existing
`test_a_genuine_late_fill_is_still_caught_with_no_live_position` in
`tests/test_reconcile.py` is the shape to follow.

## 7. Evidence gate for concurrent entry

The following values are research recommendations, not approved risk policy. They
must be pre-registered before examining results and may be revised only through an
explicit Trading/Risk decision.

Before authorizing a second position, collect enough shadow evidence to test the
hypothesis that the cap is material. A candidate gate is:

1. at least 30 distinct blocked signal cohorts across at least two declared regimes,
   with at least 10 cohorts in each;
2. at least 15% of otherwise eligible cohorts are blocked by capacity;
3. walk-forward cap-two improves net return per defined-risk-day under the same
   aggregate risk budget as cap-one;
4. the lower bound of a 95% block-bootstrap interval for incremental return per
   risk-day exceeds zero;
5. maximum drawdown and 95% expected shortfall remain inside a pre-approved relative
   tolerance;
6. results remain directionally consistent under conservative execution stress;
7. overlapping signal episodes, rather than raw position rows, are the bootstrap
   unit.

If contract indivisibility prevents two positions from fitting under the same total
risk budget, that demonstrates a capital-granularity constraint. It is not evidence
that total risk should be increased.

**What gate 1 costs in calendar time.** H0 evaluates one SPY trend/retest setup
per completed session, and `MP-007` makes one completed-session state one cohort,
so the maximum rate of cohort accumulation is **one per trading day** — and only
those days on which a cohort is both otherwise eligible *and* blocked by capacity
count toward the 30. On 31 August 2026 the live worker qualified on roughly one
session in one, but produced a position on one of nine intraday scans, so the
eligible-and-blocked rate is unknown and cannot be assumed high. Thirty blocked
cohorts across two declared regimes is therefore a **multi-month** collection at
best, and regime diversity may extend it further, since two regimes cannot be
manufactured on demand.

This dominates the schedule. Section 10 estimates 15-24 engineer-days, which is
the engineering only; the evidence gate is the larger half and is bounded by the
market rather than by staffing. Read the two together, or the delivery table
reads as a quarter of the true elapsed time.

## 8. Controlled cap-two Paper canary

Only after the management, risk, and evidence gates pass:

- maximum two `OPEN` strategies;
- maximum one `PENDING` entry;
- unique option contract symbols across strategies;
- unique completed-session cohort;
- all SPY positions assigned to one additive correlation cluster;
- no offset credit;
- no simultaneous opposing SPY strategies;
- no new entry while any position is `CLOSING` or `INCIDENT`;
- full pending risk reserved until terminal reconciliation;
- immediate rollback to cap one after any exposure-attribution, duplicate-order,
  oversubscription, deadline, lease, or restart defect.

Exercise at least 20 overlapping-position lifecycle episodes with zero ownership or
execution-integrity failures. This validates mechanics only; it does not validate
profitability.

## 9. Runtime and research cadence

| Process | Recommended cadence |
|---|---|
| Completed-session signal recalculation | After each completed daily session |
| Entry/capacity scan | Approximately every 15 minutes inside the approved entry window |
| Position valuation and exit evaluation | Every 60 seconds while exposure exists |
| Order/deadline monitoring | Every 5 seconds while a mutation is outstanding |
| Reconciliation | Startup, immediately around mutations, and at least every 60 seconds while exposure exists |
| Capacity-outcome enrichment | Nightly after the declared horizon is complete |
| Diagnostic review | Weekly, offline |
| Policy promotion | Offline only, after evidence and owner approval |

These cadences are responsibilities, not a demand for market-data streaming or
online strategy learning.

## 10. Delivery sequence and estimate

| Increment | Scope | Directional effort |
|---|---|---:|
| A | `MP-001` shadow capacity records | 1-3 engineer-days |
| B | `MP-002` to `MP-003`: manage many, enter one | 3-5 engineer-days |
| C | `MP-004` to `MP-005`: aggregate reconciliation and close ownership | 3-5 engineer-days |
| D | `MP-006` to `MP-008`: portfolio ledger, cohort guard, fencing and fill identity | 5-8 engineer-days |
| E | `MP-009`, acceptance matrix, deployment and operator proof | 3-5 engineer-days plus Paper sessions |

A safe bounded cap-two implementation is approximately **15-24 engineer-days**, plus
the calendar time required for Paper validation. General multi-underlying operation,
overlapping contract allocation, or horizontally partitioned workers is a separate
portfolio-system project, likely measured in multiple additional weeks.

## 11. Release gates

### Gate M1 — Manage-many correctness

- all `MP-AC-01` through `MP-AC-06`, `MP-AC-09`, `MP-AC-10`, `MP-AC-14`, and
  `MP-AC-15` pass;
- one entry remains enforced at the agent and gateway;
- every owned exposure has a recent observation or an open incident;
- restart reconstruction covers the full active set;
- full offline validation remains green.

### Gate M2 — Portfolio governor shadow correctness

- `MP-AC-07`, `MP-AC-08`, `MP-AC-11`, `MP-AC-12`, and `MP-AC-13` pass;
- open plus reserved risk reconciles across restarts and partial fills;
- no broker write depends on a UI, model, skill, scheduler, or raw broker count for
  authority;
- Trading/Risk approves total, cluster, daily-loss, count, and re-entry rules.

### Gate M3 — Cap-two Paper authorization

- the capacity evidence gate has a recorded disposition;
- all acceptance scenarios pass in a production-shaped database;
- monitoring and rollback are rehearsed;
- the operator approves the versioned policy;
- the deployed gateway defaults to cap one and requires an explicit versioned
  configuration change for cap two.

## 12. Rollback

The cap-two feature must be independently reversible without disabling position
management:

1. set admission capacity back to one;
2. halt new risk if the rollback was caused by an integrity incident;
3. do not automatically close existing positions merely because the cap decreased;
4. continue reconciling, valuing, and closing every owned position;
5. retain all reservations until their associated exposure or order is terminal;
6. record the rollback reason, policy version, operator, and time.

## 13. Ownership and unresolved decisions

| Decision | Final owner | Required before |
|---|---|---|
| Whether blocked opportunities justify cap two | Quantitative Strategy + Product | Gate M3 |
| Total open plus pending defined-risk cap | Trading/Risk | Gate M2 |
| SPY-cluster cap and whether opposing exposure receives any credit | Trading/Risk | Gate M2 |
| Daily realized plus marked-loss stop | Trading/Risk | Gate M2 |
| Re-entry after an exit from the same cohort | Trading/Risk | Gate M2 |
| Portfolio reservation and reconciliation implementation | Backend | Gate M2 |
| Lease fencing and deployment topology | Backend + DevOps | Gate M2 |
| Failure matrix and Paper proof | QA + Backend + Trading | Gate M3 |
| Portfolio operational UX and incident language | UX/UI + Backend | Gate M3 |

No numerical portfolio limit in an older design document is approved by this
handoff. In particular, the earlier three-position, 3% total-risk, and 1.5%
cluster-risk values remain hypotheses until the owners above approve evidence.

## 14. Developer start checklist

- [ ] Confirm the deployed worker is disarmed or otherwise safely bounded before
      lifecycle migrations or clock changes. **This is currently an active
      blocker, not a formality:** autonomous Paper entry was armed on 30 August
      2026 and the worker opened and is managing a live SPY vertical on
      31 August. Run `scripts/disarm_worker.sh` — which stops new risk while
      continuing to manage open exposure — and confirm the position is flat
      before changing any lifecycle selector or clock.
- [ ] Add tests that reproduce two simultaneous active positions before refactoring.
- [ ] Add the simultaneous identical-contract failure test, even though overlap will
      initially be rejected.
- [ ] Implement `MP-001` without write authority.
- [ ] Replace singular position selection with deterministic collections.
- [ ] Add batch results and position-specific failure isolation.
- [ ] Preserve reconcile-before-manage and exits-before-entry.
- [ ] Preserve persistence-before-mutation and reconciliation-after-mutation.
- [ ] Keep entry capacity at one through Gate M1.
- [ ] Review migrations against a production-shaped PostgreSQL backup.
- [ ] Run the focused lifecycle, reconciliation, deadline, worker, gateway, dashboard,
      and reporting suites.
- [ ] Run the complete offline validation script.
- [ ] Rehearse restart, lease loss, rollback, and two simultaneous exit triggers.
- [ ] Update the traceability matrix only with observed evidence; do not mark
      portfolio requirements complete from unit tests alone.

## 15. Handoff conclusion

Scaling safely is not a change from `> 0` to `>= N`. The current database and
single-writer model are useful foundations, but multi-position control requires
collection-based management, aggregate reconciliation, atomic risk reservation,
signal-cohort uniqueness, failure isolation, lease fencing, portfolio observability,
and evidence that additional capacity solves a real problem.

The approved implementation direction is **manage many, enter one**. Cap two is a
later, reversible Paper experiment behind explicit Trading/Risk and evidence gates.
