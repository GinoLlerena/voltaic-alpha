# Options Alpha

## OSS Backup — Implementation Plan

| Field | Value |
|---|---|
| Version | v0.1 |
| Date | 21 September 2026 |
| Status | **Plan only. Nothing is implemented.** §0.1, §0.3 and §0.4 are resolved from documentation; §0.2 and §0.5 remain to verify at execution |
| Design | [Deployment Cost Analysis §7.2](../improvements/options_alpha_deployment_cost_analysis_v0_1.md) |
| Unblocked by | `CIIP-I-BLK-001`, resolved 21 September — OSS activated in the console |
| Targets | A 24-hour off-host recovery point for the one irrecoverable asset: a ~50 MB PostgreSQL database. **Targets**, not guarantees — see §7.4 |
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

### 0.1 Versioning retention — **resolved from documentation**

Confirmed, not open. On a versioned bucket a current-version `Expiration`
**creates a delete marker** and makes the object noncurrent;
`NoncurrentVersionExpiration` then counts **from that point**. Retention is the
sum of the two rules, not the first of them.

| Prefix | Nominal | **Actual bytes retained** |
|---|---|---|
| `daily/` | 7 days | **~14 days** |
| `weekly/` | 63 days | **~126 days** |

§3 and the cost figures below are restated accordingly. The scratch-bucket test
survives as **execution validation** — confirming the rules were applied as
intended — not as the gate on this decision.

### 0.2 Archive objects cannot be read without `RestoreObject`

Retrieving an Archive-class object requires a `RestoreObject` call and a wait —
minutes to hours — before a `GetObject` succeeds.

This lands on **§8 restore validation**: a drill that selects a `weekly/` object
older than 7 days fails unless it restores first. The drill targets `daily/`
deliberately, and §6 gives the restore identity `RestoreObject` only if Archive
retrieval is ever exercised.

**Verify at execution:** the restore latency tier on this account, and whether
retrieval carries a separate charge at this volume.

### 0.3 RAM permissions — **resolved from documentation**

Also confirmed rather than open:

- **`GetObjectMeta` is authorised by `oss:GetObject`.** There is no separate
  `oss:GetObjectMeta` permission to grant.
- **The monitor needs no object-read permission at all.** `ListObjectsV2`
  returns `LastModified`, which is the only field §7 reads, and `oss:ListObjects`
  can be constrained with an **`oss:Prefix` condition**.

So the host identity gets `oss:PutObject` on `daily/*` and `weekly/*` plus
prefix-scoped `oss:ListObjects`, and **no read of object contents whatsoever**.
It also gets **no write to `anchor/`**: that prefix holds the one-time pre-resize
copy, written once by an operator, and there is no demonstrated need for an
automated identity to touch it.

### 0.4 Per-prefix noncurrent rules — **resolved from documentation**

`NoncurrentVersionExpiration` is an element of a lifecycle rule, and a rule
carries a prefix. The one-bucket layout with separate `daily/`, `weekly/` and
`anchor/` prefixes is therefore supported as designed: three rules, three
prefixes, different noncurrent behaviour in each.

No three-bucket fallback is needed, and §1 stands. The scratch-bucket exercise
remains **execution validation** — confirming the rules were applied as written
— not an architectural decision gate.

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

Restated for versioned-bucket semantics (§0.1). The nominal column is what the
rules say; the retained column is what is actually billed.

| Prefix | Current version | Noncurrent versions | Delete markers | Bytes retained |
|---|---|---|---|---|
| `daily/` | expire at 7 days | expire 7 days after becoming noncurrent | **cleaned up** | ~14 days |
| `weekly/` | transition to Archive at 7 days, expire at 63 | expire 63 days after becoming noncurrent | **cleaned up** | ~126 days |
| `anchor/` | **no rule** | **no rule** | **untouched** | indefinite |

**Delete markers must be cleaned up on the rotating prefixes.** Expiring a
current version on a versioned bucket creates a delete marker, and once the
noncurrent bytes below it are gone the marker remains — one per expired object,
forever, at roughly one per day and one per week. They are tiny, but they
accumulate without limit and clutter every listing the monitor makes. Set
`ExpiredObjectDeleteMarker` on `daily/` and `weekly/`.

**`anchor/` is excluded from every rule**, including marker cleanup. It has no
expiration, so it produces no markers, and the correct configuration for it is
no rule at all — not a rule with a large number, which still deletes eventually.

### Corrected cost

| Horizon | Objects | Standard | Archive | $/month |
|---|---|---:|---:|---:|
| Day 63 | 14 daily + 10 weekly = 24 | 2.25 GB | 0.76 GB | **0.040** |
| **Day 126 — steady state** | **14 + 18 = 32** | 4.37 GB | 2.78 GB | **0.080** |
| Day 182 | 14 + 18 = 32 | 6.26 GB | 4.92 GB | **0.116** |

The design document's figures — 16 objects, $0.023 at steady state, $0.063 at
six months — were computed before the delete-marker behaviour was confirmed and
are **low by roughly 1.8×**. The corrected numbers are still negligible against
a $14–20 base, and the conclusion does not move; the arithmetic does, and the
cost analysis should be updated to match when this plan is executed.

Steady state arrives at **day 126**, not day 63, because `weekly/` noncurrent
versions take that long to age out.

## 4. Least-privilege RAM identities — **two of them**

The host that writes backups and the operator who restores them need different
rights, and combining them would put read access to the archive on the
production box. Two identities, neither able to do the other's job.

### 4.1 The uploader (on ECS)

**Allow, scoped to this bucket:**

| Action | Scope | Why |
|---|---|---|
| `oss:PutObject` | `daily/*` and `weekly/*` only | Writing the daily object is the whole job |
| `oss:ListObjects` | constrained by an **`oss:Prefix` condition** | §7 reads `LastModified` from `ListObjectsV2`. That is the only field it needs |

**No object-read permission at all.** `GetObjectMeta` is authorised by
`oss:GetObject`, and the monitor does not need it — `ListObjectsV2` already
returns the timestamp. Granting `oss:GetObject` to save a call would give the
host the ability to fetch every stored backup, which is exactly what the
encryption design is arranged to prevent.

**No write to `anchor/`.** That prefix holds the one-time pre-resize copy,
written once by an operator. No automated identity has a demonstrated need for
it, so none gets it.

**Denied:** `oss:DeleteObject`, `oss:DeleteObjectVersion`,
`oss:PutBucketVersioning`, `oss:PutBucketLifecycle`, `oss:PutBucketWorm`,
`oss:GetObject`, any access to other buckets, and bucket creation.

Key in `/etc/options-alpha-backup.env`, mode `0600`, root-owned, referenced by
`EnvironmentFile=`. **Not** in `/etc/options-alpha.env` — the backup identity
and the broker identity should not share a blast radius.

### 4.2 The restore identity (operator machine only)

Used by §8 and by a real recovery. **Never installed on ECS.**

| Action | Why |
|---|---|
| `oss:GetObject` | Reading a backup to restore it |
| `oss:ListObjects` | Finding the newest object |
| `oss:RestoreObject` | **Only if** Archive retrieval is exercised — a `weekly/` object older than 7 days |

These are precisely the permissions the uploader must not have. If a single
identity ends up holding both sets, the separation is gone whether or not the
key files are separate.

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

A new `options-alpha-backup-offsite.{service,timer}`, **beside** the existing
`options-alpha-backup.timer` rather than inside it — the local hourly job is
proven and should not be made to depend on network reachability.

### 6.1 It consumes the verified dump; it does not make one

The offsite service **must not run `pg_dump`**. A second dump would be
unverified, would double the load, and would race the hourly job that may be
writing at that moment.

Instead it reads `/var/lib/options-alpha/backup.json`, which the existing
verified backup already writes, and refuses to proceed unless:

- `verified` is `true` — the dump was restored into a scratch database and
  dropped, which is what makes it a backup rather than a file;
- `at` is recent enough to be this cycle's dump rather than a stale record;
- the file at `path` still exists and its size matches `bytes`.

It then encrypts and uploads **that exact file**. The record also carries
`alembic_revision`, `tables` and `rows_restored`, which are worth copying into
the upload's metadata so a restorer knows what they have before decrypting.

If any precondition fails, the service **fails loudly and uploads nothing**. A
missing upload is caught by §7 within 30 hours; an unverified upload is not
caught at all.

### 6.2 Upload mechanism

**`ossutil api put-object`, with forbid-overwrite enabled.** Two reasons beyond
convenience: it keeps the required permission at exactly `oss:PutObject`, and it
**fails safely if the dated key already exists** rather than silently replacing
it — which is the same destructive path versioning exists to catch, refused one
layer earlier.

Install a **pinned official ossutil 2.x** and **verify Alibaba's published
SHA-256** during installation. Not an unpinned installer script: a backup path
that fetches and executes whatever is current is a supply chain into the host
that holds the broker credentials.

Upload over the **internal endpoint**. The public endpoint appears nowhere in
the service configuration.

### 6.3 Weekly mechanics

On the weekly day the same artifact goes to both prefixes. **Encrypt once,
upload the same ciphertext twice:**

1. Stage the ciphertext once, in a **root-only** runtime location —
   `/run/options-alpha/` via `RuntimeDirectory=`, mode `0700`.
2. `put-object` it to `daily/YYYY-MM-DD.dump.age`.
3. `put-object` the **same file** to `weekly/YYYY-MM-DD.dump.age`.
4. Remove it in a `trap`, so it goes even on failure.

No second `pg_dump`, no second encryption pass, and **no plaintext written
anywhere outside the existing backup directory**. Staging under `/run` keeps
the ciphertext off persistent storage entirely.

- Fires **every 4 hours** with `Persistent=true`, uploading **at most once per
  day** because the service is idempotent (§7.1). The cadence is the retry
  mechanism, not a higher backup frequency.
- Records the outcome to `worker_events` as a durable fact, per §7.
- Never deletes anything, locally or remotely.

## 7. Retry and monitoring

### 7.1 Automatic retry, so one bad afternoon does not cost a day

A daily upload that fails transiently — a network blip, a brief API refusal —
would otherwise leave the recovery point 24 hours stale until the next run. That
is a long time to lose to something that would have worked twenty minutes later.

**Run the timer every 4 hours and make the service idempotent.** On each firing
it lists `daily/` for today's key, using the prefix-scoped `oss:ListObjects`
permission §4.1 already grants:

- today's object present → **exit 0, upload nothing**;
- absent → encrypt and upload.

No extra permission, no lock file, no retry counter, and no second mechanism to
maintain. A transient failure costs **at most 4 hours**, and the weekly upload
inherits the same property.

`Persistent=true` covers the case where the host was down at the scheduled time.
Forbid-overwrite (§6.2) remains the backstop: if the listing is stale or racy,
the upload is refused rather than replacing a good object.

### 7.2 The 30-hour age check

The existing watchdog reads the newest `daily/` object's `LastModified` from
`ListObjectsV2` and fails when it exceeds **30 hours** — one daily cycle plus
margin, which with 4-hourly retries means roughly six attempts have failed
before it fires.

### 7.3 Durable failure reporting

An upload can fail while the API call succeeds; `UserDisable` was exactly that
shape. Record any non-2xx as a fault event in `worker_events`, so it survives a
log rotation and is visible on the dashboard rather than only in the journal.

### 7.4 What this does and does not guarantee

Stated plainly, because "24-hour RPO" is easy to read as a promise:

- A daily upload with 4-hourly retries **targets** a 24-hour recovery point.
- The 30-hour alarm **detects a breach** of it.
- **Neither guarantees it.** If OSS is unreachable for two days, the recovery
  point is two days old. Monitoring does not prevent that; it ensures the gap is
  *known* rather than discovered during a recovery.

The honest claim is: **a 24-hour target, with transient failures absorbed by
retry and sustained failures surfaced within 30 hours.** A guarantee would
require a second independent target, which this design does not have and does
not need at this value of data.

### 7.5 A dead host cannot report itself, and this task does not fix that

The age check runs on the host, so it covers exactly one failure: **uploads
stopped while the host is alive.** That is the failure this design makes likely,
and it is worth covering.

An earlier draft claimed host loss was "already visible through the stale worker
lease on the dashboard". That was circular — **the dashboard runs on the same
ECS host**, so a dead host cannot surface its own death through it. External
availability monitoring is a real gap, a separate concern, and explicitly **out
of scope here**. It should not be described as covered.

## 8. Monthly restore validation

**Runs on the operator's machine, not on ECS** — only the operator holds the
private identity, and a drill performed where a real recovery would happen is
worth more than one performed on the box being recovered from.

1. Download the newest `daily/` object, using the **restore identity** from
   §4.2 — never the uploader's key. **Prefer `daily/`**: a `weekly/` object
   older than 7 days is in Archive and needs `RestoreObject` and a wait first
   (§0.2). Exercise that path deliberately at least once, so the latency is
   measured before a real recovery depends on it.
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
| RAM uploader | upload as the backup identity; then attempt `rm`, a lifecycle write, a `GetObject`, and a write to `anchor/` | upload succeeds, **all four denied** |
| RAM restore | `GetObject` as the restore identity | succeeds, and that identity is absent from ECS |
| Forbid-overwrite | `put-object` the same dated key twice | second attempt **refused**, not silently replaced |
| ossutil | compare the installed binary against Alibaba's published SHA-256 | matches the pinned 2.x release |
| `age` | `age -r <pub> </dev/null \| age -d -i <identity>` on the operator machine | round-trips |
| Timer | `systemctl list-timers options-alpha-backup-offsite` | scheduled, next run shown |
| Source dump | run with `verified:false` in `backup.json` | service **refuses** and uploads nothing |
| End to end | run the service once; list `daily/` | one object, size ≈ dump, **not** plaintext |
| Weekly path | run on the weekly day | two keys, **identical ciphertext**, `/run` staging removed afterwards |
| Encryption | `ossutil cat` the first bytes | `age-encryption.org/v1`, never SQL |
| Monitor | set the threshold to 0 temporarily | fault event appears in `worker_events` |
| Retry idempotence | run the service twice in one day | second run exits 0, uploads nothing, creates no second object |
| Delete markers | after a `daily/` object expires and its noncurrent copy ages out | no marker accumulates; `anchor/` unaffected |

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
