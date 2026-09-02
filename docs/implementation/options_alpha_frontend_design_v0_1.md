# Options Alpha Frontend Design v0.1

*Judge-first interface for an auditable Paper execution firewall*

| Field | Value |
|---|---|
| Status | H0 implementation-ready UX/UI handoff |
| Audience | Hackathon judges, authenticated operator, post-run reviewer |
| Frontend stack | FastAPI, Jinja2, HTMX, Plotly |
| Primary viewport | Desktop judge demo; responsive down to 360 px |
| Authority boundary | Read-only by default; UI actions never create trading authority |

## 1. Design judgment

The interface must not resemble a retail trading terminal whose central promise is profit. The project's differentiator is proof: where evidence came from, where model authority ended, why deterministic policy approved or refused the setup, what exact request was authorized, and whether broker and local state reconciled.

The UI therefore uses an **evidence-to-authority-to-outcome** narrative. Paper P&L is subordinate to process integrity, correct refusal, and duplicate-prevention evidence. Model confidence is displayed as model metadata, never as a calibrated probability or an order-sizing control.

## 2. Users and access

### 2.1 Judge — public, redacted, read-only

Needs to understand the product in under three minutes and inspect three frozen demonstrations:

1. a qualified SPY Paper open/close lifecycle;
2. a correct `NO_TRADE` refusal; and
3. an ambiguous-write or restart recovery with no duplicate strategy.

The judge cannot change mode, acknowledge incidents, submit, replace, cancel, close, rotate credentials, or reveal raw account/order payloads.

### 2.2 Operator — authenticated

Needs current health, reconciliation, execution state, incidents, and explicit control consequences. Operator controls call protected control endpoints and create append-only audit events. Controls do not bypass the deterministic workflow or generate `ApprovedOrderIntent`.

### 2.3 Reviewer — authenticated or redacted export

Needs stable IDs, timestamps, policy/model versions, evidence provenance, reason codes, hashes, broker correlation, Paper/stressed outcome separation, and an export that excludes secrets and confidential payloads.

## 3. UX principles

1. **Safety state is never hidden.** Environment, bot mode, execution state, endpoint proof, data freshness, and reconciliation appear in the global shell.
2. **Evidence precedes narrative.** Observed facts and deterministic classifications appear before the model memo.
3. **Authority is visible.** Every screen differentiates observed data, model output, deterministic policy, immutable authority, and broker state.
4. **Refusal is a successful outcome.** `NO_TRADE` receives a complete result view, not an error treatment.
5. **Ambiguity remains visible until reconciled.** A timeout never becomes a silent retry or a generic success message.
6. **Paper is not live truth.** Feed and Paper limitations remain visible near any performance result.
7. **No decorative AI.** The UI compares the bounded model path with the deterministic no-LLM baseline on the same snapshot.
8. **No color-only meaning.** Every status includes a word, icon/shape, and accessible description.
9. **No hidden trading controls.** Public UI contains no action that looks like order submission. Authenticated controls state their exact effect and authority limit.

## 4. Information architecture

The application has one shell and exactly five primary views, matching H0 scope:

| # | Route | Label | Primary question |
|---:|---|---|---|
| 1 | `/` | Status | Is the system safe, current, and understandable? |
| 2 | `/decisions/{id}/evidence` | Evidence | What was observed, and what did deterministic code qualify? |
| 3 | `/decisions/{id}/memo` | Model memo | What bounded contribution did the model make relative to the baseline? |
| 4 | `/decisions/{id}/authority` | Authority | Which deterministic checks and immutable hashes permitted or prevented a write? |
| 5 | `/decisions/{id}/outcome` | Outcome | What did the broker do, did state reconcile, or why was no order created? |

A global **demonstration selector** switches among the qualified lifecycle, refusal, and recovery traces. It changes the selected frozen record; it is not a strategy or market filter.

## 5. Global application shell

### 5.1 Header

- Product: `Options Alpha`.
- Product descriptor: `Auditable Paper execution firewall`.
- Persistent environment status: `PAPER · endpoint verified`, including proof timestamp in its details.
- Bot mode: `observe`, `recommend`, or `paper_execute`.
- Durable execution state: `NORMAL`, `NO_NEW_RISK`, or `FREEZE_ALL_WRITES`.
- Reconciliation: `matched`, `pending`, or `mismatch` plus last completed time.
- Access label: `Judge view` or authenticated operator identity.

The word `PAPER` is not endpoint proof by itself. Its expanded details show the resolved host, verification time, and redacted account fingerprint.

### 5.2 Navigation

- Desktop: fixed left rail with the five numbered views and current-view marker.
- Tablet/mobile: horizontally scrollable tab row below the global status strip.
- Preserve selected demonstration and view in the URL.
- Browser Back/Forward must work; HTMX history updates are required.

### 5.3 Demonstration selector

Options:

- `Qualified lifecycle` — one combined-limit SPY vertical opened and closed in Paper.
- `Correct refusal` — stale, contradictory, or illiquid snapshot terminates as `NO_TRADE`.
- `Recovery proof` — ambiguous write or restart enters `NO_NEW_RISK`, reconciles by client ID and broker state, and creates no duplicate.

Every demonstration is visibly labeled `Frozen demo record` or `Current Paper run`. Historical examples must never look live.

## 6. View specifications

### 6.1 Status

**Purpose:** establish trust before showing any trade result.

Content order:

1. outcome headline in plain language;
2. four safety facts: Paper endpoint proof, execution state, reconciliation, data freshness;
3. six-stage workflow rail from `OBSERVED` to `DECIDED`;
4. current decision summary: SPY, setup, action/refusal, policy version;
5. service readiness: database, worker lease, Alpaca, OpenAI, market clock;
6. disclosure strip: Paper simulation, feed label, no established alpha.

For `NO_NEW_RISK`, the page must say what remains allowed: cancels and reconciled risk-reducing closes. For `FREEZE_ALL_WRITES`, it must say that every write, including closes, is blocked pending operator resolution.

### 6.2 Evidence

**Purpose:** show facts and deterministic interpretation before model prose.

Content order:

1. snapshot identity, decision time, completed-bar cutoff, underlying price, provider/feed;
2. data-quality summary with missing/stale/provider reason codes;
3. compact completed-bar chart with signal time after bar `t` and earliest eligible execution in `t+1`;
4. evidence-family table: stable evidence ID, family, direction, measured value/summary, strength, source, observed time, freshness;
5. deterministic setup card: family, direction, evidence references, invalidation;
6. deterministic no-LLM baseline result beside the model-assisted path result.

The chart cannot imply a same-bar fill. Forming bars are visually excluded and labeled.

### 6.3 Model memo

**Purpose:** prove that the model is bounded, traceable, and evaluated rather than treated as an oracle.

Content order:

1. authority notice: `Advisory output — cannot reverse setup, change invalidation, size risk, or submit orders`;
2. direction and `model confidence metadata` with a tooltip stating that it is not a calibrated probability;
3. concise reasoning summary;
4. supporting evidence references;
5. counter-evidence references;
6. unchanged deterministic invalidation;
7. model metadata: provider/model, prompt/schema version, latency, token use, `store=false`, status;
8. ablation comparison: baseline versus model-assisted result, evidence fidelity, counter-evidence captured, abstention, latency, and cost.

Do not display hidden chain-of-thought or label fluent prose as reasoning quality.

### 6.4 Authority

**Purpose:** make the execution firewall the visual centerpiece.

Primary visualization: a left-to-right or top-to-bottom hash lineage:

`snapshot → setup/thesis → risk decision → approved intent → prepared request → broker order → reconciliation`

Each node shows:

- immutable record ID;
- timestamp;
- schema/policy/adapter version where applicable;
- truncated hash with accessible copy/details control;
- status and deterministic reason codes.

The boundary between `approved intent` and `prepared request` is labeled `Only deterministic gateway may cross`.

For a refusal, later nodes are replaced with one explicit terminal panel: `No authority created · no broker request prepared`.

For recovery, show the ambiguous response, `NO_NEW_RISK`, lookup by deterministic `client_order_id`, orders/activities/fills/positions comparison, and `duplicate prevented` result.

### 6.5 Outcome

**Purpose:** show lifecycle truth without overstating simulated performance.

Qualified lifecycle:

- combined MLeg strategy with parent quantity and both leg intents;
- order timeline: prepared, submitted, acknowledged, partial/filled, close prepared, closed;
- parent and leg states plus filled strategy quantity;
- entry/exit combined limit and fill;
- original maximum loss and current/final defined risk;
- Paper P&L and conservative stressed P&L as separate values;
- reconciliation matrix for orders, activities, fills, positions, and local records;
- Paper/feed limitations adjacent to results.

Refusal:

- `NO_TRADE` as the headline outcome;
- exact terminating stage and reason codes;
- data/model/broker calls that were skipped;
- explicit proof that no intent, prepared request, or broker order exists.

Recovery:

- incident timeline;
- state transition to `NO_NEW_RISK`;
- client-ID lookup and multi-source reconciliation;
- duplicate-attempt count `0`;
- operator-reviewed return to `NORMAL`, if completed.

## 7. Component inventory

| Component | Required variants |
|---|---|
| Global safety strip | verified, warning, critical, unknown |
| Status label | text + icon/shape; never color only |
| Workflow rail | reached, current, refused, skipped, pending |
| Evidence row | aligned, counter, neutral, stale, missing, provider error |
| Provenance detail | provider, feed, source time, receipt time, age, hash |
| Baseline comparison | same result, model adds counter-evidence, model abstains, mismatch |
| Hash lineage node | verified, absent by design, mismatch, expired, ambiguous, reconciled |
| Reason-code list | plain-language label plus stable machine code |
| Reconciliation matrix | matched, absent, pending, mismatch |
| Timeline event | deterministic, model, broker, operator, incident |
| Disclosure strip | Paper limitations, feed limitations, no-alpha claim |
| Empty state | no decision yet, no position by design, no incident |
| Error state | stale snapshot, provider unavailable, unauthorized, reconciliation mismatch |
| Operator confirmation | consequence, allowed operations, durable state change, audit ID |

## 8. State and copy model

| State | Headline | Required explanation |
|---|---|---|
| Ready | `Ready to evaluate · Paper writes gated` | Endpoint verified, state normal, broker/local state matched |
| Observe | `Observing only · writes disabled` | Market reads may run; no approved intent can reach the broker |
| Recommend | `Recommendation mode · writes disabled` | Full decision path may run; execution gateway refuses writes |
| `NO_NEW_RISK` | `New risk blocked` | Entry and risk-increasing replaces blocked; reconciled cancels/closes remain available |
| `FREEZE_ALL_WRITES` | `All broker writes frozen` | Credential/adapter/endpoint integrity incident; operator action required |
| `NO_TRADE` | `Correct refusal · no authority created` | Show terminating gate and reason codes |
| Ambiguous | `Broker response ambiguous · reconciling` | No retry; lookup and reconciliation in progress |
| Reconciled | `Broker and local state matched` | Show compared sources and completion time |
| Stale data | `Snapshot unusable · decision stopped` | Show fields, ages, thresholds, and skipped downstream stages |
| Disconnected | `Showing last verified state` | Timestamp the last known state; disable controls and mark data non-current |

Avoid `success` for profitable trades. Use `reconciled`, `approved`, `refused`, and `closed` to describe process truth.

## 9. Visual system

### 9.1 Direction

Calm institutional interface with high information density, generous spacing, and no gamified trading cues. The design supports light and dark system appearances.

### 9.2 Color roles

- Ink/navy: primary text and authority structure.
- Slate: secondary metadata and unselected navigation.
- Blue: observed information and links.
- Teal: verified/reconciled process state.
- Amber: degraded, stale, or operator-attention state.
- Red: blocked integrity failure only, not ordinary negative P&L.
- Violet: bounded model output, visually distinct from facts and deterministic policy.

Bullish/bearish direction uses arrow/icon plus text and is never encoded only as green/red.

### 9.3 Typography

- UI and narrative: system sans-serif, 14–16 px base.
- IDs, hashes, symbols, prices, timestamps, reason codes: system monospace.
- Page title: 28–32 px desktop, 24–28 px mobile.
- Minimum interactive target: 44 × 44 px.

### 9.4 Density

- One primary claim per page.
- Up to four safety facts above the fold.
- Long identifiers are truncated visually but available in full to assistive technology and copy/details controls.
- Advanced raw fields use disclosure panels; confidential payloads are never rendered.

## 10. Responsive behavior

### Desktop, 1024 px and above

- 224 px left navigation rail.
- Main content max width 1240 px.
- Two-column comparisons allowed only when both paths remain readable.
- Hash lineage is horizontal when seven nodes fit; otherwise it wraps as a stepped rail.

### Tablet, 736–1023 px

- Navigation becomes a horizontal tab strip.
- Safety facts use two columns.
- Evidence/baseline and outcome/reconciliation sections stack.
- Hash lineage becomes vertical.

### Mobile, 360–735 px

- Product header and demonstration selector stack.
- Global safety facts become a single compact list.
- Tables render as labeled record blocks; do not require horizontal scrolling for primary facts.
- Charts retain axes/labels and omit optional annotations before shrinking text.
- Persistent public UI remains read-only; operator controls move to a separate authenticated sheet.

## 11. Accessibility and privacy

- Target WCAG 2.2 AA contrast and keyboard behavior.
- One visible `h1`; semantic heading order thereafter.
- `aria-current="page"` for navigation and accessible names for status icons.
- Status changes use a polite live region; critical execution-state changes use an assertive live region.
- Focus returns to the triggering element after HTMX swaps or dialogs.
- Charts have tabular text alternatives.
- Never render API keys, authorization headers, full account numbers, private endpoints, raw prompts, hidden reasoning, or unredacted broker payloads.
- Public IDs use redacted fingerprints; exports are explicitly labeled `Redacted`.

## 12. Interaction and authority rules

1. Public judge routes are GET/read-only.
2. Case switching loads an existing frozen/current record; it does not run a strategy.
3. Copy/details controls never expose confidential values.
4. Mode/state controls exist only for authenticated operators and use CSRF protection, reauthentication for critical actions, consequence text, and append-only audit logging.
5. No UI action can construct or mutate `ApprovedOrderIntent`.
6. `NO_NEW_RISK` and `FREEZE_ALL_WRITES` state changes require server-side authorization and state-machine validation.
7. A browser timeout or network error never implies that a broker write failed; the UI enters ambiguous/reconciliation state.
8. UI refreshes use database-backed state. The browser is never the authoritative lifecycle store.

## 13. View-model contracts

Server-rendered pages should consume redacted, page-specific view models rather than provider payloads.

| View model | Minimum fields |
|---|---|
| `ShellView` | access role, environment proof, bot mode, execution state, reconciliation state/time, selected demo |
| `StatusView` | decision headline, workflow transitions, readiness checks, policy version, disclosures |
| `EvidenceView` | snapshot metadata, bar cutoff, data quality, signals/provenance, setup, baseline/model outcomes |
| `MemoView` | bounded thesis fields, referenced evidence, counter-evidence, invalidation, model metadata, ablation |
| `AuthorityView` | immutable IDs/hashes, deterministic checks, TTL, client ID, dry-run, request/broker/reconciliation states |
| `OutcomeView` | action/refusal, MLeg/leg states, timeline, Paper/stressed P&L, reconciliation matrix, limitations |

All timestamps render in `America/New_York` for market context with UTC available in details. Financial values retain `Decimal` precision at the server boundary.

## 14. Implementation plan

### Increment UI-1 — shell and frozen demonstrations

- Add FastAPI application factory and read-only route skeletons.
- Add base Jinja shell, responsive navigation, global safety strip, disclosures, and demonstration selector.
- Create redacted view-model fixtures for lifecycle, refusal, and recovery.
- Add semantic/accessibility smoke tests.

### Increment UI-2 — Status and Evidence

- Implement readiness, workflow rail, snapshot/provenance, data quality, evidence families, completed-bar chart, and baseline comparison.
- Test stale/forming-bar and disconnected states.

### Increment UI-3 — Model memo and Authority

- Implement bounded memo, evidence-reference linking, model metadata, ablation, hash lineage, deterministic checks, refusal terminal, and recovery reconciliation.
- Test that no dashboard code imports or calls the broker gateway.

### Increment UI-4 — Outcome and operator boundary

- Implement MLeg lifecycle, Paper/stressed result separation, reconciliation matrix, and refusal/recovery outcomes.
- Add authenticated control surface only after protected server endpoints and audit logging exist.

### Increment UI-5 — responsive and release QA

- Verify 360, 736, 1024, and 1440 px layouts in light/dark appearances.
- Test keyboard flow, screen-reader labels, contrast, disconnected/empty/error states, confidentiality scans, and judge clean-session walkthrough.
- Capture release screenshots and the fallback demo from the deployed build.

## 15. H0 acceptance criteria

- A judge can identify Paper environment, mode, execution state, reconciliation, and selected demo without scrolling.
- A judge can explain the difference between observed evidence, deterministic baseline, bounded model memo, deterministic risk, immutable authority, and broker state.
- Lifecycle, refusal, and recovery records are each reachable within one selection and one primary-view change.
- `NO_TRADE` clearly proves that no intent/request/order was created.
- Recovery clearly proves that no duplicate strategy was created.
- Paper P&L is never shown without stressed P&L and simulation/feed limitations.
- Model confidence is labeled as uncalibrated metadata and cannot visually dominate deterministic evidence.
- Public views expose no write control or confidential value.
- All five primary views pass desktop and mobile smoke tests without overlap or essential horizontal scrolling.
- Frontend dependencies cannot reach Alpaca order submission directly.

## 16. Explicit non-goals

- General portfolio dashboard or watchlist.
- Multi-symbol screener.
- Strategy builder or threshold editor.
- Chat interface for order execution.
- Live-money switch.
- Social trading, gamification, leaderboard, or P&L-first home page.
- Post-H0 policy promotion UI.

## 17. Requirement coverage

| Requirements | UI treatment |
|---|---|
| `HK-009`, `HK-018` | Public redacted demo URL; persistent Paper, feed, risk, and non-advisory disclosures |
| `AI-003`, `AI-005` to `AI-010` | Structured memo, evidence/reference linking, bounded-authority notice, model metadata, no hidden reasoning, and visible no-LLM ablation |
| `DATA-004`, `DATA-006`, `DATA-016` | Provider/feed/source/receipt/freshness metadata, completed-bar timing, and feed-specific labels |
| `RISK-014` to `RISK-017` | No public write controls; endpoint/mode/state proof; exact semantics for `NO_NEW_RISK` and `FREEZE_ALL_WRITES` |
| `RISK-018` to `RISK-021` | Intent/request hashes, deterministic client ID, native MLeg lifecycle, ambiguous-write containment, and multi-source reconciliation |
| `OPS-006` to `OPS-010` | Readiness, read-only operational APIs, authenticated controls, five-view dashboard, and redacted trace/export behavior |
| `QA-006`, `QA-007` | `t`/`t+1` visibility; separate Paper and stressed results with omitted-effect disclosure |
| `QA-009`, `QA-010` | Exact-request lineage, lifecycle, restart/timeout recovery, and duplicate-prevention proof |
| `QA-015`, `QA-016` | Named responsive breakpoints, accessibility/release checks, clean-session demo, and fallback capture |

## 18. Decision authority and design readiness

The UX/UI lead owns information architecture, visual hierarchy, component behavior, responsive transformation, accessibility, public copy, and presentation of system state. The UX/UI lead does not invent trading facts, create execution authority, or reinterpret broker state.

The H0 design is ready for implementation when the interface can be built without a developer choosing a new layout, status meaning, public interaction, or responsive behavior. Exact trading thresholds and real lifecycle values are runtime/product inputs, not unfinished visual design.

| Decision area | Final authority | H0 disposition |
|---|---|---|
| Navigation, hierarchy, components, visual tokens, responsive behavior | UX/UI lead | Decided in this document |
| Public versus authenticated interaction | Product plus Security, expressed by UX/UI | Public experience is read-only; operator controls are excluded until protected endpoints exist |
| Strategy labels, risk semantics, lifecycle truth, reason codes | Trading/Risk and Backend | UI renders typed values and approved plain-language mappings; it does not infer them |
| Demo scope and judging narrative | Product, advised by UX/UI | Three frozen records and five views; no portfolio terminal or strategy builder |
| Final acceptance fixtures | Trading/Risk, Backend, QA | Must replace representative design values before release |

### 18.1 Resolved UX decisions

| ID | Decision | Rationale |
|---|---|---|
| `UXD-001` | Default landing view is Status with the Qualified lifecycle selected. | Establishes safety and product value before trade detail. |
| `UXD-002` | The public selector uses `?demo=qualified`, `?demo=refusal`, or `?demo=recovery`. | Keeps demonstrations linkable and Back/Forward-safe without implying a strategy filter. |
| `UXD-003` | Frozen demonstrations never auto-refresh. A current authenticated Paper run may refresh every 15 seconds and always shows its last refresh time. | Historical evidence must remain stable; current state must expose age. |
| `UXD-004` | The public H0 experience contains no write-shaped control, disabled order button, or mode toggle. | A disabled trading control still suggests authority that the judge does not have. |
| `UXD-005` | Light/dark appearance follows the operating-system preference; H0 has no theme toggle. | Meets both appearances without adding nonessential state and controls. |
| `UXD-006` | H0 uses the `Options Alpha` text wordmark and shield/lineage mark; no custom logo project is required. | Preserves implementation time and avoids decorative branding becoming a dependency. |
| `UXD-007` | Market time is primary (`America/New_York`); UTC is available in details. Relative time is supplemental and never replaces an absolute timestamp. | Trading interpretation requires market context and audit records require an unambiguous instant. |
| `UXD-008` | Only the Evidence view uses a price chart. Outcome uses a lifecycle timeline and reconciliation matrix, not a performance chart. | Prevents the interface from becoming P&L-first and assigns one visual form to each kind of proof. |
| `UXD-009` | Model output is violet and explicitly advisory; deterministic policy and authority use ink/teal. | Visually separates narrative contribution from execution permission. |
| `UXD-010` | Status vocabulary is limited to observed, qualified, refused, approved, prepared, submitted, acknowledged, filled, closed, ambiguous, matched, mismatch, and reconciled. | Avoids the misleading use of `success` for trading outcomes. |
| `UXD-011` | Operator authentication and control screens are not part of the public H0 frontend increment. | Their safe design depends on protected endpoints, reauthentication, CSRF, and audit semantics that do not yet exist. |
| `UXD-012` | Representative fixture values may be used during implementation only when visibly tagged `Design fixture`. | Enables parallel frontend work without presenting synthetic values as Paper evidence. |

## 19. Canonical H0 demonstration narratives

These narratives freeze the user experience, not the trading oracle. IDs, prices, timestamps, fill values, thresholds, hashes, and broker states in the released demonstration must come from accepted fixtures or Paper evidence. Until then, the UI must display `Design fixture · not broker evidence`.

### 19.1 Qualified lifecycle

**Judge takeaway:** the model contributed a bounded memo, deterministic policy created the only authority, one combined Paper order opened and closed, and broker/local state reconciled.

| Element | Required design state |
|---|---|
| Selector label | `Qualified lifecycle` |
| Status headline | `Closed and reconciled · defined risk preserved` |
| Shell | `PAPER · endpoint verified`; `paper_execute`; `NORMAL`; `matched` |
| Decision | SPY `trend_continuation_retest`; bullish; `OPTIONS_POSITION` |
| Workflow | All six decision stages reached; execution lifecycle is shown separately |
| Evidence | Completed bars only, bullish structure plus participation, freshness usable, no forming-bar input |
| Memo | Advisory bullish memo, referenced evidence, counter-evidence, unchanged invalidation, baseline comparison |
| Authority | Complete lineage through broker order and reconciliation; intent/request hashes and client order ID visible in redacted form |
| Outcome | One bull call debit spread, parent quantity and both leg intents, combined limit, defined maximum loss, open/close timeline, matched reconciliation |
| Performance copy | `Paper result` and `Conservative stressed result` appear side by side with limitations immediately below |

The default design fixture may reuse the architecture-test shape—one SPY bull call debit spread and a USD 400 calculated maximum loss—but it must not be described as a real fill or a validated risk threshold.

### 19.2 Correct refusal

**Judge takeaway:** unusable evidence stopped the workflow before model synthesis, structure selection, authority creation, or broker access. Refusal is expected safety behavior.

| Element | Required design state |
|---|---|
| Selector label | `Correct refusal` |
| Status headline | `Correct refusal · no authority created` |
| Shell | `PAPER · endpoint verified`; `recommend`; `NORMAL`; `matched` |
| Decision | SPY; `NO_TRADE`; terminal reason `stale:option_chain` in the design fixture |
| Workflow | `OBSERVED` reached and refused by data quality; later stages marked `Skipped by policy` |
| Evidence | Stale option-chain field, observed time, receipt time, age, permitted age, feed, and plain-language consequence |
| Memo | `Not requested`; explain that model synthesis was skipped after deterministic refusal |
| Authority | Terminal panel: `No intent · no prepared request · no broker order` |
| Outcome | Refusal reason, skipped calls, append-only decision record, and zero write attempts |

If the accepted refusal fixture later uses contradictory evidence or illiquidity, the same screen structure remains; only the terminating stage and approved reason-code mapping change.

### 19.3 Recovery proof

**Judge takeaway:** an ambiguous broker response did not trigger a retry; new risk was blocked, the deterministic client order ID was reconciled across broker sources, and no duplicate strategy was created.

| Element | Required design state |
|---|---|
| Selector label | `Recovery proof` |
| Status headline | `Recovered and reconciled · duplicate prevented` |
| Shell after recovery | `PAPER · endpoint verified`; `paper_execute`; `NORMAL`; `matched after incident` |
| Incident state | Timeline visibly enters `NO_NEW_RISK` while the broker result is ambiguous |
| Workflow | Decision stages complete; ambiguity begins only after a prepared request crosses the deterministic gateway |
| Evidence and memo | Same bounded read-only treatment as the qualified record |
| Authority | Prepared-request hash, deterministic client order ID, ambiguous response, lookup, and matched broker correlation |
| Outcome | Orders, activities, fills, positions, and local-record comparison; duplicate-attempt count `0`; operator-reviewed return to `NORMAL` if recorded |

The resolved headline must not erase the incident. The incident transition and its duration remain visible on Status, Authority, and Outcome.

## 20. Visual tokens

All tokens are CSS custom-property inputs. Components consume semantic roles rather than hard-coded colors.

### 20.1 Color

| Token | Light | Dark | Use |
|---|---|---|---|
| `--canvas` | `#F5F7FA` | `#0B1220` | Page background |
| `--surface` | `#FFFFFF` | `#111C2E` | Primary panels |
| `--surface-subtle` | `#EEF2F6` | `#17243A` | Grouped metadata and alternating rows |
| `--border` | `#CBD5E1` | `#3B4A63` | Dividers and component outlines |
| `--text` | `#102033` | `#EDF2F7` | Primary text |
| `--text-muted` | `#526174` | `#AEBBD0` | Secondary text; never below 12 px |
| `--info` | `#0B5CAD` | `#7AB8FF` | Observed information and links |
| `--verified` | `#087F6D` | `#59D6BA` | Verified, matched, and reconciled process state |
| `--attention` | `#8A4B08` | `#F6C66D` | Stale, pending, degraded, and operator attention |
| `--critical` | `#B42318` | `#FF9188` | Integrity mismatch and frozen writes only |
| `--model` | `#6941C6` | `#C4A7FF` | Bounded model output |
| `--focus` | `#1D4ED8` | `#93C5FD` | Keyboard focus ring |

Status backgrounds use a 10–14% tint of their semantic foreground over the current surface. Text remains the semantic foreground; white text is not placed on these tinted backgrounds. Direction uses `Bullish ↑`, `Bearish ↓`, or `Neutral —` plus text; it does not receive a separate red/green semantic system.

Every foreground/background combination used in text, icons, focus rings, and charts must pass automated WCAG 2.2 AA contrast checks. The token table is the approved visual direction; a failed contrast check is corrected at the token level, not with a one-off component color.

### 20.2 Typography

| Token | Size/line | Weight | Use |
|---|---:|---:|---|
| `--type-caption` | 12/16 px | 500 | Labels, provenance, absolute secondary time |
| `--type-body-sm` | 14/20 px | 400 | Dense metadata and table content |
| `--type-body` | 16/24 px | 400 | Narrative and primary explanations |
| `--type-label` | 14/20 px | 600 | Buttons, tabs, status labels |
| `--type-h3` | 20/28 px | 650 | Panel headings |
| `--type-h2` | 24/32 px | 650 | Section heading |
| `--type-h1` | 32/40 px desktop; 28/36 px mobile | 700 | One page title |
| `--type-mono` | 12/18 px | 500 | IDs, hashes, symbols, prices, timestamps, codes |

The sans stack is `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`; the implementation must fall back cleanly without downloading a font. The mono stack is `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`.

### 20.3 Spacing, shape, and motion

- Spacing scale: `4, 8, 12, 16, 24, 32, 48, 64` px.
- Page gutters: 32 px desktop, 24 px tablet, 16 px mobile.
- Panel padding: 24 px desktop, 20 px tablet, 16 px mobile.
- Panel gap: 24 px desktop, 16 px tablet/mobile.
- Radius: 6 px controls, 10 px panels, pill radius only for short status labels.
- Border: 1 px semantic border; 2 px for current workflow node and selected tab.
- Shadow: `0 1px 2px rgb(16 32 51 / 8%)`; authority and critical state rely on structure/border, not stronger shadows.
- Focus ring: 3 px `--focus` with 2 px surface offset.
- Motion: 120–180 ms opacity/background transitions only. No price ticks, pulsing status, celebratory animation, or parallax.
- `prefers-reduced-motion: reduce` removes nonessential transitions and animated scrolling.

## 21. Responsive layout redlines

### 21.1 Desktop — 1024 px and above

- Left rail: 224 px fixed within the viewport; content scrolls independently only when required.
- Content: fluid, maximum 1240 px, centered within remaining width.
- Global shell: product/environment on the first row; mode, execution, reconciliation, access, and demo selector on the second row when width is below 1280 px.
- Status safety facts: four equal columns, minimum 180 px each.
- Evidence: chart spans 7/12 columns and data-quality summary 5/12; evidence table then spans all columns.
- Memo: narrative 7/12 and metadata/ablation 5/12; stacks when either column would be below 360 px.
- Authority: horizontal lineage only when every node can retain a minimum width of 136 px; otherwise use the vertical form.
- Outcome: lifecycle 7/12 and position/risk summary 5/12; reconciliation spans all columns.

### 21.2 Tablet — 736–1023 px

- Remove the left rail; use a sticky, horizontally scrollable tab row with visible focus and selected state.
- Safety facts use two columns; all primary content sections stack.
- Tables may remain tabular only when each required column fits at 14 px without truncating the meaning. Otherwise use record cards.
- Authority lineage is vertical with a persistent boundary label between intent and request.
- Chart minimum height is 280 px.

### 21.3 Mobile — 360–735 px

- Header order: product, access/environment, demo selector, safety summary, navigation tabs.
- Demo selector is a full-width native/select-style control; it is not a three-column segmented control at 360 px.
- Safety facts are a single list with 44 px minimum rows.
- Evidence, reconciliation, and order tables become labeled record cards. The label precedes the value in DOM order.
- Workflow and authority rails are vertical. Skipped stages remain visible but compact.
- Chart height is 240 px. Preserve time and price axes; remove optional annotations before reducing text size.
- Long IDs wrap only inside an expanded details region; the collapsed row uses first 8 and last 6 characters.
- No sticky bottom order/control area exists in judge view.

At every breakpoint, environment, execution state, reconciliation, and selected demonstration must be visible before the first trade or model detail.

## 22. Interaction specification

### 22.1 Navigation and selection

- A primary-view navigation event changes the path and retains the `demo` query parameter.
- Changing the demonstration retains the current primary view when that view exists for all three records.
- The selected demonstration and primary view are server-addressable. Copying the URL reproduces the same public state.
- HTMX swaps only the main content and updated shell fields. It pushes history, updates the document title, moves focus to the new `h1`, and announces the view change in a polite live region.
- Browser Back/Forward restores the route, demonstration, title, focus target, and scroll position where practical.

### 22.2 Details and copy

- Provenance, full hashes, and UTC timestamps use native disclosure semantics or an accessible dialog when comparison requires overlay.
- `Copy` writes only the redacted public value. After activation, its accessible label becomes `Copied` for two seconds without moving layout.
- Tooltips supplement visible labels; they never contain essential risk, state, or authority information.
- The uncalibrated-confidence explanation is available by keyboard, pointer, and touch and is also present in nearby visible copy.

### 22.3 Refresh and connectivity

- Frozen records have no polling, loading shimmer, or live indicator.
- Authenticated current-run pages may poll read-only database endpoints every 15 seconds. Polling pauses when the document is hidden and resumes with an immediate freshness check.
- During refresh, existing verified content remains visible with `Updating…`; it is not replaced by skeletons.
- A failed refresh changes the shell to `Showing last verified state`, preserves the last timestamped record, and disables authenticated controls.
- A browser/network timeout during a control request displays `Result unknown · reconciling`; it never displays `Failed` until server-side reconciliation establishes that result.

### 22.4 Empty, error, and authorization behavior

| Condition | Public treatment | Required action |
|---|---|---|
| No accepted demo records | `Demonstration evidence is not available yet` | Link to project limitations; render no invented metrics |
| Record not found | `Record unavailable` | Return to Status with the same valid demo selection |
| Stale/disconnected | Keep last verified data and absolute timestamp | Mark all non-current fields and explain skipped actions |
| Confidential field omitted | `Redacted by public export policy` | Do not leave an unexplained blank |
| Unauthorized operator route | `Operator access required` | No preview of controls or confidential state |
| Reconciliation mismatch | Critical integrity panel | Keep mismatch visible; never collapse it into a generic error toast |
| Model timeout/malformed/refusal | Advisory panel with explicit status | Show deterministic fallback/refusal and downstream skips |

Critical execution-state changes use an assertive live region once. Repeated polling does not re-announce an unchanged state.

## 23. Route and component handoff

| Route | Page composition | View model | Mandatory variants | Forbidden presentation |
|---|---|---|---|---|
| `/` | Global shell, outcome headline, safety facts, workflow rail, decision summary, readiness, disclosure | `ShellView` + `StatusView` | qualified, refusal, recovery, disconnected | P&L hero, order button, unlabeled live-looking fixture |
| `/decisions/{id}/evidence` | Snapshot header, data quality, completed-bar chart, evidence list/table, setup, baseline comparison | `ShellView` + `EvidenceView` | usable, stale, missing, provider error, forming-bar excluded | Model prose before evidence, same-bar fill implication |
| `/decisions/{id}/memo` | Authority notice, memo, evidence/counter-evidence references, invalidation, metadata, ablation | `ShellView` + `MemoView` | available, timeout, malformed, provider refusal, not requested | Hidden reasoning, confidence as probability, risk sizing control |
| `/decisions/{id}/authority` | Hash lineage, checks, boundary label, terminal refusal or recovery reconciliation | `ShellView` + `AuthorityView` | complete, no authority, expired, ambiguous, mismatch, reconciled | Editable intent, raw broker payload, retry action |
| `/decisions/{id}/outcome` | Action/refusal headline, strategy/legs, timeline, risk/results, reconciliation, limitations | `ShellView` + `OutcomeView` | closed lifecycle, refusal, active recovery, recovered | Aggregated P&L without stressed result, `success` claim |

### 23.1 Shared component contracts

| Component | Required input | Output behavior |
|---|---|---|
| `SafetyStrip` | environment proof, mode, execution state, reconciliation, freshness | Always names each state; expands to proof timestamp and redacted identifiers |
| `DemoSelector` | selected demo, available frozen records | Changes only the selected record and URL; never initiates evaluation |
| `WorkflowRail` | ordered transitions and terminal stage | Shows reached/current/refused/skipped; missing stages are not inferred |
| `EvidenceRecord` | stable ID, family, direction, value/summary, source and timing | Links to memo references; stale/missing states include reason and consequence |
| `BaselineComparison` | same-snapshot baseline and model-assisted result | Compares result, evidence fidelity, abstention, latency, and cost without declaring model superiority |
| `HashLineage` | typed lineage nodes and boundary | Uses absent-by-design nodes for refusal and explicit ambiguity/mismatch states |
| `LifecycleTimeline` | append-only timestamped events | Separates deterministic, model, broker, operator, and incident events |
| `ReconciliationMatrix` | source, local state, broker state, observed time, status | Never derives `matched` in the browser |
| `DisclosureStrip` | Paper/feed/no-alpha limitations | Remains adjacent to any result; cannot be dismissed permanently |

Page templates may format values but may not calculate policy approval, reconciliation, P&L, risk, hashes, freshness, or lifecycle truth.

## 24. Approved public copy mappings

Backend reason codes remain stable machine values. The view model supplies an approved public label and explanation; templates do not convert arbitrary strings with title casing.

| Machine value | Public label | Public explanation |
|---|---|---|
| `stale:option_chain` | `Option chain is stale` | `The observed option data exceeded the permitted age, so evaluation stopped before model or broker access.` |
| `no_qualified_setup` | `No qualified setup` | `Completed-bar evidence did not satisfy the frozen trend/retest definition.` |
| `thesis_neutral` | `Model abstained` | `The bounded memo did not support a directional thesis; no structure or authority was created.` |
| `thesis_direction_outside_setup` | `Model contradicted the qualified direction` | `Deterministic policy refused the memo instead of allowing it to reverse the setup.` |
| `thesis_changed_deterministic_invalidation` | `Model changed a protected condition` | `The memo altered deterministic invalidation, so evaluation stopped.` |
| `no_eligible_spread` | `No eligible defined-risk spread` | `The observed chain did not contain a spread satisfying the frozen selection policy.` |
| `non_paper_account` | `Paper verification failed` | `The account was not verified as Paper, so evaluation stopped and writes remained disabled.` |
| `NO_NEW_RISK` | `New risk blocked` | `Entries and risk-increasing replacements are blocked while reconciliation continues.` |
| `FREEZE_ALL_WRITES` | `All broker writes frozen` | `An integrity incident blocks every broker write pending operator resolution.` |

Unknown reason codes render as `Unmapped reason code` plus the redacted stable code and are treated as a release defect in frozen demonstrations.

## 25. Design-to-development entry checklist

The frontend may enter implementation when all boxes below are true:

- [x] Five routes and their primary questions are fixed.
- [x] Qualified, refusal, and recovery narratives are fixed.
- [x] Public interaction and authority boundaries are fixed.
- [x] Visual tokens, type, spacing, shape, and motion are fixed.
- [x] Desktop, tablet, and mobile transformations are specified.
- [x] Navigation, selection, refresh, disclosure, focus, and error behavior are specified.
- [x] Route/component/view-model boundaries are specified.
- [x] Accessibility, privacy, redaction, and forbidden presentations are specified.
- [ ] Trading/Risk has supplied or approved the final qualified and refusal fixture payloads.
- [ ] Backend/QA has supplied the accepted Paper lifecycle and recovery evidence records.
- [ ] Product has approved any final event-required sponsor wording and public limitations copy.

The final three items do not block construction with visibly labeled design fixtures. They block removal of the `Design fixture` label and release of the public demonstration.
