# Options Alpha — Setup and exit study, Part B: the fixed alternatives

| Field | Value |
|---|---|
| Date | 5 November 2026, America/Lima |
| Plan | [Setup and exit study plan](../improvements/options_alpha_setup_exit_study_plan_v0_1.md), §4, measured as fixed in §4.1 on 5 November 2026 (commit `b04da6a`), before computing |
| Inputs | The Part 2 entries, exit paths and cost cases, unchanged. The current rules reproduce the Part 2 trades digest `sha256:59d5e170cb6a564e27ea09c35dbb992e38c6e399ed9040f656de223112dc8fa7`. B5: its own entries and `paths_dte21/` (manifest digest `sha256:75b8f854…`) |
| Code | `src/options_alpha_lab/study_variants.py`; run `uv run python -m options_alpha_lab.study_variants` |
| Status | **Exploratory.** No variant passes the reading rule. No trading rule changes |

## 1. Summary

**None of the alternatives is a candidate.** Four were computed and none clears
the reading rule. B4 was not run, by the owner's decision. B1's five-session
stop was not run for lack of data (§4). This is the result Part A predicted:
changing an exit changes how much is lost, not whether money is lost, because
the setup does not pick sessions that are followed by a rise.

| Variant | Mean change per trade against today, central [95%] | Rule met? |
|---|---|---|
| B1, session stop 2 | +2.17 [−17.18, +16.12] | no |
| B1, session stop 5 | not run: data (§4) | — |
| B2, profit target 30% | −1.71 [−12.51, +8.40] | no |
| B3, no stop loss | +4.38 [−0.69, +12.37] | no |
| B4, entry 11:00 | not run: owner | — |
| B5, 21–45 days to expiry | −13.80 [−27.04, −0.44] (47 shared sessions) | no |

Under every variant the strategy's own mean stays negative in the central and
pessimistic cases.

## 2. How it is read

As fixed in §4.1: each variant changes one shipped constant for the run, and
everything else stays as in Part 2. The comparison is per session: the variant's
result minus today's, on the same Permitted session and cost case, with the
frozen moving-block interval (10,000 replicates, seed 20261012, 95%) at block
10, and again at 5 and 20. A variant is a candidate only if:

1. the lower end of the interval is above zero at block 10, in the central
   **and** pessimistic cases;
2. the same holds at blocks 5 and 20;
3. its one-position portfolio ends higher in all three cost cases.

The rule is written for six comparisons. Running four of them makes it
stricter, not looser.

## 3. Numbers

Today's rules, Permitted, 84 trades, none unresolved. Mean per spread in USD:
optimistic −20.32 [−50.99, +12.19], central −29.64 [−60.09, +2.69],
pessimistic −39.79 [−67.67, −8.40]. One-position portfolio total:
−927.89, −1,478.12 and −1,821.34.

### B1, session stop at 2 sessions (today 3)

| Case | Own mean | Change against today | Blocks 5 / 20 | Portfolio (today) |
|---|---|---|---|---|
| Optimistic | −18.40 | +1.92 [−17.56, +15.79] | [−17.34, +16.84] / [−18.81, +15.56] | −817.64 (−927.89) |
| Central | −27.46 | +2.17 [−17.18, +16.12] | [−17.19, +17.30] / [−18.49, +15.88] | −1,347.62 (−1,478.12) |
| Pessimistic | −37.48 | +2.31 [−17.24, +16.09] | [−16.75, +17.07] / [−18.51, +15.63] | −1,538.85 (−1,821.34) |

84 closed: 71 session stops, 9 stop losses, 4 invalidations (central). The
portfolio ends higher in all three cases. The interval is about ±$17 around
+$2. **Not a candidate (condition 1).**

### B2, profit target at 30% of maximum gain (today 60%)

| Case | Own mean | Change against today | Blocks 5 / 20 | Portfolio (today) |
|---|---|---|---|---|
| Optimistic | −20.96 | −0.64 [−11.51, +8.09] | [−11.59, +8.99] / [−11.55, +7.95] | −1,410.08 (−927.89) |
| Central | −31.34 | −1.71 [−12.51, +8.40] | [−12.76, +8.97] / [−12.92, +8.11] | −1,917.26 (−1,478.12) |
| Pessimistic | −41.52 | −1.73 [−11.21, +7.55] | [−11.72, +8.39] / [−11.47, +7.52] | −2,322.65 (−1,821.34) |

The target now fires on 26 trades instead of 1 (central), but it does not
help. Part A found the target fills about $33 below the reading that triggered
it. Capping the winners while leaving the losers unchanged makes the portfolio
worse in every case. **Not a candidate (conditions 1 and 3).**

### B3, no stop loss (today 50% of the debit)

| Case | Own mean | Change against today | Blocks 5 / 20 | Portfolio (today) |
|---|---|---|---|---|
| Optimistic | −15.69 | +4.63 [+0.01, +12.22] | [−0.02, +12.02] / [+0.04, +12.74] | −764.82 (−927.89) |
| Central | −25.26 | +4.38 [−0.69, +12.37] | [−0.79, +12.11] / [−0.75, +13.03] | −1,294.82 (−1,478.12) |
| Pessimistic | −35.26 | +4.53 [−2.57, +13.63] | [−2.22, +13.33] / [−2.69, +14.15] | −1,824.82 (−1,821.34) |

The closest of the four. Without the stop, trades that would have stopped out
mostly run to the session stop (75 of 84, central) and lose a little less on
average. The lower end clears zero only in the optimistic case, by a cent, and
the pessimistic portfolio ends $3.48 lower. **Not a candidate (conditions 1
and 3).** The strategy's own mean is still negative.

### B5, 21–45 days to expiry (today 14–45)

| Case | Own mean (n) | Change against today, 47 shared sessions | Blocks 5 / 20 | Portfolio (today) |
|---|---|---|---|---|
| Optimistic | −13.63 (120) | −11.39 [−24.89, +2.10] | [−25.09, +1.91] / [−25.39, +2.00] | −11.46 (−927.89) |
| Central | −24.25 (120) | −13.80 [−27.04, −0.44] | [−27.22, −0.79] / [−27.77, −0.34] | −805.84 (−1,478.12) |
| Pessimistic | −35.31 (120) | −15.47 [−28.57, −2.22] | [−28.44, −2.51] / [−29.84, −2.27] | −1,380.81 (−1,821.34) |

121 entries, one unresolved (triggered, then no later bar in which both legs
traded). On the sessions both versions traded, B5 is **worse**: its interval
lies below zero in the central and pessimistic cases at every block length.
Its own mean and its portfolio look better only because it trades a different
set of sessions (next section). **Not a candidate (condition 1).**

### Context, not in §4.1: why B5 trades different sessions

These lines were added after seeing B5's result, to explain it. They are
descriptive.

- Of 241 Permitted sessions, today's rules enter 84 and B5 enters 121. Only 47
  sessions are entered by both. 37 are entered by today's rules only, and 74
  by B5 only.
- The cause is mostly the fill rule, not the expiry. Of the 37 today-only
  sessions, B5's legs did not both trade in the 10:00–10:05 bar on 35. Of the
  74 B5-only sessions, today's legs did not both trade in that bar on 41, and
  today's selector found no eligible pair on 27.
- Central means: on the 47 shared sessions, today −26.32 and B5 −40.12. On the
  sessions only one version traded, today −33.85 (37) and B5 −14.04 (73).
- Median days to expiry at entry: 14 today, 23 under B5. Estimated debit over
  width: 0.558 today, 0.567 under B5.

So B5's better-looking total is a session-mix effect: which sessions happen to
have both legs trading at 10:00. On matched sessions, the longer expiry lost
more. Part A's idea that slower time decay would help is not supported here.

## 4. What was not run

- **B4, 11:00 entry:** the owner decided on 26 October not to download for it,
  after Part A found nothing wrong at the entry.
- **B1, session stop at 5:** the shipped policy counts *completed* sessions,
  so a five-session stop fires at the first observation of the **sixth**
  session. Every downloaded window ends after the fifth (147 of 149 trades
  exactly, the other two at six and seven). The plan's 31 October note was
  wrong to say no download was needed; §4.1 corrects it. Running it needs the
  next two sessions of each of the 84 Permitted trades' legs (two, to leave
  the same room for the exit fill that a three-session stop has). That is 84
  read-only requests, about 15 minutes and under 1 MB, in a `session.py`
  session outside market hours, with the owner's approval.

Given B1 at 2 and Part A's finding that the value falls about $24 a session
while held, a longer hold is unlikely to clear the rule. But the plan says
results are computed, not guessed.

## 5. Limits

- Same data as Part 2, so every Part 2 limit applies, including values rebuilt
  from 5-minute bars and synthetic quotes.
- Four comparisons were run on data already seen. A variant that passed would
  still only be a candidate for Paper testing.
- B5's comparison uses the 47 shared sessions only. Its sessions are not a
  random sample: they are those where both versions' legs traded at 10:00.

## 6. What it means

No exit or expiry change on the list turns the result positive, and none
passes the rule. In line with Part A, the loss comes from the entry signal's
lack of follow-through, not from the exits. **This study recommends no change
for Paper testing.** The next useful question is about the setup itself: why
sessions the trend-retest rule permits are not followed by a rise. That would
be a new plan, written before anything is computed.

Decisions for the owner:

1. Approve the B1 (5) download, sized above, to close the list? Recommended:
   yes. It is cheap, and it makes the list complete as written.
2. Close Part B with "no candidate" once B1 (5) is in, and keep Paper armed
   with today's rules? Recommended: yes.
