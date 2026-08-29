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
    SG=sg-t4n6kaxrojixmg4ivuh8; HOST=43.98.206.148
    SERVICE=options-alpha-worker
    PATHS="app.py requirements.txt pyproject.toml README.md src"
    ;;
  dashboard)
    SG=sg-t4naetmr3bp6sry6lw7a; HOST=47.84.108.130
    SERVICE=options-alpha
    PATHS="app.py requirements.txt pyproject.toml README.md src demo artifacts .streamlit"
    ;;
  *) echo "usage: $0 [worker|dashboard]" >&2; exit 2 ;;
esac

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
