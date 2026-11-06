# Options Alpha — Setup follow-through study: plan

| Field | Value |
|---|---|
| Date | 5 November 2026, America/Lima |
| Status | **Approved by the owner, 5 November 2026.** §3 and §4 are frozen, with the details in §3.1 fixed the same day, before anything was computed |
| Why | The setup and exit study ([Part A](../analysis/options_alpha_setup_exit_study_part_a_v0_1.md), [Part B](../analysis/options_alpha_setup_exit_study_part_b_v0_1.md)) found the loss comes from direction, not from the exits: after Permitted sessions SPY's 3-session move averaged 0.00%. [Veto backtest Part 1](../analysis/options_alpha_veto_backtest_part1_v0_1.md) had already noted that all qualifying sessions averaged +0.045% over three sessions, against +0.220% for every replayed session |
| Boundary | Offline research only, on data already cached. No download, no paid model call, and no change to any trading rule, threshold or worker setting |

## 1. The question

Do the sessions the trend-retest setup qualifies have any forward edge on SPY
over the sessions it does not? If not, which part of the rule picks sessions
that lag?

The setup buys a bullish debit spread for a rise over one to three sessions.
If the qualifying sessions are not followed by more of a rise than ordinary
sessions, no exit rule can fix the strategy (Part B), and the setup itself is
the problem.

## 2. The problem with answering it from the same data

Part 1's figure was seen before this plan was written, so this study cannot
"discover" it. What it can do:

1. **Measure it properly, once** (§3): qualifying against non-qualifying
   sessions, with the frozen interval, which Part 1 did not do.
2. **Describe where it comes from** (§4), over a short fixed list of splits
   written down now. Nothing in §4 is a test.

Any rule this suggests needs its own plan and forward Paper evidence. Nothing
here is evidence for a new rule.

## 3. Part A: the one comparison

**Inputs.** The Part 1 replay rows (rows digest `sha256:e959635b…4080`,
reproduced unchanged) and the cached SPY daily bars. The groups are those of
the replay:

- **Qualifying:** Permitted plus Breadth-vetoed. These are the sessions where
  the setup's structure and confirmation hold, before the breadth veto.
- **Non-qualifying:** every other replayed session with a measurable outcome.

**Outcome.** Part 1's SPY move from `C[-1]` (the last completed close the
decision read) to `C[h]`, in %, for h = 1, 2 and 3. **The primary outcome is
h = 3.**

**Comparison.** The mean for qualifying minus the mean for non-qualifying,
with Part 1's frozen moving-block interval (`veto_outcomes.block_contrast`:
block 10, 10,000 replicates, seed 20261012, percentile 95%), and again at
blocks 5 and 20.

**Reading.**
- *The setup lags:* the interval at h = 3 lies wholly below zero at all three
  block lengths.
- *The setup leads:* it lies wholly above zero at all three.
- *Otherwise:* no measurable difference. That still means the setup has no
  shown edge to pay for a debit spread's time decay and costs.

### 3.1 Details fixed on approval, before computing

The owner approved §3 and §4 on 5 November 2026. These details were left open
by the draft and are fixed here, before any outcome is computed:

1. **The h-session move** is Part 1's: from `C[-1]` to the h-th close after it.
   In Part 1's notation that close is `C[h-1]`, so h = 3 is `C[2]`, as in
   Part 1's +0.045% and +0.220%.
2. **Non-qualifying** means the replay's No setup, Out of scope (bearish
   structure) and Other/multiple vetoes sessions. Unmeasurable sessions are
   left out, because the rule was never evaluated on them. Their count is
   reported for context.
3. **A session counts** in §3 and §4 only if all h closes after `C[-1]` are
   cached. Censored sessions are counted and reported.
4. **The confirming family (D1)** is the one the classifier itself picks: the
   strongest bullish non-structure signal at or above 0.50, with ties broken by
   signal ID. It is rebuilt from each row's stored signals. For Breadth-vetoed
   sessions the bearish breadth reading is not bullish, so the same rule
   applies.
5. **Structure strength (D2)** is the strength of the anchor: the strongest
   bullish structure signal.
6. **Thirds (D2 to D4)** are cut from the qualifying sessions with an h = 3
   outcome, ranked by the split variable. The two cut values sit at ranks
   ⌈n/3⌉ and ⌈2n/3⌉. Lower is at or below the first, middle is above it and at
   or below the second, upper is the rest. Ties go to the lower third, and the
   cut values are reported. D3 is `(C[-1] − C[-21]) / C[-21]` and D4 is
   `(C[-1] − C[-2]) / C[-2]`, in %, from the cached SPY daily bars.

## 4. Part B: where it comes from (descriptive, fixed list)

The qualifying sessions only, at h = 3. Each split is made on information the
decision had. The thirds are cut from the split variable alone, never from the
outcomes. Each line reports the mean and its block-10 interval
(`study_decomposition.block_mean`).

| # | Split | Why |
|---|---|---|
| D1 | The confirming family: momentum, participation, or volatility | Does one kind of confirmation pick the lagging days? |
| D2 | The structure signal's strength, in thirds | Do stronger trends follow through better or worse? |
| D3 | SPY's move over the 20 sessions up to `C[-1]`, in thirds | Does the setup fire late in extended runs? |
| D4 | SPY's move on the last completed session, `C[-2]` to `C[-1]`, in thirds | Is it buying right after an up day that then reverts? |

Non-qualifying sessions are shown alongside D3 and D4, in the same thirds'
ranges, so a pattern of the whole market is not mistaken for one of the setup.

## 5. What it will not do

- No search over thresholds, lookbacks or new signals, and no combining of
  splits.
- No change to the classifier, the breadth veto, the exits or the risk budget.
- No option prices. This is about SPY's direction only.
- No claim beyond February 2024 to October 2026, a calm market throughout
  (Part 1, §1).

## 6. What the results would mean

- **No edge, or a lag (the likely result):** the setup, as built, has not
  picked sessions worth a debit spread in this period. The owner's options
  would then be to:
  - keep Paper running to collect real evidence;
  - pause new entries;
  - commission a new hypothesis, written as its own plan and tested forward.
- **One split stands out:** it is a hypothesis for a new plan, not a rule. It
  was found on seen data, among four splits.

## 7. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| 1 | Approve §3 and §4 as written, before anything is computed? | Yes, or edit now. They cannot change after |
| 2 | Keep Paper armed with today's rules meanwhile? | Yes. It costs nothing and gives real fills |
