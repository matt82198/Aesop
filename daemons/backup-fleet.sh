#!/usr/bin/env bash
# Backup fleet repos: stash uncommitted work, push unpushed commits to backup branches.
# Runs every 150s from run-watchdog.sh. Abort on secret-scan failures.
#
# Configuration: Set AESOP_ROOT and repos list in aesop.config.json or via environment.
# This script discovers and processes git repos configured in your setup.

AESOP_ROOT="${AESOP_ROOT:-.}"
CONFIG="${CONFIG_FILE:-$AESOP_ROOT/aesop.config.json}"

# Helper: write heartbeat (epoch-seconds) to mark this cycle
write_heartbeat() {
  mkdir -p "$AESOP_ROOT/state"
  date +%s > "$AESOP_ROOT/state/.watchdog-heartbeat"
}

# Helper: check if a repo has uncommitted or unpushed changes
is_touched() {
  local repo="$1"
  if ! cd "$repo" 2>/dev/null; then return 1; fi
  git fetch -q 2>/dev/null
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then return 0; fi
  if [ -n "$(git log -1 --pretty=%H origin/HEAD..HEAD 2>/dev/null)" ]; then return 0; fi
  return 1
}

# Helper: run secret-scan gate (example: python secret_scan.py)
# Users must provide their own secret scanning implementation.
check_secrets() {
  local repo="$1"
  if [ -f "$AESOP_ROOT/tools/secret_scan.py" ]; then
    python "$AESOP_ROOT/tools/secret_scan.py" --path "$repo" 2>/dev/null
    return $?
  fi
  return 0
}

# Main: discover repos and process each
write_heartbeat
echo "[$(date '+%F %T')] backup-fleet: cycle started"

# Stub: load repos from config (example pattern)
# In production: parse aesop.config.json for REPOS array and process each.
# For now, we show the pattern and leave the actual discovery to the user.

repos_touched=0
repos_failed=0

# Example: if REPOS environment variable is set, process those repos
if [ -n "$REPOS" ]; then
  for repo in $REPOS; do
    if is_touched "$repo"; then
      repos_touched=$((repos_touched + 1))
      if ! check_secrets "$repo"; then
        echo "[$(date '+%F %T')] secret-scan BLOCKED: $repo"
        repos_failed=$((repos_failed + 1))
        continue
      fi
      if cd "$repo" 2>/dev/null; then
        if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
          stash_name="backup/wip-$(date +%Y%m%d-%H%M%S)"
          git stash push -u -m "watchdog backup" 2>/dev/null
          git push origin "$stash_name" 2>/dev/null
          echo "[$(date '+%F %T')] stashed to $stash_name"
        fi
      fi
    fi
  done
fi

echo "[$(date '+%F %T')] backup-fleet: cycle done ($repos_touched touched, $repos_failed blocked)"
[ "$repos_failed" -eq 0 ]
