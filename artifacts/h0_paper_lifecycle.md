# H0 Paper Lifecycle Evidence

Recorded 28 August 2026 from a verified Alpaca Paper account whose identifier is
redacted from public evidence. No live endpoint was contacted; the gateway
verifies the resolved Paper endpoint immediately before every write.

## Lineage

| Stage | Value |
|---|---|
| Snapshot | `spy-lifecycle-20260828T154747Z` |
| Decision hash | `sha256:c418fac02a1464f6979e96666d1d4efc648c007260f7d1c340394cf0d54f1517` |
| Open intent hash | `sha256:82f1b3334159eb8b9ab8689cd93356f0ef1123faa8fa210b2ad067ddeb28b20d` |
| Open request hash | `sha256:bf2e48de34539a20dbe76a651a9365331e23f51b7a1609d9408ec3c3c7fbb31f` |
| Open client order id | `oa-82f1b3334159eb8b9ab8689cd933` |
| Close intent hash | `sha256:82e515d1aa4f6fd6494f91e26a9b5cac2eaeb4f723734568db1d5bdd19cb57e9` |
| Close client order id | `oa-82e515d1aa4f6fd6494f91e26a9b` |

The client order id is the first 28 hex characters of the intent hash. It is
derived, never generated, which is what makes a retry after an ambiguous
response idempotent rather than duplicative.

## Broker result

| Order | Class | Status | Qty | Limit | Filled avg |
|---|---|---|---|---|---|
| Open `oa-82f1b333…` | `mleg` | filled | 1 | 3.39 | **3.13** |
| Close `oa-82e515d1…` | `mleg` | filled | 1 | 3.05 | **3.06** |

Legs, open: buy `SPY260911C00772000` @ 6.90, sell `SPY260911C00778000` @ 3.77.
Legs, close: sell `SPY260911C00772000` @ 6.87, buy `SPY260911C00778000` @ 3.81.

Final broker observation: **0 open positions**, equity 100000.00 → 99992.90.

## What this demonstrates, and what it does not

It demonstrates that an approved decision reached the broker as the exact bytes
that were approved, that both legs filled as one strategy, and that the broker
was later observed flat.

It does **not** demonstrate durable local reconciliation. The current manual
lifecycle command persists the approved intent, prepared request, and initial
broker response with `filled_quantity=0`. It prints an immediate lookup for the
open order but does not apply that result to stored fills or positions, and it
does not reconcile or persist the close before returning. The filled prices and
flat result in this artifact are observed Paper evidence assembled for the
watched demonstration, not proof that the autonomous worker can reconstruct the
same lifecycle after restart.

It also demonstrates nothing about profitability. The round trip realized **-7.10**,
which is the cost of crossing the spread twice on a single contract. That is the
expected result of opening and immediately closing a position, and it is the
friction the null hypothesis in the signal specification says must be beaten
before any edge can be claimed. One round trip is not evidence either way.
