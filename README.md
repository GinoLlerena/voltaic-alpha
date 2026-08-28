# Options Alpha — an auditable AI execution firewall

**Team:** Voltaic Alpha · **Repository:** `github.com/GinoLlerena/voltaic-alpha`

The interesting part of this project is not the strategy. It is the firewall
around it: a language model may write a memo, but it cannot pick a direction,
change an invalidation level, size risk, create execution authority, or reach a
broker tool. Every decision carries completed-bar evidence, a deterministic risk
approval, an immutable approved order intent, and a reconciliation trail.

One SPY setup and one vertical debit-spread family are enough to demonstrate
that. H0 runs on Alpaca Paper only, and no claim is made that the strategy has
alpha or that the model improves decisions — a `NO_TRADE` refusal and a
deterministic baseline beating the model are both valid results.

## What exists at this commit

No order submission. No broker write path, no database, no hosted interface.
What is built today is two deliberately separate layers:

1. the original synthetic interaction lab, which tests spread and risk feedback;
2. a production-facing architecture slice with timestamped contracts, provider
   ports, and a bounded fail-closed decision workflow.

Neither layer creates a trading bot or places orders. The architecture is
documented in [Architecture Slice v0.1](docs/options_alpha_architecture_slice_v0_1.md).

It answers four early questions:

1. Can an event thesis be passed to an options specialist without losing its
   evidence and invalidation conditions?
2. Can the specialist produce a machine-checkable, risk-defined structure?
3. Can deterministic code reject an unsafe proposal and request a bounded
   revision?
4. Can the final decision explain why it is a trade candidate or no-trade?

## Deliberately out of scope

- Alpaca order submission, replacement, cancellation, or position changes
- Live credentials or any live endpoint. Paper credentials are used only by the
  opt-in read-only integration test described below; normal runs need none.
- Autonomous execution
- Portfolio optimization
- Backtesting
- Multiple concurrent strategies
- A production UI

The fixture contains synthetic prices. Nothing in this repository is an
investment recommendation.

## Configure local credentials

The current simulation does not need credentials. To prepare for the OpenAI
agent and Alpaca read-only adapters, run:

```bash
python3 scripts/configure_secrets.py
```

The script securely prompts for:

- `OPENAI_API_KEY`
- `ALPACA_API_KEY` using Paper credentials
- `ALPACA_SECRET_KEY` using Paper credentials

Terminal input is hidden. The generated `.env` is ignored by Git, receives
owner-only permissions on macOS/Linux, enables Paper mode, and explicitly keeps
trading disabled.

Check configuration without displaying any credential:

```bash
python3 scripts/configure_secrets.py --check
```

## Interaction under test

```text
Event Thesis Agent
        |
        v
Options Structure Agent
        |
        v
Deterministic Risk Gate --rejects/suggests quantity--> Options Structure Agent
        |
        v
Decision Arbiter: TRADE_CANDIDATE or NO_TRADE
```

The risk gate is intentionally not an LLM agent. Position sizing, maximum loss,
DTE, evidence thresholds, and bid/ask checks must remain deterministic.

## Production architecture slice

New production work targets `options_alpha_lab.architecture`. The first slice
defines:

- timestamped decision, account, signal, option, thesis, spread, and risk contracts;
- `bullish`, `bearish`, and `neutral` direction semantics;
- the full validation-suite decision vocabulary;
- ports for market data, deterministic setup/options/risk components, bounded
  thesis synthesis, audit, and persistence;
- an explicit `observe -> qualify -> thesis -> structure -> risk -> decide`
  workflow with terminal `NO_TRADE` gates.

The original `ExperimentCase` path remains available for compatibility. It is
not the production input contract because it contains expected answers.

## Run the sample

From the project directory:

```bash
PYTHONPATH=src python3 -m options_alpha_lab.cli fixtures/nvda_earnings_bearish.json
```

The sample deliberately starts with two contracts. The risk gate rejects that
size, returns a suggested quantity of one, and the options agent revises the
proposal once. The final output includes the full interaction trace.

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The offline suite covers architecture boundaries, bullish and bearish vertical construction,
multi-expiration option chains, quote and spread integrity, evidence and
invalidation requirements, risk-based quantity revision, unaffordable trades,
decision traces, serialization, and local secret-file protections. Architecture
tests additionally cover oracle isolation, timestamp/look-ahead protection,
Paper-only input, neutral abstention, evidence-reference validation, directional
authority, and terminal risk vetoes. Offline tests do not call OpenAI or Alpaca.

## Run the live contract test

The opt-in integration test makes one billable OpenAI Responses API request and
three read-only Alpaca requests: Paper account status, an NVDA stock snapshot,
and an indicative NVDA option-chain snapshot. It has no order-submission code.

```bash
RUN_LIVE_API_TESTS=1 PYTHONPATH=src python3 -m unittest discover \
  -s tests -p 'test_live_integration.py' -v
```

The test defaults to `gpt-5.6-terra`. Set `OPENAI_MODEL` in the command
environment to exercise another model. Normal test runs skip this live test,
so they remain free and deterministic.

## What this teaches us for the hackathon

- Whether the state contract contains enough information for every node
- Which calculations must remain outside the model
- Which rejection reasons are useful enough to drive a revision
- Whether one bounded revision is enough or creates unstable loops
- What must be persisted for auditability
- Which Alpaca fields will later be needed in the live-read adapter

## Hackathon H0 direction

The hackathon build is now scoped as an **auditable AI execution firewall demonstrated through one SPY options setup**. It does not claim that the strategy has established alpha or that an LLM improves trading decisions merely because it produces a fluent explanation.

H0 is deliberately small:

- SPY is the only tradeable underlying; QQQ/IWM may be read-only context.
- One mirrored trend-continuation/retest setup maps to a bull-call or bear-put vertical debit spread.
- One qualified frozen case and one refusal case run through both a deterministic no-LLM baseline and the bounded model path.
- The distinctive proof is the hash-linked evidence, approval, exact prepared request, broker state, and reconciliation trail.
- The execution demonstration contains one Paper open/close lifecycle and one ambiguous-write or restart recovery case.
- The judge experience is limited to five views: health/mode, evidence and baseline, model memo, approval/request lineage, and reconciled outcome or refusal.

The currently published event criteria are Application of Technology, Presentation, Business Value, and Originality; the public page does not list P&L as a judging criterion. Paper P&L is therefore presented as a diagnostic result unless organizers publish a separate leaderboard rule.

## Frontend design

The judge-facing UX/UI baseline is defined in [Frontend Design v0.1](docs/options_alpha_frontend_design_v0_1.md). It specifies the five-view information architecture, lifecycle/refusal/recovery journeys, evidence and authority presentation, responsive behavior, accessibility, privacy, view-model boundaries, and staged implementation plan. It is a design specification; templates, styles, routes, and dashboard tests are not implemented yet.

## Next architecture increment

Add a JSON loader for the production `DecisionSnapshot` contract and create one
qualified SPY fixture plus one refusal fixture with separate test oracles and
hidden post-decision outcomes. Implement the single deterministic trend/retest
classifier and read-only SPY adapter, then compare the bounded model memo with a
deterministic no-LLM baseline. Keep order submission absent until this trace and
the exact-request/idempotency/reconciliation gates are stable.

## Alpaca agent-skill review

The official [Alpaca Trading API agent skills](https://github.com/alpacahq/alpaca-skills/tree/main/skills/trading-api) were reviewed on 26 August 2026. No runtime skill was installed and no write path was enabled.

The project adopted their useful reproducibility, Paper-endpoint verification, exact dry-run, client-order idempotency, ambiguous-submit lookup, lifecycle, and disclosure patterns as documented requirements. It did not adopt conversational confirmation or generic agent tools as execution authority:

- production orders remain exclusive to a deterministic `alpaca-py` gateway accepting immutable approved intents;
- Alpaca MCP remains read-only and omits the `trading` toolset;
- the Alpha-preview Alpaca CLI may be used only as a version-pinned operator diagnostic and dry-run cross-check;
- PostgreSQL will be authoritative, while any filesystem run package must be a derived confidential/redacted export whose root is ignored by version control before creation; and
- the generic backtest workflow informs replay artifacts, but options-spread selection, fills, expiry, and exercise/assignment require project-owned logic.

See the [implementation-plan disposition](docs/options_alpha_bot_implementation_plan_v0_1.md#34-disposition-of-alpaca-trading-api-agent-skills), [execution-adapter obligations](docs/options_alpha_architecture_slice_v0_1.md#31-future-execution-adapter-obligations), and [traceability dispositions](docs/options_alpha_requirements_traceability_v0_1.md#33-alpaca-trading-api-skill-disposition-register).
