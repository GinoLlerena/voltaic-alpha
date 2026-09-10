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
4. Install the worker unit and drop-in; leave it **disarmed** (`recommend` mode).
5. Apply journald caps and the partitioned `position_observations` schema.
6. Restore drill: recover to a scratch host from OSS with the production host
   stopped; verify row counts and one full lineage chain.
7. Re-run `bash scripts/run_h0_validation.sh` and the dashboard suite against the
   rebuilt host.
8. Arm the worker only when `CIIP-4` shadow evidence is ready to begin.

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

#### `CIIP-I-BLK-002` — the worker has no Alpaca credentials

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
