# Options Alpha Agent

## Phase 0 Record: Verified Event Cut Line

| Field | Value |
|---|---|
| Version | v0.1 |
| Phase | 0 of 7 (implementation plan §9) |
| Opened | 28 August 2026, 09:00 GMT-5 |
| Owner | Gino Llerena (Voltaic Alpha) |
| Status | `COMPLETE` for the exit gate. Revised 28 August 2026 11:00 UTC after the event page, live dashboard, Rule Book, and Submission Guidelines were read in full: `F-01` and `F-03` are retired, three fallbacks remain in force |
| Authority | Normative. Sections 3, 4, and 6 bind implementation. Later phases may not encode a different default. |

## 1. Purpose

Phase 0 records what is known about the event, freezes the H0 scope, and — for
every question that cannot be answered without the organizers — chooses a
**binding fallback interpretation** that is safe under every plausible answer.

The exit gate is deliberately not "all questions answered". It is "no question
can silently become an implicit default". A fallback here is a decision, not a
placeholder: implementation follows it until an organizer answer replaces it,
and §6 names the exact trigger and cost of each replacement.

Uncalibrated trading thresholds remain explicitly `PROVISIONAL` (implementation
plan §3.3) and do not block read-only work.

## 2. Confirmed facts

Verified from the public event page on 27 August 2026 and re-read at the Phase 0
opening. Each row is a fact this project may rely on without further proof.

| ID | Fact | Requirement |
|---|---|---|
| `F-A` | Online build window: 28 August – 4 September 2026 | `HK-001`, `CLR-002` |
| `F-B` | Teams of 1–6; enrollment and team participation required | `HK-002` |
| `F-C` | Alpaca **Paper** environment is the trading environment | `HK-003`, `RISK-014` |
| `F-D` | Eligible universe permits Alpaca stocks, options, ETFs, and crypto. Options are **permitted, not required** | `HK-004` |
| `F-E` | Judging criteria: Application of Technology, Presentation, Business Value, Originality. **P&L is not a published criterion** | `HK-005`, `HK-017` |
| `F-F` | Submissions must be original and MIT-compliant | `HK-008` |
| `F-G` | The event page names the Alpaca Trading API, MCP server, and CLI without stating that all are mandatory | `HK-006`, `CLR-018` |
| `F-H` | **Submission deadline: 4 September 2026, 15:00 UTC** (10:00 GMT-5). "You have until Sep 4, 2026, 15:00 UTC to submit." Kickoff and registration close 28 August 2026, 15:00 UTC | `HK-001` |
| `F-I` | Manual submission is available for 6 hours after the deadline, only with prior organizer or mentor approval | `HK-001` |
| `F-J` | **A public GitHub repository is mandatory.** A private repository "may lower your overall score" because judges cannot review it | `HK-010`, `DEC-001` |
| `F-K` | ~~The demo must be hosted on Streamlit, Replit, or Vercel~~ **Superseded 29 August 2026: the organizers confirmed there is no deployment-platform restriction.** The platform pages name those three as suggestions, not requirements | `HK-009`, `HK-011`, `DEC-005` |
| `F-L` | Video: maximum 5 minutes, MP4, mandatory. Deck: PDF, mandatory. Cover: PNG or JPG, 16:9. Short description ≤ 255 characters; long description ≥ 100 words | `HK-012` to `HK-015` |
| `F-M` | Judging criteria confirmed as Presentation, Business Value, Application of Technology, and Originality. **No weights are published** | `HK-017` |
| `F-N` | One track: **Options Alpha Agents**, main track, open to all. Prize pool $6,000 | `HK-014` |
| `F-O` | Every participant registers individually and must belong to a team on the platform, solo participants included | `HK-002` |

Two consequences follow directly and are binding:

1. Because of `F-D`, choosing options is a **project design decision**, not an
   event requirement. It must be justified on its own merits and must never be
   presented as a scoring fact.
2. Because of `F-E` and `F-M`, Paper P&L is a **diagnostic result only**. No
   deck, video, README, or dashboard copy may present it as a score. A
   `NO_TRADE` refusal is a valid and presentable outcome.
3. Because of `F-J`, `github.com/GinoLlerena/voltaic-alpha` **must be public at
   submission**. It may be created private; the flip to public is a release-gate
   checklist item at `G4`, not an afterthought.
4. `F-K` is superseded. The organizers confirmed on 29 August 2026 that no
   deployment platform is required, so `D-01` is closed and the hosting choice
   is a free architectural decision again. The Alibaba ECS deployment is the
   submission URL.

## 3. Frozen H0 scope (normative)

Frozen at the Phase 0 opening. Widening any row requires a decision-log entry
and a schedule re-plan, not a code change.

| Dimension | Frozen value | Excluded from H0 |
|---|---|---|
| Tradeable underlying | `SPY` only | All other symbols. QQQ/IWM are read-only context; individual equities are test-only |
| Setup | One mirrored trend-continuation/retest setup | Breakout/breakdown, earnings, mean reversion |
| Structure family | Vertical debit spreads (bull call, bear put) | Credit spreads, calendars, condors, naked legs, single options |
| Direction semantics | `bullish`, `bearish`, `neutral`; `neutral` terminates as `NO_TRADE` before option selection | Any direction chosen or reversed by the model |
| Cases | One qualified case, one refusal case, each with a separate oracle | Broad case catalogs |
| Execution | One Paper open/close lifecycle plus one ambiguous-write or restart recovery case | Multi-position portfolio operation |
| Concurrency | One open or pending strategy; no second entry after a loss or execution incident | Portfolio, cluster, and multi-position limits (`CLR-013`, post-H0) |
| Model role | Bounded memo only | Direction, invalidation, sizing, eligibility, or execution authority |
| Judge interface | Five views: health/mode, evidence and baseline, model memo, approval/request lineage, reconciled outcome or refusal | A sixth view |
| Broker interface | Alpaca Trading API through `alpaca-py`, single execution path | MCP in the deployed runtime (`F-03`; permitted as a local read-only testing tool); raw HTTP outside contract tests |
| Hosting | Free choice. `F-K` was superseded on 29 August 2026 by an organizer answer confirming no platform restriction | — |

This table is the single source for the Phase 1 allowlist configuration. Phase 1
transcribes it; it does not reinterpret it.

## 4. Paper-only authority (normative)

Restated here so that no later phase can weaken it by omission.

- `ALPACA_PAPER_TRADE=true` is mandatory and is validated against the **actually
  loaded value and the resolved endpoint** at startup and immediately before
  every write. Printed expected values are not proof (`EV-003`, `RISK-015`).
- `ALPACA_TRADING_ENABLED=false` is the default and stays false until the
  exact-request, idempotency, and reconciliation gates pass (Phase 4).
- Live credentials are never present, never a fallback, and never interchangeable
  with Paper credentials.
- The model reaches no broker tool. Orders exist only as immutable approved
  intents executed by a deterministic `alpaca-py` gateway. MCP is out of the H0
  runtime entirely (`F-03`). Where it is installed as a local read-only testing
  tool it omits the `trading` toolset, uses Paper credentials only, and produces
  no input to any decision record.
- The Alpaca CLI is a version-pinned operator diagnostic and dry-run cross-check.
  It is never execution authority.

## 5. Ownership

| Role | Owner |
|---|---|
| Vertical slice (Phases 1–4) | Gino Llerena |
| Judge demo and hosting (Phases 5–6) | Gino Llerena |
| Submission artifacts (Phase 7) | Gino Llerena |

Voltaic Alpha is a one-person team, so all three roles resolve to one owner.
This is a concentration risk with no staffing mitigation available. The
mitigations that are available are used instead: the H0 cut line in §3, the
protected integration window in §7, and the rule that a phase's safety exit gate
may not be bypassed to recover schedule.

## 6. Open questions and binding fallbacks

Each fallback is in force now. "Cost if wrong" states what must change if the
organizer answer differs — in every case a bounded change, never a rebuild.

### F-01 — Exact deadline and timezone — **RETIRED 28 August 2026**

**Answered by `F-H`:** the live dashboard states the deadline explicitly —
**4 September 2026, 15:00 UTC**, which is 10:00 GMT-5.

The fallback assumed 3 September 23:59 GMT-5 and was conservative by
approximately ten hours, exactly as its stated cost predicted. The schedule in
§7 is revised accordingly: 3 September returns as a full build day.

The 6-hour manual-submission window (`F-I`) requires prior approval and is a
backstop for a technical failure, never a planned part of the schedule.

### F-02 — Pre-existing code — **RETIRED 29 August 2026**

**Team determination:** the H0 build began at the event start time, so the
question the fallback was hedging against does not arise. The fallback is
retired and pre-existing code is no longer tracked as an open risk.

The [reuse ledger](options_alpha_reuse_ledger.md) is kept, not because the
question is still open, but because it is the evidence for the answer: it names
the three pre-event modules the H0 path uses - the contracts, the ports and the
workflow state machine - with their baseline commit and replacement cost, and it
shows the rest of the pre-event lab is not in the H0 path at all. The
`baseline-pre-event` tag stays for the same reason. Deleting either would remove
the support for the claim rather than strengthen it.

### F-03 — Are the MCP server and CLI mandatory? — **RETIRED 28 August 2026**

**Team decision, 28 August 2026:** MCP is **not mandatory**. No published event
material requires it: the event blurb names the Trading API, MCP server, and CLI
as available tooling, and neither the Rule Book nor the Submission Guidelines
makes any of them a condition of a complete submission.

**Binding consequence:** the autonomous agent uses the **Alpaca Trading API
through `alpaca-py`** as its single execution path. This is the project's
central claim, not a compromise — deterministic code holds execution authority
precisely because no model-reachable tool sits on the write path.

**Scope effect, deliberate:** the MCP evidence adapter leaves the H0 **runtime**
critical path. Nothing the submitted application does at run time depends on
MCP, and that removal is a schedule gain rather than a gap, because the Trading
API already supplies every read H0 needs. The pinned CLI doctor/dry-run artifact
is retained only while it stays cheap; it is an operator diagnostic and never
execution authority. Raw HTTP remains contract-test-only. Execution stays behind
an execution port, so an MCP adapter remains addable later without touching the
gateway.

**Permitted use — development and testing only.** The Alpaca MCP server may be
installed on a developer machine as a read-only exploration and
cross-check tool: comparing what the deterministic adapter read against what MCP
reports, exercising schema questions, and inspecting Paper state during
debugging. This is explicitly allowed and is not a contradiction of the decision
above, because it sits outside the deployed runtime.

Four conditions bind any such installation, and they are the same conditions the
firewall thesis applies to every model-reachable tool:

1. The `trading` toolset is omitted from the MCP configuration. A read tool that
   can be talked into a write is not a read tool.
2. Paper credentials only. Live credentials are never placed in an MCP
   configuration.
3. No MCP call is evidence. Anything MCP reports is a developer convenience;
   only the deterministic adapter's timestamped, hashed reads enter a decision
   record, because only those are reproducible from the audit trail.
4. The dependency stays out of the submitted runtime, so a judge cloning the
   repository never needs MCP to reproduce a decision.

**Installed configuration, 28 August 2026.** Launcher
`~/myprojects/alpaca_mcp_readonly.sh`, registered with Claude Code as
`alpaca-readonly` at **local scope** — private to this project, stored outside
the repository, so no `.mcp.json` is committed and condition 4 holds by
construction. Credentials are read from `.env` at launch and never copied into
any client configuration; the registered environment block is empty.

`ALPACA_TOOLSETS="assets,stock-data,options-data"`, verified empirically rather
than assumed:

| Configuration | Tools | Mutating tools |
|---|---|---|
| No filter (server default) | 72 | `place_stock_order`, `place_option_order`, `place_crypto_order`, `cancel_order_by_id`, `cancel_all_orders`, `close_position`, `close_all_positions`, `replace_order_by_id`, `exercise_options_position`, `do_not_exercise_options_position`, `create_locate`, plus watchlist writes and `update_account_config` |
| Documented "read-only" example, including `account` | 38 | `update_account_config` |
| **Installed configuration** | **32** | **none** |

Two findings from that verification are worth recording:

- The vendor's own read-only example still exposes a write. The `account`
  toolset bundles `update_account_config` (`patchAccountConfig`), which can set
  `suspend_trade`, `no_shorting`, and `pdt_check`. Toolsets are the server's only
  filtering granularity — there is no per-tool switch and no read-only flag — so
  `account` was dropped entirely. Account reads come from the deterministic
  adapter, which is the only component permitted to produce evidence anyway.
- `search_alpaca_docs`, `fetch_alpaca_doc`, and the API-spec search tools are
  always registered and are classified `external_text` by the server's own risk
  model. They pull untrusted external prose into an agent context. They are
  harmless for reading documentation and must never be treated as market data.

The installed package is PyPI `alpaca-mcp-server==2.3.0`, pinned in the
launcher; the running server self-reports version `3.4.7`. The two version
lines diverge upstream. Re-verify the tool inventory after any version change,
because this configuration's safety rests on the filter, not on the pin.

Condition 3 is the load-bearing one. An MCP-sourced number that reaches a
decision would silently break the reproducibility claim the whole project rests
on, and it would do so without any test failing.

**Residual risk, accepted:** a judge could read "uses Alpaca's Trading API, MCP
server and CLI" as expecting all three. The mitigation is presentational — the
deck and README state plainly why a firewall design keeps MCP off the write
path — not architectural.

### F-04 — Is autonomous execution required? — **RETIRED AS A BLOCKER 1 September 2026**

The organizer rule remains **NOT STATED**; what changed is that it no longer
blocks anything. Both postures ship and `scripts/arm_worker.sh` /
`scripts/disarm_worker.sh` select between them, so either answer costs one
configuration change. Retained below as the recorded interpretation, and removed
from the open-questions list. See `HK-007`, now `RESOLVED_BY_CONFIGURATION`.

### F-04 — Is autonomous execution required? (`DEC-004`, `HK-007`, `CLR-019`)

**Unknown:** whether execution must be fully autonomous, may be human-approved,
or is unconstrained. **NOT STATED**, though the event blurb's "autonomous
agents **and** trading apps" reads as permissive rather than mandatory. The
fallback stands and costs one configuration value either way.

**Fallback:** build the autonomous end-to-end path, and put the operator
approval boundary behind explicit configuration (`REQUIRE_OPERATOR_APPROVAL`,
default `true`, recorded on every decision). The judge demo runs the autonomous
configuration.

**Why safe:** the autonomous requirement is met by the demo path, and the
human-approval requirement is met by a flag, without either being a rewrite.
The approval state is durable and auditable in both configurations.

**Cost if wrong:** one configuration value and the demo script's mode.

### F-05 — Account, equity, reset policy, leaderboard (`DEC-003`, `HK-003`, `HK-005`)

**Account, equity and reset answered 1 September 2026 by direct verification;
leaderboard answered 29 August 2026 by inspection.** The Paper account was
verified read-only as same-day, created 81 minutes before kickoff, with zero
pre-kickoff orders, `ACTIVE`, options level 3, and its identifier deliberately
not recorded (`HK-003`). No starting-equity, reset or account-age rule is
published anywhere; that absence is recorded rather than guessed at. This
fallback is therefore **retired as a blocker**, and the construction below is
kept because it is why the unknown never mattered.

**Leaderboard answered 29 August 2026 by inspection of the live dashboard.** It
ranks *Top builders*, *Top referrers* and *Top submissions*. There is no P&L or
trading-performance ranking anywhere on it. Paper P&L therefore stays a
diagnostic, which is what the dashboard, README and deck already say. The
account, equity and reset questions remain open under the fallback below.

**Unknown:** required account type, starting equity, reset rules, and whether a
separate enrolled-dashboard P&L leaderboard exists.

**Fallback:** no constant equity anywhere in the system. Risk sizing derives
only from a fresh, timestamped Alpaca account snapshot, and `recommend` and
`paper_execute` reject fixture equity (`CLR-007`). P&L is reported as a
diagnostic with its sample size stated.

**Why safe:** the system is correct for any starting equity and any reset, so
the unknown cannot invalidate a calculation. If a leaderboard is later
confirmed, presentation changes; the risk engine does not.

**Cost if wrong:** presentation copy only.

### F-06 — OPRA entitlement (`DEC-006`, `CLR-015`)

**Unknown:** whether the account has OPRA option data or only the indicative feed.

**Fallback:** assume the **indicative feed**. Every option quote carries its
feed label and freshness; indicative data uses the conservative 120-second
freshness policy and is disclosed in the dashboard and deck wherever a quote is
shown.

**Why safe:** the strictest data assumption is the default, so an entitlement
upgrade only tightens thresholds and never invalidates a recorded decision.

**Cost if wrong:** if OPRA is available, freshness tightens to 30 seconds and
the disclosure text shortens. Entitlement is cheap to check and is a Phase 1
first action.

## 6a. Open project decisions

Not organizer questions — decisions this team owes itself, created by facts
confirmed on 28 August 2026.

### D-01 — Demo hosting platform — **CLOSED 29 August 2026**

**Answered by the organizers:** there is no deployment-platform restriction. The
Rule Book and Submission Guidelines name Streamlit, Replit, and Vercel as
suggestions rather than requirements.

**Resolution:** the Alibaba ECS deployment is the submission URL. The decision
that drove `D-01` - that the judge view is read-only over evidence already
produced, so it needs no always-on worker - remains correct on its merits and is
what made a credential-free dashboard possible. The worker now runs separately
on its own host with its own database, which is a better architecture than the
constraint would have permitted.

No Streamlit Community Cloud deployment is required.

## 7. Schedule under `F-H`

Seven team-days against the confirmed deadline of **4 September 2026, 15:00 UTC
(10:00 GMT-5)**, with the final window protected for integration and submission
only (`CLR-002`).

| Day | Phase |
|---|---|
| 28 Aug | 0 (this record) and 1 — executable vertical skeleton |
| 29 Aug | 2 — read-only SPY evidence and frozen replay |
| 30 Aug | 3 — bounded model memo, option mapping, and ablation |
| 31 Aug – 1 Sep | 4 — execution firewall and one Paper lifecycle |
| 2 Sep | 5 — five-view judge experience on the `D-01` host |
| 3 Sep | 6 — validation, deployment, narrative; **submission artifacts complete and uploaded by 23:59 GMT-5** |
| 4 Sep | 7 — buffer until **10:00 GMT-5**. No new capability. Repository flipped public. |

Submitting on 3 September rather than on the morning of the 4th is a deliberate
choice: it keeps the confirmed deadline as slack instead of spending it, and the
6-hour manual-submission window (`F-I`) then remains a genuine emergency
backstop rather than the plan.

## 8. Exit gate

The Phase 0 exit gate requires that eligibility, Paper-only authority, build
rules, H0 scope, and fallback interpretation are recorded.

| Gate element | Where recorded | Met |
|---|---|---|
| Eligibility | §2 `F-A`, `F-B`, `F-D`, `F-F`, `F-H`, `F-J`, `F-O`; fallbacks `F-02`, `F-05` | Yes |
| Paper-only authority | §4 | Yes |
| Build rules | §2 `F-F`; fallback `F-02` and the reuse ledger | Yes |
| H0 scope | §3, including the broker-interface and hosting rows | Yes |
| Fallback interpretation | §6: `F-01` and `F-03` retired, `F-02`, `F-04`, `F-05`, `F-06` in force | Yes |
| Single owner assigned | §5 | Yes |

Three questions remain unanswered by any published source — pre-existing code
(`F-02`), autonomy (`F-04`), and account/leaderboard details (`F-05`) — plus
OPRA entitlement (`F-06`) at the `G1` gate. None blocks Phase 1: each is covered
by a fallback with a named replacement trigger and a bounded cost. No unresolved
choice is encoded as an implicit default.

One decision this team owes itself is open and dated: `D-01`, demo hosting,
owed by the start of Phase 5.

**Phase 0 is closed. Phase 1 may begin.**

## 9. First actions carried into Phase 1

1. Confirm platform enrollment **and** team membership before kickoff. Both are
   required of solo participants (`F-O`), and registration closes at 15:00 UTC
   on 28 August with no stated grace period.
2. No organizer question remains a blocker. `F-02` retired 29 August, and `F-04`
   and `F-05` were retired as blockers on 1 September — the first because both
   postures ship behind a configuration switch, the second because the account
   was verified directly and no equity or reset rule is published to conflict
   with. Each remains recorded as the interpretation it always was; none of them
   now gates a submission.
3. Ask whether the Submission Guidelines' "IBM Bob Report" clause applies to
   this event. It appears on the generic platform page rather than the event
   page and reads as carried-over copy, but it is marked mandatory, and
   discovering on 4 September that it applies would be expensive.
4. Verify Alpaca options entitlement and option level on the Paper account
   (`DEC-006`) — cheap, and it settles `F-06`.
5. Decide `D-01` no later than the start of Phase 5, and earlier if Phase 1
   configuration would otherwise encode a host assumption.
6. Keep the [reuse ledger](options_alpha_reuse_ledger.md) current from the
   first Phase 1 module onward.
7. Add "flip the repository to public" to the `G4` checklist (`F-J`).
