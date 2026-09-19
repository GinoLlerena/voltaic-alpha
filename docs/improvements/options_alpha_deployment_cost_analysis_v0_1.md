# Options Alpha

## Deployment Cost Analysis

| Field | Value |
|---|---|
| Version | v0.1 |
| Date | 19 September 2026 |
| Status | **Analysis only.** No infrastructure or deployment file was modified |
| Scope | Every paid resource in the account: compute, storage, network, database, CI/CD |
| Supersedes | Nothing. Extends [§12 of the infrastructure redesign](options_alpha_infrastructure_redesign_v0_1.md), which priced the host on 11 September |
| Method | Live account queries — `DescribeInstances`, `DescribeDisks`, `DescribePrice`, `QueryInstanceBill` — and on-host measurement, not estimates |

---

## 0. The finding that comes before any optimisation

**September's bill is $31.07 and entirely unpaid.** `QueryBillOverview` reports
`cash=$0, outstanding=$31.07`; `QueryAccountBalance` reports `available=0.00,
credit=0.00`.

This is the same condition that disabled OSS under `CIIP-I-BLK-001` and that
`restore_hosted_demo.sh` warns about in its preflight phase. It outranks every
saving in this document, because this host holds **the only copy** of 331
decisions and two weeks of evidence: no snapshot exists, and the backups sit on
the same disk they protect. A suspension for non-payment costs the whole
evidence clock, which cannot be regenerated.

It also constrains what can be done. **Subscription pricing requires
prepayment, so it cannot be purchased at a $0 balance.** Of the options below,
only the pay-as-you-go rightsizing is executable today.

## 1. What is actually running

| Component | Spec | Purpose | Required? | $/month |
|---|---|---|---|---:|
| ECS `i-t4n88bkfwsq0lhzmfjii` | `ecs.e-c1m2.large`, 2 vCPU / 4 GB, PostPaid, `ap-southeast-1a` | Worker, Streamlit dashboard, FastAPI read API, PostgreSQL | Yes | **25.99** |
| System disk `d-t4n88bkfwsq0lhzp8xth` | 40 GB `cloud_essd` **PL1** | OS, code, database, backups | Yes — not at this size or tier | **7.39** |
| EIP `eip-t4nog5mmlwazufrsn8nfz` (`47.236.50.157`) | PayByTraffic, 5 Mbps | The public dashboard address | Yes | **0.01** |
| Cloud Data Transfer | — | — | — | 0.00 |
| Load balancer, NAT gateway, snapshots, custom images, OSS | **none exist** | — | — | 0.00 |
| GitHub Actions | ~282 job-seconds per run | CI: lint, types, tests, PostgreSQL replay, browser gate | Yes | **0.00** |
| | | | **Total, list** | **33.38** |

Two things are worth stating because they are easy to assume otherwise.

**There is no load balancer and no managed database.** Port 80 reaches Streamlit
through an `iptables` REDIRECT installed by `options-alpha-port80`, and
PostgreSQL runs on the same box. At a 49 MB database and one viewer at a time,
both are the right call; a managed database here would cost more than the entire
current deployment.

**CI is free.** The repository is public, so GitHub Actions runs on standard
runners at no charge. There is no lever in CI/CD, however much it runs.

### Observed spend

| Period | Amount | Note |
|---|---:|---|
| August 2026 | $8.86 | Host created 28 August; partial month |
| September 1–19 | **$31.07** | Of which **$12.03** belongs to three instances **already released** |
| — the live host alone | $19.04 | $14.45 compute + $4.59 disk, over 19 days |

The live host therefore runs at **$1.002/day observed** against a **$1.097/day**
list rate; the gap implies roughly 1.4 days stopped. Forward run rate at the
current specification is **$33.38/month**.

$12.03 of September — 39% — was paid for instances that no longer exist. That
is already fixed and is not a future saving; it is recorded so the month's total
is not mistaken for the run rate.

## 2. Utilisation against allocation

| Resource | Allocated | Measured | Verdict |
|---|---|---|---|
| CPU | 2 vCPU | load average **0.16 / 0.04 / 0.01**; `sar` ~0.03 across 24 h; **98.3% idle** | Heavily over-provisioned |
| Memory | 4 GB (3 499 MB usable) | **949 MB used**, 2 550 MB available. Peaks since boot: dashboard 136 MB, worker 145 MB, API 64 MB, PostgreSQL 203 MB. **Zero OOM kills in the instance's lifetime** | Over-provisioned ~2× |
| Disk | 40 GB ESSD PL1 | **4.1 GB used (11%)**: `/opt` 639 MB, PostgreSQL 136 MB, backups 326 MB, logs 82 MB. The database itself is **49 MB** | Over-provisioned in size *and* performance tier |
| Network | 5 Mbps, pay by traffic | $0.01 egress for the month | Correctly sized |

`shared_buffers` is 128 MB and `work_mem` 4 MB. Nothing in this workload — a
five-minute tick, a low-traffic dashboard and a 49 MB database — needs 4 GB.

This is the third time the volume question has been answered the same way, and
the answer has not changed: **the data is not the cost.** ECS bills provisioned
GB and CPU-hours. Deleting rows saves exactly $0.00; only releasing provisioned
capacity or stopping compute reduces spend.

## 3. Options, priced against this account

Every figure comes from `DescribePrice` for this region and zone.

| # | Change | From | To | Saving/mo | % | Effort | Recommendation |
|---|---|---:|---:|---:|---:|---|---|
| 1 | **2c4g → 2c2g** (`ecs.e-c1m1.large`) | 33.38 | 20.39 | **12.99** | 39% | Stop → modify → start, ~5 min | **Now** |
| 2 | PAYG → 1-month subscription, same spec | 33.38 | 22.38 | 11.00 | 33% | Billing only, no downtime | Blocked on funding |
| 3 | **Options 1 and 2 together** | 33.38 | 14.20 | **19.18** | 57% | 5 min + prepayment | **Now, once funded** |
| 4 | Disk PL1 → `cloud_essd_entry` | 7.39 | 3.10 | 4.29 | 13% | **Full rebuild** | Only inside a rebuild |
| 5 | Disk 40 GB → 20 GB | 3.10 | 1.55 | 1.55 | 5% | **Full rebuild** | Only inside a rebuild |
| 6 | Stop outside market hours | 25.99 | ~5.80 | 20.19 | 60% | New automation | **Later** |
| 7 | Serverless / managed-database rewrite | — | — | *negative* | — | Months | **Not at all** |
| 8 | **Add one snapshot** | 0.00 | ~0.30 | **−0.30** | — | One API call | **Now** |

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

**Option 1 is validated rather than assumed.** `ModifyInstanceSpec --DryRun true`
returned `InvalidInstanceStatus.NotStopped` — every other parameter passed
validation, so `ecs.e-c1m1.large` is a legal target for this instance and only
the running state blocks it. That call changes nothing by definition.

Going to 2 GB needs two mitigations, neither of which costs anything:
`effective_cache_size` is currently set to 4 GB and should drop to about 1 GB —
it is a planner hint, not an allocation — and the box has **no swap**, so a 1 GB
swapfile is worth adding as a floor. Measured headroom after the change is about
1 GB, and the instance has never recorded an OOM kill.

**Option 4 is why the disk stays as it is.** §12 established that `ModifyDiskSpec`
refuses this change in both instance states, with
`InvalidDiskCategory.NotSupported` for the category and
`InvalidPerformanceLevel.Malformed` for the performance level. The only
remaining route is `ReplaceSystemDisk`, which reinstalls the operating system:
PostgreSQL, schema, credentials and units rebuilt, against a live evidence clock,
with no off-host copy, to save $4.29/month. Fold it into the next rebuild that
happens for some other reason, where the marginal cost is one parameter.

**Option 5 cannot be done at all without a rebuild.** A system disk can grow in
place; it cannot shrink.

**Option 6 is the largest single lever and is still the wrong move today.** It
trades away precisely what the spend is buying: the overnight and weekend ticks
are what prove the exit and reconciliation paths `CIIP-4` needs, the public
dashboard is dark whenever the host is stopped, and §14 already records a missed
restart costing 1.7 hours of live session. It is also **mutually exclusive with
subscription** — a prepaid instance bills for all 730 hours whether it is running
or not. Revisit when `CIIP-4` has its evidence.

**Option 7 is a genuine anti-optimisation.** This product is an always-on
auditable firewall with a worker lease and a durable audit trail. Moving to
Function Compute and a serverless database would add cold starts, require the
lease semantics to be rebuilt, and enlarge the operational surface — to save
perhaps $10/month on a $33/month system. The cheapest architecture is not the
one that is cheapest to run for a month; it is the one that is cheapest to run
and still correct in a year.

**Option 8 costs money and is recommended anyway.** There is currently no
disk-level recovery of any kind: no snapshot, and the backups live on the disk
they protect. The brief asked not to optimise purely for price, and this is
where that applies.

## 4. Three target configurations

| | Configuration | $/month | vs now | Trade-off |
|---|---|---:|---:|---|
| **A. Minimum viable** | `e-c1m1.large`, 20 GB entry disk, PAYG, stopped outside market hours | **~4.45** | −87% | Needs a rebuild *and* scheduling automation that does not exist. Dashboard dark most of the week; loses the overnight evidence `CIIP-4` depends on. Cheapest and most fragile. |
| **B. Balanced** | `e-c1m1.large`, 40 GB PL1, 1-month subscription, one snapshot | **~14.50** | −57% | No rebuild. Keeps the evidence clock and the public URL. Requires prepayment, so blocked until the account is funded. |
| **C. Safe rightsizing only** | `e-c1m1.large`, 40 GB PL1, PAYG | **20.39** | −39% | One stop/start, fully reversible, no billing commitment, no rebuild. **The only configuration executable at a $0 balance.** |

## 5. Assumptions, and what could not be measured

- 730 hours per month. The stop-window in option 6 assumes 163 hours — 13:00 to
  20:30 UTC across 21 weekdays — derived from observed decision timestamps of
  13:45 to 19:14 UTC.
- **Snapshot pricing is the one figure not retrieved from the account.**
  `DescribePrice` does not cover snapshots; ~$0.30/month assumes roughly
  $0.05–0.07 per GB-month against 4.1 GB used. Verify before relying on it.
- Utilisation is a point-in-time sample, plus `sar` over roughly 24 hours and
  systemd `MemoryPeak` since boot, with an uptime of 4 days 23 hours. **There is
  no CloudMonitor time series here**, so a peak outside that window cannot be
  excluded — though zero OOM kills across the instance's lifetime is good
  evidence against one.
- Reserved instances and savings plans were not priced. At this scale the
  one-month subscription already captures most of the available discount at a
  fraction of the commitment.
- Prices are list prices for `ap-southeast-1` in USD, exclusive of tax.

## 6. Prioritised: highest saving, lowest operational risk

1. **Settle the outstanding $31.07 and fund the account.** Saves nothing and
   protects everything. A suspension loses the only copy of the evidence.
2. **Take one snapshot** (~$0.30/month). Costs money; removes the largest single
   risk in the architecture.
3. **Rightsize 2c4g → 2c2g** — **$12.99/month, 39%**, about five minutes of
   downtime, reversible, and already validated by dry run. The best ratio here.
4. **Convert to a one-month subscription** — a further **$6.19/month** on the
   rightsized instance, no technical change, one month of commitment. After
   funding.
5. **Fold the entry-tier disk into the next rebuild** — $4.29/month at zero
   marginal effort *when a rebuild happens anyway*, and not worth causing one.
6. **Revisit stop-scheduling once `CIIP-4` has its evidence** — $10–20/month,
   but today it would destroy the thing being paid for.

Items 3 and 4 together take the run rate from **$33.38 to $14.20 per month, a
57% reduction**, without a rebuild, without an architectural change, and without
losing a minute of the evidence clock.
