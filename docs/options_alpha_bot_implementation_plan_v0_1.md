# Options Alpha Agent

## Bot Implementation Plan

*Implementation plan for a paper-trading directional options agent with structured AI reasoning and deterministic risk controls*

| Field | Value |
|---|---|
| Version | 0.1.5 |
| Date | 27 August 2026 |
| Status | Active hackathon vertical-slice plan; adversarial scope review incorporated |
| Trading environment | Alpaca Paper only during the hackathon |
| Default LLM | `gpt-5.6-terra` through the OpenAI Responses API |
| Primary design | [Trading System Design Specification](./options_alpha_trading_design_v0_1.md) |
| Requirement tracker | [Requirements Traceability Matrix](./options_alpha_requirements_traceability_v0_1.md) |
| Executable architecture | [Architecture Slice v0.1](./options_alpha_architecture_slice_v0_1.md) |
| External review | Claims are preserved in Section 3.2 as advisory dispositions; the named source artifact is not present in this repository and cannot serve as release evidence |
| Alpaca skill review | [Alpaca Trading API skills](https://github.com/alpacahq/alpaca-skills/tree/main/skills/trading-api), advisory patterns only; no runtime skill installed |

## 1. Purpose

This document converts the trading design and the current interaction lab into an executable delivery plan. It defines the implementation boundary, selected technology, component contracts, phases, tests, deployment shape, and hackathon deliverables.

The bot is not intended to let an LLM freely trade. The AI layer interprets a bounded evidence pack and produces a schema-constrained thesis. Deterministic code owns data eligibility, setup recognition, option construction, position sizing, portfolio limits, execution permission, order state, and exits.

The hackathon product is an **auditable AI execution firewall demonstrated through one bounded SPY options strategy**. Its defensible claim is that model-assisted trading decisions can be constrained, reproduced, challenged, and reconciled from evidence through broker state. Positive directional alpha is a hypothesis to test, not a prerequisite claim and not the primary product promise.

The target user is a team building an AI-assisted trading application that needs an inspectable boundary between model reasoning and brokerage authority. The business-value story is safer integration, faster incident reconstruction, and evidence that an agent cannot bypass deterministic policy—not guaranteed returns.

## 2. Source and requirement confidence

The plan uses the following source hierarchy:

1. The supplied [Alpaca AI Trading Agents Hackathon page](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon).
2. The existing trading design, which records the project's chosen options strategy and Paper-only safety boundary.
3. The [lablab.ai guide](https://lablab.ai/guide) and [submission guidelines](https://lablab.ai/ai-articles/hackathon-guidelines) for general platform deliverables.
4. Current official Alpaca and OpenAI documentation for platform capabilities.
5. Official Alpaca agent skills as advisory operating patterns, checked against current product documentation and project trust boundaries.
6. Executable evidence in this repository.
7. External review documents as hypotheses to validate, never as self-authorizing specifications.

The public event page was re-verified on 27 August 2026. It confirms an online build from 28 August through 4 September 2026, use of Alpaca's Paper environment, and a sponsor stack described through the Trading API, MCP server, and CLI. It lists Application of Technology, Presentation, Business Value, and Originality as judging criteria. It does **not** publish P&L as a judging criterion or confirm that options are mandatory. The exact submission cutoff/timezone, account/reset rules, whether every named sponsor interface is mandatory, autonomy expectations, and any separate leaderboard remain organizer-confirmation items.

Do not import rules from the separate 2026 Kraken/ERC-8004 AI Trading Agents event. It is a different competition.

## 3. Definition of done

The hackathon vertical slice is done when all of the following are true:

1. It runs one complete `observe -> qualify -> thesis -> structure -> risk -> paper order -> reconcile -> close` lifecycle for SPY and replays the same evidence without placing a second order.
2. It produces `NO_TRADE` without calling the execution path when evidence, data quality, option quality, account state, or risk state fails.
3. The demonstration persists the evidence snapshot, model output, deterministic checks, approved intent, exact prepared-request hash, broker response, reconciliation state, and close result with timestamps and correlation IDs.
4. The LLM cannot submit, alter, replace, cancel, or close an order directly.
5. Every paper order is a combined multi-leg limit order with an idempotent client order ID and a recorded pre-trade risk approval.
6. Restarts reconcile broker positions and open orders before new decisions are allowed.
7. A hosted judge-facing dashboard shows five concise views: health/mode, evidence and deterministic baseline, bounded model memo, approval/request lineage, and reconciled Paper outcome or refusal.
8. An ablation report compares the bounded LLM path with the deterministic no-LLM baseline on evidence fidelity, counter-evidence detection, abstention, malformed output, latency, and cost. It does not claim trading improvement without evidence.
9. Offline tests, one frozen replay, the exact-request dry run, one ambiguous-submit/restart recovery test, and one opt-in Paper lifecycle pass in CI or a documented release check.
10. The public repository, reproducible setup, hosted demo, pitch video, slide deck, submission metadata, and recorded fallback are complete.

### 3.1 Pre-build inconsistency and clarification gate

The prototype, trading design, and implementation plan are not yet one consistent specification. The following items must be resolved before feature implementation begins. Foundation work such as repository setup and CI may proceed, but market logic, production schemas, and order execution should not be built against unresolved assumptions.

| Clarification | Current inconsistency or ambiguity | Project decision or remaining proof |
|---|---|---|
| Event rules | The public event page is now accessible and confirms dates, Paper use, the named Alpaca stack, and four qualitative judging dimensions; account, autonomy, exact cutoff, and any leaderboard details remain open. | Record the verified facts now and confirm only the remaining details in the enrolled dashboard/Discord. Do not retain stale `NEEDS_CONFIRMATION` wording for public facts. |
| Seven-day schedule | The event is confirmed for 28 August through 4 September 2026. | Use the seven-day vertical-slice schedule in Section 9 and protect the final day as integration/submission buffer. |
| Trading universe | The event permits several asset classes and does not publicly require options. The earlier plan attempted three ETFs while the lab uses individual equities. | Trade only SPY in hackathon H0. QQQ/IWM may supply contextual observations but become tradeable only after H0 is stable. Keep individual equities test-only/deferred. |
| Strategy identity | The lab is event/earnings-oriented; the design contains two ETF setup families and broader regime logic. | H0 implements one mirrored trend-continuation/retest setup and one vertical-debit-spread structure family. Breakout/breakdown and event strategies are deferred. |
| Core state contract | `ExperimentCase` contains event date, days until event, expected direction, and free-text evidence; the design requires timestamped family evidence, setup, counter-evidence, horizon, freshness, and source quality. | Approve a versioned production schema and define a compatibility/migration boundary for the interaction-lab fixtures. |
| Meaning of the live test | The live test fetches Alpaca account, stock snapshot, and option-chain count, but the decision still uses synthetic underlying price, synthetic evidence, synthetic option quotes, and synthetic equity. | Rename it as connectivity/contract validation. Add a distinct live-data shadow acceptance test that maps Alpaca payloads into production inputs. |
| Account equity source | Live Alpaca account status is checked, but position sizing uses fixture equity. | Paper sizing must use a fresh timestamped Alpaca account snapshot. Add a test proving fixture equity cannot enter `recommend` or `paper_execute`. |
| Thesis authority | The test gives the LLM an expected direction and confidence and requires them to be copied; this does not validate thesis formation. | Deterministic features establish setup eligibility and the allowed directional envelope. Terra may synthesize, agree, or abstain but cannot reverse it. Remove expected answers from production input. |
| Neutral state | The design permits bullish, bearish, or neutral theses; the code `Direction` enum only supports bullish and bearish, with `NO_TRADE` produced later by risk. | Add `neutral` as a thesis result and terminate it as `NO_TRADE` before option selection. |
| Evidence threshold | The design calls several mostly price-derived families independent and assigns uncalibrated weights; code requires only two unique free-text strings. | H0 requires objective structure plus at least one non-duplicative confirmation and explicit counter-evidence. Treat score weights and the 0.65 threshold as experimental, not calibrated confidence. |
| DTE policy | The design target is approximately 14-35 DTE; the validation suite says preferred 21-45 DTE; the fixture permits 14-45 DTE. | Evaluate hard 14-45/preferred 21-35 as a candidate, then freeze target and hard-reject bands from chain-coverage/replay evidence. Update policy, fixtures, tests, and dashboard together. |
| Per-trade risk | The design proposes approximately 0.75% standard and 1.0% hard cap; the fixture uses 0.5%. | Select one standard risk value and an explicit hard ceiling based on confirmed contest equity/scoring. Version the policy. |
| Portfolio policy | Total open risk, cluster risk, daily loss stop, and maximum positions are unvalidated product hypotheses. | H0 permits at most one open or pending strategy and a conservative owner-approved loss cap. Multi-position and cluster policy move to post-hackathon hardening. |
| Option selection | The design targets long delta 0.55-0.70 and short delta 0.25-0.40; code selects the nearest same-expiration strikes and does not filter delta. | Delta, freshness, liquidity, debit/width, and deterministic tie-breaking are required. Validate exact thresholds and the availability/timestamp of open interest and volume before freezing them. |
| Market-data entitlement | The test uses IEX and indicative options, while the design assumes quote/Greeks quality suitable for trading. OPRA access is unknown. | Support labeled feed-specific policies. Indicative data may support observe/recommend and controlled Paper evaluation; automated Paper eligibility still requires measured quality and team approval. |
| Signal definitions | Regime, relative strength, breadth, trend, retest, breakout, extension, freshness, and event-safety concepts are described but not mathematically specified. | Specify only the H0 SPY trend/retest formula, one confirmation, timestamps, freshness, and missing-data behavior. Defer the remaining signal taxonomy. |
| Component mapping | The design names six responsibility components; the lab implements thesis, options, risk, and arbiter; the plan proposes one explicit state machine. | Treat the six names as logical responsibilities in one state machine. Only thesis synthesis uses an LLM in P0; other responsibilities are deterministic modules. |
| Alpaca integration path | The public event page explicitly presents the Trading API, MCP server, and CLI, but does not make the exact required combination clear. The current test uses raw HTTP. | H0 visibly uses read-only MCP evidence, deterministic `alpaca-py` Trading API execution, and a version-pinned CLI doctor/dry-run release artifact. The CLI and MCP still cannot create order authority. Confirm whether this satisfies organizer expectations. |
| Autonomy and approval | The current configuration disables trading; the target plan includes paper execution; event rules on autonomy/human approval are unverified. | Freeze the allowed runtime mode and operator approval boundary before any write credential is enabled. |
| Exit thresholds | Exit categories exist in the design, but exact loss, profit capture, time-stop, conviction-decay, and expiry thresholds are not frozen. | Approve deterministic exit formulas and their precedence before an opening paper order can be enabled. |

Each row is tracked as `CLR-001` through `CLR-020` in the traceability matrix. A clarification is resolved only when:

1. The decision and authoritative source are recorded.
2. The trading design is updated if strategy or policy changed.
3. The implementation plan and traceability row agree with the decision.
4. Affected fixtures and tests have explicit migration tasks.
5. One owner is accountable for the resulting implementation and acceptance proof.

The clarification gate is split to avoid circular sequencing:

1. **Before feature work:** confirm eligibility, build-window/code rules, Paper-only scope, SPY/one-setup cut line, and that no model/tool can create execution authority. Data adapters and replay plumbing may then proceed with explicitly provisional policy values.
2. **Before any Paper write:** resolve account/options permissions, actual endpoint and mode proof, H0 signal and option rules, conservative risk/exit limits, exact MLeg mapping, idempotency, and reconciliation. Replay, chain-coverage, and dry-run evidence produced by earlier phases is allowed—and required—to close these items.

Unresolved product-scale portfolio, learning, and tuning policies do not block the hackathon vertical slice because those capabilities are not in H0.

### 3.2 Adversarial disposition of the external v0.2 review

The external document calls itself authoritative and says it overrides v0.1. That instruction is rejected: authority belongs to the team, organizer rules, accepted project documents, and executable evidence. Its claims were checked against the repository and current official Alpaca/OpenAI documentation before incorporation.

Disposition labels are `ACCEPT`, `ACCEPT_WITH_CHANGES`, `PROVISIONAL`, `UNVERIFIED`, and `REJECT`.

| ID | External-review claim | Disposition | Project conclusion |
|---|---|---|---|
| `REV-001` | The external document overrides v0.1. | `REJECT` | It is an advisory input. No statement becomes a requirement merely because the review labels it `RESOLVED`. |
| `REV-002` | The competition runs 28 August to 4 September 2026 and the named event is confirmed. | `ACCEPT_WITH_CHANGES` | The public event page was re-verified on 27 August 2026. Dates, online format, Paper environment, sponsor stack, and qualitative rubric are now public facts; exact cutoff/timezone, account/autonomy details, and any separate leaderboard remain open. |
| `REV-003` | P0 is SPY/QQQ/IWM, two ETF setup families, and debit spreads; individual equities and earnings are test-only/deferred. | `ACCEPT_WITH_CHANGES` | ETF/debit-spread direction is retained, but H0 is narrower: SPY only, one mirrored trend/retest setup, and one vertical-debit-spread structure family. QQQ/IWM execution and breakout/breakdown are post-H0. |
| `REV-004` | Split the existing live test into connectivity validation and a real-input shadow decision test; never size a paper decision from fixture equity. | `ACCEPT` | Repository inspection confirms the current live test fetches providers but decides from synthetic fixture inputs. A timestamped Alpaca account snapshot is mandatory for `paper_execute`. |
| `REV-005` | Remove expected answers from production LLM input, support neutral abstention, and keep financial authority deterministic. | `ACCEPT` | Expected direction/confidence are test-oracle fields, not production evidence. `neutral` terminates as `NO_TRADE` before option selection. |
| `REV-006` | Six agent names are logical responsibilities; only thesis synthesis needs an LLM; use `alpaca-py` for deterministic production adapters. | `ACCEPT_WITH_CHANGES` | Adopt the component mapping and SDK path. MCP stays optional/read-only unless organizer rules require it; raw HTTP remains test-only. |
| `REV-007` | A native MLeg is one strategy unit, so tests should not model two independently submitted legs. | `ACCEPT_WITH_CHANGES` | Alpaca defines `mleg` as a combined order and parent `qty` as strategy units. Still persist parent and leg states, handle partially filled strategy quantity, and halt new risk on any broker/account ambiguity; do not assume reconciliation is unnecessary. |
| `REV-008` | The normal kill switch must allow cancels and risk-reducing exits. | `ACCEPT` | Replace the single all-write blocker with `NORMAL`, `NO_NEW_RISK`, and exceptional `FREEZE_ALL_WRITES` states. |
| `REV-009` | Proposed cadence, formulas, TTLs, DTE/delta/liquidity thresholds, risk percentages, replace rules, and exit thresholds are resolved defaults. | `PROVISIONAL` | These are coherent starting hypotheses, not demonstrated edge. Freeze them only after replay, boundary, stress, data-availability, and Paper-behavior evidence. |
| `REV-010` | Basic/indicative data is sufficient, and open-interest/volume gates can be enforced as written. | `ACCEPT_WITH_CHANGES` | Indicative data can support observe/recommend and controlled Paper evaluation with prominent feed labels. Option-chain snapshots provide quote/trade/Greeks; open interest comes from contract metadata. Make volume conditional until a reliable source and timestamp contract are proven. |
| `REV-011` | One operator enablement permits autonomous `paper_execute` without per-order approval. | `UNVERIFIED` | Keep `recommend` as default. Autonomy remains a team safety and organizer-rule decision under `CLR-019`. |
| `REV-012` | The validation suite needs ETF-only P0 cases and corrected partial-fill semantics. | `ACCEPT_WITH_CHANGES` | H0 uses only one qualified SPY case and one SPY refusal with separate oracles; the AAPL/TSLA/NVDA cases remain outside H0. Retain the corrected native-MLeg partial-strategy-quantity and ambiguous-reconciliation semantics. |
| `REV-013` | Use a manually reviewed competition-week event calendar for P0. | `PROVISIONAL` | This is a pragmatic bounded source if ownership, provenance, effective dates, timezone, and stale/missing behavior are specified and tested. |

### 3.3 Candidate policy registry

The following values were useful enough to retain for evaluation, but none is an approved production threshold yet. The versioned policy must store each accepted value and its evidence.

| Candidate area | External-review proposal | Acceptance evidence required |
|---|---|---|
| Entry cadence | Finalized 15-minute bars only; compute the signal after bar `t` closes; the earliest eligible entry uses the first observable quote or bar in `t+1`; entries 09:45-15:15 ET; monitor every 5 minutes | Replay across normal, open, close, early-close, and volatile sessions; prove that same-bar fills and forming-bar inputs are rejected; API budget and scheduler tests |
| Freshness | Account 30 s, clock 60 s, bar 90 s after close, OPRA option 30 s, indicative option 120 s, evidence 5 min, approval 90 s | Provider timestamp mapping, delayed-data tests, and measured Paper latency |
| Signals/setups | Daily EMA20/EMA50, 5/20-session returns, 15-minute ATR14; ATR/volume-based retest, breakout confirmation, and extension veto | Formula specification, no-look-ahead unit tests, replay sensitivity, and comparison against simpler baselines |
| Options | Hard 14-45 DTE, preferred 21-35; long delta 0.55-0.70; short delta 0.25-0.40; spread and debit/width limits | Chain coverage study by Tier-1 ETF/feed, rejection-rate report, payoff checks, and boundary tests |
| Liquidity | Open interest >= 500; prior-session volume >= 50 when available | Verified source/observation timestamp for each field; no fail-open substitution when unavailable |
| Risk | 0.50% transition, 0.75% standard, 1.00% exceptional; 3% total; 1.5% cluster; 2% daily stop; three positions | Replay/stress loss distribution, contest account/scoring confirmation, pending-order reservation, and policy-owner approval |
| Entry lifecycle | Midpoint start, bounded movement toward natural, 20-second replace interval, three attempts, 90-second TTL | Paper fill experiment, idempotency/reconciliation tests, and adverse-price bound |
| Exits | 50% debit loss, staged 60%/75% profit capture, time/conviction/event/DTE exits | Historical/replay sensitivity study, precedence matrix, conservative liquidation marking, and lifecycle tests |
| Event safety | T-60 through T+30 minute blackout and two completed bars after an event | Reviewed event-source contract, timezone tests, missing-calendar fail-closed behavior, and replay cases |

Policy adoption is a separate decision from architecture adoption. A plausible number remains `PROVISIONAL` until its acceptance evidence is attached to the traceability matrix.

### 3.4 Disposition of Alpaca Trading API agent skills

The official [Alpaca Trading API skills](https://github.com/alpacahq/alpaca-skills/tree/main/skills/trading-api) were reviewed at commit `62891ec` on 26 August 2026. They are useful operating references, but they are generic instructions for an interactive AI agent and do not replace this project's domain contracts, durable state, or release gates.

| Skill | Disposition | Adopted patterns | Project-specific limits |
|---|---|---|---|
| `alpaca-trading-backtest` | `ACCEPT_WITH_CHANGES` | Formal strategy specification, explicit fill timing, look-ahead controls, raw/normalized data fingerprints, run lineage, fee/slippage assumptions, benchmarks, and reproducible reports. | Its V1 reference supports stocks and crypto, not options. Do not adopt its default run-specific single-file engine; build a reusable options-spread replay path on frozen project contracts. |
| `alpaca-trading-paper-trading` | `ACCEPT_WITH_CHANGES` | Paper-environment proof, account/permission/contract checks, exact order preview, client-order idempotency, ambiguous-submit lookup, lifecycle monitoring, and Paper limitations disclosure. | Risk controls cannot be optional or waived, and conversational confirmation cannot replace an immutable approved order intent or durable execution state. |
| `alpaca-trading-paper-trading-cli` | `OPERATOR_ONLY` | `alpaca doctor`, installed-schema discovery, `--dry-run`, structured output, exit-code handling, and lookup by `client_order_id` are useful for diagnostics and release smoke tests. | The CLI is Alpha Preview. Pin the tested version and keep it outside the production `BrokerGateway`; no scheduler or agent may invoke CLI order submission directly. |
| `alpaca-trading-paper-trading-mcp` | `REJECT_FOR_EXECUTION` | Tool discovery and least-privilege toolset guidance reinforce the read-only MCP configuration. | The LLM must not receive the `trading` toolset. An open MCP client-interoperability issue affects MLeg `legs` arrays, and even a fixed tool would still violate the project trust boundary. |

Cross-cutting decisions from the review:

1. A skill is guidance, not authority. Installing or invoking a skill cannot enable writes, bypass `RiskGovernor`, create an approval, or change `BOT_MODE` or durable execution state.
2. Prove the actual resolved Paper endpoint at startup and immediately before every write. A configured variable name, profile name, account-number prefix, or status message is not sufficient proof.
3. Persist and review the exact native-MLeg request before submission. The request uses a bounded parent strategy quantity, simplified leg ratios, explicit position intents, a combined limit price, and the project-approved `day` TIF.
4. Generate a deterministic `client_order_id` for each logical attempt. After a timeout or other ambiguous result, query by that ID and reconcile before any retry.
5. PostgreSQL is the authoritative lifecycle store. Optional `runs/` exports are derived artifacts, must be classified as confidential or redacted, must include hashes/lineage, and must be ignored by version control before creation.
6. Paper P&L and stressed execution P&L remain separate because Paper does not model market impact, latency slippage, queue position, price improvement, regulatory fees, or dividends.
7. Every intraday signal must declare its completed-bar contract: provider and feed, `America/New_York` session/calendar including early closes, adjustment mode, timeframe, source and receipt timestamps, bar-finalization delay, pagination/completeness checks, and fail-closed behavior for missing, late, corrected, or forming bars. A rolling statistic excludes the current signal bar unless a versioned formula explicitly proves otherwise.
8. Replay and Paper evaluation use decision-time execution semantics: a signal calculated only after bar `t` is finalized may fill no earlier than the first eligible observable quote or bar in `t+1`. Same-bar fills are prohibited, and the recorded result must identify the quote/bar used plus spread, slippage, latency, and missed-fill assumptions.

### 3.5 Adversarial scope correction

The plan does not treat its trading or product claims as established facts.

| Claim | Classification | H0 treatment |
|---|---|---|
| Alpaca supports Paper accounts, option data, and native combined MLeg orders. | Platform fact, subject to current account permissions and feed entitlement. | Verify through current official contracts and one reviewed Paper lifecycle. |
| Deterministic authority, request hashes, idempotency, and reconciliation reduce software-caused execution ambiguity. | Strong engineering inference. | Make this the main product demonstration and preserve negative tests. |
| Context, structure, and participation convergence improves short-horizon directional outcomes. | Unvalidated trading hypothesis. | Compare against declared simple baselines; do not describe it as alpha without out-of-sample evidence. |
| A bounded LLM improves the decision process. | Unvalidated AI hypothesis. | Run a deterministic-versus-LLM ablation. Require measurable improvement in evidence synthesis, counter-evidence detection, or correct abstention; narrative quality alone is insufficient. |
| Paper results approximate deployable performance. | Weak inference. | Label the feed, separate broker Paper P&L from stressed execution P&L, and avoid live-performance claims. |
| “LLM + guardrails + dashboard” is original. | Rejected as a differentiator. | Differentiate with evidence-to-intent-to-request hash lineage, reproducible refusal, ambiguous-write recovery, and an explicit model ablation. |

The null hypotheses are first class: a deterministic baseline may match or outperform the LLM-assisted path, the strategy may not beat a simple benchmark after friction, and the correct hackathon result may be a safe refusal rather than a trade. H0 must make those outcomes visible rather than conceal them.

## 4. Current baseline and gap analysis

| Area | Present in the repository | Missing for the bot |
|---|---|---|
| Domain contracts | Legacy experiment dataclasses plus production-facing timestamped snapshots, signals, option observations, thesis, spread, risk, decision, and workflow contracts | Portfolio state, immutable order intents, orders, fills, positions, exits, and versioned policy values |
| Thesis | Fixture adapter and opt-in OpenAI schema-preserving live test | Production thesis service using real evidence, prompt versioning, fail-closed behavior, evals |
| Option construction | Bull call and bear put debit-spread construction | Full live-chain mapping, delta/DTE filters, quote freshness, scoring, deterministic tie-breaking |
| Risk | Per-trade risk budget, quote checks, geometry checks, evidence and invalidation checks | Portfolio exposure, correlation clusters, daily stop, concurrency cap, event safety, kill switch |
| Orchestration | Legacy bounded quantity revision plus an explicit production decision workflow with fail-closed data, account, setup, thesis, option, and risk gates | Persistence, provider implementations, retries, scheduling, restart recovery, monitoring and exits |
| Alpaca | Read-only live test for account, NVDA stock snapshot, and indicative option chain | Typed adapter in `src`, pagination, clock/calendar, bars, positions, orders, trade updates, reconciliation |
| Execution | Deliberately absent | Paper-only multi-leg limit order gateway, idempotency, replace/cancel policy, fill handling |
| Persistence | In-memory result only | Durable audit database and migrations |
| Interface | Fixture CLI | Control API and judge-facing dashboard |
| Quality | 36 deterministic tests across the legacy lab and production architecture boundary, plus one opt-in live integration test | Adapter, replay, broker sandbox, lifecycle, recovery, load, CI, lint, type, and deployment tests |
| Operations | Secure local `.env` generator, Paper and trading-disabled defaults | Configuration status currently reports Paper/trading flags as constants rather than verifying the loaded values or resolved endpoint; production secrets, health checks, structured logs, alerts, artifact classification, deployment, rollback and runbook remain |

The NVDA earnings fixture is a contract test only. It does not change the ETF-first strategy in the trading design.

## 5. Technology decisions

### 5.1 Selected stack

| Concern | Technology | Decision and rationale |
|---|---|---|
| Language | Python 3.11+ | Matches the existing package and both provider ecosystems. Use one runtime for domain, worker, API, and tests. |
| Packaging | `uv` with `pyproject.toml` and a committed lockfile | Fast reproducible setup and dependency locking. |
| Domain schemas | Pydantic 2 plus `Decimal` | Versioned validation at every provider and API boundary. Preserve exact financial arithmetic. |
| Web/API | FastAPI and Uvicorn | Typed health, control, trace, decision, position, and metrics endpoints. |
| Persistence | PostgreSQL 16, SQLAlchemy 2, Alembic | Durable audit history, transactions, constraints, and hosted deployment support. |
| Scheduler | APScheduler plus Alpaca market clock/calendar | Sufficient for one hackathon worker without adding Redis or Celery. Jobs must use database leases. |
| Alpaca deterministic adapter | Official `alpaca-py` SDK | Typed market-data and Trading API integration behind project-owned interfaces. |
| Alpaca agent tools | Alpaca MCP Server V2, read-only toolsets only | Demonstrates sponsor technology without exposing order tools to the LLM. Start with `account,assets,stock-data,options-data,news`. |
| Operator diagnostics | Version-pinned Alpaca CLI, optional | Use only for schema discovery, `doctor`, read-only inspection, request `--dry-run`, and a rehearsed release smoke test. It is not the production broker adapter or an unattended order path. |
| LLM | Official OpenAI Python SDK, Responses API, `gpt-5.6-terra` | Structured outputs, configurable reasoning effort, and model override. Set `store=False`. |
| Dashboard | FastAPI server-rendered Jinja2, HTMX, and Plotly | One deployable Python application with live operational views and no separate frontend build. Implement the judge/operator boundary, five-view information architecture, component states, and responsive behavior from [Frontend Design v0.1](./options_alpha_frontend_design_v0_1.md). |
| HTTP resilience | SDK retry controls plus bounded exponential backoff | Retry only safe reads and explicitly idempotent writes. |
| Logging | Python logging with JSON formatting and correlation IDs | Machine-readable audit and deploy logs without a large observability stack. |
| Tests | `pytest`, existing `unittest` compatibility, `pytest-asyncio`, and mocked provider clients | Preserve existing tests while adding fixtures, adapters, replay, and async coverage. |
| Quality | Ruff, mypy, coverage.py, pip-audit, and detect-secrets | Fast CI gates for correctness and secret leakage. |
| Delivery | Docker, Docker Compose for local Postgres, GitHub Actions, one always-on container host | Reproducible local and hosted environments. The host is selected after event resource confirmation. |

### 5.2 Explicit non-choices

- Do not add LangGraph, CrewAI, or another general agent framework for the MVP. The workflow is small, bounded, and safety-sensitive; an explicit state machine is easier to test and explain.
- Do not add Celery, Kafka, or Redis until one worker and database-backed leases are demonstrably insufficient.
- Do not expose the Alpaca MCP `trading` toolset to the LLM. A deterministic broker gateway is the only order path.
- Do not install a generic Alpaca paper-trading skill as runtime write authority. Agent prompts, previews, or confirmation settings cannot substitute for an approved intent and execution-state check.
- Do not make the Alpha-preview Alpaca CLI a production or scheduled order dependency. If used operationally, pin and record the tested version.
- Do not implement live-money trading, 0DTE, naked options, credit spreads, earnings-event strategies, or autonomous policy mutation.
- Do not use model output for prices, Greeks, quantity, maximum loss, account equity, order status, or P&L.
- Do not create local raw account/order run folders until their path is ignored by version control and their confidential/redacted retention contract is defined.

### 5.3 Platform constraints that affect the design

- Alpaca Basic market data provides IEX coverage for equities and the indicative feed for options. The plan must label the feed and treat it as a competition/demo limitation, not consolidated-market truth. See [About Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api).
- The option-chain endpoint returns quotes, trades, and Greeks, supports filters, and is paginated. The adapter must consume `next_page_token` and reject incomplete chains. Open interest is exposed on option-contract metadata; do not assume the chain snapshot supplies it or that prior-session volume is always available. See [Option chain](https://docs.alpaca.markets/us/reference/optionchain) and [Alpaca-py option-contract models](https://alpaca.markets/sdks/python/api_reference/trading/models.html#optioncontract).
- Multi-leg spreads use `order_class: "mleg"` with a `legs` array and explicit position intents. Parent `qty` is the number of strategy units; leg quantities are ratios. Use combined limit orders to reduce legging risk, while retaining parent/leg state reconciliation and partial-strategy-quantity handling. Current options orders use `day` time in force. See [Options Level 3 Trading](https://docs.alpaca.markets/us/docs/options-level-3-trading) and [Create an Order](https://docs.alpaca.markets/us/reference/createorderforaccount).
- Paper trading does not model market impact, latency slippage, queue position, price improvement, regulatory fees, or dividends. Evaluation must report stressed execution separately. See [Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading).
- Alpaca MCP Server V2 exposes read and trading tools and defaults to Paper. Toolset filtering is required to keep the model read-only. See [Trading MCP Server](https://docs.alpaca.markets/us/docs/alpaca-mcp-server).
- Alpaca's CLI is an Alpha Preview and must be discovered at runtime and pinned for any release evidence. Its dry-run and client-order-ID lookup are useful independent diagnostics, not a stable application boundary. See [Trading CLI](https://docs.alpaca.markets/us/docs/alpacas-cli).
- The Alpaca backtest skill V1 supports stocks and crypto and says options require explicit contract selection and fill logic. Reuse its reproducibility contract, but implement option-chain, spread valuation, exercise/assignment, expiry, and quote-aware fills in project-owned replay code. See [Trading API Backtesting skill](https://github.com/alpacahq/alpaca-skills/tree/main/skills/trading-api/backtest).
- The Alpaca MCP paper-trading skill cannot prove that an MCP tool is Paper from the account payload alone, and the current MCP server has an open client-interoperability report for MLeg arrays. These reinforce, rather than relax, the read-only MCP decision. See [issue #97](https://github.com/alpacahq/alpaca-mcp-server/issues/97).
- OpenAI Docs list `gpt-5.6-terra` as supporting the Responses API and Structured Outputs. See [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra).

## 6. Target architecture

```text
Alpaca Market Data / MCP read-only
              |
              v
      Market Data Gateway
              |
              v
   Snapshot + Evidence Builders -------> Audit Store
              |                              ^
              v                              |
  Deterministic Setup Classifier             |
              |                              |
              v                              |
 OpenAI Thesis Synthesizer ------------------+
              |
              v
 Deterministic Options Selector
              |
              v
 Deterministic Risk Governor
       | reject       | approve
       v              v
    NO_TRADE     Order Intent + Hash
                       |
                       v
              Paper Execution Gateway
                       |
                       v
              Alpaca multi-leg order
                       |
                       v
        Reconciler + Position Monitor
                       |
                       v
              Deterministic Exit Intent
                       |
                       v
              Paper Execution Gateway

FastAPI/Dashboard reads control state and the audit store; it does not bypass
the risk governor or execution gateway.
```

### 6.1 Trust boundaries

| Boundary | Allowed input | Required validation | Failure behavior |
|---|---|---|---|
| Alpaca -> domain | Account, clock, bars, snapshots, contracts, orders, positions | Pydantic schema, timestamps, feed label, pagination, symbol allowlist | Mark snapshot invalid and return `NO_TRADE` |
| Evidence -> OpenAI | Compact normalized evidence, counter-evidence, setup and freshness metadata | Remove secrets, cap size, version prompt and schema | Skip thesis or return `NO_TRADE` |
| OpenAI -> domain | Direction, confidence, evidence references, counter-evidence, invalidation | Strict structured output, enum/range/reference checks | Reject model output; never repair silently |
| Decision -> risk | Immutable snapshot, policy version, thesis, spread candidate | Recompute all prices, debit, width, max loss, exposures | Veto |
| Risk -> execution | Approved immutable order intent | Approval ID, intent hash, TTL, deterministic client ID, explicit mode/enablement, durable execution state, resolved Paper endpoint, exact native-MLeg mapping | Refuse order |
| Alpaca -> lifecycle | Order/fill/position updates | Broker ID, client ID, quantities, state transition validity | Freeze new entries and reconcile |

### 6.2 Core interfaces

The implementation should depend on project-owned protocols so provider code does not leak into trading logic:

```python
class MarketDataGateway(Protocol):
    def account_snapshot(self) -> AccountSnapshot: ...
    def market_clock(self) -> MarketClock: ...
    def bars(self, symbols: list[str], timeframe: str) -> list[Bar]: ...
    def option_chain(self, request: OptionChainRequest) -> OptionChainSnapshot: ...

class ThesisSynthesizer(Protocol):
    def synthesize(self, evidence: EvidencePack) -> Thesis: ...

class BrokerGateway(Protocol):
    def submit(self, approved: ApprovedOrderIntent) -> BrokerOrder: ...
    def replace(self, request: ReplaceRequest) -> BrokerOrder: ...
    def cancel(self, order_id: str) -> BrokerOrder: ...
    def open_orders(self) -> list[BrokerOrder]: ...
    def positions(self) -> list[Position]: ...
```

Provider adapters may be asynchronous, but the domain contracts must remain provider-neutral and serializable.

## 7. Runtime workflow

### 7.1 Startup and recovery

1. Load and parse validated configuration, resolve the effective Alpaca endpoint, and refuse startup unless Paper is proven; do not trust a profile/variable name or status label alone.
2. Connect to PostgreSQL and apply a migration compatibility check.
3. Fetch Alpaca account, clock, open orders, positions, and recent activities.
4. Reconcile local and broker state. Any unexplained difference moves the bot to `HALTED`.
5. Verify the kill switch, daily risk state, data feed entitlement, and options trading level.
6. Acquire the singleton worker lease.
7. Start observation only after health state becomes `READY`.

### 7.2 Decision cycle

1. Check market clock and the configured decision window.
2. Snapshot account and portfolio state.
3. Pull bars and breadth inputs for the allowed ETF universe.
4. Build family-level regime, structure, participation, and catalyst evidence.
5. Reject stale, missing, correlated, or contradictory evidence before the LLM call.
6. Recognize an allowed setup deterministically.
7. Call OpenAI only for bounded thesis synthesis with strict structured output.
8. Fetch a complete, filtered option chain for qualified symbols.
9. Select eligible bull call or bear put debit spreads deterministically.
10. Apply option-quality and portfolio-risk gates.
11. Persist `NO_TRADE` or an immutable approved order intent.
12. If paper execution is enabled, submit a combined limit `mleg` order through the broker gateway.

### 7.3 Order lifecycle

1. Generate `client_order_id` from strategy, decision ID, and attempt number.
2. Serialize the exact native-MLeg request, validate it against the approved intent, persist its hash, and pass a dry-run mapper test before submission is enabled.
3. Re-prove the resolved Paper endpoint, `paper_execute` mode, trading enablement, intent TTL/hash, options level, and durable execution state immediately before the write.
4. Submit only once for a given idempotency key.
5. If the result is ambiguous, query by `client_order_id`; do not retry until broker and local state prove the original request was not accepted.
6. Poll or stream order updates and persist every parent-order, leg, and filled-strategy-quantity transition.
7. Do not chase indefinitely. Use a bounded replace policy with a maximum attempt count and price limit derived from current quotes.
8. Cancel stale unfilled entries before the entry window closes.
9. Enter `NO_NEW_RISK` when broker state is ambiguous; keep cancellation and reconciled risk-reducing exits available.
10. Reconcile filled strategy units into position records before monitoring begins. Never infer two independent leg orders from a native MLeg parent.

### 7.4 Position and exit lifecycle

1. Persist the original evidence, thesis, invalidation, risk, fill, and expected horizon.
2. Refresh underlying, breadth, option quotes, account risk, and time-to-expiry.
3. Evaluate deterministic thesis invalidation, loss, profit capture, time stop, and expiry safety rules.
4. Create a close intent that passes portfolio and order-state validation.
5. Submit a combined multi-leg close order with explicit `sell_to_close` and `buy_to_close` intents.
6. Reconcile fills, calculate realized results, and close the audit lifecycle.
7. Never rewrite the original thesis after entry.

## 8. Functional requirement groups

The stable identifiers below are defined in detail in the companion tracker.

| Group | IDs | Outcome |
|---|---|---|
| Pre-build clarifications | `CLR-001` to `CLR-020` | One consistent, implementable specification |
| Hackathon and submission | `HK-001` to `HK-018` | Eligible, complete, judgeable submission |
| AI and orchestration | `AI-001` to `AI-010` | Bounded structured reasoning with deterministic authority |
| Data and signal system | `DATA-001` to `DATA-016` | Fresh, complete, traceable evidence and option snapshots |
| Risk and execution | `RISK-001` to `RISK-022` | Fail-closed paper execution with portfolio controls |
| Operations and lifecycle | `OPS-001` to `OPS-014` | Durable state, recovery, monitoring, dashboard, and health |
| Quality and release | `QA-001` to `QA-016` | Reproducible verification and deployment evidence |
| Learning and review | `LEARN-001` to `LEARN-012` | Outcome enrichment, governed recommendations, policy promotion, and rollback |

## 9. Delivery phases

The phases are dependency-ordered and sum to seven team-days. They deliberately exclude product-scale portfolio analytics, autonomous learning, broad strategy research, and a general backtesting platform. A phase may overlap presentation work, but its safety exit gate may not be bypassed.

### Phase 0: Verified event cut line - 0.25 day

**Goal:** record public facts and resolve only the decisions that can invalidate the build.

- Record the confirmed 28 August–4 September window, Paper environment, qualitative judging criteria, and required submission artifacts.
- Confirm the exact deadline/timezone, account/options eligibility, pre-existing-code rule, autonomy expectation, and whether the Trading API, MCP, and CLI must all appear in the submitted runtime.
- Freeze H0 to SPY, one mirrored trend-continuation/retest setup, and one vertical-debit-spread structure family.
- Assign one owner for the vertical slice, demo, and submission.

**Exit gate:** eligibility, Paper-only authority, build rules, H0 scope, and fallback interpretation are recorded. Uncalibrated trading thresholds remain explicitly provisional and do not block read-only work.

**Status: `COMPLETE`, 28 August 2026.** Recorded in the [Phase 0 record](./options_alpha_phase0_event_cut_line_v0_1.md), which is normative for the frozen H0 scope (§3), Paper-only authority (§4), ownership (§5), and the binding fallbacks `F-01` to `F-06` (§6). Five organizer confirmations remain open; each is covered by a fallback with a named replacement trigger and a bounded cost, so none blocks Phase 1.

### Phase 1: Executable vertical skeleton - 0.75 day

**Goal:** make one fixture travel through the production contracts into a durable decision trace.

- Add only the runtime dependencies required by the H0 path and commit the lockfile.
- Add validated `observe`, `recommend`, and `paper_execute` configuration with trading disabled by default.
- Add the minimum database schema for runs, snapshots, model calls, decisions, risk decisions, intents, prepared requests, orders, fills, positions, and audit events.
- Preserve the offline suite and convert one SPY qualified fixture plus one refusal fixture to separate snapshot/oracle records.
- Add one clean-checkout test command and CI job.

**Exit gate:** a clean checkout replays both fixtures, persists their traces, and contains no broker write implementation.

**Status: `COMPLETE`, 28 August 2026.** `uv run python -m options_alpha_lab.replay` takes `fixtures/h0/spy_qualified.snapshot.json` and `fixtures/h0/spy_refusal.snapshot.json` through the production workflow into `decisions`, `market_snapshots`, `signals`, `evidence_packs`, `theses`, `spread_candidates`, `risk_decisions`, and `audit_events`. Execution tables are created but asserted empty, and CI fails the build if order-submission symbols appear in `src/`. Deferred to Phase 2 with the read-only adapters: Alembic migrations, since the schema has no production data to migrate yet.

### Phase 2: Read-only SPY evidence and frozen replay - 1 day

**Goal:** replace synthetic values needed by the demonstration without building a general signal platform.

- Implement account, clock, SPY bars, option-contract metadata, and complete SPY option-chain reads.
- Record provider, feed, source/receipt time, freshness, pagination, and input hashes.
- Specify and implement one trend-continuation/retest classifier and one non-duplicative confirmation; QQQ/IWM may be context only.
- Freeze one qualified snapshot and one stale/contradictory refusal snapshot.
- Declare a simple price-only benchmark and the null hypothesis that the proposed setup has no advantage after friction.

**Exit gate:** the read-only path emits a reproducible H0 evidence pack or a reasoned refusal, with no expected answer visible to the system.

**Status: `COMPLETE`, 28 August 2026.** `ReadOnlyAlpacaClient` is GET-only by construction and is deliberately not built on `TradingClient`. `evidence.py` discards the forming session while the market is open, applies feed-specific freshness, and takes its confirmation from a different instrument than its structure signal. `freeze.py` writes a live observation plus a provenance manifest to `fixtures/h0/frozen/`, and the frozen file replays to an identical decision. The frozen H0 rule is [`SRC-SIGNAL`](./options_alpha_h0_signal_spec_v0_1.md), which also declares benchmark `B0` and null hypothesis `H0`.

### Phase 3: Bounded model memo, option mapping, and ablation - 1 day

**Goal:** show a meaningful but non-authoritative AI contribution.

- Implement the production `ThesisSynthesizer` with strict structured output, evidence references, counter-evidence, neutral abstention, `store=False`, timeout, and fail-closed behavior.
- Implement deterministic SPY vertical-debit-spread eligibility and tie-breaking from the complete chain.
- Run the same frozen cases through a deterministic no-LLM baseline and the bounded model path.
- Report evidence fidelity, counter-evidence detection, correct abstention, malformed/hallucinated output, latency, and cost.
- Do not claim the model improves trading performance unless the evidence supports that claim.

**Exit gate:** the model cannot change setup direction, calculated risk, option eligibility, or execution authority, and its incremental contribution is visible rather than assumed.

**Status: `COMPLETE`, 28 August 2026.** The model never receives the invalidation conditions and has no field to emit them: they are copied from the setup in code. A reversal is coerced to abstention rather than argued with. Every failure mode - timeout, HTTP error, malformed JSON, refusal, empty output - resolves to a neutral thesis and therefore a `NO_TRADE`. The ablation report at `artifacts/ablation_h0.json` shows the model changed no decision across three frozen cases, which is reported as the result rather than presented as a disappointment.

### Phase 4: Execution firewall and one Paper lifecycle - 1.25 days

**Goal:** prove the distinctive evidence-to-intent-to-request-to-broker boundary.

- Enforce one open or pending strategy, a conservative owner-approved loss cap, no averaging, and deterministic close rules for the demonstration.
- Implement immutable approved intents, TTL/hash, deterministic client IDs, and the exact native MLeg mapper.
- Prove the loaded Paper mode and resolved endpoint immediately before every write.
- Persist and review the prepared-request hash; cross-check one request with a pinned CLI dry run without allowing CLI submission.
- Submit one minimal Paper open/close lifecycle through `alpaca-py` only after dry-run review.
- Test client-ID lookup and reconciliation after one simulated ambiguous response or restart.

**Exit gate:** duplicate or ambiguous requests cannot create a second strategy, and local state reconciles with Alpaca before another entry is possible.

**Status: `COMPLETE`, 28 August 2026.** One Paper MLeg lifecycle filled and reconciled to flat; see `artifacts/h0_paper_lifecycle.md`. Six guards run immediately before every write rather than at startup, because the interesting failures develop between the two. The Paper-endpoint guard proved itself in practice by refusing a real submission when `resolved_endpoint` returned an enum member name instead of a URL.

### Phase 5: Five-view judge experience - 1 day

**Goal:** make the core proof understandable without exposing internal logs or hidden reasoning.

- Expose health/readiness plus read-only trace APIs.
- Build five views: mode/health, evidence and deterministic baseline, bounded model memo, approval/request hash lineage, and reconciled order/outcome or refusal.
- Display feed limitations, Paper versus stressed execution results, and the no-alpha-claim disclosure.
- Protect every control action and include a visible `NO_NEW_RISK` demonstration.

**Exit gate:** a judge can reconstruct the qualified or refused decision and see exactly where model authority ends.

### Phase 6: Validation, deployment, and narrative - 1 day

**Goal:** deploy the smallest credible product and align it to the published rubric.

- Run offline, frozen replay, ablation, exact-request, lifecycle, and recovery checks.
- Containerize and deploy the API/dashboard with durable storage and protected secrets.
- Prepare the business case for an execution/audit layer used by teams building agentic trading applications.
- Draft the deck and video around Application of Technology, Presentation, Business Value, and Originality.
- Demonstrate originality through hash-linked authority, reproducible refusal, recovery evidence, and the model ablation—not a generic “LLM plus guardrails” claim.

**Exit gate:** the hosted demo works in a clean session and the narrative makes no unsupported alpha, data-quality, or live-performance claim.

### Phase 7: Integration buffer and submission - 0.75 day

**Goal:** fix integration defects, rehearse, and submit; add no new product capability.

- Freeze code, configuration, prompts, policy, and demo data.
- Rehearse the live path, refusal path, recovery explanation, and recorded fallback.
- Finalize repository visibility, title, descriptions, tags, cover, video, deck, platform, and application URL.
- Recheck the submission form and event dashboard for last-minute rule changes.

**Exit gate:** every H0 artifact and link passes from a clean session, and the fallback video demonstrates the same released build.

## 10. Priority scope

### H0: hackathon must ship

- SPY only as a tradeable underlying; QQQ/IWM may be read-only context.
- One mirrored trend-continuation/retest setup.
- One vertical-debit-spread structure family: bull call for bullish and bear put for bearish.
- One frozen qualified case and one refusal case with separate test oracles.
- A deterministic baseline and bounded OpenAI thesis memo with a visible ablation.
- Alpaca read-only MCP evidence, deterministic `alpaca-py` Paper execution, and one pinned CLI doctor/dry-run artifact.
- One exact combined-limit MLeg open/close lifecycle, one ambiguous-write/restart recovery proof, and `NO_NEW_RISK`.
- Hash-linked evidence, approval, prepared request, broker state, and reconciled outcome.
- A five-view hosted dashboard, reproducible repository, video, deck, cover, descriptions, application URL, and fallback.

### P1: ship after H0 is stable

- QQQ and IWM as tradeable underlyings, then Tier 2 ETFs.
- Confirmed breakout/breakdown setup family.
- Streaming quotes/trade updates rather than bounded polling.
- Richer event/news evidence.
- Live dashboard updates and more detailed analytics.
- Model comparison evals against Luna or Sol.
- Multi-position total-risk, cluster-risk, and daily-loss policies.

### Deferred

- Individual equities and earnings strategies.
- 0DTE and same-day expiration.
- Credit, naked, calendar, condor, and volatility-neutral structures.
- Live brokerage execution.
- A general options backtesting platform and any claim of validated alpha.
- Automated outcome enrichment, scheduled reviews, recommendation generation, policy promotion, and champion/challenger operation.
- Self-modifying prompts, weights, thresholds, or risk policies.
- Large agent debates, long-term memory, and autonomous learning.
- Multi-account, multi-user, or high-frequency architecture.

## 11. Test strategy

| Layer | Required tests | Release evidence |
|---|---|---|
| Domain | Existing contracts plus all policy boundaries and state transitions | Deterministic unit suite |
| Schemas | Provider payloads, strict parsing, missing fields, numeric ranges, timestamps | Contract fixtures |
| Market data | Pagination, feed labeling, staleness, retries, 429, partial chains | Mocked adapter suite and opt-in live smoke |
| LLM | Structured output, evidence fidelity, counter-evidence, refusal, timeout, malformed output, plus deterministic no-LLM ablation | Offline fake, frozen-case comparison, and opt-in OpenAI eval report |
| Strategy | H0 trend/retest recognition, non-duplicative confirmation, extension veto, no-trade cases, and a declared simple benchmark | Frozen SPY qualified/refusal pair; broader replay is post-H0 |
| Options | Delta/DTE/liquidity filters, geometry, deterministic ranking | Chain fixture suite |
| Risk | H0 one-strategy cap, per-trade limit, allowlist, staleness, authority boundary, and halt state | Focused H0 policy matrix; portfolio/cluster/daily-loss matrices are P1 |
| Execution | Exact native-MLeg request mapping and hash, idempotency, dry run, ambiguous-submit lookup, duplicate suppression, replace/cancel limits | Mock broker, optional pinned-CLI cross-check, and Alpaca Paper lifecycle |
| Recovery | Restart with open order, filled order, unmatched position, provider outage | Failure-injection suite |
| Learning/review | Outcome isolation, review triggers, process/outcome attribution, recommendation lifecycle, policy promotion, shadow comparison, rollback | Frozen replay corpus and governance audit |
| Performance | One decision cycle within the agreed latency and provider budgets | Timed release run |
| Security | Secret scan, log/export redaction, verified Paper endpoint, disabled live endpoint, ignored confidential artifact paths | CI report |
| Demo | Hosted smoke test, link check, clean-session walkthrough | Release checklist and fallback recording |

Coverage percentage is not the acceptance target by itself. Critical safety branches require explicit behavioral tests even if overall line coverage is already high.

## 12. Data model and audit minimum

Create append-oriented records with UTC timestamps and schema versions. H0 implements only the records needed to reconstruct the frozen decision/refusal and one Paper lifecycle; the remaining records describe the post-hackathon product model:

- `runs`: runtime version, policy version, mode, start/end, health result.
- `market_snapshots`: provider, feed, source time, received time, payload hash.
- `signals`: family, direction, strength, confidence, freshness, source quality.
- `evidence_packs`: setup, aligned families, contradictions, invalidations, payload hash.
- `model_calls`: provider, model, prompt version, schema version, latency, token usage, status; never store secrets or hidden reasoning.
- `theses`: direction, confidence, evidence references, counter-evidence, invalidation.
- `spread_candidates`: legs, quotes, Greeks, debit, width, max gain/loss, rejection reasons.
- `risk_decisions`: policy inputs, each check, approval, budget, intent TTL.
- `order_intents`: immutable hash, idempotency key, desired limit, legs, approval reference.
- `prepared_order_requests`: exact serialized request, intent/hash match, adapter/schema version, dry-run result, preparation time, and expiry; no authorization headers.
- `broker_orders` and `fills`: provider IDs, client IDs, states, quantities, prices.
- `positions`: original thesis, open risk, cluster, lifecycle status.
- `exit_decisions`: trigger, evidence, order intent, realized outcome.
- `decision_outcomes`: decision horizon, observed path, MFE/MAE, realized/stressed P&L, invalidation result, execution quality, evaluator version.
- `decision_reviews`: process score, outcome score, classification, component attribution, reviewer, notes, review version.
- `recommendations`: affected component/config path, current/proposed behavior, evidence, uncertainty, state, owner, approval requirement.
- `evaluation_runs`: frozen dataset version, current/candidate versions, metrics, hard failures, regime coverage, reproducibility metadata.
- `policy_versions`: immutable configuration, parent version, schema/hash, effective time, status, rollback target.
- `policy_promotions`: recommendation, approver, source/target versions, shadow result, activation/rollback events.
- `audit_events`: actor/component, action, entity, prior/new state, correlation IDs.

Do not persist API keys, authorization headers, full `.env` content, or model hidden reasoning.

PostgreSQL is authoritative. Any filesystem run package is a derived export with a manifest and hashes. Raw account, order, activity, and position payloads are confidential; redacted reports are separate artifacts. The export root must be ignored by version control before the first export is created.

## 13. Configuration and safety modes

| Mode | Market reads | OpenAI | Paper order writes | Intended use |
|---|---:|---:|---:|---|
| `observe` | Yes | Optional | No | Adapter and data validation |
| `recommend` | Yes | Yes | No | Full decision shadow mode |
| `paper_execute` | Yes | Yes | Yes, gated | Competition paper trading |

Required controls:

- `ALPACA_PAPER_TRADE=true` is mandatory and validated against the actual loaded value and resolved endpoint at startup and immediately before every write. The current `configure_secrets.py --check` status text is not proof because it prints the expected Paper/trading values rather than parsing them.
- `ALPACA_TRADING_ENABLED=false` remains the default.
- `BOT_MODE` must be explicit; missing or unknown mode fails startup.
- A durable execution state controls write authority:

| Execution state | New/increased risk | Replace entry | Cancel | Risk-reducing close | Use |
|---|---:|---:|---:|---:|---|
| `NORMAL` | Allowed through all gates | Allowed through bounds | Allowed | Allowed | Normal Paper operation |
| `NO_NEW_RISK` | Blocked | Blocked except to reduce/cancel exposure | Allowed | Allowed after reconciliation | Primary trading halt, loss stop, stale data, or ambiguous state |
| `FREEZE_ALL_WRITES` | Blocked | Blocked | Blocked | Blocked | Exceptional adapter, credential, or endpoint integrity incident requiring operator intervention |

- Every execution method checks the durable state. `FREEZE_ALL_WRITES` must raise an incident because it can temporarily prevent risk reduction.
- An allowlist limits underlyings and structures.
- Policy, prompt, model, and code version are attached to every decision.
- Secrets are supplied by the deployment secret store, never committed or displayed.
- Paper and live credentials are never interchangeable or fallback alternatives. Credential replacement is an operator-controlled maintenance event; the application cannot regenerate, promote, or silently substitute credentials.

## 14. Operational runbook minimum

Before the market opens:

1. Verify deployment health, worker lease, clock, account status, buying power, options level, feed, open orders, positions, and kill switch.
2. Reconcile broker and local state.
3. Verify policy and universe versions.
4. Run a read-only data freshness check.

During the session:

1. Monitor stale data, provider errors, daily loss, open risk, rejected orders, and model latency.
2. Halt new entries on unexplained broker state, repeated API failures, database write failure, or risk-policy load failure.
3. Keep exits available only when state is reconciled; otherwise require operator review.
4. Trigger an incident review package on risk, data, execution, reconciliation, or authority-boundary violations; never activate a recommendation intraday automatically.

After the session:

1. Reconcile activities, orders, fills, positions, and P&L.
2. Enrich decisions whose declared horizon has completed and export the daily trade/`NO_TRADE`/incident review summary.
3. Review incidents and proposed recommendations without changing strategy thresholds during the competition unless a clear correctness defect is documented.
4. Run candidate changes only against frozen replay/stress data and record approval or rejection.
5. Back up the audit database and verify the next market calendar.

Credential rotation and recovery:

Alpaca's current [Paper onboarding guide](https://alpaca.markets/learn/start-paper-trading) states that the secret is available only when issued and that regenerating credentials invalidates the current pair. Rotation is therefore a stateful broker-integrity event, not a configuration edit.

1. Enter `NO_NEW_RISK`, pause the worker's order-write lease, and acquire the operator maintenance lock.
2. Reconcile activities, open orders, fills, and positions; confirm that no broker request is in flight. Cancel pending entries and do not invalidate credentials while an unreconciled position needs a risk-reducing action.
3. Enter `FREEZE_ALL_WRITES`, generate replacement **Paper** credentials, and write the one-time secret directly to the protected deployment secret store without printing, logging, prompting, or placing it in an artifact.
4. Replace the deployment secret atomically and rebuild the `alpaca-py` client. Never fall back to live credentials or a live endpoint when Paper authentication fails.
5. Verify through a read-only account request that the retired credentials are rejected and that the replacement credentials resolve the expected Paper endpoint and account. Check status, blocking flags, buying power, and options level without logging confidential payloads.
6. Reconcile activities, orders, fills, and positions again under the replacement credentials. Any mismatch keeps the system in `FREEZE_ALL_WRITES` or `NO_NEW_RISK` and opens an incident.
7. Record a redacted rotation audit event. Restore `NORMAL` only after endpoint, account, reconciliation, health, and worker-lease checks pass and an operator explicitly approves the transition.

## 15. Major risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Unproven directional edge is presented as fact | Credibility loss and misleading product claims | Declare the null hypothesis, compare with simple benchmarks, and describe results as diagnostic unless out-of-sample evidence supports a stronger statement |
| LLM is merely decorative | Weak Application of Technology score and unnecessary variability | Run a deterministic-versus-LLM ablation and require measurable evidence-synthesis, counter-evidence, or abstention value |
| Generic “agent plus guardrails” positioning | Low originality relative to other registered concepts | Lead with hash-linked execution authority, reproducible refusal, exact-request proof, and ambiguous-write recovery |
| Event rules remain ambiguous | Ineligible or mis-scoped submission | Phase 0 confirmation; keep uncertainty visible in tracker |
| Indicative option quotes differ from executable market | Misleading spread quality or P&L | Label feed, use conservative quote rules, stress fills, disclose limitation |
| LLM invents evidence | Unsafe or untraceable thesis | Evidence IDs, strict schema, reference validation, fail closed |
| Duplicate order after timeout/restart | Excess position risk | Deterministic client IDs, idempotency table, broker reconciliation |
| Partial or ambiguous broker state | Incorrect follow-up action | Combined `mleg`, persist parent/leg and filled strategy quantity, enter `NO_NEW_RISK`, reconcile before action |
| Paper fill optimism | Overstated performance | Separate broker P&L from stressed P&L and document omitted effects |
| Generic agent skill bypasses domain authority | An interactive prompt submits an order without a valid project approval | Skills remain advisory; only `BrokerGateway.submit(ApprovedOrderIntent)` can write, and dependency tests exclude direct CLI/MCP/SDK order access from AI code |
| CLI or MCP schema drift | A valid intent is serialized incorrectly or an MLeg array is rejected | Pin diagnostic versions, validate discovered schemas in release checks, keep SDK mapping authoritative, dry-run exact requests, and fail closed on mismatch |
| Raw run artifacts enter source control | Confidential account/order data leaks into the repository or submission | Ignore export roots before creation, separate confidential and redacted outputs, scan artifacts, and keep PostgreSQL authoritative |
| Too much scope | Unfinished core lifecycle | P0 freeze, Tier 1 universe, two setups, two structures, one worker |
| Dashboard work displaces bot safety | Polished but unsafe demo | Dashboard begins only after execution and recovery gates pass |
| Provider outage or rate limit | Missed observations or inconsistent state | Bounded backoff, caching, circuit breaker, `NO_TRADE`, health visibility |
| Credential leakage or invalid rotation | Account compromise, lost broker access, or accidental environment substitution | Secret store, redaction, owner-only local file, scanning, operator maintenance lock, Paper-only atomic replacement, retired/new credential proof, reconciliation, and rotation audit |

## 16. Decision log

Record changes to architecture or scope here and mirror requirement changes in the traceability matrix.

| Date | Decision | Reason | Requirements affected |
|---|---|---|---|
| 2026-08-19 | Keep an explicit state machine rather than add an agent framework | Small bounded workflow and deterministic safety are easier to test and explain | `AI-004`, `RISK-001` |
| 2026-08-19 | Use `gpt-5.6-terra` as the default model | Existing live test passed; selected balance of capability and cost | `AI-001` |
| 2026-08-19 | Keep Alpaca MCP read-only and execute through a deterministic gateway | Prevent the LLM from reaching order tools directly | `HK-006`, `RISK-014` |
| 2026-08-19 | Use PostgreSQL and one worker | Durable audit and restart recovery without distributed-system overhead | `OPS-001`, `OPS-004` |
| 2026-08-19 | Restrict P0 to Tier 1 ETFs and debit spreads | Matches the design and protects the seven-day delivery window | `DATA-005`, `RISK-011` |
| 2026-08-19 | Treat the external v0.2 review as advisory, not authoritative | Its event claims were not independently reproducible and its numeric policies lack validation evidence | `CLR-001`, `CLR-002`, `CLR-011` to `CLR-016`, `CLR-019`, `CLR-020` |
| 2026-08-19 | Use `NO_NEW_RISK` as the primary halt and reserve `FREEZE_ALL_WRITES` for infrastructure incidents | Blocking closes during an ordinary loss/data halt can trap exposure | `RISK-017`, `OPS-008` |
| 2026-08-19 | Model native MLeg fills in strategy units while retaining parent/leg reconciliation | This matches Alpaca's order contract without assuming broker state is infallible | `RISK-019`, `RISK-021`, `QA-010` |
| 2026-08-19 | Keep imported numerical policy values provisional until replay and stress evidence exists | Internal consistency is not evidence of trading robustness | `CLR-011` to `CLR-016`, `CLR-020`, `QA-008` |
| 2026-08-20 | Add a production architecture package while preserving the legacy interaction lab | Separates oracle-bearing fixtures from provider-neutral, timestamped contracts and lets architecture evolve without masking legacy regressions | `CLR-005`, `AI-004`, `AI-005`, `AI-008`, `DATA-004`, `QA-001`, `QA-006` |
| 2026-08-20 | Use automatic evaluation/recommendation with manual policy promotion | Preserves learning speed without allowing small samples, LLM suggestions, or noisy outcomes to mutate active risk behavior | `LEARN-001` to `LEARN-012`, `DEF-005` |
| 2026-08-26 | Treat Alpaca Trading API skills as advisory patterns, not runtime write authority | Their environment, idempotency, dry-run, lifecycle, and reproducibility patterns are useful, but their conversational authority and generic risk model are weaker than the project boundary | `RISK-001`, `RISK-014` to `RISK-021`, `OPS-001`, `OPS-003`, `OPS-013`, `QA-007`, `QA-009`, `QA-010` |
| 2026-08-26 | Keep the Alpaca CLI operator-only and MCP trading disabled | The CLI is Alpha Preview, MCP MLeg client interoperability is unresolved, and neither path should let the LLM or scheduler bypass the deterministic SDK gateway | `CLR-018`, `RISK-014`, `RISK-019`, `QA-004`, `OPS-014` |
| 2026-08-26 | Make PostgreSQL authoritative and classify filesystem run outputs as derived exports | The reviewed skills write raw account/order data to `runs/`; this project needs durable reconciliation and must prevent confidential artifacts from entering source control | `OPS-001`, `OPS-003`, `OPS-010`, `OPS-013`, `QA-011` |
| 2026-08-27 | Reframe H0 as an auditable execution firewall demonstrated by one SPY setup | The strategy has no demonstrated alpha, similar agent/guardrail concepts are common, and the published rubric rewards technology, presentation, business value, and originality rather than a stated P&L leaderboard | `HK-004`, `HK-005`, `HK-016`, `HK-017`, `AI-010`, `DATA-005`, `DATA-008` |
| 2026-08-27 | Split the clarification gate into pre-feature and pre-write gates | The previous gate required replay and lifecycle evidence before the phases that build those capabilities, creating a sequencing deadlock | `CLR-001` to `CLR-020`, `QA-005`, `QA-007`, `QA-009` |
| 2026-08-27 | Cut H0 to one tradeable underlying, one mirrored setup, one structure family, one lifecycle, one refusal, and one recovery proof | The previous phase estimates totaled eight days inside a seven-day event and attempted product-scale learning, portfolio, dashboard, and validation work | `DATA-005`, `DATA-008`, `RISK-007` to `RISK-010`, `LEARN-001` to `LEARN-012` |
| 2026-08-27 | Treat Paper credential rotation as a broker-integrity recovery workflow | Alpaca exposes a replacement secret once and invalidates the prior credential pair; an uncoordinated edit can interrupt risk reduction or accidentally substitute environments | `RISK-015` to `RISK-017`, `RISK-021`, `OPS-013`, `OPS-014` |
| 2026-08-28 | Close Phase 0 on binding fallbacks rather than on organizer answers | The organizers cannot be blocking dependencies for a seven-day build. Each open question instead gets one interpretation that is safe under every plausible answer, with a named replacement trigger and a bounded cost, so no unresolved choice becomes an implicit default | `CLR-001`, `CLR-018`, `CLR-019`, `HK-001` to `HK-008`, `DEC-001` to `DEC-004`, `DEC-006` |
| 2026-08-28 | Treat the submission deadline as 3 September 2026 23:59 GMT-5 and hold 4 September as buffer | The published window ends 4 September without a stated time or timezone; the earliest defensible reading costs nothing if the true deadline is later and survives an early cutoff | `HK-001`, `CLR-002` |
| 2026-08-28 | Make the pre-existing-code boundary auditable with a tagged baseline plus a reuse ledger instead of guessing the rule | If pre-existing code is permitted the ledger is honest documentation; if it is prohibited the ledger is the exact worklist, and eligibility is assessable without archaeology through the diff | `HK-008`, `DEC-001` |
| 2026-08-28 | Build the autonomous execution path with the operator approval boundary behind configuration | Satisfies a mandatory-autonomy reading and a human-approval reading with one durable, auditable approval state rather than two code paths | `HK-007`, `CLR-019`, `DEC-004` |
| 2026-08-28 | Assume the indicative option feed until OPRA entitlement is verified | The strictest data assumption is the safe default: an entitlement upgrade only tightens freshness thresholds and cannot invalidate a decision already recorded under the conservative policy | `CLR-015`, `DEC-006` |
| 2026-08-28 | Execute through the Alpaca Trading API and drop MCP from the H0 runtime | No published event material makes any Alpaca interface mandatory. A deterministic `alpaca-py` gateway is the project's central claim: execution authority stays in code that no model-reachable tool can touch. MCP remains available as a local read-only testing aid that contributes no decision input | `HK-006`, `CLR-018`, `DEC-002`, `RISK-014`, `RISK-019` |
| 2026-08-28 | Retire fallback `F-01` on the confirmed deadline of 4 September 2026 15:00 UTC | The live dashboard states the cutoff verbatim; the conservative fallback returned 3 September as a full build day, and the six-hour manual-submission window stays an emergency backstop rather than schedule | `HK-001`, `CLR-002` |
| 2026-08-28 | Treat the demo host as a constrained decision (`D-01`) rather than an open one | The platform mandates Streamlit, Replit, or Vercel, and none hosts an always-on Python worker well; the judge views and the decision worker can no longer be assumed to share a runtime | `HK-009`, `HK-011`, `DEC-005`, `OPS-004`, `SRC-UI` |
| 2026-08-28 | Derive the client order id from the intent hash instead of generating one | Idempotency has to be a property of the approved intent, not of a retry helper. The same intent can only ever produce the same id, so a duplicate submit collides at the broker instead of opening a second strategy | `RISK-018`, `RISK-020`, `QA-009` |
| 2026-08-28 | Resolve an ambiguous submit by client-id lookup and never by re-submitting | Re-submitting is how duplicates are created. If the lookup finds nothing, the gateway refuses rather than assuming the order was lost | `RISK-020`, `RISK-021`, `OPS-005`, `QA-010` |
| 2026-08-28 | Verify the Paper endpoint from the client about to be used, not from the environment variable that configured it | Those two can disagree, and only one of them is what the bytes will actually reach | `RISK-015`, `RISK-016` |
| 2026-08-28 | Never show the model the invalidation conditions, rather than validating that it preserved them | A check can be removed; an absence cannot be bypassed. The model has no field for invalidation and never sees the text, so there is no path by which a memo could soften a stop | `CLR-008`, `AI-005`, `RISK-003` |
| 2026-08-28 | Coerce a direction reversal to abstention and record it, rather than rejecting the call | An abstention is a safe, meaningful outcome and keeps the trace intact; a hard rejection would discard the evidence that the model tried | `CLR-008`, `AI-008`, `AI-010` |
| 2026-08-28 | Report ablation cost in tokens rather than currency | Token counts are observed. A dollar figure would be an unverified constant presented as a measurement | `AI-007`, `QA-005` |
| 2026-08-28 | Build a purpose-built read-only HTTP client instead of using `alpaca-py`'s `TradingClient` for reads | `TradingClient` carries `submit_order`, `cancel_order`, and `close_position` as latent capability. "We chose not to call them" is a weaker claim than "the object cannot express them", and the read path is the part a judge will inspect | `RISK-014`, `DATA-001`, `CLR-018`, `QA-004` |
| 2026-08-28 | Require delta for option eligibility and fail closed when it is missing | A missing Greek is a reason to decline a contract, never a reason to fall back on strike distance. Substituting a proxy is how a liquidity or quality filter silently stops filtering | `CLR-014`, `DATA-011` to `DATA-014`, `RISK-004` |
| 2026-08-28 | Add a minimum spread width and a debit/width ceiling after the first live run | The first live selection was a $1-wide spread on a $771 underlying paying 63% of width. It passed every existing check and was still a bad structure, which is evidence that nearest-strike selection is not a policy | `CLR-014`, `CLR-020`, `RISK-005` |
| 2026-08-28 | Bind every decision to its observation with an input hash and a decision hash | Reproducibility is the project's central claim, so the link between what was seen and what was decided must be mechanical rather than asserted. Canonical serialization refuses floats and naive datetimes so a digest cannot drift with binary rounding or machine timezone | `DATA-004`, `OPS-001`, `OPS-003`, `QA-006` |
| 2026-08-28 | Keep the deterministic no-LLM thesis as a permanent component rather than a Phase 3 placeholder | It is the control arm of the ablation. If it is written as scaffolding it will be deleted when the model lands, and the comparison that makes the AI contribution measurable will disappear with it | `AI-010`, `QA-005` |
| 2026-08-28 | Make the repository public before submission and treat the flip as a `G4` checklist item | A public GitHub repository is mandatory and a private one may lower the score, so visibility is a release step rather than a preference | `HK-010`, `DEC-001` |

## 17. Immediate next actions

1. Record the newly verified public event facts and confirm only the remaining account, code-eligibility, autonomy, exact-deadline, and sponsor-interface questions.
2. Freeze the H0 SPY trend/retest and vertical-debit-spread cut line before adding capability.
3. Add one SPY qualified fixture and one refusal fixture with separate oracles, then make both persist through the production workflow.
4. Implement the read-only SPY data path and deterministic baseline before the production LLM adapter.
5. Run the deterministic-versus-LLM ablation before claiming that the model adds decision value.
6. Correct configuration verification, define the confidential export boundary, and complete exact-request/idempotency/reconciliation proof before enabling any Paper write.
7. Stop adding scope when the H0 hosted demo and submission artifacts need integration time.
