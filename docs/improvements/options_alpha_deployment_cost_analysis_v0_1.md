# Options Alpha

## Deployment Cost Analysis

| Field | Value |
|---|---|
| Version | v0.3 (filename retained for existing links) |
| Date | 19 September 2026 |
| Status | **Reviewed recommendation and implementation handoff.** Infrastructure changes are not executed; acceptance gates below are pending |
| Scope | Reported Alibaba infrastructure and GitHub CI/CD costs; not total product operating cost |
| Supersedes | v0.1 recommendations in this file. Extends [§12 of the infrastructure redesign](options_alpha_infrastructure_redesign_v0_1.md); its September 11 prices remain historical |
| Method | Original v0.1 reports live account queries and host measurements. This revision checks repository evidence, arithmetic and provider documentation; it does not repeat account queries or host measurements |

**Decision:** retain the consolidated, always-on host and its existing disk/EIP.
Use configuration C as a PAYG capacity trial, then configuration B only if the
trial passes. Billing eligibility, an independently recoverable backup and
representative capacity checks are prerequisites. If 2 GB fails those checks,
retain 4 GB: the saving does not justify losing availability or evidence.

The implementation sequence is in §6–§7. This document authorizes no payment,
instance stop, resize, subscription purchase or change to trading authority.

---

## 0. Billing status: accrued, not restricted

**Corrected in v0.3.** v0.1 and v0.2 led with the outstanding balance as the
finding that outranked everything. That was an over-escalation. The account is
on normal end-of-month postpaid billing, where a month-to-date accrued balance
and a $0.00 prepaid credit are the expected steady state, not a fault.

Measured 20 September: September accrued **$32.44**, `cash=$0`,
`AvailableAmount=0.00`. Those are the same fields v0.1 read as an emergency.

The question that matters is whether the account is **restricted**, and the
evidence says it is not:

| Probe | Result |
|---|---|
| `DescribeInstanceStatus`, `DescribeSecurityGroups` | answer normally |
| `ModifyInstanceSpec --DryRun` | `InvalidInstanceStatus.NotStopped` — a *state* error, not `Forbidden`, `NotEnoughBalance` or an overdue code |
| `oss ListBuckets` | **answers** (0 buckets) — where `CIIP-I-BLK-001` recorded `403 UserDisable` |

That last row looked like a change worth acting on. **It was not.** Re-tested
20 September: `CreateBucket` still returns **`UserDisable`**, the same code
`CIIP-I-BLK-001` recorded. `ListBuckets` is permitted while creation is refused,
so the earlier reading was insufficient evidence and the blocker **stands**. The
probe bucket was deleted; nothing was provisioned. §7.2 chooses its backup
target accordingly.

**Treatment:** billing is not a gate. Confirm no restriction in the same hour as
any maintenance window, because a host that stops and will not restart is the
one failure this check is cheap insurance against. Otherwise proceed.

What remains true from v0.1, with the inflation removed: the live evidence
exists in one place. Per `CIIP-VAL-013` that evidence is **331 decisions across
six trading days and six distinct completed closes** — six independent
observations, not two weeks of them. Section 7.2 sizes protection to that.

## 1. What is actually running

Reported September 19 inventory from v0.1; re-verify before implementation.

| Component | Spec | Purpose | Required? | $/month |
|---|---|---|---|---:|
| ECS `i-t4n88bkfwsq0lhzmfjii` | `ecs.e-c1m2.large`, 2 vCPU / 4 GB, PostPaid, `ap-southeast-1a` | Worker, Streamlit dashboard, FastAPI read API, PostgreSQL | Yes | **25.99** |
| System disk `d-t4n88bkfwsq0lhzp8xth` | 40 GB `cloud_essd` **PL1** | OS, code, database, backups | Yes — not at this size or tier | **7.39** |
| EIP `eip-t4nog5mmlwazufrsn8nfz` (`47.236.50.157`) | PayByTraffic, 5 Mbps | The public dashboard address | Yes | **0.01 observed month-to-date; variable** |
| Cloud Data Transfer | — | — | — | 0.00 |
| Load balancer, NAT gateway, snapshots, custom images, OSS | **none exist** | — | — | 0.00 |
| GitHub Actions | ~282 job-seconds per run | CI: lint, types, tests, PostgreSQL replay, browser gate | Yes | **0.00** |
| | | | **Compute + disk baseline** | **33.38** |

The displayed components sum to **$33.39** including observed EIP usage. All
comparisons below use the **$33.38 compute + disk baseline**, excluding variable
network charges, backups and tax. The EIP observation is not a fixed monthly quote.

Two things are worth stating because they are easy to assume otherwise.

**There is no load balancer and no managed database.** Port 80 reaches Streamlit
through an `iptables` REDIRECT installed by `options-alpha-port80`, and
PostgreSQL runs on the same box. At a 49 MB database and one viewer at a time,
both are reasonable for the observed workload. No managed-database alternative
was quoted here; retain this topology unless availability or recovery requirements
justify the migration cost.

**CI is free.** The repository is public, so GitHub Actions runs on standard
runners at no charge. Preserve the current standard-runner setup; the $0 claim
is not a guarantee for future paid runners, storage or other billing changes.

### Observed spend

| Period | Amount | Note |
|---|---:|---|
| August 2026 | $8.86 | Host created 28 August; partial month |
| September 1–19 | **$31.07** | Of which **$12.03** belongs to three instances **already released** |
| — the live host alone | $19.04 | $14.45 compute + $4.59 disk, over 19 days |

The live host therefore runs at **$1.002/day observed** against a **$1.097/day**
list rate. Do not infer stopped hours from that gap: the query cutoff, discounts
and compute/disk billing durations must be reconciled separately. Forward
compute + disk run rate at the current specification is **$33.38/month**.

$12.03 of September — 39% — was incurred by instances that no longer exist. That
is already fixed and is not a future saving; it is recorded so the month's total
is not mistaken for the run rate.

## 2. Utilisation against allocation

| Resource | Allocated | Measured | Verdict |
|---|---|---|---|
| CPU | 2 vCPU | load average **0.16 / 0.04 / 0.01**; `sar` ~0.03 across 24 h; **98.3% idle** | Heavily over-provisioned |
| Memory | 4 GB (3 499 MB usable) | **949 MB used**, 2 550 MB available. Reported peaks since boot: dashboard 136 MB, worker 145 MB, API 64 MB, PostgreSQL 203 MB. No OOM reported in inspected logs | 2 GB candidate; representative peaks unproven |
| Disk | 40 GB ESSD PL1 | **4.1 GB used (11%)**: `/opt` 639 MB, PostgreSQL 136 MB, backups 326 MB, logs 82 MB. The database itself is **49 MB** | Over-provisioned in size *and* performance tier |
| Network | 5 Mbps, pay by traffic | $0.01 egress for the month | Correctly sized |

`shared_buffers` is 128 MB and `work_mem` 4 MB. These measurements justify
testing 2 GB, not declaring it sufficient. Infrastructure redesign §16 records
**zero positions and zero model calls**: the observed workload did not exercise
all intended paths. A five-minute strategy tick is not the whole workload;
`src/options_alpha_lab/agent.py:position_clock` manages exposure between ticks,
and `scripts/backup_database.sh` restores a scratch database alongside production.
Absence of OOM on 4 GB does not establish safety on 2 GB.

This is the third time the volume question has been answered the same way, and
the answer has not changed: **the data is not the cost.** ECS bills provisioned
GB and CPU-hours. Deleting rows does not reduce the existing provisioned-disk
bill. It can affect future capacity and backup costs, but evidence retention is
not a cost-cutting target.

## 3. Options, priced against this account

The original compute/disk quotes are reported from `DescribePrice` for this
region and zone. Scheduled-runtime figures are calculations; backup costs remain
unquoted. Refresh quotes and preserve their request parameters before purchase.

| # | Change | From | To | Saving/mo | % | Effort | Recommendation |
|---|---|---:|---:|---:|---:|---|---|
| 1 | **2c4g → 2c2g** (`ecs.e-c1m1.large`) | 33.38 | 20.39 | **12.99** | 39% | Maintenance window; duration unverified | **After billing, backup and capacity gates** |
| 2 | PAYG → 1-month subscription, same spec | 33.38 | 22.38 | 11.00 | 33% | Billing conversion; verify eligibility | Requires payment and restriction checks |
| 3 | **Options 1 and 2 together** | 33.38 | 14.20 | **19.18** | 57.5% | Resize trial, observation, then prepayment | **Preferred conditional target** |
| 4 | Disk PL1 → `cloud_essd_entry` | 7.39 | 3.10 | 4.29 | 13% | **Full rebuild** | Only inside a rebuild |
| 5 | Disk 40 GB → 20 GB | 3.10 | 1.55 | 1.55 | 5% | **Full rebuild** | Only inside a rebuild |
| 6 | Scheduled economical mode, illustrative 157.5 h/month | 25.99 | ~5.61 | 20.38 | 61% | Calendar/exposure checks and reliable restart automation | **Deferred** |
| 7 | Serverless / managed-database rewrite | — | — | Not established | — | Architecture study and migration | **No current cost justification** |
| 8 | **Off-disk backup: one-time pre-resize copy, then daily to OSS** | 0.00 | **0.05–0.15** | Added cost | — | Upload script, lifecycle rule, restore drill | **Before resize** |

Percentages use the $33.38 baseline, including rows showing component-only
prices. Savings are alternatives, not additive; stop-scheduling has no compute
billing benefit after subscription conversion.

### Price matrix

Pay-as-you-go, per month at 730 hours; subscription at one month prepaid.

| Configuration | PAYG | 1-month subscription |
|---|---:|---:|
| `e-c1m2.large` + ESSD PL1 40 GB — **current** | **33.38** | 22.38 |
| `e-c1m2.large` + `essd_entry` 40 GB | 29.09 | 18.34 |
| `e-c1m1.large` + ESSD PL1 40 GB | 20.39 | 14.20 |
| `e-c1m1.large` + `essd_entry` 40 GB | 16.10 | 10.16 |
| `e-c1m1.large` + `essd_entry` 20 GB | 14.55 | 9.14 |

A one-year commitment prices `e-c1m1.large` + `essd_entry` 40 GB at $103.66, or
$8.64/month. It is not recommended: a twelve-month lock on a project whose
horizon is not twelve months buys $1.52/month over the monthly term.

### Notes on the individual options

**Option 1 is a candidate, not a validated operation.** The recorded
`ModifyInstanceSpec --DryRun true` returned `InvalidInstanceStatus.NotStopped`.
That does not show that later checks passed. Query `DescribeResourcesModification`
before stopping; repeat the dry run while stopped in the approved window and
require `DryRunOperation` before applying. Verify the original type remains an
eligible rollback target; inventory can still change.
[Resize API reference](https://www.alibabacloud.com/help/en/ecs/developer-reference/api-ecs-2014-05-26-modifyinstancespec).

For a 2 GB trial, review the reported 4 GB `effective_cache_size`; about 1 GB is
a starting planner estimate, not a RAM allocation or demonstrated memory saving.
Consider a persistent 1 GB swapfile on the existing disk after checking free space,
but treat swap as a fallback, not extra working capacity. Projected headroom is
unmeasured. Check connection counts and concurrent `work_mem` consumers under load.

**Option 4 is why the disk stays as it is.** §12 established that `ModifyDiskSpec`
refuses this change in both instance states, with
`InvalidDiskCategory.NotSupported` for the category and
`InvalidPerformanceLevel.Malformed` for the performance level. A rebuild route
using `ReplaceSystemDisk` would reinstall the operating system:
PostgreSQL, schema, credentials and units rebuilt, against a live evidence clock,
with no off-host copy, to save $4.29/month. Fold it into the next rebuild that
happens for some other reason, with image compatibility, restore and disk size
validated then. An API rejection does not prove all migration routes impossible.
After monthly subscription conversion the matrix's disk-tier saving is **$4.04**,
not the PAYG saving of $4.29; rebuild effort and restore risk remain non-zero.

**Option 5 cannot be done at all without a rebuild.** A system disk can grow in
place; it cannot shrink.

**Option 6 is deferred.** Savings require economical mode (`StopCharging`), not
an OS shutdown or a standard stop. Disks and EIP remain chargeable and released
compute capacity may be unavailable on restart.
[Economical-mode documentation](https://www.alibabacloud.com/help/en/ecs/user-guide/economical-mode).

The stop mode should still be confirmed before relying on it, but it is not
unknown here: infrastructure redesign §12 measured this host at **$1.10/day
running ($0.85 compute + $0.24 disk) and $0.24/day stopped**. Compute billing
therefore did cease on a previous stop of this instance, which is evidence that
the no-charge path is available to it — not a guarantee that a future stop will
take the same path, or that released capacity will be returned on restart.

The dashboard would be unavailable, and infrastructure redesign §14 already
records a missed restart costing 1.7 hours. A future schedule must use the
authoritative trading calendar, including daylight-saving changes and early
closes, with startup/reconciliation buffers. Never stop with open exposure,
working orders or unresolved reconciliation; require an external restart check
and alert. Subscription removes the compute savings, so do not combine them.
Overnight uptime is operational evidence; it does not itself prove exits or
qualify the six-week shadow study when no positions exist.

**Option 7 is not justified by this cost study.** This product is an always-on
auditable firewall with a worker lease and a durable audit trail. Moving to
Function Compute and a serverless database would require evaluating lifecycle,
lease and recovery semantics. No alternative was quoted or benchmarked, so do
not claim a negative saving as a measured result. Revisit only for requirements
or total ownership benefits that justify migration.

**Option 8 is the first implementation priority alongside billing.** Export a
verified database dump and recovery metadata to encrypted storage outside the
production account's payment boundary. Add recurring export, retention, failure
alerts and a restore drill. A completed manual snapshot can supplement this for
host rollback; it does not replace the independent copy. A one-time backup has
an increasing recovery-point gap as new evidence arrives. See §7.2.

## 4. Three target configurations

| | Configuration | $/month | vs now | Trade-off |
|---|---|---:|---:|---|
| **A. Scheduled lower bound — deferred** | `e-c1m1.large`, 20 GB entry disk, PAYG economical mode at 157.5 h/month | **~4.35 base** | −87% base | Requires rebuild and scheduling; not equivalent availability. Excludes backup/network/tax. |
| **B. Preferred conditional target** | `e-c1m1.large`, 40 GB PL1, 1-month subscription, independent backup and optional snapshot | **14.20 base + verified extras** | −57.5% base | After C passes. Always on; preserve disk/EIP. Requires funding and renewal planning. |
| **C. Validation stage** | `e-c1m1.large`, 40 GB PL1, PAYG, independent backup | **20.39 base + verified extras** | −39% base | Billing and capacity gates first; maintenance outage. Rollback requires another resize and available capacity. |

Fallback if 2 GB is unsuitable: retain `e-c1m2.large` and its disk; the reported
one-month subscription quote is **$22.38 base**. Recovery protection is mandatory
for either size. B is the preferred trade-off for the present small deployment,
not a high-availability design.

## 5. Assumptions, and what could not be measured

- PAYG uses 730 hours/month for comparison, not the length of every billing month.
  The illustrative 13:00–20:30 UTC window across 21 weekdays is **157.5 hours**, not
  163. It is not an implementation schedule. A's base is approximately
  `(14.55 - 1.55) × 157.5 / 730 + 1.55 = $4.35`.
- **Backup storage is now priced, not estimated.** `GetPayAsYouGoPrice`
  returns **$0.0240597/hour per 1024 GB** for OSS Standard in this region =
  **$0.01715/GB-month**. Infrequent-access ($0.0092) and Archive ($0.0018)
  rates, and the ECS snapshot rate (~$0.05/GB-month), are **published figures
  used as assumptions** — the billing API does not expose them. Snapshot blocks
  can exceed filesystem usage; verify billed size and any free allowance.
- Utilisation is a point-in-time sample, plus `sar` over roughly 24 hours and
  systemd `MemoryPeak` since boot, with an uptime of 4 days 23 hours. **There is
  no CloudMonitor time series here**, so a peak outside that window cannot be
  excluded. Retained logs cannot establish lifetime absence of OOM, and successful
  operation at 4 GB does not validate a 2 GB limit.
- Reserved instances and savings plans were not priced. The quoted one-month
  subscription has a shorter commitment; this study does not establish whether
  it captures most of the discount available from other products.
- Prices are list prices for `ap-southeast-1` in USD, exclusive of tax.
- Total product cost also includes model inference, any paid market-data plan,
  and optional DNS/TLS/monitoring services. These are not quoted here. Current
  zero model calls cannot be projected as zero future inference cost.
- The original query outputs are not attached. Preserve redacted, timestamped
  quotes and billing exports before implementation; do not treat this revision
  as a new live account audit.

## 6. Prioritised: highest saving, lowest operational risk

1. **Take one verified off-host dump and restore it into a scratch database.**
   22.5 MB, ~$0.0004/month, no window, no funding, no decision required. It is
   the only item here that reduces a risk which grows every day it is deferred.
2. **Confirm the account carries no restriction** (§0) and refresh quotes.
   Minutes, not a project. Accrued balance alone does not block anything.
3. **Validate eligibility and capacity, then trial 2c2g on PAYG** — potential
   **$12.99/month, 39%** base saving. Preserve the disk and EIP; record downtime.
4. **Observe at least five consecutive trading sessions**, including a
   backup/restore overlap. Keep PAYG until §7 acceptance is met.
5. **Add the daily off-host copy** — **$0.00** by operator pull, since OSS is
   refused. It can follow the resize rather than gate it. Add the monthly
   restore-validation check with it.
6. **Convert to one-month subscription only after acceptance** — a further
   **$6.19/month** base saving. Record renewal owner, date and total quote.
7. **Defer disk rebuild, scheduled stops and architecture migration.** The disk
   saving after subscription is $4.04/month; no rebuild is justified by that alone.

The preferred target reduces the **compute + disk** baseline from **$33.38 to
$14.20/month**, saving **$19.18 (57.5%)**, with a planned maintenance interruption.
Total monthly cost is that base plus verified backup, network, applicable tax and
any separately scoped provider charges. No zero-downtime claim is made.

## 7. Implementation handoff and acceptance gates

All items below are **pending**. The account owner owns billing, backup destination
and purchase decisions; the deployment operator owns execution and evidence. Name
both in the change record before scheduling. Writing this plan does not establish
that any gate passed.

### 7.1 Verify inventory, quotes and eligibility before maintenance

- Record UTC query time, account/region scope, instance type, disk/EIP
  attachments, instance status and billing method. Query all relevant
  products and regions before repeating the claim that no other resources exist.
- **Billing: confirm the account is not restricted, in the same hour as the
  window.** Accrued month-to-date charges and a $0.00 prepaid balance are the
  expected postpaid steady state and are *not* a reason to delay (§0). What
  would be: an explicit restriction notice, or a write call returning a
  payment-related error rather than a state error. Do configure a balance alert
  and confirm renewal funding before any subscription purchase.
- Refresh both PAYG and one-month quotes for the existing instance/disk
  combination. Save period, region/zone, currency, discounts, tax treatment and
  scope. Verify a conversion quote applies to this existing instance, not only a
  promotional new purchase.
- Query `DescribeResourcesModification` for eligible target types and record
  rollback eligibility to `ecs.e-c1m2.large`. Do not interpret a failed dry run
  as approval.

**Exit gate:** quotes current, resize eligibility established, no restriction
notice outstanding. Otherwise retain the running configuration.

### 7.2 Backup design

Rewritten in v0.3 against the specific question: what is actually needed after
the first copy? The answer is far less than v0.2 demanded, because the thing
being protected is smaller and more replaceable than that section assumed.

#### What is and is not recoverable without a backup

Audited on the host 20 September, rather than assumed.

| Runtime state | Location | In git? | Recoverable without a backup |
|---|---|---|---|
| **PostgreSQL database** | `/var/lib/postgresql` on `/dev/vda3` | no | **No — the only one.** ~49 MB |
| Redis, queues, message brokers, any second datastore | — | — | **None exist.** Only `127.0.0.1:5432` listens; `redis`, `memcached`, `rabbitmq`, `mongod`, `mysql` all inactive |
| `health.json`, `watchdog.json` | `/var/run/options-alpha` | no | Yes — `RuntimeDirectory`, rewritten every tick and watchdog run |
| `backup.json` | `/var/lib/options-alpha` | no | Yes — rewritten hourly by the backup job |
| `ablation_h0.json`, `h0_paper_lifecycle.{json,md}` | `/opt/options-alpha/artifacts` | **yes, all tracked** | Yes. Host `ablation_h0.json` md5 `7afe16b7…` matches the tracked blob exactly |
| `build/` | `/opt/options-alpha` | no | Yes — pip build output, regenerated on install |
| systemd units | `deploy/systemd/` | yes, since `CIIP-I-016` | Yes |
| worker arming drop-in | `/etc/systemd/system/options-alpha-worker.service.d` | n/a | **Directory absent** — the worker is disarmed, so there is no drop-in to lose |
| Credentials | `/etc/options-alpha.env`, `~/.aliyun/config.json` | **no, deliberately** | Re-issued, never restored. Must not enter any backup that reaches the repository |
| journald | `/var/log` | no | Diagnostics only. `CIIP-I-008` makes the database authoritative for anything the product surfaces |

The claim holds: **one ~50 MB PostgreSQL database is the entire irrecoverable
runtime state.** Everything else is either in the repository, regenerated
automatically, or deliberately excluded.

#### Do we need continuous backups? No

What a gap costs is the measure, and `CIIP-VAL-013` gives it: the worker records
~65 decisions per trading day, all reading the **same completed daily close**, so
**one lost day is one lost independent observation**, not sixty-five. There are
no positions, no orders and no model calls, so nothing financial is at stake and
no reconciliation state can be orphaned.

A 24-hour recovery point costs at most one observation out of a six-week study,
and the loss is recordable as a gap rather than silently wrong. **Daily is
proportionate. Hourly off-host replication is not justified.**

#### Tier 0 — local recovery history, **not** disaster recovery

`options-alpha-backup.timer` runs `pg_dump -Fc` **hourly**, keeps **12**, and
verifies each dump by restoring it into a scratch database and dropping it.
Measured: **22.46 MB** per dump, 326 MB total.

**Those dumps sit on the same block device as the database they protect.**
Verified: `/var/backups/options-alpha` and `/var/lib/postgresql` both resolve to
`/dev/vda3`. The distinction matters and v0.2 blurred it:

| Failure | Tier 0 covers it? |
|---|---|
| Accidental `DROP`, bad migration, logical corruption | **Yes** — 12-hour local history, restore in minutes |
| Disk corruption, instance loss, failed `ReplaceSystemDisk`, region event | **No.** The dumps die with the disk |

So Tier 0 is **local recovery history at $0.00** and contributes **nothing** to
the disaster-recovery objective. **Tier 2 is what provides the 24-hour off-host
RPO.** Keep Tier 0 exactly as it is — it is free and it covers the likeliest
failures — but do not count it as protection against losing the host.

#### Tier 1 — one-time migration safety copy

For the resize only:

1. One verified dump copied **off the host** before the maintenance window —
   22.5 MB. With OSS refused this is an operator `scp` pull, at **$0.00**. It
   must leave the instance: a copy that stays on `/dev/vda3` protects against
   nothing the resize could do.
2. Optionally one ECS snapshot of the system disk (4.1 GB used) —
   **~$0.20/month while retained**, at an assumed $0.05/GB-month.

**Deletion:** delete the snapshot **7 days after the resize passes validation**.
Keep the dump — at $0.0004/month it is cheaper to retain than to reason about,
and it anchors the provenance of the evidence clock.

**This is a resize, not a migration.** `ModifyInstanceSpec` changes the instance
type in place: the same disk, the same EIP, the same data, no second host and
nothing copied between machines. **There is no original server to delete
afterwards, and at no point does any resource run solely to hold a backup.**
The only path that destroys disk contents is the *deferred* disk rebuild
(`ReplaceSystemDisk`), which is precisely why it stays deferred.

#### Tier 2 — recurring off-host backup: this is the DR tier

One dump per day, off the host. **This tier alone carries the 24-hour recovery
point**; Tier 0 contributes nothing to it.

**The intended target is unavailable.** OSS `CreateBucket` was re-tested on
20 September and still returns `UserDisable`, so `CIIP-I-BLK-001` stands and the
$0.10/month OSS plan **cannot be executed today**. Two routes remain:

| Target | Executable now? | $/month | Notes |
|---|---|---:|---|
| **Operator pull over `scp`** | **Yes** | **$0.00** | Port 22 is open and `deploy_worker.sh` already uses a deploy key. 22.5 MB per copy. Not via Cloud Assistant — its result payload cannot carry 22 MB |
| Third-party object store (S3/B2/R2) | Yes, needs a credential decision | ~$0.01–0.02 | Also removes the single-account tail risk in one step |
| Alibaba OSS | **No** — `UserDisable` | 0.10 | Preferred *if* `CIIP-I-BLK-001` lifts. Re-test `CreateBucket`, not `ListBuckets` |
| ECS snapshot as the recurring tier | **Untested** | ~0.20 | Snapshots are an ECS feature but are stored in OSS; whether the same account restriction applies is **unknown and not tested here** |

Retention, once a target exists — priced at the six-month horizon with the
database growing ~5 MB/day and dumps at ~46% of database size:

| Policy | Standard | Archive | $/month (OSS rates) |
|---|---:|---:|---:|
| Weekly only, 8 weeks | 2.97 GB | — | 0.051 |
| **Daily 7 days → Archive to 90 days** | 2.94 GB | 27.95 GB | **0.101** |
| Daily 14 days → Archive to 90 days | 5.76 GB | 26.54 GB | 0.147 |
| *(v0.2's hourly 48 h → daily 30 d)* | 20.35 GB | 279.43 GB | *0.852* |

**Recommended: daily copies, 7 days hot, archive to 90 days, then delete.** On
the operator-pull route the storage is wherever the operator keeps it and the
Alibaba cost is **$0.00**; the table above prices the OSS route for when it
becomes available.

#### Tier 2b — restore validation

A backup that has never been restored is a hypothesis. Tier 0 already restores
**every** dump into a scratch database and drops it, so local dumps are proven
continuously at no cost. What that does *not* prove is that the **off-host copy**
survived its transfer intact.

So: **once a month, restore the most recent off-host copy into a throwaway
PostgreSQL** — a local container or scratch database, not the production host —
and check three things:

1. `pg_restore --list` enumerates without error;
2. the schema is at the expected `alembic_version`;
3. row counts for `decisions`, `market_snapshots` and `decision_outcomes` match
   the source at the backup boundary, and one decision hash resolves through its
   lineage.

The database is ~50 MB, so this is minutes, not an exercise. Record the date and
the measured restore duration — §7.2's recovery-time figure should be an
observation, not an aspiration. Do not let a restored instance reach the
production database or acquire the worker lease.

#### Tier 3 — the single-account tail

With OSS refused, the executable Tier 2 route (operator pull) **already lands
outside the Alibaba account**, so it closes this tail as a side effect. If OSS
later becomes available and is chosen for convenience, keep one monthly copy
outside the account as well — $0.00, and it is the only thing standing between
an account-level event and the evidence.

#### Retention and deletion policy

| Tier | Cadence | Retention | Deleted by | Cost |
|---|---|---|---|---:|
| 0 — local dumps | hourly | 12 copies | existing script, automatic | $0.00 |
| 1 — pre-resize snapshot | once | 7 days after validation | operator, explicit | ~$0.05 one-off |
| 1 — pre-resize dump | once | indefinite | never | $0.0004/mo |
| 2 — daily off-host **(the DR tier)** | daily | 7 days hot, archive to 90 days | lifecycle rule if OSS; operator script otherwise | **$0.00** pulled, $0.10 on OSS |
| 2b — restore validation | monthly | n/a | n/a | $0.00 |
| 3 — operator copy | monthly | 3 copies, rolling | operator, manual | $0.00 |

Two rules on deletion. Never expire the **newest verified copy**, whatever the
policy says. And never apply retention to live evidence rows — this policy
governs *backups*, not the database, and `CIIP-VAL-013` is explicit that the
records themselves are not a cost-cutting target.

#### Effect on the cost analysis

| Configuration | Base | + backup (executable today) | + backup (if OSS returns) |
|---|---:|---:|---:|
| Current (`e-c1m2.large`, PL1 40 GB, PAYG) | 33.38 | **33.38** | 33.48 |
| C — validation stage (`e-c1m1.large`, PAYG) | 20.39 | **20.39** | 20.49 |
| B — preferred (`e-c1m1.large`, subscription) | 14.20 | **14.20** | 14.30 |

Because OSS is refused, the route that can run today — an operator-pulled dump —
adds **$0.00** to the Alibaba bill. Even the OSS route would add **0.3–0.7%**.
Backup changes no configuration decision either way, which is the point of
pricing it: the recovery gap was never a cost question, and it is now less of
one than v0.2 implied.

**Exit gate:** one verified dump exists **off the instance** and has been
restored into a throwaway PostgreSQL, before the resize. The recurring tier and
its retention rule can follow the resize; they are not prerequisites for it.

### 7.3 Validate the smaller memory envelope

Collect time-series measurements across at least one full trading session and a
backup/restore cycle on the current host. Measure host `MemAvailable`, swap I/O,
memory pressure, CPU/I/O wait, process/cgroup peaks, database connections, API
latency, worker tick duration and lease/reconciliation freshness. The baseline
must include coincident dashboard/API requests and the scratch restore.

Exercise open-position management, reconciliation and the bounded model-response
path in an isolated 2 GB environment using representative fixtures or replay.
If this needs a temporary cloud instance, include its cost in the change record.
Do not open trades or arm production just to generate load. An idle production
week alone cannot substitute for representative capacity testing. Build React in
CI and deploy its static artifacts if that migration is later approved; do not
assume production Node/build workloads fit this memory budget.

Initial acceptance thresholds for the trial (engineering choices to record before
the change, not provider guarantees):

| Signal | Pass condition / rollback trigger |
|---|---|
| Memory | No OOM or memory-related service restart; rollback if `MemAvailable` remains below 256 MiB for five minutes under expected load |
| Swap | No sustained swap thrashing; repeated swapping with missed service deadlines fails the trial |
| Worker | No lease loss, new reconciliation mismatch or missed configured clock deadline attributable to resource pressure |
| API/dashboard | No capacity-related errors; comparable-load p95 latency no more than 20% worse than the recorded baseline |
| Recovery | Export/restore overlap meets the recovery targets without starving the worker or API |
| Trading authority | Preserve the recorded mode and permissions; no new broker-write authority or duplicate worker |

**Exit gate:** representative 2 GB checks pass and metrics/alerts can detect a
regression. Otherwise retain 4 GB and consider its monthly subscription separately.

### 7.4 Resize in a controlled maintenance window

1. Record the live commit, schema revision, effective units/drop-ins, worker mode,
   database role permissions, EIP binding and disk identifiers. Confirm with both
   broker and local records that no positions, working orders or reconciliation
   incidents require continuous management. Defer if this cannot be established.
2. Announce an off-session maintenance window with a **30-minute abort threshold**
   and the recovery operator available. This threshold triggers recovery; it does
   not promise a 30-minute maximum outage. Record the last successful worker tick
   and produce a fresh verified independent backup.
3. Quiesce worker and timers cleanly, then PostgreSQL. Stop through the provider's
   standard/`KeepCharging` mode for maintenance, avoiding the unnecessary resource
   release of economical mode. Wait for `Stopped`, run the explicit dry run, and
   require `DryRunOperation`. On any other result, do not resize; restart the
   unchanged host and investigate.
4. Apply only the instance-type change to `ecs.e-c1m1.large`, then start. Preserve
   the existing disk, EIP and application/schema. Apply documented memory tuning
   and swap configuration if selected in §7.3; record their previous values.
5. Check PostgreSQL and schema first; ensure exactly one worker holds the lease
   and startup reconciliation completes. Check API payloads and rendered dashboard
   content, not only HTTP 200. Confirm database read-only access using
   `deploy/verify_readonly_role.sh`, and verify backup/watchdog timers and alarms.
   Compare evidence hashes/counts to the pre-change checkpoint allowing only
   expected new records. Record the first healthy tick and the actual collection gap.

**Rollback:** on a threshold breach or failure to regain health by the abort
threshold, perform a controlled stop and restore the original 4 GB instance type,
then revert any recorded tuning changes and repeat health checks. Reconfirm safe
exposure handling before another stop. Rollback capacity is not guaranteed; if
unavailable, escalate to the named operator and use the funded recovery plan.
Do not overwrite a healthy, newer database with an old snapshot to undo a memory
resize. Restore data only for demonstrated corruption/loss, preserving the latest
recoverable state and reconciling broker state before resuming writes.

### 7.5 Observe, then choose the billing commitment

Remain on PAYG for **at least five consecutive trading sessions**, including a
backup/restore overlap and the representative load checks in §7.3. Record both
successful checks and incidents; absence of trades/model calls is not proof those
paths fit. Do not change trading authority as part of this cost exercise.

If all thresholds pass, obtain the current conversion quote and have the account
owner approve a one-month subscription. Record renewal date, renewal funding and
alert owner; verify the resulting billing method and service health. Do not rely
on a five-minute outage estimate or a guaranteed rollback. If the trial fails,
retain/restore 4 GB and document why its additional cost is justified.

### 7.6 Completion record

- [ ] Billing status and restrictions verified; owner and maintenance operator named.
- [ ] Redacted quote/query evidence saved with UTC timestamps and exact scope.
- [ ] Independent backup and isolated restore meet recorded recovery targets.
- [ ] Backup-age and failure alerts reach an operator; recurring retention verified.
- [ ] Target and rollback eligibility checked; representative capacity tests passed.
- [ ] Maintenance completed with disk/EIP and trading authority preserved.
- [ ] Post-change health, evidence integrity and actual downtime recorded.
- [ ] Five-session PAYG observation passed, or documented 4 GB fallback selected.
- [ ] Subscription purchased only if accepted; renewal owner and funding recorded.
- [ ] Actual compute, disk, network and backup charges reconciled after a complete
      billing interval; base quote and total operating cost reported separately.
- [ ] Deployment runbook and infrastructure redesign updated with the resulting
      state, date and evidence; historical measurements retained as historical.

Store operational evidence in an access-controlled location; this repository is
public. Link a redacted summary from this document when execution is complete.
Do not publish credentials, database dumps or full account exports.

## 8. Revision history

**v0.3 — 20 September 2026.** Tier 0 is local recovery history only — its dumps
share `/dev/vda3` with the database — so Tier 2 alone carries the DR objective.
The single-irrecoverable-state claim is now **audited**: no Redis, queue or
second datastore exists, host artifacts match their tracked blobs by checksum,
runtime JSON is regenerated, and only the ~50 MB database is irrecoverable.
Monthly restore validation of the off-host copy added. **`CIIP-I-BLK-001` was
re-tested and stands** — `CreateBucket` still returns `UserDisable`, so the OSS
plan is not executable and the daily copy is an operator pull at $0.00. Billing reframed from blocker to monitored
precondition: normal postpaid accrual is not a restriction, and every probe
says the account is unrestricted. OSS answers `ListBuckets` but **refuses
`CreateBucket` with `UserDisable`**, so `CIIP-I-BLK-001` stands. Backup rebuilt around what is
actually irrecoverable — one ~50 MB database, since everything else is on
GitHub — which makes continuous replication unjustified and daily proportionate.
Retention, deletion and the distinction between the one-time copy and the
recurring tier are now explicit. Backup costs **$0.00** on the route that can run
today and $0.10/month on OSS if it returns, against v0.2's implied $0.85. Clarified that the recommended change is an **in-place
resize**, so no second host exists and nothing is deleted afterwards.

**v0.2 — 19 September 2026.** Corrected v0.1's overstated dry-run evidence,
zero-balance executability, suspension-versus-deletion, snapshot limits and
cohort counts; added the implementation handoff and acceptance gates.

**v0.1 — 19 September 2026.** Original account-level analysis and pricing.

Only this document has changed. No account funding, backup export, host
mutation, trading change or subscription purchase has been performed.
