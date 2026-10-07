# Options Alpha — PUI Phase 4: Positions and Review read models

| Field | Value |
|---|---|
| Date | 6 October 2026, America/Lima |
| Status | **Approved by the owner on 6 October 2026, all six decisions as recommended (§8).** Implementation follows §7; nothing was built when this was approved. |
| Implements | [Personal UI redesign](options_alpha_personal_ui_redesign_v0_1.md) §9 Phase 4, §7 (Positions, Review) |
| Reviewed revision | `500a4c7` |
| Work prefix | `PUI4-` |
| Boundary | GET-only presentation API; Paper only; no notes, no controls, no new write path |

## 1. What is being decided

Phase 4's rule is: *agree and test the missing read models before building the
corresponding screens.* This document proposes those read models: what a
Positions screen and a Review screen may show, where each value comes from, and
what must be shown as unavailable. It ends with six decisions for the owner
(§8). No screen is built until those are answered.

## 2. What the records hold today

Measured on 6 October 2026, read-only.

| Record | Live worker database | Committed evidence |
|---|---:|---:|
| Decisions | 1,045, all `NO_TRADE` | 5 (4 positions, 1 refusal) |
| Positions, any state | **0** | 1 (`CLOSED`) |
| Position observations (marks) | 0 | 0 |
| Exit evaluations | 0 | 0 |
| Review jobs | 160 complete, 1,930 pending | present |
| Decisions reviewed / distinct closes behind all decisions | 136 / 18 | — |
| Incidents | 10, all resolved | — |

Two consequences shape the proposal:

1. **The live Positions screen will be empty**, and stay empty while the bot is
   in observe mode. It must say so truthfully ("No position has ever been
   opened in this source"), and it can only be exercised against fixtures and
   the one committed lifecycle until Paper entries are enabled.
2. **The live Review screen has real content now**, but all of it is research:
   what the underlying did after refusals. None of it measures trading. The
   existing review caveat already says this, and the screen must lead with it.

## 3. Positions read model

### 3.1 What exists

`positions` already records everything §7 of the redesign asks for except
valuation: a stable id, the decision it came from, strategy, direction, the six
lifecycle states, both legs, expiry, width, requested and filled quantity,
reconciled entry debit, open risk, typed invalidation, and open/close times with
a close reason. `position_observations` records each mark an exit decision was
made on; `exit_decisions` records every exit evaluation, including holds;
`incidents.position_id` links an incident to a position.

Today these are served only per decision (`/decisions/{digest}/lifecycle`). There
is no cross-decision view, which is the gap.

### 3.2 Proposed endpoints (additive, GET-only)

| Endpoint | Returns |
|---|---|
| `GET /api/v1/positions?state=open\|closed\|all&cursor=` | A page of position summaries, newest first, with a `total` per filter |
| `GET /api/v1/positions/{position_id}` | One position: summary, entry and exit economics, latest mark, exit evaluations, linked incidents |
| `GET /api/v1/positions/{position_id}/observations?cursor=` | The position's recorded marks, newest first, paged |

`open` means `PENDING`, `OPEN`, `CLOSING` or `INCIDENT`: every state in which
exposure may exist or is unconfirmed. `closed` means `CLOSED` or `ABANDONED`.

### 3.3 Fields and their sources

| Field | Source | When unavailable |
|---|---|---|
| `position_id` | `positions.id` | never |
| `decision_id` | the owning decision's hash; links to the decision page | never |
| `instrument` | the decision's market snapshot symbol | "not recorded" |
| `strategy`, `direction` | `positions` | never |
| `state` | `positions.lifecycle_status`, one of six | never |
| `state_meaning` | a served sentence per state (§3.4) | never |
| `legs` | long/short contract symbols, expiry, width | never |
| `requested_quantity`, `filled_quantity` | `positions`; shown side by side | never; `filled 0 of 1` is a fact |
| `entry_debit` | `avg_entry_debit`, **per share** | `null` until fills reconcile: "not yet reconciled", never the estimate |
| `open_risk` | `positions.open_risk`, **USD, whole structure** | never |
| `invalidation` | level, direction, source | "none recorded" |
| `opened_at`, `entry_filled_at`, `closed_at`, `close_reason` | `positions` | `null` shown as "—" with the state explaining why |
| `latest_mark` | newest `position_observations` row: `observed_at`, provider `source_time`, `spread_value`, `underlying_price`, price source | see §3.5 |
| `unrealized` | newest `exit_decisions.unrealized` (already computed by the exit logic) | `null`: "not measurable on this mark" |
| `latest_exit_evaluation` | trigger, `should_close`, reason, disposition | "never evaluated" |
| `realized` | `outcomes.realized_from_fills`: both sides from reconciled broker fills | `null` unless entry **and** close are filled; a half round trip has no result |
| `open_incidents` | `incidents` where `position_id` matches and unresolved | `0` is a verified zero |

The browser computes none of these. In particular it never multiplies a debit by
100 or derives a P&L; `unrealized` and `realized` are server values or absent.

### 3.4 The six states, in words

Served by the API so the page and any other surface say the same thing.

| State | Meaning shown |
|---|---|
| `PENDING` | Entry submitted; no confirmed fill. Exposure is unknown, not zero. |
| `OPEN` | Reconciled fills establish this exposure. |
| `CLOSING` | A close was submitted; the broker has not confirmed flat. |
| `CLOSED` | The broker confirms flat. |
| `ABANDONED` | The entry ended without a fill. There was never exposure. |
| `INCIDENT` | Local records and the broker disagree. Treat exposure as unknown. |

### 3.5 Mark freshness (the one new rule)

A mark is a recorded observation, not a live price. The read model classifies
the newest one, and the rule is explicit and tested:

| `mark_state` | Rule |
|---|---|
| `never_observed` | no observation row exists |
| `unreadable` | newest row has `spread_value` null (a recorded fact, not a zero) |
| `current` | newest row is younger than 5 minutes **and** the market session is open |
| `last_session` | the market is closed; the row is the last one of the latest session |
| `stale` | the session is open and the row is older than 5 minutes |

| `final` | the position is `CLOSED` or `ABANDONED`: it is no longer marked, so its last mark is the last one, not a stale one (added in step 1; the approved table had omitted closed positions) |

Five minutes is five missed cycles of the worker's 60-second position clock.
`stale` on an open position is attention, and appears in Today's attention list
(a new, tested attention rule, as the redesign requires for any such rule).

### 3.6 Deliberately absent

Live or streaming marks, Greeks, payoff diagrams, OHLC charts, account equity or
performance, per-leg P&L, and any figure not reproducible from a stored row.

## 4. Review read model

### 4.1 What exists

`GET /api/v1/outcomes` already serves per-horizon **counts** (resolved, pending,
trades, refusals, agreed, disagreed, unanswerable, with a realised result, the
smallest and largest move) and a caveat sentence derived from those counts. Each
decision page shows its own horizons. There is no way to browse the reviewed
decisions themselves.

### 4.2 Two sections that never mix

The redesign requires realised outcomes "clearly separated from research". The
proposal makes them separate endpoints and separate page sections, each with its
own sample count.

**A. Execution outcomes** — closed positions only.

`GET /api/v1/review/executions?cursor=` — one row per position in `CLOSED`:
decision link, instrument, strategy, direction, filled quantity, entry debit,
close price, `realized` (from reconciled fills), holding time, close reason, and
the exit trigger that governed the close. Positions in `ABANDONED` are listed
separately as "entered no exposure", never as a zero result.

Live today this is empty: "No position has been closed in this source, so there
is no execution outcome to review."

**B. Research horizons** — what the underlying did afterwards.

`GET /api/v1/review/sessions?horizon=T%2B1&cursor=` — **one row per market
session**, not per decision (§4.3): session date, the completed close the
decisions read, how many decisions were taken on it, their verdicts (for example
"62 × no trade: no qualified setup"), the underlying's move at the chosen
horizon, and whether a stated direction agreed, disagreed, or was unanswerable.

Each row links to that session's decisions. Pending and unresolvable horizons
are shown as such, with the recorded reason.

### 4.3 Why per session

The worker decides every few minutes against the last *completed* daily close,
which does not move intraday. A day therefore contributes one evaluation and
dozens of records of it: the live API reports that today's 1,045 decisions rest
on 18 distinct completed closes, about 58 decisions per close. A per-decision
journal would present one fact 58 times. The existing caveat
already states this in words; the journal should state it in its shape.

### 4.4 No rates in this phase

The current contract serves counts and no rate, "because over a corpus where
every row is unanswerable, a rate would be a sentence about nothing." Phase 4
keeps that. No win rate, no agreement percentage, no average move. Counts, the
smallest and largest move, and the sample size are shown; anything that reads
like a score waits until there is a sample that could support one and a
separately agreed definition.

### 4.5 Deliberately absent

Strategy P&L curves, expectancy, Sharpe-like statistics, "would have made"
figures for refusals, and personal notes (which need private storage and
authentication, neither of which exists).

## 5. Screens (built only after approval)

- **Positions** — an attention-first list: open and unconfirmed positions before
  closed ones; each row shows instrument, state in words, quantity filled of
  requested, entry debit, open risk, and mark state. One click opens the
  position: economics, latest mark with its times, exit evaluations, incidents,
  and a link to the decision.
- **Review** — the caveat sentence first, then section A (execution outcomes),
  then section B (research horizons by session) with a horizon picker in the URL.

Both reuse what exists: `useResource`, `useCursorPage`, the resource-state
components, `source_id` checks, and the typed row pattern from Phase 3.

## 6. Fixtures and release gate

The redesign's gate: fixtures include pending, open, closing and incident
states, missing marks, stale observations, and realised outcomes separated from
research. The live source cannot supply these, so:

- A committed, clearly labelled fixture database (built by a script from the
  existing lifecycle test builders, never from invented broker responses) holds
  one position in each of the six states, one with an unreadable mark, one with
  a stale mark, and one closed round trip with a realised result.
- Backend tests assert every field in §3.3 for each state, the freshness rule at
  its boundaries, the `open`/`closed` filters, and that `realized` is absent for
  a half round trip.
- The read-only boundary tests, redaction tests and query-budget test are
  extended to the new routes.
- Browser tests cover the empty live shape, each state, loading/failed/stale,
  and both widths.

**Step 5 as built (6 October 2026).** The attention rule is one server function,
`presentation/positions.attention`, and every position carries its answer as
`attention`: `open_incident`, `stale_mark`, `unreadable_mark`, or `never_marked`
(confirmed exposure with no mark more than five minutes into an open session;
the approved text named only the stale mark, and an unmarked position is the
same gap). Closed and abandoned positions never need attention, and a pending
entry is left to its own deadline. Today and the Positions list both show that
answer and compute nothing.

**Step 1 as built (6 October 2026).** `tests/test_api_positions.py` builds each
state with the lifecycle store's own calls (prepare, submit, reconcile, close,
abandon, incident) rather than from a committed database, and runs on SQLite
and in the PostgreSQL lane. The committed fixtures the browser tests need are
captured with the screens, in steps 3 and 4.

## 7. Suggested order of work

Each step is its own pull request.

1. Positions API and fixtures (no UI).
2. Review API: executions and sessions (no UI).
3. Review screen — it has live content today.
4. Positions screen — exercised on fixtures; live shows the truthful empty state.
5. The stale-mark attention rule on Today.

Steps 1–2 are where the audit's agent and store boundaries are *not* touched:
these are read models only. Audit Batch C stays out of this phase.

## 8. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | Build both screens now, although live Positions will be empty until Paper entries are enabled? | **Yes, both.** Review is useful today. Positions is the screen that must already exist, and be trusted, on the day entries are enabled. |
| D2 | Research journal by market session rather than by decision (§4.3)? | **By session.** |
| D3 | Counts only, no rates or averages, in this phase (§4.4)? | **Counts only.** |
| D4 | Mark freshness: `stale` after 5 minutes in an open session (§3.5), and a stale mark on an open position raises attention on Today? | **Yes to both.** |
| D5 | Navigation: add **Positions** and **Review** as primary destinations (five in total), or keep three and put Review under Evidence? | **Primary.** They are daily questions; Evidence stays secondary. |
| D6 | The site is public over HTTP with no login. Position records (Paper only) would be public, as decision lifecycles already are. Proceed, or put access control first? | **Proceed for Paper.** Revisit before any non-Paper use; that review is already required by the redesign §7. |

**Outcome, 6 October 2026:** the owner approved all six as recommended (D1 both
screens; D2 by session; D3 counts only; D4 stale after five minutes, raising
attention; D5 primary navigation; D6 proceed for Paper).
