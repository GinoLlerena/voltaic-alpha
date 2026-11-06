# Options Alpha — Setup follow-through study: results

| Field | Value |
|---|---|
| Date | 5 November 2026, America/Lima |
| Plan | [Setup follow-through study plan](../improvements/options_alpha_setup_follow_through_study_plan_v0_1.md), §3 and §4, approved by the owner on 5 November 2026, with the details in §3.1 fixed and committed (`297ff64`) before computing. The code was committed before it was run on the cached data |
| Inputs | Step 2 replay rows, digest `sha256:e959635b3dc7e1861ff3c9969b53fcc29528f53e552cd1741ee8877b02bb4080`, reproduced unchanged; cached SPY daily bars. No download |
| Code | `src/options_alpha_lab/study_follow_through.py`; run `uv run python -m options_alpha_lab.study_follow_through` |
| Status | Exploratory, on data already seen. No rule is changed. Paper stays armed with today's rules |

## 1. Summary

**The setup lags.** In the three sessions after a qualifying session, SPY rose
+0.045% on average. After a non-qualifying session it rose +0.470%. The
difference, −0.425 percentage points, has a 95% interval wholly below zero at
all three block lengths. That is the "setup lags" reading of plan §3.

The margin is thin: the upper end of the interval is −0.015 at block 10 and
−0.006 at block 20. This is not proof of a reliably bad signal. It does say
that, over February 2024 to October 2026, the setup did not pick days that
rose more than other days. It picked days that rose less. A bullish debit
spread needs the reverse.

The splits in §4 describe; they do not test. None of them finds a slice of
qualifying sessions that rose more than the non-qualifying sessions in the
same range.

## 2. Part A: the one comparison (plan §3)

669 sessions: 402 qualifying (241 Permitted, 161 Breadth-vetoed) and 269
non-qualifying (228 No setup, 41 Out of scope, 0 Other/multiple vetoes). Five
Unmeasurable sessions are left out (§3.1, item 2). Two qualifying sessions
are censored at h = 3 because their third close is not cached yet.

| h | Block | Qualifying mean (n) | Non-qualifying mean (n) | Difference [95%] |
|---|---|---|---|---|
| 1 | 10 | +0.023 (402) | +0.153 (269) | −0.131 [−0.279, +0.024] |
| 2 | 10 | +0.033 (401) | +0.315 (269) | −0.282 [−0.557, +0.003] |
| **3** | **10** | **+0.045 (400)** | **+0.470 (269)** | **−0.425 [−0.813, −0.015]** |
| 3 | 5 | | | −0.425 [−0.790, −0.033] |
| 3 | 20 | | | −0.425 [−0.822, −0.006] |

The qualifying mean at h = 3 reproduces Part 1's +0.045% on the same 400
sessions. The gap grows with the horizon, from −0.13 to −0.28 to −0.43.

**Reading (§3): the setup lags.** The interval lies wholly below zero at all
three block lengths.

### Context, not in the plan: which non-qualifying sessions

Added after seeing Part A, to show where the gap comes from. Mean 3-session
move, block-10 interval:

| Bucket | n | Mean | [95%] |
|---|---|---|---|
| No setup | 228 | +0.557 | [+0.240, +0.862] |
| Out of scope (bearish structure) | 41 | −0.014 | [−1.404, +1.378] |
| Permitted | 239 | −0.036 | [−0.255, +0.161] |
| Breadth-vetoed | 161 | +0.165 | [−0.115, +0.402] |

The gap comes from the No setup days, not from bearish-structure days
rebounding. Every measurable session together averaged +0.216%.

## 3. Part B: where it comes from (plan §4, descriptive)

Qualifying sessions with an h = 3 outcome (400), mean 3-session move in %,
block-10 interval.

### D1, confirming family

| Family | n | Mean [95%] |
|---|---|---|
| Volatility | 335 | +0.106 [−0.076, +0.266] |
| Participation (breadth) | 65 | −0.268 [−0.746, +0.187] |
| Momentum | 0 | — |

Momentum never confirmed in this period. Breadth-confirmed sessions did worse,
but there are only 65 of them, with a wide interval. Breadth can only confirm
a Permitted session: on a Breadth-vetoed one it is bearish.

### D2, structure strength (cuts 0.66 and 0.71)

| Third | n | Mean [95%] |
|---|---|---|
| Lower | 147 | −0.080 [−0.342, +0.169] |
| Middle | 147 | +0.071 [−0.266, +0.353] |
| Upper | 106 | +0.183 [−0.130, +0.431] |

Stronger structure did a little better, but every interval includes zero.
Strengths come in steps of 0.01, so ties make the upper third smaller.

### D3, SPY's 20-session move up to `C[-1]` (cuts +1.87% and +3.31%)

| Third | Qualifying n, mean [95%] | Non-qualifying n, mean [95%] |
|---|---|---|
| Lower | 134, −0.217 [−0.514, +0.059] | 209, +0.454 [−0.002, +0.903] |
| Middle | 133, +0.048 [−0.220, +0.291] | 16, +1.060 [+0.295, +2.010] |
| Upper | 133, +0.307 [+0.065, +0.503] | 44, +0.333 [−0.321, +0.786] |

This is the opposite of the plan's worry that the setup fires late in extended
runs. Qualifying sessions after the largest prior runs did best, and in that
third they matched the non-qualifying sessions. The lag sits in the lower
third: after a 20-session run of under +1.9%, qualifying sessions averaged
−0.22% and non-qualifying ones +0.45%. Most non-qualifying sessions (209 of
269) fall in that third, as expected, since the setup needs an uptrend.

### D4, SPY's move on the last completed session (cuts −0.03% and +0.43%)

| Third | Qualifying n, mean [95%] | Non-qualifying n, mean [95%] |
|---|---|---|
| Lower | 134, +0.173 [−0.050, +0.369] | 140, +0.539 [+0.211, +0.896] |
| Middle | 133, −0.056 [−0.311, +0.176] | 44, +0.447 [−0.461, +1.140] |
| Upper | 133, +0.017 [−0.251, +0.249] | 85, +0.368 [−0.330, +0.934] |

No pattern by the last session's move. Buying right after an up day is not
what drives the lag. Qualifying sessions trail the non-qualifying ones in
every third.

## 4. Limits

- The +0.045% against +0.220% figure had been seen before the plan was
  written. Part A measures it properly once; it was not a blind test.
- One period, February 2024 to October 2026, a calm, mostly rising market.
  "No setup" days then include many ordinary up days.
- These are SPY moves from the prior close, overnight gap included, not
  spread results.
- Four splits on seen data. Any pattern in §3, such as D3's lower third, is at
  most a hypothesis for a new plan.

## 5. What it means

Parts A and B of the setup and exit study showed that no exit change fixes the
losses. This study shows why: over this period the trend-retest setup picked
days that SPY followed with less of a rise than the days it skipped. As built,
it has shown no edge to pay for a debit spread's time decay and costs.

The owner's options (plan §6):

1. **Keep Paper running** on today's rules, to collect real fills and forward
   evidence. It costs nothing.
2. **Pause new Paper entries**, keeping the system running.
3. **Commission a new hypothesis**, written as its own plan before anything is
   computed, and tested forward. D3's lower third (weak 20-session runs) is
   one candidate. It was found on seen data, so only a forward test could
   support it.

This study recommends no rule change on its own.
