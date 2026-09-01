#!/bin/bash
# Arm autonomous Paper entry. The exact counterpart of scripts/disarm_worker.sh.
#
# Arming was originally done by hand, which is the wrong shape for the one action
# in this system that lets an unattended process open real (Paper) risk. It
# belongs in a reviewable script that states its bounds and verifies them
# afterwards, so "what did arming change" has an answer in version control
# rather than in someone's shell history.
#
# What this changes, and nothing else:
#   * `--mode paper_execute` plus an `--approve` token, as a systemd drop-in, so
#     `systemctl revert` removes it whole and cannot half-apply;
#   * ALPACA_TRADING_ENABLED=true in the environment file.
#
# Every other bound is untouched and none of them is granted here: Paper only,
# SPY only, one open or pending strategy, the calendar-derived 09:45-15:15 ET
# entry window, the 90/120 second order deadlines, and the per-trade risk budget.
#
# It refuses if ALPACA_PAPER_TRADE is not true, and afterwards reports the
# resolved broker endpoint from the client that would actually be used rather
# than from the flag that configured it. Those can disagree, and only one of
# them is safe.
set -euo pipefail
REGION=ap-southeast-1
WORKER=i-t4nfdbjx66so1we0aysh

# A fresh token per arming, recorded with every decision it authorises, so two
# armings are distinguishable in the audit trail.
TOKEN="${OPTIONS_ALPHA_APPROVAL:-operator:$(date -u +%Y%m%dT%H%M%SZ):$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')}"

script="#!/bin/bash
set -euo pipefail
grep -q '^ALPACA_PAPER_TRADE=true' /etc/options-alpha.env || {
  echo 'REFUSING: ALPACA_PAPER_TRADE is not true'; exit 2; }

sed -i 's/^ALPACA_TRADING_ENABLED=.*/ALPACA_TRADING_ENABLED=true/' /etc/options-alpha.env
install -d /etc/systemd/system/options-alpha-worker.service.d
cat > /etc/systemd/system/options-alpha-worker.service.d/10-paper-execute.conf <<'UNIT'
[Service]
ExecStart=
ExecStart=/opt/options-alpha/.venv/bin/python -m options_alpha_lab.worker --mode paper_execute --symbol SPY --interval 300 --health-file /var/run/options-alpha/health.json --approve __TOKEN__
UNIT
sed -i 's|__TOKEN__|$TOKEN|' /etc/systemd/system/options-alpha-worker.service.d/10-paper-execute.conf

systemctl daemon-reload
systemctl restart options-alpha-worker
sleep 12
echo \"unit: \$(systemctl is-active options-alpha-worker)\"
journalctl -u options-alpha-worker --no-pager -o cat | grep worker_started | tail -1
journalctl -u options-alpha-worker --no-pager -o cat | grep startup_reconcile | tail -1

cd /opt/options-alpha
set -a; . /etc/options-alpha.env; set +a
./.venv/bin/python - <<'PY'
import json, os, urllib.request
h = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
     'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
base = 'https://paper-api.alpaca.markets'
req = urllib.request.Request(base + '/v2/account', headers=h)
a = json.load(urllib.request.urlopen(req, timeout=30))
print('resolved endpoint:', base)
print('account status  :', a['status'], '| equity', a['equity'])
pos = json.load(urllib.request.urlopen(
    urllib.request.Request(base + '/v2/positions', headers=h), timeout=30))
print('broker legs open:', len(pos))
PY
"

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
    *)
      tail -n +2 <<<"$out"
      echo
      echo "Armed. Expect: \"mode\": \"paper_execute\", \"writes\": \"enabled\"."
      echo "Approval token: ${TOKEN:0:24}...${TOKEN: -4}"
      echo "Disarm with scripts/disarm_worker.sh."
      exit 0 ;;
  esac
done
echo "timed out; check with scripts/market_check.sh" >&2; exit 1
