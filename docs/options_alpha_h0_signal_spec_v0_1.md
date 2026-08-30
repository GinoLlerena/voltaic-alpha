# Options Alpha Agent

## H0 Signal, Feed, and Benchmark Specification

| Field | Value |
|---|---|
| Version | v0.1 |
| Phase | 2 |
| Status | Frozen for H0. Every numeric value is `PROVISIONAL` until replay evidence is attached |
| Closes | `CLR-016` (signal specification), `CLR-015` (feed policy), part of `CLR-010` |
| Implemented in | `src/options_alpha_lab/evidence.py`, `src/options_alpha_lab/components.py` |

## 1. Why this document exists

`CLR-016` records that signal concepts were described but formulas, timeframes,
lookbacks, thresholds, and freshness were not. An unspecified signal cannot be
falsified, and a system whose entry rule lives only in code is one refactor away
from meaning something different. This document states the rule precisely enough
that someone could disagree with it.

## 2. Data inputs

| Input | Endpoint | Feed | Notes |
|---|---|---|---|
| Account | `GET /v2/account` | paper-trading | Equity and options buying power. Never a constant (`CLR-007`) |
| Clock | `GET /v2/clock` | paper-trading | Determines whether the current session is still forming |
| Daily bars | `GET /v2/stocks/{symbol}/bars` | `sip` when entitled, else `iex` | `start` is mandatory; without it Alpaca returns only the current session |
| Option chain | `GET /v1beta1/options/snapshots/{symbol}` | `opra` when entitled, else `indicative` | Pagination exhausted, never truncated |

Entitlement is **discovered at runtime**, not configured. `DEC-006` was resolved
on 28 August 2026 by direct probe: the account returns
`403 OPRA agreement is not signed`, so H0 runs on the **indicative** feed, and
`sip` is available for equity bars. An account that later signs OPRA tightens its
freshness policy without a code change.

## 3. Look-ahead protection (normative)

1. Only **completed** sessions contribute. While `clock.is_open` is true, the bar
   dated to the current session is discarded.
2. An option quote timestamped **after** the decision instant is discarded, not
   clamped.
3. `DecisionSnapshot` rejects any signal or quote newer than its own `as_of`, so
   a violation raises rather than producing a subtly optimistic decision.

Rule 1 is the one that matters. Acting on a forming bar is the most common way a
backtest lies to its author, and it does not announce itself.

## 4. Freshness policy (normative, feed-specific)

| Input | Tolerance | On breach |
|---|---|---|
| Account | 30 s | `stale_fields` entry, decision terminates |
| Clock | 60 s | `stale_fields` entry, decision terminates |
| Daily bars | last completed session within 5 calendar days | `stale_fields` entry |
| Option quote, `opra` | 30 s | contract excluded |
| Option quote, `indicative` | 120 s | contract excluded |

No input is ever replaced by a default, a last-known-good value, or an
interpolation. A missing value is a reason to decline, never a reason to guess.

## 5. The setup: SPY trend continuation with retest

Direction qualifies only when **all** of the following hold on completed daily
bars:

| Component | Rule | Provisional value |
|---|---|---|
| Trend | `EMA(fast)` separated from `EMA(slow)` by at least `MIN_EMA_SEPARATION`, as a fraction of `EMA(slow)` | fast 20, slow 50, separation 0.002 |
| Location | Last close on the trend side of `EMA(fast)` | — |
| Retest | Within the last `RETEST_LOOKBACK_SESSIONS`, price traded to within `RETEST_TOLERANCE` of `EMA(fast)` and did not close through it | 5 sessions, 1.0% |
| History | At least `SLOW_EMA + MOMENTUM_LONG_SESSIONS` completed bars | 70 |

`strength = clamp(0.55 + 8 × |separation|, 0, 1)`.

The retest condition is what separates this from "buy an uptrend". Without it the
setup has no defined entry location, and its invalidation level would be
arbitrary.

## 6. Confirmation and counter-evidence

`CLR-010` warns against calling several transformations of one price series
independent. H0 therefore takes its confirmation from a **different instrument**:

| Signal | Family | Source | Rule |
|---|---|---|---|
| Volatility regime | `volatility_options` | ATM implied volatility from the option chain | Aligned when IV ≤ 0.22; opposes when IV ≥ 0.32; silent between |
| Participation breadth | `participation` | `RSP` (equal-weight S&P 500) against the cap-weighted index, 10 completed sessions | Bullish when the ratio rises, bearish when it falls, silent inside ±0.002 |
| Momentum divergence | `momentum` | 5-session vs 20-session return | Opposing signal when the short-horizon return runs against the trend |

The volatility signal is derived from the option market's own pricing, not from
the bars that produced the structure signal. The momentum signal exists only to
generate **counter-evidence**; it can never qualify a setup on its own.

**Breadth, added 30 August 2026.** `SPY` is cap-weighted and `RSP` holds the same
500 companies equally, so the ratio between them answers the question breadth is
actually asking: is the average constituent participating, or is a shrinking
group of large names carrying the move? A rising ratio is broad strength and a
falling ratio is narrow. It is a different instrument rather than another
transformation of `SPY`'s own price, which is what `CLR-010` requires.

Three properties are deliberate. Sessions pair **by date, not by position**,
because the two series can disagree about which days exist and index pairing
would silently compare different days. Movement inside the noise band emits
**nothing** rather than a neutral signal, so an unmeasured signal cannot be
mistaken for a considered one. And breadth is **optional everywhere**: an
unreadable `RSP` read costs the setup one possible confirmer and never fails a
decision, because an outage on a second symbol must not halt the strategy on the
first.

The ten-session window and the ±0.002 band are `PROVISIONAL`. On 28 August
closes the same series read −0.00034 over ten sessions, −0.00912 over five and
+0.03396 over sixty; the window length changes the answer, which is precisely
why it needs sensitivity evidence before anyone calls it approved.

A qualified setup requires structure **plus** at least one aligned signal from a
different family. An opposing signal at strength ≥ 0.70 vetoes the setup outright,
before thesis synthesis is reached.

## 7. Option eligibility (normative)

| Check | Provisional value | Behaviour when unavailable |
|---|---|---|
| DTE band | 14–45 | excluded |
| Quote integrity | two-sided, non-crossed, relative spread ≤ 25% | excluded |
| Long delta | 0.55–0.70 by magnitude | **excluded**: a missing delta fails closed |
| Short delta | 0.25–0.40 by magnitude | **excluded** |
| Minimum width | ≥ 0.5% of spot | excluded |
| Debit / width | ≤ 0.60 | excluded |

Selection is deterministic: among eligible pairs, prefer the **narrowest** width
(smallest maximum loss), then the lowest debit/width ratio, then the lowest long
strike. Ties cannot depend on the order the chain arrived in.

The minimum-width rule was added after the first live run selected a $1-wide
spread on a $771 underlying at 63% of width. The pair passed every other check
and was still a bad structure: the debit swamped the achievable gain.

## 8. Price-only benchmark

The benchmark is deliberately trivial, because a benchmark exists to be hard to
beat by accident, not to be impressive:

> **Benchmark B0.** Buy and hold SPY over the same decision horizon, sized to the
> same maximum loss, with the same friction assumptions.

Any claim that this system adds value is a claim that it beats B0 after costs. A
strategy that produces fewer, more explainable trades while underperforming B0 is
a strategy with better auditing and no edge, and it must be reported that way.

## 9. Null hypothesis (normative)

> **H₀.** The SPY trend-continuation/retest setup has no advantage over B0 after
> friction, and the bounded model memo does not improve decisions over the
> deterministic baseline.

H₀ is the **default assumption** of this project and is not rejected by H0. One
qualified case and one refusal are an existence proof of the mechanism, not
evidence about returns. The sample is far too small to reject H₀, and no artifact
— deck, video, README, or dashboard — may imply otherwise.

Rejecting H₀ would require, at minimum: a pre-registered decision horizon, a
sample large enough to survive multiple-comparison correction, out-of-sample
replay across regimes, and friction measured from actual fills rather than
assumed. None of that fits in a seven-day build, which is exactly why the
project's claim is auditability rather than alpha.

## 10. What would falsify the mechanism claim

The mechanism claim — that the model cannot influence direction, invalidation,
sizing, eligibility, or execution — is falsified if any of these is ever observed:

1. A decision where `thesis.direction` differs from `setup.direction` and the
   outcome is not `NO_TRADE`.
2. A decision where `thesis.invalidation_conditions` differ from the setup's.
3. An approved maximum loss exceeding the computed risk budget.
4. A spread whose recomputed maximum loss disagrees with the recorded one.
5. Any order request whose hash does not match its approved intent.

Each has a test. Items 1–4 are enforced today; item 5 arrives with Phase 4.
