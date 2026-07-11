#!/usr/bin/env bash
# Durable fleet watchdog daemon (runs in a shell window). Ctrl-C to stop.
# Backs up committed + uncommitted fleet work and scans for security issues every 150s.
# Usage: run-watchdog.sh [--once]
#
# Configuration: export AESOP_ROOT=/path/to/aesop before running, or edit default below.

AESOP_ROOT="${AESOP_ROOT:-.}"
MODE="${1:-daemon}"

# Heartbeat guard: skip if already running (within 200s)
__hb=$(cat "$AESOP_ROOT/state/.watchdog-heartbeat" 2>/dev/null)
__now=$(date +%s)
if [ "$MODE" != "--once" ] && [ -n "$__hb" ] && [ $((__now - __hb)) -lt 200 ] 2>/dev/null; then
  echo "watchdog already running (heartbeat $((__now - __hb))s ago) — not starting a duplicate."
  exit 0
fi

echo "==================================================================="
echo "  FLEET WATCHDOG DAEMON  ·  backup + ensure-push + scan / 150s"
echo "  logs: $AESOP_ROOT/state/FLEET-BACKUP.log   ·   Ctrl-C to stop"
echo "==================================================================="
echo "[$(date '+%F %T')] === watchdog daemon (shell) STARTED ===" >> "$AESOP_ROOT/state/FLEET-BACKUP.log"
trap 'echo "[$(date "+%F %T")] === watchdog daemon (shell) STOPPED ===" >> "$AESOP_ROOT/state/FLEET-BACKUP.log"; echo "stopped."; exit 0' INT TERM

if [ "$MODE" = "--once" ]; then
  bash "$AESOP_ROOT/daemons/backup-fleet.sh" 2>&1
  exit 0
fi

n=0
while true; do
  n=$((n+1))
  out=$(bash "$AESOP_ROOT/daemons/backup-fleet.sh" 2>&1 | tail -2)
  printf '%s  cycle #%d\n%s\n' "$(date '+%H:%M:%S')" "$n" "$out"
  sleep 150
done
