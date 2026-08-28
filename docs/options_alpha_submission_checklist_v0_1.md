# Options Alpha

## Phase 7 Submission Checklist

| Field | Value |
|---|---|
| Version | v0.1 |
| Deadline | **4 September 2026, 15:00 UTC** (10:00 GMT-5), confirmed on the live dashboard |
| Team | Voltaic Alpha |
| Track | Options Alpha Agents |
| Status at freeze | Code, configuration, prompts, policy, and demo data frozen; see `artifacts/release_freeze.json` |

## 1. Ready-to-paste submission fields

**Project title** (50 characters max — this is 38):

```
Options Alpha: AI Execution Firewall
```

**Short description** (255 max — this is 208):

```
An auditable execution firewall for AI trading agents. A language model writes the memo; deterministic code owns direction, invalidation, sizing, eligibility, and every broker write. One SPY setup, on Alpaca Paper.
```

**Long description** (100 words minimum — this is 191):

```
Most "AI trading agent" projects let a model propose a trade and add a validator
to check it. Checks can be removed, bypassed, or quietly loosened, and the
artifact never tells you whether that happened.

Options Alpha inverts it. The model receives evidence and writes a memo. It
never receives the invalidation conditions and has no schema field for them, so
there is no path by which a memo could soften a stop. The deterministic setup
owns direction: the model may agree or abstain, and a reversal is coerced to
abstention and recorded as an attempt. Sizing and option eligibility are
computed after the memo, from the observed chain. One file in the repository is
permitted to express a broker write, enforced by a CI check that parses the AST.

Every decision carries a hash chain from the observation, to the approved
intent, to the exact bytes sent to Alpaca, to the reconciled fill. The client
order id is derived from the intent hash, so a duplicate submit collides instead
of opening a second strategy.

We ran one Paper lifecycle and published an ablation showing the model changed
zero decisions. Both results are reported as they happened. No alpha is claimed.
```

**Technology tags:** `Alpaca`, `GPT-5`, `Python`, `Streamlit`, `PostgreSQL`, `FastAPI-free`

**Category / track:** Options Alpha Agents

## 2. Required artifacts

| Artifact | Requirement | Status |
|---|---|---|
| Public GitHub repository | **Mandatory**; private "may lower your overall score" | Repository created private. **Must be flipped public before submitting** |
| Application URL | Streamlit, Replit, or Vercel only | Streamlit app builds and runs locally; deploy and record the URL |
| Video | MP4, **5 minutes maximum** | Beats drafted in the narrative §8; not yet recorded |
| Slide deck | PDF | Ten-slide outline in the narrative §7; not yet exported |
| Cover image | PNG or JPG, 16:9 | Not yet produced |
| Title, descriptions, tags | See §1 | Drafted above, within limits |

## 3. Rehearsal script

Run in this order; each has a known-good answer.

1. **Clean-checkout validation.** `bash scripts/run_h0_validation.sh` — nine gates pass.
2. **Qualified path.** Dashboard view 2 → 3 → 4 → 5 on `spy-qualified-2026-08-27`.
   Point at the invalidation conditions and say the model never saw them.
3. **Refusal path.** Switch to `spy-refusal-2026-08-27`. View 3 shows no memo
   exists because the model was never asked. This is the strongest 30 seconds.
4. **Recovery explanation.** Show `test_ambiguous_submit_is_resolved_by_lookup_not_retry`
   and say why re-submitting is how duplicates are created.
5. **Lifecycle.** View 5: filled open at 3.13, close at 3.06, flat, `-7.10`.
   Say the friction number out loud rather than letting a judge find it.
6. **Fallback.** If the hosted app is down, the recorded video must show this
   same build. Re-record if the freeze digest changes.

## 4. Open items owned by the team

- [ ] Flip `github.com/GinoLlerena/voltaic-alpha` to **public** (`F-J`).
- [ ] Deploy the Streamlit app and record the URL.
- [ ] Record the MP4 (≤ 5 min) and export the deck PDF.
- [ ] Produce the 16:9 cover image.
- [ ] Ask the organizers whether the Submission Guidelines' "IBM Bob Report"
      clause applies to this event. It reads as carried-over copy from another
      sponsor but is marked mandatory.
- [ ] Answer the three still-open questions (`F-02` pre-existing code, `F-04`
      autonomy, `F-05` account/leaderboard) and record each against the fallback
      it replaces.

## 5. Freeze rule

No new capability after the freeze. Fixes to integration defects are permitted
and require re-running `scripts/freeze_release.py`; a changed freeze digest means
the recorded video no longer matches the released build and must be re-recorded.
