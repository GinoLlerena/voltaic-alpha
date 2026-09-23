#!/usr/bin/env bash
# Install the systemd units that live in this repository.
#
# Runs ON THE HOST, from a checkout or from /opt/options-alpha. It is
# idempotent: installing over an identical unit is a no-op, and it never
# enables a unit whose EnvironmentFile is absent, because systemd would then
# fail the unit at start with an error that reads like a code fault.
#
# `CIIP-I-016`. These two units previously existed only on the host, so a
# rebuild could not restore them. The other five (port80, backup, watchdog and
# their timers) are still written inline by scripts/restore_hosted_demo.sh --
# see deploy/systemd/README.md for why they are not duplicated here.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITS="$HERE/systemd"
DEST=/etc/systemd/system

# unit -> the EnvironmentFile it cannot start without
declare -A REQUIRES=(
  [options-alpha-worker.service]=/etc/options-alpha.env
  [options-alpha.service]=/etc/options-alpha-dashboard.env
  [options-alpha-api.service]=/etc/options-alpha-dashboard.env
  [options-alpha-watchdog.service]=/etc/options-alpha.env
  [options-alpha-backup.service]=/etc/options-alpha.env
  # Its own env file, deliberately not the broker's (OSS plan §4.1).
  [options-alpha-backup-offsite.service]=/etc/options-alpha-backup.env
)

#: Units with no environment of their own.
UNCONDITIONAL=(options-alpha-port80.service options-alpha-capacity.service)

#: Timers are enabled, not started: `--now` on a timer for a job that has just
#: run would run it again for no reason.
TIMERS=(options-alpha-backup.timer options-alpha-watchdog.timer options-alpha-backup-offsite.timer)

ALL=(
  options-alpha-worker.service
  options-alpha.service
  options-alpha-api.service
  options-alpha-watchdog.service
  options-alpha-backup.service
  options-alpha-backup-offsite.service
  "${UNCONDITIONAL[@]}"
  "${TIMERS[@]}"
)

changed=0
for unit in "${ALL[@]}"; do
  src="$UNITS/$unit"
  [ -f "$src" ] || { echo "  missing in repo: $src" >&2; exit 1; }
  if [ -f "$DEST/$unit" ] && cmp -s "$src" "$DEST/$unit"; then
    echo "  $unit: already current"
  else
    install -m 0644 "$src" "$DEST/$unit"
    echo "  $unit: installed"
    changed=1
  fi
done

[ "$changed" = 1 ] && systemctl daemon-reload

for unit in "${ALL[@]}"; do
  env_file="${REQUIRES[$unit]:-}"
  if [ -n "$env_file" ] && [ ! -f "$env_file" ]; then
    echo "  $unit: NOT enabled -- $env_file does not exist yet"
    continue
  fi
  # A timer is enabled *and started*: enabling alone leaves a rebuilt host
  # with no backups and no watchdog until something reboots it. Services
  # are only enabled -- starting the worker is a deliberate act.
  case " ${TIMERS[*]} " in
    *" $unit "*) systemctl enable --now "$unit" >/dev/null 2>&1 || true ;;
    *) systemctl enable "$unit" >/dev/null 2>&1 || true ;;
  esac
  echo "  $unit: enabled ($(systemctl is-active "$unit"))"
done

echo
echo "  Units installed from the repository. Starting or restarting them is a"
echo "  separate, deliberate step -- this script does not restart a running"
echo "  worker, because that would interrupt a live session without being asked."
