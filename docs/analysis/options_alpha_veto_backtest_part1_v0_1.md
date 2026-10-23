# Options Alpha — Breadth veto backtest: Part 1 report (SPY outcomes)

| Field | Value |
|---|---|
| Date | 23 October 2026, America/Lima |
| Status | **Step 3 complete. Stop point: the owner decides whether Part 2 (option spreads) is worth building.** |
| Plan | [Breadth veto backtest: plan](../improvements/options_alpha_veto_backtest_plan_v0_1.md) §4.3 and §8 Step 3 (`VBT-103`) |
| Protocol | [Numeric protocol](../improvements/options_alpha_veto_backtest_protocol_v0_1.md) §8, frozen 12 October 2026. The Step 3 details in §11 were committed on 23 October 2026 (`ff48c85`), before any outcome was computed |
| Previous step | [Step 2 signal replay](options_alpha_veto_step2_replay_v0_1.md), rows digest `sha256:e959635b…4080`, reproduced unchanged |
| Reproduce | `uv run python -m options_alpha_lab.veto_outcomes` (about 25 s) |
| Boundary | SPY price moves only. No option price, no trade, no rule change. |

## 1. The answer in plain words

**On SPY's own move, the breadth veto does not separate good days from bad
ones. If anything, it went the other way.** Over the three sessions after a
decision, SPY rose a little more after the sessions the veto blocked than
after the ones it allowed. The gap is small and the interval includes zero, so
the honest reading is **no measurable difference**. Nothing here shows that the
veto protects the strategy, and nothing shows that it hurts it.

| Three-session SPY move from `C[-1]` | Sessions | Mean |
|---|---:|---:|
| Permitted (the bot would have entered) | 239 | **−0.036%** |
| Breadth-vetoed (blocked by breadth alone) | 161 | **+0.165%** |
| Difference, Permitted minus Vetoed | | **−0.201%**, 95% interval −0.511% to +0.127% |

Two other findings matter as much as the main one:

1. **The setup itself lags an ordinary day.** All qualifying sessions together
   (Permitted plus Vetoed, 400) averaged +0.045% over three sessions. Every
   replayed session, whatever the bot would have decided, averaged +0.220%.
   The bullish trend-retest setup has picked days that did worse than average
   on the underlying. This is a question about the setup, not the veto, and
   the study was not designed to answer it. It is reported, not tested.
2. **Every one of these sessions was in a calm market** (Step 2, §3). The study
   says nothing about the veto when volatility is high.

**Limit, again:** SPY's move is not the spread's result. A call spread caps the
gain, and its stop and target fire during the day. Part 1 cannot show profit.

## 2. Counts

| Group | Sessions | All three closes | Censored | Clusters | Longest run |
|---|---:|---:|---|---:|---:|
| Permitted | 241 | 239 | 9 Oct (two closes), 12 Oct (one close) | 40 | 13 |
| Breadth-vetoed | 161 | 161 | none | 36 | 19 |

Both groups clear the protocol's minimum for a conclusion: at least 30
sessions and 10 clusters each (§8). That is a screen, not proof of power.
Consecutive sessions share most of their three-session window, and the
sessions come in runs, so the effective sample is far smaller than the counts.

The cached daily bars end on 12 October 2026. The two censored sessions keep
the horizons that exist and drop out of the rest. No missing close is read as
zero, and no group is compared on a horizon the other lacks.

## 3. All measured outcomes

Moving-block bootstrap, block length 10 sessions, 10,000 replicates, seed
20261012, 95% percentile interval (protocol §8 and §11). Every replicate drew
members of both groups.

| Measure | Permitted | n | Vetoed | n | Permitted − Vetoed | 95% interval |
|---|---:|---:|---:|---:|---:|---|
| **3-session move, % (primary)** | −0.036 | 239 | +0.165 | 161 | **−0.201** | −0.511 to +0.127 |
| 1-session move, % | −0.018 | 241 | +0.083 | 161 | −0.100 | −0.239 to +0.037 |
| 2-session move, % | −0.016 | 240 | +0.105 | 161 | −0.121 | −0.361 to +0.133 |
| 3-session move, USD per share | −0.355 | 239 | +0.944 | 161 | −1.299 | −3.242 to +0.752 |
| Invalidation breached, % of sessions | 13.8 | 239 | 8.1 | 161 | +5.7 | −2.7 to +13.4 |
| Worst close within 3 sessions, % | −0.493 | 239 | −0.291 | 161 | −0.201 | −0.455 to +0.066 |

Excluded for a censored value: Permitted 0 at one session, 1 at two, 2 at
three; Vetoed 0 throughout.

Every measure points the same way: the Permitted sessions did a little worse.
They breached the invalidation level more often (33 of 239 against 13 of 161)
and had a deeper worst close. None of the intervals excludes zero.

### Block-length sensitivity (primary measure)

| Block length | Difference | 95% interval |
|---:|---:|---|
| 5 | −0.201 | −0.484 to +0.086 |
| **10 (frozen)** | −0.201 | −0.511 to +0.127 |
| 20 | −0.201 | −0.551 to +0.151 |

The conclusion does not depend on the block length.

## 4. Breakdowns (primary measure)

Fixed in the protocol before the results (§8). Five subgroups are compared
here, so one interval excluding zero by chance would not be surprising.

| Subgroup | Permitted | n | Vetoed | n | Difference | 95% interval |
|---|---:|---:|---:|---:|---:|---|
| 2024 | +0.109 | 97 | +0.032 | 67 | +0.077 | −0.479 to +0.718 |
| 2025 | −0.018 | 86 | +0.320 | 62 | −0.338 | −0.733 to +0.093 |
| 2026 (to 12 Oct) | −0.314 | 56 | +0.146 | 32 | −0.461 | −1.236 to +0.224 |
| Realized volatility at or below the median | −0.287 | 99 | +0.199 | 100 | −0.486 | **−0.861 to −0.084** |
| Realized volatility above the median | +0.142 | 140 | +0.111 | 61 | +0.031 | −0.411 to +0.492 |

The median of the 20-session realized volatility over the 402 qualifying
sessions is 0.678% a day (about 10.8% a year).

- 2024 is the only year in which the Permitted sessions did better, and only
  slightly.
- In the quieter half of sessions, the vetoed sessions did better and the
  interval excludes zero. This is the one place in the study where the veto
  looks harmful on SPY's move. It is one of five subgroups and is not adjusted
  for that, so it is a lead, not a finding.

## 5. Other breadth lines (context only, not a rule proposal)

Plan §4.3 and §6.2: shown side by side, never used to choose a line.

| Breadth line | Permitted | n | Vetoed | n | Difference | 95% interval |
|---|---:|---:|---:|---:|---:|---|
| 0.60 | −0.016 | 191 | +0.101 | 209 | −0.117 | −0.433 to +0.210 |
| **0.70 (the rule)** | −0.036 | 239 | +0.165 | 161 | −0.201 | −0.511 to +0.127 |
| 0.80 | +0.027 | 292 | +0.094 | 108 | −0.067 | −0.438 to +0.345 |
| Off | +0.045 | 400 | | 0 | | |

No line separates the groups. The 0.70 row reproduces the main result exactly,
a check that regrouping from the stored breadth strength gives back the Step 2
buckets.

## 6. Indexing, checked by hand

`C[-1]` is the last completed close the decision read; `C[0]` to `C[2]` are the
closes of the decision session and the two after it (plan §4.3). The
invalidation level is `C[-1] × 0.985`, rounded to the cent, as the classifier
sets it. A breach is a close strictly below that level.

| Session | Group | `C[-1]` | `C[0]`, `C[1]`, `C[2]` | 3-session move | Level | Breached |
|---|---|---|---|---|---|---|
| 6 Feb 2024 | Vetoed | 492.55 (5 Feb) | 493.98, 498.10, 498.32 | +1.1715% | 485.16 | no |
| 8 Oct 2026 | Vetoed | 777.22 (7 Oct) | 773.93, 778.57, 778.10 | +0.1132% | 765.56 | no |
| 9 Oct 2026 | Permitted | 773.93 (8 Oct) | 778.57, 778.10, not cached | censored | 762.32 | not measured |

For example, 498.32 / 492.55 − 1 = +1.1715%, and 492.55 × 0.985 = 485.16.
The module's figures match these by hand. `tests/test_veto_outcomes.py` checks
the same indexing on a small series, plus the censored end and a missing
session, which is refused rather than shifting every horizon by one.

9 October is the session of the first real Paper trade. Its spread closed at a
loss of $189 on 15 October. SPY's move over its first two sessions was +0.54%,
which shows how little SPY's close-to-close move says about a spread's result.

## 7. What this study cannot see

- **Only one evidence mode.** The volatility input was reconstructed from
  traded option prices (Steps 1 and 2). No proxy mode was run, so there is
  nothing to keep separate.
- **Calm markets only** (Step 2, §3). Stressed periods had bearish structure,
  which is out of scope.
- **Moves include the overnight gap before entry.** `C[-1]` is the previous
  close, and the bot enters after 09:45 the next day.
- **Price only, no dividends.** The bars are split-adjusted, as the bot reads
  them. An ex-dividend day lowers the move of every session whose window holds
  it, by about 0.3%, in both groups.
- **Overlap.** Most sessions share two of their three closes with a neighbour.
  The block bootstrap allows for that. The counts overstate the information.
- **Known, not a holdout.** The 22 September to 9 October sessions were seen
  before the study began.

## 8. What the owner decides now

Plan §8 Step 3 asks whether Part 2 is worth building. Part 2 rebuilds the
option chain at each entry and simulates the real spread, its exits and three
cost cases. It is several times the work of Part 1.

| Point | Reading |
|---|---|
| Plan's rule of thumb: about 30 usable sessions per side | met: 239 and 161 |
| Does the veto separate on SPY's move? | no measurable separation; the point estimate favours the vetoed side |
| Plan, Step 7, "no measurable difference" | keep the veto unchanged and keep collecting Paper evidence |
| Can Part 1 justify loosening the veto? | **no.** A change needs Part 2's non-inferiority test in all three cost cases (protocol §8, margin $15), then its own review and Paper testing |

My recommendation:

- **Keep the veto as it is now.** The plan's rule applies, and no result
  changes production automatically.
- **Build Part 2 only if you would consider changing the veto.** Part 1 gives
  no sign that the veto helps, so Part 2 is the only way to test whether
  relaxing it would be safe. If you would not change the veto whatever Part 2
  showed, skip it and let the Paper record grow.
- **Worth a separate look:** the setup's qualifying days averaged +0.045%
  against +0.220% for all days. Whether the trend-retest setup has an edge is
  a bigger question than the veto, and outside this study's protocol.

## 9. Method and reproducibility

- **Code:** `src/options_alpha_lab/veto_outcomes.py`. It takes the Step 2 rows
  unchanged, refuses to run if Step 2 parity fails, and reads only the cached
  daily bars for forward closes.
- **Inputs:** the cache files named in the
  [manifest](options_alpha_veto_backtest_manifest.json). Their digests were
  re-checked on 23 October 2026 and all match.
- **Outcomes digest:**
  `sha256:dfefee9d43597949e48f3d63d3812110e72173b49e24570d07d9ee869792e09b`,
  the same on every run.
- **Tests:** `tests/test_veto_outcomes.py`: hand-worked indexing, the breach
  boundary, censoring, refusing a missing session, realized volatility, and a
  bootstrap whose answer is known (equal groups give zero; one block covering
  the whole sequence returns the point estimate; the same seed gives the same
  interval).
