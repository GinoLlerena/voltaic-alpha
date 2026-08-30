#!/bin/bash
# Deploy the worker (or the dashboard) to its ECS host.
#
# Opens SSH for the deploy host's current egress, ships tracked files only, and
# revokes SSH again on exit - including on failure, which is why the revoke is a
# trap rather than a final line. The egress IP is not stable, so the rule is a
# /24 and it is removed immediately afterwards.
#
# Secrets are never in the payload: `git archive` ships tracked files, and .env
# has never been tracked.
set -euo pipefail

TARGET="${1:-worker}"
REGION=ap-southeast-1
KEY="${OPTIONS_ALPHA_KEY:?set OPTIONS_ALPHA_KEY to the deploy private key path}"

case "$TARGET" in
  worker)
    SG=sg-t4n6kaxrojixmg4ivuh8; INSTANCE=i-t4nfdbjx66so1we0aysh
    SERVICE=options-alpha-worker
    PATHS="app.py requirements.txt pyproject.toml README.md src"
    ;;
  dashboard)
    SG=sg-t4naetmr3bp6sry6lw7a; INSTANCE=i-t4n88bkfwsq0lhzmfjii
    SERVICE=options-alpha
    PATHS="app.py requirements.txt pyproject.toml README.md src demo artifacts .streamlit"
    ;;
  *) echo "usage: $0 [worker|dashboard]" >&2; exit 2 ;;
esac

# Resolved, never hardcoded. Both addresses were written into this script as
# literals and both went stale the moment the instances were stopped: a
# pay-as-you-go public IP is released on stop, so the script would have opened
# SSH to the security group and then hung connecting to somebody else's host.
# An Elastic IP is preferred when one is bound, because that is the address
# that survives the next stop.
HOST=$(aliyun ecs DescribeInstances --RegionId "$REGION" --InstanceIds "[\"$INSTANCE\"]" \
  | python3 -c "
import json, sys
items = json.load(sys.stdin)['Instances']['Instance']
if not items:
    sys.exit('instance $INSTANCE not found in $REGION')
i = items[0]
if i.get('Status') != 'Running':
    sys.exit('instance $INSTANCE is %s; start it first' % i.get('Status'))
eip = i.get('EipAddress', {}).get('IpAddress') or ''
pub = (i.get('PublicIpAddress', {}).get('IpAddress') or [''])[0]
addr = eip or pub
if not addr:
    sys.exit('instance $INSTANCE has no public address; bind an Elastic IP '
             '(scripts/restore_hosted_demo.sh --apply --only eip)')
print(addr)
")
echo "target $TARGET at $HOST"

CIDR="$(curl -s --max-time 15 https://api.ipify.org | cut -d. -f1-3).0/24"
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)

cleanup() {
  aliyun ecs RevokeSecurityGroup --RegionId "$REGION" --SecurityGroupId "$SG" \
    --IpProtocol tcp --PortRange 22/22 --SourceCidrIp "$CIDR" >/dev/null 2>&1 || true
  echo "  SSH revoked"
}
trap cleanup EXIT

echo "opening SSH from $CIDR"
aliyun ecs AuthorizeSecurityGroup --RegionId "$REGION" --SecurityGroupId "$SG" \
  --IpProtocol tcp --PortRange 22/22 --SourceCidrIp "$CIDR" --Priority 1 \
  --Description "temporary deploy access" >/dev/null 2>&1 || true

TAR=$(mktemp -t oa-deploy-XXXX).tar.gz
# shellcheck disable=SC2086
git archive --format=tar.gz -o "$TAR" HEAD $PATHS
echo "  payload $(du -h "$TAR" | cut -f1); credential files: $(tar -tzf "$TAR" | grep -cE '(^|/)\.env$' || true)"

until ssh "${SSH_OPTS[@]}" -o ConnectTimeout=8 "root@$HOST" 'echo ok' >/dev/null 2>&1; do sleep 5; done
scp "${SSH_OPTS[@]}" "$TAR" "root@$HOST:/tmp/deploy.tar.gz" >/dev/null
rm -f "$TAR"

ssh "${SSH_OPTS[@]}" "root@$HOST" "set -e
  tar -xzf /tmp/deploy.tar.gz -C /opt/options-alpha && rm -f /tmp/deploy.tar.gz
  cd /opt/options-alpha && ./.venv/bin/pip install -q -r requirements.txt >/dev/null 2>&1
  systemctl restart $SERVICE
  sleep 12
  echo \"  service: \$(systemctl is-active $SERVICE)\"
"
echo "deployed $TARGET"
