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

The dashboard only. It serves the committed evidence database and has no code
path to a broker or a model provider.

The service environment contains **no Alpaca or OpenAI credential**, verified
after start by reading the process environment. The upload was produced with
`git archive`, so only tracked files were shipped and `.env` could not be
included even by accident.

The decision worker, the execution gateway, and the freeze tooling are **not**
deployed. Nothing on this host can place an order.

### 1.1 Autonomous-worker gate

The dashboard deployment is not an autonomous-agent deployment. Do not add
Alpaca/OpenAI credentials or start `options_alpha_lab.agent` on this service as
a convenience change. That would expand the host from public evidence viewer to
broker authority and invalidate its current security claim.

If autonomous Paper operation remains in scope, deploy a separate worker
boundary and require all of the following before enabling entry:

1. protected Paper-only provider secrets with no live fallback;
2. a durable hosted database and migrations for intents, orders, fills,
   positions, execution state, and incidents;
3. one database-backed worker lease and an authoritative market calendar;
4. startup reconciliation before the decision loop plus periodic reconciliation
   while any order or exposure exists;
5. durable pending/partial/open/closing/flat states based on actual fills;
6. health checks and alerts for broker/local mismatch, stale reconciliation,
   database failure, worker death, and an unmanaged position;
7. backup, restore, forced-restart, credential-rotation, and rollback evidence.

The public dashboard may read redacted evidence exported by that worker, but it
must not share broker-write credentials or expose control actions. Until this
gate passes, the hosted system demonstrates the judge experience only, not
unattended trading.

## 2. Platform caveat

The Rule Book says "Demo Application Platform: Use Streamlit, Replit, or
Vercel". Alibaba is not on that list. This deployment is a working fallback and
proof the application runs unattended; **Streamlit Community Cloud remains the
compliant target** and is the first option on the allowlist.

Vercel is not a viable alternative for this app: it runs short-lived serverless
functions, and Streamlit needs a persistent WebSocket to a long-running process.

## 3. Known limitations

- **HTTP only.** There is no domain and no TLS certificate, so browsers will
  mark the URL "not secure". The page carries no login and no user input, so
  nothing sensitive crosses the wire, but a judge will see the warning.
- **Bare IP address.** No DNS name is attached.
- **Single instance.** No load balancer and no redundancy.

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

### 7.5 Cost and teardown

Two `ecs.e-c1m2.large` instances now bill. Release both after the event:

```bash
aliyun ecs DeleteInstance --RegionId ap-southeast-1 --InstanceId i-t4nfdbjx66so1we0aysh --Force true
aliyun ecs DeleteInstance --RegionId ap-southeast-1 --InstanceId i-t4n88bkfwsq0lhzmfjii --Force true
```

There is no database backup yet. `EXIT-AC-16` asks for backup and rollback
evidence, and that part is **not** satisfied: a `pg_dump` timer is the remaining
work.
