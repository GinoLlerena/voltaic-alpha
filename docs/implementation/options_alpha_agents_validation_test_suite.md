# Options Alpha Agents — Trading Bot Validation Test Suite

**Version:** 0.2  
**Purpose:** Dev-agent specification for deterministic paper-trading validation  
**Target system:** Options Alpha Agents / Alpaca Paper Trading MVP  
**Status:** Product validation catalog with a two-case hackathon H0 cut

---

## 1. Objective

This document defines a test suite for validating the **decision quality, orchestration, risk discipline, explainability, and options-structure selection** of the Options Alpha Agents trading bot.

The goal is **not** to prove profitability from a small set of favorable examples. The goal is to expose incorrect reasoning and unsafe behavior before optimizing the strategy.

The priority order is:

1. **Decision quality**
2. **Risk management**
3. **Consistency**
4. **Explainability and traceability**
5. **Execution correctness**
6. **Profitability**

A losing trade can still be a valid PASS if the process was correct and the loss remained inside the pre-declared risk. A profitable trade can be a FAIL if it violated the strategy, used unavailable/future information, ignored a risk veto, or took an unjustified position.

---

## 2. Scope and Existing MVP Assumptions

This suite is the broader product validation catalog. The seven-day hackathon H0 cut uses only `CORE-01` plus `CORE-08`; the remaining cases do not expand the implementation scope.

### 2.1 In-scope directional setups

Hackathon H0 recognizes one mirrored tactical family:

1. **Trend continuation / retest**

**Confirmed breakout / breakdown** remains a post-H0 product case.

Market regime, macro information, sentiment, volatility, breadth, and events are used primarily as **context, confirmation, contradiction, or risk filters**. They are not standalone triggers for the MVP.

### 2.2 In-scope option structures

For the initial MVP, the preferred directional structures are defined-risk debit spreads:

- **Bull call debit spread** for bullish directional theses.
- **Bear put debit spread** for bearish directional theses.

Other structures such as naked calls/puts, credit spreads, iron condors, straddles, strangles, calendars, ratio spreads, and volatility-arbitrage structures are **out of scope for the first implementation** unless explicitly introduced in a later strategy version.

The bot must not silently substitute an unsupported options strategy because it appears more profitable in a specific test.

### 2.3 Architectural principles under test

The suite assumes a flow conceptually equivalent to:

> Market Intelligence → Directional Conviction → Options Strategist → Risk Governor → Alpaca Execution → Position Monitor

Agent names can change. The responsibilities must remain testable.

Core rules:

- The LLM may interpret and propose.
- Deterministic validation must enforce hard constraints before execution.
- `NO_TRADE` is a first-class successful outcome.
- Directional conviction and options quality are separate judgments.
- Supporting evidence and counter-evidence must both be represented.
- Evidence should come from independent families; correlated indicators must not be counted as independent confirmations.
- Every trade requires explicit invalidation conditions.
- The Risk Governor can veto a trade even when directional conviction is high.
- The system must never fabricate unavailable market data.
- Every H0 model case must also run through a deterministic no-LLM baseline; fluent prose alone is not evidence that the model adds value.

---

## 3. Public Strategy Inspiration — Attribution Boundary

The named traders below are used as **public-methodology inspiration**, not as personas and not as a claim that the system reproduces proprietary trading systems.

### 3.1 José Luis Cava-inspired evidence families

Public analyses by José Luis Cava repeatedly use concepts such as:

- trend and momentum;
- support and resistance;
- trend-line loss as evidence of momentum deterioration;
- major moving averages such as the 200-session average;
- relative strength among broad indices;
- market breadth and comparison of cap-weighted versus equal-weighted indices;
- volatility measures such as VIX;
- investor sentiment;
- monetary/liquidity conditions;
- preference for operating with market strength rather than fighting it.

For this suite, a **Cava-inspired** case means that the test combines those publicly discussed evidence families. It does **not** imply a proprietary Cava formula or an exact reproduction of his trading system.

### 3.2 Gustavo Martínez-inspired evidence families

Public appearances by Gustavo Martínez emphasize a more macro/portfolio-oriented framework, including:

- macroeconomic conditions;
- inflation and monetary policy;
- debt and currency purchasing-power risk;
- valuation and whether an investment thesis is supported by economic fundamentals;
- diversification;
- safe-haven assets such as gold;
- sector opportunity;
- concentration risk in broad equity indices;
- adjusting portfolio exposure to the investor's objectives and risk.

For this MVP, that information is intentionally treated as **regime/context evidence**. A macro thesis alone does not authorize a short-term options trade. The tactical chart structure must still satisfy the Options Alpha Agents setup rules.

### 3.3 Professional/quantitative-inspired evidence families

Additional cases use broadly accepted professional concepts:

- regime classification;
- trend persistence;
- relative strength;
- market breadth;
- realized versus implied volatility;
- option liquidity and bid/ask quality;
- Greeks;
- expected move;
- event risk;
- independent confirmation;
- position sizing by predefined maximum loss;
- explicit data-quality gates;
- avoiding hindsight and look-ahead bias.

---

## 4. Test Methodology

### 4.1 Deterministic replay first

The initial suite should run from frozen fixtures. Every fixture must contain a timestamp and only information available at or before that timestamp.

Do not query current market data when executing deterministic unit/evaluation cases.

Historical replay can be added after the decision contract is stable.

### 4.2 No look-ahead

The decision engine receives a `decision_snapshot`.

The eventual outcome belongs in a separate `post_decision_outcome` object that is hidden until after the decision has been finalized.

An intraday fixture may expose only finalized bars. Its manifest must record the provider/feed, `America/New_York` session calendar, adjustment mode, timeframe, source and receipt timestamps, bar-finalization delay, and completeness status. Missing, late, corrected, forming, or incomplete-page data fails closed. Rolling statistics exclude the current signal bar unless the versioned formula explicitly declares and tests another convention.

A signal calculated after finalized bar `t` may fill no earlier than the first eligible observable quote or bar in `t+1`. Same-bar fills are forbidden. Replay evidence must retain the quote or bar used and its spread, slippage, latency, and missed-fill assumptions.

Forbidden examples:

- using the day's closing candle when the decision occurs at 11:00 ET;
- computing a signal from a still-forming bar or filling it within the same bar;
- using next-session volume;
- using revised macro data that was not available at the timestamp;
- selecting a strike because it later became the best-performing contract;
- using post-earnings IV to justify a pre-earnings position.

### 4.3 Test-only thresholds vs. trading truth

Some fixtures need deterministic thresholds. These thresholds are **test-harness defaults**, not universal claims about how professional traders must operate.

Suggested defaults for the initial suite:

| Control | Test-harness default |
|---|---:|
| Independent evidence families required | >= 2 |
| Option-leg relative bid/ask spread | Prefer <= 8% of midpoint |
| Minimum open interest per selected leg | >= 500 |
| Minimum recent option volume per selected leg | >= 50 |
| Preferred MVP DTE band | 21–45 DTE |
| Typical long-leg delta band | 0.55–0.70 |
| Typical short-leg delta band | 0.25–0.40 |
| Tier-1 scheduled-event blackout | 60 min before event unless event strategy explicitly exists |
| New directional trade immediately after Tier-1 event | Require stabilization/confirmation fixture |
| Maximum loss | Must be <= scenario risk budget |

The implementation should make these values configurable rather than embedding them in the LLM prompt.

### 4.4 Confidence is not a trade trigger

Confidence is explanatory metadata, not permission to bypass deterministic gates.

A `90` confidence thesis with an illiquid spread is still rejected.

Tests should normally validate confidence as an acceptable **range**, not an exact integer.

---

## 5. Canonical Decision Contract

A recommended normalized object for test assertions:

```json
{
  "case_id": "CORE-01",
  "as_of": "fixture timestamp",
  "underlying": "SPY",
  "market_regime": "bull_trend_normal_volatility",
  "setup_family": "trend_continuation_retest",
  "directional_bias": "bullish",
  "directional_conviction": 78,
  "options_quality": 82,
  "signals": [],
  "counter_evidence": [],
  "independent_evidence_families": [],
  "event_risk": {
    "level": "low",
    "next_tier1_event_minutes": null
  },
  "data_quality": {
    "status": "pass",
    "missing_fields": [],
    "stale_fields": []
  },
  "decision": "OPTIONS_POSITION",
  "strategy": "bull_call_debit_spread",
  "risk": {
    "max_loss_within_budget": true,
    "liquidity_gate": "pass",
    "event_gate": "pass",
    "portfolio_gate": "pass"
  },
  "invalidation": [],
  "confidence": 78,
  "reasoning_summary": "",
  "risk_governor": {
    "result": "approve",
    "reasons": []
  }
}
```

### 5.1 Allowed high-level decisions for this suite

- `OPTIONS_POSITION`
- `NO_TRADE`
- `HOLD`
- `REDUCE_EXPOSURE`
- `EXIT`

Directional semantics should be stored separately as `bullish`, `bearish`, or `neutral` rather than overloading the decision field.

---

## 6. Required Evidence Families

The bot should classify evidence into families so that correlated indicators do not inflate confidence.

Recommended families:

1. **Structure** — trend, support/resistance, breakout/retest, swing structure.
2. **Momentum** — RSI/MACD/rate of change; multiple momentum indicators count as one family.
3. **Participation** — volume, breadth, equal-weight participation, advance/decline.
4. **Relative strength** — underlying vs. benchmark, sector vs. market, QQQ vs. SPY, etc.
5. **Volatility/options** — IV, realized vol, skew, term structure, expected move, Greeks.
6. **Macro/liquidity** — yields, dollar, monetary policy, liquidity regime, inflation context.
7. **Event** — earnings, CPI, FOMC, employment, material news.
8. **Sentiment/positioning** — fear/greed, put/call, positioning, flows where available.
9. **Execution quality** — spread width, open interest, volume, quote freshness.
10. **Portfolio risk** — correlation, concentration, existing directional exposure.

---

## 7. Summary Matrix

The suite contains **28 cases**. Exactly **8 of 28 (28.6%)** have `NO_TRADE` as the expected result.

Only two cases are hackathon H0:

- `CORE-01`: one qualified SPY trend/retest case;
- `CORE-08`: one valid directional thesis refused because the option chain is not eligible.

All other rows are post-H0 regression or research cases. Legacy `MVP` labels have been replaced with `Post-H0` so they cannot be mistaken for seven-day deliverables.

| ID | Level | Theme | Expected decision | Direction / structure |
|---|---|---|---|---|
| CORE-01 | H0 | Bull trend retest | OPTIONS_POSITION | Bull call debit spread |
| CORE-02 | Post-H0 | Confirmed upside breakout | OPTIONS_POSITION | Bull call debit spread |
| CORE-03 | Post-H0 | Confirmed downside breakdown | OPTIONS_POSITION | Bear put debit spread |
| CORE-04 | Post-H0 | False breakout / weak participation | **NO_TRADE** | None |
| CORE-05 | Post-H0 | Low-IV continuation | OPTIONS_POSITION | Bull call debit spread |
| CORE-06 | Post-H0 | Bear trend resistance retest | OPTIONS_POSITION | Bear put debit spread |
| CORE-07 | Post-H0 | High-IV but acceptable defined-risk structure | OPTIONS_POSITION | Bull call debit spread |
| CORE-08 | H0 | Direction right, option chain illiquid | **NO_TRADE** | None |
| CORE-09 | Post-H0 | Strong index, deteriorating breadth | **NO_TRADE** | None |
| CORE-10 | Post-H0 | Breakout + volume + breadth | OPTIONS_POSITION | Bull call debit spread |
| CORE-11 | Post-H0 | Breakdown + relative weakness | OPTIONS_POSITION | Bear put debit spread |
| CORE-12 | Post-H0 | Open trade invalidated | EXIT | Close spread |
| CAVA-01 | Strategy | Relative strength + breadth confirmation | OPTIONS_POSITION | Bull call debit spread |
| CAVA-02 | Strategy | Price below major resistance / 200MA test | **NO_TRADE** | None |
| CAVA-03 | Strategy | Fear + support + technical confirmation | OPTIONS_POSITION | Bull call debit spread |
| CAVA-04 | Strategy | Trend-line/support loss | OPTIONS_POSITION | Bear put debit spread |
| GM-01 | Strategy | Gold macro thesis + tactical confirmation | OPTIONS_POSITION | GLD bull call debit spread |
| GM-02 | Strategy | Sector opportunity + tactical retest | OPTIONS_POSITION | XLF bull call debit spread |
| GM-03 | Strategy | Strong macro story, no tactical setup | **NO_TRADE** | None |
| PRO-01 | Strategy | Multi-family trend confirmation | OPTIONS_POSITION | Bull call debit spread |
| STRESS-01 | Adversarial | Valid setup immediately before CPI | **NO_TRADE** | Event veto |
| STRESS-02 | Adversarial | Post-event confirmed repricing | OPTIONS_POSITION | Bull call debit spread |
| STRESS-03 | Adversarial | Stale underlying/option quote | **NO_TRADE** | Data veto |
| STRESS-04 | Adversarial | Missing Greeks/IV required by selector | **NO_TRADE** | Data/options veto |
| STRESS-05 | Adversarial | Liquidity deteriorates while position open | REDUCE_EXPOSURE | Reduce/close spread |
| STRESS-06 | Adversarial | Regime flip while position open | EXIT | Close spread |
| STRESS-07 | Adversarial | Duplicate correlated momentum signals | OPTIONS_POSITION | Bull spread, lower confidence |
| STRESS-08 | Adversarial | Execution anomaly / incomplete state | EXIT | Flatten unsafe residual risk |

---

# LEVEL 1 — CORE PRODUCT VALIDATION

Only `CORE-01` and `CORE-08` are H0. Other `CORE-*` cases remain post-H0 acceptance specifications.

## CORE-01 — Bull Trend Pullback / Retest

### Fundamentals

Validate the most important MVP behavior: enter a continuation trade only after a pullback holds a previously important area and buyers reassert control.

### Fixture snapshot

- Underlying: `SPY`
- Regime: established bullish trend, normal volatility.
- Daily structure: higher highs and higher lows; price above rising 50- and 200-session averages.
- Intraday/daily retest: price pulls back toward a prior breakout zone and holds it.
- Volume: contraction during the pullback; expansion on the recovery candle.
- Breadth: neutral-to-positive, not materially deteriorating.
- Relative strength: SPY stable versus equal-weight benchmark.
- Event calendar: no Tier-1 event inside the blackout window.
- Options: liquid 21–45 DTE chain, acceptable spreads, defined-risk debit spread fits budget.

### Signals and interpretation

Supporting:

- Structure: bullish trend intact.
- Structure: former resistance behaves as support.
- Participation: recovery occurs with stronger volume than pullback.
- Options quality: liquid chain and acceptable debit.

Counter-evidence:

- Momentum is not at a fresh high; this is a continuation entry, not a momentum chase.

The bot should understand that the **retest** is the entry condition. “Market is bullish” alone is insufficient.

### Hypothesis

If former resistance continues to hold as support and participation returns, the prior bullish trend has a reasonable probability of continuation.

### Invalidation

- Close back below the retest zone with meaningful participation.
- Breakdown of the most recent higher low.
- Risk event appears before execution.

### Expected decision

- Decision: `OPTIONS_POSITION`
- Bias: bullish
- Structure: `bull_call_debit_spread`
- Confidence: expected range `72–84`
- Risk Governor: approve

### Expected orchestration

1. Market Intelligence identifies bull regime and retest.
2. Conviction engine separates trend structure from momentum evidence.
3. Options Strategist finds a liquid debit spread.
4. Risk Governor validates max loss, event window, liquidity, portfolio exposure.
5. Execution submits only after approval.

### Key assertion

```json
{
  "case_id": "CORE-01",
  "setup_family": "trend_continuation_retest",
  "directional_bias": "bullish",
  "decision": "OPTIONS_POSITION",
  "strategy": "bull_call_debit_spread",
  "risk_governor": {"result": "approve"}
}
```

### PASS / FAIL

PASS if the bot explicitly cites the retest, identifies invalidation, and preserves defined risk.  
FAIL if it enters merely because price is above a moving average.

---

## CORE-02 — Confirmed Upside Breakout

### Fundamentals

Validate the second MVP setup family: a breakout must be confirmed rather than predicted.

### Fixture snapshot

- Underlying: `QQQ`
- Price has tested a clearly defined resistance area three times.
- Current session closes above resistance.
- Breakout volume is materially above the recent median.
- QQQ relative strength versus SPY is improving.
- Breadth within large-cap growth/technology is positive rather than one-stock-driven.
- VIX is stable or declining; no sudden volatility shock.
- Options chain is liquid and 30 DTE spread cost is reasonable relative to width.

### Signals and interpretation

Independent families:

1. Structure: confirmed close above resistance.
2. Participation: volume confirmation.
3. Relative strength: QQQ outperforming SPY.

Do not count RSI + MACD + ROC as three independent confirmations.

### Hypothesis

Acceptance above the former ceiling with broad participation should convert resistance into support and allow continuation.

### Invalidation

- Fast close back below the breakout zone.
- Failed retest accompanied by rising selling volume.

### Expected decision

`OPTIONS_POSITION` → bullish → bull call debit spread.  
Confidence range: `76–88`.

### PASS / FAIL

PASS if the model distinguishes a **confirmed breakout** from an intraday touch.  
FAIL if it uses an intraday high above resistance while the fixture says the close is still below it.

---

## CORE-03 — Confirmed Downside Breakdown

### Fundamentals

Mirror the breakout logic on the downside. Bearish decisions must not receive weaker standards simply because fear is elevated.

### Fixture snapshot

- Underlying: `IWM`
- Existing sequence of lower highs.
- Major support breaks on closing basis.
- Downside volume expands.
- IWM relative strength versus SPY is deteriorating.
- Breadth among small caps is negative.
- No major scheduled event immediately ahead.
- Put chain supports a liquid bear put debit spread.

### Interpretation

The thesis is supported by structure + participation + relative weakness. Elevated fear is contextual, not the primary trigger.

### Hypothesis

Loss of support in an already weak relative-strength regime increases probability of continuation lower.

### Invalidation

- Reclaim and hold above broken support.
- Bear trap accompanied by strong breadth recovery.

### Expected decision

`OPTIONS_POSITION` → bearish → `bear_put_debit_spread`; confidence `74–86`.

### PASS / FAIL

FAIL if the bot shorts solely because VIX is high or headlines are negative.

---

## CORE-04 — False Breakout with Weak Participation

### Fundamentals

Test whether the bot can reject a visually attractive but low-quality breakout.

### Fixture snapshot

- Underlying: `SPY`
- Price trades 0.3% above resistance intraday but closes only marginally above it.
- Volume is below the 20-session median.
- Equal-weight S&P proxy is flat/down.
- Advance/decline participation is weak.
- Momentum indicators are positive because they derive from the same price move.
- Options are liquid.

### Interpretation

The setup has apparent structure but lacks independent participation confirmation. RSI/MACD positivity must not compensate for weak breadth/volume.

### Expected decision

`NO_TRADE`; confidence in no-trade decision `75–90`.

### Invalidation of no-trade stance

A later fixture may become tradable if price holds above resistance and participation improves.

### Key assertion

```json
{
  "case_id": "CORE-04",
  "decision": "NO_TRADE",
  "counter_evidence": ["weak_volume", "weak_breadth"],
  "risk_governor": {"result": "reject"}
}
```

### FAIL conditions

- Enters because three correlated momentum indicators are bullish.
- Calls this a confirmed breakout without breadth/participation qualification.

---

## CORE-05 — Continuation with Relatively Low Implied Volatility

### Fundamentals

Validate separation between the directional thesis and option pricing quality.

### Snapshot

- Underlying: `AAPL`
- Clear bullish trend and successful retest.
- No earnings inside the trade's intended holding window.
- IV percentile is relatively low/moderate.
- Bid/ask quality is strong.
- Debit spread offers reasonable convex exposure without excessive premium.

### Interpretation

Low/moderate IV does not create the trade. It improves the **implementation quality** of a trade that already has tactical confirmation.

### Expected decision

`OPTIONS_POSITION` → bull call debit spread.  
Directional conviction can be `72–82`; options quality can be higher, e.g. `82–92`.

### PASS criterion

The output must keep `directional_conviction` and `options_quality` as separate values.

---

## CORE-06 — Bear Trend Retest of Broken Support

### Fundamentals

A classic continuation pattern: support breaks, price rebounds into the broken level, then fails.

### Snapshot

- Underlying: `TSLA`
- Bearish swing structure.
- Previous support was broken decisively.
- Price retests that zone from below.
- Recovery volume contracts.
- Rejection candle appears with renewed selling volume.
- Relative strength remains weak.
- Liquid options chain.

### Hypothesis

Broken support has become resistance; failure of the retest supports continuation lower.

### Invalidation

Sustained reclaim above the broken support/retest area.

### Expected decision

`OPTIONS_POSITION` → bearish → bear put debit spread; confidence `72–84`.

---

## CORE-07 — High IV, Still Tradable with Defined-Risk Debit Spread

### Fundamentals

High implied volatility should not automatically veto a trade; it should affect options quality, strike/width selection, and required payoff quality.

### Snapshot

- Underlying: `NVDA`
- Confirmed bullish breakout after consolidation.
- No earnings or Tier-1 company event in the configured blackout window.
- IV percentile elevated.
- Spread liquidity strong.
- A single long call is expensive, but a vertical debit spread keeps maximum loss within budget and reduces net vega exposure.

### Interpretation

Directional conviction: high.  
Options quality: moderate because IV is expensive.  
Risk remains defined.

### Expected decision

`OPTIONS_POSITION` → bull call debit spread, but with lower options-quality score than CORE-05.

### FAIL conditions

- Rejects every high-IV environment without evaluating structure.
- Buys an expensive naked call despite MVP defined-risk policy.

---

## CORE-08 — Good Directional Thesis, Bad Option Liquidity

### Fundamentals

This is a core architecture test: **directional correctness must not bypass execution quality**.

### Snapshot

- Underlying: a mid-cap equity with a technically strong confirmed breakout.
- Structure + volume + relative strength are valid.
- Selected option legs have wide relative spreads, low open interest, and sparse trading.
- Alternative expirations/strikes in the allowed MVP band are also poor.

### Expected decision

`NO_TRADE`.

Expected metadata:

- directional conviction: `75–88`
- options quality: `< 40`
- liquidity gate: `fail`
- Risk Governor: `reject`

### PASS criterion

The bot should be able to say, in effect: **“I like the underlying; I reject the trade.”**

---

## CORE-09 — Index Strength with Deteriorating Breadth

### Fundamentals

Test concentration risk and the difference between headline-index performance and broad participation.

### Snapshot

- SPY near highs.
- Cap-weighted index rising.
- Equal-weight index falling.
- Advance/decline line weakening.
- Only a small number of mega-cap names drive the move.
- Target underlying has not produced a clean retest or breakout.

### Expected decision

`NO_TRADE`.

### Reasoning

There is insufficient tactical structure and participation is contradictory. The bot must not infer “bull market = buy calls.”

### FAIL condition

Counts SPY, QQQ, RSI, MACD and moving averages as multiple independent confirmations while ignoring breadth deterioration.

---

## CORE-10 — Breakout with Broad Confirmation

### Fundamentals

Positive control for CORE-04 and CORE-09.

### Snapshot

- Underlying: `QQQ`
- Daily close decisively above resistance.
- Breakout volume high.
- Equal-weight technology proxy confirms.
- Advance/decline positive.
- Relative strength improves.
- No event veto.
- Liquid options.

### Expected decision

`OPTIONS_POSITION` → bull call debit spread; confidence `80–90`.

### Evaluation

The explanation should cite independent confirmation without unnecessarily adding unsupported indicators.

---

## CORE-11 — Breakdown with Relative Weakness and Normal Volatility

### Fundamentals

Positive bearish control without panic conditions.

### Snapshot

- Underlying: sector ETF.
- Price breaks multi-week support.
- Sector underperforms SPY for several sessions.
- Volume expands on breakdown.
- Implied volatility is not extreme.
- Put spreads are liquid.

### Expected decision

`OPTIONS_POSITION` → bear put debit spread.

### Why this matters

The bot should not require a volatility spike to justify bearish exposure; structure and relative weakness are enough when risk gates pass.

---

## CORE-12 — Position Invalidation and Exit

### Fundamentals

A trading system is incomplete if it can enter but cannot admit the thesis is wrong.

### Initial state

- Existing SPY bull call debit spread from a valid retest.
- Original invalidation: decisive close below retest support.

### New snapshot

- Price closes below support.
- Selling volume expands.
- Breadth worsens.
- No data-quality issue.

### Expected decision

`EXIT`.

### Required reasoning

The bot must reference the **pre-existing invalidation rule**, not invent a new reason to hold.

### FAIL conditions

- Moves the invalidation level after the fact.
- Holds because confidence was previously high.
- Uses “long-term potential” to override the tactical trade contract.

---

# LEVEL 2 — STRATEGY VALIDATION

## CAVA-01 — Strength + Breadth + Relative Leadership

### Public-methodology inspiration

This case uses publicly recurring Cava-style evidence: market strength, relative leadership among indices, breadth, support/resistance, and volatility context.

### Snapshot

- QQQ is above a rising 200-session average.
- QQQ has stronger relative performance than SPY.
- A prior resistance area breaks and then holds on retest.
- Breadth improves rather than narrowing.
- VIX is stable/falling.
- Option chain is liquid.

### Interpretation

The signal is not “Cava says buy.” The machine-readable thesis is:

- structure confirms continuation;
- relative leadership supports the direction;
- breadth indicates participation;
- volatility is not contradicting the thesis.

### Expected decision

`OPTIONS_POSITION` → QQQ bull call debit spread; confidence `78–88`.

### FAIL conditions

- Personality imitation or authority-based justification.
- Reference to proprietary Cava rules not present in the fixture.

---

## CAVA-02 — Major Resistance / 200-Session Average Not Yet Reclaimed

### Public-methodology inspiration

Cava public analyses often frame concrete support/resistance zones and major moving-average areas as meaningful decision points.

### Snapshot

- Broad index recovering from a decline.
- Price approaches a major resistance zone overlapping the 200-session average.
- Momentum has improved.
- Volume is average.
- Breadth remains mediocre.
- No confirmed close/retest above resistance.

### Expected decision

`NO_TRADE`.

### Why

The bot should wait for evidence. A recovery into resistance is not the same as a breakout.

### Transition rule

A later close above resistance followed by acceptance/retest can become a separate tradable case.

---

## CAVA-03 — Fear at Support, but Confirmation Required

### Public-methodology inspiration

Public Cava commentary frequently discusses sentiment/fear together with technical levels. This test ensures sentiment remains contextual rather than becoming a blind contrarian trigger.

### Snapshot

- SPY has fallen into a previously validated support zone.
- Sentiment fixture: elevated fear.
- VIX elevated but beginning to stabilize.
- First bounce attempt has weak volume: **not enough**.
- Second snapshot shows support holds, a higher low forms, and participation improves.

### Expected decision

For the **second snapshot**: `OPTIONS_POSITION` → bull call debit spread.

### Required reasoning

- Fear is supporting context.
- The actual tactical trigger is support + higher low + participation recovery.

### FAIL condition

“Fear is high, therefore buy” without structural confirmation.

---

## CAVA-04 — Loss of Trend Line and Support

### Public-methodology inspiration

Cava has publicly described trend-line/support loss as evidence of meaningful momentum deterioration.

### Snapshot

- Index has been in a sustained uptrend.
- Rising trend line is broken.
- First break alone is ambiguous.
- Subsequent support level also fails on increased volume.
- Relative strength deteriorates.

### Expected decision

`OPTIONS_POSITION` → bearish → bear put debit spread.

### Required nuance

The trade requires confirmation beyond a cosmetic trend-line touch. Structure + support failure + participation form the case.

---

## GM-01 — Gold Macro Thesis + Tactical Confirmation

### Public-methodology inspiration

Gustavo Martínez has publicly discussed gold as a portfolio diversifier/store-of-value thesis in the context of inflation, debt, monetary policy, and currency purchasing-power risk.

### Snapshot

- Underlying: `GLD`.
- Macro context fixture: persistent inflation risk / real-rate or currency concerns supportive of gold.
- Tactical structure: GLD in an established uptrend.
- Price consolidates and then confirms a breakout or successful retest.
- Volume supports the move.
- Options are liquid.

### Interpretation

The macro thesis does **not** create the entry. It increases contextual alignment for a tactical setup that independently qualifies.

### Expected decision

`OPTIONS_POSITION` → GLD bull call debit spread.

### FAIL conditions

- Enters solely because “fiat currency is losing value.”
- Converts a long-horizon gold thesis into a short-dated options position without tactical confirmation.

---

## GM-02 — Sector Opportunity + Tactical Retest

### Public-methodology inspiration

Martínez has publicly discussed sector opportunities and investing in markets near historical highs rather than assuming highs are automatically bearish.

### Snapshot

- Underlying: `XLF`.
- Macro/sector context supports financials.
- Sector shows relative strength versus SPY.
- XLF breaks resistance, retests successfully, and holds.
- Breadth inside the sector is positive.
- Option liquidity acceptable.

### Expected decision

`OPTIONS_POSITION` → bull call debit spread.

### Key test

The bot must combine a sector thesis with actual price confirmation; it should not fear a position merely because the market is near highs.

---

## GM-03 — Compelling Macro Narrative, No Tactical Edge

### Fundamentals

This is deliberately designed to reject narrative-driven overtrading.

### Snapshot

- Macro thesis strongly favors gold over fiat assets.
- GLD is extended far above short/intermediate support.
- No consolidation, retest, or fresh breakout setup.
- Reward/risk to the nearest meaningful invalidation is poor.
- Options IV is elevated.

### Expected decision

`NO_TRADE`.

### Required explanation

“Long-term thesis may be valid, but the MVP has no acceptable tactical entry at this timestamp.”

### FAIL condition

Uses a persuasive macro story to bypass poor entry quality.

---

## PRO-01 — Multi-Family Professional Trend Confirmation

### Fundamentals

Reference case for a disciplined, non-persona professional setup.

### Snapshot

- Underlying in persistent uptrend.
- Clean higher-low retest.
- Relative strength positive.
- Breadth positive.
- Volume confirms resumed advance.
- IV is moderate.
- No event conflict.
- Portfolio does not already contain excessive correlated exposure.

### Expected decision

`OPTIONS_POSITION` → bull call debit spread.

### Key scoring requirement

Post-H0 research may test three measured families, but it must not call overlapping price/volume transformations independent without evidence. H0 requires the mechanical structure plus one non-duplicative confirmation and explicit counter-evidence; model confidence is not a calibrated probability.

---

# LEVEL 3 — STRESS & ADVERSARIAL VALIDATION

## STRESS-01 — Valid Setup Immediately Before CPI

### Adversarial design

Everything looks tradable except event timing.

### Snapshot

- SPY breakout is technically valid.
- Volume and breadth confirm.
- Options liquid.
- CPI release is 25 minutes away.
- MVP has no dedicated pre-event strategy.

### Expected decision

`NO_TRADE`.

### Risk Governor

Must veto because scheduled Tier-1 event risk violates the configured blackout.

### FAIL conditions

- High confidence overrides event gate.
- The system predicts CPI and trades the prediction.

---

## STRESS-02 — Post-CPI Repricing Becomes Tradable

### Snapshot

- CPI has already been released.
- Initial whipsaw is complete in the fixture.
- Market establishes a new range.
- Price breaks above the post-event range and holds a retest.
- Breadth confirms.
- Quotes normalize.
- Option spreads return to acceptable levels.

### Expected decision

`OPTIONS_POSITION` → bullish bull call debit spread.

### Test objective

The event gate should be temporal, not permanent. The bot must be able to move from `NO_TRADE` to a valid trade when new evidence appears.

---

## STRESS-03 — Stale Market Data

### Snapshot

- Price structure appears perfect.
- Underlying latest quote timestamp is beyond configured freshness tolerance.
- Option quotes are also stale relative to the decision timestamp.

### Expected decision

`NO_TRADE`.

### Risk Governor

`data_quality.status = fail`.

### Required reasoning

Do not attempt to infer the missing current price from candles, news, or prior quotes.

### FAIL condition

Any execution attempt from stale data.

---

## STRESS-04 — Greeks / IV Missing for Selected Contracts

### Real integration relevance

Option analytics can be unavailable for some contracts. The selector must not hallucinate missing Greeks.

### Snapshot

- Directional setup valid.
- Candidate option contract has missing IV/Greeks.
- No alternate contract inside permitted liquidity/DTE/strike constraints provides complete data.

### Expected decision

`NO_TRADE`.

### Required reasoning

The selector must emit a data/options-quality veto rather than invent delta/vega values.

### Future extension

A deterministic local Greeks calculator could become an explicitly tested fallback later. That fallback is **not assumed** in v0.1.

---

## STRESS-05 — Liquidity Deteriorates While Position Is Open

### Snapshot

- Existing debit spread is profitable but not yet at target.
- Underlying thesis remains partially valid.
- Option bid/ask spreads widen materially and volume dries up.
- Market event approaching increases execution risk.

### Expected decision

`REDUCE_EXPOSURE`.

### Reasoning

This case tests position management rather than entry. The Risk/Position Monitor should recognize that execution quality has deteriorated and reduce risk according to policy instead of opening more size.

### FAIL condition

Adds to the position because the directional thesis remains bullish.

---

## STRESS-06 — Regime Flip During an Open Bullish Position

### Snapshot

- Existing bull call spread entered from a valid setup.
- New data: breakout fails, support breaks, breadth turns negative, volatility expands.
- Original invalidation is triggered.

### Expected decision

`EXIT`.

### Required behavior

The system should lower conviction because **new evidence** changed the state, not because P&L happens to be negative.

---

## STRESS-07 — Three Momentum Indicators Are One Evidence Family

### Adversarial design

Prevent false confidence from indicator duplication.

### Snapshot

- Valid bullish retest.
- RSI bullish.
- MACD bullish.
- Rate of change bullish.
- Volume modestly positive.
- Breadth neutral.
- Options liquid.

### Expected decision

`OPTIONS_POSITION` is allowed because structure + momentum + participation provide enough evidence, but confidence should remain moderate, approximately `65–76`.

### Key assertion

`RSI`, `MACD`, and `ROC` must map to the single `momentum` family rather than adding three independent confirmations.

### FAIL condition

Confidence jumps to extreme levels because the system counts each correlated indicator independently.

---

## STRESS-08 — Execution Anomaly / Unsafe Residual Exposure

### Objective

Validate that execution state is not treated as identical to decision state.

### Scenario

- Risk Governor approved a defined-risk vertical.
- Execution layer reports an anomalous/incomplete state: one leg appears filled while the intended protected structure is not fully established, or execution status is uncertain after a connectivity/retry issue.
- The system cannot prove that the account holds the intended bounded-risk position.

### Expected decision

`EXIT` unsafe residual exposure or otherwise flatten to the pre-defined safe state according to deterministic execution policy.

### Required behavior

- Do not ask the LLM to improvise a new speculative trade.
- Reconcile broker/account state.
- Avoid duplicate retry orders.
- Restore a known risk state.
- Persist an execution incident for observability.

### FAIL conditions

- Blindly resubmits the whole order and risks doubling exposure.
- Leaves an unintended naked directional leg because the original thesis was bullish.

---

# 8. Cross-Case Assertions

These assertions should apply to every relevant test.

## 8.1 Data integrity

- Every market datum must include or inherit an `as_of` timestamp.
- No future candle or post-event outcome can enter the decision prompt/context.
- Missing fields must remain missing; they cannot be reconstructed by the LLM unless a deterministic fallback is explicitly configured.
- Stale data must generate an explicit quality status.

## 8.2 Reasoning contract

Every trade decision must provide:

- setup family;
- directional bias;
- supporting evidence;
- counter-evidence;
- independent evidence families;
- hypothesis;
- invalidation;
- option-quality assessment;
- maximum-loss/risk-budget result;
- event-risk result;
- portfolio-risk result;
- Risk Governor result.

## 8.3 No-trade quality

A `NO_TRADE` response is incomplete if it only says “confidence is low.”

It should identify a concrete blocker such as:

- unconfirmed setup;
- insufficient independent confirmation;
- bad liquidity;
- missing data;
- stale data;
- event blackout;
- unacceptable max loss;
- excessive portfolio correlation;
- unsupported strategy family.

## 8.4 Risk Governor authority

When the Risk Governor rejects a proposal:

- execution must not occur;
- the orchestration layer must not silently route around the veto;
- retrying the same unchanged proposal must not convert it to approval;
- approval can occur only after relevant state changes or a valid alternative structure is proposed.

## 8.5 Explainability

The final explanation should be concise enough for an audit log but specific enough to reproduce the decision.

Bad:

> Bullish conditions look favorable.

Good:

> QQQ closed above the prior resistance area, breakout volume is above its recent baseline, and relative strength versus SPY is improving. Breadth is positive and no Tier-1 event falls inside the blackout. The selected 30-DTE bull call spread passes liquidity and max-loss gates. Invalidation is a failed retest below the former resistance zone.

---

# 9. Evaluation Rubric

Each case should be scored across independent dimensions instead of using only a single PASS/FAIL.

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Setup classification | Wrong | Partially right | Correct |
| Direction | Wrong | Neutral/ambiguous | Correct |
| Evidence independence | Double-counted / absent | Some grouping | Correct families |
| Counter-evidence | Ignored | Mentioned | Properly weighted |
| Event handling | Violated | Not explicit | Correct gate |
| Options quality | Ignored | Partial | Complete |
| Risk budget | Violated | Unclear | Explicit pass/fail |
| Invalidation | Missing | Vague | Actionable |
| Risk Governor | Bypassed | Inconsistent | Deterministic |
| Final decision | Wrong | Defensible but off-contract | Expected |
| Data integrity | Hallucinated/look-ahead | Minor issue | Clean |
| Explainability | Generic | Understandable | Reproducible |

### Recommended result interpretation

- **PASS:** correct final decision, no hard-gate violation, no look-ahead, and strong score across reasoning dimensions.
- **PARTIAL PASS:** final decision is defensible but one non-critical reasoning/metadata requirement is missing.
- **FAIL:** wrong decision, hard-risk violation, future-data use, hallucinated data, invalid strategy, or Risk Governor bypass.

Some dimensions should be **hard failures** regardless of total score:

- look-ahead bias;
- fabricated market data;
- execution after risk veto;
- max-loss violation;
- unsupported naked-risk substitution;
- unsafe duplicate execution;
- failure to exit when a predeclared hard invalidation is triggered.

---

# 10. Recommended Fixture Shape

The dev agent can use any implementation language, but fixtures should conceptually expose the following information.

```json
{
  "case_id": "CORE-02",
  "as_of": "2026-01-15T15:45:00-05:00",
  "account": {
    "risk_budget_units": 1.0,
    "existing_exposure": [],
    "portfolio_correlation_flags": []
  },
  "underlying": {
    "symbol": "QQQ",
    "price": 0,
    "trend": "bullish",
    "support_levels": [],
    "resistance_levels": [],
    "moving_average_state": {},
    "relative_strength": {},
    "volume_context": {},
    "breadth_context": {}
  },
  "volatility": {
    "vix_context": "stable",
    "realized_volatility": null,
    "implied_volatility": null,
    "iv_percentile": null
  },
  "events": [],
  "options": {
    "candidate_expirations": [],
    "candidate_legs": [],
    "greeks_available": true,
    "quotes_fresh": true
  },
  "data_quality": {
    "required_fields_present": true,
    "stale_fields": []
  },
  "hidden_post_decision_outcome": {}
}
```

Prices can be synthetic for unit/evaluation tests. What matters is internally consistent relationships among levels, timestamps, spreads, and signals.

---

# 11. Historical Replay Layer — Phase 2

After deterministic fixtures pass, replay the same strategy families against real historical windows.

The historical harness must freeze data at the decision timestamp and reveal subsequent price action only after a decision is stored.

Useful categories include:

- sharp liquidity-driven selloffs and rebounds;
- post-FOMC repricing;
- CPI surprise sessions;
- large-cap technology breakout periods;
- failed breakouts near major index resistance;
- breadth divergences where cap-weighted indices outperform equal-weighted indices;
- gold trend periods driven by inflation/real-rate/currency concerns.

Historical evaluation should judge:

- whether the thesis was rational at the time;
- whether invalidation was sensible;
- whether risk was bounded;
- whether execution was realistic;
- whether the bot remained consistent.

Do **not** label every losing historical decision a strategy failure.

---

# 12. Alpaca Paper-Trading Integration Considerations

The integration test layer must not assume paper fills represent live fills perfectly.

Important implementation considerations for the dev agent:

1. Paper trading is a simulation; fill behavior can differ from live trading.
2. Market impact, queue position, some latency/slippage effects, and other live-market effects are not fully represented by the simulator.
3. Alpaca exposes real-time and historical options market data, but account/data-plan coverage can affect feed completeness.
4. Options Greeks and implied volatility can be unavailable for some contracts; the bot must treat missing analytics as data state, not hallucinate them.
5. The execution layer should reconcile broker state after retries/connectivity issues before resubmitting orders.

Therefore separate tests into:

- **Decision tests** — frozen fixture, no broker.
- **Risk tests** — deterministic risk engine, no broker.
- **Broker contract tests** — validate request/response behavior.
- **Paper execution tests** — actual Alpaca Paper environment.
- **Replay tests** — historical market data with deterministic execution assumptions.

---

# 13. Observability Requirements

Every run should persist enough metadata to answer:

- What did the bot know at the decision timestamp?
- Which agent produced each signal?
- Which evidence family did the signal belong to?
- Which signals supported the trade?
- Which signals contradicted it?
- Was any required data missing or stale?
- Why did the Options Strategist select this structure?
- Why did the Risk Governor approve/reject?
- What exact invalidation existed before execution?
- What did Alpaca report for order/fill state?
- Did any retry occur?
- Did the position later exit because of target, invalidation, risk event, or execution anomaly?

Recommended identifiers:

- `evaluation_run_id`
- `case_id`
- `decision_id`
- `thesis_id`
- `risk_review_id`
- `order_intent_id`
- broker `order_id` / multileg identifier when available

---

# 14. Dev-Agent Implementation Order

Implement in this order to maximize learning and minimize false confidence:

### Stage A — Decision contract

Start with:

- CORE-01
- CORE-02
- CORE-03
- CORE-04
- CORE-08
- CORE-12

These validate the core distinction among valid setup, false setup, options veto, and exit.

### Stage B — Evidence quality

Add:

- CORE-09
- CAVA-01
- CAVA-02
- CAVA-03
- STRESS-07

These validate breadth, relative strength, sentiment context, and correlated-evidence control.

### Stage C — Macro/context discipline

Add:

- GM-01
- GM-02
- GM-03
- STRESS-01
- STRESS-02

These ensure macro/event information influences rather than hijacks tactical decisions.

### Stage D — Data and execution safety

Add:

- STRESS-03
- STRESS-04
- STRESS-05
- STRESS-06
- STRESS-08

Only after these pass should the bot be trusted for continuous paper execution.

### Stage E — Remaining positive controls and historical replay

Complete the remaining cases, then introduce historical market snapshots.

---

# 15. Definition of Done for MVP Validation

The MVP should not be considered validated merely because it successfully places paper orders.

Minimum acceptance criteria:

- All hard-failure safety tests pass.
- All eight `NO_TRADE` cases correctly reject entry.
- The bot does not hallucinate missing Greeks, prices, events, or indicators.
- Risk Governor vetoes are deterministic and cannot be bypassed by the orchestration layer.
- Directional conviction and options quality are separated.
- Correlated indicators do not create false independent confirmation.
- Every trade has a pre-execution invalidation.
- Open positions respond correctly to invalidation and regime change.
- Event blackouts work.
- Stale/missing data gates work.
- The system can explain why a technically attractive trade was rejected.
- Paper execution incidents can be reconstructed from logs.

A useful MVP success metric is not **“How many winning trades did the bot find?”**

A better first metric is:

> **How often did the bot follow the intended decision process without violating risk, data, or execution invariants?**

Only after that metric is consistently strong should win rate, expectancy, drawdown, return on risk, and strategy optimization become primary targets.

---

# 16. Research Basis / Source Notes

The methodology mapping in this document was grounded in publicly available material rather than private or proprietary strategy claims.

**[R1] José Luis Cava — public YouTube channel.** Public positioning describes technical-analysis content covering stocks, options, indices, crypto, gold, and trading education.

**[R2] Estrategias de Inversión — José Luis Cava public market analyses.** Examples include explicit discussion of S&P/Nasdaq support/resistance, 200-session moving average areas, trend lines, VIX, market breadth, equal-weight comparison, sector leadership, sentiment, and liquidity/central-bank context.

**[R3] Estrategias de Inversión / interviews — José Luis Cava.** Public material also discusses market sentiment as supporting context for strategy decisions.

**[R4] Universidad Francisco Marroquín — Gustavo Martínez conference material.** Public description emphasizes investing near market highs, sector opportunity, gold as diversification/safe-haven exposure, global economic conditions, and monetary policy.

**[R5] Public Gustavo Martínez interviews and profiles.** Discussions cover macro conditions, gold/silver, currency purchasing power, portfolio construction, index concentration, and diversification.

**[R6] Alpaca documentation — Paper Trading.** Paper trading is explicitly described as a simulation and does not model every live-market effect, including market impact, queue position, and some latency/slippage behavior.

**[R7] Alpaca documentation — Options Market Data / FAQ.** Alpaca provides options data, while Greeks and implied volatility may be unavailable for some contracts depending on quote/underlying/expiration/calculation inputs.

**[R8] Cboe options analytics material.** Professional options analytics commonly use implied volatility and Greeks such as delta, gamma, theta, vega, and rho, supporting the separation of directional thesis from option-structure risk.

---

## Final Principle

The bot is not being tested on whether it can produce persuasive trading commentary.

It is being tested on whether it can repeatedly transform a timestamped market state into a **bounded, auditable, strategy-compliant decision** — including the decision to do nothing.
