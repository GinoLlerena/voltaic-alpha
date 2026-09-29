# Options Alpha — Personal UI Redesign v0.1

| Field | Value |
|---|---|
| Date | 28 September 2026, America/Lima |
| Status | Proposed implementation specification; no UI changes implemented by this review |
| Audience | One owner monitoring and reviewing a personal options-trading project |
| Direction | Evolve the existing React application into a calm, trustworthy daily workspace |
| Work prefix | `PUI-` |
| Boundary | Preserve Paper-only execution, deterministic authority, and the GET-only presentation API |

## 1. Decision and scope

Keep React, TypeScript, Vite, and TanStack Router. React migration has already
happened in the repository; repeating it would not address the current problems.
Professionalize the hierarchy, resource-state handling, readability, and daily
workflow instead of rebuilding the framework or imitating a large trading terminal.

The primary question changes from **“Can a judge understand this project?”** to
**“Is it operating correctly, what changed, and do I need to investigate?”**

Implement in this order:

1. Correct misleading loading, failure, freshness, and selection states.
2. Introduce a personal-use home with attention and operational status first.
3. Simplify decision history and decision details.
4. Add positions and richer review only after authoritative read models exist.

This document updates the audience and implementation direction of the
[earlier React redesign](options_alpha_react_ui_redesign_v0_1.md). That document
remains useful historical context, especially its authority and provenance
requirements. Its Streamlit assessment, proposed React migration, and
judge-first priorities must not be treated as the current implementation state.

Out of scope: trading-strategy changes, broker controls, live-money execution,
cloud provisioning, production deployment, framework replacement, billing,
multi-user administration, and fabricated analytics. Implementation or deployment
requires a separate request; this document is a specification, not a record of delivery.

## 2. Review method and evidence limits

Three specialist agents reviewed the project from UI/UX, trading-workflow, and
frontend-architecture perspectives. This is a synthesis of those agent reviews,
not a claim of external human expert certification.

Evidence used:

- Current frontend source, API contracts, and presentation services.
- Committed desktop/mobile visual-test screenshots. These use test fixtures;
  they are not production screenshots.
- Existing winner and runner-up analyses and the earlier redesign document.
- Read-only HTTP requests to `http://47.236.50.157/` and its public API.

The live root returned HTTP 200 and an application HTML shell. At approximately
01:15–01:16 UTC on 29 September 2026 (20:15–20:16 on 28 September in Lima), the
status API reported Paper mode, disabled order writes, observe mode, a worker
heartbeat about 11 seconds old, zero open positions, and zero open incidents.
It identified a live worker database containing 718 decisions. These are
time-bounded API observations, not independently reconciled broker facts.

The Notable endpoint returned one grouped no-trade entry containing 400 records
while reporting 718 total decisions. This reinforces the need to label the
bounded grouping window; it is not evidence that every historical decision had
the same outcome.

An interactive browser was unavailable. Therefore production layout, keyboard
behavior, responsive rendering, and browser-console health were not verified.
The review did not execute a runtime test suite or modify production resources.

## 3. Findings to resolve

Priority definitions: P1 = misleading operational information or cross-record
confusion; P2 = significant daily-use friction; P3 = optional refinement.

| ID | Priority | Finding and evidence | Required correction |
|---|---|---|---|
| PUI-001 | P1 | [Incidents](../../frontend/src/components/Incidents.tsx) maps loading/failure to empty rows and can assert “No incident is open.” [WorkerEvents](../../frontend/src/components/WorkerEvents.tsx) has a similar absence pattern. | Distinguish loading, unavailable, verified empty, successful data, and stale last-known data. Never infer health from a failed request. |
| PUI-002 | P1 | [useResource](../../frontend/src/api/useResource.ts) retains state when its request path changes. Old data can remain visible under a new selection or become stale after the new request fails. | Key cached state by resource identity; never show decision A under decision B's URL. Guard overlapping refreshes against out-of-order results. |
| PUI-003 | P1 | [Decision](../../frontend/src/routes/Decision.tsx) fetches eight resources independently but exposes freshness only for the summary; `ready()` discards other request states. Failed outcomes become an empty array. | Preserve each panel's state, source, timestamps, and identity. Do not translate unavailable outcomes into “No horizons were scheduled.” |
| PUI-004 | P1 | [SourceBanner](../../frontend/src/components/SourceBanner.tsx) displays LIVE and envelope observation time; [server](../../src/options_alpha_lab/api/server.py) creates that timestamp at request time. | Separate successful UI refresh from market-input as-of, decision time, and worker heartbeat. A working API is not evidence of current market inputs. |
| PUI-005 | P1 | [DecisionTicket](../../frontend/src/components/DecisionTicket.tsx) hardcodes “Why the setup did not qualify.” [Structure](../../frontend/src/components/Structure.tsx) can describe an unselected fallback candidate as “Why this structure.” | Use actual outcome-dependent copy; distinguish selected, rejected, and merely evaluated candidates. Missing evidence is not a refusal. |
| PUI-006 | P2 | [Overview](../../frontend/src/routes/Overview.tsx) places proof metrics ahead of decisions. In committed screenshots, the first decision begins around y=590 desktop and y=1130 mobile. | Put attention, operational freshness, and latest meaningful decisions before demonstration metrics. |
| PUI-007 | P2 | Decision detail renders extensive ticket, explanation, evidence, and lineage sections sequentially. | Present one concise summary, then navigable Setup & risk, Execution, and Evidence sections. Avoid repeated explanations. |
| PUI-008 | P2 | [DecisionList](../../frontend/src/components/DecisionList.tsx) parses a multiline label rather than typed display fields. Grouped history is bounded to 400 recent decisions. | Add typed list fields as needed; label scope and group counts; use server pagination for full history. |
| PUI-009 | P2 | [ActivityFeed](../../frontend/src/components/ActivityFeed.tsx) refreshes page one while retaining older pages. New arrivals can create a gap between them. | Keep a stable browsing snapshot or refetch the whole visible window; explicitly offer new-activity refresh. |
| PUI-010 | P2 | [Styles](../../frontend/src/styles.css) repeatedly uses approximately 9–11px metadata; identifiers and raw timestamps dominate rows. | Improve type scale, labels, spacing, time formatting, and progressive disclosure. Retain full raw values in details. |

These are repository findings, not assertions that each failure was reproduced
against production. The implementation must add regression tests demonstrating
the corrected behavior.

## 4. Information architecture

Start with three primary destinations. Evidence is secondary navigation, not a
fourth equally prominent daily task. Positions and Review are later additions.

| Destination | Main question | Content |
|---|---|---|
| Today | Does anything need attention? | Source/mode strip, incidents, worker condition, latest meaningful decision, recent changes |
| Decisions | What happened, and why? | History, server-derived grouping, filters, decision summary and evidence drilldown |
| Activity | What changed operationally? | Open incidents, worker faults/events, durable audit history |
| Evidence / diagnostics | Can I verify the record? | Proof metrics, authority details, redacted exports, optional demo tour |
| Positions — later | What exposure needs monitoring? | Authoritative cross-decision positions, reconciliation, exit state, observation freshness |
| Review — later | What can I learn from recorded outcomes? | Decision journal and clearly separated execution outcomes and research horizons |

Preserve existing `/decisions/$digest` links. If `/` becomes Today and a new
`/decisions` listing is added, retain or explicitly migrate old `view` and `tour`
query links. Back navigation must restore filters and browsing context.

### Today: content order

1. Compact persistent strip: Paper, order-write state, worker mode/heartbeat,
   source identity, and last successful refresh. Unknown stays visibly unknown.
2. Attention: open incidents, recorded worker faults, or unavailable monitoring
   sources. A verified quiet state is acceptable; do not fill it with demo KPIs.
3. Latest meaningful decision: instrument, recorded action, concise reason,
   decision time, market-input age, and a link to the full record.
4. Recent changes and shortcuts to history and evidence.

Use existing backend state to explain attention. Any new severity aggregation,
staleness thresholds, or priority rules must be explicit and tested; the browser
must not guess execution authority from labels or colors.

### Decision detail: content order

Start with instrument, action/direction, qualification result, plain-language
reason, decision time, and market-input as-of. For a selected structure, expose
legs, expiry, recorded cost, maximum loss, risk result, and invalidation before
hashes and policy identifiers. Clearly label fields that are unavailable.

Then provide anchor-linked sections or accessible tabs:

- **Setup & risk:** recorded evidence, evaluated versus selected structure,
  quote quality, risk checks, and invalidation.
- **Execution:** intent, broker acceptance, fills, reconciliation, and exits.
  These are separate states, not interchangeable synonyms for “executed.”
- **Evidence:** model output, deterministic authority, provenance, identifiers,
  policy versions, and redacted export.

Warnings remain visible even when their supporting evidence is collapsed.
“No qualifying setup” is a valid decision outcome, not necessarily a system error.

## 5. Data-truth and trading-presentation requirements

### Resource states

| State | Required presentation |
|---|---|
| Loading | “Loading incidents…” or a labelled loading indicator; no zero/none claim |
| Successful and empty | “No open incidents in this source,” with last successful refresh |
| Successful with data | Render verified response with relevant source/as-of information |
| Refresh failed, same-resource cache available | Show last-known data with a local stale warning and timestamp |
| Failed, no matching cache | “Incidents unavailable” with a safe retry action |
| Confirmed not found | Show record absence only for the appropriate server response; distinguish it from transport/500 failure |

Carry resource identity through state transitions. Do not combine contradictory
sources into a single apparently coherent decision. Source changes must invalidate
or visibly segregate incompatible cached content; do not imply an atomic snapshot
unless the API provides one.

### Freshness and units

- Distinguish API fetched-at, worker heartbeat, decision time, market-input
  as-of, and position reconciliation/observation time.
- Display recorded daily-close inputs as such; successful polling does not make
  them streaming prices. Backend-defined freshness rules must account for the
  expected data cadence rather than inventing a universal threshold.
- Format currency and units explicitly: per-share, per-spread, or total as
  supplied by the contract. Do not guess multipliers or derive authoritative
  risk totals cosmetically in the browser.
- Show market-session timestamps with an explicit timezone; optionally offer
  local time. Preserve precise UTC timestamps in details.
- Keep model confidence distinct from calibrated probability. Keep subsequent
  underlying movement distinct from option-strategy P&L or win rate.
- Disabled order writes do not establish absence of existing exposure. Keep
  position and reconciliation information independently visible.

## 6. Visual system

Retain the existing restrained dark theme for the first release. Professional
means readable, consistent, and trustworthy—not more animation or terminal chrome.

- Establish shared spacing, type, surface, border, and semantic-color tokens.
- Target at least 14px for operational data and 12px for secondary metadata;
  allow zoom/reflow and verify actual readability rather than relying on size alone.
- Use normal-case labels, tabular numerals for comparable values, and monospace
  selectively for identifiers. Avoid forcing prose into technical typography.
- Reserve amber for attention and red for faults; separate model identity from
  warning color. Every status also needs text or another non-color cue.
- Preserve visible keyboard focus, native table semantics, labelled scrollable
  regions, and accessible disclosure controls.
- On mobile, show mode/source and attention before secondary metrics. Keep
  wide leg tables in labelled horizontal regions without page-wide overflow.
- Defer light theme, advanced charts, and cosmetic icon expansion until justified
  by daily use. Do not add blank analytics merely to fill space.

Move the marketing tagline, corpus proof tiles, and judge walkthrough to About,
Evidence, or Demo. Keep provenance one action away rather than beneath every
value in tiny text. Do not hide source warnings or withheld-data explanations.

## 7. Reuse and backend dependencies

The [current package manifest](../../frontend/package.json) already contains
React, React DOM, and TanStack Router, with TypeScript/Vite, generated API types,
Vitest, Testing Library, Playwright, and axe tooling. Reuse this stack and existing
components. No new production library is required for the initial phases.

A state-management or component library may be evaluated during implementation
only against a specific unmet requirement. Verify current compatibility,
maintenance, accessibility, license, and bundle impact before adopting it.
The earlier redesign's library catalogue is not an installation checklist.

| Capability | Existing support | Required limit or extension |
|---|---|---|
| Operational strip | `/api/v1/system/status` | Render field timestamps and unknown states; do not treat envelope time as market time |
| Attention | `/api/v1/incidents`, `/api/v1/worker/events` | Preserve redaction and resource states; specify any cross-source attention rules |
| History | `/api/v1/decisions`, `/api/v1/decisions/grouped` | Add typed instrument/time/structure fields where absent; paginate full history and disclose grouping bounds |
| Decision details | Summary, market, memo, structure, risk, lifecycle, proof, outcomes endpoints | Preserve per-panel identity, source and freshness; do not construct table rows by fetching every detail endpoint |
| Positions | Decision-scoped lifecycle records | Add an authoritative cross-decision read model before presenting a current positions workspace |
| Review | Recorded outcomes and decision evidence | Distinguish research horizons from execution P&L; define sample counts and unavailable measurements |
| Personal notes | No public write contract | Requires a separate private persistence/authentication design; do not imply unsaved notes are durable |

Positions need stable identifiers, requested versus filled quantity, legs/expiry,
recorded entry cost and risk, reconciliation/exit state, observation timestamps,
and explicit unavailable valuation states. Account performance, live marks,
portfolio Greeks, OHLC charts, and payoff analytics are not assumed available.

Before adding sensitive personal data or any writes, separately review access
control and transport security. The reviewed endpoint was publicly reachable
over HTTP; this review did not establish HTTPS or authentication configuration.
Do not expand public payloads to include secrets, unredacted errors, or private notes.

## 8. Lessons retained from the hackathon analyses

These are lessons from the repository's earlier analyses, not a fresh competitor
audit or a claim about why judges selected the winners.

- [Winner frontend analysis](../codex_winner_project_analysis_v0_1.md),
  `CWA-026`: retain **status → decision → explanation**, using only metrics this
  application can substantiate.
- Same analysis, `CWA-027`: compact outputs for each decision stage improve
  comprehension. Preserve the distinction between model and deterministic
  authority; do not invent an agent consensus.
- Same analysis, `CWA-028`–`CWA-030`: reject hard-coded connectivity, canned
  performance, silent stale prices, and failures rendered as reassurance.
- [Runner-up analysis](../implementation/options_alpha_runnerup_analysis_v0_1.md),
  `RA-019`: separate presentation/demo material from the real daily product.
- [Earlier winner analysis](../implementation/options_alpha_winner_analysis_v0_1.md):
  retain the distinction between verified implementation and reported capability.

Do not copy the breadth, cinematic presentation, artificial KPIs, or institutional
controls of a competition demo. Optimize for the owner's recurring tasks.

## 9. Implementation phases and release gates

### Phase 1 — Truthful state handling

Resolve PUI-001 through PUI-005 and PUI-009. Introduce a shared resource-aware
panel or equivalent explicit rendering contract. Isolate caches by request,
prevent older refreshes replacing newer responses, retain panel provenance, and
fix outcome-dependent headings. Preserve the read-only boundary.

Gate: regression tests cover initial loading, empty success, first-request
failure, stale refresh, real 404 versus server failure, decision A→B navigation
with delayed/failed B, out-of-order responses, mixed source responses, qualified
versus refused decisions, and activity arrivals while browsing older pages.

### Phase 2 — Personal shell and Today

Implement Today / Decisions / Activity navigation, compact status, attention
ordering, readable tokens, and secondary Evidence/Demo access. Reuse current
status and incident endpoints; do not require a speculative portfolio backend.

Gate: at 1280×900 and 400×900, mode/source and attention appear before demo
metrics. Keyboard navigation, zoom/reflow, and source/error states remain usable.

### Phase 3 — Decision workflow

Implement typed list fields and full-history pagination where necessary,
preserved URL filters, concise summaries, section navigation, meaningful units,
and reduced repetition. Keep existing decision URLs and proof exports working.

Gate: the owner can find the latest relevant decision without parsing a snapshot
ID; one further action exposes its supporting evidence. Selected and rejected
structures are unambiguous. Missing quote/risk information stays explicit.

### Phase 4 — Backed positions and review

Agree and test the missing read models before building the corresponding screens.
Expose only persisted, attributable observations and outcomes. Keep editable
notes and execution controls outside this phase unless separately designed and approved.

Gate: accepted fixtures include pending/open/closing/incident states, missing
marks, stale observations, and realized outcomes clearly separated from research.

## 10. Verification and definition of done

For each implementation phase:

- Run frontend typecheck, lint, unit/component tests, and build using the
  repository's existing scripts and package manager.
- Run relevant Playwright interaction, accessibility, and visual suites. Inspect
  changed screenshots before accepting new baselines; do not blindly regenerate them.
- If contracts change, regenerate OpenAPI types and run affected backend contract,
  redaction, source-selection, and read-only boundary tests.
- Verify loading/error/stale/empty states on desktop and mobile, not just the
  populated happy path. Confirm polling does not steal focus or reset browsing state.
- Complete an interactive browser review of the actual candidate build; the
  limitations of this initial review must not become release exceptions.

Success target: within ten seconds, the owner can identify mode, worker condition,
data freshness, outstanding attention, and the latest meaningful decision. Within
one additional action, the relevant evidence is available. No failed request may
render an invented zero, healthy state, or business absence.

This document itself changes no application behavior. Production deployment,
trading authority, infrastructure, and unrelated repository files remain outside
the documentation task.
