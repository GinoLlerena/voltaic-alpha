# Options Alpha Agent

## Architecture Slice v0.1

*First executable architecture boundary for deterministic ETF-options decisions*

| Field | Value |
|---|---|
| Version | 0.1.3 |
| Date | 27 August 2026 |
| Status | Executable architecture baseline aligned to the hackathon H0 vertical slice |
| Scope | Decision snapshot through approved or rejected spread candidate |
| Execution | Deliberately absent |
| Legacy compatibility | Existing event-fixture interaction lab remains unchanged |
| Implementation plan | [Bot Implementation Plan](./options_alpha_bot_implementation_plan_v0_1.md) |
| Requirement tracker | [Requirements Traceability Matrix](./options_alpha_requirements_traceability_v0_1.md) |

## 1. Purpose

This slice turns the implementation plan into executable boundaries without pretending that the trading strategy, model contribution, or broker lifecycle is validated. It provides production-facing contracts and an explicit workflow for an auditable execution firewall demonstrated with one SPY trend/retest strategy.

The existing `ExperimentCase` path remains a compatibility lab. New production work must target `options_alpha_lab.architecture` and must not add provider or expected-answer fields to the domain contracts.

## 2. Architectural invariants

1. `DecisionSnapshot` contains observations, provenance, timestamps, account state, and data quality; it never contains an expected direction or expected decision.
2. Every timestamp is timezone-aware, and no account, signal, or option observation may be newer than the decision snapshot.
3. Only a Paper account is eligible for the decision workflow.
4. The deterministic setup classifier supplies the allowed directional envelope.
5. The thesis synthesizer may agree or return `neutral`; it cannot reverse the qualified setup.
6. The thesis synthesizer cannot replace deterministic setup invalidation.
7. Thesis and setup evidence references must exist in the supplied snapshot.
8. A selected spread strategy must agree with the qualified direction.
9. An approved maximum loss cannot exceed its recorded risk budget.
10. `neutral`, unusable data, missing setup, missing structure, or a risk veto terminates as `NO_TRADE`.
11. The options selector and Risk Governor remain deterministic ports.
12. The workflow is bounded and ordered; it has no open-ended agent loop.
13. No broker execution dependency exists in this slice.
14. Agent skills, chat confirmation, CLI commands, MCP tools, and dashboard actions cannot create execution authority; only a future immutable approved intent may cross the broker boundary.
15. Paper mode must be proven from the actual loaded configuration and resolved endpoint at startup and immediately before every future write; a status label, variable name, profile name, or account payload is not proof.
16. PostgreSQL will be the authoritative lifecycle store. Filesystem run packages are derived confidential/redacted exports and cannot substitute for reconciliation state.
17. Hackathon H0 has one tradeable underlying (`SPY`), one mirrored trend-continuation/retest setup, one vertical-debit-spread structure family, and at most one open or pending strategy.
18. Every H0 model evaluation has a deterministic no-LLM baseline on the same frozen input. Model confidence is not a calibrated probability and cannot be presented as incremental value without comparative evidence.

## 3. Component boundary

```text
MarketDataGateway
       |
       v
DecisionSnapshot + DataQuality
       |
       v
SetupClassifier (deterministic)
       |
       v
ThesisSynthesizer (bounded LLM adapter later)
       |
       v
OptionsSelector (deterministic)
       |
       v
RiskGovernor (deterministic veto)
       |
       +---- reject ----> NO_TRADE
       |
       v
OPTIONS_POSITION recommendation
       |
       v
DecisionRepository / AuditSink

Future, separately gated extension:
Approved immutable intent -> exact request mapper/hash -> execution-state and
resolved-Paper checks -> Alpaca Paper gateway -> reconciliation
```

The workflow ends at a recommendation. This prevents architecture work from silently enabling Paper writes before idempotency, reconciliation, execution-state controls, and lifecycle tests exist.

### 3.1 Future execution-adapter obligations

The reviewed Alpaca backtest, generic Paper, CLI, and MCP skills are advisory sources. They do not become runtime dependencies of this slice. A future execution adapter must:

1. accept only `ApprovedOrderIntent`, never free-form agent, chat, dashboard, scheduler, or skill input;
2. verify intent hash/TTL, deterministic client ID, `paper_execute`, loaded trading enablement, durable execution state, options level, and the resolved Paper endpoint immediately before a write;
3. serialize one native combined MLeg limit request with project-approved `day` TIF, bounded parent strategy quantity, simplified leg ratios, and explicit open/close position intents;
4. persist the exact prepared-request hash and dry-run result before submission;
5. query by `client_order_id` and reconcile orders, activities, fills, and positions before retrying any ambiguous write;
6. keep MCP toolsets read-only and treat a version-pinned CLI only as an operator diagnostic/cross-check, never as the application order path; and
7. write authoritative lifecycle state to PostgreSQL. Any raw filesystem export is confidential, any shareable report is separately redacted, and the export root must be ignored by version control before creation.

## 4. Package layout

| Module | Responsibility |
|---|---|
| `architecture/contracts.py` | Versioned domain values, snapshots, decisions, workflow states, and invariants |
| `architecture/ports.py` | Provider-neutral interfaces for market data, setup, thesis, options, risk, audit, and persistence |
| `architecture/workflow.py` | Explicit fail-closed decision sequence and transition trace |
| `tests/test_architecture.py` | Boundary, authority, look-ahead, neutral, evidence, and veto tests |
| Legacy `models.py`, `agents.py`, `risk.py`, `orchestrator.py` | Original synthetic interaction experiment; compatibility only |

## 5. Production contracts

### 5.1 Decision snapshot

`DecisionSnapshot` is the immutable input boundary. It includes:

- schema version and snapshot ID;
- decision timestamp and normalized symbol;
- observed underlying price;
- timestamped Paper account equity and options buying power;
- family-classified signals with stable IDs and provenance;
- timestamped option observations with feed and optional liquidity metadata;
- explicit missing, stale, and provider-error fields.

Expected outcomes, future observations, hidden post-decision outcomes, and LLM-generated prices are forbidden.

### 5.2 Setup and thesis

`SetupCandidate` is deterministic and directional. It identifies one permitted P0 setup family, references snapshot evidence, and declares invalidation.

`Thesis` is the bounded synthesis output. It contains direction, normalized confidence, evidence and counter-evidence references, invalidation, and a concise summary. Confidence is metadata and never bypasses later gates.

### 5.3 Options and risk

`SpreadCandidate` describes one bull-call or bear-put debit-spread candidate with explicit contract symbols, quantity, debit, and calculated maximum loss. The future deterministic selector remains responsible for contract lookup, DTE/delta/liquidity eligibility, geometry, and reproducible ranking.

`RiskDecision` carries approval, stable reason codes, risk budget, recalculated maximum loss, and policy version. The workflow treats rejection as terminal.

## 6. Workflow states

| Stage | Owner | Failure result |
|---|---|---|
| `OBSERVED` | Workflow/input boundary | `NO_TRADE` on data-quality or non-Paper account failure |
| `QUALIFIED` | Deterministic setup classifier | `NO_TRADE` when no setup or unknown evidence is referenced |
| `THESIS_READY` | Bounded thesis synthesizer | `NO_TRADE` on neutral, unknown evidence, or direction reversal |
| `STRUCTURE_READY` | Deterministic options selector | `NO_TRADE` when no eligible spread exists |
| `RISK_REVIEWED` | Deterministic Risk Governor | `NO_TRADE` on any veto |
| `DECIDED` | Workflow | `OPTIONS_POSITION` or `NO_TRADE` in this slice |

Every reached stage produces a `WorkflowTransition`. An `AuditSink` can persist transitions without changing domain behavior.

## 7. Validation-suite role

The narrative validation suite is the target acceptance catalog, not executable input. It must be converted to timestamped fixtures that separate:

- `decision_snapshot`, visible to the system;
- test oracle, visible only to assertions;
- `post_decision_outcome`, hidden until replay scoring.

The H0 fixture increment contains exactly two SPY cases:

1. one mechanically qualified trend/retest snapshot that can produce an eligible vertical debit spread; and
2. one stale, contradictory, or illiquid snapshot that must terminate as `NO_TRADE` before execution.

Both cases run through a deterministic no-LLM baseline and the bounded thesis synthesizer. Broader bullish, bearish, transition, extended, breakout, and portfolio cases remain in the acceptance catalog but do not expand H0.

## 8. Post-H0 learning and review architecture

This section describes product evolution and is not part of the seven-day H0 cut. H0 retains immutable inputs/outcomes and a one-time ablation report but does not implement recommendation generation, automated policy promotion, champion/challenger operation, or scheduled learning jobs.

### 8.1 Governance model

Use a hybrid loop:

- observation capture, outcome enrichment, deterministic scoring, scheduled reports, incident detection, and recommendation generation are automatic;
- recommendation approval, policy promotion, code changes, and resuming after critical incidents are manual;
- rollback alarms are automatic, while rollback execution follows the configured safety policy and is always audited.

The system may propose a change but must not rewrite code, prompts, thresholds, or active policies by itself. An LLM may summarize evidence and suggest hypotheses; deterministic code owns measurements, eligibility checks, replay comparisons, promotion gates, and active configuration.

### 8.2 Review triggers

| Trigger | Automatic work | Required human work |
|---|---|---|
| Every decision | Verify trace completeness, input freshness, evidence references, authority boundaries, policy version, and latency | Review only on a hard violation or low-confidence diagnostic |
| Trade exit or declared decision horizon | Attach outcome, realized/stressed P&L, MFE/MAE, invalidation result, and execution quality without changing the original decision | Classify ambiguous outcomes and incident attribution |
| End of session | Produce trade, `NO_TRADE`, risk, data-quality, execution, and incident summaries | Review exceptions and sign the daily audit |
| Rolling sample threshold | Compare performance by setup, regime, feed, policy, model, and failure reason | Decide whether the sample supports a tuning experiment |
| Risk/data/execution incident | Freeze or restrict new risk according to policy and produce an immediate diagnostic package | Approve remediation and resumption when required |
| Candidate policy or prompt | Run frozen replay, stress, regression, and compatibility suites | Approve, reject, or request more evidence |

Time alone must not trigger a policy change. Scheduled reviews generate evidence; promotion requires a sufficiently relevant sample or a demonstrated correctness defect.

### 8.3 Review pipeline

```text
Immutable decision journal
        |
        v
OutcomeEnricher
        |
        v
DecisionEvaluator
        |
        v
Diagnostic / RecommendationEngine
        |
        v
EvaluationRunner on frozen data
        |
        v
Manual PromotionController approval
        |
        v
Shadow candidate -> controlled promotion
        |
        v
Monitoring -> retain or rollback
```

Required components:

| Component | Responsibility |
|---|---|
| `OutcomeEnricher` | Attach later market, position, and execution outcomes while preserving the original snapshot |
| `DecisionEvaluator` | Calculate deterministic process, outcome, risk, and execution scores |
| `ReviewScheduler` | Run horizon, end-of-session, sample, and incident reviews idempotently |
| `RecommendationEngine` | Produce evidence-backed proposals without applying them |
| `EvaluationRunner` | Compare current and candidate versions on frozen replay/stress datasets |
| `PolicyRegistry` | Store immutable policies, prompts, models, parent versions, hashes, effective times, and rollback targets |
| `PromotionController` | Enforce authorization, evidence requirements, shadow mode, activation, and rollback |
| `ReviewRepository` | Persist reviews, recommendations, evaluations, approvals, and promotion history |

### 8.4 Process quality and outcome quality

Review the decision process separately from its result. Every completed review must classify one of:

1. good process and favorable outcome;
2. good process and unfavorable outcome;
3. defective process and favorable outcome;
4. defective process and unfavorable outcome;
5. correct `NO_TRADE`;
6. missed opportunity with a valid ex-ante setup;
7. outcome not yet measurable or not attributable.

Process scoring covers data integrity, setup classification, evidence independence, counter-evidence, deterministic invalidation, option eligibility, risk compliance, and authority boundaries. Outcome scoring covers thesis horizon, MFE/MAE, realized and stressed P&L, exit quality, slippage, and whether the original invalidation occurred.

P&L alone must never label a decision good or bad. Reviews must attribute errors separately to data, setup, thesis synthesis, options selection, risk policy, execution, position management, or external/unmeasurable causes.

### 8.5 Recommendation lifecycle

Recommendations use stable states:

```text
PROPOSED -> VALIDATING -> VALIDATED -> APPROVED -> SHADOW -> ACTIVE
     |            |           |           |          |
     +--------> REJECTED <-----+-----------+----------+
                                             |
                                             +-> ROLLED_BACK
```

Every recommendation records:

- affected component and configuration path;
- current and proposed values or behavior;
- supporting and contradicting decisions;
- dataset, horizon, evaluator, policy, prompt, model, feed, schema, and code versions;
- sample size, uncertainty, regime coverage, and known biases;
- replay/stress/regression results and hard failures;
- expected benefit, risk, owner, approver, activation condition, and rollback target.

### 8.6 Configuration versus code

The application must not be recreated for normal tuning. Versioned configuration and stable ports support changes to risk percentages, DTE/delta bands, schedules, allowlists, model selection, reasoning effort, and prompts. Every loaded policy is schema-validated and attached to decisions.

Code changes remain mandatory for new signal semantics, setup families, provider mappings, domain schemas, risk invariants, execution behavior, or defect correction. Such changes require a new code/schema version and the full regression suite; they cannot be smuggled in as configuration.

### 8.7 Missing safeguards now made explicit

The earlier design contained persistence and replay but did not fully specify:

- outcome horizons and when a result becomes measurable;
- process-versus-outcome classification;
- `NO_TRADE` counterfactual review without look-ahead leakage;
- signal, risk, execution, and exit attribution;
- minimum sample relevance, uncertainty, regime coverage, and multiple-testing/overfitting controls;
- reviewer authorization, disagreement resolution, and append-only approval history;
- champion/challenger shadow evaluation and deterministic rollback targets;
- idempotent review jobs, retention rules, and schema migration for historical comparisons.

These are required architecture concerns, not optional analytics. For the short hackathon window, produce automatic daily and incident reports but keep policy promotion manual and conservative. Use the broader frozen replay corpus as the primary tuning evidence because Paper-trade samples will be small.

## 9. Next architecture increments

### Increment 2: Fixture and policy boundary

- Define a JSON loader for `DecisionSnapshot` plus a separate test-oracle schema.
- Convert one qualified SPY case and one refusal case to internally consistent fixtures.
- Add configurable H0 policy objects; keep uncalibrated thresholds explicitly provisional.
- Add the single deterministic trend/retest classifier and one non-duplicative confirmation.

### Increment 3: Read-only SPY data, deterministic options, and risk

- Map SPY account/bars, complete option snapshots, and dated contract metadata with feed/timestamp lineage.
- Add DTE, delta, freshness, spread, liquidity, geometry, and ranking rules.
- Replace fake test ports with deterministic implementations.
- Add the H0 one-strategy and per-trade risk-policy matrix.

### Increment 4: Bounded Terra synthesis and ablation

- Implement the `ThesisSynthesizer` port with the Responses API.
- Exclude oracle fields and raw hidden outcomes from input.
- Require strict structured output and validate all evidence references.
- Fail closed on refusal, timeout, malformed output, or provider failure.
- Compare the same frozen cases with a deterministic no-LLM baseline and record fidelity, counter-evidence, abstention, latency, and cost.

### Increment 5: Paper execution boundary

- Introduce immutable order intents only after the decision pipeline is stable.
- Add `NORMAL`, `NO_NEW_RISK`, and `FREEZE_ALL_WRITES` enforcement.
- Replace constant configuration-status claims with parsed loaded-value checks and resolved-Paper endpoint proof.
- Implement exact dry-run request mapping/hash, deterministic client IDs, native MLeg strategy quantity/ratios/intents, ambiguous-submit lookup, and reconciliation before Paper submission.
- Keep MCP trading disabled; permit a version-pinned CLI only in the operator runbook for discovery/read-only inspection/dry-run cross-checks.
- Define confidential and redacted derived-export contracts and ignore the export root before any raw account/order artifact is created.

### Increment 6: Hosted evidence experience

- Expose health/readiness and read-only trace endpoints.
- Show five views: mode/health, evidence and deterministic baseline, bounded model memo, approval/request hash lineage, and reconciled Paper outcome or refusal.
- Include one Paper lifecycle, one refusal, and one ambiguous-write/restart recovery trace.
- Keep controls authenticated and make feed/Paper/no-alpha limitations visible.

### Increment 7: Post-H0 review and policy promotion

- Add immutable outcome, review, recommendation, evaluation-run, and policy-version contracts.
- Implement horizon and end-of-session review scheduling with idempotency.
- Add deterministic process/outcome scoring and attribution.
- Implement a versioned policy registry, manual promotion records, shadow comparison, and rollback targets.
- Keep automatic activation and self-modification disabled.

## 10. Slice acceptance

This architecture slice is accepted when:

- all legacy tests still pass;
- architecture tests prove the invariants above;
- production snapshots contain no expected-answer fields;
- failures stop downstream component calls;
- Risk Governor rejection cannot be converted to a trade by orchestration;
- no order-submission implementation or trading credential path is introduced.
