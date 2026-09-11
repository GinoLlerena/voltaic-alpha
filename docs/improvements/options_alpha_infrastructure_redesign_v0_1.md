# Options Alpha

## Infrastructure Redesign and Retention Standard (`CIIP-I-`)

| Field | Value |
|---|---|
| Version | v0.1 |
| Date | 9 September 2026 |
| Status | **Partly executed 10 September 2026** — host, database, code and journald caps done; off-host archival and the worker are blocked on account actions. See section 10 |
| Prefix | `CIIP-I-` |
| Raised by | [`CIIP-VAL-001`](options_alpha_competitor_informed_improvement_plan_v0_1.md) — the plan assumes infrastructure that no longer exists |
| Sequence | Before `CIIP-4`; the six-week evidence clock starts at redeployment |
| Authority change | None. Paper only, one credentialed writer, cap one |

## 1. Why this exists

On 9 September 2026 the deployment was retired. This package restores a running
system on a smaller footprint and fixes the two design faults the teardown
exposed.

**What was lost, and why it matters.** `options-alpha-worker` and its 40 GB disk
were released. The live evidence database went with it: **209 decisions and
1,155 position observations**, plus every backup, because the backups lived on
the same disk. There was no snapshot.

That is the finding that shapes this design:

> A verified backup that shares a failure domain with its source is not a backup.
> The hourly dump was restore-tested every hour and still did not survive, because
> the disk it sat on was the disk that went away.

**What survives.** `options-alpha-demo` is *stopped*, not released — its 40 GB
disk is intact, the dashboard is installed, and Elastic IP `47.236.50.157`
remains bound to it. Restarting it returns the submission URL unchanged.

## 2. The volume question, answered with measurements

Measured on the worker host before teardown:

| Component | Size | Share |
|---|---:|---:|
| pg_dump backups (48 × ~19.6 MB) | **~940 MB** | **94%** |
| PostgreSQL data directory | 68 MB | 6% |
| journald | 29.5 MB | <1% |
| Root filesystem total | 3.7 GB of 40 GB | mostly OS |

Total project data was **about 1 GB, not 10 GB**, and almost all of it was
backup retention. `scripts/backup_database.sh:27` sets `BACKUP_KEEP=48` and takes
an **hourly full dump** (`pg_dump -Fc`, already compressed). Forty-eight
near-identical snapshots of a 68 MB database covered only two days.

**The database was never the problem. The backup policy was.**

## 3. Target topology

```text
                    ┌──────────────────────────────────────┐
   47.236.50.157 ───▶  options-alpha  (ecs.e-c1m2.large)   │
   (EIP retained)   │                                       │
                    │   systemd: worker (single writer)     │
                    │   systemd: dashboard (read-only)      │
                    │   PostgreSQL 16  ── evidence + telemetry
                    │   watchdog timer · WAL archiver       │
                    └───────────────┬───────────────────────┘
                                    │  continuous WAL + weekly base
                                    ▼
                         ┌────────────────────────┐
                         │  OSS bucket (private)  │
                         │  30-day PITR window    │
                         └────────────────────────┘
```

### `CIIP-I-001` One consolidated host

Restart `options-alpha-demo`, rename it `options-alpha`, and install the worker
and PostgreSQL alongside the existing dashboard. Two hosts existed because the
worker held credentials and the dashboard did not; that separation is preserved
**by process and file permissions**, not by machine — the dashboard already
cannot express a broker write, and `scripts/check_no_write_path.py` enforces it
statically on every release.

Keep `ecs.e-c1m2.large` (2 vCPU / 4 GB). The smallest type available in
`ap-southeast-1a` is `ecs.e-c1m1.large` at 2 GB, which is not enough headroom for
PostgreSQL, Streamlit and the worker together. Running one host instead of two is
already the saving.

**Cost:** ~$4.83/day, against ~$9.65/day for the previous pair. Plus ~$0.45/day
for the retained 40 GB disk and OSS storage measured in cents.

### `CIIP-I-002` Off-host archival is mandatory

WAL archiving to a private OSS bucket, plus a weekly base backup. Point-in-time
recovery over a 30-day window. Local dumps drop from 48 to **2**, kept only as a
fast-restore convenience.

Acceptance: **a restore drill must run from OSS onto a scratch host with the
production host powered off.** A backup not restored from another failure domain
is not proven.

## 4. Retention standard

The governing rule, which the current schema does not distinguish:

> **Evidence** — decisions, evidence packs, theses, intents, prepared requests,
> broker orders, fills, positions, exit decisions, incidents, audit events — is
> small, hash-linked, required by `CIIP-2` proof export, and is **never placed on
> a retention timer.**
>
> **Telemetry** — position observations, tick logs, health samples — is bulky,
> loses value with age, and is downsampled and expired on a schedule.

### `CIIP-I-003` Tiered observation retention

`position_observations` is the only table with real growth: 60-second marking is
roughly 390 rows per session per position. At cap two over a year that is about
200,000 rows, near 40 MB — small, but the *access pattern* justifies partitioning
regardless.

| Age | Resolution | Mechanism |
|---|---|---|
| 0–7 days | 60 seconds, full fidelity | live partition |
| 8–90 days | 5-minute aggregate | rollup job, source partition dropped |
| 90 days+ | one session OHLC row per position | rollup, kept forever |

Partition by `RANGE (observed_at)` monthly. Dropping a period becomes an `O(1)`
`DROP PARTITION` instead of a large `DELETE` plus `VACUUM`.

**Constraint:** a rollup may never alter or delete a row referenced by an exit
decision or incident. Marks that triggered an exit are evidence, not telemetry,
and are copied into the evidence side before their partition is dropped.

### `CIIP-I-004` Snapshot payloads stay put, for now

`market_snapshots.payload` is the fattest column (full JSON per snapshot), but
PostgreSQL TOASTs and compresses it automatically, and `payload_hash` is already
stored and indexed separately (`persistence/models.py:86-87`).

Offloading old payloads to OSS while retaining the hash is **possible but
deferred**: replay determinism and `CIIP-2` proof export both resolve through
these payloads. Do not touch this until there is a test proving
`options_alpha_lab.replay` and a proof export still succeed against an offloaded
snapshot.

### `CIIP-I-005` journald caps set explicitly

`SystemMaxUse=200M`, `MaxRetentionSec=30day`. The current configuration is
entirely default, which means a 10%-of-disk cap of about 4 GB — forty times the
observed usage, and invisible until it matters.

## 5. Logging redesign

The foundation is sound: the worker already emits structured JSON lines. Three
gaps, in priority order.

### `CIIP-I-006` Correlation identity on every line

No log line currently carries a `run_id` or `decision_id`, so logs cannot be
joined to database records. Add correlation identity to every emitted event.
Logs then become queryable evidence instead of a narrative, and `CIIP-2`'s
`presentation/activity.py` can reconcile them against durable records.

### `CIIP-I-007` Separate cadence from events

`position_clock` emits a line every 60 seconds at the same level as an incident.
Routine cadence should be sampled or demoted; every **state change** — entry,
exit, refusal, incident, lease transition, reconciliation mismatch — stays at
full fidelity. Signal is currently buried under a metronome.

### `CIIP-I-008` What matters goes in the database

journald is for diagnostics and is expendable. Anything the product surfaces —
the activity feed, reconciliation history, incident timeline — must be a durable
record. `CIIP-2` requires activity to be "server/durable-record derived, never
synthesized"; that is only true if the worker writes those events to PostgreSQL
rather than only to the journal.

## 6. Rebuild sequence

1. Restart `options-alpha-demo`; confirm `47.236.50.157` answers.
2. Create the private OSS bucket and a RAM role scoped to it — write-only for the
   archiver, read for restore. No broker or account permissions.
3. Install PostgreSQL 16, apply migrations to head, enable WAL archiving to OSS.
4. Install the units that live in version control:
   `bash deploy/install_units.sh` (worker + dashboard). The base worker unit is
   **disarmed** — it hard-codes `--mode observe` and no drop-in is installed here.
5. Install the units written inline by the restore path:
   `bash scripts/restore_hosted_demo.sh` (port 80 forward, backup timer,
   watchdog timer). **Do not skip this step.** Omitting it on 10 September is
   why the rebuilt host had no watchdog and no backups until 11 September; the
   artifacts existed, the sequence simply never named them. See `CIIP-I-016`.
6. Create the dashboard's read-only database role and point the dashboard at
   it: `bash deploy/create_readonly_role.sh`, then
   `systemctl restart options-alpha`, then `bash deploy/verify_readonly_role.sh`
   — which exits non-zero if any write succeeds. Skipping this leaves the
   dashboard holding `INSERT/UPDATE/DELETE/TRUNCATE` on the evidence tables. See
   `CIIP-I-017`.
7. Apply journald caps and the partitioned `position_observations` schema.
8. Restore drill: recover to a scratch host from OSS with the production host
   stopped; verify row counts and one full lineage chain.
9. Re-run `bash scripts/run_h0_validation.sh` and the dashboard suite against the
   rebuilt host.
10. Arm the worker only when `CIIP-4` shadow evidence is ready to begin.

## 7. Acceptance

- `47.236.50.157` serves the dashboard, credential-free, with a labelled source
  mode;
- one host runs worker, database and dashboard, and the static no-write-path gate
  still passes against the dashboard package;
- a restore from OSS succeeds **with the production host powered off**, and
  reproduces one complete decision lineage byte-for-byte;
- local dump count is 2, and total local backup footprint is under 50 MB;
- a 90-day-old observation partition can be dropped without altering any row
  referenced by an exit decision or incident;
- every worker log line carries a correlation id that resolves to a database
  record;
- journald is capped and the cap is verified by configuration, not by
  observation; and
- all 481 tests, ruff, mypy and the H0 validation gates remain green.

## 8. What this does not do

No authority change. Paper only. One credentialed writer. Cap one remains the
default and the rollback target. The worker returns **disarmed** — arming stays a
deliberate, separate, recorded operator action, consistent with `HK-007`.

## 9. Open decisions

- OSS bucket region and lifecycle rule (transition to infrequent access at 30
  days?);
- whether the 5-minute rollup keeps bid/ask or only the spread mark;
- whether `CIIP-I-004` payload offload is ever worth the replay risk; and
- who owns the quarterly restore drill once the hackathon cadence ends.

## 10. Execution record — 10 September 2026

What was built, what is blocked, and on whom.

### Done

| Item | State |
|---|---|
| `CIIP-I-001` consolidated host | `options-alpha-demo` restarted and now runs dashboard + PostgreSQL 16.15 on one box. Hostname was already `options-alpha`. |
| Elastic IP | `47.236.50.157` live again; the submission URL is unchanged |
| Database | Role and database created, credential generated **on the host** and never printed. `create_schema` then `alembic upgrade head`: **20 tables at `0003_reasoning_effort`** |
| Code | `CIIP-001`–`007` deployed — `app.py` at 919 lines, all nine `presentation/` modules importing |
| `CIIP-I-005` journald caps | `SystemMaxUse=200M`, `MaxRetentionSec=30day` applied |
| Worker unit | Installed, **disabled and inactive**, `BOT_MODE=observe`, `ALPACA_TRADING_ENABLED=false`, `REQUIRE_OPERATOR_APPROVAL=true` |

Three things worth recording because they were not in the design.

**The migration path is not `alembic upgrade head`.** Against an empty database
that produces `relation "positions" does not exist`, because `0001_h0_baseline`
is a deliberate no-op marker. Its own docstring says so: the metadata is the
source of truth for a new database, so `create_schema` builds and stamps, and
only then does `upgrade` apply `0002` and `0003`. The runbook should say this
where a rebuild will actually read it.

**The deployed package was a copy, not an editable install.** Shipping into
`/opt/options-alpha/src` therefore changed nothing, and the dashboard failed with
`ModuleNotFoundError: options_alpha_lab.presentation` while `src/` visibly
contained it. Reinstalled with `pip install --no-deps --no-build-isolation -e .`
after adding `setuptools`, so the package now resolves from `src/` and a future
ship takes effect on restart — which is what `restore_hosted_demo.sh` already
assumed in a comment.

**HTTP 200 is not a health check.** The URL returned 200 while the app was
raising on import, because Streamlit serves the shell and renders the traceback
client-side. Any future check must assert page content, not status.

### Blocked, and on whom

#### `CIIP-I-BLK-001` — OSS is disabled on the account

Creating the archive bucket fails with `StatusCode=403, ErrorCode=UserDisable`.
The account shows **$0.00 available with $21.93 of September ECS accrued and
unsettled**; ECS keeps running (PostPaid, no lock) but OSS will not serve.

This blocks `CIIP-I-002` — off-host WAL archiving — and therefore the restore
drill, which is the one acceptance criterion that mattered most after a teardown
destroyed backups that shared a disk with their source. **The system currently
has no off-host copy of anything.**

*Needs:* settle the balance or activate OSS in the console. Until then, the
honest interim is a manual `pg_dump` pulled to a machine outside this account —
off-host in the only sense that matters.

#### `CIIP-I-BLK-002` — the worker has no Alpaca credentials — **RESOLVED 11 September 2026**

`observe` mode still reads market data, so the worker refuses to start with
`ProviderError: Alpaca credentials are required for read-only access`. The
credentials lived on the released host and are gone from the infrastructure.
`/etc/options-alpha.env` carries empty `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` and
`OPENAI_API_KEY` placeholders with the enable command beside them.

*Needs:* paste the Paper credentials, then `systemctl enable --now
options-alpha-worker`. **The evidence clock for `CIIP-4` starts at that moment,
not at redeployment.**

### Not started

`CIIP-I-003` tiered partitioning (the table is empty; better done with the
rollup job), and `CIIP-I-006`–`008` logging changes, which are code rather than
infrastructure.


## 11. Worker start and self-monitoring — 11 September 2026

`CIIP-I-BLK-002` is closed. Paper credentials were transferred to
`/etc/options-alpha.env` without passing through any transcript: the Aliyun CLI
echoes the whole request URL, `CommandContent` included, on failure — it leaked
an AccessKeyId earlier in this project — so the credential-bearing call runs with
stderr suppressed and is verified by masked prefix only.

**The evidence clock started here**, not at the 10 September redeployment.

### Proven against live Alpaca

| | |
|---|---|
| Worker | `active/enabled`, `observe` mode, writes disabled, approval required, `indicative` feed |
| First decision | `spy-agent-20260911T172023Z` → `NO_TRADE`, `no_qualified_setup` |
| `CIIP-I-006` | Every emitted line carries `kind`, `run_id`, `lease_owner`; the tick carries `correlation_id` |
| `CIIP-I-008` | `worker_started`, `startup_reconcile`, `worker_stopped` persisted to `worker_events` |
| Safety strip | `Worker: Live · 5s ago`, sourced from `worker_leases.heartbeat_at` — the cell that read `UNKNOWN` since the rebuild |

### A gap the rebuild had left open

The 10 September rebuild restored the worker and dashboard but **not the watchdog
or backup timers**, though both code paths were deployed. A worker was therefore
about to run unmonitored, with no dump of any kind, while `CIIP-I-002` remained
blocked. Both are now installed and were each run once rather than merely
scheduled:

- **backup** — `verified: true`, 21 tables, 17 rows restored into a scratch
  database and dropped, revision `0004_worker_events`;
- **watchdog** — 8 of 8 checks passing, including `tick_recent` and
  `lease_present`.

Retention is `BACKUP_KEEP=12`, not the old 48. The unit file says why in a
comment that should stay there: while OSS is disabled these dumps sit on the same
disk as the database they protect, so they are a fast-restore convenience and
**not a backup**. Forty-eight near-identical copies of one disk is not
forty-eight backups — that is precisely the arithmetic that lost 209 decisions on
9 September.

### Still open

`CIIP-I-BLK-001` is unchanged: OSS returns `UserDisable` against a $0.00
balance, so there remains **no off-host copy of anything**, now including the
live decisions the worker has begun recording.

## 12. Cost review — 11 September 2026

Asked to reduce cost and why there was "so much data". The premise did not
survive measurement, and the correction matters because it points the saving at
a different place than expected.

### There is no data problem

| | |
|---|---|
| Root filesystem | 3.6 GB used of 40 GB (10%) |
| OS and system | 3.0 GB |
| `/opt` (code and venv) | 638 MB |
| Postgres data directory | 64 MB |
| journald | 31 MB |
| Backups | 260 KB |
| **The database itself** | **8.8 MB, 17 rows across 21 tables** |

The application's own data is roughly 0.02% of the disk it sits on. This is the
second time the volume question has been asked and the second time the answer
has been that the data is not the cost — §2 recorded the same result on
9 September, when 94% of a ~1 GB footprint turned out to be backup retention.

The billing model is the reason, and it is worth stating plainly because it
inverts the intuition: **ECS charges provisioned GB and CPU-hours, not bytes
stored.** Deleting rows saves nothing. Yesterday's `BACKUP_KEEP` 48 → 12 change
was correct — it stops the disk filling — but its effect on the bill is exactly
$0.00. Only releasing provisioned capacity or stopping compute reduces spend.

### Where the money went

September 1–11, $22.45 pretax:

| Line | Amount | Share |
|---|---:|---:|
| Compute (CPU/RAM hours) | $15.37 | 68% |
| System disks, by provisioned size | $7.07 | 31% |
| Network, Elastic IP, OS images | $0.01 | 0% |

The Elastic IP retention fee bills at $0.00 while attached, confirming the
earlier answer given on 9 September.

A number recorded earlier in this project was wrong and is corrected here: the
host was described as costing ~$4.83/day. The metered rate is **$1.10/day**
running ($0.85 compute + $0.24 disk) and $0.24/day stopped — high by 4.4×.

The single largest line, $9.78, belonged to `i-t4nfdbjx66so1we0aysh`, a second
options-alpha host that ran at $1.10/day alongside `options-alpha-demo` from
1–9 September and was released on the 9th. Forty-four percent of the month was
paid for running two hosts where one was needed. That is already fixed, and it
is the clearest argument in this document for the single-host topology in §3.

### Actions taken

- **Released `crypto-copilot-demo` and `agentops-demo`** (instances
  `i-t4nhyplwm55uam20b3ry`, `i-t4n1w3s9onvpaterzson`). Both were stopped and
  unrelated to this project, each still paying $0.10/day for a retained 40 GB
  system disk. A system disk cannot be released independently of its instance,
  and neither had a snapshot, so this was permanent and was confirmed as such
  before it was done. Verified afterwards: one instance and one disk remain, no
  orphans. **−$0.20/day.**
- **System disk `cloud_essd` PL1 → `cloud_essd_entry`** — **attempted and
  failed.** Recorded here because a plan that did not work is worth more in the
  file than out of it.

  It was scheduled for after the US close rather than done immediately: the
  conversion requires the instance stopped, and the observe-mode evidence clock
  had started that morning, so a Friday close put the whole weekend between the
  restart and the next session that mattered. Priced first at $0.0101/hr against
  $0.0043/hr for 40 GB, matching the observed $0.24 and $0.10 per day exactly.

  `ModifyDiskSpec` refused it in both forms and in both instance states:
  `InvalidDiskCategory.NotSupported` for the category change, running and
  stopped, and `InvalidPerformanceLevel.Malformed` for a PL1 → PL0 downgrade.
  The category of an in-place **system** disk is not modifiable on this API. The
  script restarted the instance unconditionally, which is the reason a failed
  conversion cost one minute of downtime rather than an outage: all six units
  came back active, the dashboard answered 200, and the worker resumed its lease.

  The remaining route is `ReplaceSystemDisk` with a `cloud_essd_entry` system
  disk, which reinstalls the OS. That is a full rebuild — Postgres, schema,
  credentials, units — for $4.23/month, against a live evidence clock and with
  `CIIP-I-BLK-001` still meaning there is no off-host copy. Not worth it now.
  Worth folding into the *next* rebuild that happens for another reason, where
  the marginal cost is choosing a different category in one parameter.

Actual saving is therefore **−$0.20/day** from the releases alone: run rate
$1.30/day → **$1.10/day** (~$33/month), not the ~$0.96 projected above.

### Deliberately not done

Stopping the host outside market hours is the largest remaining lever, worth
about $0.67/day, and it was declined rather than overlooked. Compute is 68% of
the bill, but the observe-mode worker began accumulating evidence that morning
and overnight and weekend ticks are part of what proves the exit and
reconciliation paths for `CIIP-4`. The lever trades away precisely what the
spend is currently buying. Revisit once `CIIP-4` has its evidence.

### `CIIP-I-016` — two units exist only on the host

Found while verifying service health. The first version of this note claimed no
unit was in the repository; that was wrong and is corrected here, because the
accurate version points at a different fix.

What is captured: `restore_hosted_demo.sh` writes `options-alpha-port80`,
`options-alpha-backup{.service,.timer}` and `options-alpha-watchdog{.service,.timer}`
as heredocs. `arm_worker.sh` writes the `10-paper-execute.conf` drop-in.

What is not captured anywhere in this repository:

- **`options-alpha.service`** — the Streamlit dashboard. The hosted demo the
  judges were pointed at has no definition in version control at all.
- **`options-alpha-worker.service`** — the base unit. `arm_worker.sh` writes a
  drop-in that overrides its `ExecStart`, but the unit that drop-in modifies,
  including the `EnvironmentFile`, `RuntimeDirectory` and the disarmed
  `--mode observe` default, exists only on the host.

The second is the sharper risk. A drop-in is an override of something assumed to
be present; if the base unit is ever rebuilt by hand slightly differently, arming
silently inherits whatever that hand-written base happened to say.

This also corrects §11's account. The watchdog and backup timers were missing
after the 10 September rebuild **not** because no artifact existed — it did — but
because `restore_hosted_demo.sh` was not run as part of that rebuild. The gap is
in §6's rebuild sequence, which does not name the script that installs them.

### `CIIP-I-016` — resolved, 11 September 2026

Fixed in the commit that follows this record.

- `deploy/systemd/options-alpha-worker.service` and
  `deploy/systemd/options-alpha.service` now exist, copied from the running host
  and **verified byte-identical** to it rather than retyped — 802 and 590 bytes,
  diffed, not eyeballed.
- `deploy/install_units.sh` installs them idempotently. It refuses to enable a
  unit whose `EnvironmentFile` is absent, because systemd would otherwise fail
  the unit at start with an error that reads like a code fault and is not one.
  It does not restart a running worker; that would interrupt a live session
  without being asked.
- `deploy/systemd/README.md` states the environment contract for both files in
  one place, keys only, no values.
- §6 now names both install steps, including the
  `scripts/restore_hosted_demo.sh` step whose omission caused the 10 September
  loss.
- `tests/test_deploy_units.py` — 12 tests. The one that earns the file asserts
  the **base** worker unit is disarmed: `--mode observe`, no `paper_execute`, no
  `--approve`, and `arm_worker.sh` writes a drop-in rather than overwriting the
  base. A drop-in overrides something it assumes is present, so a hand-rebuilt
  base unit with arming baked in would be inherited silently by the next arm.

The five inline units in `restore_hosted_demo.sh` were deliberately **not**
copied into `deploy/systemd/`. Two definitions of one unit drift, and the
drifted copy is found at the worst moment. Consolidating them is worth doing and
belongs in its own commit, because it changes a restore path that currently
works.

### `CIIP-I-017` — the dashboard's "read-only" is a code property, not a grant

Found while writing the environment contract above, and worth separating from
`CIIP-I-016` because it is a security finding rather than a reproducibility one.

The dashboard unit is titled "read-only", and
`scripts/check_no_write_path.py` does parse the tree to prove no broker write can
be expressed outside the single named gateway file. That guard is real.

The database grant is not. `DASHBOARD_DATABASE_URL` and `DATABASE_URL` resolve to
the **same** Postgres role, `options_alpha`, which holds
`INSERT`, `UPDATE`, `DELETE` and `TRUNCATE` on all 21 tables. The separate
environment file gives the shape of least authority without the substance: a
dashboard defect, or anything that reaches its credentials, can write to or
truncate the evidence the project exists to protect.

This is the same least-authority argument as `HK-006`, applied to a surface that
predates it.

### `CIIP-I-017` — resolved, 11 September 2026

`options_alpha_ro` now exists, holding `SELECT` and nothing else, and
`DASHBOARD_DATABASE_URL` points at it. The worker's own credential is untouched.

Verified against the live database rather than asserted. Reads on `decisions`,
`worker_events` and `audit_events` succeed; `INSERT`, `UPDATE`, `DELETE`,
`TRUNCATE`, `CREATE TABLE` and `DROP TABLE` are each attempted for real and each
refused. `deploy/verify_readonly_role.sh` performs exactly those probes and
**exits non-zero if any write succeeds**, which makes it a gate rather than a
reassurance — a check that cannot fail proves nothing.

The dashboard was then confirmed to still work, and confirmed the way this
project learned to confirm it on 9 September: not by an HTTP 200, which Streamlit
returns while rendering a traceback client-side, but by loading the page and
reading the DOM. It renders 24 decisions from the live worker database with zero
exception blocks.

Both halves are captured as scripts — `deploy/create_readonly_role.sh` and
`deploy/verify_readonly_role.sh` — and §6 now names them. That is `CIIP-I-016`'s
lesson applied immediately: a role created by hand is a role the next rebuild
loses, and this one would be lost silently, because a read-write dashboard looks
exactly like a read-only one until something goes wrong.

The password is generated on the host, never printed, never passed through
`argv` where `ps` would expose it, and written only to the `0600` environment
file. The previous file is kept alongside it as a rollback.

One residual, recorded so it is not mistaken for finished: the role was created
against the running database, so it exists on this host only. Until
`CIIP-I-BLK-001` is resolved and an off-host copy exists, a host loss still
takes the role, the credential and the evidence together.
