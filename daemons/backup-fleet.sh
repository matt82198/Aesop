#!/usr/bin/env bash
set -uo pipefail
# Backup fleet repos: stash uncommitted work, push unpushed commits to backup branches.
# Runs every 150s from run-watchdog.sh. Abort on secret-scan failures.
# Improvements: dot-directory discovery, path dedup, tracked-files-only secret scanning.
# P2 FIX: JSON escaping for repo names and NUL-delimited internal protocol.

AESOP_ROOT="${AESOP_ROOT:-.}"
HEARTBEAT="$AESOP_ROOT/state/.watchdog-heartbeat"
LOG="$AESOP_ROOT/state/FLEET-BACKUP.log"
REPOS_STATUS="$AESOP_ROOT/state/.watchdog-repos.json"

date +%s > "$HEARTBEAT" 2>/dev/null
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# P2 FIX: JSON escape function for safe string interpolation in JSON
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

is_touched() {
  local repo="$1"
  [ ! -d "$repo/.git" ] && return 1
  (
    cd "$repo" || return 1
    [ -n "$(git status --porcelain 2>/dev/null)" ] && return 0
    [ -n "$(git log @{u}.. --oneline 2>/dev/null)" ] && return 0
    return 1
  )
}

get_tracked_modifications() {
  local repo="$1"
  (
    cd "$repo" || return 1
    git diff --name-only HEAD 2>/dev/null
    git ls-files -m 2>/dev/null
  ) | sort -u
}

get_untracked_files() {
  local repo="$1"
  (
    cd "$repo" || return 1
    git ls-files --others --exclude-standard 2>/dev/null
  ) | sort -u
}

scan_tracked_files() {
  local repo="$1"
  local tracked_files
  local untracked_files
  local -a file_paths=()
  local repo_win

  # Convert repo path to Windows format for Python compatibility (Git Bash on Windows)
  repo_win=$(cd "$repo" 2>/dev/null && pwd -W 2>/dev/null || echo "$repo")

  tracked_files=$(get_tracked_modifications "$repo")
  untracked_files=$(get_untracked_files "$repo")

  # Collect tracked modifications
  if [ -n "$tracked_files" ]; then
    while IFS= read -r file; do
      if [ -n "$file" ] && [ -f "$repo/$file" ]; then
        file_paths+=("$repo_win/$file")
      fi
    done <<EOF
$tracked_files
EOF
  fi

  # Collect untracked files (ITEM 1 fix)
  if [ -n "$untracked_files" ]; then
    while IFS= read -r file; do
      if [ -n "$file" ] && [ -f "$repo/$file" ]; then
        file_paths+=("$repo_win/$file")
      fi
    done <<EOF
$untracked_files
EOF
  fi

  if [ ${#file_paths[@]} -eq 0 ]; then
    return 0
  fi

  if [ -f "$AESOP_ROOT/tools/secret_scan.py" ]; then
    # ITEM 2 fix: use "${file_paths[@]}" to properly quote array elements
    python "$AESOP_ROOT/tools/secret_scan.py" "${file_paths[@]}" >/dev/null 2>&1
    return $?
  fi

  return 0
}

get_default_branch() {
  local repo="$1"
  (cd "$repo" && git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's/refs\/remotes\/origin\///' || echo "master")
}

process_repo() {
  local repo="$1"
  local name=$(basename "$repo")
  local default=$(get_default_branch "$repo")

  (
    cd "$repo" || exit 0
    git fetch -q origin 2>/dev/null
    local uncommitted=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

    if [ "$uncommitted" -gt 0 ]; then
      TMPIDX=$(mktemp)
      GIT_INDEX_FILE="$TMPIDX" git read-tree HEAD 2>/dev/null
      GIT_INDEX_FILE="$TMPIDX" git add -A 2>/dev/null
      TREE=$(GIT_INDEX_FILE="$TMPIDX" git write-tree 2>/dev/null)
      rm -f "$TMPIDX"
      LOCAL=$(git rev-parse HEAD 2>/dev/null)
      HEADTREE=$(git rev-parse 'HEAD^{tree}' 2>/dev/null)
      if [ -n "$TREE" ] && [ "$TREE" != "$HEADTREE" ]; then
        COMMIT=$(git commit-tree "$TREE" -p "$LOCAL" -m "wip $(ts) — $uncommitted files" 2>/dev/null)
        WIPREF="backup/wip-$(date +%Y%m%d)"
        if scan_tracked_files "$repo"; then
          if git push -qf origin "$COMMIT:refs/heads/$WIPREF" 2>/dev/null; then
            printf 'SNAPSHOTTED\0%s\n' "$name"
            exit 0
          fi
        else
          printf 'BLOCKED\0%s\n' "$name"
          exit 0
        fi
      fi
    fi

    local unpushed=$(git log @{u}.. --oneline 2>/dev/null | wc -l | tr -d ' ')
    if [ "$unpushed" -gt 0 ]; then
      local branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
      [ "$branch" = "HEAD" ] && branch="$default"

      if [ "$branch" = "$default" ]; then
        WIPREF="backup/master-wip-$(date +%Y%m%d)"
        if scan_tracked_files "$repo"; then
          if git push -qf origin "HEAD:refs/heads/$WIPREF" 2>/dev/null; then
            printf 'SNAPSHOTTED\0%s\n' "$name"
            exit 0
          fi
        else
          printf 'BLOCKED\0%s\n' "$name"
          exit 0
        fi
      else
        if scan_tracked_files "$repo"; then
          if git push -q origin "$branch" 2>/dev/null; then
            printf 'PUSHED\0%s\n' "$name"
            exit 0
          fi
        else
          printf 'BLOCKED\0%s\n' "$name"
          exit 0
        fi
      fi
    fi

    printf 'CLEAN\0%s\n' "$name"
  )
}

log "=== cycle start ==="
temp_json=$(mktemp)
echo "[" > "$temp_json"
first=1
processed_paths=""

# Discover all git repos: scan home dot-directories, root directories, dev/ subdirectory
# This pattern includes ~/.* (dot-dirs like .claude), ~/* (home root), ~/dev/* (dev subtree)
for dir in ~/.* ~/* ~/dev/*; do
  base=$(basename "$dir")
  [ "$base" = "." ] || [ "$base" = ".." ] && continue
  [ ! -d "$dir/.git" ] && continue

  # Normalize path to detect duplicates (e.g., .claude vs .claude/)
  real_dir=$(cd "$dir" && pwd 2>/dev/null)
  if [ -z "$real_dir" ]; then continue; fi
  if echo "$processed_paths" | grep -Fq "$real_dir"; then
    continue
  fi
  processed_paths="$processed_paths
$real_dir"

  if is_touched "$dir"; then
    result=$(process_repo "$dir")
    # P2 FIX: Parse NUL-delimited protocol to safely handle pipes in repo names
    # Write to temp file to properly read NUL-delimited fields
    temp_result=$(mktemp)
    printf '%s' "$result" > "$temp_result"
    # Read first field (state) and second field (name) using NUL delimiter
    state=$(sed 's/\x0.*//' "$temp_result")
    name=$(sed 's/^[^\x0]*\x0//' "$temp_result")
    rm -f "$temp_result"
    [ -z "$state" ] && continue
    if [ "$first" = 1 ]; then
      first=0
    else
      echo "," >> "$temp_json"
    fi
    # P2 FIX: JSON-escape all interpolated values before emitting
    printf '{"repo":"%s","state":"%s","age":"%s"}' "$(json_escape "$name")" "$(json_escape "$state")" "$(date -Iseconds)" >> "$temp_json"
    log "$state: $name"
  fi
done

echo "" >> "$temp_json"
echo "]" >> "$temp_json"
mv "$temp_json" "$REPOS_STATUS"
log "=== cycle end ==="
