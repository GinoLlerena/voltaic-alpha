#!/bin/bash
# What did the live worker actually decide today?
#
# Read-only. Talks to the worker host through Cloud Assistant, which needs no
# inbound port and no SSH key, and prints the three things that matter: is the
# worker alive, what did it decide, and did anything qualify.
#
# Safe to run at any time. Outside market hours it will honestly report
# MARKET_CLOSED, which is the worker behaving correctly rather than a fault.
set -euo pipefail

REGION=ap-southeast-1
WORKER=i-t4nfdbjx66so1we0aysh
DEMO=i-t4n88bkfwsq0lhzmfjii
TICKS="${1:-40}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

remote() {
  local id="$1" script="#!/bin/bash
$2" invoke out
  invoke=$(aliyun ecs RunCommand --RegionId "$REGION" --Type RunShellScript \
    --InstanceId.1 "$id" --ContentEncoding Base64 \
    --CommandContent "$(printf '%s' "$script" | base64)" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['InvokeId'])")
  for _ in $(seq 1 60); do
    out=$(aliyun ecs DescribeInvocationResults --RegionId "$REGION" --InvokeId "$invoke" | python3 -c "
import base64, json, sys
r = json.load(sys.stdin)['Invocation']['InvocationResults']['InvocationResult'][0]
s = r.get('InvocationStatus','')
print(s)
if s not in ('Running','Pending','Invoked'):
    print(base64.b64decode(r.get('Output','')).decode('utf-8','replace'))
")
    case "$(head -1 <<<"$out")" in
      Running|Pending|Invoked) sleep 4 ;;
      *) tail -n +2 <<<"$out"; return 0 ;;
    esac
  done
  echo "  (timed out reading $id)" >&2
}

printf '\033[1mOptions Alpha — live worker check\033[0m  %s\n' "$(date -u '+%Y-%m-%d %H:%M UTC')"

say "Instances"
aliyun ecs DescribeInstances --RegionId "$REGION" | python3 -c "
import json,sys
for i in json.load(sys.stdin)['Instances']['Instance']:
    if i['InstanceId'] in ('$WORKER','$DEMO'):
        eip = i.get('EipAddress',{}).get('IpAddress') or ''
        pub = (i.get('PublicIpAddress',{}).get('IpAddress') or [''])[0]
        print(f\"  {i['InstanceName']:24} {i['Status']:10} {eip or pub}\")
"

say "Worker health and recent decisions"
remote "$WORKER" "echo '--- health ---'
cat /var/run/options-alpha/health.json 2>/dev/null || echo '  (no health file)'
echo
echo '--- last $TICKS worker events ---'
journalctl -u options-alpha-worker -n $TICKS --no-pager -o cat | grep -E '\"event\"' || echo '  (no events)'"

say "What the database records"
remote "$WORKER" 'cd /opt/options-alpha
set -a; . /etc/options-alpha.env; set +a
./.venv/bin/python - <<"EOF"
import os
from sqlalchemy import create_engine, text
e = create_engine(os.environ["DATABASE_URL"])
with e.connect() as c:
    for t in ("decisions", "model_calls", "positions", "incidents", "position_observations"):
        n = c.execute(text("select count(*) from " + t)).scalar_one()
        print("  %-24s %s" % (t, n))
    rows = c.execute(text("""
        select d.recorded_at, d.action, d.reason_codes, s.underlying_price
        from decisions d left join market_snapshots s on s.id = d.market_snapshot_id
        order by d.recorded_at desc limit 8
    """)).fetchall()
    if not rows:
        print("\n  No decision has been recorded. The worker has only run outside")
        print("  market hours, so every tick ended at MARKET_CLOSED before the")
        print("  decision path was reached.")
    else:
        print("\n  most recent decisions:")
        for r in rows:
            print(f"    {r[0]:%Y-%m-%d %H:%M}  {r[1]:20} SPY@{r[3]}  {r[2]}")
    inc = c.execute(text(
        "select kind, detail, opened_at from incidents where resolved_at is null"
    )).fetchall()
    print(f"\n  open incidents: {len(inc)}")
    for i in inc:
        print(f"    {i[0]}: {i[1][:90]}")
EOF'

say "Dashboard"
ip=$(aliyun ecs DescribeInstances --RegionId "$REGION" --InstanceIds "[\"$DEMO\"]" | python3 -c "
import json,sys
i=json.load(sys.stdin)['Instances']['Instance'][0]
print(i.get('EipAddress',{}).get('IpAddress') or (i.get('PublicIpAddress',{}).get('IpAddress') or [''])[0])")
if [ -n "$ip" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "http://$ip/" || echo 000)
  printf '  http://%s  →  %s\n' "$ip" "$code"
else
  echo "  no public address"
fi
