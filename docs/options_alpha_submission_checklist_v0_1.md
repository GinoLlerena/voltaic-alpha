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

**Project title** (50 characters max — this is **36**):

```
Options Alpha: AI Execution Firewall
```

**Short description** (255 max — this is **214**):

```
An auditable execution firewall for AI trading agents. A language model writes the memo; deterministic code owns direction, invalidation, sizing, eligibility, and every broker write. One SPY setup, on Alpaca Paper.
```

**Long description** (100 words minimum — this is **201 words**):

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

**Technology tags:** `Alpaca`, `OpenAI`, `Python`, `Streamlit`, `PostgreSQL`

`FastAPI-free` was removed on 1 September 2026: it is a negative claim rather
than a technology, it is not a selectable platform term, and a tag that names
what the project does *not* use spends attention without buying anything.

**Demo application platform:** `Alibaba Cloud ECS` — or the nearest selectable
option, with the real platform named in Additional Information.

**Additional information:**

```
Paper-only engineering demonstration. The public Alibaba Cloud ECS dashboard is
credential-free and cannot place orders. A separate worker executes only through
Alpaca's Paper endpoint behind deterministic risk and authorization checks.
Option quotes use the indicative feed because this account has no OPRA
entitlement; displayed prices are therefore not executable marks. The current
sample is too small to establish alpha, and all P&L is reported as a diagnostic
with its sample size. The H0 demonstration intentionally supports one concurrent
SPY strategy; portfolio scaling is deferred until after the hackathon.
```

**Category / track:** Options Alpha Agents

## 2. Required artifacts

| Artifact | Requirement | Status |
|---|---|---|
| Public GitHub repository | **Mandatory** | **Done.** `github.com/GinoLlerena/voltaic-alpha` is public and was validated by an unauthenticated clean clone: 34 commits, both tags, and all nine validation gates pass from the clone. |
| Application URL | No platform restriction (organizers, 29 Aug 2026) | **Done, 30 August 2026.** `http://47.236.50.157` - an Elastic IP bound to the dashboard host, so it survives the instance being stopped, unlike the pay-as-you-go address it replaces. Port 80, no port number in the URL; `:8501` still serves as a fallback. All five views verified rendering from the public internet with zero console errors. No domain is required: `F-K` was superseded. See [runbook](./options_alpha_deployment_runbook_v0_1.md) section 8. |
| Video | MP4, **5 minutes maximum** | Beats drafted in the narrative §8; not yet recorded |
| Slide deck | PDF | Ten-slide outline in the narrative §7; not yet exported |
| Cover image | PNG or JPG, 16:9 | **Done.** `assets/cover.png`, 1920x1080. Source and regeneration steps in `assets/cover.html` |
| Licence | Original and MIT-compliant (`F-F`) | **Done.** `LICENSE` at the repository root, declared in `pyproject.toml`. A public repository with no licence is all-rights-reserved by default, which is the opposite of MIT-compliant. |
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

- [ ] Record the MP4 (≤ 5 min) and export the deck PDF.
- [ ] Enter every non-media field on the form, check the platform's own
      validation, and save a draft.
- [ ] Capture a redacted export or screenshot of the saved form.
- [ ] Submit, and only then mark `HK-014` complete. **A saved draft is not a
      submitted project**, and the missing video and deck may themselves stop the
      platform accepting a final submit.

`F-04` and `F-05` were removed from this list on 1 September 2026. Neither is an
open organizer question any longer: autonomy ships in both postures behind a
configuration switch, and the Paper account was verified directly with no
published equity or reset rule to conflict with. Both remain recorded in
`SRC-PHASE0` as the interpretations they always were.

## 5. Freeze rule

No new capability after the freeze. Fixes to integration defects are permitted
and require re-running `scripts/freeze_release.py`; a changed freeze digest means
the recorded video no longer matches the released build and must be re-recorded.
