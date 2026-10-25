# Options Alpha — Setup and exit study, Part A: where the loss comes from

| Field | Value |
|---|---|
| Date | 24 October 2026, America/Lima |
| Plan | [Setup and exit study plan](../improvements/options_alpha_setup_exit_study_plan_v0_1.md), §3, with the definitions fixed in §3.1 before computing |
| Inputs | The Part 2 entries, trades and exit paths, unchanged. Trades digest `sha256:59d5e170cb6a564e27ea09c35dbb992e38c6e399ed9040f656de223112dc8fa7`, the same as the Part 2 report |
| Code | `src/options_alpha_lab/study_decomposition.py`; run `uv run python -m options_alpha_lab.study_decomposition --all-cases` |
| Status | Descriptive only. No rule is changed and nothing here is a test |

## 1. Summary

The loss is **not** at the entry and **not** in waiting for exit fills. It
builds while the spread is held, and it builds because SPY, on average, does
not rise after the sessions the bot trades.

- **Entry:** at the entry day's close, before costs, a Permitted spread is
  worth −$7.72 [−22.11, +5.07] against what it cost. Fills came in below the
  bot's own estimate in 69 of 84 trades.
- **Exit delay:** waiting for a bar in which both legs traded cost
  +$0.41 [−4.14, +4.58] a trade on average. One exception, on five trades: the
  profit target always filled about $33 below the value that triggered it.
- **While held:** before costs, the value falls by about $24 a session:
  −$7.72 at the first close, −$31.00 at the second, −$55.43 at the third.
- **Direction:** the result follows SPY's 3-session move closely. After
  Permitted sessions that move averaged **0.00%**. When SPY went roughly
  nowhere (the middle third), the spread still lost $37.20 in the central case.

So the trend-retest setup, as traded, does not pick sessions that are followed
by a rise. A debit call spread held for three sessions without that rise
loses to time decay and costs. Exit rules can change how much is lost, but
they cannot supply the direction.

## 2. Numbers

Central cost case (5 cents a share each way), Permitted trades (the bot's
rule), 84 trades, none unresolved. Mean per spread in USD, with the frozen
95% moving-block interval (block 10, 10,000 replicates, seed 20261012).
Every case and group is in the script's output.

| | Central | Optimistic (no costs) | Pessimistic |
|---|---|---|---|
| Result per spread (Part 2) | −29.64 [−60.09, +2.69] | −20.32 [−50.99, +12.19] | −39.79 [−67.67, −8.40] |

### A1. Value at the first three closes, against the entry debit

The value is read whether or not the trade had already exited, so it shows
the spread's path. In the central case, $10 of each figure is the round-trip
cost.

| Close | Central | Optimistic | Trades measured (missing) |
|---|---|---|---|
| Entry day, `C0` | −17.72 [−32.11, −4.93] | −7.72 [−22.11, +5.07] | 72 (12) |
| Next session, `C1` | −41.00 [−62.82, −24.27] | −31.00 [−52.82, −14.27] | 69 (15) |
| Session after, `C2` | −65.43 [−98.73, −30.07] | −55.43 [−88.73, −20.07] | 62 (22) |

Breadth-vetoed trades, central case, for comparison: −7.80, −9.77, −18.08.

### A2. Cost of waiting for an exit fill

| Permitted, central | Mean | Trades (trigger value missing) |
|---|---|---|
| All closed trades | +0.41 [−4.14, +4.58] | 69 (15) |
| Waited 2 observations or more | −3.04 [−14.51, +8.34] | 16 (10) |

58 of 84 exits filled at the next bar. Four waited more than 50 bars, which
is more than a full session, because no bar had both legs trading.

The 15 missing trigger values are session stops. They fire at the first
observation of a session, when often neither leg has traded in the previous
15 minutes.

The profit target fired on all five such trades, Permitted and Breadth-vetoed
together. Each filled $26.86 to $38.88 below its trigger value: −$32.69
[−35.29, −28.78] on average, four of the five at the very next bar. The target
seems to fire on a high reading that is gone a bar later. With five trades,
this is an observation, not a finding.

### A3. Result by SPY's 3-session move

The trades are split into thirds by SPY's move from `C[-1]` to `C[2]` (Part 1).
The cut points come from the moves alone. 82 of 84 trades have the move; for
the last two, `C[2]` has not happened yet.

| Permitted, central | SPY move | Mean result |
|---|---|---|
| Lowest third (28) | −2.81% to −0.41% | −140.77 [−176.84, −105.21] |
| Middle third (27) | −0.39% to +0.44% | −37.20 [−80.06, +0.72] |
| Highest third (27) | +0.49% to +2.16% | +100.96 [+67.92, +140.24] |

The middle third is −29.10 [−71.19, +7.91] with no costs, and −49.67 [−91.16,
−11.67] in the pessimistic case.

### A4. Entry price

- **Fill against the bot's estimate:** the fill reference `P` is $14.61
  [8.39, 19.65] below the estimated debit, which includes the crossing
  allowance. It is above the estimate in 15 of 84 trades. The bot does not
  overpay against its own screen.
- **Debit over width,** in thirds (central, Permitted): −35.34, −3.94 and
  −49.63. Every interval spans more than $80 and includes zero, so there is no
  pattern. Over both groups, the most expensive third (debit above 55.5% of
  the width) is −44.08 [−88.13, −2.95]. That is one of many cells, and is
  noted only.

### Context, not in §3.1

These lines were added after seeing the results, to explain A3. They are
descriptive:

- **Mean SPY 3-session move:** after Permitted sessions +0.001% (median
  +0.065%, up in 42 of 82). After Breadth-vetoed sessions +0.230% (median
  +0.483%, up in 45 of 65). This is the same pattern as Part 1, and it is why
  the vetoed trades did better.
- **Least-squares line, result against SPY's move:** Permitted, central, about
  +$101 per 1% of SPY move, and −$27 at a move of zero.

## 3. Limits

- Same data as Part 2, so every Part 2 limit applies. That includes the
  values rebuilt from 5-minute bars and the synthetic quotes.
- **Missing A1 values** (12 to 22 of 84) are closes at which a leg had not
  traded in the last 15 minutes. They may not be missing at random: thinly
  traded spreads may differ.
- A3 and A4 split the trades into thirds of about 28. Their intervals are wide.

## 4. What it means for Part B

The plan (§4) is frozen and this does not change it. On the open decision 3,
the two downloads:

- **B5, 21–45 days to expiry:** Part A points to time decay while held, with
  no directional gain to offset it. A longer expiry loses less value a day, so
  B5 tests the cause Part A found. **Recommend approving its download.**
- **B4, 11:00 entry:** Part A finds nothing wrong at the entry. The entry-day
  change before costs includes zero, and fills beat the estimate.
  **Recommend not downloading for B4.** Dropping a variant leaves fewer
  comparisons, so the §4 reading rule, written for six, becomes stricter, not
  looser.
- **B1–B3** (session stop, profit target, stop loss) need no download. Part A
  suggests they can reduce the loss but not reverse it, since the direction
  is missing.
