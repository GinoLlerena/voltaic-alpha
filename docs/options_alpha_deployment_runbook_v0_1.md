# Options Alpha

## Deployment Runbook

| Field | Value |
|---|---|
| Version | v0.1.1 |
| Provider | Alibaba Cloud ECS, region `ap-southeast-1` (Singapore) |
| Application URL | `http://47.84.108.130:8501` |
| Instance | `i-t4n88bkfwsq0lhzmfjii`, name `options-alpha-demo`, `ecs.e-c1m2.large` (2 vCPU / 4 GB), Ubuntu 24.04 |
| Security group | `sg-t4naetmr3bp6sry6lw7a`, dedicated. **Only** 8501/tcp is open |
| Service | systemd unit `options-alpha`, `Restart=always`, enabled at boot |
| Install root | `/opt/options-alpha` |

## 1. What is deployed, and what is not

Two hosts, deliberately separate. **This section describes the public dashboard
host.** The credentialed worker was added on 29 August 2026 and is documented in
section 7; the split is the point, so read both before concluding what the
system can do.

| Host | Section | Credentials | Can place an order |
|---|---|---|---|
| `options-alpha-demo` (public, 8501/tcp) | this section | none | no |
| `options-alpha-worker` (no inbound port) | [section 7](#7-credentialed-worker-added-29-august-2026) | Alpaca Paper, OpenAI | no - `recommend` mode, writes disabled |

The dashboard serves evidence and has no code path to a broker or a model
provider. Its service environment contains **no Alpaca or OpenAI credential**,
verified after start by reading the process environment. The upload was produced
with `git archive`, so only tracked files were shipped and `.env` could not be
included even by accident.

The decision worker, the execution gateway, and the freeze tooling are **not**
deployed *on this host*. Nothing on the dashboard host can place an order.

### 1.1 Autonomous-worker gate

The dashboard deployment is not an autonomous-agent deployment. Do not add
Alpaca/OpenAI credentials or start `options_alpha_lab.agent` on this service as
a convenience change. That would expand the host from public evidence viewer to
broker authority and invalidate its current security claim. The worker exists
precisely so that this does not have to happen.

Autonomous Paper *entry* remains disabled. The separate worker boundary now
exists, and the entry preconditions stand as follows:

| # | Precondition | Status |
|---|---|---|
| 1 | Protected Paper-only provider secrets with no live fallback | Met - `/etc/options-alpha.env`, mode 600, root-owned; `ALPACA_PAPER_TRADE=true` |
| 2 | Durable hosted database and migrations for intents, orders, fills, positions, execution state, and incidents | Met - PostgreSQL 16 plus Alembic (section 7.6) |
| 3 | One database-backed worker lease and an authoritative market calendar | Met - lease with heartbeat/TTL (section 7.2); calendar-derived entry window |
| 4 | Startup reconciliation before the decision loop, plus periodic reconciliation while any order or exposure exists | Met - `startup()` precedes any new risk; reconciliation opens every strategy tick, every position-clock pass while exposure exists, and every order-clock pass while a mutation is outstanding |
| 5 | Durable pending/partial/open/closing/flat states based on actual fills | Met - acceptance is `SUBMITTED`, never `FILLED`; state comes from reconciled fills |
| 6 | Health checks and alerts for broker/local mismatch, stale reconciliation, database failure, worker death, and an unmanaged position | Partial - health JSON and durable incidents exist; there is no alerting |
| 7 | Backup, restore, forced-restart, credential-rotation, and rollback evidence | Partial - forced restart and migration rollback are evidenced; backup and restore are not (section 7.7) |

Two further conditions are policy rather than plumbing, and neither is met:
exit thresholds are still `PROVISIONAL` without sensitivity evidence, and
`DEC-008` is open. **Until 6 and 7 close and `DEC-008` is answered, entry stays
disabled.** The switch is deliberately two steps - `--mode paper_execute` plus
`--approve` - so that it cannot be flipped by editing one line.

The public dashboard reads the worker's database through a `SELECT`-only role
and holds no broker-write credential and no control actions (section 7.3).

## 2. Platform

The organizers confirmed on 29 August 2026 that there is **no deployment-platform
restriction**. The Rule Book and Submission Guidelines name Streamlit, Replit,
and Vercel as suggestions. This deployment is the submission URL.

## 3. Known limitations

- **HTTP only.** There is no domain and no TLS certificate, so browsers will
  mark the URL "not secure". The page carries no login and no user input, so
  nothing sensitive crosses the wire, but a judge will see the warning.
- **Bare IP address.** No DNS name is attached.
- **Single instance.** No load balancer and no redundancy.
- **The recorded addresses are not reserved.** `47.84.108.130` and
  `43.98.206.148` were assigned at creation. Both instances have since been
  stopped to stop the meter, which releases a pay-as-you-go public address, so
  they will not come back on restart. The dashboard address is the submission
  URL, so allocate an Elastic IP and bind it before submitting; until then,
  treat every address in this document as historical.

## 4. Operating it

No SSH port is open. All administration goes through ECS Cloud Assistant, which
needs no inbound port at all:

```bash
# Service status
aliyun ecs RunCommand --RegionId ap-southeast-1 --Type RunShellScript \
  --InstanceId.1 i-t4n88bkfwsq0lhzmfjii \
  --CommandContent "$(printf 'systemctl status options-alpha --no-pager | head -20' | base64)" \
  --ContentEncoding Base64

# Then read the output
aliyun ecs DescribeInvocationResults --RegionId ap-southeast-1 --InvokeId <InvokeId>
```

Redeploying after a code change:

1. `git archive --format=tar.gz -o /tmp/oa.tar.gz HEAD app.py requirements.txt pyproject.toml README.md src demo artifacts .streamlit`
2. Re-open 22/tcp to your current egress IP in `sg-t4naetmr3bp6sry6lw7a`,
   `scp` the tarball, extract over `/opt/options-alpha`, then **revoke 22 again**.
3. `systemctl restart options-alpha` via Cloud Assistant.

The deploy host's egress IP was not stable during setup (a Cloudflare-style
pool), so a `/32` SSH rule failed. Use the `/24`, and revoke it when done.

## 5. Cost

One `ecs.e-c1m2.large` pay-as-you-go instance plus 40 GB ESSD and pay-by-traffic
bandwidth capped at 5 Mbit/s. **It bills while it runs.** Stop or release it
after the event:

```bash
aliyun ecs StopInstance  --RegionId ap-southeast-1 --InstanceId i-t4n88bkfwsq0lhzmfjii
aliyun ecs DeleteInstance --RegionId ap-southeast-1 --InstanceId i-t4n88bkfwsq0lhzmfjii --Force true
```

The key pair `options-alpha-deploy` and its private key exist only outside the
repository. Delete the key pair when the instance is released.

## 6. Verification performed

- Public `HTTP 200` on `/` and `ok` on `/_stcore/health`.
- All five views rendered for all five decisions from the public internet, with
  zero browser console errors.
- Port 22 confirmed closed after deployment; 8501 the only open port.
- Service environment confirmed free of provider credentials.

## 7. Credentialed worker (added 29 August 2026)

| Field | Value |
|---|---|
| Instance | `i-t4nfdbjx66so1we0aysh`, `options-alpha-worker`, `ecs.e-c1m2.large`, Ubuntu 24.04 |
| Public IP | `43.98.206.148` (no inbound port is open) |
| Private IP | `192.168.1.215` |
| Security group | `sg-t4n6kaxrojixmg4ivuh8`: **only** 5432 from `192.168.0.0/16`. Nothing is reachable from the internet |
| Database | PostgreSQL 16, bound to loopback and the private address only |
| Service | systemd `options-alpha-worker`, `Restart=always`, `--mode recommend` |
| Secrets | `/etc/options-alpha.env`, mode 600, root-owned |
| Health | `/var/run/options-alpha/health.json` |

### 7.1 Authority boundary

The worker runs in `recommend` mode: it observes, decides, reconciles, enforces
deadlines, and manages exits, with `ALPACA_TRADING_ENABLED=false` and
`REQUIRE_OPERATOR_APPROVAL=true`. **It cannot open a position.** Enabling
autonomous entry is a deliberate two-step change - `--mode paper_execute` plus
`--approve` - and should wait until the exit thresholds have sensitivity
evidence and `DEC-008` is closed.

### 7.2 Single writer

A database lease is acquired before any work and heartbeated every 20 seconds
against a 90-second TTL. A second worker refuses to start and names the current
holder. An expired lease is taken over, so a worker that died without releasing
does not block its replacement.

The heartbeat cadence matters and was wrong at first: heartbeating once per tick
left the lease expired between 300-second ticks, which is precisely the window
in which another worker would take over while the first was alive and holding a
position. The lease is now renewed several times inside its own TTL, and a test
asserts that relationship rather than trusting the two constants to stay
compatible.

### 7.3 Dashboard boundary

The dashboard holds **no Alpaca or OpenAI credential**. It reads the worker
database through a `dashboard_ro` role granted `SELECT` only; `CREATE TABLE` is
denied, which was verified rather than assumed.

This is a deliberate, narrow deviation from `EXIT-AC-16`'s literal wording that
the dashboard remain credential-free. It holds one read-only database
credential and no provider credentials, so the property that matters - the
surface a judge browses cannot trade - is preserved. Flagged for the owner's
decision rather than quietly reinterpreted.

If the live database has no decisions yet, the dashboard falls back to the
committed evidence and says so in the sidebar. A worker started outside market
hours has decided nothing, and showing a judge an empty page would be worse than
showing frozen evidence honestly labelled.

### 7.4 Verified

- Restart: `SIGKILL` with no graceful release; systemd restarted the service, the
  new process acquired the lease under a new owner, and health returned healthy.
- Single writer: a second worker refused to start against a live lease.
- Isolation: port 22 closed on both hosts, 5432 unreachable from the internet.
- Packaging: deploying caught `httpx` being declared a dev-only dependency while
  the read-only adapter imports it at module scope. The dashboard had never
  exposed this because it does not import the provider modules.

### 7.5 The three clocks

The worker runs three cadences, because the questions have different timescales.

| Clock | Cadence | What it does | Runs when |
|---|---|---|---|
| Strategy | `--interval`, default 300s | Reconcile, enforce deadlines, manage exits, consider entries | always |
| Position | `--position-clock-interval`, default 60s | Reconcile, value the open spread, evaluate exits. Never considers an entry | a position is OPEN or CLOSING, and the market is open |
| Order | `--order-clock-interval`, default 5s | Reconcile and enforce deadlines *only* | a broker mutation is outstanding |

Each is gated on a local database read first, so a flat, idle worker makes no
provider call on either fast cadence. Each is due independently: a quiet pass on
one must not skip the other, and an earlier version of the loop had exactly that
bug latent in it - the order clock's `continue` would have skipped the position
clock for that second. They are not alternatives; a worker can need both at
once.

**The position clock exists because value is not a daily question.** The
strategy hypothesis changes once per completed session, so re-deciding it every
minute would add correlated records rather than information. The value of an
open spread does not: a stop loss judged once per 300-second tick is enforced
against a mark up to 300 seconds stale, and the observation series MFE and MAE
are computed from has 300-second resolution - too coarse to see the excursion it
exists to measure.

The strategy hypothesis is daily and its inputs change once per completed
session, so re-deciding it every few seconds would add correlated records rather
than information. An order deadline is 90 seconds for an entry and 120 for a
close, and a check that runs every 300 seconds can enforce one 300 seconds late
- by which time the unfilled order still occupies the single strategy slot and
the market has moved away from its limit.

The order clock decides whether to contact the broker from a local database
read, so a quiet pass costs nothing, and it stands down ten minutes after a
submission. An order still working past every deadline the policy declares has
something wrong with it that five-second polling will not fix; the strategy loop
keeps reconciling it. `--order-clock-interval 0` disables it.

Health JSON carries `order_clock_actions` and `position_clock_actions`, so a
worker that looks idle at tick granularity can be seen to have been busy at
order and position granularity. A worker holding a spread should show the
position count climbing; a flat one never will.

### 7.6 Schema migrations

The schema is versioned with Alembic from 29 August 2026. Before that, the
hosted PostgreSQL was created by `create_schema`, which calls `create_all` and
left no `alembic_version` row. Adding the Phase 1 capture tables
(`position_observations`, `exit_decisions`) is the first change to reach it, so
the existing database has to be told where it already stands before it can be
moved forward:

```bash
# Once, on the worker host. Records that the h0.1 schema is already present.
uv run alembic stamp 0001_h0_baseline
# Then, and on every later deployment.
uv run alembic upgrade head
uv run alembic current   # expect: 0003_reasoning_effort (head)
```

Stop the worker service before upgrading and start it afterwards. The migration
only adds tables and columns, so it does not rewrite anything the running worker
holds, but a single writer is the invariant the lease exists to protect and a
schema change is not the moment to make an exception to it.

**Migrate before deploying code that reads the new shape, including the
dashboard.** The dashboard queries through the same ORM models, so a model with
a column its database lacks fails the whole page with `no such column`, not just
the field. This is not hypothetical: adding `model_calls.reasoning_effort`
(revision `0003`) broke every dashboard render against the committed evidence
database until it was rebuilt. Order is: stop the worker, `alembic upgrade
head`, start the worker, then deploy the dashboard.

Rollback is `uv run alembic downgrade 0001_h0_baseline`, which drops the two
tables. It discards the observations and exit decisions captured since the
upgrade; there is no earlier shape to preserve them into, and pretending
otherwise would be the more dangerous option.

`alembic.ini` carries no database URL. `migrations/env.py` takes `-x url=` first,
then a URL set programmatically by `create_schema`/`upgrade_schema`, and only
then falls back to the application's own `Settings` - so a migration cannot be
run against a database the application itself would refuse to open.

**Known limitation, stated rather than discovered later:** `alembic upgrade head`
against a genuinely empty database does not build the schema. Revision
`0001_h0_baseline` is a marker, not a transcription of the seventeen h0.1
tables. A new database is created by `create_schema`, which builds it from the
model metadata and stamps head; migrations exist to move existing databases
forward.

### 7.7 Cost and teardown

Two `ecs.e-c1m2.large` instances now bill. Release both after the event:

```bash
aliyun ecs DeleteInstance --RegionId ap-southeast-1 --InstanceId i-t4nfdbjx66so1we0aysh --Force true
aliyun ecs DeleteInstance --RegionId ap-southeast-1 --InstanceId i-t4n88bkfwsq0lhzmfjii --Force true
```

There is no database backup yet. `EXIT-AC-16` asks for backup and rollback
evidence, and that part is **not** satisfied: a `pg_dump` timer is the remaining
work.

## 8. Rehearsing the loop outside market hours

The worker is only interesting while the exchange is open. Every other hour of
the week `tick()` reaches the market-open check and stops, which is correct
behaviour and a useless demonstration: reconciliation, the decision workflow,
the risk governor and the execution firewall never run where anyone can see
them. A demonstration recorded on a Saturday would show one line saying
`MARKET_CLOSED`.

```bash
uv run python -m options_alpha_lab.rehearsal            # baseline thesis
uv run python -m options_alpha_lab.rehearsal --arm model # bounded model memo
```

This drives `TradingAgent.tick()` - the same method the worker calls, not a
copy - from the committed H0 snapshots. Nothing tells the agent to pretend the
market is open; the observation comes from a recording taken while it was, which
is what a rehearsal is. Output is the worker's JSON event shape, one `tick`
event per snapshot, at `--interval` seconds apart so a screen recording is
readable.

Three properties keep it from becoming a second, quieter trading path:

- **No gateway is constructed.** A qualified setup reaches `TRADE_CANDIDATE` and
  stops, which is what the deployed `recommend` worker does.
- **No provider client exists.** `RehearsalClient` raises on every read, so a
  future change that reached past the observation source would fail loudly
  rather than quietly go live.
- **The production database is not addressable.** Rehearsal accepts SQLite only
  and overrides the ambient `DATABASE_URL`, so running it on the worker host
  cannot append rehearsal rows to the authoritative store. If the inherited
  configuration was write-capable, the start-up event says
  `inherited_config: overridden` rather than downgrading in silence.

The rows it writes identify themselves: their snapshot ids are the committed
fixture ids (`spy-qualified-2026-08-27`), not the `spy-agent-<stamp>` ids the
live agent mints. A rehearsal trace is a demonstration of the loop, not a record
of anything that happened, and `rehearsal/` is git-ignored for that reason.
