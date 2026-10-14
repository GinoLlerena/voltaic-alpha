# Options Alpha — Breadth veto: Step 1 coverage report

| Field | Value |
|---|---|
| Date | 13 October 2026, America/Lima |
| Status | **Step 1 complete. Stop point: the owner reviews this report before Step 2.** |
| Plan | [Breadth veto backtest: plan](../improvements/options_alpha_veto_backtest_plan_v0_1.md) §8 Step 1 |
| Calibration | [Calibration and parity gates](options_alpha_veto_calibration_v0_1.md): all three gates pass |
| Reproduce | `uv run python -m options_alpha_lab.veto_reconstruction --coverage` |
| Boundary | Inputs only. No setup is classified, no outcome is computed and no rule is changed. |

## 1. Result

The at-the-money volatility reading, the input the entry rule needs from the
option market, can be rebuilt for **673 of the 676 sessions** from 1 February
2024 to 12 October 2026.

| | Count |
|---|---:|
| Sessions downloaded | 676 |
| Sessions with a reading | 673 |
| Sessions with no reading | 3 |
| Contracts priced | 129,043 |
| Contracts dropped: no trade in the 15 minutes before 10:00 | 9,184 |
| Contracts dropped: price below intrinsic value, or no volatility in the bounds | 3 |

Contracts that did not trade at all in the window are not in the download and
are not counted above.

## 2. The three sessions with no reading

| Session | Listed contracts | Traded |
|---|---:|---:|
| 2 February 2024 | 850 | 0 |
| 26 February 2024 | 868 | 0 |
| 15 March 2024 | 950 | 0 |

No contract traded at all on these mornings, while the sessions around them
returned about 190 each. They look like gaps in the provider's early data, all
in the first six weeks of its option history. All three fall on sessions where
the feasibility count put bullish structure with breadth **below** the veto
line. Under the protocol they are unmeasurable: counted, never filled, and
never treated as "no setup". Three of 245 sessions in that group is too few to
bias the comparison much, but it is recorded so the two groups' missing data
can be compared.

## 3. The reading over the period

| | Value |
|---|---:|
| Lowest | 0.0697 |
| Median | 0.1334 |
| Highest | 0.5541 |
| Calm (at or below 0.22) | 626 sessions |
| Neither | 40 sessions |
| Stressed (at or above 0.32) | 7 sessions, all in April 2025 |
| Within one volatility point of a threshold | 18 sessions |

- **Most of the period is calm.** On 93% of sessions the reading is at or below
  0.22, where it confirms a bullish setup. The stressed sessions are the April
  2025 sell-off.
- **18 sessions sit close enough to a threshold** that the reconstruction's
  error could move them across it. The calibration measured errors up to 0.008,
  but only in a calm stretch far from either threshold. Step 2 reports these
  18 sessions apart, so a result does not rest on them unseen.

## 4. Data

| File | Content |
|---|---|
| `options/<session>.json`, 676 files | 5-minute option trade bars, 09:45 to 10:05 New York; contracts expiring 10 to 60 days out, calls and puts within 1% of the previous close (calls from 0.94 to 1.07 of it for 22 September to 8 October 2026) |
| `spy_5min_open.json` | SPY 5-minute bars opening 09:30 to 10:00 New York |
| `DGS3MO.csv` | the 3-month Treasury yield, FRED |

Downloaded read-only through the server on 13 October 2026 under the owner's
approval of that day: 8,377 requests, nothing written on the server, no
credential copied. The manifest names the files by digest.

Not checked: January 2024. The plan noted that the provider's documentation
says February 2024 while an earlier probe saw bars from 18 January. The
approved download starts on 1 February, and that session had a full set of
trades, so the question does not affect the study.

## 5. What Step 2 needs from the owner

Step 2 replays the entry rule on every session with these readings, and
records which setups the veto blocks and which it lets through. It still
computes no outcome; outcomes come in Step 3, under the frozen protocol.

The owner decides whether to continue to Step 2 on this coverage.
