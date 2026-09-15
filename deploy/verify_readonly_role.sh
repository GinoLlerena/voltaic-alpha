#!/usr/bin/env bash
# Prove the dashboard's database role can read and cannot write. `CIIP-I-017`.
#
# Runs ON THE HOST, as root. Reads the credential out of the 0600 env file and
# never prints it. Exits non-zero if any write succeeds, so this is usable as a
# gate after a rebuild rather than only as something a human reads.
#
# The writes below are attempted for real against the live database. Every one
# is expected to be refused; if the grant were ever loosened, the INSERT would
# succeed and this script would both say so and fail. That is the point -- a
# check that cannot fail proves nothing.
set -uo pipefail

ENV_FILE=/etc/options-alpha-dashboard.env
DB=options_alpha

[ "$(id -u)" = 0 ] || { echo "must run as root" >&2; exit 1; }

URL=$(sed -n 's/^DASHBOARD_DATABASE_URL=//p' "$ENV_FILE")
ROLE=$(printf '%s' "$URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
PW=$(printf '%s' "$URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
HOST=$(printf '%s' "$URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
[ -n "$ROLE" ] && [ -n "$PW" ] || { echo "could not parse $ENV_FILE" >&2; exit 1; }

export PGPASSWORD="$PW"
echo "  role under test: $ROLE"
fail=0

expect () { # expect <allow|refuse> <label> <sql>
  local want="$1" label="$2" sql="$3" got
  if psql -h "$HOST" -U "$ROLE" -d "$DB" -q -v ON_ERROR_STOP=1 -tAc "$sql" >/dev/null 2>&1; then
    got=allow
  else
    got=refuse
  fi
  if [ "$got" = "$want" ]; then
    printf '    ok       %-22s (%s)\n' "$label" "$got"
  else
    printf '    FAILED   %-22s (wanted %s, got %s)\n' "$label" "$want" "$got"
    fail=1
  fi
}

echo "  reads:"
expect allow  "select decisions"   "select count(*) from decisions"
expect allow  "select worker_events" "select count(*) from worker_events"
expect allow  "select audit_events" "select count(*) from audit_events"

echo "  writes, all must be refused:"
expect refuse "insert"  "insert into runs (id, runtime_version, policy_version, bot_mode, trading_enabled, started_at) values ('ciip017','x','x','observe',false,now())"
expect refuse "update"  "update runs set bot_mode='probe'"
expect refuse "delete"  "delete from runs"
expect refuse "truncate" "truncate runs cascade"
expect refuse "create table" "create table ciip_017_probe (i int)"
expect refuse "drop table" "drop table decisions"

unset PGPASSWORD
echo
if [ "$fail" = 0 ]; then
  echo "  PASS - the dashboard role can read and cannot write"
else
  echo "  FAIL - see above" >&2
fi
exit "$fail"
