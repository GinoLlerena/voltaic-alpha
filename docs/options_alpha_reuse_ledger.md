# Options Alpha Agent

## Pre-Event Code Reuse Ledger

| Field | Value |
|---|---|
| Version | v0.1 |
| Opened | 28 August 2026, Phase 0 |
| Required by | Fallback `F-02` ([Phase 0 record](./options_alpha_phase0_event_cut_line_v0_1.md) §6) |
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

None yet. Phase 1 has not landed a module.

| Date | Module reused | Baseline commit | What it contributes to an H0 outcome | Why not rewritten | Replacement cost if disallowed |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## 4. Maintenance rule

An entry is added in the **same commit** that first reuses the module. A reuse
discovered after the fact is a defect in this ledger and is recorded with its
discovery date, not backdated.
