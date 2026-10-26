# Options Alpha — Setup and exit study: plan (draft for the owner)

| Field | Value |
|---|---|
| Date | 23 October 2026, America/Lima |
| Status | **Approved by the owner, 26 October 2026, after seeing Part A** (see §7). §4 is frozen from that date. An earlier approval recorded on 24 October was a mistake and is withdrawn (§7) |
| Why | [Veto backtest Part 2](../analysis/options_alpha_veto_backtest_part2_v0_1.md): in simulation, the strategy's average trade is negative in every cost case (central: −$29.64 a trade over 84 Permitted trades). Three in four trades end on the session stop; the profit target was reached 5 times in 149 |
| Boundary | Offline research only. No trading rule, threshold or worker setting changes. Any change found here needs its own proposal, review and Paper testing |

## 1. The question

Does the bullish trend-retest debit spread, as the bot trades it, have a
positive expectation? If not, is that because of the entry, the exits, or
costs?

Part 2 answered only whether the breadth veto mattered. It did not ask
whether the strategy works. Its numbers suggest it may not:

| Central case, independent setups | Permitted | Breadth-vetoed |
|---|---:|---:|
| Mean result per spread | −$29.64 | +$5.98 |
| Ended by the session stop | 64 of 84 | 54 of 65 |
| Ended by the profit target | 1 | 4 |

## 2. The problem with answering it from the same data

Every trade from February 2024 to October 2026 has now been seen. Any exit
rule chosen because it does better on those trades is fitted to them, and
its result will look better than it is. Historical option data from the
provider starts in February 2024, so there is no older period to hold out.

So this plan does three things:

1. **Explains** the current result, with no rule changed (§3). This is fair
   to do on seen data, because nothing is chosen.
2. **Tests a small fixed list of alternatives**, written down here before
   any is computed (§4). This is explicitly exploratory: no variant is
   called better on this data alone.
3. **Confirms forward**, on Paper, only what the owner then chooses to
   propose (§5).

## 3. Part A: decompose the current result (no rule changed)

From the Part 2 trades and paths already cached. No new download.

- **Where the money goes:** the entry debit against the value at each of
  the first three closes, per trade. Is the loss already there at the first
  close (a poor entry), or does it build later (time decay, poor exits)?
- **Cost of the exit delay:** the value at the trigger observation against
  the actual fill, for the 48 of 149 exits that waited two bars or more.
- **Time decay against direction:** SPY's 3-session move (Part 1) against
  the spread's result. How much of the loss is theta on days SPY went
  nowhere?
- **Entry price:** the fill reference `P` against the bot's estimated
  debit, and the debit-to-width ratio against the result.

These are descriptions with intervals, not tests.

### 3.1 Part A definitions (fixed 24 October 2026, before computing)

Inputs: the Part 2 entries, trades and exit paths, unchanged (trades digest
as in the Part 2 report). Every figure is per spread, in USD, for each of the
three cost cases; the report leads with the central case. Groups: Permitted
(the bot's rule), Breadth-vetoed, and both together. Unresolved trades are
left out of result means and counted, as in Part 2.

- **A1, value at the closes.** For each entered trade with a path, the
  spread's value at the close of the entry session (`C0`) and of the next two
  sessions (`C1`, `C2`): the long leg's minus the short leg's newest trade
  bar, each at most 15 minutes old and at most 10 minutes apart (the Part 2
  rule), less the case's friction. Change = (value − entry debit) × 100. The
  value is read whether or not the trade had already exited: it describes the
  spread's path, not the trade. A close at which the value cannot be measured
  is left out for that close, and counted.
- **A2, exit delay.** For each closed trade: the delay in observations from
  the trigger to the fill, and the cost of waiting = (exit value − value at
  the trigger observation) × 100, both values less friction. A trigger whose
  value could not be measured (a session stop can fire without one) is left
  out, and counted. Reported for all closed trades and for delays of two
  observations or more, and by trigger.
- **A3, direction against time decay.** Part 1's SPY 3-session move
  (`C[-1]` to `C[2]`, %) for each trade's session. The trades of a group are
  split into thirds by that move alone (cut points from the moves, not from
  the results); the mean result is reported for each third.
- **A4, entry price.** (`P` − estimated debit) × 100 per trade, and the
  share of trades with `P` above the estimate. The entry debit (with
  friction) over the width, split into thirds the same way, with the mean
  result per third.

Intervals: the frozen Part 2 bootstrap (moving blocks of 10 over the
chronological sequence of replayed sessions, 10,000 replicates, seed
20261012, percentile 95%), applied to a single mean, with the sessions
outside the subset as gaps. Nothing in Part A is a test, and no rule is
chosen from it.

## 4. Part B: a fixed list of alternatives (exploratory)

Each variant changes **one** rule and keeps every other rule and data input
of Part 2. The list is closed: no variant is added after a result is seen.

| # | Variant | Today | Alternative | Why this one |
|---|---|---|---|---|
| B1 | Session stop | 3 sessions | 2 and 5 | the main exit; both directions |
| B2 | Profit target | 60% of max gain | 30% | reached 5 times in 149 at 60% |
| B3 | Stop loss | 50% of the debit | none | does the stop help, or cut trades that recover? |
| B4 | Entry time | 10:00 | 11:00 | after the opening noise; legs trade more |
| B5 | Days to expiry | 14–45, nearest | 21–45, nearest | less time decay per day |

For each one, report the same tables as Part 2: independent trades for
Permitted sessions only (the bot's rule), the three cost cases, the
moving-block bootstrap, and the one-position portfolio. The statistics are
the frozen Part 2 settings.

**Reading rule, fixed now.** Six alternatives are compared. If none truly
helped, the chance that at least one 95% interval excludes zero anyway is
about one in four (1 − 0.95⁶). A variant counts as worth a proposal only if all of these hold:

- the lower end of its 95% interval against the current rules is above
  zero in the central **and** pessimistic cases;
- it holds at block lengths 5, 10 and 20;
- its one-position portfolio is better in all three cost cases.

A variant that meets this is a candidate for Paper testing (§5), not a
change.

B4 and B5 need a new download: chains at 11:00, and chains for the longer
expiries. Each needs the owner's separate approval, sized like the 23 October
download.

## 5. Part C: forward confirmation (only if the owner proposes a change)

The only data not yet seen is the future. A candidate from Part B would run
on Paper next to the current rules: one live, the other shadow-logged, or
alternating by week. A fixed number of trades is set in advance, at least
30 on each side. Its design would be a separate document.

## 6. What this will not do

- No search over thresholds, and no combining of variants.
- No change to the breadth veto (the veto study is closed), the setup
  classifier, or the risk budget.
- No paid model calls; the baseline thesis only, as in Part 2.
- No claim of profitability from simulated results. Paper fills are the
  evidence.

## 7. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| 1 | Run Part A (decomposition, cached data, no rule changed)? | Yes: cheap, and it says where the loss comes from |
| 2 | Approve Part B's list and reading rule as written, before anything is computed? | Yes, or edit the list now. It cannot change after |
| 3 | B4 and B5 need new downloads. Approve now, or decide after Part A? | After Part A: it may show they are not needed |
| 4 | Keep Paper armed meanwhile? | Yes. It costs no money and it is the only source of real fills |

**Correction, 24 October 2026.** An approval of decisions 1 to 3 was
recorded here, and merged in #106, from a misread instruction: the owner's
"Proceed from 1 to 3" referred to three backlog items, not to this table. The
owner has not answered §7. Part A was computed on that misreading, with its
definitions fixed in §3.1 before computing. If the owner now edits §4, the
edit is made after Part A was seen, and must say so. Paper stays armed, as it
is.

Approval of this document freezes §4. A later change needs a dated note
saying what changed and why, made before the affected results are computed.

**Approval, 26 October 2026.** The owner approved this plan, answering the
four decisions above with the recommendations, and decision 3 with the
recommendation Part A made: download for B5, not for B4. The owner saw Part A
first. §4 is not edited: B4 stays on the list and is reported as not run, and
the reading rule stays written for six comparisons, which is stricter for
five. B5's download is sized and shown to the owner before it is run, as §4
requires. Paper stays armed.
