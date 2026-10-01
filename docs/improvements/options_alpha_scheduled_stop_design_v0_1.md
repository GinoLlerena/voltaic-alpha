# Options Alpha — Scheduled Stop Design v0.1

| Field | Value |
|---|---|
| Date | 29 September 2026, America/Lima |
| Status | **Enabled 30 Sep 2026, 23:13 UTC**, after every mandatory check passed (§12). Approved by the owner 29–30 Sep |
| Instance | `i-t4n88bkfwsq0lhzmfjii`, `ecs.e-c1m1.large` (2c2g), pay-as-you-go |
| Owner requirements | 27 Sep 2026: an external failed-start alert; a manual override for demos **and** development that does not change the market-hours schedule and that a scheduled stop never interrupts; show the session check before `StopInstance` and how a forgotten override expires; verify both before enabling |
| Cost analysis | [§ Option 6 and §7.7](options_alpha_deployment_cost_analysis_v0_1.md) |

## 1. Why, and what it saves

The server is only useful around US market hours. Running it all the time on 2c2g
costs about **$20.37/month** in compute and disk; stopped in economical mode
(`StopCharging`) outside those hours, about **$10.74/month**. That comes from
DescribePrice: 2c2g compute $0.0178/h, PL1 disk $0.0101/h (billed all 730 hours,
stopped or not), and the §3 window of about 9 h across 21 sessions a month,
roughly 189 running hours. The earlier estimate of $10.36 assumed 168 hours. Backup, network and tax are extra, as in the
cost analysis. The trade-offs, from cost analysis Option 6, still hold:

- The dashboard and API are down off-hours. The owner accepted this on 26 Sep.
- Released compute capacity may not be available on restart. That is why a
  failed-start alert is required.
- The server must never stop with open exposure, working orders or unresolved
  reconciliation.

**Billing mode: checked 30 Sep 2026.**

- The instance is pay-as-you-go, VPC, not spot, with a pay-as-you-go ESSD PL1
  system disk. Economical mode (`StopCharging`) requires exactly this.
- The EIP is pay-by-traffic, and no separate EIP line appears on the daily bill.
- The bill for 29 Sep, the first full day on 2c2g, was **$0.670**. The model
  predicts compute $0.0178 × 24 = $0.427 plus disk $0.0101 × 24 = $0.242, which
  is $0.669.
- The same instance was measured earlier at $0.24/day while stopped in this
  mode (cost analysis Option 6). That is the disk alone.

So the savings rest on real bills, not only list prices. The first stopped
day's bill is still checked during validation (§8, step 6).

## 2. Where the scheduler runs: outside the server and outside the Mac

The instance cannot start itself, and this week showed that the operator Mac and
the Claude session are unreliable schedulers: a cron check-in fired seven hours
late. The scheduler therefore runs on **Alibaba Cloud Function Compute**, on a
15-minute timer trigger, under a dedicated RAM role.

| Choice | Why |
|---|---|
| Function Compute timer, every 15 min | Cloud-side and independent of both the instance and the Mac. The code is Python in this repository, so it is reviewed and tested like the rest. |
| The function decides on every tick, idempotently | No cron-in-UTC arithmetic: each tick computes "should the server be running now?" in `America/New_York`, so DST changes and early closes need no second schedule. A missed tick is caught by the next one. |
| Rejected: OOS scheduled templates | Also cloud-side, but the lock, calendar and readiness logic would live in YAML with little testability. |
| Rejected: cron on the instance or the Mac | The instance cannot start itself, and the Mac proved unreliable. |

The RAM role `oa-scheduler-role` is minimal:

- `ecs:DescribeInstances`;
- `ecs:StartInstance`, `ecs:StopInstance` and `ecs:TagResources` on this one
  instance only;
- `cms:PutCustomEvent` for alerts and a durable decision log.

It has no OSS and no RunCommand. The one tag write exists for a single case: an
invalid lock is rewritten to a valid 24-hour one (§4.2). The policy is committed
as `deploy/scheduler/ram-policy.json`.

## 3. The schedule

Every tick computes a **desired state**:

```
run_window(session) = [open − 60 min, close + 90 min]     # America/New_York
  open − 60 min : worker start-up, lease, startup reconciliation, first tick
  close + 90 min: SPY options trade until 16:15; the post-close backup at
                  17:00 ET; its off-host upload (§6) at about 17:30

desired = RUNNING  if a session's run_window contains now
        = RUNNING  if a valid session lock is active (§4)
        = STOPPED  otherwise
```

On a normal day that is 08:30–17:30 ET, about 9 h. On a 13:00 early close it
ends at 14:30. Weekends and holidays are STOPPED unless a session lock is active.

**Calendar.** Stopped, the server cannot ask Alpaca for its calendar, and the
function holds no broker keys. The function therefore ships the **published NYSE
calendar** (sessions, holidays and early closes, published a year or more ahead)
as a committed JSON file. While the server runs, the function cross-checks the
next 10 sessions against the worker's own Alpaca calendar through a read-only
API endpoint (§7). A mismatch raises an alert. Both unknown cases fail toward
availability:

- A date the committed calendar does not cover is treated as a trading day, so
  the server is started, not left off.
- A calendar the function cannot load means no stop at all.

## 4. The manual session lock: demos and development

**Mechanism: an ECS instance tag.** No new storage and no new credentials are
needed. The owner can set it from the console, on a phone, or with a small CLI.

```
Tag key:   oa-session-until
Tag value: 2026-10-03T22:00Z          # absolute UTC expiry
Tag key:   oa-session-reason
Tag value: dev | demo                  # shown in alerts and logs
```

Owner CLI (`scripts/session.py`, using the owner's own `aliyun` profile):

```
session.py start --hours 4 --reason dev   # tag with until = now + 4 h; StartInstance if stopped
session.py extend --hours 2               # push `until` forward (same cap)
session.py end                            # set `until` to now: the lock expires; after the grace, the next tick stops if off-hours
session.py status                         # desired state, lock, expiry, instance status
```

**What the lock does, and does not do.**

- It keeps the server running outside the schedule: a Saturday development
  session, or a demo at 19:00.
- It never changes the schedule. The window above is computed the same way
  whether or not a lock exists. A lock only adds RUNNING time and can never
  remove any.
- A scheduled stop never interrupts it. The check is below.

### 4.1 The check before `StopInstance`

This is the order on every tick where the desired state is STOPPED and the
instance is Running. Every "no" leaves the server running.

```python
def tick(now):
    inst = describe_instance()                     # status + tags, one call
    lock = read_lock(inst.tags, now)               # §4.2
    if lock.invalid:                               # (0) never a stop past a badly written lock:
        retag(until=now + 24h)                     #     held, alerted, rewritten to the cap
        alert(f"session lock invalid: {lock.problem}")
        return KEEP_RUNNING
    if lock.active:
        log("lock active", reason=lock.reason, until=lock.until)
        warn_if_expiring(lock, now)                # one alert ~30 min before expiry
        return KEEP_RUNNING                        # (1) a session in progress is never stopped
    if calendar_unavailable():
        return KEEP_RUNNING                        # (2) fail toward availability
    if in_run_window(now) or grace_after_lock_end(now, inst):
        return KEEP_RUNNING                        # (3) inside the schedule, or <15 min since a lock ended
    ready = stop_readiness()                       # §7, read-only, from the server itself
    if not ready.ok:
        alert(f"stop skipped: {ready.reasons}")    # (4) open exposure, working orders,
        return KEEP_RUNNING                        #     unreconciled, or today's backup not off-host
    stop_instance(StoppedMode="StopCharging")      # (5) only now
    log("stopped", window_closed_at=..., backup=ready.offsite_key)
```

Step (3)'s 15-minute grace after a lock ends or expires stops the server from
shutting down under a session the owner is just finishing. They get one more
tick to extend.

### 4.2 How a forgotten override expires

```python
MAX_LOCK = timedelta(hours=24)

def read_lock(tags, now) -> Lock:
    raw = tags.get("oa-session-until")
    if raw is None:
        return Lock.none()
    try:
        until = parse_utc(raw)                     # must be ISO-8601 with Z / +00:00
    except ValueError:
        return Lock.invalid("unparseable until")
    if until <= now:
        return Lock.expired(until)                 # expired: treated exactly as no lock
    if until - now > MAX_LOCK:
        return Lock.invalid("longer than 24 h")
    return Lock.active(until, tags.get("oa-session-reason", "unspecified"))
    # Also invalid: a reason with no expiry, and any other `oa-session…` key
    # (a misspelling or wrong case).
```

- Every lock carries its own absolute expiry. There is no "on until I say off"
  state to forget.
- No lock can reach more than 24 h ahead. The CLI refuses longer.
- **An invalid lock never permits a stop (owner, 29 Sep).** Invalid means
  over the cap, unreadable, missing a timezone, a reason with no expiry, or a
  misspelt key. The function keeps the server running (starting it if stopped),
  alerts, and rewrites the tag to a valid lock expiring 24 h from that tick. The
  lock is then honoured and expires normally. If the rewrite fails, the server
  still stays up and the alert repeats on every tick.
- A forgotten session, valid or not, therefore costs at most about one day of
  compute, about $0.43.
- About 30 minutes before expiry, one alert is sent: "dev session ends at 22:00Z;
  `session.py extend` to keep it".
- After expiry, the next tick past the 15-minute grace runs the normal checks
  from §4.1 step (3) onward, and stops the server if it is outside the schedule
  and ready.
- The function never deletes a tag. Its only write is the rewrite above.
  `session.py end` expires a lock by setting `until` to the current time, so
  ending and forgetting follow one path, with the same grace. `session.py
  status` shows the lock as expired, and `start` overwrites it.

### 4.3 Setting the lock from a phone

The ECS web console works in a phone's browser. Times are UTC, and Lima is
UTC−5, so 17:00 Lima is `22:00Z`.

| Action | Console steps |
|---|---|
| **Start a session** | ECS → Instances → `options-alpha-demo` → **Tags** → Edit. Add `oa-session-until` = the end time, e.g. `2026-10-03T22:00Z` (no more than 24 h ahead), and `oa-session-reason` = `dev` or `demo`. Save. If the server is stopped, the next 15-minute tick starts it, or press **Start** to skip the wait. |
| **Extend** | Edit `oa-session-until` to a later time, again no more than 24 h ahead. |
| **End** | Edit `oa-session-until` to the current UTC time. After the 15-minute grace, the next tick stops the server if it is outside market hours. |
| **Check** | The tags show the expiry. The email alerts say when a lock was rewritten or is about to expire. |

A mistyped value can never stop the server. It is held, rewritten to 24 h, and
emailed (§4.2).

*Unverified:* whether the Alibaba Cloud mobile app can edit instance tags.
Until the owner confirms that it can, use the web console in the phone's
browser; the steps above work there.

The rules in §3 and §4 are implemented and tested now, as a pure function
without cloud calls: `src/options_alpha_lab/scheduler.py` (`read_lock`,
`in_run_window`, `decide`) and `tests/test_scheduler.py`. The tests include
every 15-minute tick of a locked Saturday, none of which may end in a stop. The
Function Compute handler only gathers inputs and carries out the decision.

## 5. The failed-start alert, from outside

Two independent layers, so neither the function failing nor the server failing
goes unnoticed:

1. **The function checks its own start.** On the first tick at least 20 minutes
   after `StartInstance`, it requires the instance to be `Running` and the public
   `GET /api/v1/system/status` to return 200 with a worker heartbeat younger
   than 5 minutes. Otherwise it sends an alert. It retries `StartInstance` once
   on `OperationDenied.NoStock` (economical mode may have released the capacity),
   and alerts if that also fails.
2. **Alarms on the function itself.** CloudMonitor watches the function's own
   metrics and emails the owner. `oa-scheduler-errors` fires on any failed
   invocation: a tick that cannot decide raises, after trying to send its own
   alert. `oa-scheduler-silent` fires when the timer delivers nothing for an
   hour. Together they cover the function failing, whatever the cause: a
   permission change, a code error, or a stopped timer.

   *Changed from the first draft (30 Sep):* a site probe on the public URL was
   dropped. CloudMonitor's alert window cannot exclude weekends, so the probe
   would have emailed every weekend while the server is correctly stopped.

**Channel.** Both go through CloudMonitor alert contacts (the owner's email, and
optionally SMS). Neither involves the Mac, a Claude session or any new
third-party service.

## 6. What a stopped server changes elsewhere (implemented 30 Sep 2026)

These ship before enabling, or the first weekend stop would skip backups and
raise false incidents. They are also correct for a server that never stops, so
they ship first.

| Area | Before | Now |
|---|---|---|
| Calendar | Fetched from Alpaca at worker start-up, never stored | `src/options_alpha_lab/data/nyse_sessions.json`: Alpaca's calendar for 2026–2027, fetched on the host with the worker's read-only client by `scripts/refresh_calendar.py`. Used by the uploader, the watchdog, readiness and the scheduler. Past its coverage, each falls back to its previous rule. |
| Daily off-host copy | Keyed by the dump's UTC date: the first dump of each UTC day. The bucket forbids overwrites | Keyed by the **trading session** the dump follows: the first verified dump taken at least 15 min after that session's close. A dump taken during a session uploads nothing, so a partial day is never stored under a session's key. |
| Weekly copy | Sunday (UTC), when a stopped server takes no dump | The week's last session (normally Friday; Thursday 2 Jul 2026, before a holiday). |
| Upload cadence | Every 4 h at :30 | Hourly at :10, ten minutes after the hourly dump. The 17:00 ET post-close dump is off-host by about 17:12 ET, before a 17:30 ET stop. |
| Watchdog freshness | Newest copy under 30 h old | The last completed session's copy is in OSS, checked 3 h after that session's close. A Friday-to-Monday stop leaves a 63-hour-old copy, which is the right one. |
| Watchdog after a start | Old tick, backup and upload records would fail at once | Boot grace: those checks are excused for 90 min (backup and upload) and 15 min (worker tick) after boot, and say so. Nothing else is excused. |
| Security updates (added 1 Oct) | Ubuntu's apt timers: daily, randomized, `Persistent=true`. Missed while stopped, then caught up at the next boot, where an upgrade restarted PostgreSQL during the boot-time backup (30 Sep 22:01 UTC) | Drop-ins pin downloads to 08:47 ET and upgrades to 08:50 ET on weekdays, with no random delay and no catch-up. That is after the scheduled start and its backup, before the 09:00 ET backup, and 40 min before the open. The backup also retries once if PostgreSQL drops its connection mid-run; any other failure still fails. |

**Transition.** On the day this deploys, today's session key already exists
from the old 00:30 UTC upload. That day's post-close copy is skipped, and
off-host coverage is about a day staler until the next session's copy lands.

## 7. A read-only stop-readiness endpoint (implemented 30 Sep 2026)

`GET /api/v1/system/stop-readiness`. This is public-safe: it returns counts and
timestamps only.

```json
{ "ok": false, "open_positions": 0, "working_orders": 0, "unresolved_incidents": 1,
  "backup_at": "2026-10-02T21:01:03+00:00", "backup_verified": true,
  "session_due": "2026-10-02", "session_copy_off_host": true,
  "reasons": ["1 unresolved incident(s)"] }
```

`ok` requires all of:

- a live database;
- no open position;
- no non-terminal broker order;
- no unresolved incident (which covers unreconciled state);
- a verified backup taken after the last session's close (+15 min);
- that session's key in the uploader's last successful record.

Anything missing or unreadable counts against a stop. The earlier idea of
cross-checking the calendar here was dropped: the committed calendar already is
Alpaca's.

## 8. Verification before enabling

Stops stay disabled until every step passes. The owner asked for the lock and
the alert to be verified first.

1. **Unit tests, in CI:** the desired-state function across DST changes (8 Mar
   and 1 Nov 2026), an early close (27 Nov 2026), a holiday, weekends and
   uncovered dates; `read_lock` for absent, active, expiring, expired,
   malformed and more than 24 h; and the tick's check order, where every "no"
   path makes no `StopInstance` call.
2. **Dry run for one trading week:** the function runs with `DRY_RUN=1`. It
   logs its decision on every tick and sends alerts, but calls neither
   `StartInstance` nor `StopInstance`. Each decision is compared with the
   schedule by hand.
3. **Lock test, live, outside hours:** `session.py start --hours 1` on a weekday
   evening. The server is started and not stopped while the lock holds. After
   `end` plus the grace, it is stopped. Then set a lock for 25 h by hand in the
   console, and confirm it is ignored and alerted.
4. **Expiry test:** a 30-minute lock left to expire. Confirm the warning arrives,
   then the stop after expiry and grace.
5. **Failed-start test:** point the function's health URL at a closed port for
   one start. Confirm the alert reaches the owner by email. Separately, confirm
   the CloudMonitor probe alerts while the server is stopped inside the alert
   window.
6. **Backup continuity:** after the first real weekend stop, confirm `weekly/`
   has the Friday copy, `daily/` has Friday's and Monday's, and the watchdog
   raised no false incident on Monday's start.

## 9. Provisioning — needs the owner's approval

These create billable resources and IAM changes, so none of them happens without
explicit approval:

- a Function Compute service and function (the timer invocations cost cents a
  month);
- a RAM role for the function, scoped as in §2;
- CloudMonitor alert contacts and a site-monitoring task;
- the §6 host changes, the §7 endpoint and `scripts/session.py`, through normal
  PRs and deploys.

## 10. The owner's answers (29 Sep 2026)

1. Alerts go by email only, with no SMS.
2. Document setting, extending and ending the lock from a phone: see §4.3.
3. Keep the 24-hour cap.
4. Keep the 08:30 ET start.

## 11. Provisioning status (30 Sep 2026)

| Item | State |
|---|---|
| RAM role `oa-scheduler-role`, trusted by Function Compute only | Created |
| Policy `oa-scheduler-policy` (`deploy/scheduler/ram-policy.json`) | Created and attached by the owner in the console (30 Sep); the operator user lacks `ram:CreatePolicy` |
| CloudMonitor contact `oa-owner` (email) and group `oa-alerts` | Created. Email activated by the owner |
| CloudMonitor group `oa-scheduler`, custom-event rule `oa-scheduler-alert` | Created |
| Metric rules `oa-scheduler-errors`, `oa-scheduler-silent` | Created |
| Function `oa-scheduler` (Python 3.12, 128 MB), `DRY_RUN=1` | Created. Its signing is verified against Alibaba's published example and against the live API |
| Timer `every-15-min` | **Enabled, live (`DRY_RUN=0`) since 30 Sep 23:13 UTC** |

Commands (`scripts/provision_scheduler.py`): `apply` (create or update),
`mode dry|live` (the only switch that lets it act), `disable|enable` (the
timer), `status` (configuration, timer, and the last decisions and alerts,
logged as CloudMonitor custom events).

## 12. Validation results (30 Sep 2026)

The observation period was shortened at the owner's request; every check the
owner made mandatory was kept. Times are UTC.

| Check | Evidence |
|---|---|
| Backup | 20:17:45 backup verified after the close. A fresh dump was copied to `anchor/`, downloaded, decrypted, and its sha256 matched (28 tables, 6,926 rows). This covers the transition day, when `daily/2026-09-30` held 29 Sep data. |
| Readiness | `ok: true`: no positions, no working orders, no unresolved incidents, a verified post-close backup, and the session copy off-host. |
| Lock | Live mode, outside the window, active lock: decision `none` ("dev session lock active"). No stop. |
| Invalid lock | Expiry set 3 days ahead: held, rewritten to now + 24 h, **exactly one** alert-log entry. |
| Expiry | One warning entry. A run inside the 15-minute grace did nothing. **First real stop at 21:55:35**; confirmed `StoppedMode: StopCharging`, EIP kept. |
| Failed start | The function started the server itself (21:56:39). With its health URL on a closed port, it raised "not healthy" **once** (22:20:30); the owner confirmed the email arrived. |
| Unsafe stop refused | At 22:38 the function refused to stop and alerted once: an unattended upgrade had restarted PostgreSQL at 22:01, so the 22:00 backup was unverified. It stopped by itself at 23:13:22, once the 23:00 backup verified. |
| One email per alert | Four alerts, four alert-log entries, four emails. Separate incidents each emailed; the function alarms' silence is 1 h. |
| urllib3 | Upgraded to 2.8.0 at 20:17:45 (CVE-2026-97687/97689). Every service restarted at 21:57 on it. Health PASS, watchdog green, 0 incidents. |

**First automatic day (1 Oct).** Started at 12:43 (the first 15-minute tick in
the window; 47 min before the open). The 13:13 start check reported "status
200, worker live". Every backup since boot verified, the watchdog is green, and
there are no incidents.

**Cost.** Compute and disk drop from $20.37 to about $10.74 a month on 2c2g
(about $11 with backups, the function and alerts). That is a projection on
billed unit prices, to be confirmed on the first mostly-stopped day's bill.

**Disable or override.**

- `python3 scripts/provision_scheduler.py mode dry` keeps deciding and logging, but acts on nothing.
- `python3 scripts/provision_scheduler.py disable` turns the timer off.
- `python3 scripts/session.py start --hours N --reason demo|dev` holds the server up for at most 24 h (or set the tags from a phone, §4.3); `end` releases it.
- In the ECS console, Start brings the server up by hand.
