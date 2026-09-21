# Options Alpha

## OSS Backup — Implementation Plan

| Field | Value |
|---|---|
| Version | v0.1 |
| Date | 21 September 2026 |
| Status | **Plan only. Nothing is implemented.** Section 0 must be verified before any step runs |
| Design | [Deployment Cost Analysis §7.2](../improvements/options_alpha_deployment_cost_analysis_v0_1.md) |
| Unblocked by | `CIIP-I-BLK-001`, resolved 21 September — OSS activated in the console |
| Delivers | A 24-hour off-host recovery point for the one irrecoverable asset: a ~50 MB PostgreSQL database |
| Does **not** deliver | `CIIP-I-002`'s 30-day PITR, which needs WAL archiving rather than periodic dumps |

### Host facts, measured 21 September

| | |
|---|---|
| OS | Ubuntu 24.04.4 LTS |
| `age` | **Packaged: 1.1.1-1ubuntu0.24.04.3.** Not installed. No third-party repository needed |
| OSS client | **None present** — no `ossutil`, no `aliyun` CLI, no `oss2` in the venv |
| Internal endpoint | `oss-ap-southeast-1-internal.aliyuncs.com` → `100.118.219.12`, **resolves** |
| Free space | 34 GB |
| Dump | 22.46 MB, `pg_dump -Fc`, produced and verified hourly already |

---

## 0. What must be verified before execution

Each of these changes the plan if it turns out otherwise. None is assumed below
without being listed here.

### 0.1 Versioning changes what "expire" means — **highest impact**

On a versioned bucket, a lifecycle `Expiration` rule does **not** free the data.
It writes a **delete marker** and the object becomes noncurrent; the bytes
persist until a `NoncurrentVersionExpiration` rule removes them.

If that holds here, the retention described in the design is **nominal, and the
real storage lifetime is the sum of both rules** — `daily/` would hold bytes for
7 days current plus 7 days noncurrent, not 7 total, and the cost estimate is
correspondingly low.

**Verify:** enable versioning on a scratch bucket, write an object, apply an
`Expiration: 1 day` rule, and observe whether the data is billed after the
marker appears. **Then restate the retention table in terms of total lifetime,
and reprice.** Do not carry the current figures forward unchecked.

### 0.2 Archive objects cannot be read without `RestoreObject`

Retrieving an Archive-class object requires a `RestoreObject` call and a wait —
minutes to hours — before a `GetObject` succeeds.

This lands squarely on **§8 restore validation**: a drill that happens to select
a `weekly/` object older than 7 days will fail unless it restores first. The
drill must either target `daily/` deliberately, or include the restore step and
its wait.

**Verify:** the restore latency tier available on this account, and whether
`RestoreObject` incurs a separate retrieval charge at this volume.

### 0.3 RAM action names and resource scoping

The design calls for an identity that may create objects and read metadata and
nothing else. Confirm the exact action names — `oss:PutObject`, `oss:GetObject`,
`oss:GetObjectMeta`, `oss:ListObjects` — and, more importantly, **whether a
prefix-scoped list is expressible.** Some object stores can only scope listing at
bucket granularity; if OSS is one of them, the monitor gets list rights over the
whole bucket and that should be a recorded decision rather than an accident.

**Verify:** that a policy denying `oss:DeleteObject`, `oss:DeleteObjectVersion`,
`oss:PutBucketVersioning`, `oss:PutBucketLifecycle` still permits the upload, by
testing with the real identity against a scratch bucket before production use.

### 0.4 Per-prefix noncurrent rules

Confirm OSS lifecycle supports `NoncurrentVersionExpiration` **filtered by
prefix**, so `daily/`, `weekly/` and `anchor/` can differ. If rules are
bucket-wide only, the layout needs three buckets instead of three prefixes, and
§1 changes.

### 0.5 Archive minimum duration — already reasoned, still worth confirming

A lifecycle-transitioned object counts the 60-day Archive minimum from its
last-modified time, and `weekly/` expires at day 63, so no early-deletion charge
should arise. Confirm against the first real invoice rather than the docs.

---

## 1. Bucket creation and region

**Region: `ap-southeast-1`**, matching the ECS instance. This is not a
preference. A same-region bucket can be reached over
`oss-ap-southeast-1-internal.aliyuncs.com`, which the host already resolves, and
that path carries **no public egress charge** and does not traverse the
internet. A bucket in any other region forfeits both.

- One bucket, private ACL, no static website, no public read.
- Name must be globally unique and DNS-safe; use a project prefix and avoid
  anything that reveals account structure.
- **Use the internal endpoint in the uploader.** The public endpoint should
  appear nowhere in the service configuration.

## 2. Versioning

Enable **before the first upload** — preferred ordering, not a correctness
requirement: Alibaba applies lifecycle rules to pre-existing objects as well as
new ones, with up to ~24 hours to take effect.

Versioning is the overwrite protection the design depends on: `PutObject`
overwrites a key by default, and the uploader has no delete permission, so
without versioning an overwrite is still destructive.

In normal operation it costs nothing, because object keys carry the dump's date
and no key is ever rewritten. Versions appear only on overwrite — the case being
defended against.

## 3. Lifecycle configuration

**Subject to §0.1 and §0.4.** Written as intended; restate once those are known.

| Prefix | Current version | Noncurrent versions | Purpose |
|---|---|---|---|
| `daily/` | expire at 7 days | expire 7 days after becoming noncurrent | Rolling recent history |
| `weekly/` | transition to Archive at 7 days, expire at 63 | expire 63 days after becoming noncurrent | Cheap medium history |
| `anchor/` | **no rule** | **no rule** | The pre-resize copy. Removed only by explicit human action |

`anchor/` must be excluded from every rule, not merely given a long one. A rule
with a large number still deletes eventually; no rule never does.

## 4. Least-privilege RAM identity

One RAM user, one access key, used only by the backup service.

**Allow, scoped to this bucket and these prefixes:**

| Action | Why |
|---|---|
| `oss:PutObject` | Writing the daily object is the whole job |
| Minimum read for the monitor — `oss:GetObjectMeta`, and `oss:ListObjects` if metadata alone cannot find the newest key | §7 must read the newest object's timestamp |

**Deny everything else**, explicitly: `oss:DeleteObject`,
`oss:DeleteObjectVersion`, `oss:PutBucketVersioning`, `oss:PutBucketLifecycle`,
`oss:PutBucketWorm`, `oss:*` on any other bucket, and bucket creation.

The uploader may create objects and read their metadata. It cannot remove
history, disable the protection that retains it, or rewrite the rules that bound
it. It also cannot read backup **contents** usefully, because it holds no `age`
identity.

Store the access key in `/etc/options-alpha-backup.env`, mode `0600`, root-owned,
referenced by `EnvironmentFile=`. **Not** in `/etc/options-alpha.env` — the
backup identity and the broker identity should not share a blast radius.

## 5. `age` encryption

```
apt-get install age          # 1.1.1-1ubuntu0.24.04.3, already in Ubuntu 24.04
```

No third-party repository, no pinned binary, no build step.

**Key handling, in order:**

1. **Generate the identity off-host** — `age-keygen` on the operator's machine.
   Never on ECS.
2. **Two protected copies of the private identity**, both off the production
   host, in places that do not fail together.
3. **Copy only the recipient (public) key to the instance**, e.g.
   `/etc/options-alpha-backup.pub`, world-readable is acceptable — it is public.
4. The private identity **never** touches ECS, in any form, at any point.

**Pipeline:** `pg_dump -Fc` → `age -r <recipient>` → upload. Plaintext is never
written to OSS, and preferably never to disk: prefer a pipeline to a staged
temporary file, and if a temporary file is unavoidable, place it under a
root-only directory and remove it in a `trap`.

Symmetric encryption is not an acceptable substitute, and the private key is not
to be generated on ECS and moved off. Generating off-host is the requirement.

## 6. Daily upload timer

A new `options-alpha-backup-offsite.{service,timer}`, beside the existing
`options-alpha-backup.timer` rather than inside it — the local hourly job is
proven and should not be made to depend on network reachability.

- Runs once daily, after a local dump exists. `Persistent=true`, so a missed run
  fires on boot.
- Key format: `daily/YYYY-MM-DD.dump.age`. Weekly day additionally writes
  `weekly/YYYY-MM-DD.dump.age` — the same bytes, a second key, no re-encryption.
- Uploads via the **internal endpoint**.
- Records the outcome to `worker_events` as a durable fact, per §7.
- Never deletes anything, locally or remotely.

A client must be installed: **`ossutil`** is preferred over adding `oss2` to the
application venv, which would change the application's dependency set and the
freeze manifest for a concern unrelated to the application.

## 7. Monitoring: 30-hour object age

The mechanism that makes 24 hours a property rather than an intention.

1. **Age check.** Extend the existing watchdog to read the newest `daily/`
   object's `LastModified` and fail when it exceeds **30 hours** — one cycle
   plus margin.
2. **Durable failure reporting.** An upload can fail while the API call
   succeeds; `UserDisable` was exactly that shape. Record any non-2xx as a fault
   event in `worker_events`, so it survives a log rotation and is visible on the
   dashboard rather than only in the journal.
3. **A dead host cannot report itself.** The age check catches "uploads stopped
   while the host lives", which is the failure this design makes likely. Host
   loss is already visible through the stale worker lease. Neither check
   subsumes the other, and neither should be described as covering both.

## 8. Monthly restore validation

**Runs on the operator's machine, not on ECS** — only the operator holds the
private identity, and a drill performed where a real recovery would happen is
worth more than one performed on the box being recovered from.

1. Download the newest `daily/` object. **Prefer `daily/`**: a `weekly/` object
   older than 7 days is in Archive and needs `RestoreObject` first (§0.2).
2. `age -d -i <identity>` → `pg_restore` into a throwaway PostgreSQL.
3. Verify: `pg_restore --list` enumerates; `alembic_version` matches
   expectation; row counts for `decisions`, `market_snapshots` and
   `decision_outcomes` match the source at the backup boundary; one decision
   hash resolves through its lineage.
4. **Record the measured restore duration**, so the recovery-time figure is an
   observation rather than an aspiration.
5. The restored instance must never reach the production database or acquire the
   worker lease.

## 9. Rollback, cleanup and verification

### Verification after each step

| Step | Command | Expected |
|---|---|---|
| Bucket | `ossutil stat oss://<bucket>` | exists, private ACL |
| Versioning | `ossutil bucket-versioning --method get oss://<bucket>` | `Enabled` |
| Lifecycle | `ossutil lifecycle --method get oss://<bucket>` | three prefixes as §3; `anchor/` absent from all rules |
| RAM | upload as the backup identity; then attempt `rm` and a lifecycle write | upload succeeds, **both others denied** |
| `age` | `age -r <pub> </dev/null \| age -d -i <identity>` on the operator machine | round-trips |
| Timer | `systemctl list-timers options-alpha-backup-offsite` | scheduled, next run shown |
| End to end | run the service once; list `daily/` | one object, size ≈ dump, **not** plaintext |
| Encryption | `ossutil cat` the first bytes | `age-encryption.org/v1`, never SQL |
| Monitor | set the threshold to 0 temporarily | fault event appears in `worker_events` |

### Rollback

Each step reverses independently, and nothing here touches the application, the
database or trading authority:

1. Timer: `systemctl disable --now options-alpha-backup-offsite.timer`. Uploads
   stop; nothing else changes.
2. RAM identity: disable the access key. The uploader fails closed; the local
   hourly dumps continue untouched.
3. Lifecycle/versioning: remove the rules. **Objects already written remain** —
   this is the direction that cannot be undone by deletion, which is the point.
4. Bucket: delete only after confirming it holds nothing worth keeping. A
   versioned bucket needs its versions and delete markers removed first.
5. `age`: uninstalling is harmless. **Destroying the private identity is not** —
   it makes every stored backup unreadable, permanently.

### Cleanup that is *not* part of rollback

The `anchor/` object and the pre-resize snapshot are deliberate artifacts with
their own lifetimes, recorded in the design. Do not remove them as part of
unwinding this work.
