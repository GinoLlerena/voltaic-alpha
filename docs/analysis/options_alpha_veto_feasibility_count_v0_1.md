# Options Alpha — Breadth veto: feasibility count

| Field | Value |
|---|---|
| Date | 12 October 2026, America/Lima |
| Status | **Preliminary: run on the committed bar fixture. The full period and the reference check need a data export the owner has not yet approved (§5).** |
| Plan | [Breadth veto backtest: plan](../improvements/options_alpha_veto_backtest_plan_v0_1.md) §4.0, Step 0B, `VBT-100` |
| Code | `src/options_alpha_lab/veto_study.py`, `tests/test_veto_study.py` |
| Reproduce | `uv run python -m options_alpha_lab.veto_study` |
| Boundary | Counts only. No outcome, price move or return is computed. No rule is changed. |

## 1. Result

On the history already in the repository, the count **passes the screen** with
room to spare.

| Group | Sessions | Clusters | Longest run | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| Bullish structure, opposing breadth below the line | 183 | 31 | 13 | 43 | 85 | 55 |
| Bullish structure, opposing breadth at or above the line | 101 | 27 | 15 | 18 | 62 | 21 |
| Screen, per group | 30 | 10 | | | | |

- 493 completed sessions were measured, 11 September 2024 to 28 August 2026.
- Bullish structure reached 0.60 on 284 of them; bearish structure, out of
  scope, on 41.
- No session in either group carried a veto from another family that can be
  read from daily bars (momentum).

## 2. What this means

- **The option-backed study is worth starting.** Each group has roughly three
  times the screen's sessions and clusters, before the remaining months of
  2024 and September to October 2026 are added.
- **The veto is not rare.** In this period opposing breadth reached the line on
  about a third of the sessions where bullish structure passed (101 of 284).
- **The numbers will shrink.** They are an upper bound. The full rule also
  needs a confirmation, and a stressed-volatility reading can veto. Entry-time
  option data will be missing for some sessions, and the chronological
  portfolio in the plan's §5.5 takes at most one position at a time. A run of
  13 qualifying sessions is at most a handful of trades.
- **Clusters are the better guide.** About 30 separate episodes per group is
  the realistic size of the evidence, not 183 or 101.

This says nothing about whether the veto helps. No outcome was measured.

## 3. Method

For each completed session the script builds the window the worker would have
had (bars up to that session, within the worker's 400-day lookback) and calls
the real `build_signals` with no implied volatility. It records whether a
bullish structure signal reaches 0.60 and whether opposing breadth reaches
0.70. A cluster is a set of member sessions with fewer than three sessions
between neighbours.

**Why it is an upper bound.** Supplying volatility later can only remove
sessions. `test_veto_study.py` checks this against the shipped classifier on
every session in the fixture, at a calm, a middle and a stressed volatility:
the classifier never qualifies a bullish setup outside the "below the line"
group, and never qualifies anything in the "at or above" group.

Other tests cover: no row uses a later bar; the window is the bounded 400 days
and not the whole series; the 0.70 line itself counts as at or above; a veto
from another family is reported separately.

## 4. Data

| Field | Value |
|---|---|
| File | `fixtures/h0/sensitivity_bars.json` (committed) |
| SHA-256 | `69a79a590ddac05fb68c1687a68db13d438dc6cab1967552e3a04636d22fb5f3` |
| Provider, feed | Alpaca, SIP, fetched 31 August 2026 |
| Coverage | SPY and RSP, 562 sessions each, 3 June 2024 to 28 August 2026 |
| First counted session | 11 September 2024, after the 70-bar minimum |

## 5. What is still missing

1. **The full option-data period.** February to August 2024 and 29 August to
   October 2026 are not in the fixture. Earlier bars are also needed so that
   sessions from February 2024 have their warm-up.
2. **The reference check.** The plan requires the count to agree with the
   bot's stored signals for 22 September to 9 October 2026. The fixture ends
   before that, so this check has not been run.
3. **Feed.** The fixture is SIP. The feed the live worker uses has to be
   recorded and matched, or the difference stated.

All three need one read-only export from the server: SPY and RSP daily bars
from 2023 onward with the worker's own settings, and the stored signals for
the reference interval. The plan (§9, decisions 4 and 11) requires the owner
to approve that export explicitly. It has not been run.

## 6. Recommendation

Go: continue to Step 1 of the plan once the export is approved and the two
checks above pass. The preliminary result is large enough that the missing
months cannot turn a pass into a fail; the reference check can still show the
replay is wrong, and that would stop the work.
