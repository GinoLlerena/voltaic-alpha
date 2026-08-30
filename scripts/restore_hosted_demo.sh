#!/bin/bash
# Bring the stopped deployment back and make its address survive the next stop.
#
# The instances were stopped in StopCharging mode, which releases a
# pay-as-you-go public address. The recorded IPs are therefore dead, and the
# dashboard address is the submission URL - so it has to become an Elastic IP,
# which is held by the account rather than by a running instance.
#
# Every phase is idempotent. Re-running after a partial failure resumes rather
# than duplicating: an existing unbound EIP is reused instead of allocating a
# second one, an already-running instance is left alone, and an already-stamped
# database is not re-stamped.
#
# Nothing here runs without --apply. A dry run prints the plan and touches
# nothing, because every phase below spends money or changes a production host.
set -euo pipefail

REGION=ap-southeast-1
DEMO=i-t4n88bkfwsq0lhzmfjii          # options-alpha-demo, public dashboard
WORKER=i-t4nfdbjx66so1we0aysh        # options-alpha-worker, no inbound port
DEMO_SG=sg-t4naetmr3bp6sry6lw7a
STREAMLIT_PORT=8501
PUBLIC_PORT=80

APPLY=0
PHASES="preflight eip start code migrate port80 verify"
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --only)  shift; PHASES="$1" ;;
    -h|--help)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      echo; echo "usage: $0 [--apply] [--only \"phase phase\"]"
      echo "phases: preflight eip start code migrate port80 verify"
      exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '  \033[31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if [ "$APPLY" = 1 ]; then "$@"; else note "would run: $*"; fi
}

wants() { case " $PHASES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

instance_field() {  # instance_field <instance-id> <json-key>
  aliyun ecs DescribeInstances --RegionId "$REGION" --InstanceIds "[\"$1\"]" \
    | python3 -c "
import json,sys
items = json.load(sys.stdin)['Instances']['Instance']
print(items[0].get('$2', '') if items else '')
"
}

public_ip() {
  aliyun ecs DescribeInstances --RegionId "$REGION" --InstanceIds "[\"$1\"]" \
    | python3 -c "
import json,sys
i = json.load(sys.stdin)['Instances']['Instance'][0]
eip = i.get('EipAddress', {}).get('IpAddress') or ''
pub = (i.get('PublicIpAddress', {}).get('IpAddress') or [''])[0]
print(eip or pub)
"
}

wait_for_status() {  # wait_for_status <instance-id> <status> <seconds>
  local id="$1" want="$2" budget="${3:-180}" waited=0
  [ "$APPLY" = 1 ] || { note "would wait for $id to be $want"; return 0; }
  while [ "$waited" -lt "$budget" ]; do
    [ "$(instance_field "$id" Status)" = "$want" ] && { note "$id is $want"; return 0; }
    sleep 5; waited=$((waited + 5))
  done
  die "$id did not reach $want within ${budget}s"
}

remote() {  # remote <instance-id> <script text> - Cloud Assistant, no inbound port needed
  local id="$1" script="$2" invoke
  # Cloud Assistant executes RunShellScript with /bin/sh, which on Ubuntu is
  # dash: `set -o pipefail` is a bash builtin and dash exits 2 on it. An
  # explicit shebang is the difference between the script running and the
  # migration failing on its first line.
  script="#!/bin/bash
$script"
  if [ "$APPLY" != 1 ]; then note "would run on $id:"; sed 's/^/      /' <<<"$script"; return 0; fi
  invoke=$(aliyun ecs RunCommand --RegionId "$REGION" --Type RunShellScript \
    --InstanceId.1 "$id" --ContentEncoding Base64 \
    --CommandContent "$(printf '%s' "$script" | base64)" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['InvokeId'])")
  local waited=0
  while [ "$waited" -lt 300 ]; do
    local out
    out=$(aliyun ecs DescribeInvocationResults --RegionId "$REGION" --InvokeId "$invoke" \
      | python3 -c "
import base64, json, sys
r = json.load(sys.stdin)['Invocation']['InvocationResults']['InvocationResult'][0]
status = r.get('InvocationStatus', '')
print(status)
if status not in ('Running', 'Pending', 'Invoked'):
    print(base64.b64decode(r.get('Output', '')).decode('utf-8', 'replace'))
    print('EXIT_CODE=%s' % r.get('ExitCode'))
")
    case "$(head -1 <<<"$out")" in
      Running|Pending|Invoked) sleep 5; waited=$((waited + 5)) ;;
      *) tail -n +2 <<<"$out" | sed 's/^/      /'
         grep -q 'EXIT_CODE=0' <<<"$out" || die "remote command failed on $id"
         return 0 ;;
    esac
  done
  die "remote command on $id did not finish within 300s"
}

ship() {  # ship <instance-id> <tar-source...> - push files with no inbound port
  # Cloud Assistant caps CommandContent at roughly 18 KB after encoding, and a
  # base64 tarball of the migrations is most of that on its own, so it goes up
  # in chunks and is reassembled on the host. SSH would be simpler and needs a
  # private key this script deliberately does not want.
  local id="$1"; shift
  local payload chunk i=0
  payload=$(tar --exclude='__pycache__' -czf - "$@" | base64 | tr -d '\n')
  [ "$APPLY" = 1 ] || { note "would ship $* to $id (${#payload} encoded chars)"; return 0; }
  note "shipping $* to $id (${#payload} encoded chars)"
  while [ -n "$payload" ]; do
    chunk=${payload:0:5000}
    payload=${payload:5000}
    if [ "$i" = 0 ]; then
      remote "$id" "printf '%s' '$chunk' > /tmp/oa_ship.b64"
    else
      remote "$id" "printf '%s' '$chunk' >> /tmp/oa_ship.b64"
    fi
    i=$((i + 1))
  done
  remote "$id" "set -eu
base64 -d /tmp/oa_ship.b64 | tar -xzf - -C /opt/options-alpha
rm -f /tmp/oa_ship.b64
echo 'extracted:'; ls /opt/options-alpha"
}

# --- preflight ---------------------------------------------------------------
if wants preflight; then
  say "1. Preflight"
  command -v aliyun >/dev/null || die "the aliyun CLI is not on PATH"
  command -v python3 >/dev/null || die "python3 is required to parse API responses"

  balance=$(aliyun bssopenapi QueryAccountBalance \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['Data']['AvailableAmount'])")
  note "available balance: $balance"
  # Starting an instance with no balance and an unpaid cycle is how a
  # submission URL goes dark on the morning it is judged. This is a warning
  # rather than a hard stop: only the account owner can see the real payment
  # state, and refusing to run would be presumptuous.
  case "$balance" in
    0|0.00|0.0) warn "no available balance. Confirm a payment method before relying on this host." ;;
  esac

  for id in "$DEMO" "$WORKER"; do
    note "$(instance_field "$id" InstanceName): $(instance_field "$id" Status)"
  done
fi

# --- elastic ip --------------------------------------------------------------
if wants eip; then
  say "2. Elastic IP for the dashboard"
  bound=$(public_ip "$DEMO")
  existing=$(aliyun vpc DescribeEipAddresses --RegionId "$REGION" \
    | python3 -c "
import json,sys
for e in json.load(sys.stdin)['EipAddresses']['EipAddress']:
    if e.get('Status') == 'Available':
        print(e['AllocationId'], e['IpAddress']); break
")
  current_eip=$(aliyun vpc DescribeEipAddresses --RegionId "$REGION" \
    | python3 -c "
import json,sys
for e in json.load(sys.stdin)['EipAddresses']['EipAddress']:
    if e.get('InstanceId') == '$DEMO':
        print(e['IpAddress']); break
")
  if [ -n "$current_eip" ]; then
    note "already bound: $current_eip"
  elif [ -n "$existing" ]; then
    note "reusing the unbound EIP already allocated: $existing"
    run aliyun vpc AssociateEipAddress --RegionId "$REGION" \
      --AllocationId "$(cut -d' ' -f1 <<<"$existing")" --InstanceId "$DEMO"
  else
    note "allocating a new pay-by-traffic EIP"
    if [ "$APPLY" = 1 ]; then
      alloc=$(aliyun vpc AllocateEipAddress --RegionId "$REGION" --Bandwidth 5 \
        --InternetChargeType PayByTraffic --InstanceChargeType PostPaid \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['AllocationId'], d['EipAddress'])")
      note "allocated: $alloc"
      aliyun vpc AssociateEipAddress --RegionId "$REGION" \
        --AllocationId "$(cut -d' ' -f1 <<<"$alloc")" --InstanceId "$DEMO"
    else
      note "would allocate and associate an EIP"
    fi
  fi
  [ -n "$bound" ] && note "previous address was $bound"
fi

# --- start -------------------------------------------------------------------
if wants start; then
  say "3. Start the instances"
  for id in "$WORKER" "$DEMO"; do
    status=$(instance_field "$id" Status)
    if [ "$status" = "Running" ]; then
      note "$(instance_field "$id" InstanceName) already running"
    else
      note "starting $(instance_field "$id" InstanceName) ($status)"
      run aliyun ecs StartInstance --InstanceId "$id"
      wait_for_status "$id" Running 240
    fi
  done
  # Cloud Assistant needs a moment after the instance reports Running.
  [ "$APPLY" = 1 ] && sleep 20 || true
fi

# --- code --------------------------------------------------------------------
if wants code; then
  say "3b. Ship the current source to the worker"
  # Cloud Assistant rather than scp, so this needs no private key. The worker
  # runs a plain venv, and nothing in this payload adds a dependency, so no
  # reinstall is required - but the service has to restart to pick it up.
  ship "$WORKER" src app.py
  remote "$WORKER" 'set -euo pipefail
cd /opt/options-alpha
# The package was installed non-editable, so site-packages held a *copy* and
# /opt/options-alpha/src was never imported: shipping source appeared to work
# and changed nothing. Reinstalling editable makes src authoritative, so every
# later ship takes effect on restart with no reinstall at all. --no-deps
# because nothing here adds a dependency and a resolver run needs the network.
./.venv/bin/pip install -q --no-deps -e . 2>&1 | tail -3
./.venv/bin/python -c "import options_alpha_lab as m; print(\"imports from:\", m.__file__)"
systemctl restart options-alpha-worker
sleep 10
systemctl is-active options-alpha-worker
journalctl -u options-alpha-worker -n 3 --no-pager -o cat'
fi

# --- migrate -----------------------------------------------------------------
if wants migrate; then
  say "4. Migrate the worker database"
  # The migrations were never in the worker payload, so they have to get there
  # before anything can be upgraded. Shipping them is idempotent: same files,
  # extracted over the same paths.
  ship "$WORKER" alembic.ini migrations

  # Stop the writer first. The migration only adds a table and a column, so it
  # does not rewrite what a running worker holds, but a single writer is the
  # invariant the lease exists to protect and a schema change is not the moment
  # to make an exception to it.
  remote "$WORKER" 'set -euo pipefail
ROOT=/opt/options-alpha
ALEMBIC="$ROOT/.venv/bin/alembic"
PY="$ROOT/.venv/bin/python"
# There is no uv on this host: the service runs a plain venv. Asserting the
# binary exists is the difference between a clear failure and the previous
# behaviour, where a missing command was indistinguishable from an unversioned
# database - and would have stamped a database that was already at 0002 back
# down to the baseline.
test -x "$ALEMBIC" || { echo "alembic not found at $ALEMBIC" >&2; exit 1; }

systemctl stop options-alpha-worker || true
cd "$ROOT"
set -a; . /etc/options-alpha.env; set +a

state=$("$PY" - <<'"'"'EOF'"'"'
import os
from sqlalchemy import create_engine, inspect
engine = create_engine(os.environ["DATABASE_URL"])
print("HAS_VERSION" if "alembic_version" in inspect(engine).get_table_names() else "NO_VERSION")
EOF
)
echo "version table: $state"
# -x url= is the first thing migrations/env.py consults, and it is what makes
# this work at all: /etc/options-alpha.env carries DATABASE_URL but not
# BOT_MODE, because the unit passes the mode as a command-line flag. Falling
# through to load_settings() therefore raises ConfigurationError. Addressing
# the database directly is also narrower - a migration should not need the
# full application configuration to be valid.
AL() { "$ALEMBIC" -x "url=$DATABASE_URL" "$@"; }
if [ "$state" = "NO_VERSION" ]; then
  # Built by create_schema before Alembic existed, so it carries no version
  # row. Stamping records that the h0.1 shape is already present; upgrading
  # without it would try to create tables that already exist.
  echo "stamping the baseline"
  AL stamp 0001_h0_baseline
fi
AL upgrade head
AL current
systemctl start options-alpha-worker
sleep 8
systemctl is-active options-alpha-worker'
fi

# --- port 80 -----------------------------------------------------------------
if wants port80; then
  say "5. Serve the dashboard on port 80"
  # A redirect rather than moving Streamlit itself: it needs no knowledge of the
  # unit file, no capability grant to bind a privileged port, and it is undone
  # by deleting one rule. Port 8501 stays open so a rollback needs no change.
  note "opening $PUBLIC_PORT/tcp on $DEMO_SG"
  run aliyun ecs AuthorizeSecurityGroup --RegionId "$REGION" --SecurityGroupId "$DEMO_SG" \
    --IpProtocol tcp --PortRange "$PUBLIC_PORT/$PUBLIC_PORT" --SourceCidrIp 0.0.0.0/0 \
    --Description "judge dashboard, plain HTTP"

  remote "$DEMO" "set -euo pipefail
# Survive a reboot. A rule that vanishes on restart is worse than no rule: the
# URL works until the one time it matters. The unit is the single owner of the
# rule - adding one by hand as well leaves a duplicate and a unit that reports
# inactive while the redirect works, which is the kind of disagreement that
# gets discovered during a demo.
cat >/etc/systemd/system/options-alpha-port80.service <<'UNIT'
[Unit]
Description=Redirect 80 to the Streamlit dashboard on 8501
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/iptables -t nat -A PREROUTING -p tcp --dport $PUBLIC_PORT -j REDIRECT --to-port $STREAMLIT_PORT
ExecStop=/usr/sbin/iptables -t nat -D PREROUTING -p tcp --dport $PUBLIC_PORT -j REDIRECT --to-port $STREAMLIT_PORT

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable options-alpha-port80
# Idempotent: drop every copy of the rule first, so re-running does not stack
# duplicates, then let the unit add exactly one.
while iptables -t nat -C PREROUTING -p tcp --dport $PUBLIC_PORT -j REDIRECT --to-port $STREAMLIT_PORT 2>/dev/null; do
  iptables -t nat -D PREROUTING -p tcp --dport $PUBLIC_PORT -j REDIRECT --to-port $STREAMLIT_PORT
done
systemctl restart options-alpha-port80
echo \"unit: \$(systemctl is-enabled options-alpha-port80) / \$(systemctl is-active options-alpha-port80)\"
echo \"rules: \$(iptables -t nat -S PREROUTING | grep -c -- '--dport $PUBLIC_PORT -j REDIRECT')\""
fi

# --- verify ------------------------------------------------------------------
if wants verify; then
  say "6. Verify"
  ip=$(public_ip "$DEMO")
  if [ -z "$ip" ]; then
    warn "no public address yet; skipping the reachability check"
  else
    note "address: $ip"
    for url in "http://$ip/" "http://$ip/_stcore/health" "http://$ip:$STREAMLIT_PORT/"; do
      if [ "$APPLY" = 1 ]; then
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$url" || echo 000)
        [ "$code" = 200 ] && note "200  $url" || warn "$code  $url"
      else
        note "would check $url"
      fi
    done
    say "Submission URL"
    note "http://$ip"
    note "Record the MP4 against this address. Nothing about it may change afterwards."
  fi
fi

[ "$APPLY" = 1 ] || printf '\n\033[33mDry run. Nothing was changed. Re-run with --apply.\033[0m\n'
