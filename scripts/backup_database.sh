#!/bin/bash
# Back up the worker's PostgreSQL, and prove the dump can be restored.
#
# Runs on the worker host as root, on a systemd timer. A dump whose restore has
# never been attempted is a file, not a backup: this script therefore restores
# every dump it takes into a scratch database and checks the result before it
# will call the run a success. The scratch database is dropped afterwards, and
# nothing here writes to the live one.
#
# It authenticates as `postgres` over local peer auth rather than as the
# application role, which deliberately has neither superuser nor CREATEDB. The
# backup needs to create a database; the application must never be able to.
#
# Exit status is the alarm: non-zero means there is no verified backup from this
# run, and the watchdog reads the status file this writes.
set -euo pipefail

DB="${OPTIONS_ALPHA_DB:-options_alpha}"
SCRATCH="${DB}_restore_check"
DIR="${BACKUP_DIR:-/var/backups/options-alpha}"
# Deliberately **not** under /run/options-alpha. That directory is the worker
# unit's `RuntimeDirectory`, so systemd deletes it whenever the worker stops -
# taking this file with it, and leaving the watchdog to report a missing backup
# after every restart including the host's own unattended-upgrade one. State
# written by one unit must not live inside another unit's lifecycle.
STATUS="${BACKUP_STATUS:-/var/lib/options-alpha/backup.json}"
KEEP="${BACKUP_KEEP:-48}"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="$DIR/$DB-$STAMP.dump"
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)

psql_() { sudo -u postgres psql -v ON_ERROR_STOP=1 -tAq "$@"; }

fail() {
  local detail="$1"
  mkdir -p "$(dirname "$STATUS")"
  cat > "$STATUS" <<JSON
{
  "at": "$started",
  "verified": false,
  "path": null,
  "detail": $(printf '%s' "$detail" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
}
JSON
  echo "backup FAILED: $detail" >&2
  # The scratch database must never outlive a failure; a half-restored copy of
  # production sitting on the same server is its own hazard.
  sudo -u postgres dropdb --if-exists "$SCRATCH" >/dev/null 2>&1 || true
  exit 1
}

# A PostgreSQL restart mid-run (an unattended security upgrade restarts it, as
# it did at 22:01 UTC on 30 Sep, four minutes after a scheduled start) is not a
# bad backup: it is a dropped connection. Those, and only those, are retried
# once, after the server answers again. Anything else still fails at once.
transient() {
  grep -qiE "server closed the connection|terminating connection|could not connect|connection to server .* failed|the database system is (shutting down|starting up)" "$1"
}
wait_for_postgres() {
  for _ in $(seq 45); do sudo -u postgres pg_isready -q && return 0; sleep 2; done
  return 1
}

# The dump is written by `postgres`, not by root, so the directory has to belong
# to that user. It stays 700: the file is a complete copy of the decision record
# and the postgres role already holds all of it, but nobody else should.
mkdir -p "$(dirname "$STATUS")"
install -d -m 700 -o postgres -g postgres "$DIR"

# --- dump --------------------------------------------------------------------
dump_once() { sudo -u postgres pg_dump -Fc -d "$DB" -f "$DUMP" 2>/tmp/backup.err; }
if ! dump_once; then
  transient /tmp/backup.err && wait_for_postgres && echo "pg_dump: connection lost; retrying once" >&2 \
    && dump_once || fail "pg_dump failed: $(tail -3 /tmp/backup.err)"
fi
chmod 600 "$DUMP"
bytes=$(stat -c %s "$DUMP")
[ "$bytes" -gt 0 ] || fail "pg_dump produced an empty file"

# --- restore it, which is the only thing that proves it is a backup ----------
restore_once() {
  sudo -u postgres dropdb --if-exists "$SCRATCH" >/dev/null 2>&1 || true
  sudo -u postgres createdb "$SCRATCH" 2>/tmp/restore.err || return 1
  sudo -u postgres pg_restore --no-owner --no-privileges -d "$SCRATCH" "$DUMP" 2>/tmp/restore.err
}
if ! restore_once; then
  transient /tmp/restore.err && wait_for_postgres && echo "pg_restore: connection lost; retrying once" >&2 \
    && restore_once || fail "pg_restore failed: $(tail -3 /tmp/restore.err)"
fi

tables_src=$(psql_ -d "$DB" -c \
  "select count(*) from information_schema.tables where table_schema='public'")
tables_new=$(psql_ -d "$SCRATCH" -c \
  "select count(*) from information_schema.tables where table_schema='public'")
[ "$tables_src" = "$tables_new" ] \
  || fail "restored $tables_new tables, source has $tables_src"

rev_src=$(psql_ -d "$DB" -c "select version_num from alembic_version")
rev_new=$(psql_ -d "$SCRATCH" -c "select version_num from alembic_version")
[ "$rev_src" = "$rev_new" ] \
  || fail "restored schema is at $rev_new, source is at $rev_src"

# Row counts. The source is live - the worker keeps ticking while this runs - so
# a restored count may legitimately lag, but it must never exceed the source and
# a table with rows must not come back empty. That catches a truncated restore
# without inventing a consistency the dump never claimed.
mismatch=""
rows=0
while IFS='|' read -r table src; do
  [ -n "$table" ] || continue
  new=$(psql_ -d "$SCRATCH" -c "select count(*) from \"$table\"")
  rows=$((rows + new))
  if [ "$new" -gt "$src" ]; then
    mismatch="$mismatch $table(restored $new > source $src)"
  elif [ "$src" -gt 0 ] && [ "$new" -eq 0 ]; then
    mismatch="$mismatch $table(source $src, restored empty)"
  fi
done < <(psql_ -d "$DB" -c "
  select table_name || '|' || (
    xpath('/row/c/text()', query_to_xml(
      format('select count(*) as c from %I.%I', table_schema, table_name),
      false, true, ''))
  )[1]::text::int
  from information_schema.tables
  where table_schema = 'public' order by table_name")

[ -z "$mismatch" ] || fail "row counts disagree:$mismatch"

sudo -u postgres dropdb "$SCRATCH" || fail "could not drop the scratch database"

# --- retention ---------------------------------------------------------------
ls -1t "$DIR"/"$DB"-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old"
done
kept=$(ls -1 "$DIR"/"$DB"-*.dump 2>/dev/null | wc -l)

cat > "$STATUS" <<JSON
{
  "at": "$started",
  "verified": true,
  "path": "$DUMP",
  "bytes": $bytes,
  "tables": $tables_new,
  "rows_restored": $rows,
  "alembic_revision": "$rev_new",
  "dumps_retained": $kept,
  "detail": "restored into $SCRATCH and dropped"
}
JSON

echo "verified backup $DUMP ($bytes bytes, $tables_new tables, $rows rows, rev $rev_new; $kept retained)"
