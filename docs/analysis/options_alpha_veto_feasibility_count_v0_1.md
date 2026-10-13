# Options Alpha — Breadth veto: feasibility count

| Field | Value |
|---|---|
| Date | 12 October 2026, America/Lima |
| Status | **Complete. The count passes the screen on the full option-data period, and the replay reproduces the bot's stored signals exactly.** The preliminary fixture-only result is kept in §6. |
| Plan | [Breadth veto backtest: plan](../improvements/options_alpha_veto_backtest_plan_v0_1.md) §4.0, Step 0B, `VBT-100` |
| Code | `src/options_alpha_lab/veto_study.py`, `tests/test_veto_study.py` |
| Reproduce | `uv run python -m options_alpha_lab.veto_study --bars .cache/veto_backtest/daily_bars.json --since 2024-02-01 --reference .cache/veto_backtest/stored_signals.json` |
| Boundary | Counts only. No outcome, price move or return is computed. No rule is changed. |

## 1. Result

On the full period the option data covers, the count **passes the screen**.

| Group | Sessions | Clusters | Longest run | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| Bullish structure, opposing breadth below the line | 245 | 42 | 15 | 100 | 86 | 59 |
| Bullish structure, opposing breadth at or above the line | 162 | 36 | 19 | 68 | 62 | 32 |
| Screen, per group | 30 | 10 | | | | |

- 676 completed sessions were measured, 1 February 2024 to 12 October 2026.
- Bullish structure reached 0.60 on 407 of them; bearish structure, out of
  scope, on 41.
- No session in either group carried a veto from another family that can be
  read from daily bars (momentum).

**Reference check: passed.** The replay was compared with the signals the bot
stored for its 14 sessions from 22 September to 9 October 2026 (843
snapshots). Structure, breadth and momentum signals match on every session, in
direction and in strength to two decimals, including the four sessions with no
signal at all, 5 October at structure 0.59, and 9 October with no breadth
signal. The volatility signal is not replayed, because the count supplies no
implied volatility.

## 2. What this means

- **The option-backed study is worth starting.** Each group has several times
  the screen's sessions and clusters.
- **The veto is not rare.** Opposing breadth reached the line on 40% of the
  sessions where bullish structure passed (162 of 407).
- **The numbers will shrink.** They are an upper bound. The full rule also
  needs a confirmation, and a stressed-volatility reading can veto. Entry-time
  option data will be missing for some sessions, and the chronological
  portfolio in the plan's §5.5 takes at most one position at a time. A run of
  15 qualifying sessions is at most a handful of trades.
- **Clusters are the better guide.** About 40 separate episodes per group is
  the realistic size of the evidence, not 245 or 162.

This says nothing about whether the veto helps. No outcome was measured.

## 3. Method

For each completed session the script builds the window the worker would have
had (bars up to that session, within the worker's 400-day lookback) and calls
the real `build_signals` with no implied volatility. It records whether a
bullish structure signal reaches 0.60 and whether opposing breadth reaches
0.70. A cluster is a set of member sessions with fewer than three sessions
between neighbours.

**Why it is an upper bound.** Supplying volatility later can only remove
sessions. `test_veto_study.py` checks this against the shipped classifier on
every session in the committed fixture, at a calm, a middle and a stressed
volatility: the classifier never qualifies a bullish setup outside the "below
the line" group, and never qualifies anything in the "at or above" group.

Other tests cover: no row uses a later bar; the window is the bounded 400 days
and not the whole series; the 0.70 line itself counts as at or above; a veto
from another family is reported separately; and the reference check treats a
different strength, a missing signal or an unreachable session as a
disagreement.

## 4. Data

Exported read-only from the server on 12 October 2026 (Lima) with
`scripts/veto_export.py`, under the owner's approval of the same day. The files
are kept out of git; `options_alpha_veto_backtest_manifest.json` names them by
digest.

| File | Content | Coverage |
|---|---|---|
| `daily_bars.json` | SPY and RSP daily bars; Alpaca, SIP feed, split-adjusted: the worker's own request | 947 sessions each, 3 January 2023 to 12 October 2026 |
| `stored_signals.json` | each distinct signal the worker stored, per session | 14 sessions, 843 snapshots, 22 September to 9 October 2026 |

The export read market data and ran one SELECT. It wrote nothing on the
server, restarted nothing, and no credential left the host. The first counted
session is 1 February 2024; 2023 supplies the warm-up.

## 5. Recommendation

**Go.** Continue to Step 1 of the plan. Before any outcome is computed, the
numeric protocol in the plan's decision 9 has to be proposed and approved.

## 6. Preliminary result, superseded

The first run used only the committed fixture
(`fixtures/h0/sensitivity_bars.json`, SIP, 3 June 2024 to 28 August 2026) and
counted 183 sessions in 31 clusters below the line and 101 in 27 at or above,
over 493 sessions from 11 September 2024. It is consistent with the full
result and is kept here because the tests run on that fixture.
