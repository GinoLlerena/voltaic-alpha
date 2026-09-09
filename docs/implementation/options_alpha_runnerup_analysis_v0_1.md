# Options Alpha

## Runner-Up Analysis — TradePilot AI (`RA-`)

| Field | Value |
|---|---|
| Version | v0.1 |
| Phase | Post-hackathon |
| Team | Voltaic Alpha |
| Analysed | 9 September 2026 |
| Subject | **TradePilot AI**, second place |
| Backend | `github.com/divine308/Tradepilot` — 17 commits, 31 Aug – 4 Sept 2026 |
| Frontend | `github.com/divine308/TradepilotAi` — 11 commits, separate repository |
| Live demo | `https://tradepilot-ai-dun.vercel.app/` — online at time of analysis |
| Submission | `lablab.ai/submissions/tpyjss8emfl37zk4jq9jz16t` |
| Contributors | Four named: Divine Okechukwu, Esther Olinya, Peace SOSSA, Jethro Ibebuike |
| Finding prefix | **`RA-`** |
| Companion | [Winner analysis (`WA-`)](options_alpha_winner_analysis_v0_1.md) |

## 1. Method

Same as the `WA-` analysis: four specialists — agent architecture, data and
security, trading and risk, product and presentation — working the two cloned
repositories in parallel, with every load-bearing claim re-checked directly
before being recorded here.

- **`VERIFIED`** — re-run first-hand for this document.
- **`REPORTED`** — from a specialist's read, `file:line` given, not re-run.

We do not know the judges' reasoning and did not see their video. Nothing here
argues the placings were wrong.

## 2. Executive summary

**TradePilot is the real thing.** Where the winner's "AI" turned out to be
`if/elif` ladders and `np.random` (see `WA-004`, `WA-005`), TradePilot genuinely
calls a model, on a strict JSON schema, over genuinely computed indicators, with
fail-closed error handling and real broker-side protective stops. It is the most
honest of the three entries about its own limitations.

It is also, uncomfortably, **the closest thing to our own thesis in the
competition** — and it placed above us:

> *"A central principle of TradePilot is that AI should not have unrestricted
> authority over trading execution. AI reasoning and deterministic risk
> enforcement are separated within the architecture."* — their README

That is the execution-firewall argument. So the idea was not the problem.

What separated them from us was **packaging**: a separate 20,495-line React
frontend, a landing page, registration and login, a live Vercel deployment
anyone can click, a four-person team, and — tellingly — a 2,988-line cinematic
demo page built purely for video capture with **zero backend calls**.

And the cross-cutting finding that applies to both entries above us:
**neither of them ever traded an option.**

## 3. The finding that spans all three entries

### `RA-001` No top-three finisher except us traded options · `VERIFIED`

Counting references to the Alpaca options API surface — `OptionLegRequest`,
option chains, Greeks, expiry, strike, MLeg:

| Entry | Options-API references | What it actually trades |
|---|---|---|
| ALPHA HUNTER (1st) | **0** | equities, ETFs, crypto — whole-share quantities |
| TradePilot (2nd) | **0** | equities only, 7 hardcoded tickers |
| **Options Alpha (ours)** | **102** | SPY debit verticals, native MLeg multi-leg orders |

TradePilot imports only `MarketOrderRequest`, `StopOrderRequest` and
`ReplaceOrderRequest` (`alpaca_service.py:15-19`). Its 519-line README contains
no options terminology at all. The track was named **Options Alpha Agents**.

We were the only entry of the three that built the thing the track was named
after — delta bands, debit-to-width screening, DTE guards, native multi-leg
submission — and it counted for nothing visible in the result. That is worth
sitting with before the next competition: **the track name did not describe the
scoring.**

## 4. The AI is genuine

### `RA-002` A real model call, on a strict schema · `VERIFIED`

`app/services/ai_service.py` uses `from openai import OpenAI` and
`client.responses.create` — the same Responses API we use — with structured
output enforced:

```python
text={"format": {
    "type": "json_schema", "name": "trade_decision", "strict": True,
    "schema": {"type": "object", "properties": {
        "decision":    {"type": "string", "enum": ["BUY","SELL","HOLD"]},
        "confidence":  {"type": "number", "minimum": 0, "maximum": 1},
        "risk_score":  {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning":   {"type": "string"}},
    "required": [...], "additionalProperties": False}}}
```

Four fields, all required, `strict: True`, `additionalProperties: False`. This
is the same discipline as our five-field memo schema, arrived at independently.
Default model `gpt-4.1-mini` (`core/config.py:18`).

### `RA-003` No fabrication anywhere in the decision path · `VERIFIED`

A grep for `np.random`, `random.`, `mock`, `fake` and `hardcod` across
`app/agents/` and `app/services/` returns **nothing**. Indicators are genuinely
computed with pandas from real 90-day Alpaca bars (`market_agent.py:33-43`).

This is the sharpest contrast with the winner, whose backtest drew its Sharpe
ratio from `np.random.uniform(1.35, 1.95)`.

### `RA-004` The model picks direction — but must be corroborated · `REPORTED`

Unlike ours, **the model does choose BUY/SELL/HOLD**. There is no
neutral-coercion concept and no equivalent of our
`model_attempted_direction_reversal` telemetry.

But it cannot act alone. `strategy_agent.py:215-274` requires **three-way
agreement** before a trade proceeds: the model says BUY, **and** an
independently computed `quantitative_score >= 70`, **and** `confidence >= 0.70`,
**and** `risk_score <= 0.50`. Any disagreement collapses to `HOLD`. A second
portfolio-level gate follows in `risk_agent.py`.

Sizing is fully deterministic (`autonomous_agent.py:1660-1673`) and the model has
no size field at all. Instruments come from a hardcoded seven-symbol watchlist —
the model cannot propose a ticker.

**"Model proposes, code confirms and sizes"** versus our **"code decides, model
only writes a memo."** Theirs is the more common agentic pattern and puts the
model closer to the trade; ours is stricter. Both are defensible, and theirs is
easier to explain on camera.

### `RA-005` Fail-closed error handling · `REPORTED`

`strategy_agent.py:82-105` wraps the model call and returns
`decision: "HOLD", confidence: 0.0, risk_score: 1.0` on any failure — network
error, malformed JSON, bad enum, out-of-range float. `supervisor.py:68-73`
carries the comment *"Fail closed. If we cannot determine existing exposure, do
not assume the portfolio is empty."*

This is the same instinct as our neutral-thesis-on-failure rule. No explicit
timeout is set on the OpenAI call, so a hung request would stall the scan —
a liveness gap, not a safety one.

## 5. Data, persistence and provenance

### `RA-006` Four tables, and the trade table is dead · `VERIFIED`

`users`, `api_keys`, `trades`, `autonomous_agent_state`. A grep for `Trade(`
outside its own model definition returns **nothing** — the trades table is
created and never written to. Its `ai_reasoning` column, sized `String(5000)`
and clearly intended to store the model's justification, is never populated.

Against our 20-table hash-linked chain, they persist essentially nothing of the
trading lifecycle. All order, position and account state is read live from
Alpaca on every request.

### `RA-007` The audit trail is a 100-entry in-memory list · `REPORTED`

`autonomous_agent.py:203-226` appends activity entries to `self.activity`,
capped at 100 and wiped on restart. The only database write from the entire
autonomous subsystem is a single `enabled` boolean.

**A trade executed today cannot be reconstructed from the database tomorrow.**
That is the largest architectural gap between their system and ours — and the
same gap the winner had.

### `RA-008` No idempotency key · `REPORTED`

No `client_order_id` is set on any Alpaca request; Alpaca auto-assigns one. A
retry would submit a duplicate. There is real defensive engineering nearby —
`get_available_sell_quantity` nets position quantity against open sell orders
(`alpaca_service.py:132-203`), and `submit_protective_stop` refuses if a stop
already exists (`:619-640`) — which shows genuine thought about broker-side
races, just not request-level idempotency.

### `RA-009` `SUBMITTED` and `FILLED` are not locally distinguished · `REPORTED`

`Trade.status` defaults to `"pending"` and is never updated because no row is
ever created. Fill state is whatever Alpaca reports, live, surfaced straight to
the frontend. There is a genuine polling reconciliation loop
(`wait_for_order_fill`, `alpaca_service.py:525-571`) — it just has no local
ledger to reconcile against.

## 6. Security

### `RA-010` Multi-user auth over a single shared brokerage account · `VERIFIED`

This is the most consequential finding in the repository.

The app has registration, login, JWT sessions and per-user API keys. But the
Alpaca client is a **module-level singleton** built from environment variables:

```
alpaca_service.py:988   alpaca_service = AlpacaService()
routers/trading.py:11   from app.services.alpaca_service import alpaca_service
routers/trading.py      mentions of user_id: 0
```

Every authenticated user trades the **same one paper account**. Any registered
user can view, cancel or close every other user's positions — including via
`DELETE /api/trading/orders` and `POST /api/trading/positions/close-all`. The
multi-tenancy is presentational.

### `RA-011` A real signing key ships in `.env.example` · `REPORTED`

`.env.example` carries a fully-formed 64-hex-character `SECRET_KEY` (masked
here), present since the initial commit. It is the *example* file, not `.env`,
and `.gitignore` correctly excludes `.env` — but anyone who deploys by copying
the example without regenerating it ships a **publicly known HS256 JWT signing
key**. The token payload is only `{"sub": user_id, "exp": ...}`, so forging any
user's session would be trivial.

### `RA-012` The issued API keys authenticate nothing · `REPORTED`

`POST /api/keys` mints `mk_live_…` keys and stores a SHA-256 hash. That hash is
**never read back** — every protected route uses JWT bearer auth instead. There
is no revoke route despite an `active` column. `api_keys.py:28-39` defines
`router` twice, the second definition silently discarding the
`Depends(get_current_user)` from the first (dead code, not exploitable, since
each route re-checks separately).

### `RA-013` What is genuinely well done · `REPORTED`

Worth recording plainly: **argon2** password hashing, JWT algorithm correctly
pinned to `["HS256"]` on every decode (preventing `alg:none` confusion), a narrow
CORS allowlist with no wildcard, and parameterised SQLAlchemy queries throughout
with **no injection surface**. No `.env` blob was ever committed — unlike the
winner (`WA-017`). Their credential hygiene beats first place.

## 7. Trading and risk

### `RA-014` Real broker-side stops, asymmetric protection · `REPORTED`

Stop-loss is a genuine `StopOrderRequest` at −4%, placed at the broker and
re-armed each cycle if missing (`_ensure_position_protection`). But
**take-profit (+30%) and breakeven (+10%→+0.5%) are software-polled**, checked
only inside `manage_positions()` every 300 seconds and executed as market sells.

If the process dies, the stop still protects; the take-profit does not. All
orders use `TimeInForce.DAY`, so protective stops lapse at each close and must
be re-submitted — an unprotected window at every open if the process was down
overnight.

### `RA-015` No exit precedence, no drawdown circuit breaker · `REPORTED`

`MAX_SESSION_TRADES = 10` is a trade-count throttle, not a P&L stop. There is
nothing comparable to our `EXPIRY_GUARD → INVALIDATION_BREACHED → STOP_LOSS →
SESSION_STOP → PROFIT_CAPTURE` ordering. ATR is computed and handed to the model
as context but **never used programmatically** — the stop is a flat 4%
regardless of the symbol's actual volatility.

### `RA-016` No backtesting, and the README says so · `VERIFIED`

No backtester exists. Unlike the winner, they did not fabricate one — the README
states plainly:

> *"Formal historical backtesting and independent validation remain areas for
> further development."*

It also carries a Safety and Risk Disclaimer and declines to claim any
performance figure. **On intellectual honesty, TradePilot is closer to us than
to the winner**, and both of us are far ahead of first place.

### `RA-017` No market-hours check, and in-progress bars · `REPORTED`

No `get_clock`/`is_open` call anywhere. `StockBarsRequest(end=datetime.now())`
can return the still-forming daily bar, whose "close" is just the latest trade —
feeding RSI, MACD and ATR a non-final data point during the session. That is the
look-ahead exposure our `completed_daily_close` rule exists to prevent.

## 8. Product and presentation — where they beat us

### `RA-018` A deployed, clickable, multi-page product · `VERIFIED`

21 REST endpoints behind a 10-page React frontend: Landing, Register, Login,
Dashboard, Agents, Markets, Portfolio, ApiKeys, Settings, Demo. **20,495 lines**,
React + Vite + Tailwind + framer-motion. Live on Vercel and still up.

A judge does not clone anything. They click a link, see a landing page, register
an account, and watch an agent run. We asked them to read a read-only dashboard.

### `RA-019` A cinematic demo page with zero backend calls · `VERIFIED`

`src/pages/Demo.jsx` is **2,988 lines** implementing an eight-scene animated
sequence — Opening → Market → Scanner → AI → Agents → Risk → Execution →
Portfolio → Closing. A grep for `axios`, `fetch(`, `api.` inside it returns
**zero**.

It is a scripted marketing animation, publicly routed at `/demo`, not linked
from the sidebar. It exists to be filmed.

This is the single sharpest tactical lesson in either analysis. **They separated
"what the product does" from "what the video shows,"** and built a purpose-made
artefact for the second. We filmed our real application and spent the budget
fighting Streamlit's chrome.

### `RA-020` The README claims live charts that do not exist · `VERIFIED`

The README advertises *"Live market charts"* and *"Real-time market
information."* Searching the entire frontend for `lightweight-charts`,
`recharts`, `chart.js`, `WebSocket`, `EventSource` and `socket.io` returns
**zero files for every one of them**.

What exists instead is a hand-rolled inline SVG sparkline driven by polling —
effective, and cheaper than the winner's TradingView integration, but not what
was claimed.

### `RA-021` Hardcoded signals on the Markets page · `VERIFIED`

`src/pages/Markets.jsx:41-96` bakes signal strengths into source — `signal:
"Strong Buy", strength: 96`. Real Alpaca bars are mixed with invented conviction
scores, with no visual distinction. A judge with devtools open would see it.

## 9. Scale, and what it says

| | Lines | Commits | Tests |
|---|---|---|---|
| ALPHA HUNTER (1st) | 8,624 | 16 | 3 files |
| TradePilot (2nd) | 7,801 back + 20,495 front = **28,296** | 28 | **0 files** |
| **Options Alpha (ours)** | 21,428 | 73 | **8,538 lines** |

We wrote more test code than the winner wrote code in total. TradePilot, at
28,296 lines, has **no tests at all** — and placed second.

Two thirds of TradePilot's mass is frontend. That ratio is the finding.

## 10. What they did better

1. **They shipped a product a judge could use.** Landing page, registration,
   live URL, no clone required. Presentation and Business Value both.
2. **They built an artefact specifically for the video** (`RA-019`) instead of
   filming their application.
3. **A team of four** with named roles, against our one.
4. **SaaS shape** — auth, per-user keys, settings — which reads as a business
   even when, as here, the keys authenticate nothing (`RA-012`).
5. **A live autonomous loop** with real broker-side protective stops, fill
   polling, breakeven logic and emergency close. Ours produces a memo.
6. **A simpler story.** "Observe. Reason. Execute. Manage." is four words. Our
   pitch needs a paragraph before it lands.

## 11. What we did better

1. **We built for the actual track** (`RA-001`). The only options system in the
   top three.
2. **Durable provenance.** Their audit trail is 100 entries in RAM
   (`RA-007`); ours is a hash-linked chain that survives restarts.
3. **Real multi-tenancy or none.** Their auth gates a single shared account
   where any user can close another's positions (`RA-010`). We claimed
   single-user and were single-user.
4. **`SUBMITTED` is never `FILLED`**, and idempotency is derived from the intent
   hash (`RA-008`, `RA-009`).
5. **Tests.** 8,538 lines against zero.
6. **Look-ahead protection.** Our `completed_daily_close` rule against their
   in-progress bars (`RA-017`).
7. **An ablation we published against our own interest.** Neither entry above us
   attempted to falsify itself.

## 12. Lessons

The `WA-` document concluded that we optimised for being right while the
competition rewarded being legible. TradePilot sharpens that, because unlike the
winner they were *also* largely right — and still beat us.

1. **The thesis was never the problem.** They won second with our argument,
   stated in plainer words, wrapped in a product. Our differentiation was real
   but our delivery was not competitive.
2. **Build the demo artefact separately** (`RA-019`). A purpose-built,
   backend-free demo scene is not dishonest if the real system also exists — it
   is just recognising that a five-minute video is a different medium from an
   application.
3. **Deploy something clickable, with a front door.** A landing page and a login
   cost a day and change the first ten seconds of every judge's experience.
4. **Ship with a team.** Four contributors covering full-stack, data, research
   and AI logic produced 28,296 lines in five days.
5. **Say it in four words.** "Observe. Reason. Execute. Manage."
6. **Do not assume the track name describes the scoring** (`RA-001`). Both
   entries above us ignored options entirely. Building the harder, on-topic
   thing earned nothing visible — which is worth knowing in advance next time,
   not resented afterwards.

## 13. Responsible disclosure

`RA-011` concerns a real-format HS256 signing key committed in `.env.example`,
and `RA-010` a multi-tenancy flaw where any registered user can act on another's
positions. Both are in a public repository belonging to a third party. Values are
masked here and nothing was extracted.

If this is reported, the recommended framing is: regenerate the example
`SECRET_KEY` to an obvious placeholder, and either scope the Alpaca client
per-user or state plainly that the deployment is single-account.

**No mutating endpoint was called, no account was registered, and no trade was
submitted during this analysis.** Only read-only `GET` requests were made against
the live deployment.
