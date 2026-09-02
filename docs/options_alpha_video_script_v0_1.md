# Options Alpha

## Submission Video Script (MP4, 5 minutes maximum)

| Field | Value |
|---|---|
| Version | v0.1 |
| Phase | 7 |
| Team | Voltaic Alpha |
| Track | Options Alpha Agents |
| Governs | `HK-013` (deck/video artifact), `HK-018` (disclosure wording) |
| Source beats | [Submission narrative](options_alpha_submission_narrative_v0_1.md) §8 |
| Build recorded | `799f967`, freeze digest in `artifacts/release_freeze.json` |

## 1. How to use this document

Two registers, marked on every beat:

- **SCRIPT** — read word for word. The hook and the disclosures both have to be
  exact, the first because it is the only sentence guaranteed to be heard, the
  second because `HK-018` is proved by wording matching across four surfaces.
- **PROMPT** — bullets only. During live navigation, reading full prose makes you
  narrate past what the viewer is looking at.

This is a screencast. Your face is not on camera, so read from a second monitor
or a printed page. Do not memorize.

**Pace.** Scripted passages total 414 words, written to sit between 125 and 145
words per minute — a deliberate, unhurried read. The **PROMPT** beats add
roughly 150 improvised words on top; the rest of the budget is navigation
silence, which is desirable rather than wasted.

Measured words-per-minute against each beat's own window:

| Beat | Words | Window | Pace |
|---|---|---|---|
| 0:00 hook | 71 | 30s | 142 |
| 0:30 architecture | 108 | 45s | 144 |
| 2:15 refusal | 74 | 45s | 99 |
| 3:00 lineage (one scripted line) | 35 | 60s | 35 |
| 4:00 ablation | 53 | 25s | 127 |
| 4:25 disclosures | 73 | 35s | 125 |

Nothing exceeds 145. The two densest beats are the hook and the architecture, in
that order; if a take runs long, cut from architecture, never from the refusal.

## 2. The script

### 0:00–0:30 — The problem **[SCRIPT]**

> *Screen: dashboard landing at `http://47.236.50.157`, no talking-head intro.*

"A risk reviewer asks an AI trading team one question: what exactly did the
model decide, and what could it have decided?

Most teams answer with a prompt, a log file, and a promise.

This is Options Alpha. An LLM writes the memo, and is structurally unable to
pick the direction, move the stop, size the risk, or reach the broker. Every one
of those boundaries is provable from recorded evidence."

### 0:30–1:15 — Where model authority ends **[SCRIPT]**

> *Screen: architecture diagram slide, then the five tabs across the top —
> Evidence & setup, Model memo, Approval lineage, Outcome, Guards & state.*

"This is not 'LLM plus guardrails'. In that pattern the model proposes and a
validator checks — and a check can be deleted in a refactor while every test
still passes.

The strongest boundary here is not a check. It is an absence. The model **never
receives** the invalidation level and has no schema field to put one in. There is
no path to bypass, because there is nothing to bypass.

Direction is owned by deterministic setup code. A reversal is coerced to
abstention and recorded as an attempt. Every model failure resolves to a neutral
thesis, and therefore to no trade. There is no 'submit anyway' branch."

### 1:15–2:15 — The qualified case **[PROMPT]**

> *Screen: snapshot `spy-qualified-2026-08-27`, walk tabs 1 → 2 → 3 → 4.*

- **Evidence & setup** — provider, feed, source time, receipt time, page count,
  payload hash. Say: *277 `sip` daily bars and a five-page option chain, each
  one hashed.*
- **Model memo** — this is the model's entire contribution. Be precise here:
  `RESPONSE_SCHEMA` in `providers/openai_thesis.py` **does** carry a `direction`
  field, so "there is no direction field" is false. The model states a
  direction; a reversal against the deterministic setup is coerced to neutral
  and recorded as `model_attempted_direction_reversal`. What is genuinely absent
  is invalidation — the schema has five properties, `additionalProperties` is
  `False` and `strict` is `True`, so the model cannot emit one.
- Say out loud: *the invalidation conditions came from deterministic code, and
  the model never saw them.*
- **Approval lineage** — the hash chain from observation to intent.
- Say: *the client order id is the first 28 hex characters of the intent hash, so
  a duplicate submit collides at the broker instead of opening a second
  position.*

### 2:15–3:00 — The refusal **[SCRIPT]**

> *Screen: switch to `spy-refusal-2026-08-27`. Open the Model memo tab and let
> the empty state sit on screen for a beat before speaking.*

**Do not cut this beat for time. It is the most persuasive thirty seconds in the
video.**

"Same pipeline, different day. The setup did not qualify.

Look at the model memo tab. There is no memo. Not a memo that was rejected — no
memo at all, because the model was never called.

That is the difference between a system that asks permission and a system where
the question never reaches the model. The refusal costs nothing, produces no
tokens, and is recorded with the same evidence hashes as a trade."

### 3:00–4:00 — Lineage to a real filled order **[PROMPT + one scripted line]**

> *Screen: Outcome tab on the completed Paper lifecycle, then Guards & state.*

- One Alpaca **Paper** MLeg lifecycle, end to end: opened filled at **3.13**
  against a 3.39 limit, closed at **3.06**, reconciled to zero open positions.
- Point at the reconciliation, and say the governing rule **[SCRIPT]**:

  > "Broker acknowledgement is recorded as SUBMITTED, never as FILLED. A fill is
  > only ever written from a reconciled broker record, because assuming an
  > acknowledgement is a fill is how phantom positions are born."

- **Guards & state** — five exit triggers in fixed precedence: expiry guard,
  invalidation breach, stop loss, session stop, profit capture.
- Say the friction number out loud: *that round trip realized **minus 7.10**.*
  Do not let a judge find it first.

### 4:00–4:25 — Ablation, and the live position **[PROMPT]**

- Model ablation across **five** frozen cases against `gpt-5.6-terra`, each run
  with the model and without: **the model changed zero decisions.**
- Say: *that is what an ablation is for. A system that cannot produce that answer
  is not measuring anything.*
- **Live position** — pick the line matching your record date:
  - *Recording Wednesday:* "There is a position open right now, down about a
    hundred and sixteen dollars, and it is on screen because a demo that only
    shows the winning trade is a brochure."
  - *Recording Thursday, after the session stop:* "The position you are seeing
    closed itself this morning on the session stop, at a loss, with no human in
    the loop."

### 4:25–5:00 — Limits, stated out loud **[SCRIPT — verbatim, see §3]**

> *Screen: the disclosure slide (§3) on screen for the full 35 seconds.*

"Four limits, stated plainly.

Alpaca **Paper** only. No live endpoint exists in this build.

Quotes come from the `indicative` feed — the account has no OPRA agreement, so
these are **not trading-quality prices**.

**No alpha is claimed.** The null hypothesis, that this has no advantage over
holding SPY after costs, is not rejected. The sample is two trades.

And nothing here is investment advice. It is an engineering demonstration of an
execution boundary."

## 3. The disclosure slide — required, not optional

`HK-018` is proved by the same four statements appearing in the README, the
dashboard sidebar, the deck, **and the video**, in consistent wording. The full
README text runs about 180 words. Thirty seconds of speech holds roughly 70.

**Therefore: display the four disclosures as an on-screen slide for the whole of
4:30–5:00, using the exact README wording, while speaking the condensed version
above.** The video then contains the verbatim wording *and* a spoken summary that
contradicts none of it. Reading the condensed version alone, with no slide, is
the one variant that leaves `HK-018` arguably unmet.

Copy the slide text verbatim from the `## Disclosures` section of `README.md`.
Do not retype it — paste it, so a wording drift cannot creep in.

## 3a. Which data the demo shows, and why it is not all one source

Recorded 2 September 2026 as a **hybrid**, for a reason found while building it:

| Window | Source | Why |
|---|---|---|
| 0:00-0:30 | hosted `47.236.50.157` | proves the app is genuinely deployed |
| 0:30-4:00 | local, committed evidence database | the refusal claim is only true here |
| 4:00-4:25 | hosted `47.236.50.157` | the live open position |
| 4:25-5:00 | disclosure slide | `HK-018` |

**The finding.** The hosted instance runs with `DASHBOARD_DATABASE_URL` set, so
`app.py` reads the live worker database rather than `demo/h0_demo.db`. Every
refusal in the live database is `max_loss_exceeds_risk_budget`, and risk is
stage 04 while the memo is stage 03 - so on the hosted app **every refusal has a
model memo**. The line "no memo at all, because the model was never called"
would have been visibly false on camera.

`demo/h0_demo.db` carries `spy-refusal-2026-08-27`, `NO_TRADE`,
`no_qualified_setup`, with zero theses attached. There the claim is exactly
true, and the dashboard says so in words: *"No memo exists for this decision.
The setup did not qualify, so the model was never called."*

Because the recording crosses sources, each segment carries a caption naming the
real URL, and beat 2 opens by saying so: *"This is the same application on its
committed evidence database, where every case replays to identical hashes."*
The switch is stated, not hidden, and it doubles as the replay-determinism claim.

## 4. Recording notes

- **Order of takes.** Record 1:15–4:00 first, while the dashboard state is fresh
  and you are warm. Record the 0:00–0:30 hook last; it is the take you will redo
  most and it is only 30 seconds.
- **Do not narrate loading.** Pause the recording during any page load longer
  than two seconds and cut it out, rather than filling with "so while this
  loads…".
- **One browser, one tab, no bookmarks bar.** No account numbers, no API keys,
  no `.env`, and no broker payloads on screen at any moment.
- **If the hosted app is down**, the recording must still show this same build.
  Per the checklist freeze rule, a changed freeze digest means the video no
  longer matches the release and must be re-recorded.

## 5. What this script deliberately does not claim

Consistent with the narrative §9: no edge, no backtest result, no statement that
the system is profitable, and no suggestion that a two-trade sample supports any
conclusion about performance. The `-7.10` and the open loss are both stated on
camera because omitting them would undermine the only claim being made.
