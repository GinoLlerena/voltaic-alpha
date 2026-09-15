#!/usr/bin/env bash
# Create the dashboard's SELECT-only Postgres role and point the dashboard at it.
#
# Runs ON THE HOST, as root. `CIIP-I-017`.
#
# Before this existed, DASHBOARD_DATABASE_URL and DATABASE_URL resolved to the
# same `options_alpha` role, which holds INSERT/UPDATE/DELETE/TRUNCATE on every
# table. The separate environment file had the shape of least authority without
# the substance: anything reaching the dashboard's credentials could truncate
# the evidence this project exists to protect.
#
# Captured here rather than run by hand for the reason `CIIP-I-016` records: a
# rebuild cannot restore what was never written down. Without this file the next
# rebuild silently goes back to a read-write dashboard.
#
# The password is generated here and never printed, never passed through argv
# (where `ps` would show it), and never written anywhere but the 0600 env file.
set -euo pipefail

DB=options_alpha
ROLE=options_alpha_ro
ENV_FILE=/etc/options-alpha-dashboard.env

[ "$(id -u)" = 0 ] || { echo "must run as root" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE does not exist" >&2; exit 1; }

PW=$(openssl rand -hex 24)

exists=$(sudo -u postgres psql -tAc \
  "select count(*) from pg_roles where rolname='$ROLE'")

# CREATE or re-key, then re-assert grants. Re-asserting is harmless and keeps
# the script correct when a table was added since the role was made.
{
  if [ "$exists" = "0" ]; then
    printf "CREATE ROLE %s LOGIN PASSWORD '%s';\n" "$ROLE" "$PW"
  else
    printf "ALTER ROLE %s LOGIN PASSWORD '%s';\n" "$ROLE" "$PW"
  fi
  printf "GRANT CONNECT ON DATABASE %s TO %s;\n" "$DB" "$ROLE"
  printf "GRANT USAGE ON SCHEMA public TO %s;\n" "$ROLE"
  printf "GRANT SELECT ON ALL TABLES IN SCHEMA public TO %s;\n" "$ROLE"
  # so a table created by a future migration is readable without re-running this
  printf "ALTER DEFAULT PRIVILEGES FOR ROLE options_alpha IN SCHEMA public GRANT SELECT ON TABLES TO %s;\n" "$ROLE"
} | sudo -u postgres psql -d "$DB" -q -v ON_ERROR_STOP=1 -f -

# Rewrite only the credential portion, so scheme, host, port and dbname survive.
OLD=$(sed -n 's/^DASHBOARD_DATABASE_URL=//p' "$ENV_FILE")
[ -n "$OLD" ] || { echo "DASHBOARD_DATABASE_URL not found in $ENV_FILE" >&2; exit 1; }
NEW=$(printf '%s' "$OLD" | sed "s|://[^@]*@|://$ROLE:$PW@|")

cp -a "$ENV_FILE" "$ENV_FILE.bak"
chmod 0600 "$ENV_FILE.bak"
umask 077
printf 'DASHBOARD_DATABASE_URL=%s\n' "$NEW" > "$ENV_FILE"
chmod 0600 "$ENV_FILE"

echo "  $ROLE created or re-keyed, grants asserted"
echo "  $ENV_FILE updated (previous kept at $ENV_FILE.bak)"
echo "  URL shape: $(printf '%s' "$NEW" | sed 's|://[^@]*@|://<role>:<pw>@|')"
echo
echo "  Restart the dashboard to pick it up:  systemctl restart options-alpha"
echo "  Verify it is genuinely read-only:     bash deploy/verify_readonly_role.sh"
