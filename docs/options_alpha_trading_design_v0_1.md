# Options Alpha Agent

## Trading System Design Specification

*Regime-aware directional options trading with explicit evidence, bounded risk, and deterministic vetoes*

| **Document**          | **Value**                                                          |
|-----------------------|--------------------------------------------------------------------|
| Version               | 0.1.3 — exit lifecycle review incorporated                        |
| Date                  | 28 August 2026                                                     |
| Target category       | Options Alpha Agents                                               |
| Operating environment | Alpaca paper trading during the hackathon                          |
| Primary horizon       | Directional swing trades held intraday to ~3 sessions              |
| Primary structures    | Defined-risk bull call spreads and bear put spreads                |
| Design priority       | Auditable execution boundary first; trading hypothesis is a demo   |

| **Design position:** The strategy is not assumed correct. H0 uses one SPY trend-continuation/retest setup to demonstrate a bounded AI memo, deterministic risk, immutable execution authority, and reconciliation. The strategy and the model's incremental value remain hypotheses; `NO_TRADE` and a deterministic baseline outperforming the model are valid results. |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# Contents

- 1\. Executive conclusion

- 2\. Critical assessment of the concept

- 3\. Trading objective and competition constraints

- 4\. Core market hypothesis

- 5\. Trading universe and horizon

- 6\. End-to-end trading decision model

- 7\. Signal model and evidence contract

- 8\. Regime layer

- 9\. Market structure and setup families

- 10\. Relative strength and breadth

- 11\. Sentiment, news and event risk

- 12\. Options suitability and structure selection

- 13\. Conviction and arbitration

- 14\. Risk governor

- 15\. Position lifecycle and exits

- 16\. Agent responsibilities

- 17\. State and decision records

- 18\. Observability and explainability

- 19\. Validation and evaluation

- 20\. Hackathon operating profile

- 21\. Failure modes and controls

- 22\. MVP scope and deferred ideas

- 23\. Worked examples

- 24\. Source basis and design notes

# 1. Executive conclusion

The recommended hackathon product is an auditable AI execution firewall demonstrated through one bounded SPY directional-options setup. It does not ask an LLM to predict prices. Deterministic code recognizes the setup, constructs a defined-risk vertical, calculates risk, creates execution authority, and reconciles broker state. The LLM produces a schema-constrained evidence memo that may support or abstain, and its incremental value must be measured against a deterministic no-LLM baseline.

| **Core principle:** The AI layer may interpret, reconcile and explain evidence, but raw numerical signals, eligibility gates, position-risk limits and execution vetoes should remain explicit and testable. |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

The trading design is intentionally narrower than the broader research inspiration. José Luis Cava contributes useful concepts around strength, breadth, liquidity, confirmation, false signals and disciplined exits. Gustavo Martínez contributes a macro/regime perspective, expectations, liquidity/cycle awareness and capital-preservation discipline. However, neither person is treated as a live signal source, and their views are not copied as trades.

For a seven-day competition, broad macro research, several setup families, and product-scale portfolio learning are unjustified scope. H0 focuses on one mirrored trend-continuation/retest setup on SPY. QQQ and IWM may provide read-only context but are not tradeable until the vertical slice is stable.

# 2. Critical assessment of the concept

| **Current idea**           | **Assessment**                                                                                        | **Design consequence**                                                      |
|----------------------------|-------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| Use macro regime           | Useful, but slow and often ambiguous over a one-week window.                                          | Use as prior/filter and risk modifier, not primary trigger.                 |
| Use market breadth         | Strong addition because it tests whether index moves have participation.                              | Keep as an independent confirmation family.                                 |
| Use relative strength      | Highly relevant for directional alpha and candidate narrowing.                                        | Make it a core ranking/confirmation input.                                  |
| Use sentiment/news         | Useful but noisy; LLM sentiment can overreact to narratives.                                          | Cap its weight; require freshness and source quality.                       |
| Use options IV/Greeks      | Necessary, but mostly determines trade expression rather than direction.                              | Separate directional thesis from options suitability.                       |
| Use valuation/fundamentals | Important for investing, weak as a short-horizon entry signal.                                        | Defer from MVP except as an extreme-risk/context flag.                      |
| Use many agents            | Can improve separation of concerns but can also create correlated opinions and coordination overhead. | Prefer a small number of evidence owners plus deterministic arbitration.    |
| Trade around events        | Can create opportunities but changes the strategy into an event/volatility system.                    | Treat scheduled events as risk/catalyst metadata unless explicitly enabled. |

| **Rejected assumption:** More signals do not automatically produce more confidence. Several technical indicators can be different mathematical views of the same price movement. The system must aggregate by evidence family and cap correlated contributions. |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 3. Trading objective and competition constraints

## 3.1 Objective

Demonstrate that an AI-assisted Paper-trading decision can be reconstructed and constrained from evidence through an immutable approved intent, exact broker request, and reconciled outcome. Directional performance is measured, but positive alpha is not assumed and is not claimed from a short Paper sample.

## 3.2 Practical constraints

- The competition window is short, so daily and intraday evidence must drive entries while slower regime signals provide context.

- Options introduce spread, theta, gamma and implied-volatility effects; a correct directional view can still lose money if the structure is poor.

- Paper fills are useful for competition scoring but can be more optimistic than real execution; evaluation should apply a separate slippage/liquidity realism check.

- The bot must be willing to remain flat when no setup passes all gates.

- The design should remain understandable enough that a judge can inspect why the trade existed, why the chosen option structure fit the thesis, and what would invalidate it.

# 4. Core market hypothesis

The strategy tests whether a mechanically defined trend/retest setup plus one non-duplicative confirmation produces better short-horizon decisions than a declared simple price-only baseline after option friction. This is a falsifiable hypothesis, not an established edge. Most proposed regime, structure, relative-strength, and breadth features are transformations of overlapping price/volume data and must not be called statistically independent without measurement.

| **Trading thesis:** Trade direction only when context + structure + participation converge; use volatility and options data to decide how to express the view; use risk controls to decide whether the system is allowed to act. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

**Null hypotheses:** the confirmation adds no value after friction; the deterministic baseline matches or exceeds the LLM-assisted path; and the available feed does not support a sufficiently reliable option expression. H0 reports these outcomes rather than tuning them away.

## 4.1 Evidence hierarchy

| **Layer**            | **Question**                                                               | **Role**                     |
|----------------------|----------------------------------------------------------------------------|------------------------------|
| Regime               | Is the broader environment supportive, hostile, transitional or unclear?   | Prior / sizing modifier      |
| Candidate strength   | Which liquid underlyings are leading or lagging?                           | Universe narrowing           |
| Market structure     | Is there a specific, testable setup now?                                   | Primary entry trigger        |
| Participation        | Is the move broad enough to trust?                                         | Confirmation / contradiction |
| Sentiment & catalyst | Is narrative/positioning supportive or dangerously crowded?                | Secondary modifier           |
| Options suitability  | Can the thesis be expressed with acceptable IV, spread, Greeks and payoff? | Trade construction gate      |
| Risk                 | Can this trade be taken without violating portfolio constraints?           | Final veto                   |

# 5. Trading universe and horizon

## 5.1 Universe

The MVP should prefer highly liquid ETFs with deep options markets. This reduces single-company event risk, improves quote quality, and lets macro/relative-strength logic operate naturally.

| **Tier** | **Examples**                 | **Use**                                                                           |
|----------|------------------------------|-----------------------------------------------------------------------------------|
| H0       | SPY                           | Only tradeable underlying for the hackathon vertical slice.                        |
| P1       | QQQ, IWM                      | Read-only H0 context; tradeable only after the SPY lifecycle is stable.             |
| Later    | XLK, XLF, XLE, SMH, GLD, TLT | Expansion only after contract liquidity and spread quality pass.                   |
| Deferred | Individual equities          | Add only after the ETF process is stable; requires earnings/event-specific rules. |

## 5.2 Horizon

- Signal horizon: approximately 1–3 trading sessions.

- Entry evaluation: intraday, but not high-frequency.

- Preferred option expiration: enough time to reduce extreme theta/gamma sensitivity while preserving directional responsiveness.

- The strategy should not depend on same-day expiry behavior for the MVP.

# 6. End-to-end trading decision model

| **Stage**            | **Trading responsibility**                                                                        |
|----------------------|---------------------------------------------------------------------------------------------------|
| 1\. Observe          | Refresh regime, candidate ranking, structure, participation, sentiment and options state.         |
| 2\. Qualify          | Reject stale, incomplete, illiquid or contradictory evidence before scoring.                      |
| 3\. Form thesis      | Create bullish, bearish or neutral directional thesis with explicit counter-evidence.             |
| 4\. Confirm setup    | Require an allowed setup family: trend continuation or confirmed breakout/retest.                 |
| 5\. Select structure | Choose a defined-risk call or put vertical that fits the expected horizon and volatility state.   |
| 6\. Risk review      | Check per-trade risk, cluster exposure, total open risk, daily loss state and event risk.         |
| 7\. Execute          | Use controlled order logic; no forced market participation.                                       |
| 8\. Monitor          | Track thesis validity, option behavior, P&L and time decay.                                       |
| 9\. Exit             | Exit on thesis invalidation, risk limit, profit objective, time stop or structural deterioration. |
| 10\. Learn           | Record trade outcome and signal behavior without changing live rules opportunistically.           |

# 7. Signal model and evidence contract

Every signal should be represented as evidence with direction, strength, confidence, freshness, horizon and invalidation metadata. This prevents the decision layer from treating all observations as equally reliable.

```json
{
  "signal_id": "breadth.equal_weight_confirmation",
  "as_of": "2026-08-31T10:15:00-04:00",
  "underlying": "QQQ",
  "family": "participation",
  "direction": 1,
  "strength": 0.74,
  "confidence": 0.88,
  "horizon": "1_to_3_sessions",
  "freshness": "current",
  "source_quality": 0.95,
  "evidence": {
    "observation": "equal-weight participation confirms cap-weight advance",
    "counter_evidence": "small-cap participation remains neutral"
  },
  "expires_when": [
    "participation_score < 0.45",
    "source becomes stale"
  ]
}
```

## 7.1 Family-level aggregation

Correlated indicators should be combined inside a family before reaching the final conviction score. For example, moving-average slope, ADX and recent momentum are all related to trend. They should not count as three independent bullish votes.

| **Family**         | **Typical evidence**                                                              | **Final role**              |
|--------------------|-----------------------------------------------------------------------------------|-----------------------------|
| Regime             | Broad index trend, risk appetite, rates/liquidity proxies, volatility environment | Context                     |
| Structure          | Trend state, pullback/retest quality, breakout integrity, volume/price behavior   | Primary directional trigger |
| Participation      | Relative strength, equal-weight confirmation, sector breadth                      | Independent confirmation    |
| Sentiment/Catalyst | News novelty, option skew, crowding, scheduled catalysts                          | Modifier / warning          |
| Options quality    | Bid/ask, quote freshness, IV vs realized volatility, Greeks, payoff geometry      | Expression gate             |
| Risk state         | Open risk, drawdown, correlation cluster, event exposure                          | Veto                        |

# 8. Regime layer

The regime layer is inspired by macro/liquidity thinking but deliberately avoids pretending that the economy can be classified perfectly in real time. Its output is a market-risk prior, not a price prediction.

| **Regime** | **Meaning**                                                      | **Trading consequence**                                                                      |
|------------|------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| Risk-on    | Broad trend and risk appetite supportive; volatility controlled. | Long setups require less additional evidence; bearish trades require stronger contradiction. |
| Risk-off   | Broad trend deteriorating; defensive/risk-off behavior visible.  | Bearish setups favored; bullish positions smaller or rejected.                               |
| Transition | Conflicting evidence or regime shift in progress.                | Higher threshold, smaller size, fewer trades.                                                |
| Uncertain  | Data disagreement or low confidence.                             | No regime advantage; system relies on exceptionally strong local setup or stays flat.        |

## 8.1 Regime inputs

- Broad equity trend and volatility-adjusted momentum.

- Risk-appetite relationships such as growth vs defensive or credit-sensitive proxies.

- Rates and liquidity-sensitive market proxies where timely and reliable.

- Breadth/participation deterioration that may precede index-level weakness.

- Volatility state and evidence of transition rather than a simple high/low label.

| **Important limitation:** Slow macro releases, money-supply narratives and valuation are not suitable as intraday triggers. In this bot they can change regime confidence or position size, but they cannot independently authorize a trade. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 9. Market structure and setup families

H0 supports one mirrored directional setup family. Limiting the taxonomy improves testability and prevents the model from inventing a new trading style for every market situation.

## 9.1 Setup A — Trend continuation / second opportunity

1\. Underlying is already in a qualified directional trend.

2\. Relative strength/weakness is favorable versus the benchmark or peer group.

3\. Price pulls back, consolidates, or retests a recently broken area without invalidating the trend.

4\. Participation does not materially deteriorate during the pause.

5\. A renewed directional trigger appears after the retest.

6\. Options quality passes and event risk is acceptable.

| **Why this is the core setup:** It operationalizes the “go with strength, then wait for a second opportunity” concept while avoiding late breakout chasing. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------|

## 9.2 Post-H0 setup B — Confirmed breakout / breakdown

1\. Price exits a well-defined recent range or structural level.

2\. The move is not treated as valid on price alone; participation and relative strength must confirm.

3\. A very extended first impulse may be rejected in favor of a retest entry.

4\. A false-break condition is defined before the trade is opened.

5\. The option structure must still provide a reasonable payoff after the move has begun.

## 9.3 Explicitly excluded from MVP

- Countertrend mean-reversion trades.

- Confirmed breakout/breakdown until the SPY trend/retest vertical slice is stable.

- 0DTE directional gambling or gamma scalping.

- Uncovered option selling.

- Pure earnings/event bets without a separate tested event model.

- Elliott-wave labeling as an execution trigger.

- LLM-generated support/resistance that cannot be traced to objective market structure.

# 10. Relative strength and breadth

Relative strength narrows the battlefield; breadth tests whether the apparent move is supported by participation. They should be evaluated separately because a strong ETF can rise while the underlying market becomes increasingly narrow.

## 10.1 Relative-strength responsibilities

- Rank candidate underlyings on short and medium lookback windows.

- Compare candidate performance with SPY and relevant peer groups.

- Prefer instruments where strength persists across more than one horizon rather than a single one-day spike.

- Penalize candidates that are strong only because of one isolated event unless event trading is explicitly enabled.

## 10.2 Breadth responsibilities

- Measure whether equal-weight behavior confirms capitalization-weighted index movement.

- Track percentage of the monitored universe participating above short/medium trend thresholds.

- Detect divergence: index makes new highs/lows while participation weakens.

- Use breadth as a confirmation or confidence penalty, not as an independent entry by itself.

# 11. Sentiment, news and event risk

Sentiment is intentionally secondary. The system should distinguish information from narrative. A news headline may explain a move but should not automatically become a directional trade.

| **Input**               | **Use**                                          | **Guardrail**                                                             |
|-------------------------|--------------------------------------------------|---------------------------------------------------------------------------|
| News                    | Detect novel information and possible catalysts. | Require freshness, relevance and corroboration by price/structure.        |
| Options skew / IV shape | Identify asymmetric demand or crowding.          | Treat as context; avoid interpreting every skew move as informed flow.    |
| Extreme sentiment       | Possible contrarian warning.                     | Only actionable when price/participation shows exhaustion or reversal.    |
| Scheduled events        | Identify gap/volatility risk.                    | Reduce size or block entry when the event is outside the strategy thesis. |

| **Rule:** An LLM sentiment label cannot authorize a trade. It may add or subtract limited confidence after market-derived evidence already exists. |
|----------------------------------------------------------------------------------------------------------------------------------------------------|

# 12. Options suitability and structure selection

Directional conviction answers “what do we believe?” The options layer answers “is there an efficient defined-risk way to express it?” These are separate decisions.

## 12.1 MVP structures

| **Direction**            | **Preferred structure** | **Reason**                                                                                                                 |
|--------------------------|-------------------------|----------------------------------------------------------------------------------------------------------------------------|
| Bullish                  | Bull call debit spread  | Defined maximum loss, reduced premium cost versus a naked long call, less exposure to IV/theta than a single far-OTM call. |
| Bearish                  | Bear put debit spread   | Defined maximum loss and clean bearish expression without short-stock dependency.                                          |
| Neutral / low conviction | No trade                | The system is not required to manufacture an options position.                                                             |

## 12.2 Baseline contract-selection profile

| **Parameter**   | **Initial design target**                                     | **Rationale**                                                                      |
|-----------------|---------------------------------------------------------------|------------------------------------------------------------------------------------|
| Expiration      | Approximately 14–35 DTE                                       | Avoid extreme 0DTE gamma/theta while remaining responsive to a 1–3 session thesis. |
| Long-leg delta  | Approximately 0.55–0.70                                       | Keeps the spread meaningfully directional rather than lottery-like.                |
| Short-leg delta | Approximately 0.25–0.40                                       | Caps cost and sets a realistic target zone.                                        |
| Spread width    | Aligned with expected move and liquid strike spacing          | Avoid arbitrary width; target payoff should match the thesis horizon.              |
| Net debit       | Prefer \<= ~50% of spread width; reject clearly poor geometry | Supports approximately 1:1 or better max reward-to-risk before execution friction. |
| Quote quality   | Fresh two-sided quotes; narrow relative spread                | Avoid theoretical edges that cannot be executed.                                   |
| Order style     | Limit-oriented; combined multi-leg execution where available  | Controls slippage and avoids legging risk.                                         |

| **Not sacred:** These numerical ranges are starting constraints for validation, not truths. They should be changed only after replay/backtest evidence, not because one live trade would have worked better. |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## 12.3 Options quality score

A separate options-quality score should combine contract liquidity, quote freshness, IV/realized-volatility relationship, payoff geometry and time/Greeks fit. Poor options quality blocks the trade even when the directional thesis is excellent.

# 13. Conviction and arbitration

The broader product may eventually combine measured evidence families, not raw indicators. The initial weights below are research candidates only. H0 does not present their output as calibrated probability and does not require this weighted score for execution.

| **Directional family**      | **Baseline weight** |
|-----------------------------|---------------------|
| Market structure            | 35%                 |
| Relative strength + breadth | 30%                 |
| Regime                      | 20%                 |
| Sentiment + catalyst        | 15%                 |

The signed directional score is evaluated independently from options quality and data quality. This avoids a highly liquid option chain accidentally increasing bullish conviction or a macro view compensating for an invalid entry structure.

```json
{
  "directional_thesis": {
    "direction": "bullish",
    "score": 0.73,
    "agreement": {
      "structure": 0.82,
      "participation": 0.76,
      "regime": 0.58,
      "sentiment_catalyst": 0.55
    },
    "counter_evidence": [
      "small-cap breadth remains neutral"
    ]
  },
  "quality_gates": {
    "data_quality": 0.93,
    "options_quality": 0.81,
    "event_safety": 0.9,
    "risk_governor": "approve"
  },
  "decision": "eligible"
}
```

## 13.1 Suggested entry gates

- Objective SPY trend-continuation/retest structure passes its frozen mechanical rule.

- At least one non-duplicative confirmation aligns with the direction.

- The deterministic baseline and bounded model memo are both retained; model confidence is metadata, not a calibrated entry probability.

- No single high-confidence counter-signal that invalidates the setup.

- Data quality above a strict minimum.

- Options quality above a strict minimum.

- Risk governor approval.

- Setup family explicitly recognized and invalidation level known before entry.

| **No-trade is first class:** A neutral decision is not a failure of the agent. A system that can explain why it refused a tempting but low-quality trade is more credible than one that must always act. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 14. Risk governor

The risk governor has veto authority and should not be overruled by an LLM. Risk is defined at the option-spread level and at the portfolio/correlation-cluster level.

| **Control**                       | **Hackathon H0 baseline** | **Purpose**                                                     |
|-----------------------------------|--------------------------|-----------------------------------------------------------------|
| Maximum loss per demonstration trade | Conservative owner-approved cap; candidate ceiling 0.50% of equity | Bound the only H0 position without pretending the value is statistically calibrated. |
| Concurrent or pending strategies  | 1                        | Removes cluster and multi-position state from H0.               |
| Total open defined risk           | Equal to the one-strategy cap | No separate portfolio optimization in H0.                   |
| Daily realized + marked loss stop | No second entry after the demonstration loss or execution incident | Keep the demo from increasing exposure after failure. |
| Averaging down                    | Not allowed              | Prevents thesis drift and risk escalation.                      |

Multi-position, correlation-cluster, high-conviction tiers, and statistically calibrated loss limits are post-H0 product work. The candidate 0.50% ceiling still requires owner approval and a valid minimum one-spread quantity before a Paper write; if one spread exceeds the cap, the result is `NO_TRADE`.

## 14.1 Automatic veto conditions

- Required market or options data is stale or missing.

- Option quotes are one-sided, crossed, abnormally wide or otherwise unreliable.

- The market is halted or the execution state is inconsistent.

- Daily loss stop or total risk budget has been reached.

- The trade duplicates an existing highly correlated directional position.

- A major scheduled event creates gap risk that is not part of the thesis.

- The expected maximum loss cannot be known before entry.

- The setup has no objective invalidation condition.

# 15. Position lifecycle and exits

Entry is only half of the system. Each open trade retains the original thesis, invalidation conditions and expected time horizon. The monitoring process evaluates whether the thesis is strengthening, unchanged, decaying or invalidated.

| **Exit type**       | **Trigger**                                                                           | **Behavior**                                                          |
|---------------------|---------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| Thesis invalidation | Underlying breaks the pre-defined structural invalidation or confirmation disappears. | Close; do not wait for maximum option loss.                           |
| Risk stop           | Spread loss reaches the configured maximum tolerable fraction of debit.               | Close even if the narrative still sounds plausible.                   |
| Profit capture      | A substantial portion of achievable spread profit is realized quickly.                | Prefer realizing gains rather than holding for theoretical max value. |
| Time stop           | Expected move fails to develop within the thesis horizon.                             | Close or reduce; do not pay theta for an inactive idea.               |
| Conviction decay    | Evidence score drops below the maintenance threshold.                                 | Exit when deterioration is broad, not on one noisy feature.           |
| Expiry control      | DTE reaches a minimum safety threshold.                                               | Close before expiration/assignment mechanics dominate the trade.      |

## 15.1 Initial exit profile

- Use underlying thesis invalidation as the primary stop logic; option premium P&L is a secondary hard risk limit.

- Do not require a fixed take-profit if the thesis remains strong, but capture gains when the spread has realized a large portion of its available profit early.

- Use a time stop around the intended 1–3 session horizon.

- Avoid carrying very short-dated spreads into expiration merely to seek the final few percentage points of maximum profit.

## 15.2 H0 operational disposition

The current code implements provisional trigger arithmetic, but it does **not** yet validate the complete autonomous position lifecycle. The governing adversarial assessment is the [Exit Policy and Position-Lifecycle Review v0.1](./options_alpha_exit_policy_review_v0_1.md).

For H0, the candidate policy separates broker integrity from economic exits. Reconciliation mismatch, unexpected or partial exposure, and ambiguous close state are handled first as incidents; the agent retains responsibility until Alpaca confirms the remaining filled quantity or flat state. Economic precedence is then expiry/calendar safety, scheduled-event control, typed completed-session thesis invalidation, a loss cap calculated from actual filled debit, a three-completed-session time stop, and profit capture calculated from actual fill. Missing option value is an integrity condition that halts new risk, not `HOLD` and not a reason to suppress independent exit rules.

The provisional values—7-DTE expiry guard, 50% of filled debit loss threshold, three completed trading sessions, and 60% of maximum spread gain—are candidate H0 parameters. They are not optimized values and remain subject to Trading-owner approval and replay/sensitivity evidence. Conviction decay remains diagnostic rather than an automatic H0 broker trigger until a deterministic maintenance score is defined and validated.

An order may be described as opened or closed only after filled strategy quantity and broker position reconcile. Broker acceptance alone is `SUBMITTED`; process-local state alone is not position ownership. Autonomous entry stays disabled until the exit review's acceptance matrix is satisfied.

# 16. Agent responsibilities

The agent design exists to support an auditable authority boundary; it should not manufacture a trading edge. These are logical responsibilities in one bounded workflow, not six autonomous agents.

| **Component**          | **Owns**                                                                                         | **Must not do**                                                   |
|------------------------|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| Regime Agent           | Broad context, regime confidence, transition warnings.                                           | Select specific contracts or override a setup.                    |
| Market Structure Agent | Candidate ranking, trend/breakout/retest state, relative strength, breadth synthesis.            | Place trades or change risk limits.                               |
| Bounded Thesis Synthesizer | Produce a referenced trade memo, surface counter-evidence, and return support or neutral abstention. | Reverse the deterministic setup, change invalidation, invent data, or create authority. |
| Options Strategist     | Choose eligible defined-risk structure and evaluate IV/Greeks/payoff quality.                    | Create direction independently of the thesis.                     |
| Risk Governor          | Sizing, concentration, daily loss state, vetoes.                                                 | Be overridden for “high confidence.”                              |
| Position Manager       | Monitor thesis, time, risk and exit conditions.                                                  | Rewrite the original thesis to justify staying in a losing trade. |

| **Deliberate choice:** This is not a six-agent debate. Most components exchange structured evidence. Free-form multi-agent argument should be limited to summarizing counter-evidence, because debate can create narrative confidence without new information. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

H0 runs the same frozen cases through a deterministic no-LLM baseline and the bounded model path. The model earns a role only if it measurably improves evidence fidelity, counter-evidence detection, or correct abstention at acceptable latency and cost. A more persuasive explanation by itself is not evidence of a better decision.

# 17. State and decision records

## 17.1 Thesis record

```json
{
  "thesis_id": "2026-08-31-SPY-01",
  "underlying": "SPY",
  "direction": "bullish",
  "setup": "trend_continuation_retest",
  "horizon": "1_to_3_sessions",
  "formed_at": "2026-08-31T10:20:00-04:00",
  "evidence": {
    "regime": 0.58,
    "structure": 0.82,
    "participation": 0.76,
    "sentiment_catalyst": 0.55
  },
  "counter_evidence": [
    "IWM breadth not confirming"
  ],
  "invalidation": [
    "underlying closes below retest failure level",
    "participation score falls below maintenance threshold"
  ],
  "status": "qualified"
}
```

## 17.2 Trade plan

```json
{
  "trade_plan": {
    "thesis_id": "2026-08-31-QQQ-01",
    "structure": "bull_call_spread",
    "expiration_profile": "14_to_35_DTE",
    "long_leg_delta_target": "0.55_to_0.70",
    "short_leg_delta_target": "0.25_to_0.40",
    "max_loss_pct_equity": 0.50,
    "options_quality": 0.81,
    "risk_status": "approved",
    "entry_status": "ready"
  }
}
```

## 17.3 Decision lifecycle

Observed → Qualified → Thesis formed → Options eligible → Risk approved → Order pending → Open → Monitoring → Exit pending → Closed. Rejected candidates retain a rejection reason rather than disappearing from the audit trail.

# 18. Observability and explainability

For the hackathon, explainability is not just presentation. It is a debugging mechanism. Every trade should be reconstructable from the evidence available at decision time.

| **Record**      | **Minimum content**                                                             |
|-----------------|---------------------------------------------------------------------------------|
| Signal snapshot | Value, direction, strength, confidence, freshness, source quality.              |
| Thesis          | Direction, setup family, supporting evidence, counter-evidence, invalidation.   |
| Option plan     | Expiration, strikes/deltas, IV context, spread quality, max loss/max gain.      |
| Risk decision   | One-strategy cap, calculated maximum loss, mode/authority state, veto checks.   |
| Execution state | Requested structure, fill/partial-fill state, quote context.                    |
| Exit record     | Reason, thesis state, P&L, holding time, whether exit rule behaved as designed. |

## 18.1 Judge-facing explanation

The human-readable explanation should answer five questions in order: Why this underlying? Why this direction? Why now? Why this option structure? What makes the bot exit or admit it is wrong?

# 19. Validation and evaluation

The strongest risk in this design is overfitting a short competition. Validation should therefore test whether the rules produce sensible behavior across different recent market conditions, not optimize every threshold for maximum historical P&L.

## 19.1 Required evaluation metrics

| **Metric**                 | **Why it matters**                                                               |
|----------------------------|----------------------------------------------------------------------------------|
| Trade count                | Confirms the strategy can actually generate opportunities in the short window.   |
| Win rate                   | Useful but insufficient by itself.                                               |
| Average win / average loss | Shows payoff asymmetry and whether exits work.                                   |
| Expectancy per trade       | Core quality measure across wins and losses.                                     |
| Maximum drawdown           | Tests whether competition risk is tolerable.                                     |
| Average holding time       | Validates the 1–3 session design.                                                |
| Signal-to-trade conversion | Shows whether gates are too strict or too loose.                                 |
| No-trade accuracy review   | Inspect rejected setups that later moved strongly to understand false negatives. |
| Slippage sensitivity       | Penalize backtest/paper results for realistic option spreads.                    |
| Correlation concentration  | Prevents three trades from being one disguised bet.                              |

## 19.2 Validation sequence

1\. Freeze a replay manifest with provider, feed, adjustment, timeframe, calendar/session filter, source timestamps, row counts, and raw/normalized hashes so repeated results use identical inputs.

2\. Replay at least several recent market regimes rather than only the last bullish period.

3\. Validate setup recognition before optimizing option parameters.

4\. Use an options-specific fill model with explicit signal/fill timing, bid/ask treatment for both legs and the net strategy, contract multiplier, fees, missed fills, expiry, and exercise/assignment assumptions.

5\. Stress the strategy with wider spreads, latency, queue/liquidity limits, missed fills, and applicable fees that Alpaca Paper omits; report broker Paper P&L separately from stressed P&L.

6\. Compare the setup with a declared simple price-only benchmark, and compare the bounded model path with the deterministic no-LLM path on the same frozen cases.

7\. Treat the hackathon sample as diagnostic. Walk-forward or holdout testing is required before any post-event alpha claim or threshold-promotion claim.

8\. Freeze the H0 rules before Paper execution; during the competition fix defects, not disappointing outcomes.

# 20. Hackathon operating profile

The competition is a special operating mode, not the production policy. It should be explicit when risk limits or cadence are chosen because of the short evaluation window.

| **Area**         | **Hackathon profile**                                                                    |
|------------------|------------------------------------------------------------------------------------------|
| Primary universe | SPY only; QQQ/IWM may be read-only context.                                               |
| Setups           | One mirrored trend continuation/retest setup.                                            |
| Direction        | Bullish and bearish.                                                                     |
| Structure        | Defined-risk vertical debit spreads.                                                     |
| Trade frequency  | One reviewed Paper lifecycle is sufficient; no trade is forced for performance optics.   |
| Risk             | One open or pending strategy and a conservative owner-approved maximum-loss cap.         |
| Events           | Risk filter by default, not a separate event-trading strategy.                           |
| Rule changes     | Core logic frozen once competition begins except clear defects or data outages.          |

| **Competition-specific risk:** The published judging criteria emphasize technology, presentation, business value, and originality; they do not currently list P&L. Broker Paper P&L is therefore a diagnostic/demo result unless organizers publish a separate leaderboard rule. It must not drive oversized risk or an unsupported alpha claim. |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 21. Failure modes and controls

| **Failure mode**       | **Example**                                                             | **Control**                                                     |
|------------------------|-------------------------------------------------------------------------|-----------------------------------------------------------------|
| Unproven alpha claim   | A few Paper outcomes are presented as evidence of a repeatable edge.     | Declare null hypotheses, benchmarks, sample limits, and diagnostic-only conclusions. |
| Decorative AI          | The LLM rewrites deterministic signals into fluent prose without improving the decision. | Run a no-LLM ablation and measure fidelity, counter-evidence, abstention, latency, and cost. |
| Generic positioning    | The product is described only as an “AI trader with guardrails and dashboard.” | Demonstrate hash-linked authority, exact-request proof, reproducible refusal, and ambiguous-write recovery. |
| Narrative overfitting  | LLM creates a compelling macro story after a price move.                | Require structured market evidence before narrative synthesis.  |
| Signal double counting | ADX, momentum and MA slope all vote independently.                      | Aggregate within a single structure/trend family.               |
| Late entry             | Bot buys after an extended breakout because all signals look strongest. | Prefer retest/second-opportunity logic and extension veto.      |
| Options mismatch       | Correct bullish thesis but IV/spread is too expensive.                  | Options-quality gate can reject the trade.                      |
| Correlation blindness  | Long SPY, QQQ and XLK simultaneously.                                   | Cluster-level risk budget.                                      |
| Thesis drift           | Losing trade stays open because new explanations are invented.          | Persist original invalidation; no rewriting after entry.        |
| Paper-fill illusion    | Simulated execution looks better than live market reality.              | Use limit-oriented execution and slippage stress in evaluation. |
| Unreproducible replay  | A changed feed, calendar filter, or normalized file silently changes results. | Store input fingerprints, run lineage, assumptions, and exact code/policy versions. |
| Agent-tool authority drift | A generic skill, CLI command, or MCP trading tool bypasses the deterministic decision and risk path. | Treat skills as advisory, keep MCP read-only, and allow only approved immutable intents through the project broker gateway. |
| Event gap              | Position opened before a major event not modeled by the system.         | Event-safety veto or reduced size.                              |
| Over-complexity        | Too many agents/signals prevent understanding why a trade happened.     | Small evidence taxonomy; explicit ownership and arbitration.    |

# 22. MVP scope and deferred ideas

## 22.1 MVP — build and validate first

- SPY as the only tradeable underlying; QQQ/IWM read-only context if needed.

- One mechanically specified trend-continuation/retest setup plus one non-duplicative confirmation.

- Deterministic baseline plus a bounded, evidence-referenced model memo and ablation.

- Bull call and bear put debit spreads.

- Options-quality gate using quote/IV/Greeks/payoff information.

- One-strategy deterministic Risk Governor and immutable execution authority.

- Position monitoring, thesis invalidation and time exits.

- Full decision audit trail and judge-facing explanation.

- One Paper lifecycle, one refusal, and one ambiguous-write/restart recovery proof.

## 22.2 Defer until the core is stable

- Individual-stock earnings trades.

- QQQ/IWM execution, breakout/breakdown, broader regime and breadth taxonomies, and multi-position portfolio policy.

- Short-volatility structures, iron condors and calendar spreads.

- 0DTE strategies.

- Fundamental valuation as a direct short-horizon signal.

- Complex Elliott-wave interpretation.

- Autonomous strategy mutation during the live competition.

- Large multi-agent debate or self-modifying risk policy.

- A general options backtesting/learning platform and any claim of validated alpha.

# 23. Worked examples

## 23.1 Bullish example — qualified

| **Layer**         | **Observation**                                                              | **Effect**                |
|-------------------|------------------------------------------------------------------------------|---------------------------|
| Regime            | Risk-on but not euphoric.                                                    | \+ moderate bullish prior |
| Relative strength | QQQ leading SPY and peer ETFs across multiple horizons.                      | \+ bullish                |
| Structure         | Pullback holds prior breakout area; momentum resumes.                        | \+ strong bullish trigger |
| Breadth           | Equal-weight technology and majority of monitored tech constituents confirm. | \+ confirmation           |
| Sentiment         | No major contrary catalyst; crowding not extreme.                            | \+ small                  |
| Options           | Liquid 21-DTE call spread with acceptable debit and Greeks.                  | Pass                      |
| Risk              | No correlated open position; risk budget available.                          | Approve                   |

Decision: enter a defined-risk bull call spread. The thesis is invalidated if the retest fails and participation deteriorates. The bot does not remain bullish merely because the macro regime is supportive.

## 23.2 Bearish example — qualified

| **Layer**         | **Observation**                                                | **Effect**                     |
|-------------------|----------------------------------------------------------------|--------------------------------|
| Regime            | Transition toward risk-off.                                    | \- bearish prior               |
| Relative strength | IWM persistently underperforming SPY.                          | \- bearish                     |
| Structure         | Support breaks, rebound fails to reclaim it.                   | \- strong bearish trigger      |
| Breadth           | Participation deteriorating broadly.                           | \- confirmation                |
| Sentiment         | No panic extreme yet.                                          | Neutral                        |
| Options           | Put spread liquid; IV elevated but payoff still acceptable.    | Pass with smaller size         |
| Risk              | Existing QQQ long creates opposing exposure but within limits. | Approve / net exposure checked |

Decision: enter a bear put spread at reduced size because IV is less favorable. Directional conviction and option quality remain separate in the record.

## 23.3 No-trade example — correct refusal

| **Layer**         | **Observation**                              | **Effect**         |
|-------------------|----------------------------------------------|--------------------|
| Regime            | Risk-on.                                     | Bullish prior      |
| Relative strength | SPY strong.                                  | Bullish            |
| Structure         | Price is extended after a large opening gap. | Entry quality poor |
| Breadth           | Mixed; equal-weight does not confirm.        | Contradiction      |
| Sentiment         | Highly enthusiastic news cycle.              | Crowding warning   |
| Options           | Near-term IV expensive and spreads wider.    | Fail               |
| Risk              | Risk budget available.                       | Would approve      |

Decision: NO TRADE. The bot waits for a retest or a new setup instead of using the bullish regime to justify chasing.

# 24. Source basis and design notes

This specification combines the project discussion with current public information reviewed through 27 August 2026. Source material is used to verify platform capabilities and extract broad trading and operating principles; it is not used as a live recommendation feed or execution authority.

## 24.1 Platform / competition sources

- lablab.ai — Alpaca AI Trading Agents Hackathon: online build from 28 August through 4 September 2026, Paper environment, named Alpaca Trading API/MCP/CLI stack, submission categories, and published judging dimensions of Application of Technology, Presentation, Business Value, and Originality. The public page does not make options mandatory or list P&L as a judging criterion.

- Alpaca Documentation — Trading MCP Server: account, market-data, news, option-chain/Greeks and options-trading capabilities.

- Alpaca Documentation — Options Level 3 Trading / Options Trading Overview: multi-leg option support and defined-risk spread capabilities.

- Alpaca Documentation — Option Chain / Snapshots: option quotes, trades, implied volatility and Greeks availability.

- Alpaca Documentation — Paper Trading: marketability/fill assumptions and limitations of simulated execution.

- Alpaca Skills — Trading API Backtesting: advisory reproducibility, data-fingerprint, fill-model, benchmark, and disclosure patterns. Its V1 reference excludes options, so this project supplies options-specific replay logic.

- Alpaca Skills — Generic/CLI/MCP Paper Trading: advisory Paper-verification, dry-run, idempotency, ambiguous-submit, and lifecycle patterns. The project rejects generic conversational/MCP/CLI write authority; `alpaca-py` behind the deterministic gateway remains the only production order path.

## 24.2 Methodology inspiration sources

- José Luis Cava public educational material/interviews: strength and trend, market breadth, liquidity emphasis, second opportunities/retests, false-signal awareness, stop discipline and systematic execution.

- Gustavo Martínez public material/interviews: liquidity and economic-cycle framing, expectations, valuation discipline, risk/capital preservation and separating structural thesis from short-term market noise.

| **Final design judgment:** The strongest hackathon version is not “Cava + Gustavo as AI personalities” or another generic “LLM trader with guardrails.” It is an auditable execution firewall that shows where model authority ends, compares the model with a deterministic baseline, and proves one evidence-to-intent-to-request-to-reconciliation lifecycle without claiming unearned alpha. |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# Appendix A — Decision policy summary

```json
{
  "candidate": "SPY with an eligible complete option chain",
  "allowed_setups": [
    "trend_continuation_retest"
  ],
  "directional_gate": {
    "mechanical_setup_required": true,
    "minimum_nonduplicative_confirmations": 1,
    "model_confidence_is_calibrated_probability": false,
    "counter_signal_veto": true
  },
  "ai_evaluation": {
    "deterministic_baseline_required": true,
    "measure_evidence_fidelity": true,
    "measure_counter_evidence_and_abstention": true
  },
  "quality_gates": {
    "data_quality": "strict",
    "options_quality": "strict",
    "event_safety": "required",
    "risk_governor": "must_approve"
  },
  "preferred_structures": {
    "bullish": "bull_call_debit_spread",
    "bearish": "bear_put_debit_spread"
  },
  "position_policy": {
    "maximum_open_or_pending_strategies": 1,
    "no_averaging_down": true,
    "thesis_invalidation_persisted": true,
    "time_stop": true,
    "expiry_safety_exit": true
  },
  "default_outcome_when_uncertain": "NO_TRADE"
}
```
