# Options Alpha

## Winner Analysis — ALPHA HUNTER (`WA-`)

| Field | Value |
|---|---|
| Version | v0.1 |
| Phase | Post-hackathon |
| Team | Voltaic Alpha |
| Analysed | 9 September 2026 |
| Subject | `github.com/SUMANSHAKTI/alpaca` — "ALPHA HUNTER", winning entry |
| Subject state | 16 commits, 2–4 September 2026, single author, `HEAD` at *Remove Hackathon Demo Flow section from README* |
| Live instance | `https://alpaca-pmmg.onrender.com` — still online at time of analysis |
| Finding prefix | **`WA-`** — every finding in this document carries a `WA-nnn` id |

## 1. Method, and what "verified" means here

Four specialists analysed the cloned repository in parallel — agent architecture,
data and persistence, frontend and UX, trading and risk — against our own
codebase for contrast. Their findings were then **re-checked directly** before
being recorded here.

This document distinguishes two evidence levels, and says which applies to every
finding:

- **`VERIFIED`** — re-run and confirmed first-hand for this document, by reading
  the file, parsing it, or querying the live deployment.
- **`REPORTED`** — from a specialist's read, with `file:line` given, not
  independently re-run. Reliable, but one step further from the source.

**What this analysis cannot tell you.** We do not know the judges' reasoning, we
did not see what was demonstrated in their video, and a repository at `HEAD` on
9 September is not necessarily what was judged on 4 September. Nothing here is a
claim that the result was wrong. The purpose is to learn.

## 2. Executive summary

ALPHA HUNTER is a **nine-agent autonomous trading research pipeline** with a
seven-tab React dashboard, live WebSocket charting, a natural-language command
console, and a one-click propose→approve→execute loop against Alpaca Paper. It
was built in roughly **34 hours** and deployed to Render and Vercel. As a
hackathon artefact it is broader, more interactive, and more visually finished
than ours by a wide margin.

It also **contains no language model.**

That is not a rhetorical flourish. There is no LLM SDK in its dependencies, no
API call site, no prompt, and no schema. Every "agent" is deterministic Python:
`if/elif` ladders, weighted sums, and `numpy` random draws. The backtest
fabricates its performance metrics. The database schema is created at boot and
never written to. The audit log is an in-memory list with a hardcoded timestamp.

The uncomfortable and genuinely useful conclusion is that **this won anyway** —
which tells us far more about what the competition rewarded than any critique of
their code does. Section 7 is the part worth acting on.

## 3. What they built — scope and shape

### `WA-001` Nine agents, one linear pipeline · `VERIFIED`

`backend/app/agents/` holds eleven module-level singletons wired through
`orchestrator.py:131-165` in a fixed synchronous sequence: regime → discovery →
backtest → adversary → evolution scoring → portfolio allocation.

There is **no debate, voting, or consensus** despite the "AI Council" framing.
It is a pipeline, not a council.

### `WA-002` Scope: three asset classes, four seeded strategies · `REPORTED`

Equities, ETFs and crypto over a fixed universe of eight tickers plus `BTC/USD`
(`orchestrator.py:263,529`). Four strategies are hardcoded at boot
(`orchestrator.py:31-88`), including one deliberately "flawed" strawman that
exists to be rejected on camera.

**They never trade options.** Orders are plain `MarketOrderRequest` with a share
`qty` (`alpaca/trading.py:25-45`). There is no options chain, no Greeks, no
expiry handling, no multi-leg order — in a hackathon track named *Options Alpha
Agents*. The only two "option" mentions in the backend are comments over code
that computes share counts (`risk_agent.py:52`, `orchestrator.py:285-287`).

### `WA-003` Built in 34 hours, deployed twice · `VERIFIED`

First commit 2 Sept 23:29, last 4 Sept 09:17. Sixteen commits. Deployed to
Render (`render.yaml`, backend + static frontend) and configured for Vercel
(`vercel.json`). Ours took eight days and 36 commits for a narrower system.

## 4. The central finding

### `WA-004` There is no language model anywhere in the system · `VERIFIED`

This was checked four independent ways:

```
backend/requirements.txt   fastapi, uvicorn, pydantic, pydantic-settings,
                           sqlalchemy, requests, alpaca-py, numpy, pandas,
                           pytest, httpx, python-dotenv, websockets
                           -> no openai, no anthropic, no google-generativeai

grep for call sites        only two unused keys in config.py:24-25
                           (OPENAI_API_KEY, GEMINI_API_KEY) — never referenced

.env.example               LLM_PROVIDER=mock   (shipped default)
render.yaml                LLM_PROVIDER: mock  (deployed production value)
```

`LLM_PROVIDER` is inert — nothing in the codebase branches on it. The judged,
deployed instance ran with a mocked model because there was no model to mock.

### `WA-005` The backtest fabricates its own results · `VERIFIED`

`backtest.py:84-98` does not simulate the strategy against price history. It
draws the metrics:

```python
returns      = np.random.normal(0.0012, 0.011, n)
win_rate     = float(np.random.uniform(0.58, 0.68))
profit_factor= float(np.random.uniform(1.65, 2.25))
sharpe       = float(np.random.uniform(1.35, 1.95))
max_dd       = float(np.random.uniform(0.045, 0.088))
```

Real closing prices are fetched, but used only for `n = len(closes)` — the
length of the array of invented numbers. `REPORTED`: the branch is selected by
string-matching the strategy name, so the "flawed" strategy is pre-rigged to
fail (`backtest.py:27-33`) and the hero strategies pre-rigged to pass.

The chronological 70/30 train/out-of-sample split (`backtest.py:22-25`) is
structurally correct and genuinely free of look-ahead bias — over data that
carries no signal. It is rigour applied to noise.

### `WA-006` The adversary's "robustness score" is a constant · `VERIFIED`

`adversary.py:23`:

```python
score = float(np.random.uniform(18.0, 34.0)) if 'np' in globals() else 31.0
```

`adversary.py` imports only `uuid` and `typing`. **`numpy` is never imported**,
so `'np' in globals()` is always `False` and the reject-path score is always
exactly `31.0`. The line is written to look stochastic and is in fact a
constant, by accident.

`REPORTED`: the PASS branch asserts "Monte Carlo 1,000 run survival rate: 94.8%"
(`adversary.py:50-53`) as a hardcoded string. No Monte Carlo simulation exists
anywhere in the repository.

### `WA-007` "MCP tools" does not parse · `VERIFIED`

`backend/app/mcp_tools/tools.py` fails `ast.parse` with
`SyntaxError: Function parameters cannot be parenthesized` — `def get_account((self)`.
It is imported by nothing. There is no MCP server, no `FastMCP`, no wiring. The
directory name is the entire feature.

## 5. Data, persistence, and provenance

### `WA-008` A ten-table schema that is never written to · `VERIFIED`

`db/models.py` defines ten tables. Every model class — `StrategyModel`,
`OrderModel`, `TradeModel`, `AuditLogModel`, `PositionModel`, `BacktestModel` —
has **zero references outside `models.py`**, and `routes.py` uses
`Depends(get_db)` **zero times**. `init_db()` creates the tables at boot; nothing
ever reads or writes them.

`REPORTED`: no `ForeignKey` or `relationship()` declarations exist, so even the
dead schema has no joins.

### `WA-009` The audit log is in memory, and its timestamp is a literal · `VERIFIED`

`orchestrator.py:118` sets, for every event ever recorded:

```python
"timestamp": "15:36:20",
```

Confirmed live against the deployed instance, which returned:

```json
{"id":1,"timestamp":"15:36:20","agent_name":"Market Intelligence Agent",
 "action":"ANALYZE_REGIME","details":"Market regime identified as SIDEWAYS (75% confidence)"}
```

The audit trail is a Python list on a singleton (`orchestrator.py:22-23`). It
does not survive a restart. `GET /api/audit-log` on the live instance returns
`[]`.

### `WA-010` `accepted` is recorded as `FILLED` · `REPORTED`

`orchestrator.py:502` writes `execution_status = "FILLED"` when the broker status
is `"filled"` **or** `"accepted"`. In the simulation branch,
`trading.py:76-86` returns `"status": "filled"` with a fabricated
`alpaca-paper-<uuid>` id and no broker round-trip at all — `VERIFIED`.

This is precisely the failure our lifecycle exists to prevent: *"assuming an
acknowledgement is a fill is how phantom positions are born."*

### `WA-011` No idempotency key · `REPORTED`

No `client_order_id` is set on any Alpaca request (`trading.py:32-45`). The only
duplicate guard is an in-memory list of the last five `symbol-side-qty` strings
(`risk_agent.py:14,68-70`), which empties on restart. A network retry can
double-submit.

### `WA-012` Market data silently falls back to synthetic prices · `REPORTED`

Three tiers with no source tag reaching the caller: Alpaca IEX →
Yahoo Finance via raw `urllib` → **fabricated random-walk data**
(`market_data.py:295-360`, `482-519`). `get_latest_quote` returns only
`symbol/bid/ask/last_price` at every return point, so nothing downstream — risk
agent, trading loop, audit log — can distinguish a real quote from an invented
one. The autonomous loop can place real paper orders off synthetic prices.

No look-ahead protection exists: bars are taken as returned, with no check for
the currently-forming bar.

## 6. Trading, risk, and the front end

### `WA-013` No exit engine · `REPORTED`

There is nothing comparable to our exit precedence. Stop-loss and take-profit
values shown in the UI are read back from whatever Alpaca bracket orders happen
to exist (`portfolio.py:14-89`) — the system *displays* protection, it does not
decide or place it. `explainability.py:59` fabricates a cosmetic
`stop_loss_price = price * 0.965` for the narrative that is never submitted as an
order.

When a strategy deteriorates, `performance_monitor.py:32-41` cuts its edge score
and defunds it. **The open position is never closed.** Meanwhile
`orchestrator.py:330-376` scales *into* winners by 50% with no symmetric
loss-cutting rule.

### `WA-014` Entry ignores the strategies' own rules · `REPORTED`

Strategies define `entry_rules` as free text ("RSI(14) < 32"). Nothing ever
evaluates them. The live trigger picks a symbol and fires when a generic
allocation score crosses 75 (`orchestrator.py:548`).

`orchestrator.py` defines `run_autonomous_scan` **twice** (lines 255 and 515);
Python keeps only the second, so 74 lines are dead code — the file was not read
end-to-end by its own author.

### `WA-015` The front end is a genuinely better product surface · `REPORTED`

This is where they beat us, and it is not close.

React 18 + TypeScript + Vite, Tailwind with a hand-written glassmorphism layer,
**TradingView `lightweight-charts`** for candlesticks and `recharts` for
everything else. A live **WebSocket** feed pushes candle updates
(`LiveTradingChart.tsx:268-327`). Seven tabs plus a landing page against our five
static ones. Roughly a dozen affordances that mutate state or hit a live API,
against our one snapshot picker.

The demo-critical moments: a **Command Center** where you type "buy 10 NVDA" and
get a terminal response; **Optimize Portfolio** as a preview→confirm→execute loop
that places real paper orders on camera in under thirty seconds; **Run Discovery**
making a new strategy card materialise live.

### `WA-016` But much of what the UI shows is hardcoded · `REPORTED`

`LiveTradingChart.tsx:556-559` passes the AI Council panel static literals —
`edge_score: 91`, `sharpe: 1.83`, `robustness: 86` — so five of its six numbers
are **identical for every symbol**. `AICouncilView.tsx:5-70` is a fully static
array. `ExplainabilityModal.tsx:13-33` falls back to a hardcoded explanation
object when real data is absent, with no visual distinction between real and
placeholder.

The "Command Center" natural-language parser is `if "take profit" in q` plus
`re.findall` over a hardcoded symbol list (`routes.py:273-405`) — regex, not a
model, behind a box captioned "Ask AI Council".

## 7. Integrity and security findings

### `WA-017` They committed live credentials to a public repository · `VERIFIED`

Commit `09-03 12:47` is titled *"Delete .env"*. The blob remains in history and
is retrievable today:

```
BLOB 8344c568…  .env
  ALPACA_API_KEY=PKV7********
  ALPACA_SECRET_KEY=GT9C********
  DEMO_MODE=false
  LLM_PROVIDER=mock
```

**Values are masked here deliberately and were not extracted.** Deleting a file
at `HEAD` does not remove it from history — the same lesson our own `HK-003`
correction records about the account number, except this is a *credential*, not
an identifier.

Our equivalent posture, for contrast: `.env` has never been a blob in any commit,
`freeze_release.py` aborts if `.env` is ever tracked, and a `detect-secrets` gate
runs in the validation suite.

**Action:** this is a live third-party secret. Consider notifying the author, and
lablab, so the key can be rotated. Do not use it.

### `WA-018` `walkthrough.md` leaks the author's local paths · `VERIFIED`

It is an internal changelog, not a judge walkthrough, and carries
`file:///c:/Users/suman/OneDrive/Desktop/New folder (2)/...` links throughout.

## 8. What they did better — honestly

Setting aside everything above, these are real advantages we should learn from.

1. **A complete, visible loop.** Discovery → backtest → adversarial review →
   lifecycle → allocation → risk → execution → explainability → monitoring. Every
   stage is arithmetic, but it is *wired end to end and demonstrable in one
   click*. Ours does one thing thoroughly; theirs does nine things visibly.
2. **Interactivity that ends in a mutation.** A judge can *act* and watch a
   consequence. Ours is read-only by design — a defensible choice that cost us
   the single most persuasive demo mechanic available.
3. **Charts that look like trading.** One `lightweight-charts` component with
   entry/stop/target lines probably reads as more "hedge fund" in ten seconds
   than our entire dashboard does.
4. **A narrative with proper nouns.** "Edge Score", "Robustness Score", "Strategy
   Darwinism", "Adversary Agent", "AI Council". Named concepts are memorable and
   quotable in a way "deterministic execution firewall" is not.
5. **Breadth as a proxy for ambition.** Three asset classes, nine agents, seven
   tabs. Judges scoring *Application of Technology* in minutes see surface area.
6. **Motion.** Pulsing dots, spinners, animated confirmations. Every frame of
   their video looks alive; static tables do not.

## 9. What we did better — with evidence

1. **We actually call a model**, under a strict schema
   (`additionalProperties: false`, `strict: true`) with code-level defence
   against it: a direction reversal is coerced to neutral and recorded as
   `model_attempted_direction_reversal`. They govern an LLM that does not exist.
2. **Durable, hash-linked provenance.** Our chain reconstructs *why* a trade
   happened. Theirs regenerates a plausible narrative from current status
   (`routes.py:211-226`) and loses everything on restart.
3. **`SUBMITTED` is never `FILLED`.** They conflate `accepted` with filled and
   fabricate fills outright in simulation mode.
4. **Derived idempotency** from the intent hash, versus a five-entry in-memory
   list.
5. **We published the result that made us look bad** — the ablation showing the
   model changed zero decisions across five cases, and an explicit unrejected
   null hypothesis on a sample of two. They simulate having passed a test they
   never ran.
6. **Credential hygiene.** See `WA-017`.
7. **Real options.** MLeg verticals, delta bands, debit/width screening, an exit
   precedence, and a completed reconciled round trip — in the options track.

## 10. Lessons — what to actually change

Ranked by expected value if we enter something like this again.

1. **Presentation is a first-class deliverable, not packaging.** We spent our
   last days on requirement traceability. They spent theirs on a React dashboard.
   Both matter; only one is visible in five minutes.
2. **Ship one interactive affordance.** A single button a judge can press that
   causes a visible, real consequence would have changed our demo more than any
   further audit rigour. Read-only was a defensible safety posture — we could
   have kept it *and* added a "simulate this decision" control.
3. **Name our concepts.** We have genuinely novel mechanisms — the absent
   invalidation field, derived client-order-id idempotency, the refusal that
   costs no tokens. They deserve proper nouns.
4. **Use a real charting library.** Streamlit's defaults cost us; the marginal
   effort of `lightweight-charts` is small against the perceived-polish gain.
5. **Breadth reads as ambition, even when depth is worth more.** One SPY vertical
   is honest and narrow. A second instrument or a portfolio view would have cost
   little and signalled more.
6. **Our rigour is invisible unless we dramatise it.** "The model was never
   called" is a stronger claim than anything in their repo — but it is an
   *absence*, and absences need staging to land.

The deepest lesson is uncomfortable: **we optimised for being right, and the
competition rewarded being legible.** Those are not opposites, and next time we
should not treat them as a trade-off. Everything in section 9 is real and worth
keeping — it just needed the delivery of section 8.

## 11. Responsible disclosure

`WA-017` concerns a live third-party credential in a public repository. The
recommended action is to notify the repository owner and the organisers so the
key can be rotated. This document masks the values, and the credential was not
used, tested, or retained. No mutating endpoint on their live deployment was
called during this analysis; only read-only `GET` routes were queried.
