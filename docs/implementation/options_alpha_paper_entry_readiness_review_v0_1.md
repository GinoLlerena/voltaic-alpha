# Options Alpha — Paper entry readiness review v0.1

| Field | Value |
|---|---|
| Date | 7 October 2026, America/Lima |
| Reviewed revision | `b713dbc` |
| Requested by | Owner, 7 October 2026: "complete the readiness review and, if all checks pass, enable Paper trading with the current entry rules and breadth veto unchanged" |
| Scope | Re-arming autonomous **Paper** entry on the consolidated host. Entry rules, the breadth veto and every threshold are unchanged. |
| Verdict | **Not yet. One blocking defect (R-1) and one hardening item (R-2) first; then one owner decision (R-4). The lifecycle machinery passes.** |
| Work prefix | `PER-` |

## 1. Background

Autonomous Paper entry was armed on 30 August 2026 (`EV-028`) and re-armed on
1 September (`EV-041`), on a separate worker host. The broker's last order is a
filled multi-leg order dated **3 September 2026**. On 10 September the worker
moved to the consolidated host and has run there in `observe` mode with order
writes disabled ever since. This review is therefore of a re-arming, on a host
and a code base that have both changed.

Two independent things explain "no orders since 3 September":

1. The worker cannot write: `--mode observe`, `ALPACA_TRADING_ENABLED=false`.
2. No setup qualified anyway. Over the 14 sessions with recorded structure
   readings (17 September to 6 October) the structure requirement was met on six
   (22, 23, 24, 25, 28 September and 6 October), and all six were vetoed by the
   bearish breadth signal. On 5 October the structure gate passed but the
   structure signal's strength was 0.59 against a 0.60 minimum, so that day
   failed before the veto was evaluated.

## 2. The acceptance matrix

The project's own gate is `EXIT-AC-01` to `EXIT-AC-16`
([exit policy review](options_alpha_exit_policy_review_v0_1.md) §6). Each row
below names the evidence run for this review. "Tests" were run on 7 October 2026
at `b713dbc`: 326 tests in 15 suites on SQLite, and the 122 tests of the five
engine-switching suites again on PostgreSQL 16. All passed.

| ID | Requirement (short) | Evidence | Result |
|---|---|---|---|
| AC-01 | Accepted-but-unfilled entry stays pending | `test_lifecycle_store` AcceptanceIsNotFill, TerminalEntry | Pass |
| AC-02 | Partial and complete fills reconcile exactly | `test_lifecycle_store` (`only_reconciled_fills…`, `a_partial_fill…`), `test_deadline` PartialFill | Pass |
| AC-03 | Unfilled and partial close never reports flat | `test_close_responsibility` (7), `test_lifecycle_store` CloseResponsibility | Pass |
| AC-04 | Restart with open, pending, partial and flat states | `test_reconcile` StartupRecovery, `test_worker` (`a_restart_resumes…`), `test_lifecycle_e2e` (`full_lifecycle_survives_a_restart…`) | Pass |
| AC-05 | Mismatch and unexpected exposure halt new risk | `test_reconcile` Mismatch, LegQuantity; `test_lifecycle_e2e` (`unexpected_broker_exposure…`) | Pass |
| AC-06 | Typed bullish and bearish invalidation | `test_exits` InvalidationSource, `test_agent` InvalidationSource | Pass |
| AC-07 | Session time stop across weekends and holidays | `test_calendar` SessionStopAcrossAHoliday, SessionCounting | Pass |
| AC-08 | Missing, stale, crossed, one-sided quotes | `test_exits` Unmeasurable, `test_learning_capture` | Pass |
| AC-09 | Trigger precedence matrix | `test_exits` Precedence | Pass |
| AC-10 | Bounded close replacement, ambiguous responses | `test_close_responsibility` FailedClose, `test_deadline` CancelFailure, `test_lifecycle_e2e` (`the_same_approved_intent_cannot_be_prepared_twice`) | Pass |
| AC-11 | Expiry, early close, assignment-risk calendar | `test_exits` (`expiry_guard…`), `test_calendar` EarlyClose | Pass |
| AC-12 | Threshold replay and sensitivity report | `test_sensitivity` (13); `artifacts/threshold_sensitivity.md` | **Provisional.** Decision sensitivity exists; outcome evidence does not. See R-4. |
| AC-13 | End-to-end autonomous Paper lifecycle | `test_lifecycle_e2e` with a scripted broker (5). Real Paper: one round trip on the *previous* host, last fill 3 September. | **Pass in controlled tests; no real round trip on this host.** See R-5. |
| AC-14 | Unfilled, rejected, canceled, expired, late-filled, partial entries | `test_deadline` (13), `test_lifecycle_store` TerminalEntry, `test_reconcile` ReentryOnTheSameContracts | Pass |
| AC-15 | Entry window: normal, final minute, early close, holiday | `test_calendar` NormalSession, EarlyClose, NonTradingDay; `test_agent` EntryWindow | Pass |
| AC-16 | Credentialed worker deployment and forced restart | §3 below | Pass, with R-1 and R-5 |

Also run: `test_execution_firewall` (26: Paper-only endpoint, write authority,
approval token), `test_task1_acceptance` (18: manage many, enter one),
`test_bounded_model` (29: the model cannot change direction, size or
invalidation), `test_rehearsal` (16), and the rehearsal itself, which drove the
real `tick()` over the committed snapshots with deterministic decision hashes
and no write authority.

## 3. The environment, read on 7 October 2026 (read-only)

| Check | Observed | Result |
|---|---|---|
| Broker endpoint | `https://paper-api.alpaca.markets` | Paper |
| Broker account | `ACTIVE`; trading and account not blocked; equity 100,044.52; options level 3 | Pass |
| Broker exposure | 0 positions, 0 open orders; last order filled 3 September | Flat |
| Local execution tables | 0 intents, 0 broker orders, 0 positions, 0 open incidents | Flat; agrees with the broker |
| Credentials file | `/etc/options-alpha.env`, mode 600, root | Pass |
| Flags | `ALPACA_PAPER_TRADE=true`, `ALPACA_TRADING_ENABLED=false`, `REQUIRE_OPERATOR_APPROVAL=true`, `BOT_MODE=observe` | As expected before arming |
| Who loads the credentials | worker and watchdog only. The public API and the dashboard load `/etc/options-alpha-dashboard.env` (a SELECT-only database role) | Pass (`EXIT-AC-16`: dashboard credential-free) |
| Worker | `--mode observe`, no drop-in, lease held, steady | As expected |
| Model | `gpt-5.6-terra` reachable with the host's key (metadata request, no completion). Never called on this host: 0 model calls | Pass |
| Backup and alerting | Hourly verified backups, daily and weekly encrypted copies off-host, watchdog, scheduler alerts by email | Pass. This was the missing precondition on 30 August. |
| Reviews | Review clock fixed on 6 October (`#80`); backlog resolved | Pass |

## 4. Findings

### PER-R-1 — Blocking: holding a position overnight floods the alert channel

`scheduler.decide` treats every "not ready to stop" as an alert, and the
function emits one alert event per tick with no de-duplication. Stop-readiness
correctly refuses to stop while a position is open or an order is working. The
strategy holds for up to three sessions. So one held position produces an alert
every 15 minutes outside market hours: about 60 a night, several hundred over a
weekend, each one saying the system is doing what it should.

That is worse than noise. It trains the owner to ignore the channel that also
carries "server did not start" and "tick failed".

**Required before arming.** Holding exposure is a reason to stay up, not an
alert: `decide` returns "holding: N open position(s)" with no alert when the
only reasons are open positions or working orders. Other reasons while flat
(backup not verified, copy not off-host) still alert as now. Needs tests, a
function redeploy (`provision_scheduler.py apply`), and a check that the decision
log shows the new reason.

### PER-R-2 — Hardening: the arm and disarm scripts predate current rules

`scripts/arm_worker.sh` and `disarm_worker.sh` call `aliyun` directly and let
its stderr through; the CLI echoes the AccessKey ID on failure, which is why
every other operator script goes through the redacting layer. They are also not
window-aware (arming restarts the worker at any hour), and the disarm message
says the worker returns to `recommend` when the base unit is `observe`.

**Required before arming:** route both through the redacting layer or discard
stderr; refuse to arm inside the trading day unless told to; correct the text.
The mechanism itself (a systemd drop-in plus one flag, verified afterwards) is
sound and stays.

### PER-R-3 — Cost while holding

The server does not stop while a position is open, by design. A day spent
holding costs about $0.72 instead of about $0.47 (24 hours of compute at
$0.0178, plus the fixed $0.29), and a held weekend day about $0.72 instead of
$0.29. With positions held about a third of the time the month moves from about
$12.90 to roughly $15–16. No action; recorded so the bill is not a surprise.

### PER-R-4 — Owner decision: thresholds are still provisional (`DEC-008`)

`DEC-008` is open and cannot be closed by review: its missing evidence is
outcomes, and outcomes need trades. Every exit threshold in `exits.py` and every
entry threshold in `components.py` and `evidence.py` is labelled `PROVISIONAL`.
The project's rule is that arming does not mean these are approved.

Arming is therefore an explicit owner decision to collect Paper evidence with
provisional thresholds, as it was on 30 August, now with backup and alerting in
place. Any result is evidence that the mechanism runs, not that the thresholds
are right. The owner has said the rules and the veto stay unchanged; this review
asks only that the provisional status be acknowledged.

### PER-R-5 — Evidence gap: no real Paper round trip on this host

Controlled tests cover the lifecycle with scripted brokers, including restart,
partial fills, late fills and mismatches. They do not cover this host talking to
the real Paper API on today's code: the last real fill was on the previous host.
No setup qualifies today, and the owner has ruled out loosening the veto to
produce one, so this cannot be exercised on demand.

The first real trade is the test. Until it has completed a full round trip:

- arm with the existing bounds only (Paper, SPY, one position, one contract
  structure, the 09:45–15:15 ET window, the 90/120-second order deadlines, the
  per-trade risk budget);
- verify at arming: `may_write_orders` true, the resolved endpoint is Paper,
  startup reconciliation clean, one lease;
- force one worker restart after arming and confirm reconciliation is clean;
- when the first entry is submitted, follow it on the Positions screen through
  fill, marks, exit evaluation and close, and compare the realised result with
  the broker's.

### PER-R-6 — Notes

- The Paper account receives the indicative option feed, not OPRA. Fills are a
  Paper approximation.
- The watchdog unit loads the full credentials file although it needs only the
  database. Not a blocker; worth narrowing.
- The model memo has never run on this host: the first qualified setup is also
  its first live call. The memo is advisory by design and `test_bounded_model`
  holds it to that, but how a live model failure reads on this host is
  unobserved until it happens.

## 4a. Progress

| Item | Status |
|---|---|
| PER-R-1 | **Fixed in code, 7 October 2026.** `scheduler.decide` returns "holding N open position(s); the server stays up" with no alert when exposure is held and no incident is open; an unresolved incident still alerts; a refusal with no exposure alerts as before. The handler passes the counts from stop-readiness. Eight tests (`HoldingExposureTests`). The alert rule sends one email per event (`Period 15`), so the old behaviour was about sixty emails a night per held position. **Takes effect only after the function is redeployed** (`python3 scripts/provision_scheduler.py apply`). |
| PER-R-2 | Open. |
| PER-R-4 | Asked on 7 October 2026 whether the provisional status of the thresholds is accepted, the owner replied "proceed". Recorded as that reply, to be confirmed in words at arming. |
| PER-R-5 | Applies at and after arming. |

## 5. Order of work

1. Fix PER-R-1 (scheduler: holding is not an alert), with tests; redeploy the function.
2. Fix PER-R-2 (arm and disarm scripts).
3. Owner acknowledges PER-R-4.
4. Arm outside the trading day with `scripts/arm_worker.sh`; verify as in PER-R-5; force one restart.
5. Record the arming as an evidence row, and follow the first trade end to end.

Disarming is `scripts/disarm_worker.sh` at any time; it removes the drop-in and
sets `ALPACA_TRADING_ENABLED=false`, and closes remain permitted in every mode.
