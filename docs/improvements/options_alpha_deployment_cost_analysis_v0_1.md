# Options Alpha

## Deployment Cost Analysis

| Field | Value |
|---|---|
| Version | v0.3 (filename retained for existing links) |
| Date | 19 September 2026 |
| Status | **Reviewed recommendation and implementation handoff.** Infrastructure changes are not executed; acceptance gates below are pending |
| Scope | Reported Alibaba infrastructure and GitHub CI/CD costs; not total product operating cost |
| Supersedes | v0.1 recommendations in this file. Extends [§12 of the infrastructure redesign](options_alpha_infrastructure_redesign_v0_1.md); its September 11 prices remain historical |
| Method | v0.1 from live account queries and host measurement. v0.2 checked repository evidence, arithmetic and provider documentation without re-querying. **v0.3 re-verified live on 20 September**: restriction probes, an OSS `CreateBucket` test, a host state audit, and OSS storage pricing from the billing API |

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
| `oss CreateBucket` | **succeeds** since activation — 3 of 4 probes across four hours; `CIIP-I-BLK-001` resolved |

That last row is now settled. `CreateBucket` refused with `UserDisable` at
21:16Z on 20 September and succeeded at 22:03Z because **OSS was activated in
the console** between the two tests. Confirmed by delayed probes at **23:05Z and
01:05Z**, both successful, with `AvailableAmount` at $0.00 throughout — so the
cause was activation, not the balance. **`CIIP-I-BLK-001` is resolved.**

`ListBuckets` answered the whole time, including while `CreateBucket` refused.
That is the lesson worth keeping: a service can be reachable and still refuse
the operation you need, so §7.2 probes the operation it depends on.

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

1. **Take one verified safety copy off the instance and restore it.** Manual
   operator `scp`, 22.5 MB, $0.00, no window, no funding, no decision required.
   This satisfies the **pre-resize gate** and nothing more: it is a one-time
   artifact that ages from the moment it is taken, and it is **not** the 24-hour
   RPO. Still first, because it is the only item that reduces a risk which grows
   every day it is deferred.
2. **Confirm the account carries no restriction** (§0) and refresh quotes.
   Minutes, not a project. Accrued balance alone does not block anything.
3. **Validate eligibility and capacity, then trial 2c2g on PAYG** — potential
   **$12.99/month, 39%** base saving. Preserve the disk and EIP; record downtime.
4. **Observe at least five consecutive trading sessions**, including a
   backup/restore overlap. Keep PAYG until §7 acceptance is met.
5. **Stand up the recurring DR tier: a daily public-key-encrypted push to OSS**
   — **$0.023/month at steady state, $0.063 at six months**. Two prefixes with
   separate lifecycle rules (`daily/` expiring at 7 days, `weekly/` archived at
   7 and expiring at 63), both enforced by OSS server-side; the host holds no
   delete permission. A newest-object age check fails at 30 hours and any
   non-2xx upload becomes a durable fault event. Add the monthly restore
   validation — which runs on the operator's machine, since only it holds the
   private key — and the Tier 3 off-account copy.

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

One encrypted dump per day, pushed off the host. **This tier alone carries the
24-hour recovery point**; Tier 0 contributes nothing to it.

**Target: Alibaba OSS.** `CreateBucket` was refused with `UserDisable` at
21:16Z on 20 September and succeeded at 22:03Z. **OSS was activated in the
console between those two tests**, which explains the change: the service was
not enabled on the account, and then it was. A full round trip then passed —
create, put, list, get with identical bytes, delete object, delete bucket.

An earlier draft read that flip as evidence of *intermittent* availability and
built the design around it. That was the wrong inference from the right
observation. There is no evidence OSS comes and goes; there is evidence it was
off and is now on.

Upload-failure handling and object-age monitoring stay regardless. They are not
compensation for an unreliable target — they are the ordinary controls any
unattended backup needs, and their absence is how a backup stops running without
anyone noticing.

##### The mechanism, in five parts

| | What | Runs where | Cost |
|---|---|---|---:|
| Produce | `pg_dump -Fc`, already running hourly | existing `options-alpha-backup.service` | $0.00 |
| Encrypt | client-side, before upload | same timer | $0.00 |
| Push | one dump per day to OSS | new systemd timer beside the existing one | negligible |
| Retain / delete | OSS **lifecycle rule** | **OSS itself, server-side** | $0.00 |
| Monitor | newest-object age check | existing watchdog timer | $0.00 |

**No additional server, at any point.** The push is a timer on the host that
already exists; retention and deletion are executed by OSS itself with no
compute; the Tier 3 copy is a manual monthly action. Nothing here runs
continuously except things already running.

##### Frequency, retention and automatic deletion

An earlier draft specified "one daily stream, transition at 7 days, expire at
63" and claimed it produced 7 daily plus 8 weekly objects. **It does not.** A
single stream under one age rule yields 63 daily objects, not a daily set and a
weekly set. Two prefixes with separate rules are needed to express that policy.

| | `daily/` | `weekly/` |
|---|---|---|
| **Written** | every day | one per week, same dump, written to both prefixes |
| **Storage class** | Standard | Standard, then Archive |
| **Transition** | none | **to Archive at 7 days** |
| **Expiry** | **7 days** | **63 days** |
| **Steady-state count** | 7 | 9 |

The uploader's only decision is whether today is also the weekly day; it writes
the same encrypted object to one prefix or to both. It never deletes anything.

**Deletion is executed by OSS lifecycle rules, server-side.** The production
host runs no pruning job and holds no delete permission, so neither a host
failure nor a stray script can remove stored backups, and neither runaway
retention nor premature deletion originates on that side.

**Withholding delete is not sufficient on its own**, and an earlier draft
claimed more than the mechanism gives. `PutObject` overwrites an existing key by
default, so an identity that can only write can still destroy a backup's
contents by writing over it.

**Required baseline: bucket versioning.** An overwrite then creates a new
version and retains the previous one, so the old bytes survive the write. This
is the control this design depends on.

In normal operation it costs nothing. Object keys carry the dump's date —
`daily/2026-09-20.dump.age` — so the uploader never writes an existing key and
no noncurrent versions are produced. Versions appear only when something
overwrites, which is precisely the case being defended against.

Noncurrent versions still need bounding, per prefix, or an attacker who
overwrites repeatedly inflates the bill instead of destroying the data:

| Prefix | Current version | Noncurrent versions |
|---|---|---|
| `daily/` | expire at 7 days | expire 7 days after becoming noncurrent |
| `weekly/` | Archive at 7 days, expire at 63 | expire 63 days after becoming noncurrent |
| `anchor/` | no expiry | **retain** — one 22.5 MB object, and an overwrite here is the event worth keeping evidence of |

**WORM is documented as an optional stronger control, not a requirement.**
Bucket-level WORM applies a single retention period to the entire bucket, and
this layout deliberately carries three different horizons — 7 days, 63 days and
indefinite — which one period cannot express without changing the retention
policy itself. Object-level WORM could, but Alibaba documents it as
invitation-only, so the design must not depend on it. If separate buckets are
later used per horizon, or ObjectWorm is confirmed available on this account,
WORM becomes available as an upgrade; until then, versioning is the mechanism.

##### The uploader's permissions, for the implementation phase

Grant the **minimum and nothing beyond it**. Written as an allow-list rather
than a deny-list, because a deny-list silently grants whatever it forgot to
name:

| Allowed | Why |
|---|---|
| `oss:PutObject` on the backup prefixes only | Writing the daily object is the uploader's entire job |
| The minimum read/list the object-age monitor needs — `oss:GetBucket`/`ListObjects` scoped to those prefixes, or `oss:GetObjectMeta` | The 30-hour age check must read the newest object's timestamp. Nothing more; it does not need to read backup contents, and cannot decrypt them anyway |

Everything else is withheld: **no delete of any kind** (`DeleteObject`,
`DeleteObjectVersion`), **no version management** (`PutBucketVersioning`), **no
lifecycle management** (`PutBucketLifecycle`), **no WORM configuration**
(`PutBucketWorm`), and **no broad OSS access** — not `oss:*`, not bucket
creation, not access to any other bucket or prefix in the account.

The uploader may create objects and read their metadata. It cannot remove
history, disable the protection that retains it, or rewrite the rules that bound
it.

With versioning in place and that policy applied, the accurate claim is: **a
compromised host can write new objects and can obscure the newest backup, but
cannot destroy the retained history.** Without versioning, the only claim
available is that deletion is not permitted — which leaves overwrite open, and
overwrite is enough.

| Horizon | Objects | Standard | Archive | $/month |
|---|---|---:|---:|---:|
| Day 7 | 7 daily + 2 weekly = 9 | 0.25 GB | 0.02 GB | **0.004** |
| Day 42 | 7 + 7 = 14 | 0.88 GB | 0.37 GB | **0.016** |
| **Day 63 — steady state** | **7 + 9 = 16** | 1.26 GB | 0.74 GB | **0.023** |
| Day 182 | 7 + 9 = 16 | 3.40 GB | 2.88 GB | **0.063** |

The steady state is **nominally 16 objects, reached at day 63** — the set the
policy intends to retain, bounded by count rather than age, which is why cost
grows with the database rather than with elapsed time.

**It is not an instantaneous inventory.** OSS lifecycle processing is
asynchronous: objects past an expiry or transition boundary can persist for some
time before the rule is applied, so a bucket listing may show more than 16
objects, or objects still in Standard that the policy has already marked for
Archive. The table above is therefore an **approximation from the intended
policy**, accurate enough for a figure in the third decimal of a dollar and not
intended as a billing prediction.

The previous figure of "$0.056 for 15 objects" was arithmetic over a model that
could not produce those objects at all; the corrected six-month approximation is
**$0.063**.

The 60-day minimum billable duration for Archive was checked against this
policy. A lifecycle-transitioned object counts that minimum from its
last-modified time, and `weekly/` objects expire at day 63, so nothing is
deleted inside its minimum term and no early-deletion charge arises.

##### The protected copy

An age-based lifecycle rule cannot exempt "the newest verified object" — it has
no concept of verification, and the earlier claim that such an object would
never be deleted was not enforceable by the mechanism described.

Two things replace it:

1. **A third prefix, `anchor/`, with no lifecycle rule at all.** It holds the
   one-time pre-resize copy and nothing else. Never transitioned, never expired,
   deleted only by an explicit human action. One object, 22.5 MB, $0.0004/month.
2. **For the rotating tiers, no exemption is claimed.** Protection there comes
   from the retention window and the 30-hour age alert: the window is 7 days of
   dailies, so a failure must go unnoticed for a week before the newest good
   copy expires, and the alert fires after 30 hours.

##### Encryption: public-key, so the host cannot decrypt its own backups

Encrypt **client-side, before upload**, so the stored object is opaque to the
storage account. Server-side encryption alone protects against disk theft at the
provider, not against anything that can read the bucket.

Use **asymmetric encryption**. The host holds only a **public** key; the
**private key never touches the production machine** and lives with the
operator, away from the host it would be used to rebuild.

**Be precise about what this does and does not protect.** The host can
obviously read the live database — it runs the thing. What the asymmetric design
buys is narrower and still worth having: **the host holds no private key, so its
backup credentials and key material cannot decrypt previously stored backup
objects.** An attacker who compromises the host gets today's plaintext, which
they would have anyway from PostgreSQL. They do not thereby get a readable
archive of every prior day.

A symmetric scheme forfeits exactly that. It requires the decryption secret to
sit on the production host, so one compromise yields the live data *and* the
entire history. The asymmetric design costs nothing extra and removes the second
half.

Concretely: `age` with a recipient public key, or `openssl smime`/GPG with an
RSA or ECC public key — any tool where encryption needs only the public half.

Two consequences worth stating, because they are the price of this choice:

- **A lost private key means unreadable backups.** There is no recovery path,
  by design. Hold it in at least two places the host cannot reach.
- **Restore validation (§7.2b) needs the private key**, so it runs on the
  operator's machine, not on the host. That is the right place for it anyway —
  a restore drill performed on the production box proves less than one performed
  where a real recovery would happen.

##### Monitoring: what makes this an RPO rather than a hope

An upload that silently stopped three weeks ago is indistinguishable from one
that ran this morning, until the moment it is needed. This is the part that
makes the 24-hour figure a property of the system rather than an intention.

1. **Age check.** The existing watchdog already reads `backup.json` for local
   dump age. Extend it to record the **newest OSS object's timestamp** and fail
   when it exceeds **30 hours** — one daily cycle plus margin.
2. **Alarm on refusal, not just on absence.** An API call can succeed at the
   transport level and still refuse the operation — `UserDisable` was exactly
   that shape. Treat any non-2xx upload as a fault event in `worker_events`, so
   it is durable and visible rather than a line in a journal nobody reads.
3. **The host cannot report its own death.** An on-host check catches "uploads
   stopped while the host lives", which is the failure this target makes likely.
   Host loss is already visible through the stale worker lease on the dashboard.
   Neither check subsumes the other.

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

With OSS as the Tier 2 target, **every automated copy lives inside one Alibaba
account** — the same account whose OSS service refused a request an hour before
it accepted one. Tier 3 is therefore required, not optional, and it is the only
thing standing between an account-level event and the evidence.

**One copy per month, pulled to operator-controlled storage outside the account.**
Manual, `scp`, about 25 MB today. Keep three rolling. **$0.00.**

It is deliberately not automated. Automating it would need either another
always-on machine — which this design refuses — or credentials for a second
provider on the same host, which reintroduces the exposure Tier 3 exists to
avoid. A monthly manual action whose absence is visible in a checklist is the
proportionate answer for a tail risk.

If Tier 2 later moves to a third-party store, this tier can be retired: that
target already sits outside the account.

#### Retention and deletion policy

| Tier | Cadence | Retention | Deleted by | Cost |
|---|---|---|---|---:|
| 0 — local dumps | hourly | 12 copies | existing script, automatic | $0.00 |
| 1 — pre-resize snapshot | once | 7 days after validation | operator, explicit | ~$0.05 one-off |
| 1 — pre-resize dump, **interim operator `scp`** | once | indefinite | never | $0.00 |
| 2 — daily encrypted push to OSS **(the DR tier)** | daily, unattended | `daily/` 7 days; `weekly/` Archive at 7, expire 63 (**nominal**) | **OSS lifecycle rules, server-side**; **bucket versioning** against overwrite | **~0.023 → ~0.063** as data grows |
| 2c — `anchor/` protected copy | once | **no lifecycle rule** | explicit human action only | $0.0004/mo |
| 2b — restore validation | monthly | n/a | n/a | $0.00 |
| 3 — off-account copy | monthly, manual | 3 rolling | operator | $0.00 |

Two rules on deletion. Never expire the **newest verified copy**, whatever the
policy says. And never apply retention to live evidence rows — this policy
governs *backups*, not the database, and `CIIP-VAL-013` is explicit that the
records themselves are not a cost-cutting target.

#### Effect on the cost analysis

Costed against the **recurring DR tier**, now OSS. The one-time interim copy and
the monthly Tier 3 copy are not recurring charges.

| Configuration | Base | + DR backup, steady state | + DR backup, at six months |
|---|---:|---:|---:|
| Current (`e-c1m2.large`, PL1 40 GB, PAYG) | 33.38 | 33.40 | **33.44** |
| C — validation stage (`e-c1m1.large`, PAYG) | 20.39 | 20.41 | **20.45** |
| B — preferred (`e-c1m1.large`, subscription) | 14.20 | 14.22 | **14.26** |

Backup is **0.02–0.4%** of the bill. It adds no server, no licence and no
recurring human task beyond one monthly copy. The recovery gap was never a cost
question, and pricing it confirms that rather than changing it.

#### What happens to the data after the resize

Asked directly, because "migration" invites the wrong assumption.

**The resize is in place.** `ModifyInstanceSpec` changes the instance type of
the existing host. The same system disk stays attached, the same EIP stays
bound, PostgreSQL's data directory is untouched and no bytes move between
machines. There is no new server, no copy step and therefore **no original
server to decommission**.

| Artifact | After validation |
|---|---|
| The database | **Untouched throughout.** Never deleted, never re-created, never restored unless something actually failed |
| `/dev/vda3` and its contents | Preserved. The disk is not replaced |
| Tier 0 hourly dumps | Continue unchanged; the existing script keeps pruning to 12 |
| Pre-resize **snapshot** | **Delete 7 days after validation passes.** The only artifact created for the change and the only one deliberately removed |
| Pre-resize **`scp` copy** | Keep indefinitely. 22.5 MB, $0.00, and it anchors the provenance of the evidence clock |
| EIP, security group, units | Unchanged |

The single deletion in the whole exercise is that snapshot, and only once the
host has been healthy for a week. Restore data **only** on demonstrated
corruption or loss — never to undo a memory resize, and never overwriting a
healthy newer database with an older copy.

**Exit gate for the resize:** one verified dump exists **off the instance** and
has been restored into a throwaway PostgreSQL. The interim operator `scp` copy
satisfies this — a single independent safety copy is all the resize requires.

**This gate is not the 24-hour RPO.** They are separate objectives: the gate
protects one planned change, the RPO is a standing property of the deployment.
Passing the gate says nothing about the RPO, and the recurring push in Tier 2
can be built after the resize without holding it up. Do not record the gate as
evidence the recovery objective is met.

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

**Baseline collection — started 23 September 2026, 15:49 UTC.**
`options-alpha-capacity.service` runs `scripts/capacity_baseline.py` every 30 s
at `Nice=10`, writing one JSON line per sample to
`/var/lib/options-alpha/capacity/YYYY-MM-DD.jsonl` (about 2.4 MB a day). It
records `MemAvailable`, swap-in/out and OOM-kill counters, CPU and I/O-wait
jiffies, PSI pressure for memory, CPU and I/O, per-service cgroup
`memory.current` and `memory.peak` (worker, dashboard, API, PostgreSQL, and the
backup and offsite jobs while they run), database connections, lease heartbeat
age, worker tick age and `management_batch_ms`, and loopback latency for the
API and dashboard. It holds no credential and changes nothing. The hourly backup
restores into a scratch database, so every hour includes the backup/restore
overlap this section asks for. Summarise a session with, for example:

```
/opt/options-alpha/.venv/bin/python /opt/options-alpha/scripts/capacity_baseline.py \
  --summarize --start 2026-09-24T13:30 --end 2026-09-24T20:00
```

First reading, idle and outside a full session: about 1.0 GiB of 3.5 GiB in
use; worker 129 MiB, dashboard 112, API 65, PostgreSQL 166; no swap configured.
One reading proves nothing about peaks — that is what the session is for. Leave
the collector running through any 2 GB trial so a regression is visible against
this baseline.

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

### 7.7 2c2g trial record

#### Decision — account owner, 23 September 2026

**Run the reversible pay-as-you-go trial (§7.4–§7.5).** Memory is treated as
passed on the representative evidence below. **Latency is explicitly unresolved**
until measured on the real server; this is **not** a waiver of the 20% gate. No
subscription is bought and the 2 GB size is not made permanent until the trial
passes. The trial starts only after a complete production baseline, runs
off-session, and is preceded by verification of the latest backup, the instance
state, monitoring and the rollback procedure.

#### Rollback criteria — any one returns the instance to `ecs.e-c1m2.large`

1. p95 latency more than **20%** worse than the pre-registered baseline session,
   for any of the three probes (`/api/v1/system/status`, `/api/v1/decisions`,
   dashboard health).
2. Any **OOM kill**.
3. Memory pressure (PSI `some avg10`) above **1.0** in any sample, **or** present
   in more than **1%** of samples.
4. `MemAvailable` under **256 MiB for five minutes** (this section's own memory
   criterion).
5. Any API or dashboard probe failure, failed worker tick, stalled worker (tick
   older than 900 s) or late lease heartbeat (over 120 s), or failed hourly
   backup (which includes its restore) or off-host upload.
6. Fewer than **90%** of the expected 780 session samples in either window, or a
   missing latency series — insufficient or inconclusive measurement.

**Revised 26 September 2026 (criterion 3).** The owner's first wording rolled
back on *any* memory-pressure event. The 4 GB baseline itself showed PSI 0.12 in
2 of 780 samples on 24 September — about 12 ms stalled in a 10 s window, with
2.4 GB free — so that rule could not tell a healthy server from a struggling
one. The owner approved the thresholds above: 1.0 is about eight times the worst
baseline reading and still only 1% of the time stalled; 1% of samples is ten
times the baseline rate. Criterion 4 was added at the same time.

#### Representative 2 GB check — operator Mac, 23 September 2026

The whole stack in **one** container — PostgreSQL 16, the API, the dashboard, the
rehearsal loop (deterministic and model arms; the bounded memo served by a local
stub at its 900-character maximum), the H0 replay, and a backup-and-restore cycle
every minute — against a copy of production data, pinned to **2 CPUs**, with no
swap. Load: four API clients and three real browser sessions throughout.

| Pair | Order | Peak (4 GB / 1,500 MiB cap) | OOM | Pressure | Failures | API p95 | Dashboard p95 |
|---|---|---|---|---|---|---|---|
| 1 | baseline first | 961 / 1,036 MiB | 0 | 0.00 | 0 | contaminated¹ | contaminated¹ |
| 2 | baseline first | 990 / 976 MiB | 0 | 0.00 | 0 | 142 → 208 ms (+46%) | 4.2 → 6.3 s (+50%) |
| 3 | capped first | 1,021 / 993 MiB | 0 | 0.00 | 0 | 161 → 202 ms (+26%) | 5.4 → 6.6 s (+22%) |

¹ The full test suite ran on the same machine during pair 1; its latencies are
not evidence and are not used.

**Memory passed firmly.** **Latency was not demonstrated:** the capped run was
slower in both clean pairs, above the 20% limit, while memory pressure never left
0.00 — so the cap is an unlikely cause, and a laptop cannot model the instance's
CPU. That question is what the trial answers.

The 1,500 MiB cap is the budget a 2 GiB instance leaves for the application:
~1,707 MiB `MemTotal` after the image's 256 MiB crash-kernel reservation, less
~170 MiB of non-application memory that cannot be reclaimed (agents 88,
kernel 82). The Cloud Assistant agent's 741 MiB cgroup figure is 691 MiB of
reclaimable file cache.

#### Production baseline — 4 GB, collected by `options-alpha-capacity.service`

| Session (13:30–20:00 UTC) | Samples | API status p95 | API decisions p95 | Dashboard p95 | Pressure | Min `MemAvailable` | Peak used | OOM | Failures |
|---|---|---|---|---|---|---|---|---|---|
| Thu 24 Sep | 780 / 780 | 38 ms | 29 ms | 5 ms | 0.12 in 2 samples | 2,410 MiB | 1,090 MiB | 0 | 0 |
| **Fri 25 Sep** | **780 / 780** | **35 ms** | **29 ms** | **4 ms** | none | 2,487 MiB | 1,012 MiB | 0 | 0 |

**Pre-registered baseline: Friday 25 September, 13:30–20:00 UTC** — the most
recent full session and the stricter of the two. Fixed before the trial so it
cannot be chosen after seeing the result.

Peak use of 1,090 MiB leaves about 600 MiB free on a ~1,707 MiB instance — more
than twice criterion 4's floor.

**Control tests of the evaluator**, 4 GB against itself: Thursday as baseline
and Friday as trial, and the reverse — **PASS both ways**, with day-to-day p95
movement of −10% to +11%. Thursday's two pressure blips pass under the revised
criterion 3; under the original wording they would have forced a rollback of a
healthy server.

#### Preflight — 23 September 2026, read-only

Pay-as-you-go (`PostPaid`), zone `ap-southeast-1a`; **both** `ecs.e-c1m1.large`
and `ecs.e-c1m2.large` available with stock; `ModifyInstanceSpec` dry run returned
the state error `InvalidInstanceStatus.NotStopped` (permission present);
`StopInstance` dry run returned `DryRunOperation`. The operator key cannot attach
RAM roles (`PassRoleForbidden`) and does not need to for a resize. Stock is
re-checked for both types immediately before stopping: rollback capacity is not
guaranteed and the tooling will not stop a healthy instance for a change that
cannot land.

#### Procedure — `scripts/resize_trial.py`, run from the operator machine

`preflight` (read-only) → `resize --to ecs.e-c1m1.large`, which records a
checkpoint; takes a fresh verified dump, uploads it encrypted and copies it
server-side into `anchor/`; takes a system-disk snapshot (optional per §7.2,
deleted seven days after validation); quiesces timers, the worker, the API, the
dashboard and PostgreSQL; stops in `KeepCharging` mode; requires a
`DryRunOperation`; changes only the instance type; starts; and waits for
`health` — every unit active, exactly one lease holder, a real API payload, the
dashboard, a clean startup reconciliation, a first tick and a green watchdog.
**Not healthy within the 30-minute abort threshold → automatic resize back to
`ecs.e-c1m2.large`.** The rollback path is the same code; checkpoint and quiesce
are best-effort there, so an unwell host cannot block its own rescue. Every
`aliyun` call's stderr is captured and redacted.

After the trial session, `evaluate --apply` compares the trial window with the
pre-registered baseline and **resizes back automatically** on any criterion.

#### Schedule

| | UTC |
|---|---|
| First weekly off-host copy written and verified, on the unchanged server | Sun 27 Sep |
| Maintenance window (owner reachable) | Sun 27 Sep — to be confirmed |
| Trial session | Mon 28 Sep, 13:30–20:00 |
| Evaluation, with automatic rollback on any criterion | Mon 28 Sep, after 20:00 |

#### Results

*To be recorded:* window start and end, actual downtime, the post-change health
record and `MemTotal`, the trial session's samples, latencies and memory, the
verdict and reasons, and the final instance type.

## 8. Revision history

**v0.3 — 20 September 2026.** Re-verified live rather than reasoned from v0.1.

*Billing.* Normal end-of-month postpaid accrual is not a restriction; every
probe says the account is unrestricted. Demoted from blocking finding to a
pre-flight check. `CIIP-I-BLK-001` is unaffected and **stands**: `CreateBucket`
still returns `UserDisable`, so the OSS backup target is unavailable.

*Backup.* Rebuilt around an audited claim — one ~50 MB database is the only
irrecoverable runtime state, since no second datastore exists, host artifacts
match their tracked blobs by checksum, and runtime JSON regenerates. Tier 0 is
local recovery history only, sharing `/dev/vda3` with the database, so Tier 2
alone carries the 24-hour RPO. Continuous replication is unjustified: one lost
day costs one independent observation. Monthly restore validation added for the
off-host copy, which nothing previously proved had survived transfer.

*Execution model.* An operator laptop pull is an interim copy, not an RPO
mechanism; the unattended route is a host push to a third-party store, priced
honestly at $0.035–0.134/month at six months rather than the "$0.01–0.02" first
quoted from today's data size.

*Scope.* The recommended change is an in-place resize, so no second host is
created and nothing is deleted afterwards.

**v0.5 — 21 September 2026.** `CIIP-I-BLK-001` **resolved**: `CreateBucket`
succeeded at 22:03Z, 23:05Z and 01:05Z after refusing at 21:16Z, with the
balance at $0.00 throughout, so OSS activation was the cause. The uploader's
permissions are specified as an allow-list for the implementation phase —
`PutObject` on the backup prefixes plus the minimum read the age monitor needs,
and nothing else.

**v0.4 — 20 September 2026.** Backup design settled on OSS, which was
**activated in the console** between a refused and a successful `CreateBucket` —
an activation, not intermittency, and an earlier draft drew the wrong inference
from it. Upload-failure handling and object-age monitoring stay regardless, as
ordinary controls rather than compensation.

Retention reworked: a single daily stream under one age rule cannot yield a
daily set and a weekly set, which is what the previous draft claimed. Two
prefixes now carry separate lifecycle rules — `daily/` expiring at 7 days,
`weekly/` transitioned to Archive at 7 and expiring at 63 — giving a **nominal**
steady state of 16 objects at ~$0.023/month, ~$0.063 at six months. Lifecycle
processing is asynchronous, so that set is the policy's intent rather than an
instantaneous count, and the costs are approximations. Both rules run
server-side.

Withholding delete permission was claimed to stop a compromised host destroying
backups. It does not: `PutObject` overwrites an existing key by default.
**Bucket versioning is now the required baseline**, with per-prefix noncurrent
version rules so overwrites cannot inflate the bill either. WORM is documented
as an optional upgrade rather than an alternative: bucket-level WORM applies one
retention period to a bucket carrying three different horizons, and object-level
WORM is invitation-only, so neither can be depended on here. The uploader's RAM
policy denies `DeleteObjectVersion`, `PutBucketVersioning`, `PutBucketLifecycle`
and `PutBucketWorm`.

The unenforceable "newest verified object is never deleted" is replaced by an
`anchor/` prefix carrying no lifecycle rule, plus honest reliance on the 7-day
window and the 30-hour alert for the rotating tiers.

Encryption is **public-key**, with the guarantee stated precisely: the host can
read the live database because it runs it, but holds no private key, so its
credentials cannot decrypt previously stored backup objects. A compromise yields
today's plaintext, not the archive. The private key stays with the operator,
which also moves restore validation off the production machine — where it
belonged anyway.

**v0.2 — 19 September 2026.** Corrected v0.1's overstated dry-run evidence,
zero-balance executability, suspension-versus-deletion, snapshot limits and
cohort counts; added the implementation handoff and acceptance gates.

**v0.1 — 19 September 2026.** Original account-level analysis and pricing.

This revision changes this document and §17 of the infrastructure redesign,
which carried v0.1's superseded billing conclusion. No account funding, backup
export, host mutation, trading change or subscription purchase has been
performed. The only write-class call was an OSS `CreateBucket` probe, which was
refused; its bucket would have been deleted either way.
