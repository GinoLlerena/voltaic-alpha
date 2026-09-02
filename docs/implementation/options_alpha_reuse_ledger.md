# Options Alpha Agent

## Pre-Event Code Reuse Ledger

| Field | Value |
|---|---|
| Version | v0.1 |
| Opened | 28 August 2026, Phase 0 |
| Required by | Fallback `F-02` ([Phase 0 record](options_alpha_phase0_event_cut_line_v0_1.md) §6) |
| Owner | Gino Llerena (Voltaic Alpha) |
| Baseline boundary | Tag `baseline-pre-event` |

## 1. Why this exists

The event requires original, MIT-compliant submissions but does not state
whether code written before the window may be part of one (`HK-008`, `DEC-001`).
Rather than guess, the boundary is made auditable.

Two rules bind until an organizer answer replaces them:

1. **The H0 runtime path is authored in-window.** Everything that produces an H0
   outcome is committed after `baseline-pre-event`.
2. **Every pre-event module reused in the H0 path is listed below** before the
   commit that reuses it, naming what it contributes and why it was not rewritten.

If pre-existing code turns out to be permitted, this ledger is documentation. If
it turns out to be prohibited, this ledger is the complete worklist — no
archaeology through the diff is required.

## 2. What the baseline contains

Recorded for context. Presence in the baseline does **not** make something part
of the H0 path; only §3 does.

| Area | Contents | In the H0 path? |
|---|---|---|
| `docs/` | Six specifications | Not runtime code |
| `src/options_alpha_lab/` (legacy lab) | `models`, `risk`, `orchestrator`, `agents`, `cli` — the synthetic interaction lab | No. Retained as a non-load-bearing artifact |
| `src/options_alpha_lab/architecture/` | `contracts`, `ports`, `workflow` | Candidate. Any reuse is listed in §3 |
| `tests/` | 36 offline tests, 1 opt-in live test | Regression protection, not an H0 outcome |
| `fixtures/nvda_earnings_bearish.json` | One synthetic case | No. Outside the frozen SPY scope; replaced in Phase 1 |
| `scripts/configure_secrets.py` | Local credential helper | Operator tool, not a decision path |
| Build environment | `pyproject.toml`, `uv.lock`, CI, compose, `.gitignore` | Infrastructure, not a submission claim |

## 3. Reuse entries

| Date | Module reused | Baseline commit | What it contributes to an H0 outcome | Why not rewritten | Replacement cost if disallowed |
|---|---|---|---|---|---|
| 2026-08-28 | `src/options_alpha_lab/architecture/contracts.py` | `b3b88a7` | The timestamped `DecisionSnapshot`, `SetupCandidate`, `Thesis`, `SpreadCandidate`, `RiskDecision`, and `DecisionOutcome` types that every H0 outcome is expressed in | It is a data contract with validation, not behaviour. Retyping it would produce the same file with different whitespace and would lose the look-ahead and oracle-isolation invariants it already encodes | Low. Roughly 320 lines of dataclasses and validators, mechanical to re-derive |
| 2026-08-28 | `src/options_alpha_lab/architecture/ports.py` | `b3b88a7` | The `Protocol` boundaries that keep the model behind a synthesizer interface and execution behind a port | 65 lines of interface declarations with no logic | Negligible |
| 2026-08-28 | `src/options_alpha_lab/architecture/workflow.py` | `b3b88a7` | The bounded `observe -> qualify -> thesis -> structure -> risk -> decide` state machine, including the gates that stop a thesis reversing direction or altering invalidation | This is the firewall itself. It is covered by 15 pre-event tests, and rewriting the one component whose correctness the whole claim depends on, to satisfy a rule that may not exist, would trade real safety for speculative eligibility | Moderate. About 244 lines, and any rewrite must re-prove every gate |

Not in the H0 path, and therefore not reused: `models.py`, `risk.py`,
`orchestrator.py`, `agents.py`, and `cli.py`. Those remain the original
synthetic lab. `fixtures/nvda_earnings_bearish.json` likewise stays outside H0;
the H0 path uses `fixtures/h0/`, authored in-window.

## 4. Maintenance rule

An entry is added in the **same commit** that first reuses the module. A reuse
discovered after the fact is a defect in this ledger and is recorded with its
discovery date, not backdated.
