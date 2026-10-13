# Options Alpha — Breadth veto: calibration and parity gates

| Field | Value |
|---|---|
| Date | 13 October 2026, America/Lima |
| Status | **The reconstruction passes the three parity gates on the calibration sessions.** The historical download for the full period has not run yet. |
| Protocol | [Numeric protocol](../improvements/options_alpha_veto_backtest_protocol_v0_1.md) §2, §3, §4, §7 |
| Code | `src/options_alpha_lab/veto_reconstruction.py`, `veto_pricing.py`, `veto_calibration.py` |
| Reproduce | `uv run python -m options_alpha_lab.veto_reconstruction` |
| Boundary | Prices and stored quotes only. No trade outcome is computed. No rule is changed. |

## 1. Result

The study rebuilds implied volatility and delta from traded option prices,
because the provider keeps no history of either. The bot's stored snapshots
are the only place the rebuilt values can be compared with observed ones.

| Gate (protocol §7) | Result | Needed | |
|---|---|---|---|
| At-the-money volatility within 0.010 of the stored value | 13 of 13 sessions | 90% | passes |
| Delta within 0.03 of the stored value, calls in the two delta bands | 1,220 of 1,263 contracts (96.6%) | 90% | passes |
| Same calm / neither / stressed class | 13 of 13 sessions | all | passes |

The fourth check in §7, replaying the classifier from the stored snapshots,
belongs to Step 2 and is not done here.

| Session | Stored | Rebuilt | Error |
|---|---:|---:|---:|
| 22 Sep | 0.1118 | 0.1122 | +0.0004 |
| 23 Sep | 0.1006 | 0.1006 | +0.0000 |
| 24 Sep | 0.1110 | 0.1117 | +0.0007 |
| 25 Sep | 0.1129 | 0.1091 | −0.0038 |
| 28 Sep | 0.1154 | 0.1170 | +0.0016 |
| 29 Sep | 0.1277 | 0.1262 | −0.0015 |
| 30 Sep | 0.1207 | 0.1208 | +0.0001 |
| 1 Oct | 0.1318 | 0.1240 | −0.0078 |
| 2 Oct | 0.1089 | 0.1173 | +0.0084 |
| 5 Oct | 0.1190 | 0.1189 | −0.0001 |
| 6 Oct | 0.1217 | 0.1227 | +0.0010 |
| 7 Oct | 0.1028 | 0.1046 | +0.0018 |
| 8 Oct | 0.1020 | 0.0988 | −0.0032 |

On every session the rebuilt reading came from the same contract as the bot's
own: the nearest-expiry call at the strike nearest the previous close. The
absolute delta error has a median of 0.011, a 90th percentile of 0.022 and a
largest value of 0.047.

## 2. What this does and does not show

- **The method works where it can be checked.** In this sample the rebuilt
  at-the-money volatility is within one volatility point of the bot's on every
  session, and it never changes which side of a threshold the reading is on.
- **It is a calibration, not a validation.** The sample is 13 sessions in one
  calm stretch, with volatility between 0.10 and 0.13. The calm threshold is
  0.22 and the stressed one 0.32, so no session here was near either. An error
  of 0.008 would matter for a reading close to a threshold; this sample cannot
  say how often that happens.
- **Coverage is the larger limit for Part 2.** Of the 2,271 stored call quotes
  in the two delta bands, 1,263 (56%) had a trade in the 15 minutes before the
  decision. The rest cannot be priced, so the rebuilt chain offers the spread
  selector fewer legs than the bot really had. That biases Part 2 towards the
  more heavily traded strikes and has to be reported with its results.
- **The dividend yield matters little here.** At 0.7% the gates give 13 of 13,
  96.1% and 13 of 13; at 1.7% they give 12 of 13, 96.4% and 13 of 13.

## 3. Inputs

| Input | Content |
|---|---|
| `decision_snapshots.json` | one stored snapshot a session, 22 September to 8 October 2026, the first at or after 10:00 New York |
| `options/<session>.json` | 5-minute option trade bars, 09:45 to 10:05 New York, for the same 13 sessions |
| `spy_5min_open.json` | SPY 5-minute bars opening 09:30 to 10:00 New York, 2 January 2024 to 13 October 2026 |
| `DGS3MO.csv` | the 3-month Treasury yield, FRED |

The quote half-width `k` was measured from the same snapshots and frozen at
0.6224% (protocol §11).

Two readings the protocol left to the implementation, both in the module's
header: the underlying price is the volume-weighted price of SPY's bar over
the same five minutes as the option bar, and a bar's age is measured from its
end.

## 4. Observations from the trial download

Nineteen sessions were fetched as a trial of the export tool, about 18 seconds
and 10 to 42 requests each.

- **2 February 2024 returned no option trade at all** in the window, although
  850 contracts were listed and the sessions on either side returned about 190
  traded contracts each. It looks like a gap at the provider. The full
  download will show whether there are more; each is an unmeasurable session,
  counted and not filled.
- About a quarter to a third of the listed contracts trade in the window. The
  rest have no price.

## 5. Next

Run the full download (about 676 sessions), then report coverage and
exclusions across the whole period. That report is the plan's Step 1 stop
point, for the owner's review, before Step 2.
