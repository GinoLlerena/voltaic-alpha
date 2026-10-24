# Options Alpha — Breadth veto backtest: Part 2 report (simulated spreads)

| Field | Value |
|---|---|
| Date | 23 October 2026, America/Lima |
| Status | **Steps 4 to 6 complete. Stop point: the owner reviews this report (plan §8 Step 6, then Step 7). No result changes the bot.** |
| Plan | [Breadth veto backtest: plan](../improvements/options_alpha_veto_backtest_plan_v0_1.md) §5 and §8 Steps 4 to 6 |
| Protocol | [Numeric protocol](../improvements/options_alpha_veto_backtest_protocol_v0_1.md) §§1–8, frozen 12 October 2026. The Step 4, 5 and 6 details in §11 were each committed before that step ran |
| Part 1 | [SPY outcomes](options_alpha_veto_backtest_part1_v0_1.md): no measurable separation on SPY's move |
| Data | Approved by the owner on 23 October 2026 (plan §9): 402 entry chains and 149 exit paths, plus the 2024–2026 calendar, all read-only, listed in the [manifest](options_alpha_veto_backtest_manifest.json) |
| Reproduce | `uv run python -m options_alpha_lab.veto_entries`, then `veto_exits`, then `veto_portfolio` |

## 1. The answer in plain words

**Taken one at a time, the trades the breadth veto blocked did no worse than
the ones it allowed. On average they did better.** They pass the study's
"no worse" test in all three cost cases. That test is the bar a proposal to
change the veto would have to clear.

**But the strategy loses money in this simulation, with or without the veto.**
Run as the bot runs it, one position at a time from $100,000, both portfolios
end lower in every cost case. Removing the veto loses more, not less, because
it takes more trades at a negative average.

| Central cost case ($0.05 a share each way) | Permitted | Breadth-vetoed |
|---|---:|---:|
| Trades (independent setups) | 84 | 65 |
| Mean result per one-contract spread | **−$29.64** | **+$5.98** |
| Median | −$34.40 | +$13.69 |
| Win rate | 38.1% | 55.4% |
| Worst trade | −$370.41 | −$320.16 |

Breadth-vetoed minus Permitted: **+$35.62** per spread, 95% interval
**−$8.85 to +$74.86**. The "no worse" test needs the lower end above −$15. It is.

| Portfolio, $100,000 start, one position | Baseline (with the veto) | Without the breadth veto |
|---|---:|---:|
| Optimistic | −$927.89 (54 trades) | −$1,080.36 (83 trades) |
| Central | **−$1,478.12** (54) | **−$2,038.43** (84) |
| Pessimistic | −$1,821.34 (54) | −$2,633.80 (84) |

**The reading.** The veto doesn't pick out bad trades. The vetoed ones were,
if anything, the better half. But keeping it reduces how often a strategy
with a negative simulated average trades, so it limited the losses. The
bigger question this raises is whether the entry setup and its exits have an
edge at all. Part 1 pointed the same way: the setup's days lagged ordinary
days on SPY.

## 2. What the decision rule says

Plan §8 Step 7 lists three outcomes. This study lands on the third row, with
two warnings.

| Condition for row 3 | Result |
|---|---|
| Vetoed trades meet the "no worse" test in all three cost cases (lower end above −$15) | **yes**: −$8.95, −$8.85, −$12.51 at the frozen block length |
| Reconstruction quality acceptable | parity gates passed in Step 1. Trade-derived prices and synthetic quotes remain a model (§6) |
| Portfolio results reviewed | **they argue against removing the veto**: it loses more in every cost case |

Row 3's own wording: "Consider a separate proposal with its own review and
Paper testing; this study alone does not authorize a change."

**Warning 1, fragile.** At a block length of 5, the pessimistic case's lower
end is −$16.21, just past the margin. At 10 (the frozen value) and 20 it
passes. The result holds at the protocol's settings and not by much.

**Warning 2, the portfolio.** Removing the veto would not have made money in
any case. It would have lost $150 to $800 more over the period.

## 3. Step 4: the entries

The bot's own selector, baseline thesis and risk governor, unchanged, on the
10:00 call chain rebuilt from traded prices with synthetic quotes
(`k = 0.6224%`).

| Session outcome | Permitted (241) | Breadth-vetoed (161) |
|---|---:|---:|
| **Entered** | **84** (35%) | **65** (40%) |
| A leg did not trade in the 10:00–10:05 fill bar | 87 (36%) | 52 (32%) |
| Selector found no eligible pair | 51 | 27 |
| Risk governor refused (max loss above $750) | 19 | 17 |
| Legs' bars more than 10 minutes apart | 0 | 0 |

- **Missing data is similar in both groups.** The largest exclusion, an
  untraded leg in the fill bar, is 36% against 32%. That is close enough not
  to drive the comparison, but it means most sessions never produce a trade.
- **The leg-time limit never binds.** With the 15-minute age limit, two bars
  can be at most 10 minutes apart, so this gate is redundant.
- **The spreads:** 14 to 18 days to expiry (median 14), 4 to 15 wide (median 7),
  estimated debit 1.88 to 7.06 (median about 4).
- **9 October 2026, the first Paper trade.** The study chooses the 774/781
  calls expiring 23 October. The bot bought the 775/781 calls with the same
  expiry: same short strike, long strike one apart. The bot decided at 09:45
  and the study at 10:00, so this is close agreement, not a mismatch. Fill
  reference 3.62 against the bot's real fill of 3.25.

## 4. Step 5: exits, independent setups

Each entry stepped through its legs' 5-minute bars, with the shipped
`evaluate_exit` deciding at every observation and the shipped calendar
counting sessions. Every trade resolved: **no unresolved exit and no value
outside 0 to the width**, in any case.

| Case | Group | Trades | Win rate | Mean | Median | Worst | Total |
|---|---|---:|---:|---:|---:|---:|---:|
| Optimistic | Permitted | 84 | 45.2% | −20.32 | −24.40 | −360.41 | −1,706.75 |
| | Vetoed | 65 | 58.5% | +16.06 | +23.69 | −310.16 | +1,043.86 |
| Central | Permitted | 84 | 38.1% | −29.64 | −34.40 | −370.41 | −2,489.38 |
| | Vetoed | 65 | 55.4% | +5.98 | +13.69 | −320.16 | +388.92 |
| Pessimistic | Permitted | 84 | 34.5% | −39.79 | −48.36 | −287.67 | −3,341.96 |
| | Vetoed | 65 | 50.8% | −7.97 | +2.00 | −330.16 | −518.22 |

Breadth-vetoed minus Permitted, mean USD per spread, moving-block bootstrap
over the 676-session sequence (10,000 replicates, seed 20261012):

| Case | Difference | Block 10 (frozen) | Block 5 | Block 20 | Lower end above −$15? |
|---|---:|---|---|---|---|
| Optimistic | +36.38 | −8.95 to +76.37 | −11.82 to +77.79 | −5.54 to +72.64 | yes |
| Central | +35.62 | −8.85 to +74.86 | −11.69 to +76.27 | −5.19 to +70.88 | yes |
| Pessimistic | +31.81 | −12.51 to +70.55 | **−16.21** to +71.84 | −7.62 to +65.72 | yes at 10 and 20 |

The sample clears the protocol's minimum: 84 trades in 49 clusters and 65
in 30. By year (central): Permitted −$17 (2024, 35 trades), −$20 (2025, 34),
−$79 (2026, 15). Vetoed −$7 (29), +$42 (28), −$72 (8). 2025 carries most of
the vetoed group's advantage, and 2026 is small and poor for both.

**How the trades ended (central):**

| Exit | Permitted | Vetoed |
|---|---:|---:|
| Session stop (3 completed sessions) | 64 | 54 |
| Stop loss (value at half the debit) | 15 | 5 |
| Invalidation (close below 98.5% of `C[-1]`) | 4 | 2 |
| Profit capture | 1 | 4 |

Three out of four trades end at the session stop. The profit target, 60% of
the maximum gain, was reached 5 times in 149. On these spreads the target
sits far away for a three-session hold.

**9 October 2026, against the real trade.** The study exits at the session
stop on 14 October at 09:35 (+$8 central). The bot's session stop fired on
14 October at 09:30, the same moment, but its close was blocked by the
chain-read bug fixed in #96. It closed on 15 October at a stop loss, −$189.
The timing matches. The result differs because of a live fault the study
does not model.

## 5. Step 6: portfolios

Same entries, same trades, $100,000 start, a budget of 0.75% of running
equity, one position, re-entry from the session after an exit fill.

| Case | Arm | Trades | From vetoed sessions | Wins | Total | Largest fall | 2024 | 2025 | 2026 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Optimistic | Baseline | 54 | 0 | 24 | −927.89 | 1,396.50 | −119.43 | −35.31 | −773.16 |
| | Without veto | 83 | 33 | 39 | −1,080.36 | 1,858.88 | −355.12 | +208.34 | −933.58 |
| Central | Baseline | 54 | 0 | 22 | −1,478.12 | 1,524.27 | −382.63 | −257.85 | −837.64 |
| | Without veto | 84 | 34 | 36 | −2,038.43 | 2,086.65 | −866.16 | −114.20 | −1,058.07 |
| Pessimistic | Baseline | 54 | 0 | 19 | −1,821.34 | 1,830.45 | −554.87 | −376.26 | −890.21 |
| | Without veto | 84 | 34 | 33 | −2,633.80 | 2,633.80 | −1,130.55 | −332.61 | −1,170.64 |

Per trade, removing the veto is slightly better (central: −$24.27 against
−$27.37). But it trades 56% more often, and at a negative average more trades
lose more. One position at a time also means the two arms trade different
sessions. Without the veto, 204 qualifying sessions fall while a position is
open, against 98 with it. The portfolio is not the independent comparison
rearranged.

No confidence interval is given for the portfolios (protocol §8).

## 6. What this simulation cannot see

- **Traded prices, not quotes.** There is no bid/ask history. Each leg is
  priced at its 5-minute volume-weighted trade price, with a synthetic quote
  of ±0.62% for selection. Real fills could be better or worse. The first
  Paper trade filled 0.37 below the study's reference on a different strike.
- **The long leg trades rarely.** It is in the money, and in many bars it
  does not trade. 101 of the 149 central exits filled in the bar right after
  the trigger. The other 48 waited 2 to 9 bars or more, at whatever price came
  next. Many observations could not be valued, so the stop and target were
  checked less often than the bot checks them live.
- **5-minute bars.** A stop or target touched inside a bar is missed.
- **One decision a day, at 10:00.** The bot may enter from 09:45 to 15:15 and
  may re-enter the same day. The study does neither.
- **Calm markets only** (Part 1, Step 2 §3).
- **No fees.** About a few cents a contract, ignored as the protocol states.
- **The baseline thesis only.** No model memo, as no historical model calls exist.
- **Known period.** 22 September to 9 October 2026 was seen before the study.

## 7. What the owner decides now

My recommendation:

1. **Keep the breadth veto as it is.** Removing it would have lost more in
   every portfolio case. The "no worse" result on single trades holds at the
   frozen settings, but only narrowly in the pessimistic case. The plan does
   not allow a change from this study alone either way.
2. **The more important finding is the strategy itself.** Both arms lose.
   The setup's average simulated trade is negative in every cost case, and
   three in four trades end on the time stop. Before more Paper evidence
   accumulates, consider a separate, pre-registered study of the entry setup
   and the exit rules: profit target distance, session stop length, entry
   time. That would be new work with its own protocol. No rule here has been
   tuned, and none should be tuned on this data.
3. **Paper trading can stay armed.** It costs no money, and it is the only
   source of real fills. It now has a measured expectation to be compared
   against: about −$30 a trade in the central case.

## 8. Method and reproducibility

| Step | Module | Digest |
|---|---|---|
| 4 | `src/options_alpha_lab/veto_entries.py` | entries `sha256:6b8227c52017c5d5180d3641d96ed8d5ab479eca3585ca610a42d6f4633b2633` |
| 5 | `src/options_alpha_lab/veto_exits.py` | trades `sha256:59d5e170cb6a564e27ea09c35dbb992e38c6e399ed9040f656de223112dc8fa7` |
| 6 | `src/options_alpha_lab/veto_portfolio.py` | from the trades above |

- **Shipped code, unchanged:** `DeterministicBaselineThesis`,
  `DeterministicSpreadSelector`, `DeterministicRiskGovernor`, `crossing_debit`,
  `evaluate_exit`, `TradingCalendar`. Step 2's rows digest
  (`sha256:e959635b…4080`) is reproduced, and Step 3's report is unchanged
  after its bootstrap was shared with Part 2.
- **Hand checks:**
  - **8 February 2024**, central case. The session stop fires at 09:35 on
    13 February after closes on 8, 9 and 12 February. It fills in the
    09:35–09:40 bar at 2.87125 − 0.937067 − 0.05 = 1.8842, a result of −$101.58.
  - **2 June 2025**, central case. The fill reference is
    8.707778 − 3.575 = 5.1328. The exit is the first bar with both legs
    after the 09:35 trigger on 5 June: 13.38 − 6.4243 − 0.05 = 6.9057,
    a result of +$172.29.
- **Two errors were found and fixed during the build**, both before any
  result was read:
  - The session stop had counted a close at the closing instant itself.
  - One lookup had mixed UTC and New York times.

  Both have tests.
- **Tests:** `tests/test_veto_entries.py`, `tests/test_veto_exits.py`,
  `tests/test_veto_portfolio.py`.
