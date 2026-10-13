# Options Alpha — Breadth veto backtest: numeric protocol (decision 9)

| Field | Value |
|---|---|
| Date | 12 October 2026, America/Lima |
| Status | **Approved by the owner on 12 October 2026, as proposed, with no value changed (§10). The values are frozen for the study.** |
| Parent | [Breadth veto backtest: plan](options_alpha_veto_backtest_plan_v0_1.md) §9 decision 9, and §6 control 1 |
| Reviewed revision | `037f9f5` |
| Boundary | Offline research settings only. No trading rule, threshold or worker setting changes. |

The plan requires every numeric choice to be fixed before results exist. This
document proposes a value for each. Where a value is a judgement and not
derived from the code, the table says so, and §9 lists the ones the owner is
most likely to want to change.

## 1. Scope and timing

| Setting | Proposed value | Basis |
|---|---|---|
| Decision sessions | 1 February 2024 to the last session with three later closes available | option-data coverage; feasibility count |
| Direction | bullish setups only | plan decision 6 |
| Decision time | 10:00 ET, once per session | judgement: the entry window opens at 09:45, and 10:00 leaves three completed 5-minute bars |
| Information available at the decision | 5-minute bars that **end** at or before 10:00 ET; daily bars through the previous session | no bar still forming is read |
| Entry fill | the bar covering 10:00–10:05 ET, each leg at that bar's volume-weighted price | a fill never uses the bar that chose the legs |
| Early-close and holiday handling | the real calendar; a session with no bar ending by 10:00 is unmeasurable | |

## 2. Implied volatility and delta

Used twice: for the at-the-money reading that confirms or vetoes a setup
(Part 1), and for choosing spread legs (Part 2). One method for both.

| Setting | Proposed value | Basis |
|---|---|---|
| Pricing model | Black–Scholes–Merton, European exercise, continuous dividend yield | SPY options are American; the early-exercise premium on short-dated calls is small. Stated as an approximation and measured in §7 |
| Option price input | the leg's last 5-minute bar ending by the decision time, volume-weighted price | traded price, not a quote |
| Underlying for pricing | SPY's 5-minute bar ending at the same time as the option bar | contemporaneous spot. The setup rules still use the previous completed close, as the bot does |
| Risk-free rate | the 3-month Treasury bill rate for the previous business day (FRED series DGS3MO) | public daily series; fetched once and cached with its digest |
| Dividend yield | 1.2% a year, constant | judgement; SPY's yield was close to this over the period. Sensitivity run at 0.7% and 1.7% |
| Time to expiry | calendar time from the bar's end to 16:00 ET on the expiry date, divided by 365 | |
| Solver | Brent's method, volatility bounded 1% to 300%, price tolerance $0.0001 | |
| Invalid input | price at or below intrinsic value less $0.01, or no root in the bounds: the contract is dropped and counted | never clipped into a valid value |
| At-the-money reading | the nearest strike to the previous completed SPY close among surviving contracts with 10 to 60 days to expiry, first in contract-symbol order on a tie | mirrors `build_option_chain`; ordering is checked against the live snapshots |

## 3. Data quality limits

| Setting | Proposed value | Basis |
|---|---|---|
| Maximum age of a leg's last trade bar at the decision | 15 minutes | judgement |
| Maximum time between the two legs' bars | 10 minutes | judgement |
| Minimum volume in the bar used | 1 contract | a bar with no trade is not a price |
| Contract existence | listed in the provider's contract record with an expiry on or after the session, and at least one trade bar on or before the session | no use of later data to prove earlier existence |
| A session with no usable at-the-money reading | unmeasurable; counted, not treated as "no setup" | plan §4.2 |

Every exclusion is counted separately for the two groups, so that a difference
in missing data between them is visible.

## 4. Synthetic quotes and selection

There is no bid/ask history, and the bot's spread selection needs a bid and an
ask. The quote is modelled:

| Setting | Proposed value | Basis |
|---|---|---|
| Bid and ask | `price − h` and `price + h` | |
| Half-width `h` | `max($0.01, k × price)` | |
| `k` | the median relative half-spread of contracts inside the bot's two delta bands in the live decision snapshots, measured **once** and then frozen | calibrated from observed quotes, never from outcomes. If the snapshots cannot be exported, `k = 1.0%` |
| Sensitivity | selection re-run at `k/2` and `2k` | |
| Selection | the real `DeterministicSpreadSelector`, unchanged, including the 25% relative-spread limit, expiry-first order and the crossing allowance | plan §5.1 |
| Thesis | the deterministic baseline; no model calls | plan §5.1 |

The crossing allowance is used for eligibility only. Fills are priced as in §5,
so the allowance and the friction cases are not both charged.

## 5. Fills, costs and exits

| Setting | Proposed value | Basis |
|---|---|---|
| Spread reference price `P` | long leg's volume-weighted price minus the short leg's, in the fill bar | |
| Cost cases | entry `P`, `P + 0.05`, `P + 0.10`; exit `P`, `P − 0.05`, `P − 0.10` | plan decision 3, approved |
| Fees | none modelled | the broker charges no commission on options; regulatory fees of a few cents per contract are ignored and stated |
| Quantity | 1 contract (100 shares) | as the bot trades today |
| Exit observation cadence | every completed 5-minute bar while the market is open | |
| Value used to test stop and target | the spread reference at that bar, less the case's exit friction | a conservative mark, as the bot marks at long bid minus short ask |
| Exit fill | the next bar after the trigger, at its reference price less the case's friction | no fill in the bar that triggered |
| Daily-close rules | invalidation and the session stop are acted on at the first bar of the next session | the bot does not manage positions while the market is closed |
| A trigger with no later usable price | the exit is unresolved: reported, excluded from averages, and bounded by assuming the whole debit is lost | never dropped silently |
| Each cost case | simulated on its own from entry, because the debit moves the stop and the target | plan §5.3 |

## 6. Portfolio simulation

| Setting | Proposed value | Basis |
|---|---|---|
| Starting equity | $100,000 | the Paper account |
| Risk budget | the bot's own: 0.75% of equity per trade | `RISK_FRACTION_OF_EQUITY` |
| Positions | one open or pending at a time | the bot's limit |
| Re-entry | earliest at the 10:00 ET decision of the session after an exit fill | judgement; the bot can re-enter the same day, which this study does not model |
| Arms | baseline, and the same with only opposing breadth removed | plan §4.2 |

## 7. Parity gates, checked before outcomes

Measured against the live decision snapshots, which hold the provider's own
implied volatility, delta and quotes.

| Check | Proposed pass level |
|---|---|
| Reconstructed at-the-money implied volatility against the stored value | within 0.010 (one volatility point) on at least 90% of sessions |
| Reconstructed delta against stored delta, contracts in the two delta bands | within 0.03 on at least 90% of contracts |
| Calm/neither/stressed classification of the at-the-money reading | identical on every calibration session |
| Deterministic replay from stored snapshots, same code revision | identical output |

If a gate fails, the reconstruction is reported as not validated and no outcome
is computed until the owner decides how to proceed. The levels are not relaxed
after results are seen. The calibration sample is a few weeks in one calm
regime, so passing validates the method there and not elsewhere.

## 8. Statistics

| Setting | Proposed value | Basis |
|---|---|---|
| Primary metric, Part 1 | mean three-session percentage move of SPY, Permitted minus Breadth-vetoed | plan §6.5 |
| Primary metric, Part 2 | mean net result in USD per one-contract spread, same contrast, central cost case | plan §6.5 |
| Confidence level | 95%, two-sided | convention |
| Resampling | moving-block bootstrap over the chronological sequence of sessions, each block carrying its sessions' group labels | consecutive sessions are not independent |
| Block length | 10 sessions; sensitivity at 5 and 20 | judgement: longer than the three-session outcome and than most runs |
| Repetitions and seed | 10,000; seed 20261012 | reproducible |
| Sessions with no measurable outcome | kept in the sequence as gaps, never filled | |
| Minimum for a conclusion | at least 30 trades and 10 clusters per group; below that the result is inconclusive | a screen, not a power calculation |
| "No worse" margin, Part 2 | $15 per one-contract spread | judgement: about 5% of a typical $325 debit |
| "No worse" test | the lower end of the 95% interval for (Breadth-vetoed minus Permitted) lies above −$15, in all three cost cases | a non-significant difference is not enough |
| Portfolio comparison | reported as paths and per-year results for each cost case, with no confidence interval | a block bootstrap of trades is not valid for a path-dependent portfolio |
| Breakdown | by calendar year, and by whether SPY's 20-session realized volatility was above or below its median | fixed now, so no regime is chosen after the fact |

## 9. The values most worth the owner's attention

| # | Value | Proposed | Why it matters |
|---|---|---|---|
| 1 | Decision time | 10:00 ET | later times have more option trades and less of the opening noise; earlier is closer to the bot's first chance |
| 2 | "No worse" margin | $15 per spread | this is the bar a future proposal to change the veto would have to clear. A smaller margin is stricter |
| 3 | Trade-age limit | 15 minutes | tighter is more accurate but drops more sessions |
| 4 | Dividend yield | constant 1.2% | simple; the alternative is a dated series |
| 5 | Parity levels | one volatility point, 0.03 delta, 90% | they decide whether the reconstruction is trusted at all |
| 6 | Risk-free rate source | FRED DGS3MO | a public download from the Mac, no credential |

## 10. What approval means

Approving this document freezes these values for the study. A later change
needs a dated note in this file saying what changed and why, made before the
affected results are computed. Approval does not authorize any change to the
bot.

**Owner's answer, 12 October 2026: "Agree".** It was given in reply to the
request to review this document, with the six values of §9 listed in that
request. It approves every value here as proposed. The column heading
"Proposed value" is kept as written; the values are now the frozen ones.

## 11. Measured values and implementation notes

Dated notes, as §10 requires. None changes an approved value.

**12 October 2026: `k` measured and frozen at 0.6224% (0.006224).** It is the
median relative half-spread of 2,271 call quotes inside the two delta bands,
from 13 stored decision snapshots, one a session from 22 September to
8 October 2026, each the first at or after 10:00 New York. No quote was
unusable. By band: 0.7576% for the long leg's band and 0.4828% for the short
leg's; session medians ran from 0.4793% to 0.7457%. The input is
`decision_snapshots.json`, named by digest in the
[manifest](../analysis/options_alpha_veto_backtest_manifest.json), and the
measurement is `python -m options_alpha_lab.veto_calibration`. It reads quotes
only. 9 October has no snapshot at or after 10:00, because the position
opened at 09:45 and the worker stopped looking for entries; 12 October has
none for the same reason. The sensitivity runs of §4 use 0.3112% and 1.2448%.

**12 October 2026: two implementation choices**, put to the owner the same day
and accepted ("Agree"):

- The risk-free rate is the published DGS3MO value read as an annual rate,
  with no compounding conversion.
- `k` counts calls only: they are the legs of the bullish spread the study
  covers.
