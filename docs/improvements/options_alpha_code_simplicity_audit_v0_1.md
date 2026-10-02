# Options Alpha: Code Organization and Simplicity Audit

*A technical paper on keeping a personal trading project simple, modular, and safe*

| Field | Value |
|---|---|
| Version | 0.1 |
| Review date | 2 October 2026, America/Lima |
| Reviewed revision | `2d834c1` |
| Status | Audit and proposed refactoring plan; not an implemented refactor. Section 9 adds a verification and reprioritization review (2 October 2026) |
| Work prefix | `CSA-` |
| Scope | Python backend, React frontend, test organization, packaging, and operational entry points |

## Abstract

Options Alpha has useful module boundaries and strong executable safety checks,
but its organization has not fully caught up with its growth from a hackathon
experiment to a persistent personal application. The principal problem is not
an excessive number of frameworks or interfaces. It is a combination of
concentrated responsibilities, overlapping application generations, duplicated
state coordination, and operational tools that depend on other operational tools.

The recommended approach is a sequence of small, behavior-preserving changes:
establish one supported continuous runtime; extract observation and position
management from the main agent; isolate the historical experiment; consolidate
the duplicated pagination lifecycle; reduce repeated decision read-model loading;
and clarify deployment and dependency ownership. Keep deterministic risk,
execution authority, transaction boundaries, public-data redaction, and typed
contracts explicit. These protections are not boilerplate.

The objective is **fewer places to understand and change one behavior**, not
the smallest possible line count or a new architecture framework.

## 1. Method, evidence, and limitations

This paper combines source inspection, Python AST inventory, import/reference
searches, targeted offline tests, lint/type checks, and a local SQL-query probe.
It is an engineering audit, not an exhaustive security certification, profitability
assessment, production performance benchmark, or full coverage report.

Only the paper is added to the repository. No application source, dependencies,
database schema, deployment configuration, or trading policy was changed. The
pre-existing untracked `.claude/` directory was left untouched. No production
endpoint, cloud operation, broker operation, or paid model call was exercised.
Diagnostic commands may update ordinary ignored test/type-check caches.

Evidence labels used below:

- **Verified source:** directly present in the reviewed code.
- **Measured:** observed by an explicitly described local diagnostic.
- **Inferred risk:** a consequence of the control flow that was not reproduced
  as a production incident during this review.
- **Recommendation:** proposed future work, not an existing capability.

### 1.1 Inventory

Physical line counts include comments, blank lines, and docstrings. They identify
review targets, not quality scores. Generated frontend API types and installed
dependencies are excluded from the frontend discussion.

| Area | Measured size | Interpretation |
|---|---:|---|
| Python application package | 71 Python files; 17,861 lines | Small enough to remain one application |
| `agent.py` | 1,466 lines | Multiple operational responsibilities in one module |
| `execution/lifecycle.py` | 921 lines | State types, persistence, observations, exits, and incidents |
| `persistence/models.py` | 842 lines | Database schema; length alone is not a refactoring reason |
| `api/dto.py` | 596 lines | Public contract; explicit fields protect the boundary |
| `api/server.py` | 535 lines | App setup, dependency closures, routes, mappings, static serving |
| `worker.py` | 529 lines | Lease, health, composition, CLI, and scheduling |
| Streamlit `app.py` | 914 lines | A second maintained presentation surface |
| Frontend `app.test.tsx` | 1,105 lines | Many unrelated journeys and fixtures in one test module |
| Backend `test_agent.py` | 1,086 lines | Test cases also serve as shared fixture infrastructure |

The frontend has only three direct production dependencies in its manifest:
React, React DOM, and TanStack Router. A dependency-heavy frontend framework is
not the source of the present organization problem.

### 1.2 Verification performed

| Check | Result | Boundary |
|---|---|---|
| Targeted backend suite | 251 tests passed | Nine selected files, listed in Appendix A; SQLite harness, not PostgreSQL |
| Frontend unit/component suite | 124 tests passed across four files | Repeated React `act(...)` warnings appeared |
| Ruff | Passed | `src`, `scripts`, `tests`, and `app.py` |
| Mypy | Passed; reported 72 source files | Does not establish that existing `Any` boundaries are well designed |
| Frontend TypeScript check | Passed | Existing project script |
| Frontend ESLint | Passed | Existing project script |
| Decision API SQL probe | Eight HTTP 200 responses; 78 SQL statements | One committed fixture decision, local TestClient, fixed source |

Not run: the complete backend suite, browser/visual regression suites, production
load tests, container builds, PostgreSQL lifecycle tests, dependency-removal trials,
or deployment commands. Green checks do not negate the maintainability findings.

## 2. What should remain simple—and what should remain explicit

The project already has a useful deterministic decision sequence in
[architecture/workflow.py](../../src/options_alpha_lab/architecture/workflow.py):
observe, qualify, synthesize a bounded thesis, select a structure, evaluate risk,
and return a decision. The workflow rejects unknown evidence references,
direction reversal, and changed invalidation conditions.

Other worthwhile boundaries include:

- [Execution gateway](../../src/options_alpha_lab/execution/gateway.py): broker-write authority and last-moment guards.
- [Lifecycle store](../../src/options_alpha_lab/execution/lifecycle.py): durable transitions and transaction ownership.
- [Public DTOs](../../src/options_alpha_lab/api/dto.py) and [mappers](../../src/options_alpha_lab/api/views.py): redaction, money serialization, and explicit public fields.
- [Source resolution](../../src/options_alpha_lab/presentation/source.py): provenance and labelled fallback.
- [Resource states](../../frontend/src/components/ResourceState.tsx): loading, failed, stale, and verified content.
- Generated OpenAPI/TypeScript contracts and the existing safety-boundary tests.

Do not combine domain objects, ORM rows, and public DTOs merely because some
fields overlap. They have different responsibilities and exposure rules.
Similarly, validations at input, decision, and execution boundaries can be
deliberate defense in depth, not accidental duplication.

The earlier UI audit's request-key isolation and false-empty-state findings
have received changes in the current code. This paper does not repeat those
historical defects as if nothing had changed.

## 3. Findings

Priorities are refactoring priorities: **P1** addresses divergent operational
behavior or a prerequisite safety gap; **P2** addresses material maintenance cost;
**P3** is cleanup after the higher-value work. They are not vulnerability ratings.

### CSA-001 — Two continuous runtimes have different guarantees [P1]

**Verified source.** [agent.py](../../src/options_alpha_lab/agent.py), lines
1291–1314 and 1324–1453, contains its own scheduler and CLI. Its `--ticks 0`
path schedules `tick()` through APScheduler. Separately,
[worker.py](../../src/options_alpha_lab/worker.py), lines 240–529, acquires a
worker lease, maintains health/heartbeat state, and invokes order, position,
and review clocks between strategy ticks.

Both construct substantially similar clients, model reviewers, stores,
reconcilers, and gateways, but the continuous behavior is not equivalent.
The agent CLI does not acquire the worker lease or run those between-tick clocks.
The one-shot entry point is useful; the second continuous runtime is the problem.

**Inferred risk.** An operator can choose a valid-looking invocation that lacks
the runtime protections of the supported worker. This is not a finding that
the execution gateway itself can be bypassed or that both processes are running.

**Recommendation.** Make the worker the single supported continuous runner.
Keep a clearly named one-shot command if needed. Share construction through one
small composition function, while keeping replay/rehearsal construction separate
where their safety requirements differ. Before changing entry points, characterize
lease behavior, fast-clock behavior, write-mode restrictions, and shutdown.

Do not replace this with a scheduler framework or a dependency-injection container.

### CSA-002 — The agent is a coordinator and several subsystems [P2]

**Verified source.** [agent.py](../../src/options_alpha_lab/agent.py) owns provider
observation, workflow construction, reconciliation coordination, multi-position
management, valuation/exit handling, intent reconstruction, recording, scheduling,
and CLI setup. `_manage_open_position` spans 190 physical lines, `manage_positions`
143, and `_consider_entry` 145.

**Impact.** Changes to provider data, exit policy application, persistence
metadata, or runtime startup all require understanding the same large object.
Mutable fields such as `run_id`, `decision_row_id`, `last_cycle`, and
`_cycle_ticks` couple operations across method calls.

**Recommendation.** Extract cohesive behavior, not individual methods:

1. Runtime construction and scheduling out of `TradingAgent`.
2. Observation into an `observation.py` module returning the already defined
   `Observation` contract.
3. Position-cycle and exit coordination into `position_management.py`, with
   an explicit result rather than hidden scratch state where practical.

Leave `TradingAgent.tick()` as a readable coordinator. Preserve reconciliation
and deadline handling before new risk, management of every owned position,
and the existing single-entry constraint. This is not authorization to implement
portfolio-entry expansion from a separate roadmap.

### CSA-003 — The historical experiment is still the package's front door [P2]

**Verified source.** [__init__.py](../../src/options_alpha_lab/__init__.py) exports
the original `run_experiment`. The older [models.py](../../src/options_alpha_lab/models.py),
[agents.py](../../src/options_alpha_lab/agents.py),
[risk.py](../../src/options_alpha_lab/risk.py), and
[orchestrator.py](../../src/options_alpha_lab/orchestrator.py) coexist with
production contracts, components, and workflow. They are still referenced by
the legacy CLI and tests; they are not proven dead code.

For example, the older `Direction` has bullish/bearish values, while the production
contract also represents neutral. Both generations define a `Thesis`, with
different semantics. The older fixture includes an expected direction; that
must not become production input through a careless unification.

**Recommendation.** Put the historical experiment behind an explicit `legacy/`
namespace or an equivalently clear boundary. Retain compatibility entry points
only where a known caller needs them, and document their retirement criteria.
Remove the implicit legacy import from the package initializer after checking
public callers. Do not merge the old and new types to reduce the file count.

### CSA-004 — Interfaces exist, but the live coordinator bypasses some of them [P2]

**Verified source.** [architecture/ports.py](../../src/options_alpha_lab/architecture/ports.py)
defines a useful `ThesisSynthesizer`, yet `TradingAgent.__init__` accepts its
synthesizer and recorder as `Any`. `_consider_entry`, starting at line 1129,
mutates `synthesizer.last_call` and reads metadata with `getattr`.
[DecisionRecorder.record_decision](../../src/options_alpha_lab/persistence/repository.py)
also accepts `model_call` and `structure` as `Any`.

Repository reference searches found `MarketDataGateway` and `DecisionRepository`
only at their declarations. The real recorder has a different, richer contract.
These two protocols are candidates for removal, not reasons to force another
adapter layer into production.

**Recommendation.** Use precise types for collaborators actually exchanged.
Give model-call metadata an explicit contract or small evaluation result rather
than requiring an undeclared mutable attribute. Use a concrete recorder type
unless substituting implementations genuinely requires a protocol. Keep external
provider payloads flexible at their boundary, then normalize them once.

Do not introduce one interface per class. Keep interfaces where there are actual
alternatives, test substitutions, or authority boundaries.

### CSA-005 — Decision presentation repeats expensive aggregate loading [P2]

**Verified source and measured.**
[Decision.tsx](../../frontend/src/routes/Decision.tsx) independently polls eight
decision endpoints. Most routes in [server.py](../../src/options_alpha_lab/api/server.py)
load the full [DecisionView](../../src/options_alpha_lab/presentation/decision.py),
even when they return only one part of it.

A local probe attached a SQLAlchemy statement listener after resolving a fixed
committed source and selecting its newest decision. It then requested each
endpoint once through FastAPI TestClient:

| Endpoint suffix | SQL statements |
|---|---:|
| `summary` | 14 |
| `market` | 10 |
| `memo` | 10 |
| `structure` | 10 |
| `risk` | 10 |
| `lifecycle` | 11 |
| `proof` | 10 |
| `outcomes` | 3 |
| **Total** | **78** |

This is one fixture's query count, not production latency, a worst-case count,
or a load-test result. A live resolver and other record shapes can differ.

**Recommendation.** First add a repeatable query-budget test. Then prefer one
screen-oriented read endpoint that loads shared records once and maps explicit
sections, while retaining existing routes until their consumers migrate. This
matches how the current decision page consumes the data. Alternatively, keep
independent routes but give them narrow loaders; do not implement both approaches
without a demonstrated need.

Keep per-section unavailable/absent distinctions, public redaction, and source
metadata. A single response establishes shared request provenance but does not
by itself promise transaction-level snapshot consistency. Avoid a global cache,
GraphQL layer, or generic endpoint-generation framework for this cleanup.

### CSA-006 — Pagination state is duplicated, including its race risks [P2]

**Verified source.** [ActivityFeed.tsx](../../frontend/src/components/ActivityFeed.tsx),
lines 25–58, and `History` in [Decisions.tsx](../../frontend/src/routes/Decisions.tsx),
lines 82–113, duplicate extra-page storage, cursor management, loading/errors,
pause-on-browse, reset, and asynchronous append logic.

**Inferred risk.** When browsing older pages, a pending `more()` request can
finish after `newest()` resets the view and append its obsolete result. Neither
copy associates that continuation with a reset generation. Pausing polling also
does not cancel an already-issued first-page request. These races were identified
by control-flow inspection, not reproduced in the audit's existing test run.

**Recommendation.** Add delayed-response tests first, then one focused
`useCursorPage` hook for these two consumers. It should own reset/request identity,
abort or ignore obsolete requests, preserve page source envelopes, and keep the
server's ordering/cursor semantics. Leave rendering in the two components.

Do not replace all fetching or introduce global state management merely to remove
this duplication. The recently improved `useResource` is a useful existing seam.

### CSA-007 — Source identity is represented by a display label [P2]

**Verified source.** [ResourceState.tsx](../../frontend/src/components/ResourceState.tsx),
lines 85–99, compares `source_label` to detect incompatible sources.
[Resolver.current](../../src/options_alpha_lab/presentation/source.py) includes
the current decision count in that label.

**Inferred consequence.** Two requests to the same database can be labelled
`live worker database (201 decisions)` and `live worker database (202 decisions)`
and be reported as different sources. Conversely, a display label is not a robust
identifier for distinguishing datasets. This is a contract-design issue, not a
reason to remove provenance warnings.

**Recommendation.** Add a stable, non-secret source identity to the public
contract and compare that plus decision correlation where appropriate. Keep
counts and explanatory labels as display data. Never expose a database URL or
credentials as the identity. Test both same-source count changes and actual
live/frozen source changes.

### CSA-008 — Operational reuse is hidden inside command scripts [P2]

**Verified source.** [ship_host.py](../../scripts/ship_host.py) imports
`deploy_react` and `resize_trial`; [deploy_react.py](../../scripts/deploy_react.py)
also imports `resize_trial`. Generic cloud transport, transfer, and safety helpers
are therefore owned by command-specific scripts. These files also carry host/path
configuration and substantial generated remote-shell content.

**Impact.** A change to a trial-specific script can affect routine deployment.
The host deploy and UI deploy have different payload scopes; neither should
silently become a universal mutator while extracting helpers.

**Recommendation.** Extract the already shared, tested transport and transfer
functions into a small operational support module, for example `scripts/_lib/`.
Keep each CLI explicit about its allowed targets, dry-run behavior, restart
authority, rollback, and verification. Centralize genuinely shared configuration,
but do not introduce a cloud plugin system or a generic deployment engine.

### CSA-009 — Legacy presentation and packaging obscure the current product [P2]

**Verified source.** React and Streamlit both remain maintained. The
[Dockerfile](../../Dockerfile) starts Streamlit; systemd also retains the
[dashboard service](../../deploy/systemd/options-alpha.service). The React deploy
checks Streamlit health and supports rollback to it. It is therefore unsafe to
treat `app.py` as unused just because React is the main UI.

The Dockerfile copies `uv.lock`, but installs with `uv pip install --system .`;
that command does not select the project lockfile as the installation plan.
CI uses `uv sync --frozen`, and host requirements have a separate lock-export
consistency test. These installation paths have different reproducibility properties.

**Recommendation.** Declare React the primary UI and explicitly decide whether
Streamlit remains a rollback surface, a local diagnostic, or a retirement target.
Keep it working until that decision and rollback replacement are approved.
Make the container's installation demonstrably lock-driven and test its role
separately; do not silently change the image from Streamlit to React in a cleanup PR.

Direct source-import searches did not find uses of `openai`, `jinja2`, `plotly`,
or `pythonjsonlogger` in the inspected Python application/tests/scripts. The
model transport currently uses HTTPX. These are **dependency-review candidates**,
not proven removable transitive packages: inspect dependency relationships,
scripts and optional workflows, then test a clean install before removing a
direct declaration. APScheduler remains used by the alternative runtime until
CSA-001 is resolved. Keep generated `requirements.txt` when hosts require it;
its consistency test is useful, not needless duplication.

### CSA-010 — Test helpers and acceptance suites are entangled [P2]

**Verified source and measured.**
[test_task1_acceptance.py](../../tests/test_task1_acceptance.py),
[test_learning_capture.py](../../tests/test_learning_capture.py), and
[test_lifecycle_e2e.py](../../tests/test_lifecycle_e2e.py) import fixtures/classes
from `test_agent`. Other tests import helpers from `test_reconcile`.
The frontend's [app.test.tsx](../../frontend/src/__tests__/app.test.tsx) combines
large fixtures with 69 tests. Its run passed but emitted repeated `act(...)` warnings.

**Recommendation.** Move only shared builders, fake clients, and database setup
to test-support modules. Test modules should not act as infrastructure libraries
for other test modules. Split frontend tests by user journey/resource behavior
and extract their common fixture builder. Fix or narrowly explain async warnings;
do not globally silence stderr or remove assertions to obtain a clean log.

Avoid elaborate fixture factories, deep test-class inheritance, and identical
end-to-end setup for pure-function tests. Keep explicit scenarios for partial fills,
ambiguous submissions, restarts, and multi-position management.

### CSA-011 — PostgreSQL exists in CI, but not for the new lifecycle harness [P1 prerequisite]

**Verified source.** [CI](../../.github/workflows/ci.yml) provides `DATABASE_URL`
and runs a PostgreSQL replay. The newer [pgsupport.py](../../tests/pgsupport.py)
harness switches its tests to PostgreSQL only through
`OPTIONS_ALPHA_TEST_DATABASE_URL`, which is not set by that workflow. Therefore
the existence of a PostgreSQL service does not mean those lifecycle/acceptance
tests exercise PostgreSQL row ordering and locking.

**Recommendation.** Add a deliberately scoped PostgreSQL job for the lifecycle,
reconciliation, and multi-position acceptance tests before changing their store
or runtime boundaries. Use a disposable test service and suitable permissions;
the helper creates per-test databases. Preserve the faster SQLite lane. Do not
point that helper at an operator or production database.

This is not a claim that all CI database testing uses SQLite: PostgreSQL replay
already exists. It is a specific gap in the affected harness.

### CSA-012 — Documentation and naming preserve multiple eras [P3]

**Verified source.** The [README](../../README.md) still leads with the judge
dashboard and historical interaction lab, while the repository now contains a
React personal workspace and a persistent worker. Names such as `agent`/`agents`,
root `models`/ORM `models`/`contracts`, and root `lifecycle`/execution `lifecycle`
require contextual knowledge to navigate.

**Recommendation.** Add a short current-state map and list the supported commands,
then link historical plans under an explicitly historical heading. Document
which service runs continuously and which command is a one-shot or demo. Rename
ambiguous modules only when touching their boundary; do not mix a repository-wide
rename with behavior changes. Move historical rationale to short decision notes
where appropriate, retaining comments explaining safety invariants beside the code.

## 4. Minimal target organization

This is an ownership map, not a mandate to create every directory now. Existing
imports should remain stable until the corresponding bounded change is tested.

```text
src/options_alpha_lab/
  architecture/          existing pure contracts and decision workflow
  components.py          deterministic strategy implementations; retain for now
  observation.py         extracted provider-to-snapshot orchestration
  position_management.py extracted management-cycle/exit coordination
  agent.py               thin observe/manage/consider-entry coordinator
  runtime.py             one explicit live-component construction function
  worker.py              single supported continuous runtime
  execution/             gateway, intents, requests, reconciliation, lifecycle
  persistence/           schema and decision recording
  providers/             external adapters and bounded model reviewer
  presentation/          read models; no broker/model authority
  api/                   HTTP boundary, DTOs, explicit public mapping
  legacy/                historical synthetic interaction workflow

frontend/src/
  api/                   generated contracts, request and cursor-state hooks
  routes/                screen composition
  components/            reusable presentation components
  test/                  shared fixture builders and test setup

scripts/
  _lib/                  only genuinely shared operational support
  <commands>.py          explicit, separately authorized operational commands

tests/
  support/               shared builders/fakes, not executable test cases
  test_*.py              behavior-focused tests
```

No microservices, event bus, repository-per-table pattern, generic service base
class, provider plugin registry, or frontend state framework is justified by this
audit. A single-process modular application remains appropriate.

Keep the useful distinction between `DecisionRecorder` and `LifecycleStore`:
decision evidence and execution lifecycle writes have different transaction
semantics. A long explicit recorder is often safer than a reflection-based generic
mapper. Extract local helpers within its transaction if readability improves;
do not turn one atomic operation into several independently committed calls.

The two stores also repeat a small commit/rollback/close context manager. That
is a lower-value simplification candidate than runtime divergence or pagination.
Use an existing SQLAlchemy transaction primitive if equivalent; do not create a
new universal repository abstraction to save a few lines.

## 5. Working rules for future changes

1. **One behavior, one owner.** Identify where a policy or state transition lives
   before adding a second implementation.
2. **Prefer functions and explicit composition.** A class is appropriate when it
   owns state or a resource; a protocol when an actual boundary needs substitution.
3. **Extract cohesive responsibilities, not arbitrary line counts.** A large DTO
   file and a large orchestrator are not the same problem.
4. **Share repeated state machines.** Pagination lifecycle is a better extraction
   candidate than two superficially similar financial rules.
5. **Keep contracts explicit.** Do not replace public allowlists with automatic
   ORM serialization or erase domain distinctions to reduce mapping code.
6. **Separate behavior changes from moves.** Preserve existing hashes, reason
   codes, ordering, policy versions, and APIs during structural refactors unless
   an independently reviewed contract change is intended.
7. **Do not add a dependency to move code around.** Adopt one only when measured
   simplification exceeds the integration and maintenance cost.
8. **Retire deliberately.** Check callers, commands, services, rollback, and tests
   before deleting an older path.
9. **Make uncertainty visible.** Unknown, unavailable, stale, and empty must remain
   distinct after simplifying code.

## 6. Proposed delivery sequence

Each row is a bounded change or small series, not one large refactor PR.

| Stage | Scope | Required exit evidence |
|---|---|---|
| 0 — Establish the baseline | Current-state map; test-support extraction; PostgreSQL lane for affected tests | Existing behavior passes SQLite and relevant PostgreSQL tests; no application behavior changes |
| 1 — One runtime | Shared explicit construction; designate worker as continuous runner; deprecate or redirect alternate continuous CLI | Lease, shutdown, fast clocks, and authority tests; no duplicate setup logic for live startup |
| 2 — Thin agent | Extract observation, then position management in separate changes; tighten collaborator types | Replay outputs and authority boundaries unchanged; exits/management still precede entries; all managed positions covered |
| 3 — Coherent read/UI state | Query-budget test and chosen read-loading fix; separately fix source identity and share cursor lifecycle | Measured query reduction; source-change, delayed-page, reset, and stale/error tests; OpenAPI types regenerated where necessary |
| 4 — Remove historical friction | Isolate legacy experiment; extract operational helpers; review direct dependencies and container installation | Commands retain documented semantics; dry-run/rollback tests pass; clean locked installs; no unapproved retirement |
| 5 — Review optional cleanup | Reassess smaller modules, comments, and names after earlier stages | Demonstrable reduction in change locations or navigation effort, not merely lower line count |

Do not combine store transaction changes with gateway behavior changes. Do not
combine deployment-helper extraction with a production deployment. Keep trading
strategy development, provider replacement, and portfolio expansion out of these PRs.

## 7. Acceptance criteria

The cleanup is successful when:

- A new contributor can identify the production entry point and trace a decision
  from snapshot to risk gate without first learning the historical experiment.
- Exactly one documented continuous runtime owns the lease and required clocks.
- A position-management change does not require editing provider observation or
  CLI composition, except when its contract explicitly changes.
- Activity and decision history share one tested pagination lifecycle, including
  reset-versus-pending-request behavior.
- Decision-page query work is measured and reduced without losing provenance,
  redaction, or the distinction between absence and failure.
- Source identity remains stable when display counts change and changes when the
  underlying evidence source changes.
- Test modules no longer depend on other test modules for shared builders.
- Dependency and deployment entry points clearly declare their role and preserve
  lockfile reproducibility and operational permission boundaries.
- Existing authority, reconciliation, restart, partial-fill, and multi-position
  management regressions remain green on the databases relevant to deployment.

Not success criteria: a universal maximum file length, elimination of every
repeated line, fewer safety checks, more interfaces, or a fashionable directory tree.

## 8. Conclusion

The user's concern is supported by the code, but a rewrite would attack the
wrong problem. The application has a solid deterministic core and substantial
regression protection. Its largest organizational costs are accumulated around
that core: competing runtimes, a broad coordinator, mixed historical and current
entry points, duplicated client-side state, repeated read-model work, and script
coupling.

The recommended policy is **simplify coordination while preserving explicit
boundaries**. Start with one runtime and a thinner agent, not more layers. Treat
contracts, persistence integrity, and trading authority as assets to preserve.

## 9. Review addendum — verification and reprioritization (2 October 2026)

A second review checked the findings against revision `2d834c1` and the
running deployment. The findings stand. This addendum changes priorities and
delivery order, adds two observations, and records which claims were
independently confirmed. Sections 1–8 are unchanged.

### 9.1 Independent verification

| Finding | Check performed | Result |
|---|---|---|
| CSA-001 | `agent.py` imports APScheduler for `--ticks 0` and has no lease; the systemd units start only `options_alpha_lab.worker` | Confirmed |
| CSA-003 | `__init__.py` exports only `run_experiment` from `orchestrator` | Confirmed |
| CSA-004 | `MarketDataGateway` and `DecisionRepository` appear only in `architecture/ports.py`; `TradingAgent` takes `synthesizer: Any` and `recorder: Any` and mutates `last_call` | Confirmed |
| CSA-006 | `History` in `Decisions.tsx` copies `ActivityFeed`'s paging, including the reset-versus-pending race. The copy was introduced by PUI Phase 3 (PR #61) | Confirmed |
| CSA-007 | `Resolver.current` puts the decision count in `source_label`; `Loaded` compares labels and renders `source-mismatch` | Confirmed; see 9.2 |
| CSA-009 | `openai`, `jinja2`, `plotly` and `python-json-logger` are declared in `pyproject.toml` with no imports in `src`, `tests`, `scripts` or `app.py`; the Dockerfile runs `uv pip install --system .` | Confirmed |
| CSA-010 | `test_lifecycle_e2e.py`, `test_learning_capture.py` and `test_task1_acceptance.py` import from `test_agent` | Confirmed |
| CSA-011 | `OPTIONS_ALPHA_TEST_DATABASE_URL` is read by `tests/pgsupport.py` and set nowhere in `.github/workflows/` | Confirmed |
| CSA-005 | 78-statement probe | Not reproduced; plausible from the per-route `DecisionView` loading |

### 9.2 Priority changes

**CSA-007: raise from P2 to P1.** The consequence is not hypothetical. The live
worker records a decision every few minutes during a session, and each of the
decision page's eight resources refreshes on its own 15-second interval. A
refresh that straddles a new decision returns `live worker database (N+1
decisions)` beside panels still labelled `(N decisions)`. The page then states
that the panel "came from a different source … It may not describe the same
record." That is a false provenance warning on the primary UI: the kind of
misleading operational information the PUI specification classes as P1. The
fix is small and additive: a stable, non-secret source identifier in the
envelope, compared in place of the label.

**CSA-001: lower from P1 to P2.** No deployed unit runs the agent's continuous
loop, and the runbook already forbids starting `options_alpha_lab.agent` on
the service. The remaining risk is an operator choosing the wrong command. A
one-line guard closes most of it: make `--ticks 0` refuse and name the worker.
Shared runtime construction can then move to CSA-002 rather than lead the plan.

**CSA-002: defer until a feature needs it.** It is the largest change and it
touches the trading core while the system is in observe mode collecting
evidence. Schedule it with the first change that must edit position
management (e.g. enabling Paper entries or multi-position work), after
CSA-011's PostgreSQL lane exists.

**CSA-005: keep P2, but schedule early.** Eight independently polled endpoints
at roughly 78 statements per page view, every 15 seconds per open tab, is
material on the 2-vCPU/2-GiB instance that also runs the worker and the
hourly backups. Measure first, as recommended. The worker's headroom is the
constraint that makes this more than tidiness.

### 9.3 Additional observations

- **A second deploy path survives inside CSA-008's scope.** `ship_host.py` is
  the one host deployment path (PRs #58–#60), but `deploy_react.py` still ships
  `api/server.py` and `api/limits.py` itself and restarts the API. Two tools can
  therefore change the same modules. Recommendation: `deploy_react.py` ships
  only `frontend/dist` and its port-80 cutover, and requires the host's API
  code to already match, as reported by `ship_host.py`.
- **Dependency removal has a security payoff.** Each unused direct dependency
  widens the `pip-audit` surface; the urllib3 CVEs of 30 September are the
  recent example. Removal needs a regenerated `requirements.txt` and a host
  deploy with `ship_host.py --install-deps`, outside the trading day.

### 9.4 Revised delivery order

This replaces the ordering, not the scope, of section 6. Each item is its own PR.

| Batch | Items | Why first |
|---|---|---|
| A — quick, verifiable wins | CSA-007 stable source identity; CSA-006 shared `useCursorPage` with delayed-response tests; remove the four unused dependencies; drop the legacy `__init__` export and the two unused protocols; `agent --ticks 0` refuses | Small, low-risk, and each removes a live defect or a measurable surface |
| B — prerequisites | CSA-011 PostgreSQL lane; CSA-010 test-support modules; CSA-005 query-budget test, then the chosen loading fix | Required before structural changes to the runtime or stores |
| C — with feature work | CSA-002 agent extraction (and CSA-001's shared construction); CSA-008 operational library and single-owner deploys; CSA-003 `legacy/` namespace; CSA-012 README and naming | Larger moves, justified when a concrete change needs them |

The acceptance criteria in section 7 are unchanged.

## Appendix A — Commands and reproducibility

The targeted backend run used the existing virtual environment and explicitly
disabled live integration tests:

```sh
env RUN_LIVE_API_TESTS=0 .venv/bin/python -m pytest -q \
  tests/test_architecture.py tests/test_bounded_model.py \
  tests/test_agent.py tests/test_execution_firewall.py \
  tests/test_lifecycle_store.py tests/test_reconcile.py \
  tests/test_task1_acceptance.py tests/test_close_responsibility.py \
  tests/test_api.py

.venv/bin/ruff check src scripts tests app.py
.venv/bin/mypy

# From frontend/
pnpm test
pnpm run typecheck
pnpm run lint
```

The selected pytest invocation exited successfully with all-pass progress;
a separate collection run reported 251 tests. The environment check confirmed
`OPTIONS_ALPHA_TEST_DATABASE_URL` was unset. This supports the SQLite result,
not a PostgreSQL claim.

For the query probe, the reviewer used `resolve('', Path('demo/h0_demo.db'))`,
created a TestClient for `create_app(source)`, selected the first decision from
`/api/v1/decisions?limit=1`, and attached a `before_cursor_execute` listener to
that source's engine. The listener was reset before each of the eight requests
and removed afterward. Source selection and initial listing were excluded from
the reported counts. The requests were read-only and no app endpoint was added.

## Appendix B — Related project documents

- [Personal UI redesign](options_alpha_personal_ui_redesign_v0_1.md): user-facing priorities; this audit evaluates the subsequently changed code.
- [Architecture slice](../implementation/options_alpha_architecture_slice_v0_1.md): original contracts and authority separation.
- [Multi-position Task 1](../implementation/options_alpha_multi_position_task_1_manage_many_v0_1.md): manage-many/enter-one behavior to preserve.
- [Deployment runbook](../implementation/options_alpha_deployment_runbook_v0_1.md): operational commands and rollback context.

These documents have different dates and scopes. The findings in this paper are
anchored to revision `2d834c1`, rather than assuming every historical plan is the
current implementation.
