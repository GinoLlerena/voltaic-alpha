#!/bin/bash
# Disarm autonomous Paper entry. Safe to run at any time, including mid-position.
#
# Removes the paper_execute drop-in and returns the worker to `recommend`, where
# it still observes, decides, reconciles, enforces deadlines and manages exits -
# it simply cannot open new risk. Risk-reducing closes are unaffected either
# way, because blocking an exit would trap exposure at the moment it most needs
# reducing.
#
# This does NOT close an open position. If one is open, the worker keeps
# managing it under the same exit policy; check with scripts/market_check.sh.
set -euo pipefail
REGION=ap-southeast-1
WORKER=i-t4nfdbjx66so1we0aysh

script='#!/bin/bash
set -euo pipefail
sed -i "s/^ALPACA_TRADING_ENABLED=.*/ALPACA_TRADING_ENABLED=false/" /etc/options-alpha.env
rm -f /etc/systemd/system/options-alpha-worker.service.d/10-paper-execute.conf
rmdir /etc/systemd/system/options-alpha-worker.service.d 2>/dev/null || true
systemctl daemon-reload
systemctl restart options-alpha-worker
sleep 10
journalctl -u options-alpha-worker --no-pager -o cat | grep worker_started | tail -1'

invoke=$(aliyun ecs RunCommand --RegionId "$REGION" --Type RunShellScript \
  --InstanceId.1 "$WORKER" --ContentEncoding Base64 \
  --CommandContent "$(printf '%s' "$script" | base64)" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['InvokeId'])")
for _ in $(seq 1 40); do
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
    *) tail -n +2 <<<"$out"; echo; echo "Disarmed. Expect: \"mode\": \"recommend\", \"writes\": \"disabled\"."; exit 0 ;;
  esac
done
echo "timed out; check with scripts/market_check.sh" >&2; exit 1
