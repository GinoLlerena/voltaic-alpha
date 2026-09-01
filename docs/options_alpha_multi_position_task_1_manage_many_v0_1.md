# Options Alpha Agent

## Multi-Position Task 1 — Manage Many, Enter One

*Immediate safety implementation for the current SPY Paper worker. This task does
not authorize concurrent entry.*

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Date | 31 August 2026 |
| Status | **Implemented 31 August 2026**; not yet deployed (see section 7) |
| Target | Current hackathon runtime |
| Directional effort | 3-5 engineer-days |
| Required entry capacity after delivery | One open or pending strategy |
| Master handoff | [Multi-Position Scaling Handoff](./options_alpha_multi_position_scaling_handoff_v0_1.md) |
| Deferred task | [Task 2 — Portfolio Evidence and Cap Two](./options_alpha_multi_position_task_2_portfolio_entry_v0_1.md) |

## 1. Outcome

The worker shall reconcile the complete active set, value every uniquely
attributable `OPEN` or `CLOSING` position, persist every applicable management
decision, and execute all eligible risk reductions without allowing one position's
result to terminate the cycle.

The entry policy remains exactly one open or pending strategy. The gateway's
current guard stays enabled. Task 1 improves responsibility for exposure; it does
not increase intended risk.

## 2. Why this is a current requirement

Multiple exposures can exist even when the bot intends to enter only one strategy:

- a cancel can lose a race with a late fill;
- a partial close can leave exposure;
- an operator can intervene at the broker;
- an abandoned and a later order can name the same contracts;
- a restart can discover exposure created before the current process.

The store and reconciler already use collections, but `tick()`, `position_clock()`,
`active_position()`, and `unresolved_position()` select one row. Because
`active_positions()` has no `ORDER BY`, even that selected row is not a guaranteed
stable choice.

### 2.1 What the current code actually does with two live rows

Measured against the reconciler as it stands on 31 August 2026, not inferred.
Two `OPEN` rows naming the same contracts produce two different wrong answers:

| Broker state | Today's result |
|---|---|
| `+2/-2` — both lots live, the correct aggregate | `leg_imbalance` raised against the **first** row, which goes to `INCIDENT` and halts new risk. A healthy pair is reported as broken, because one local row is compared against the aggregate broker quantity |
| `+1/-1` — one lot genuinely closed | The first row silently claims the survivor; the second is declared `position_vanished` and goes to `INCIDENT` |

In the second case the system decides which local lot survived, and it decides
by unordered database return order, so the same inputs can produce a different
answer on a different pass. `T1-05` is therefore not hardening against a future
possibility. It replaces behaviour that is wrong now.

## 3. Binding scope

### 3.1 Included now

- deterministic collection-based position selection;
- one reconciliation pass per management cycle;
- one reusable SPY snapshot per cycle;
- an observation and management result for every attributable position;
- independent submission of every eligible risk-reducing close;
- independent per-position error handling;
- complete unresolved-position reporting;
- detection and fail-closed disposition of overlapping live option symbols;
- minimal batch health and unmanaged/unvalued-position alarms;
- restart, deadline, incident, and simultaneous-exit tests;
- deployment with the one-entry guard unchanged.

### 3.2 Explicitly deferred

- any increase to the open or pending entry count;
- portfolio-risk reservations or admission tokens;
- total-risk, cluster-risk, or daily-loss percentage policy;
- stable signal-cohort identity and blocked-opportunity research;
- automatic allocation between overlapping local lots;
- broker execution/activity IDs and general fill-ledger redesign;
- lease epochs or horizontally partitioned workers;
- general multi-underlying management;
- the full portfolio dashboard.

Task 1 must measure batch duration against the existing lease TTL. If the measured
margin is unsafe, stop and move independent heartbeating/fencing forward from Task
2; do not hide the result by increasing the TTL without analysis.

## 4. Safety invariants

1. Entries remain capped at one in both the agent and gateway.
2. Reconciliation runs before position management.
3. All position evaluations complete before a possible entry is considered.
4. Every position observation is persisted before its management decision.
5. Every close reason and order are persisted before broker submission.
6. A submitted close is not a closed position; responsibility remains until the
   broker confirms the relevant exposure is flat.
7. One position's provider, pricing, reconstruction, persistence, or broker failure
   does not suppress management of another position.
8. `NO_NEW_RISK` continues to permit ordinary risk-reducing closes and cancels.
9. Ambiguous overlapping broker quantities are never assigned to a guessed local
   lot.
10. A position in `INCIDENT` is never silently treated as flat.

## 5. Implementation design

### T1-01 — Collection API and deterministic base order

Add collection-based reads and migrate new callers away from singular helpers:

```python
managed_positions() -> list[ManagedPosition]
unresolved_positions() -> list[ManagedPosition]
```

The repository query must have a stable base order, such as `recorded_at, id`.
Safety priority is then decided explicitly by the agent, not by physical database
order.

Retain temporary singular adapters only for callers that cannot migrate in the
same change. Add a test that creates rows in a different order and proves the
management outcome does not depend on database return order.

### T1-02 — Two-phase management cycle

Replace the singular early return with two phases:

1. **Evaluate:** reconcile once, re-read the complete set, fetch one SPY snapshot,
   and persist a result for every attributable position.
2. **Act:** order risk-reducing candidates deterministically and submit each
   independently.

Close priority is:

1. integrity/expiry safety;
2. structural invalidation;
3. stop loss;
4. session stop;
5. profit capture;
6. stable position ID as the final tie-breaker.

This ordering is not new. It is `PRECEDENCE` in `options_alpha_lab.exits`,
which already carries exactly these five triggers in exactly this order and has
a test asserting it. **Import it; do not restate it.** A second copy of exit
precedence is a second thing to keep in step, and the watchdog shipped on
31 August did precisely that with the worker lease name, guessed it wrong, and
reported a healthy lease-holder as having no lease. Position ID remains the
final tie-breaker and is the only part `PRECEDENCE` does not supply.

Do not stop after the first `HOLD`, working close, incident, refusal, or submitted
close.

### T1-03 — Batch result

Introduce a result shaped for several positions, for example:

```python
@dataclass(frozen=True)
class PositionManagementResult:
    position_id: str
    action: str
    detail: str
    submitted_order_id: str | None = None
    incident_id: str | None = None

@dataclass(frozen=True)
class ManagementCycleResult:
    at: datetime
    reconciliation_summary: str
    positions_seen: int
    positions_valued: int
    results: tuple[PositionManagementResult, ...]
    elapsed_ms: int
```

Names may change, but the worker and health output must retain every per-position
outcome. A single `last_action` cannot be the only evidence of a multi-position
cycle.

### T1-04 — State-specific behavior

| State | Task 1 behavior |
|---|---|
| `PENDING` | Reconcile and enforce the order deadline; do not evaluate an exit without confirmed exposure |
| `OPEN` | Persist a mark, evaluate every exit rule, and act if a close is authorized |
| `CLOSING` | Persist a mark and report the working close; do not submit another close |
| `INCIDENT` healed by reconciliation | Manage under the resulting `OPEN` or `CLOSING` state in the same cycle |
| `INCIDENT` with confirmed or possible exposure that cannot be healed | Keep `NO_NEW_RISK`; record which inputs/rules remain decidable; do not call it flat; invoke the operator recovery path |
| `ABANDONED` | Continue late-fill surveillance through reconciliation/deadline logic |
| `CLOSED` | Exclude from active management |

### T1-05 — Inherited overlapping-contract disposition

Build the symbol-ownership map for all unresolved local rows **before any
per-position judgement is made**. Ordering matters here more than it looks.

The reconciler already consumes broker exposure position by position: live rows
are settled first and their expected exposure is deducted, so a terminal row
sees only the residue. That was added on 31 August to stop an abandoned entry
being blamed for a live position's legs, and it is correct for the
terminal-versus-live case. It is **wrong** for two live rows, because consuming
in sequence silently attributes exposure to whichever row is settled first —
which is exactly the decision point 5 below forbids, taken before any overlap
check would run.

So detection cannot simply be added alongside the existing path. For any symbol
with more than one live or possibly live claimant, the consume-and-compare path
must be skipped entirely and the aggregate comparison used instead. An
implementer who adds overlap detection after the per-row loop will find the
mis-attribution has already happened.

If more than one live or possibly live local strategy claims the same option
symbol:

1. compare aggregate expected signed quantity with broker net quantity;
2. retain responsibility for the aggregate exposure;
3. set global `NO_NEW_RISK` and record one deduplicated durable incident;
4. continue managing every disjoint, attributable position;
5. do not decide which local lot a broker quantity belongs to;
6. do not automatically submit a lot-specific close while attribution is
   ambiguous;
7. expose the affected positions, symbols, expected quantity, observed quantity,
   orders, and fills to the operator;
8. resolve the incident only after an operator-approved action and broker/local
   reconciliation establish an unambiguous state.

This is a recovery path, not support for creating overlapping strategies. Task 2
will reject a new candidate before reservation if either leg overlaps unresolved
exposure.

### T1-06 — Minimal operational output

Extend worker health/reporting with:

- positions seen and valued in the last cycle;
- per-position action counts;
- oldest mark age;
- unresolved or unvalued position count;
- overlapping-symbol incident count;
- management batch duration;
- number of close attempts and failures.

Do not build the full portfolio-risk dashboard in this task.

## 6. Acceptance tests

| ID | Scenario | Required result |
|---|---|---|
| `T1-AC-01` | Two disjoint open spreads; one stop fires and one holds | Both are marked and evaluated; only the stop-triggered position closes |
| `T1-AC-02` | Two exits fire in the same cycle | Both close claims are processed; neither suppresses the other |
| `T1-AC-03` | First close submission fails | Its incident is position-linked; the second close still proceeds |
| `T1-AC-04` | One open position and one pending order | Exit evaluation and deadline enforcement both run on their declared cadence |
| `T1-AC-05` | Restart with multiple pending/open/closing rows | Every row is reconciled before entry evaluation |
| `T1-AC-06` | Rows are returned in different database order | The same deterministic evaluations and close priority result |
| `T1-AC-07` | One position cannot be valued | It raises an incident; other positions remain managed |
| `T1-AC-08` | `NO_NEW_RISK` with several positions | Entry is refused; eligible closes and cancels remain permitted |
| `T1-AC-09` | Two active local rows share a symbol, broker holds the correct aggregate | Aggregate exposure remains owned, new risk halts, disjoint positions continue, and **neither overlapping row changes lifecycle state on the basis of attribution** — today both failures in section 2.1 are exactly such a state change, so asserting the negative is what makes this test bite |
| `T1-AC-09b` | Two active local rows share a symbol, broker holds one lot fewer | The shortfall is reported against the aggregate; no row is declared vanished and no row is declared the survivor |
| `T1-AC-10` | Late fill with no live claimant | Exposure is reinstated, incident recorded, and new risk halted |
| `T1-AC-11` | Unresolved incident may represent exposure | It is never reported flat or silently omitted from cycle health |
| `T1-AC-12` | Multiple positions exist after Task 1 deployment | Agent and gateway still refuse a second risk-increasing entry |
| `T1-AC-13` | Worst-case tested management batch | Duration stays at or under **30 seconds**, one third of the 90-second `LEASE_TTL`. Measured baseline on 31 August 2026: one position-clock pass takes about 6 seconds including its chain fetch, and the wait loop heartbeats every 20 seconds but **nothing heartbeats during a batch**, which is what the margin is protecting |

These exist as `tests/test_task1_acceptance.py`, written before the
implementation as section 14 of the master handoff asks. Ten carry
`pytest.mark.xfail(strict=True)` and ten fail today; the marker keeps the suite
green now and turns the arrival of the behaviour into an `XPASS(strict)`
failure, which is a demand to delete the marker rather than a pass nobody
notices.

Four already pass and are pinned so Task 1 cannot regress them while
rearranging everything around them: `T1-AC-05` (reconciliation already
reconstructs the whole active set, pending rows included), `T1-AC-08`
(`NO_NEW_RISK` permits a close; only `FREEZE_ALL_WRITES` blocks one),
`T1-AC-10` (a late fill with no live claimant is still caught) and `T1-AC-12`
(the gateway refuses a second entry, stating the cap itself rather than letting
the caller infer it).

The two overlap tests fail on **behaviour**, not on a missing API: today
`T1-AC-09` gets `INCIDENT` where it requires `OPEN`, and `T1-AC-09b` finds the
`position_vanished` it forbids. The other eight fail on
`TradingAgent.manage_positions` and `TradingAgent.managed_positions` not
existing, which names the two entry points `T1-01` and `T1-02` must add.

## 7. Deployment and rollback

Before deployment:

1. verify current broker exposure and deployed worker authority;
2. if the worker is armed, disarm new entries with `scripts/disarm_worker.sh`;
3. confirm broker/local reconciliation and that no exposure remains. There is
   no automated flattening procedure and this document does not invent one: the
   options are to let the position reach its own exit under the existing policy,
   or for the operator to close it manually at the broker and let the next
   reconciliation pass record the result. Closing by hand mid-thesis discards
   the completed-lifecycle evidence that position was producing, so prefer
   waiting unless something is actually wrong;
4. run focused agent, lifecycle, reconciliation, deadline, worker, gateway, health,
   and reporting tests;
5. run the complete offline validation suite;
6. deploy with entry capacity fixed at one;
7. force a worker restart and verify the full active set is reconstructed.

Rollback restores the prior singular orchestration only if the broker is flat.
If any position exists, stop new risk and preserve the multi-position manager or an
operator-owned management process until exposure is reconciled and flat. Never
rollback by abandoning a position that only the new code knows how to manage.

## 8. Definition of done

Task 1 is complete only when:

- all `T1-AC-*` tests pass against SQLite and production-shaped PostgreSQL where
  locking/order behavior matters;
- every uniquely attributable active position receives a timely persisted mark or
  an explicit incident;
- ambiguous overlap has the declared fail-closed/operator disposition;
- the worker reports batch and per-position health;
- restart evidence covers more than one active row;
- the one-entry cap remains proven at both authority layers;
- no portfolio-limit or multi-entry requirement is marked complete;
- deployed Paper smoke and rollback evidence are recorded.

## 9. Handoff to Task 2

Task 1 produces a safe plural manager, not a portfolio trader. Task 2 may begin
after the hackathon from this boundary, but cap two remains disabled until its
portfolio governor, shadow evidence, and promotion gates pass.
