# Frontend (`RUI-2`)

React + TypeScript over the read-only presentation API. What it renders comes
from the server, including the judgements: source mode, status tone, the decision
list's grouping and labels. A second implementation in the browser is how two
surfaces come to disagree, which `RUI-VAL-009` already demonstrated once.

## Working on it

    pnpm install
    pnpm run dev        # expects the API on 127.0.0.1:8600; Vite proxies /api

    pnpm run typecheck
    pnpm run lint
    pnpm run test
    pnpm run build

## The contract

`openapi.json` is exported from the API by `scripts/export_openapi.py` and
committed, so type generation and CI need neither Python nor a running server.
`src/api/schema.ts` is generated from it — never edited by hand.

Two guards keep that honest: a Python test fails if the committed document has
drifted from the server, and CI regenerates the types and fails on any diff.

`get` accepts only URLs built by `api.*`, which are checked against the generated
paths. Accepting a bare string would make the path union decorative: a typo would
type-check.

## What is deliberately absent

No write helper, no credentials, no `method:` — the API publishes no write, and a
client that cannot express one cannot drift into attempting one. A test asserts
this against the source with comments stripped, because a guard that cannot tell
a call from prose explaining why we never make that call punishes documentation.

## How it is served

In production the API serves the build from the same origin
(`PRESENTATION_UI_DIR`, default `frontend/dist`), so there is no CORS and no
separate file server. `/api/` is rate-limited; static files are not. See the
deployment runbook, section 11.

## Checks

- `pnpm run test` — unit tests (vitest, jsdom).
- `pnpm exec playwright test` — axe at 360–1440 px, no horizontal overflow on
  phone widths, and visual baselines per platform (`e2e/__screenshots__/`).
  Linux baselines come from the CI artifact.
- `LIVE_URL=http://host:port pnpm exec playwright test -c playwright.live.config.ts`
  — the main flows against a real, running stack (`e2e-live/`). Not in CI: it
  needs data.

The theme is dark-only for now; a light theme is deferred.
