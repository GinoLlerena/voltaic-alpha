# Threshold sensitivity

Generated 2026-08-31T20:00:38.775874+00:00.

**decision sensitivity, not outcome sensitivity.** This says which thresholds are close to changing decisions. It says nothing about whether any threshold is profitable: that needs many trades with known results, and this system has taken one. DEC-008 stays open.

## structure

Outcome measured: the full signal set at each of the last 120 completed sessions: structure direction, confirmers and opposers.

| Threshold | Current | Unchanged over | Share of outcomes changed by ±10% | Distinct outcomes | |
|---|---|---|---|---|---|
| `evidence.MIN_EMA_SEPARATION` | 0.002 | 0.002 – 0.003 | 0.0% | 30 |  |
| `evidence.RETEST_TOLERANCE` | 0.01 | 0.01 – 0.01 | 2.5% | 20 |  |
| `evidence.RETEST_LOOKBACK_SESSIONS` | 5 | 5 – 5 | 0.0% | 9 |  |
| `evidence.FAST_EMA` | 20 | 20 – 20 | 11.7% | 34 | **fragile** |
| `evidence.SLOW_EMA` | 50 | 50 – 63 | 0.8% | 16 |  |
| `evidence.PARTICIPATION_SESSIONS` | 10 | 10 – 10 | 49.2% | 59 | **fragile** |
| `evidence.MIN_PARTICIPATION_DIVERGENCE` | 0.002 | 0.002 – 0.0025 | 0.0% | 29 |  |
| `evidence.MOMENTUM_SHORT_SESSIONS` | 5 | 5 – 5 | 0.0% | 19 |  |
| `evidence.MOMENTUM_LONG_SESSIONS` | 20 | 10 – 60 | no flip across 10–60 | 1 |  |

## decision

Outcome measured: decided action on each of 5 committed snapshots.

| Threshold | Current | Unchanged over | Share of outcomes changed by ±10% | Distinct outcomes | |
|---|---|---|---|---|---|
| `components.MIN_STRUCTURE_STRENGTH` | 0.6 | 0.3 – 0.65 | 40.0% | 4 | **fragile** |
| `components.MIN_CONFIRMATION_STRENGTH` | 0.5 | 0.2 – 0.61 | 0.0% | 4 |  |
| `components.CONTRADICTION_VETO_STRENGTH` | 0.7 | 0.35 – 1 | 0.0% | 3 |  |
| `components.MIN_DTE` | 14 | 9 – 22 | 0.0% | 3 |  |
| `components.MAX_DTE` | 45 | 22 – 120 | 0.0% | 2 |  |
| `components.MAX_RELATIVE_QUOTE_SPREAD` | 0.25 | 0.03 – 0.8 | 0.0% | 2 |  |
| `components.LONG_DELTA_BAND[low]` | 0.55 | 0.3 – 0.56 | 20.0% | 4 | **fragile** |
| `components.LONG_DELTA_BAND[high]` | 0.7 | 0.66 – 0.95 | 20.0% | 2 | **fragile** |
| `components.SHORT_DELTA_BAND[low]` | 0.25 | 0.05 – 0.38 | 0.0% | 2 |  |
| `components.SHORT_DELTA_BAND[high]` | 0.4 | 0.27 – 0.7 | 0.0% | 2 |  |
| `components.MAX_DEBIT_TO_WIDTH` | 0.6 | 0.54 – 0.95 | 0.0% | 4 |  |
| `components.MIN_WIDTH_FRACTION_OF_SPOT` | 0.005 | 0.0005 – 0.0155 | 0.0% | 5 |  |
| `components.RISK_FRACTION_OF_EQUITY` | 0.0075 | 0.00475 – 0.02 | 0.0% | 5 |  |
| `components.EXECUTION_ALLOWANCE_FRACTION` | 0.5 | 0 – 2 | no flip across 0–2 | 1 |  |

## Fragile thresholds

A ±10% move changes more than 10% of outcomes for: `evidence.FAST_EMA`, `evidence.PARTICIPATION_SESSIONS`, `components.MIN_STRUCTURE_STRENGTH`, `components.LONG_DELTA_BAND[low]`, `components.LONG_DELTA_BAND[high]`. These are the numbers most in need of the evidence `DEC-008` and `DEC-010` still owe.

## Inert thresholds

No outcome anywhere in the swept range depends on these. That is not the same as robust - it means the constant is dead, or the path it governs was never exercised by this evidence:

- `evidence.MOMENTUM_LONG_SESSIONS` — inert, and the sweep is how that was found: `long_return` is computed in `build_signals` and never read, so the trigger is `short_return` against the trend alone. The signal is named divergence and compares nothing
- `components.EXECUTION_ALLOWANCE_FRACTION` — added 31 August; signal spec section 7.1

## Not covered

- `evidence.CALM_ATM_IV / evidence.STRESSED_ATM_IV` — Implied volatility is not in the daily bar history, and the committed snapshots carry their signals precomputed, so neither sweep can reach these. Covering them needs a historical option chain, which this project does not hold.

- `components.EXECUTION_ALLOWANCE_FRACTION` — Swept, but every committed snapshot quotes far tighter than the live indicative feed - 0.20 wide against the 0.45 to 0.90 seen on 31 August - so the allowance never approaches the budget on this evidence and reports no flip. Read that as the fixtures being unrepresentative here, not as the threshold being robust.
