# Options Alpha — Breadth veto: Step 2 signal replay

| Field | Value |
|---|---|
| Date | 15 October 2026, America/Lima |
| Status | **Step 2 complete. Stop point: Step 3 computes the first outcomes, so the owner decides whether to start it.** |
| Plan | [Breadth veto backtest: plan](../improvements/options_alpha_veto_backtest_plan_v0_1.md) §4.2 and §8 Step 2 (`VBT-102`) |
| Protocol | [Numeric protocol](../improvements/options_alpha_veto_backtest_protocol_v0_1.md), frozen 12 October 2026; no value changed |
| Previous step | [Step 1 coverage report](options_alpha_veto_step1_coverage_v0_1.md) |
| Reproduce | `uv run python -m options_alpha_lab.veto_replay` (exit 0 only if parity passes) |
| Boundary | Classification only. No forward price is read, no outcome is computed and no rule is changed. |

## 1. Result

Every downloaded session was passed through the bot's own signal builder and
classifier, as the worker would have seen it at 10:00 New York: the completed
daily bars of its 400-day window, RSP over the same window, and the
at-the-money implied volatility rebuilt in Step 1.

| Bucket | Sessions |
|---|---:|
| Permitted: qualified, and no opposing signal at 0.70 or above | **241** |
| Breadth-vetoed: refused, but qualifies when only opposing breadth is removed | **161** |
| Other/multiple vetoes | 0 |
| No setup | 228 |
| Out of scope: bearish structure | 41 |
| Unmeasurable | 5 |
| **Total**, 1 February 2024 to 12 October 2026 | **676** |

Both groups clear the protocol's minimum for a conclusion (§8: 30 in each
group and 10 separate clusters), with room to spare:

| Group | Sessions | Clusters | Longest run | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| Permitted | 241 | 41 | 13 | 97 | 86 | 58 |
| Breadth-vetoed | 161 | 36 | 19 | 67 | 62 | 32 |

A cluster is a run of members with fewer than three sessions between them, so
19 vetoed sessions in a row count as one episode, not nineteen.

**These are sessions, not trades.** The bot holds one position at a time, so
Part 2 will have far fewer trades than qualifying sessions. Part 1 (Step 3)
measures SPY's move after each session, so for Part 1 the session is the unit.

## 2. Parity with the bot's own record

The plan's must-pass check. The 14 sessions the worker recorded, 22 September
to 9 October 2026, were classified twice: once from the signals the worker
stored, and once from the replay. **The bucket is the same on all 14.** That
includes the two the plan names: the 5 October refusal (structure 0.59, below
the line) and the 9 October qualification, which opened the first Paper trade.

| Session | Worker | Replay | Volatility strength, worker / replay |
|---|---|---|---|
| 22 Sep | Breadth-vetoed | Breadth-vetoed | 0.72 / 0.72 |
| 23 Sep | Breadth-vetoed | Breadth-vetoed | 0.74 / 0.74 |
| 24 Sep | Breadth-vetoed | Breadth-vetoed | 0.72 / 0.72 |
| 25 Sep | Breadth-vetoed | Breadth-vetoed | 0.71 / 0.72 |
| 28 Sep | Breadth-vetoed | Breadth-vetoed | 0.71 / 0.71 |
| 29 Sep to 2 Oct (4) | No setup | No setup | none / none |
| 5 Oct | No setup | No setup | 0.70 / 0.70 |
| 6 Oct | Breadth-vetoed | Breadth-vetoed | 0.70 / 0.69 |
| 7 Oct | Breadth-vetoed | Breadth-vetoed | 0.73 / 0.73 |
| 8 Oct | Breadth-vetoed | Breadth-vetoed | 0.74 / 0.74 |
| 9 Oct | Permitted | Permitted | 0.75 / 0.75 |

Every signal other than the volatility reading (structure, breadth, momentum)
is identical in direction and strength. The volatility reading's strength
differs by 0.01 on two sessions. It comes from the rebuilt input, and the
difference changes no bucket: the confirmation needs 0.50.

The worker's reference is its 10:00 decision snapshot for 13 sessions. For
9 October, which has only the 09:45 snapshot that opened the position, it is
that snapshot's signals.

## 3. Every Permitted and Breadth-vetoed session is in a calm market

All 402 qualifying sessions have an at-the-money reading in the calm class.
All 7 stressed sessions (April 2025) had **bearish** structure. So did every
"neither" session that had a structure signal at all: 25 of the 40, 22 of them
at or above 0.60, in March and April 2025 and March 2026. This study is bullish-only. So in this period the breadth veto was only ever tested against
calm markets, and the study can say nothing about how it behaves when
volatility is high. Step 1 expected this; Step 2 confirms it.

## 4. Sessions not compared

| Reason | Sessions |
|---|---|
| The 400-day window reaches before the cached bars | 3: 1, 2 and 5 February 2024 |
| No at-the-money reading (Step 1, §2) | 2: 26 February and 15 March 2024 |
| **No setup:** no structure signal | 203 |
| **No setup:** structure below 0.60 | 25 |
| **No setup:** no confirmation from another family | 0 |

The daily bars were requested from 1 January 2023, so a decision whose window
starts earlier is missing up to three sessions at the start of its window. Those
three are counted as unmeasurable rather than replayed on a short window.
2 February 2024 also has no volatility reading; it is counted once.

No qualifying session lacked a confirmation: whenever structure passed, the
calm volatility reading confirmed it. No session was vetoed by another family:
momentum divergence never reached 0.70 against a bullish setup.

## 5. Sensitivity

| Variant | Permitted | Breadth-vetoed | Parity |
|---|---:|---:|---|
| Dividend 1.2% (frozen) | 241 | 161 | 14/14 |
| Dividend 0.7% | 241 | 161 | 14/14 |
| Dividend 1.7% | 241 | 161 | 14/14 |

For context only, and not a rule proposal (plan §4.3), the same qualifying
sessions under other breadth lines:

| Breadth line | Permitted | Breadth-vetoed |
|---|---:|---:|
| 0.60 | 193 | 209 |
| 0.70 (the rule) | 241 | 161 |
| 0.80 | 294 | 108 |
| Off | 402 | 0 |

These counts are consistent with the earlier feasibility count, which was an
upper bound: it found 246 sessions with breadth below the line and 162 at or
above, against 241 and 161 here.

## 6. Method, briefly

- **Signals and classifier:** `evidence.build_signals` and
  `DeterministicSetupClassifier`, unchanged. The replay restates none of their
  arithmetic.
- **Attribution (plan §4.2):** if the shipped classifier qualifies the setup,
  it is Permitted. Otherwise only the opposing breadth signal is removed and the
  classifier asked again; if that qualifies, the session is Breadth-vetoed and
  takes its invalidation level from that counterfactual. If it qualifies only
  once every opposing signal is removed, it is Other/multiple vetoes.
- **No look-ahead:** each session reads daily bars up to the last session
  completed before it. A test doubles every price from the decision session
  onward and checks that the session's row does not change.
- **Determinism:** rows digest
  `sha256:e959635b3dc7e1861ff3c9969b53fcc29528f53e552cd1741ee8877b02bb4080`,
  identical across runs.
- Tests: `tests/test_veto_replay.py`. Among them, every combination of a signal
  pool is checked: Permitted is assigned exactly when the shipped classifier
  qualifies.

## 7. What Step 3 would do, and why it needs the owner

Step 3 attaches SPY's move one, two and three sessions after each Permitted and
Breadth-vetoed session. It checks whether the setup's invalidation level was
breached, and records the worst close. It then compares the two groups with
the frozen block bootstrap (protocol §8). Step 3 computes the study's first
outcomes. The protocol is frozen, so no setting can be tuned towards a result.
Starting Step 3 is still the owner's decision.

Step 3 needs no new download: the cached daily bars already reach
12 October 2026. The last few sessions will be censored where three later
closes do not exist yet, and are reported as such.
