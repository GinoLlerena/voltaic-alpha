# Options Alpha

## Submission Narrative, Business Case, and Rubric Mapping

| Field | Value |
|---|---|
| Version | v0.1 |
| Phase | 6 |
| Team | Voltaic Alpha |
| Track | Options Alpha Agents |
| Repository | `github.com/GinoLlerena/voltaic-alpha` (public before submission, `F-J`) |

## 1. The claim, in one sentence

An LLM can write the memo and still be structurally unable to pick the
direction, move the stop, size the risk, choose the contracts, or reach the
broker — and every one of those boundaries is demonstrable from recorded
evidence rather than asserted in a slide.

## 2. Why this is not "LLM plus guardrails"

That phrase usually describes a system where the model proposes and a validator
checks. Checks can be removed, bypassed, or quietly loosened, and nothing in the
artifact tells you whether that happened.

Four differences, each one testable:

| | Usual pattern | This build |
|---|---|---|
| Invalidation | Model proposes, code validates it did not change | Model **never receives** invalidation and has no schema field for it. There is no path to bypass |
| Direction | Model chooses, code sanity-checks | Deterministic setup owns direction. A reversal is **coerced to abstention** and recorded as an attempt |
| Idempotency | Retry helper generates an id | Client order id is the **first 28 hex of the intent hash**. A duplicate submit collides at the broker |
| Failure | Degrades or retries | Every model failure resolves to a neutral thesis and therefore `NO_TRADE`. There is no "submit anyway" branch |

The strongest of these is the first. A check can be deleted in a refactor and the
tests still pass; an absence cannot be bypassed at all.

## 3. What actually ran

- Live read path against Alpaca Paper `PA3WZR22ITRR`: account, clock, 277 `sip`
  daily bars, a 5-page option chain, each with provider, feed, source time,
  receipt time, page count, and payload hash.
- One qualified SPY case and one refusal, replayed to identical decision hashes.
- Model ablation over three frozen cases against `gpt-5.6-terra`.
- One Paper MLeg lifecycle: open filled at 3.13 against a 3.39 limit, close at
  3.06, reconciled to zero open positions.

## 4. The uncomfortable numbers, stated plainly

The round trip realized **-7.10**. The model changed **zero** decisions across
three cases. Neither is hidden, because both are the honest result and hiding
them would undermine the only claim being made.

- `-7.10` is the cost of crossing the spread twice on one contract. It is the
  friction any real edge would have to clear, and it is the reason the
  null hypothesis is stated as the default rather than as a caveat.
- "The model changed nothing" is what an ablation is for. A system that cannot
  produce that answer is not measuring anything.

## 5. Business case

**Who has this problem.** Teams shipping agentic trading applications must
answer a compliance or risk reviewer asking: what exactly did the model decide,
and what could it have decided? Today that answer is usually a prompt, a log
file, and a promise.

**What this is.** An execution and audit layer that sits between a model and a
broker. The model's contribution is bounded and recorded; authority stays in
deterministic code; and every order carries a hash chain back to the observation
that justified it.

**Why it is worth money.** The expensive failure in this domain is not a bad
trade, it is an unexplainable one. A firm that cannot reconstruct why an
automated system acted cannot defend it to a regulator, an investor, or an
insurer. Reconstruction is exactly what this produces, and it is cheaper to
build in than to retrofit.

**Where it goes next.** The layer is broker- and strategy-agnostic by
construction: `MarketDataGateway`, `ThesisSynthesizer`, and the execution port
are protocols. SPY verticals are the demonstration, not the product.

## 6. Rubric mapping

| Criterion | Evidence |
|---|---|
| **Application of Technology** | Alpaca Trading API for execution and market data, `alpaca-py` MLeg native multi-leg orders, OpenAI Responses API with strict structured output and `store=False`, PostgreSQL audit schema, deterministic hash lineage. A read-only client built so it *cannot* express a write, and a CI guard that parses the AST to keep it that way |
| **Presentation** | Five judge views reconstructing one decision end to end, including the exact bytes sent to the broker. Disclosures on every page |
| **Business Value** | Section 5. The buyer is a team that must explain an automated decision to someone with authority over them |
| **Originality** | Hash-linked evidence-to-intent-to-request lineage, a reproducible refusal, derived-id idempotency, ambiguous-write recovery by lookup, and a published ablation that reports the model changed nothing |

P&L is not a published criterion and is not presented as a result.

## 7. Deck outline (10 slides)

1. **The problem** — an automated trade nobody can explain afterwards.
2. **The uncomfortable question** — "what could the model have decided?"
3. **The firewall** — one diagram: evidence → setup → memo → risk → intent →
   request → broker, with the model touching exactly one box.
4. **What the model never sees** — invalidation, sizing, eligibility, execution.
5. **Live refusal** — the contradiction case, refused before the model was asked.
6. **Hash lineage** — decision hash → intent hash → request hash → filled order.
7. **The Paper lifecycle** — real fills, reconciled to flat, `-7.10` friction.
8. **The ablation** — the model changed zero decisions; why we published that.
9. **Business case** — who buys an audit layer, and why retrofitting is worse.
10. **Limits** — Paper only, indicative feed, one setup, no alpha claim.

## 8. Video script beats (5 minutes maximum, MP4)

| Time | Beat |
|---|---|
| 0:00–0:30 | The problem, stated as a question a risk reviewer asks |
| 0:30–1:15 | Architecture in one diagram; where model authority ends |
| 1:15–2:15 | Live: qualified case through all five views |
| 2:15–3:00 | Live: refusal case, and that no model call was made |
| 3:00–4:00 | Hash lineage to the filled Paper order, reconciled to flat |
| 4:00–4:30 | Ablation result, including that the model changed nothing |
| 4:30–5:00 | Limits and the no-alpha claim, stated out loud |

Open with the demo, not the team. The refusal is the most persuasive thirty
seconds in the video and should not be cut for time.

## 9. What we would not claim

- That the strategy has edge. One round trip and three ablation cases cannot
  support that, and the null hypothesis is stated as the default.
- That the indicative feed is trading-quality. It is not, and the dashboard
  says so wherever a quote appears.
- That the system is production-ready. It runs one setup, on one symbol, with
  one open strategy at a time, on Paper.
