# Options Alpha — Streamlit retirement: plan (for the owner's decisions)

| Field | Value |
|---|---|
| Date | 24 October 2026, America/Lima |
| Status | **Draft. Nothing is removed and nothing on the host is changed until the owner answers §5.** |
| Why | React has served port 80 since 29 September. Streamlit still runs on the host as the rollback surface. Port 8501 has been closed to the world since 23 October, so nobody outside reaches it |
| Rule | Code simplicity audit, principle 8: retire deliberately. Check callers, commands, services, rollback and tests, and keep it working until the retirement and the rollback replacement are approved |

## 1. What still depends on Streamlit

| Where | What | Effect of removing Streamlit |
|---|---|---|
| Host | `options-alpha.service` runs `streamlit run app.py` on 8501 | Frees memory and CPU on the 2c2g server; to be measured on the next session |
| Host | `options-alpha-port80.service` redirects 80 to 8501; React's drop-in overrides it | The unit must keep working for React, so it is rewritten, not deleted |
| `scripts/deploy_react.py` | `rollback` puts port 80 back on Streamlit, and the deploy checks Streamlit's health | Needs a different rollback (§3) |
| `scripts/ship_host.py`, `deploy_all.py`, `restore_hosted_demo.sh` | Streamlit health checks and restarts | Those lines are removed |
| `Dockerfile` | The image runs Streamlit on 8501. It is the judges' "run it yourself" image | Needs a decision (§5, D2) |
| `README.md` | `uv run streamlit run app.py`, "the five judge views" | Rewritten for React |
| Repository | `app.py` (914 lines), `.streamlit/`, the `streamlit` dependency | Removed in the last phase |
| Tests | `test_dashboard.py` (20 tests), `test_presentation_tour.py` (11), `test_parity.py` (9, checks that Streamlit and the API agree), two `AppTest` runs in `test_api.py`, packaging and deploy tests | Dashboard tests removed. Parity is kept as API-only checks |

`presentation/*`, the read model both UIs share, stays: the API uses it.

## 2. Phases

Each phase is its own PR, merged and deployed only after the one before it
has been verified.

1. **Stop serving.** On the host, outside the trading day: stop and disable
   `options-alpha.service`, and rewrite the port-80 unit so it no longer
   names 8501. React and the API are unaffected. The code stays, so a local
   `uv run streamlit run app.py` still works for diagnosis. Undo: enable and
   start the unit.
2. **New rollback, deploy scripts.** `deploy_react.py rollback` restores the
   previous `frontend/dist` and API module from `.deploy-backup/` (it already
   saves them there). Remove the Streamlit health checks from the deploy
   scripts, and update their tests.
3. **Remove the code.** Remove `app.py`, `.streamlit/`, the dependency, the
   dashboard tests and the Streamlit parts of the README. The Docker image
   follows D2.

## 3. The rollback replacement

Today a bad React deploy is undone by pointing port 80 back at Streamlit.
Afterwards it is undone by putting back the previous React build and API
module, both already saved by every deploy in `.deploy-backup/<stamp>/`. That
is a rollback to the last good React, not to a second UI. Phase 2 tests it
the way `test_deploy_react.py` tests today's rollback.

## 4. What it does not touch

The worker, the database, the scheduler, the trading rules, and the API's
endpoints and read model.

## 5. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | Scope: phase 1 only (stop serving, keep the code as a local diagnostic), or all three phases? | **All three**, one at a time. Keeping 914 lines and 40 tests for a UI nobody uses is the cost the simplicity audit names |
| D2 | The Docker image (the judges' self-run demo): switch it to React and the API, or freeze it as the submission record? | **Freeze it as the submission record**: tag the current commit and point the README's Docker section at that tag, so the record still runs. Switching the image is a separate, larger job |
| D3 | The rollback in §3 replaces "port 80 back to Streamlit". Accept it? | **Yes** |
| D4 | Phase 1 on the host needs a session outside market hours (`session.py start --reason dev`), with no position open. When? | The first evening this week with no position open |
