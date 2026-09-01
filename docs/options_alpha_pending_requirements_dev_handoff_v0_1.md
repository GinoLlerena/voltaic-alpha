# Options Alpha — Pending Hackathon Requirements Developer Handoff

| Field | Value |
|---|---|
| Version | v0.1 |
| Prepared | 31 August 2026 |
| Scope | Close or correctly reclassify `HK-002`, `HK-003`, `HK-005`, `HK-007`, `HK-014`, and `HK-018` |
| Explicitly excluded | `HK-012` video, `HK-013` deck, and `HK-017` deck/video rubric mapping |
| Primary files to review | `docs/options_alpha_requirements_traceability_v0_1.md`, `docs/options_alpha_phase0_event_cut_line_v0_1.md`, `docs/options_alpha_submission_checklist_v0_1.md` |

## 1. Delivery objective

Update the requirements records so they distinguish:

1. requirements supported by verified evidence;
2. organizer facts that are not published but are neutralized by a recorded
   fallback; and
3. work that cannot be called complete until the lablab submission form is
   saved or submitted.

Do not mark a row complete merely because the application can tolerate an
unknown rule. Eligibility evidence and implementation safety are different
claims.

## 2. Verified evidence

### `HK-002` — enrollment and team eligibility

Verified:

- The event is online and publicly states that participants may build from
  anywhere in the world.
- The public Voltaic Alpha team page lists Gino Llerena as its member.
- The participant is resident in Peru and has confirmed Peru as the applicable
  region.
- The team intends one project submission under Voltaic Alpha.

Public evidence:

- <https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon>
- <https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/voltaic-alpha>
- <https://lablab.ai/guide>

Recommended transition: `PARTIAL` -> `COMPLETE`.

Required wording constraint: record the Peru residency and one-submission
statement as a **team attestation**, not as an organizer quotation. Do not claim
that the public rules contain a Peru-specific eligibility clause.

### `HK-003` — Alpaca Paper account

A read-only query against the Alpaca Paper Trading API verified all of the
following for the credentials currently configured in the local project:

| Check | Verified result |
|---|---|
| Correct account | Exact equality with the owner-confirmed account number; keep the number redacted in public documents |
| Resolved environment | Alpaca Paper endpoint |
| Account status | Active |
| Account created | `2026-08-28T13:38:58.339250Z` (`08:38:58` Peru time) |
| Event kickoff | `2026-08-28T15:00:00Z` (`10:00:00` Peru time) |
| Orders before kickoff | `0` |
| Earliest submitted order | `2026-08-28T15:48:37.052143Z` |
| Earliest fill | `2026-08-28T15:48:37.092502Z` |
| Orders returned | `4` |
| Options approved level | `3` |
| Options trading level | `3` |
| Trading blocked | `false` |

The available Alpaca MCP connector was not used for this proof because its
installed tool inventory is market-data-only and exposes no account, order, or
activity-history method. Enabling the MCP `account` or `trading` toolsets would
violate the project's least-authority decision because those toolsets bundle
mutating operations. The read-only Trading API query is the authoritative
broker-side evidence.

The public event sources do not state a required starting equity, reset policy,
or account-age threshold. Record that absence honestly. Do not invent an
organizer rule. The verified same-day account, zero pre-kickoff orders, and
fresh-equity sizing close the project's eligibility risk unless an organizer
later publishes a contradictory requirement.

Recommended transition: `PARTIAL` -> `COMPLETE` with the qualifier **no
additional account/equity/reset condition is published**.

Security constraints:

- Do not copy the full account number into README, fixtures, screenshots, logs,
  or this handoff.
- Do not print API keys or raw account/order payloads.
- Do not enable MCP trading tools to reproduce this read.
- The exact corrected account-number string was not found in the current
  worktree or by `git log -S`; do not repeat a claim about that exact string
  being in Git history without a separate history audit.

## 3. Rows that can be closed from existing evidence

### `HK-005` — P&L leaderboard

Current evidence shows:

- Published judging dimensions do not include P&L.
- The live dashboard ranks community-voted submissions, builders, and
  referrers; it does not expose a trading-performance leaderboard.
- Project P&L is already described as diagnostic and accompanied by sample
  size. No alpha is claimed.

Recommended transition: `PARTIAL` -> `COMPLETE`.

Also update `F-05` and `DEC-003` so they no longer say that a separate P&L
leaderboard remains open. Preserve the rule that a later organizer announcement
would change presentation, not the risk engine.

### `HK-007` — autonomous execution

The organizer has not published a sentence requiring either fully autonomous
execution or per-trade human approval. This is no longer an implementation
blocker:

- the project has an autonomous Alpaca Paper execution path;
- operator approval is a configuration boundary rather than a second code
  path; and
- `scripts/arm_worker.sh` and `scripts/disarm_worker.sh` select the intended
  operating posture.

Recommended transition: `NEEDS_CONFIRMATION` -> `COMPLETE` or the repository's
equivalent `RESOLVED_BY_CONFIGURATION` status.

The evidence note must say that the **demo mode is autonomous after deliberate
operator arming**. Do not claim that no human action is ever required. Keep the
organizer's missing statement recorded as `NOT STATED`, but remove it from the
submission blockers.

## 4. Submission-form work that still requires action

### `HK-014` — non-media submission fields

This row is not complete yet. The public team page currently reports that the
team leader has not made a submission, and the repository has no final form
export or screenshots.

Existing prepared fields:

- project title;
- short description;
- long description;
- primary track; and
- repository and application URLs elsewhere in the checklist.

Corrections required before form entry:

| Item | Current issue | Required change |
|---|---|---|
| Title count | Checklist says `38` | Correct to `36` characters |
| Short-description count | Checklist says `208` | Correct to `214` characters |
| Long-description count | Checklist says `191` | Recount using the platform result; local whitespace count is approximately `201`, safely above the 100-word minimum |
| Technology tags | Includes `FastAPI-free` | Remove it; a negative/non-technology tag weakens the submission |
| Preferred tags | May not match platform vocabulary | Use selectable, actually used tags such as `Alpaca`, `OpenAI`, `Python`, `Streamlit`, and `PostgreSQL` |
| Demo application platform | Missing prepared value | Use `Alibaba Cloud ECS`, or the nearest selectable platform plus an explanation in Additional Information |
| Additional Information | No prepared response | Add the draft below and adjust only if the form imposes a smaller limit |

Suggested Additional Information:

> Paper-only engineering demonstration. The public Alibaba Cloud ECS dashboard
> is credential-free and cannot place orders. A separate worker executes only
> through Alpaca's Paper endpoint behind deterministic risk and authorization
> checks. Option quotes use the indicative feed because this account has no
> OPRA entitlement; displayed prices are therefore not executable marks. The
> current sample is too small to establish alpha, and all P&L is reported as a
> diagnostic with sample size. The H0 demonstration intentionally supports one
> concurrent SPY strategy; portfolio scaling is deferred until after the
> hackathon.

Required status handling:

1. Change `PENDING` to `PARTIAL / READY_FOR_FORM` after correcting the checklist
   and preparing every non-media field.
2. Open the actual form, enter the values, verify platform validation, and save
   a draft.
3. Capture a redacted preview/export.
4. Change to `COMPLETE` only after the platform records the final submission.

Video and deck uploads are outside this handoff, but their absence may prevent
the platform from accepting the final submit action. Do not misreport a saved
draft as a submitted project.

## 5. Disclosure row ownership

### `HK-018` — disclosures

The development-owned surfaces are complete:

- README and dashboard contain matching Paper-only, indicative-feed, no-alpha,
  sample-size, and non-advisory statements; and
- `tests/test_dashboard.py` verifies the required dashboard phrases.

Because the original acceptance proof also names the deck and video, the honest
status is:

- **Development scope:** `COMPLETE`.
- **Whole requirement:** `PARTIAL — PRESENTATION-ONLY REMAINDER`.

Do not mark the whole row `COMPLETE` until the omitted presentation artifacts
carry consistent disclosure wording. No application-code change is required.

## 6. Required document changes

Review and update these records together so they cannot contradict each other:

1. `docs/options_alpha_requirements_traceability_v0_1.md`
   - update the six `HK-*` rows using the status rules above;
   - add one evidence-log entry for the Paper-account verification;
   - update `DEC-003` and `DEC-004` consistently; and
   - do not expose the account number.
2. `docs/options_alpha_phase0_event_cut_line_v0_1.md`
   - retire the account/equity/reset and leaderboard remainder of `F-05` with
     the exact distinction between published rules and verified fallback;
   - retain `F-04` as the recorded interpretation if useful, but remove it from
     the blocker list.
3. `docs/options_alpha_submission_checklist_v0_1.md`
   - correct field counts and technology tags;
   - add Demo Application Platform and Additional Information;
   - remove `F-04` and `F-05` from the active organizer-question checklist;
   - add the form-draft and final-submission proof steps.

## 7. Acceptance checklist

- [ ] `HK-002` records worldwide event evidence, public team membership, Peru
      team attestation, and one intended Voltaic Alpha submission.
- [ ] `HK-003` records the redacted Paper-account match, creation timestamp,
      zero pre-kickoff orders, earliest order/fill, active status, and options
      level without exposing credentials or the account number.
- [ ] `HK-005`, `F-05`, and `DEC-003` no longer contradict each other about a
      P&L leaderboard.
- [ ] `HK-007`, `F-04`, and `DEC-004` distinguish an unpublished organizer rule
      from a resolved implementation posture.
- [ ] `HK-014` field counts, tags, platform, and Additional Information are
      corrected, and its status matches actual platform state.
- [ ] `HK-018` clearly separates complete development disclosures from the
      presentation-owned remainder.
- [ ] No full account number, API key, secret, or raw broker payload appears in
      the diff.
- [ ] Relevant documentation links resolve and the existing validation suite
      still passes if any executable file is touched.

## 8. Expected implementation effort

The documentation reconciliation should take approximately 45–75 minutes.
Preparing and validating the non-media submission form should take another
30–45 minutes. No trading-engine or frontend implementation is required for
these six rows.
