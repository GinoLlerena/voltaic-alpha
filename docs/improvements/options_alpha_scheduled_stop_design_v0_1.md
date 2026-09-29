# Options Alpha — Scheduled Stop Design v0.1

| Field | Value |
|---|---|
| Date | 29 September 2026, America/Lima |
| Status | Design for review. Nothing is provisioned or enabled by this document |
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

The RAM role is minimal: `ecs:DescribeInstances`, `ecs:StartInstance` and
`ecs:StopInstance` on this one instance, plus `cms:PutCustomEvent` for
alerts. It has no OSS, no RunCommand and no tag writes:
the function reads the override and never has to edit it (§4).

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
    if lock.active:
        log("lock active", reason=lock.reason, until=lock.until)
        warn_if_expiring(lock, now)                # one alert ~30 min before expiry
        return KEEP_RUNNING                        # (1) a session in progress is never stopped
    if lock.invalid:
        alert(f"session lock ignored: {lock.problem}")   # malformed, or longer than the cap
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
        return Lock.invalid("unparseable until")   # ignored, alerted, never honoured
    if until <= now:
        return Lock.expired(until)                 # expired: treated exactly as no lock
    if until - now > MAX_LOCK:
        return Lock.invalid("longer than 24 h")    # a typo'd year cannot pin the server on
    return Lock.active(until, tags.get("oa-session-reason", "unspecified"))
```

- Every lock carries its own absolute expiry. There is no "on until I say off"
  state to forget.
- No lock can reach more than 24 h ahead. The CLI refuses longer, and the
  function ignores a longer tag set by hand in the console and alerts on it. A
  forgotten session therefore costs at most one day of compute, about $0.43.
- About 30 minutes before expiry, one alert is sent: "dev session ends at 22:00Z;
  `session.py extend` to keep it".
- After expiry, the next tick past the 15-minute grace runs the normal checks
  from §4.1 step (3) onward, and stops the server if it is outside the schedule
  and ready.
- The function never deletes the expired tag, which keeps its role read-only on
  tags. `session.py end` expires a lock by setting `until` to the current
  time, so ending and forgetting follow one path, with the same grace.
  `session.py status` shows the lock as expired, and `start` overwrites it.

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
2. **CloudMonitor site monitoring** probes `http://47.236.50.157/api/v1/system/status`
   every 5 minutes, alerting only between 14:30 and 20:00 UTC on weekdays. That
   core window is inside the session in both EDT and EST. This covers the
   function itself failing: a role change, a code error, or a missed timer.
   Market holidays inside the window produce a known false alarm, about 9 a
   year, which can be muted ahead of time.

**Channel.** Both go through CloudMonitor alert contacts (the owner's email, and
optionally SMS). Neither involves the Mac, a Claude session or any new
third-party service.

## 6. What a stopped server changes elsewhere

These must ship before enabling, or the first weekend stop raises false incidents
and skips backups:

| Area | Today | Change |
|---|---|---|
| Daily off-host copy | Uploaded at 00:30 UTC, when the server would be stopped | Run the offsite upload immediately after the 17:00 ET post-close backup (timer `OnCalendar` in ET, or triggered by `ExecStartPost`). The dump key stays dated by the dump. |
| Weekly copy | Taken on Sunday (UTC), when the server is off | Taken on the week's last trading session, normally Friday post-close. `offsite.WEEKLY_WEEKDAY` becomes "last session of the ISO week". |
| Watchdog freshness | `offsite_fresh` fails at 30 h; a Friday-to-Monday stop is about 63 h | Measure staleness in hours the server has been running since the last scheduled stop. The stop records `/var/lib/options-alpha/last_scheduled_stop.json` via `ExecStop` on shutdown. Also add a 90-minute start-up grace. |
| Timers at boot | `Persistent=true` on the backup timer | Keep it: the missed hourly backup runs at boot, so a fresh dump exists before the first watchdog check. |
| Capacity collector | Gaps while stopped | None needed; the evaluator already windows by session. |

## 7. A read-only stop-readiness endpoint

`GET /api/v1/system/stop-readiness`. This is public-safe: it returns counts and
timestamps, with no identifiers or broker detail.

```json
{ "ok": false,
  "open_positions": 0, "working_orders": 0, "unreconciled": 1,
  "last_backup": {"at": "2026-09-29T21:00:11Z", "verified": true},
  "last_offsite": {"key_date": "2026-09-29", "at": "2026-09-29T21:31:02Z", "ok": true},
  "sessions_next": [{"date": "2026-09-30", "open": "09:30", "close": "16:00"}, "…"],
  "reasons": ["1 unreconciled order"] }
```

`ok` requires:

- no open positions;
- no working orders;
- nothing unreconciled;
- a verified backup newer than today's close;
- an off-host copy of that backup.

The function never infers readiness from other endpoints. `sessions_next` is the
worker's Alpaca calendar, used for the §3 cross-check.

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

## 10. Open questions for the owner

1. Is email enough for alerts, or should SMS be added? SMS costs a little per
   message.
2. Should `session.py start` also be available as a one-tap console action, with
   documented steps to edit the instance tags from the Alibaba app?
3. Is 24 h the right cap for a lock? It bounds the cost of forgetting at about
   $0.43.
4. The run window is 08:30–17:30 ET. A later start (09:00) saves about 10 h a
   month (~$0.18) but tightens start-up margin. The recommendation is to keep
   08:30.
