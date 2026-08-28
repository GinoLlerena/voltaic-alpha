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
