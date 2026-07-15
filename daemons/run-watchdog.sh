#!/usr/bin/env bash
# Durable fleet watchdog daemon (runs in a shell window). Ctrl-C to stop.
# Backs up committed + uncommitted fleet work and scans for security issues every 150s.
# Usage: run-watchdog.sh [--once]
#
# Configuration: export AESOP_ROOT=/path/to/aesop before running (defaults to script directory's parent).
# Testing: export AESOP_WATCHDOG_CYCLE_CMD to override backup-fleet.sh invocation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AESOP_ROOT="${AESOP_ROOT:-$(dirname "$SCRIPT_DIR")}"
MODE="${1:-daemon}"
LOCK_DIR="$AESOP_ROOT/state/.watchdog-lock"
LOCK_STALE_THRESHOLD=300

# Atomic lock acquire: mkdir is atomic (POSIX guarantees)
# Returns 0 if lock acquired, 1 if held by another process, 2 if stale lock reclaimed
acquire_lock() {
  local lock_dir="$1"
  local stale_threshold="$2"

  # Ensure parent directory exists
  mkdir -p "$(dirname "$lock_dir")" 2>/dev/null || true

  # Try to create lock directory atomically (this is atomic on all POSIX systems)
  if mkdir "$lock_dir" 2>/dev/null; then
    # We created it; write timestamp and PID
    date +%s > "$lock_dir/timestamp" 2>/dev/null
    echo $$ > "$lock_dir/pid" 2>/dev/null
    return 0
  fi

  # Lock directory already exists; check if it's stale
  # AUDIT FIX 2: Verify both timestamp AND pid files exist before the stale comparison
  if [ -d "$lock_dir" ]; then
    # Try to read pid file to check if process is still running
    local lock_pid=""
    if [ -f "$lock_dir/pid" ]; then
      lock_pid=$(cat "$lock_dir/pid" 2>/dev/null)
    fi

    # Check if both required files exist
    if [ -f "$lock_dir/timestamp" ] && [ -f "$lock_dir/pid" ] && [ -n "$lock_pid" ]; then
      # Both files present and pid is readable - use timestamp for stale check
      local lock_mtime=$(cat "$lock_dir/timestamp" 2>/dev/null || echo 0)
      local now=$(date +%s)
      local lock_age=$((now - lock_mtime))

      if [ "$lock_age" -gt "$stale_threshold" ]; then
        # Lock is stale; try to reclaim it
        rm -rf "$lock_dir" 2>/dev/null || true
        if mkdir "$lock_dir" 2>/dev/null; then
          date +%s > "$lock_dir/timestamp" 2>/dev/null
          echo $$ > "$lock_dir/pid" 2>/dev/null
          echo "watchdog lock was stale (${lock_age}s) — reclaimed." >&2
          return 2
        fi
      fi
    else
      # AUDIT FIX 2: Timestamp or pid file missing, or pid is empty - lock is incomplete
      # Check if the pid (if present) is still running
      local pid_running=0
      if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
        pid_running=1
      fi

      if [ $pid_running -eq 0 ]; then
        # Process is not running - lock is stale, reclaim it
        rm -rf "$lock_dir" 2>/dev/null || true
        if mkdir "$lock_dir" 2>/dev/null; then
          date +%s > "$lock_dir/timestamp" 2>/dev/null
          echo $$ > "$lock_dir/pid" 2>/dev/null
          echo "watchdog lock was stale (incomplete/no process) — reclaimed." >&2
          return 2
        fi
      fi
      # If process is still running, hold the lock (conservative)
    fi
  fi

  # Lock is held by another process
  return 1
}

# Release lock: verify ownership before removing (P0 fix)
release_lock() {
  local lock_dir="$1"
  if [ -f "$lock_dir/pid" ]; then
    local lock_pid=$(cat "$lock_dir/pid" 2>/dev/null || echo "")
    if [ "$lock_pid" = "$$" ]; then
      rm -rf "$lock_dir" 2>/dev/null
    fi
  fi
}

# Try to acquire lock (applies to both --once and daemon modes)
acquire_lock "$LOCK_DIR" "$LOCK_STALE_THRESHOLD"
lock_result=$?

if [ $lock_result -eq 1 ]; then
  echo "watchdog already running — not starting a duplicate."
  exit 0
fi

echo "==================================================================="
echo "  FLEET WATCHDOG DAEMON  ·  backup + ensure-push + scan / 150s"
echo "  logs: $AESOP_ROOT/state/FLEET-BACKUP.log   ·   Ctrl-C to stop"
echo "==================================================================="
echo "[$(date '+%F %T')] === watchdog daemon (shell) STARTED ===" >> "$AESOP_ROOT/state/FLEET-BACKUP.log"
trap "release_lock \"$LOCK_DIR\"; echo \"[$(date '+%F %T')] === watchdog daemon (shell) STOPPED ===\" >> \"$AESOP_ROOT/state/FLEET-BACKUP.log\"; echo \"stopped.\"; exit 0" INT TERM

# Allow override of backup cycle command (for testing)
# Use array to safely handle paths with spaces (P1 fix)
if [ -n "$AESOP_WATCHDOG_CYCLE_CMD" ]; then
  # Override: run as-is through bash -c
  CYCLE_CMD_ARRAY=("bash" "-c" "$AESOP_WATCHDOG_CYCLE_CMD")
else
  # Default: array form for proper quoting
  CYCLE_CMD_ARRAY=("bash" "$AESOP_ROOT/daemons/backup-fleet.sh")
fi

if [ "$MODE" = "--once" ]; then
  full_out=$("${CYCLE_CMD_ARRAY[@]}" 2>&1)
  cmd_exit=$?
  echo "$full_out"
  if [ $cmd_exit -ne 0 ]; then
    err_msg="[$(date '+%F %T')] ERROR: cycle #1 failed with exit code $cmd_exit"
    echo "$err_msg" >> "$AESOP_ROOT/state/FLEET-BACKUP.log"
    echo "[ERROR: exit $cmd_exit]" >&2
  fi
  python "$AESOP_ROOT/tools/alert_bridge.py" --scan || true
  release_lock "$LOCK_DIR"
  exit $cmd_exit
fi

n=0
while true; do
  n=$((n+1))
  full_out=$("${CYCLE_CMD_ARRAY[@]}" 2>&1)
  cmd_exit=$?
  if [ $cmd_exit -eq 0 ]; then
    out=$(echo "$full_out" | tail -2)
    printf '%s  cycle #%d\n%s\n' "$(date '+%H:%M:%S')" "$n" "$out"
  else
    echo "[$(date '+%F %T')] ERROR: cycle #$n failed with exit code $cmd_exit" >> "$AESOP_ROOT/state/FLEET-BACKUP.log"
    out=$(echo "$full_out" | tail -2)
    printf '%s  cycle #%d [ERROR: exit %d]\n%s\n' "$(date '+%H:%M:%S')" "$n" "$cmd_exit" "$out"
  fi
  python "$AESOP_ROOT/tools/alert_bridge.py" --scan || true
  sleep 150
done
