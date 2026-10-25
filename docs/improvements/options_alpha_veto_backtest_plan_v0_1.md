# Options Alpha — Breadth veto backtest: plan

| Field | Value |
|---|---|
| Date | 12 October 2026, America/Lima |
| Status | **Decisions 1–8, 10 and 11 approved by the owner on 12 October 2026 (§9). Feasibility count done: go. Decision 9 (numeric protocol) approved the same day, values in the [protocol](options_alpha_veto_backtest_protocol_v0_1.md). Step 1 done ([coverage](../analysis/options_alpha_veto_step1_coverage_v0_1.md)). Step 2 done on the owner's "Agree ... go" of 15 October 2026 ([replay](../analysis/options_alpha_veto_step2_replay_v0_1.md)): parity 14/14, 241 Permitted and 161 Breadth-vetoed sessions. Step 3 done on the owner's "proceed" of 23 October 2026 ([Part 1 report](../analysis/options_alpha_veto_backtest_part1_v0_1.md)): no measurable separation on SPY's move (Permitted minus Breadth-vetoed −0.201%, 95% interval −0.511% to +0.127%). Part 2 built on the owner's "proceed" of 23 October 2026 ([Part 2 report](../analysis/options_alpha_veto_backtest_part2_v0_1.md)): vetoed trades meet the no-worse test in all three cost cases, but both portfolios lose and removing the veto loses more. **Step 7, owner's decision of 23 October 2026: "The veto keep as it is".** The breadth veto stays unchanged at 0.70; the study is closed.** |
| Requested by | Owner, 7 October 2026: "We can review the veto later with a longer backtest and results for the actual option spreads. I don't want to loosen it just to generate trades." |
| Reviewed revision | `70e1493` |
| Work prefix | `VBT-` |
| Boundary | Offline analysis only. Read-only market data. No change to trading rules, worker configuration or deployment. Any host-side data export requires explicit approval. Paper only. |
| Review | Code review on 12 October 2026; findings and verification evidence in §10. Author's adjustments after that review in §10.3 |

**Review conclusion:** retain the two-stage research approach, but do not implement
the original protocol unchanged. Reconcile the reference observations, supply
volatility inputs before classifying historical setups, and separate estimated
spread outcomes from a capacity-constrained portfolio simulation. Recommendations
below are proposed research requirements, not authorization to change production.

## 1. The problem

### 1.1 How the entry rule works

This study proposes to examine **bullish SPY setups only**. The shipped classifier
also supports bearish setups and the selector supports put spreads; this is a
scope restriction, not a description of the whole strategy. For a bullish setup
to qualify, all three conditions must hold:

| Condition | Threshold | Source |
|---|---|---|
| A structure signal (trend with a recent retest) | strength at least 0.60 | SPY daily bars |
| A confirmation from a different signal family | strength at least 0.50 | any aligned non-structure family; calm ATM IV or aligned breadth can confirm |
| No opposite signal strong enough to veto | no opposing signal at or above 0.70 | any family, including breadth, momentum and stressed volatility |

Qualification is not an order: data quality, thesis, spread eligibility, risk,
entry window and execution controls remain downstream gates. The study must not
label a classified setup an actual trade.

Breadth compares equal-weight RSP with cap-weighted SPY over ten completed
paired sessions. The gap is the change in the **RSP/SPY price ratio**, not a
subtraction of the two percentage returns. The implementation computes:

`strength = round_to_2_decimals(clamp(0.50 + abs(gap) × 25, 0, 1))`

The classifier compares the rounded strength. Under the default Decimal rounding
used in the reviewed code, the following boundaries apply:

| RSP gap against SPY | Breadth signal | Effect on a bullish setup |
|---|---|---|
| absolute gap strictly below 0.2% | none emitted | no breadth veto |
| lagging by at least 0.2%, but less than 0.78% | bearish, rounded strength below 0.70 | no breadth veto |
| lagging by 0.78% or more | bearish, rounded strength at least 0.70, capped at 1.00 | **breadth veto** |

Use the real function and full-precision inputs, not this display table, for
boundary tests. Incomplete paired histories can span more than ten market
sessions; the research data-quality gate must detect that rather than silently
treat it as a valid ten-session observation.

All of these thresholds are marked PROVISIONAL in the code. None has been
validated against outcomes (DEC-008 is open).

### 1.2 Reported observations — reconciliation required

The following table is preserved from the original plan as **reported evidence,
not a verified replay oracle**. The local review did not access production data.

| Session | Structure | Breadth gap | Breadth strength | Result |
|---|---|---|---|---|
| 22 Sep | passed | −3.30% | 0.95 | vetoed |
| 23 Sep | passed | −2.76% | 0.95 | vetoed |
| 24 Sep | passed | −2.25% | 0.95 | vetoed |
| 25 Sep | passed | −2.57% | 0.95 | vetoed |
| 28 Sep | passed | −2.65% | 0.95 | vetoed |
| 5 Oct | 0.59, failed | −2.23% | 0.95 | no setup (not a veto) |
| 6 Oct | passed | −0.90% | 0.73 | vetoed |
| 7 Oct | passed | −0.95% | 0.74 | vetoed |
| 8 Oct | passed | −1.54% | 0.89 | vetoed |
| 9 Oct | passed | −0.11% | none | **traded** |

The original account says these gaps were seen that morning, using the previous
session's closes. Obtain the raw snapshots, precise decision times and deployed
code revisions before treating these observations as acceptance fixtures.

**Confirmed discrepancy:** the current code maps each of the six displayed gaps
from −2.23% to −3.30% to strength **1.00**, not 0.95. This does not change their
veto outcome, but makes an exact strength match impossible as written. The smaller
gaps are rounded for display and cannot establish their exact expected strengths.
Do not change the implementation or silently rewrite historical records to make
the table pass. Record whether the discrepancy is transcription, source data or
deployed-policy drift. The table is also not a complete daily census of the interval.

**Reconciliation, 12 October 2026 (author's reply to R1): transcription error,
not policy drift.** The 0.95 values did not come from the bot's records. They
came from an ad-hoc script that recomputed the gaps from raw closes and applied
a 0.95 cap that the shipped code does not have. The live decision record for
22 September, read through the presentation API, stores the breadth signal at
strength **1.0000** with a gap of −0.0330, and for 6 October at 0.7300 with
−0.0090. The recorded values therefore agree with the shipped function. The
gaps in the table are the recomputed ones, rounded to two decimals; the stored
signals remain the authority, and Step 1 should export them for the whole
interval rather than rely on this table.

For the five vetoed sessions in September, SPY's next-session move was −0.12,
−5.57, −0.63, +4.17 and −5.74 USD per share. Four of five were down, which
is consistent with the veto doing its job. Five sessions prove nothing.

### 1.3 Why this is a problem

1. **One unvalidated number appears decisive in the reported sample.** From 22 September to
   8 October the structure rule passed on eight sessions and the veto removed
   all eight. Whether the bot trades at all is being decided by the 0.70 line.
2. **The veto switches on small moves.** The reported 6 October strength is
   only 0.03 above the threshold; its exact margin requires the raw inputs. On 9 October
   the gap moved from −1.54% to −0.11% in one session and the trade went
   through. A rule this sensitive needs evidence that the line is in a
   sensible place.
3. **There is no evidence either way.** The 0.70 line and the `× 25` scaling
   were chosen by judgement. Nobody has measured whether vetoed setups do
   worse than permitted ones.
4. **Paper trading will not answer it soon.** At the current rate the bot
   takes perhaps one or two trades a month. A fair comparison needs dozens on
   each side, so waiting means years.
5. **SPY's move is the wrong yardstick on its own.** The bot manages a capped
   call spread with a three-completed-session trigger, stop and target. A trigger
   is not a guaranteed fill or a strict maximum holding duration. A day when
   SPY rises can still lose money on the spread. The owner asked for results
   on the actual spreads for this reason.

### 1.4 What must not happen

The owner's instruction is not to loosen the veto just to generate trades. The
risk in a backtest is the same mistake in a different form: trying many
thresholds and keeping the one that looks best. §6 sets the controls.

### 1.5 The questions

The backtest asks three things over a much longer history:

1. How often does the setup qualify, and how often does the veto block it?
2. Do vetoed setups do worse than permitted ones? By how much, and is the
   difference larger than chance?
3. Does the answer hold for estimated historical spreads selected under explicit
   input assumptions and the real exit policy, rather than only SPY's move?
4. Does it still hold in a chronological portfolio that respects the bot's
   one-open-or-pending-strategy limit?

## 2. What this will not do

- It will not change the veto, the 0.70 line, or any other threshold. It
  produces a report. Any change is a separate decision by the owner (DEC-008
  stays open).
- It will not search for the threshold that would have made the most money.
  That is curve fitting, and §6 lists the controls against it.
- It will not be read as proof of an edge. The signal specification (§9)
  forbids that reading, and one strategy on one instrument over a few years is
  a small sample.

## 3. Data availability and provenance

The original plan reports a read-only probe on 12 October 2026 using the bot's
connection. This review did **not** repeat that probe. Retain its sanitized
request parameters, response evidence, feed and coverage results before accepting
the reported availability below.

**Provenance of the 12 October checks (author's note).** The statements in §1.2
and here that production data was not accessed describe the code review. The
plan's author did read production data that day, read-only, and the two should
not be confused:

| Check | How it was run | What it touched |
|---|---|---|
| Decision, position and signal records | GET requests to the presentation API | the live worker database, through the read-only API |
| Entry snapshot contents and stored breadth signals | one SELECT script on the host, through Cloud Assistant | `market_snapshots`, `signals` |
| SPY/RSP gap recomputation | the bot's read-only data client on the host | daily bars endpoint |
| Broker account, positions and orders | GET requests with the same client | Paper trading endpoint, read-only |
| Option data coverage | GET requests with the same client | option bars, trades, quotes and contracts endpoints |

Nothing was written, no service was restarted and no credential left the host.
The scripts were ad hoc and their output was not archived, so none of it counts
as retained evidence. Step 1 repeats the coverage probe and the record export
in a form that is kept: sanitized parameters, responses and hashes in the
manifest.

| Data | Available | Limit |
|---|---|---|
| SPY and RSP daily prices | Yes | at least back to mid-2020 |
| Expired SPY option contracts (listing) | Yes | |
| Option daily and 5-minute bars (traded prices, volume) | Yes | from about 18 January 2024, nothing earlier |
| Option trades | Yes | same start |
| Historical option bid/ask quotes | Reported unavailable through the tested connection | do not generalize this to every provider or subscription |
| Historical greeks (delta) and implied volatility | **No** | must be computed from prices |

Alpaca's [historical option documentation](https://docs.alpaca.markets/us/docs/historical-option-data)
states availability since **February 2024**, which differs from the January 18
date reported above. This is an evidence discrepancy to resolve, not proof that
the probe is wrong. Measure usable coverage per contract and session; an isolated
early bar does not establish complete chain coverage.

Consequences and requirements:

- **Separate evidence levels.** Six-year daily-price diagnostics may be possible;
  a realized-volatility proxy study is not a six-year replay of the live IV rule.
  The shorter option-backed study still uses reconstructed IV, not observed
  historical broker IV. Never combine these populations into one headline result.
- **Part 1 needs option inputs.** Historical ATM IV reconstruction must happen
  before faithful setup bucketing, not first appear in Part 2.
- **No historical quotes means estimated execution.** Trade bars cannot establish
  bid/ask eligibility or actual spread fills. Any synthetic quotes must be labelled
  assumptions and specified before outcomes are computed.
- **Existing adapters are not historical-chain adapters.** `daily_bars` defaults
  to 400 calendar days and split adjustment; `option_contracts` requests active
  contracts; `option_chain` requests current snapshots. Historical discovery and
  prices need dedicated read-only fetching and complete pagination.
- **The committed evidence is insufficient for the reference period.** The daily
  fixture has 562 sessions, 3 June 2024–28 August 2026. The committed calendar
  covers 2026–2027 only. Fetch a calendar covering the entire research horizon,
  warm-up and forward-outcome period; obtain separate September–October fixtures.
- **Live snapshots are the calibration set.** The live database stores a full
  decision snapshot for every recorded decision (1,239 on 12 October 2026, from
  mid-September onward). Each holds the option chain the bot actually saw: bid,
  ask, the provider's delta and implied volatility, and quote times. This is the
  only place where reconstructed values can be compared with observed ones.
  Step 1 exports it read-only and uses it three ways: to measure the error of
  reconstructed IV and delta, to measure real quote widths against the synthetic
  quote rule, and as the exact-input fixtures for the parity gate in §6.4. It
  covers a few weeks in one volatility regime, so it bounds nothing outside
  that regime; report it as a calibration sample, not a validation.
- **Freeze provenance.** Cache data outside git with a small committed manifest:
  hashes, fetch time, endpoints, sanitized parameters, feeds, adjustment policy,
  timezone, pagination/coverage counts and code revision. Keep SIP/IEX and
  indicative/OPRA provenance explicit; do not silently switch feeds for parity.

## 4. Part 1 — Setup classification and underlying outcomes

Work items `VBT-1xx`.

### 4.0 Feasibility count — before any reconstruction (`VBT-100`)

The option-backed work in §4.1 and §5 is the expensive part. Before building
it, count whether there is enough history for it to conclude anything.

**Method.** Over the verified option-data period (and, for context, the full
daily history), replay the daily bars with the production lookback and record
for each session only two things: whether a bullish structure signal reaches
0.60, and whether opposing breadth reaches 0.70. Implied volatility is not
supplied.

**Why this is a valid screen.** Without the volatility input the count is an
**upper bound** on both groups. Supplying it later can only remove sessions:
a session may lose its confirmation, or gain a stressed-volatility veto. It
cannot add a qualifying session. So if the upper bound is too small, the full
study is too small as well.

**What it must not do.**

- It computes **no outcomes**: no forward SPY moves, no returns. Only counts.
  This keeps it outside the protocol freeze in §6.1, because nothing in it can
  be tuned towards a result.
- It is not a classification. Its rows are labelled "structure passed, breadth
  below the line" and "structure passed, breadth at or above the line", never
  Permitted or Breadth-vetoed.
- Aligned breadth can itself be the confirmation, so the bound is on sessions
  passing structure, not on sessions passing the whole rule.

**Reported.** Counts per group and per year, the longest run in each group,
and the number of distinct clusters (runs separated by at least three sessions),
since eight consecutive vetoed sessions carry much less information than eight
separate ones.

**Go/no-go.** Proposed screening rule, to be approved in §9: continue to the
option-backed study only if the upper bound shows at least about 30 sessions
and 10 distinct clusters in each group within the option-data period. Below
that, stop: report that the available history cannot decide the question,
keep the veto unchanged, and continue collecting Paper evidence. Passing the
screen does not promise the full study will be conclusive.

### 4.1 Inputs and replay scope

For each decision session, use only completed daily bars available before the
decision and the production **400-calendar-day lookback**, including sufficient
warm-up. Match provider boundary semantics rather than feeding an expanding
six-year series into the EMA. Reuse `build_signals` and the real classifier.

`sensitivity.signals_over_history` is a useful signal-generation example, **not
an existing classification replay**: it passes `atm_iv=None` and returns signal
summaries without calling the classifier. `gate_study.windows` demonstrates the
bounded lookback, with tests for production structure-gate agreement.

Run separately labelled studies:

1. **Option-backed reconstruction:** supply historical ATM IV reconstructed under
   the frozen pricing method in §5.1. Its coverage determines the main horizon.
2. **Optional proxy diagnostic:** distinct from the feasibility count in §4.0,
   which uses no volatility input and computes no outcomes. Use a fully specified
   trailing realized-volatility proxy. Fix window, annualization and timing before results. Do not describe
   this as broker IV, exact production replay or evidence sufficient to change rules.

The production ATM-IV input is chosen by nearest strike to the previous completed
SPY close among surviving chain quotes, not by the eventual selected spread. The
agent requests a 10–60 DTE chain, while spread selection uses 14–45 DTE. Preserve
the ATM-selection universe, quote freshness and tie behavior when testing parity;
a calls-only, 14–45 DTE reconstruction can change the confirmation itself.

### 4.2 Buckets and breadth-only attribution

The classifier returns either a setup or `None`, not a refusal reason. A research
adapter must retain the signal evidence and distinguish these outcomes:

| Bucket | Meaning |
|---|---|
| Unmeasurable | required input missing, stale, unaligned or reconstruction invalid; not a valid no-setup observation |
| Out of scope | bearish setup in the proposed bullish-only study |
| No setup | no qualifying structure or no qualifying independent confirmation |
| Permitted | qualified, and no opposite signal at 0.70 or above |
| Breadth-vetoed | baseline refuses, but the otherwise identical snapshot qualifies when only opposing breadth is excluded |
| Other/multiple vetoes | structure and confirmation qualify, but another opposing family still vetoes when opposing breadth is excluded |

Assign buckets in that order of prerequisites: input usability, study direction,
structure/confirmation, then veto attribution. Keep the underlying flags as well
as the final bucket so a missing confirmation is not misreported as a veto.

For the counterfactual, remove only the opposing participation signal from an
immutable snapshot copy and call the same classifier. Preserve all other signals,
confirmations and thresholds. Do not remove aligned breadth, invent confirmation,
or disable the global contradiction gate. Store all applicable refusal evidence;
the main comparison excludes other/multiple vetoes and reports them separately.
Obtain a breadth-vetoed setup's invalidation from its qualifying counterfactual.

Alternative breadth lines 0.60/0.70/0.80/off are exploratory only. Any research-only
adapter must preserve non-breadth vetoes at 0.70 and demonstrate baseline agreement
with the shipped classifier; do not change production constants globally.

### 4.3 Outcomes and reporting

**Measured for Permitted and Breadth-vetoed sessions:**

- SPY's move from the previous completed close `C[-1]` to the decision session's
  close `C[0]`, then `C[1]` and `C[2]`, in USD per share and percent. These are
  one-, two- and three-session diagnostics, not achievable entry-to-exit returns:
  they include the overnight move before entry and do not model executable exits.
- Whether SPY closed below the setup's invalidation level within those three
  sessions.
- The worst close within those three sessions.

**Reported:**

- Counts per bucket, per year, evidence mode and missing-data reason, and the
  longest run of breadth-vetoed sessions. Missing sessions interrupt an observed
  run rather than being silently bridged.
- The difference between Permitted and Breadth-vetoed outcomes, with a confidence
  interval from resampling. Consecutive sessions overlap and are not
  independent, so sessions are resampled in blocks.
- The same table at breadth lines 0.60, 0.70, 0.80 and "breadth veto off", shown
  side by side for context only; other vetoes remain unchanged.
- Explicitly censored observations near the dataset end: never treat an unavailable
  forward close as zero or compare groups using different unreported horizons.

**Limit.** SPY's move is not the spread's result. A call spread has capped
gains, and the stop and target fire during the day. Part 1 shows whether the
veto separates good days from bad ones. It cannot show profit.

**Output.** A thin `scripts/veto_backtest.py` entry point with a `signals`
subcommand, cached data outside git, a manifest and report in `docs/analysis/`.
Keep fetching, reconstruction and pure replay/report functions separate where
useful; do not introduce a generic backtesting framework or duplicate core rules.

## 5. Part 2 — Estimated historical spreads and portfolio outcomes

Work items `VBT-2xx`. Built only if Part 1 is worth following up (§8).

### 5.1 Entry

For each Permitted and Breadth-vetoed session in the verified option-data period:

1. Establish which contracts existed at the decision time, including expired
   contracts now inactive. Complete all pages and exclude contracts with no
   point-in-time existence evidence. Do not use current tradability as historical
   eligibility or later prices to fill an entry-time gap.
2. Freeze a decision clock and data-availability convention. The production entry
   window opens at 09:45 ET, but that does not mean the bot always enters then.
   A once-daily sample is a declared research simplification. A bar labelled
   09:45 is not a completed 09:45 observation if it spans 09:45–09:50. Never select
   legs using its close and assume a fill at its open. Prefer observations available
   by the decision instant and a subsequent eligible fill; otherwise explicitly
   move the decision after bar completion. Record observation, availability,
   decision and fill timestamps. See [Alpaca bar aggregation](https://docs.alpaca.markets/us/docs/market-data-faq#how-are-bars-aggregated).
3. Freeze the IV/delta reconstruction method before Part 1: pricing model and
   exercise-style approximation, synchronized underlying price, rates, dividends,
   time-to-expiry convention, solver bounds/tolerance and invalid-price handling.
   Preserve the distinction between contemporaneous spot for pricing and the
   prior close used by the live setup/ATM-selection rules. Do not assume the
   computed Greeks equal broker Greeks or differ by at most one strike.
4. Supply documented quote assumptions and run `DeterministicSpreadSelector`.
   The full implementation requires positive uncrossed bid/ask, relative quote
   spread at most 25%, DTE 14–45, long absolute delta 0.55–0.70, short 0.25–0.40,
   and width at least 0.005 × snapshot underlying price. It chooses the nearest
   tradeable expiry **before** searching pairs, then the narrowest eligible width,
   quoted debit/width ratio and strike. Do not silently fall through to later
   expiries if no pair qualifies at that expiry.
5. Preserve the distinction between quoted debit and execution allowance. The
   60%-of-width screen uses `long.ask − short.bid`. `crossing_debit` then adds
   half the sum of the two quote widths, rounded up to a cent, and requires the
   resulting debit to remain below width. Trade-price-as-bid-and-ask silently
   eliminates both liquidity screening and this allowance; it is not exact parity.
6. Record selected contracts, assumed quotes, quoted/estimated/filled debit,
   rejection reason and reconstruction provenance. Do not conflate a selector
   candidate with a risk-approved, executable trade. Use the deterministic
   baseline thesis for offline research and label the absence of historical LLM
   decisions; no paid model calls are required.

The synthetic quote model, observation-age/leg-synchronization limits and fill
rule remain **blocking protocol choices** in §9. Without defensible quote inputs,
report a model-based spread study, not what the live bot necessarily would have bought.

### 5.2 Exit

Call `evaluate_exit` rather than reimplementing it. Step through observations
available to the simulated worker and use the actual precedence:

| Rule | Value |
|---|---|
| 1. Expiry guard | 7 calendar days to expiry or fewer |
| 2. Invalidation | completed SPY daily close breaches the stored typed rule; source must match |
| 3. Stop loss | spread value at or below 50% of the actual simulated filled debit |
| 4. Session stop | at least 3 completed trading sessions since the fill |
| 5. Profit capture | value at least `entry_debit + 0.60 × (width − entry_debit)` |

Use `TradingCalendar.completed_sessions_between`: the entry day's close counts
if it occurs after the fill. The worker does not manage positions while the market
is closed. A third close or invalidation observed only after closing is actionable
on the next eligible market-open observation, not retroactively at that close.
Use actual holidays, early closes, DST and the chosen observation cadence.

Production marks a close at `long.bid − short.ask`; historical trade differences
are a proxy. Keep trigger time, suggested order limit and simulated fill distinct.
`evaluate_exit` suggests a limit of 90% of current value, floored at $0.01; that
is not an observed fill. If a premium is missing, premium-independent rules can
still trigger, but the simulation cannot invent a closing price. Record unresolved
or censored exits and their exposure instead of silently dropping the trade.

### 5.3 Costs

The following are proposed execution-friction sensitivities, not a calibrated
bid/ask model. Freeze their relationship to synthetic quotes and the production
allowance so costs are not double-counted. Let `P` be the explicitly defined
trade-derived spread reference price at the simulated fill observation:

| Case | Entry | Exit |
|---|---|---|
| Optimistic | P | P |
| Central | P + $0.05 | P − $0.05 |
| Pessimistic | P + $0.10 | P − $0.10 |

Amounts are per spread share, each way. For one standard 100-share contract,
the central round-trip haircut is $10 and the pessimistic haircut is $20 before
fees. State contract multiplier, quantity and any excluded fees explicitly.

**Simulate each scenario independently from entry onward.** Its filled debit
changes both stop and target; different costs can change exit time and later
portfolio availability. Specify separately how assumed executable marks trigger
exits and how fills are priced. Test impossible prices, missing fills and limit
violations; do not silently clip them into plausible profitable observations.

The reported first live trade gives one reference point: quoted cost 3.55, filled at
3.25, and marked at 3.09 a minute later on the bot's conservative basis.
A conclusion that holds only in the optimistic case is not a conclusion. Verify
the source fills and timestamps; one quote/fill/mark sequence cannot calibrate
historical liquidity or establish a reliable bound on slippage.

### 5.4 Known weaknesses, stated in the report

- Thinly traded contracts have stale bars. Fix numeric maximum observation age
  and inter-leg time difference before results; report rejections separately for
  Permitted and Breadth-vetoed groups to expose differential missing-data bias.
- The two legs' bars are not from the same instant.
- 5-minute bars can miss a stop or target touched inside a bar.
- Computed IV/delta can materially change confirmation, strikes or whether any
  spread qualifies. Measure discrepancies where original snapshots exist; leave
  the magnitude unknown elsewhere rather than promising a one-strike bound.
- Reconstructed quotes, fills and once-daily decisions are not a replay of every
  production tick. State which production gates are modeled and which are not.

### 5.5 Reported

- Per trade: entry, exit, reason, result in USD, for all three cost cases.
- Permitted against Breadth-vetoed: number of trades, win rate, average and median
  result, worst trade, and total, with a resampled confidence interval.
- Exclusion and unresolved-exit counts by group and year, plus measured input and
  contract-selection discrepancies. Clearly identify uncertainties that cannot be measured.

Produce **two distinct analyses**:

1. Independent hypothetical setup outcomes, allowing overlaps for studying the
   breadth association. Their sum is not an executable strategy equity curve.
2. Chronological portfolios with and without **only the breadth veto**, using the
   same initial capital, risk policy, timing and fill assumptions. Enforce one
   open or pending strategy, manage exits first, account for capital/buying power,
   and retain unavailable-capacity/rejected-entry records. Each cost scenario has
   its own path. Define re-entry timing and decision cadence before outcomes.

Only the second supports a portfolio cumulative-result comparison. It remains a
deterministic-baseline simulation unless all historical production gates are supplied.

## 6. Controls against fooling ourselves

1. **Freeze an executable protocol before new outcome analysis.** Commit this
   document, owner decisions and a run configuration first. Include dates,
   sampling time, input/quote/Greek assumptions, costs, exclusions, primary metrics
   and statistical settings. Historical observations already discussed are known,
   not a holdout. Later method changes need a dated explanation and review.
2. **No threshold search.** Alternative breadth lines are exploratory. Do not
   select the best result or let another veto move with the breadth threshold.
3. **No look-ahead.** Truncate input arrays explicitly; passing an `as_of` value
   to `build_signals` does not itself remove future bars. Test completed-bar
   timing, delayed observations, decision/fill ordering and end-of-sample censoring.
4. **Use two different parity gates.** With original input snapshots and matching
   code revision, deterministic outputs must match exactly. With reconstructed
   inputs, first quantify input, signal and contract differences against those
   snapshots using predeclared tolerances. Do not relax tolerances after viewing
   outcomes. A discrepancy blocks claims of exact replay, not publication of an
   honest failed-validation report. Reconcile §1.2 before making it an oracle.
   The exact-input fixtures are the exported live snapshots (§3); the reference
   interval is every recorded decision in them, not the ten rows of §1.2.
5. **Freeze statistical choices.** Proposed primary Part 1 metric: mean three-
   session percentage move, Permitted minus Breadth-vetoed. Proposed primary
   Part 2 setup metric: mean net USD result per one-contract spread, same contrast,
   central cost case. Report the portfolio contrast separately. Before outcomes,
   approve confidence level, bootstrap method, numeric block length, repetitions,
   seed, treatment of gaps and a practical non-inferiority margin in USD. Resample
   chronological blocks jointly with their group labels, not each group as if
   independent. Report regime/year breakdowns and predeclared block-length
   sensitivity. A simple block bootstrap of individual P&Ls is not automatically
   valid for a path-dependent portfolio; specify its uncertainty method separately.
6. **Counts do not establish power.** Fewer than about 30 usable observations per
   group is a screening reason to call results inconclusive. More than 30 is not
   proof of precision: overlapping outcomes and clustered regimes reduce effective
   information. Show intervals, exclusions and counts for every horizon/cost case.
   Failure to detect a difference is not evidence of equivalence.

## 7. Safety and cost

- Analysis runs on the Mac. Nothing is deployed. A host-side read-only export is
  an optional, separately approved acquisition step, not permission to change the worker.
- Uses read-only market data. The Mac has no broker credentials today, and
  none will be copied from the host (standing rule). §9, decision 4, covers how
  the data is fetched.
- No order path is touched or instantiated. Keep fetch and replay separate; the
  offline replay must work without credentials or network access. Use pure policy
  components, not an execution gateway or production agent with write capability.
- Run `check_no_write_path` on **both `src` and `scripts`**; its default scans only
  `src`. It is a named-identifier check, not proof that arbitrary HTTP writes are
  impossible. Add tests that replay makes no network calls and fetching permits
  only the required read endpoints.
- No LLM calls are needed. Do not claim zero total cost: data access, transfer,
  storage and request volume depend on the selected acquisition route. Do not
  extend host runtime or buy a subscription without approval.

## 8. Steps to solve it

Each step lists what is done, what it produces, and how it is checked. Work
stops at each marked stop point until the owner replies.

### Step 0 — Agree the method (this document)

- **Do:** resolve §9 and the blocking research choices; commit this document and
  frozen configuration before new outcome computation. Reconcile the existing
  reference claims without treating already observed data as a holdout.
- **Produces:** an approved protocol through the normal branch/PR path, ultimately
  on `main`; no automatic commit or merge is authorized by this plan.
- **Check:** each §10 finding is addressed or explicitly retained as a limitation;
  no undefined timing, quote, bucketing or statistical choice remains hidden.

### Step 0B — `VBT-100` Feasibility count

- **Do:** fetch SPY and RSP daily bars and the historical calendar, then run
  the count in §4.0. No option data, no volatility input, no outcomes.
- **Produces:** a one-page count report and the first entries of the data
  manifest. The daily-bar cache is reused by Step 1.
- **Check:** production lookback and adjustment settings; no look-ahead; the
  count for 22 September to 9 October 2026 agrees with the stored signals
  (structure passed on nine sessions, breadth at or above the line on eight).
- **Stop point: go/no-go.** If the upper bound fails the approved screen, the
  work ends here with a short report and the veto stays as it is. This step
  may run before the numeric protocol in decision 9 is frozen, because it
  measures no outcome.

### Step 1 — `VBT-101` Cache data and `VBT-101B` prepare volatility inputs

- **Do:** acquire SPY/RSP bars, the full historical calendar, warm-up and forward
  windows, original reference snapshots and sanitized probe evidence. Export
  the live decision snapshots and stored signals read-only (§3) and measure
  reconstructed IV, delta and quote width against them. Prepare
  historical ATM IV under §5.1 **before Step 2**, reusing that acquisition and
  reconstruction code in Part 2 rather than building it twice.
- **Produces:** immutable out-of-git caches, a committed manifest, IV provenance
  and a coverage/reconciliation report with the calibration errors against the
  live snapshots. Keep proxy and reconstructed inputs separate.
- **Check:** complete pagination, aligned unique sessions, calendar coverage,
  production feed/adjustment/lookback settings, no future inputs, and available
  reference-period data. Flag gaps; do not fill them silently. Reconcile January
  versus February option coverage and §1.2 strengths using raw observations.
- **Stop point:** the owner reviews coverage, exclusions, reference discrepancies
  and reconstruction feasibility. If IV cannot be supported, only an explicitly
  approved proxy diagnostic may continue, with no claim of faithful classification.

### Step 2 — `VBT-102` Replay the signals

- **Do:** pass production-window completed bars and the chosen IV input into real
  signal construction/classification. Apply §4.2 attribution on immutable copies.
- **Produces:** one row per decision session and evidence mode, with baseline and
  counterfactual results, all refusal evidence, exact/rounded strengths, gap,
  IV source and invalidation where a qualifying setup exists.
- **Check (must pass):** exact deterministic parity on reconciled original
  snapshots, including the reported October 5 refusal and October 9 qualification
  if verified. Test the complete reference interval rather than only selected
  rows; separately report reconstruction disagreements under §6.
- **Tests:** rounding/no-signal boundaries, independent confirmation, other/multiple
  vetoes, missing data, bearish scope, immutable inputs, 400-day warm-up/lookback,
  no look-ahead and baseline agreement with the production classifier.

### Step 3 — `VBT-103` Measure outcomes and write the Part 1 report

- **Do:** attach SPY's 1, 2 and 3-session moves, the invalidation breach and
  the worst close to each permitted and breadth-vetoed row. Compute the comparison and
  its confidence interval by block resampling.
- **Produces:** `docs/analysis/options_alpha_veto_backtest_part1_v0_1.md` with
  the tables in §4 and a plain-language reading of them.
- **Check:** hand-calculated indexing examples match §4.3; every figure shows its
  usable and excluded counts; proxy/reconstructed modes remain separate; seeded
  block resampling is reproducible and follows the frozen protocol. State
  inconclusive results without treating sample size alone as proof of power.
- **Stop point: the owner decides whether Part 2 is worth building.** A fair
  screening rule of thumb: Part 2 may be worth it with about 30 usable sessions
  on each side in the verified option-data period, subject to reconstruction
  quality and expected exclusions. If the veto shows no separation at all on
  SPY's move, Part 2 still matters, because the spread can behave differently.

### Step 4 — `VBT-201` Rebuild the option chain at each entry

- **Do:** extend Step 1's historical reconstruction to eligible spread legs and
  synthetic quote/fill inputs. Use the approved decision time, full selector
  behavior and baseline thesis; do not assume an uncompleted 09:45 bar is available.
- **Produces:** the chosen spread and debit per session, or the reason none
  qualified.
- **Check:** compare October 9 against the verified original decision snapshot,
  reported 775/781 October 23 calls and actual fill record. Separate quoted debit,
  allowance, limit and fill: “near 3.25 to 3.55” is not a numeric acceptance
  tolerance. Explain discrepancies against predeclared limits before proceeding.
- **Tests:** expired-contract discovery/pagination, point-in-time existence,
  quote quality, expiry-first selection, delta/width boundaries, allowance
  arithmetic, chain ordering and rejection of invalid model inputs.

### Step 5 — `VBT-202` Simulate the exits and costs

- **Do:** step each trade through 5-minute bars under the real exit rules
  (§5.2), in the three cost cases (§5.3).
- **Produces:** separate trajectories per cost case with trigger time, executable
  observation, fill time/value, reason, result and missing/unresolved status.
- **Check:** compare the first reported live trade's exit when its actual fill
  record becomes available. The original October 14 expectation is not a
  guaranteed fill deadline or evidence available at this review date.
- **Tests:** hand-worked rules and precedence collisions, cost-dependent threshold
  changes, entry-day session counting, holidays/early closes/DST, next-open
  handling of completed-close triggers, missing marks and no retroactive fills.

### Step 6 — `VBT-203` Write the Part 2 report

- **Do:** build the capacity-constrained portfolios and compare them separately
  from independent setup outcomes (§5.5). Quantify §5.4 weaknesses where measurable;
  identify unknowns rather than inventing bounds.
- **Produces:** `docs/analysis/options_alpha_veto_backtest_part2_v0_1.md`.
- **Check:** no overlapping open/pending strategies in portfolio mode; identical
  initial capital/policy assumptions across arms; deterministic re-entry and
  fill rules; missing exits cannot free capacity silently; each cost case has its
  own path. Show group-specific exclusions and the approved uncertainty analysis.
- **Stop point:** the owner reviews it. No result changes production automatically.

### Step 7 — Decide (the owner)

The report supports one of three outcomes. None is taken automatically.

| Finding | Reasonable decision |
|---|---|
| Breadth-vetoed trades are materially worse under the prespecified comparison and central costs | Keep the veto as it is; attach evidence and limitations to DEC-008, without claiming proof of an edge |
| No measurable difference, or too few trades to tell | Keep the veto unchanged and keep collecting Paper evidence |
| Breadth-vetoed trades meet the predeclared non-inferiority criterion in all three cost cases, with acceptable reconstruction quality and portfolio results reviewed | Consider a separate proposal with its own review and Paper testing; this study alone does not authorize a change |

**Decision, 23 October 2026.** The owner kept the veto as it is ("The veto
keep as it is"), after the [Part 2 report](../analysis/options_alpha_veto_backtest_part2_v0_1.md).
The single-trade "no worse" test passed narrowly, but both portfolios lost and
removing the veto lost more. No rule changes; this study is closed.

“No worse” requires an approved practical margin and interval-based criterion,
not a non-significant difference. Preserve the veto if evidence is inconclusive.

### Effort

The original one-session/three-session estimates are withdrawn pending coverage
and reconstruction checks. Part 1 now explicitly includes option-backed IV work;
Part 2 includes portfolio state and executable timing. Re-estimate after Step 1.
The feasibility count (Step 0B) is small: daily bars and counting only.
Keep implementation small and modular, with normal branch, full CI and PR review.

## 9. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| 1 | Retain Part 1 first, with IV acquisition/reconstruction moved ahead of classification? | Yes; the Part 2 stop point remains, but Part 1 cannot be daily-bars-only if it claims faithful setup qualification |
| 2 | Include a longer realized-volatility proxy diagnostic? | Optional and separately labelled; use option-backed reconstructed IV for the main study, never call either reconstructed or proxy IV an observed broker measure |
| 3 | Retain $0.00 / $0.05 / $0.10 execution-friction cases? | Yes as uncalibrated sensitivities, conditional on an explicit quote/allowance/fill model and independent simulation of each case |
| 4 | Where does the data fetch run? (a) On the server, with the bot's existing read-only connection, saving a data file that is then copied to the Mac. (b) On the Mac, with a separate read-only data key the owner creates. | (a): no new credential |
| 5 | Separately record failed RSP provider reads? | Yes, in a separate change. `agent.observe` swallows `ProviderError` and passes no participation read; malformed supplied bars can already produce a provider-error record in `build_snapshot`. Whether failure should block entry is a separate rule decision |
| 6 | Limit the initial study to bullish SPY setups and a breadth-only counterfactual? | Yes; count bearish and other/multiple-veto observations separately and preserve all non-breadth vetoes |
| 7 | Accept a trade-derived, model-based spread study if quote history is unavailable, or obtain historical quotes first? | Accept only explicitly model-based conclusions with reviewed assumptions; exact quote/selector parity requires suitable historical quotes |
| 8 | Use a fixed daily decision time or simulate every production entry opportunity? | Start with a declared fixed-time study; do not call it a complete worker replay. Approve the time, availability lag, fill rule and portfolio re-entry schedule |
| 9 | Approve the detailed reconstruction and inference configuration before outcomes? | Required: pricing/IV model, numeric age/synchronization limits, synthetic quote rule, fees, bootstrap settings, primary metrics and practical non-inferiority margin must all be specified and reviewed |
| 10 | Run the feasibility count (§4.0, Step 0B) first, and stop if it fails the screen of about 30 sessions and 10 distinct clusters per group? | Yes. It is cheap, computes no outcomes, and avoids building the reconstruction for a sample that cannot decide the question. It may run before decision 9 is settled |
| 11 | Export the live decision snapshots and stored signals read-only as the calibration and exact-parity set? | Yes, under the same approval as decision 4(a): one reviewed read-only export, no deployment, no credentials copied |

**Owner's answer, 12 October 2026: "approved as recommended, including the
export".** This approves the recommendation column for decisions 1 to 8, 10
and 11, and the read-only export of daily bars and stored signals, which ran
that day (`scripts/veto_export.py`; result in the
[feasibility count](../analysis/options_alpha_veto_feasibility_count_v0_1.md)).
Three things it does not cover:

- **Decision 9** stayed open at that point. The values were then proposed in
  the [numeric protocol](options_alpha_veto_backtest_protocol_v0_1.md), and
  the owner approved them as proposed later the same day ("Agree"; recorded
  in that document's §10).
- **Decision 11's export of full decision snapshots** has not run. The stored
  signals were enough for the feasibility check; the snapshots are needed for
  Step 1 and are a larger transfer, to be run with the same read-only limits.
- **Decision 5** approves recording a failed RSP read as a separate change to
  the live bot. It changes no entry rule. **Built 15 October 2026:** a failed
  read is kept in the snapshot's `data_quality.advisories` as
  `rsp:read_failed:<error class>[:status_<code>]`, without the request URL or
  the provider's reply. Advisories never make a snapshot unusable and never
  become reason codes. One related behaviour is unchanged and needs a rule
  decision of its own: RSP bars that *arrive but cannot be parsed* are already
  a provider error (`rsp:bars_unreadable`), and a provider error blocks the
  decision, which contradicts the code comment that breadth "must never be
  able to fail a decision".
  **Decided 24 October 2026 by the owner:** malformed RSP bars are now an
  advisory (`rsp:bars_unreadable`) like a failed read, and block nothing. A
  bar whose time does not parse is included; it used to raise out of the
  observation altogether.

**Owner's answer, 13 October 2026: "Approved".** It approves the historical
option download as it was put to the owner that day: the same host through
Cloud Assistant; GET requests only (the option contract record, 5-minute option
trade bars and SPY 5-minute bars); prices from 09:45 to 10:05 New York for
contracts expiring 10 to 60 days out, for the sessions from 1 February 2024;
calls and puts struck within 1% of the previous close, and calls from 0.94 to
1.07 of it for the sessions that have a stored snapshot; requests 0.5 seconds
apart; the result returned in the command output and kept on the Mac outside
git; nothing written on the host, nothing restarted, no credential leaving it,
no new subscription and no added host hours. The tool is
`scripts/veto_export.py options` and `spot`. Exit-path prices for Part 2 are
not covered and need a later request.

**Owner's answer, 23 October 2026: "Proceed".** It was given to the Part 2
download as it was put to the owner that day. That request named two stages:

- **Stage A, entry chains:** 5-minute call trade bars from 09:45 to 10:05 New
  York, struck 0.94 to 1.07 of the previous close, expiring 10 to 60 days out,
  for the Permitted and Breadth-vetoed sessions of the Step 2 replay. About
  8,700 requests. The tool is `scripts/veto_export.py chains`. The data goes to
  its own folder, so the Step 1 to 3 inputs keep their digests.
- **Stage B, exit paths:** after Step 4 has chosen each spread, the two legs'
  5-minute bars from the entry to the exit, up to about four sessions. About
  1,000 to 2,000 requests.

Both use the same host and GET requests as on 13 October, spaced 0.5 seconds
apart, with nothing written on the host and no credential leaving it. Unlike
13 October, they **add host hours**: they run after 16:15 New York with no
position open, keeping the server up with `scripts/session.py` for about five
hours in all (roughly $0.15).

Decision 4(a) authorizes neither a deployment nor copying credentials. The owner
must separately approve the export's target, read-only commands and transfer;
the analysis remains local. No owner approvals are inferred from this document edit.

## 10. Code-review findings and verification record

Reviewed on 12 October 2026 against `70e1493`. This section records source-based
findings, not completed backtest work. Relative links refer to this repository;
the revision identifies the code audited even if files later change.

| ID / priority | Finding and source | Required response / location |
|---|---|---|
| R1 / High | Breadth caps at 1.00 and rounds before comparison; the 0.95 reference values cannot match current code. [`evidence.py`](../../src/options_alpha_lab/evidence.py), `_clamp`, `participation_signal` | Preserve reported history, reconcile raw inputs/revision; boundary tests. §1, Steps 1–2 |
| R2 / High | Historical sensitivity supplies no IV and does not classify; production confirmation/veto applies across families. [`sensitivity.py`](../../src/options_alpha_lab/sensitivity.py), `signals_over_history`; [`components.py`](../../src/options_alpha_lab/components.py), `DeterministicSetupClassifier` | IV before classification, separate proxy study, breadth-only counterfactual and explicit missing/multiple-veto states. §4 |
| R3 / High | Trade bars cannot reproduce bid/ask liquidity screens, expiry-first selection and execution allowance. [`components.py`](../../src/options_alpha_lab/components.py), `DeterministicSpreadSelector`, `crossing_debit`; [`evidence.py`](../../src/options_alpha_lab/evidence.py), `build_option_chain` | Specify point-in-time chain, Greek/quote reconstruction and modeled-versus-observed fields. §5.1 |
| R4 / High | A 09:45 bar may contain later information; a fixed sample is not every production entry opportunity. [`calendar.py`](../../src/options_alpha_lab/calendar.py), `Session.entry_window`; provider aggregation documentation linked in §5.1 | Separate data availability, decision and fill times; no same-bar look-ahead. §5.1, Steps 2/4 |
| R5 / High | Original exit table had wrong precedence and an unspecified target; session counting and actual execution timing matter. [`exits.py`](../../src/options_alpha_lab/exits.py), `evaluate_exit`; [`agent.py`](../../src/options_alpha_lab/agent.py), `sessions_since`, `_exit_inputs`, `spread_value`; [`calendar.py`](../../src/options_alpha_lab/calendar.py), `completed_sessions_between` | Reuse policy, cost-specific thresholds, completed-session timing, missing-price behavior and separate fills. §5.2–5.3 |
| R6 / High | Independent daily trades violate one-open/pending-strategy capacity when interpreted as a portfolio. [`gateway.py`](../../src/options_alpha_lab/execution/gateway.py), `ExecutionGateway` | Separate setup outcomes and chronological portfolios with risk/capital/timing assumptions. §5.5, Step 6 |
| R7 / Medium | Production uses a bounded 400-day, split-adjusted stock history; historical-chain fetching is not implemented by current adapters. [`alpaca_readonly.py`](../../src/options_alpha_lab/providers/alpaca_readonly.py); [`gate_study.py`](../../src/options_alpha_lab/gate_study.py), `windows` | Freeze feed/adjustment/window and implement dedicated read-only historical acquisition. §3–4, Step 1 |
| R8 / Medium | Local bar fixtures end in August; committed calendar does not cover 2020–2025; reported option start differs from public documentation. [`sensitivity_bars.json`](../../fixtures/h0/sensitivity_bars.json); [`nyse_sessions.json`](../../src/options_alpha_lab/data/nyse_sessions.json) | Obtain full calendar, original reference inputs and sanitized coverage probe evidence. §3, Step 1 |
| R9 / Medium | Thirty observations, unspecified bootstrap settings and “no worse” are insufficient decision criteria. Original plan §6/§8 | Freeze statistical protocol/margin, report exclusions and effective dependence, separate portfolio inference. §6, Step 7 |
| R10 / Medium | RSP provider errors can vanish, and the default write-path scanner excludes scripts. [`agent.py`](../../src/options_alpha_lab/agent.py), `observe`; [`check_no_write_path.py`](../../scripts/check_no_write_path.py), `main` | Keep live error-reporting fix separate; scan both trees and test no-network replay. §7/§9 |

### 10.1 Checks completed during review

The following local, targeted command passed with **167 tests and 814 subtests**:

```sh
env RUN_LIVE_API_TESTS=0 .venv/bin/python -m pytest -o addopts='' -q \
  tests/test_evidence.py tests/test_sensitivity.py tests/test_exits.py \
  tests/test_calendar.py tests/test_gate_study.py tests/test_architecture.py \
  tests/test_execution_pricing.py tests/test_execution_firewall.py \
  tests/test_structure_reading.py
```

Both scanner invocations passed:

```sh
.venv/bin/python scripts/check_no_write_path.py
.venv/bin/python scripts/check_no_write_path.py scripts
```

Direct checks of the shipped strength function confirmed 1.00 for the six large
negative gaps in §1.2 and 0.70 for a −0.78% gap. Calendar checks confirmed the
entry-day close contributes to elapsed completed sessions. These are checks of
existing components, **not validation of an implemented backtest**. Full CI was
not run as part of that review; no production or broker data was requested and
no live rules were changed.

### 10.2 Review acceptance checklist

- [x] Feasibility count run and its go/no-go recorded (§4.0): go, 12 October 2026.

- [ ] Owner decisions in §9 recorded; unresolved numeric protocol choices frozen.
- [ ] Reference evidence and deployed-policy discrepancies reconciled.
- [ ] Data feeds, coverage, historical calendar and reconstruction provenance accepted.
- [ ] Proxy, reconstructed-input replay and exact-input parity claims distinguished.
- [ ] Breadth-only attribution and bullish-only scope accepted.
- [ ] Observation/decision/fill timing and quote/Greek assumptions accepted.
- [ ] Exit rules, cost-dependent simulation and capacity constraints accepted.
- [ ] Statistical settings and decision margin approved before new outcome analysis.
- [ ] Read-only acquisition authority and offline execution boundary confirmed.
- [ ] Implementation and effort re-estimated after coverage/feasibility review.

### 10.3 Author's adjustments after the review

Made on 12 October 2026. The review's findings R1 to R10 are accepted. Seven
claims were checked against the code and the live records and found correct:
the 1.00 cap and the 0.78% boundary (R1), the missing volatility input and
classification in the sensitivity code (R2), the exit precedence and profit
target formula (R5), the scanner's default scope (R10) and the bearish
support in the classifier. R3, R4 and R6 to R8 were not checked line by line.
The review's test command was not re-run.

| Adjustment | Where |
|---|---|
| R1 reconciled: the 0.95 values were the author's transcription error; stored signals agree with the shipped code | §1.2 |
| Feasibility count added ahead of all reconstruction, with a go/no-go stop | §4.0, Step 0B, decision 10 |
| Live decision snapshots named as the calibration and exact-parity set | §3, §6.4, Step 1, decision 11 |
| Provenance of the author's 12 October read-only checks recorded, and marked as not retained evidence | §3 |

Decision 9 was open when this section was written. It is now closed: the
feasibility count passed, and the pricing model, age and synchronization
limits, synthetic quote rule, bootstrap settings and non-inferiority margin
are frozen in the [numeric protocol](options_alpha_veto_backtest_protocol_v0_1.md).
