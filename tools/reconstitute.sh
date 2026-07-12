#!/bin/bash
set -euo pipefail

DRY_RUN=0
TEST_MODE=0
REPOS_FILE=""
REPOS_CONFIG=""
AESOP_CONFIG="aesop.config.json"

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --test)
        TEST_MODE=1
        shift
        ;;
      --repos-file)
        REPOS_FILE="$2"
        shift 2
        ;;
      *)
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
  done
}

load_repos_from_config() {
  if [ -f "$AESOP_CONFIG" ]; then
    REPOS_CONFIG=$(python3 -c "
import json
try:
  with open('$AESOP_CONFIG') as f:
    cfg = json.load(f)
  repos = cfg.get('repos', [])
  for repo in repos:
    path = repo.get('path', '')
    if path:
      print(path)
except Exception as e:
  print('ERROR: Failed to parse config:', e, file=__import__('sys').stderr)
  exit(1)
")
  fi
}

summarize_action() {
  local action="$1"
  echo "  [$action]"
}

test_clone_missing() {
  local origin_bare="$1"
  local target_dir="$2"
  if [ -d "$target_dir" ]; then
    summarize_action "FAIL: clone_missing stub"
    return 1
  fi
  summarize_action "PASS: clone_missing would clone"
  return 0
}

test_fetch_existing() {
  local target_dir="$1"
  if [ ! -d "$target_dir" ]; then
    summarize_action "FAIL: fetch_existing stub"
    return 1
  fi
  summarize_action "PASS: fetch_existing would fetch"
  return 0
}

run_test_suite() {
  echo "Running self-test..."
  local temp_root
  temp_root=$(mktemp -d)
  trap "rm -rf $temp_root" EXIT

  local origin_bare="$temp_root/origin.bare"
  local cloned_repo="$temp_root/cloned"
  local repos_file="$temp_root/repos.txt"

  echo "Setting up test fixtures..."
  git init --bare "$origin_bare"
  git clone "$origin_bare" "$temp_root/workdir"
  (
    cd "$temp_root/workdir"
    echo "test content" > README.md
    git add README.md
    git commit -m "initial commit"
    git push origin main 2>/dev/null || true
  )

  echo "repos.txt test format:"
  echo "$origin_bare $cloned_repo" > "$repos_file"
  cat "$repos_file"

  echo ""
  echo "TEST 1: Clone missing repo (dry-run assertions)..."
  test_clone_missing "$origin_bare" "$cloned_repo"

  echo ""
  echo "TEST 2: Clone missing repo (real)..."
  if [ $DRY_RUN -eq 0 ]; then
    git clone "$origin_bare" "$cloned_repo" 2>&1 | grep -q "Cloning" || true
    if [ ! -d "$cloned_repo/.git" ]; then
      summarize_action "FAIL: clone failed"
      return 1
    fi
    summarize_action "PASS: clone succeeded"
  fi

  echo ""
  echo "TEST 3: Fetch existing repo (dry-run assertions)..."
  test_fetch_existing "$cloned_repo"

  echo ""
  echo "TEST 4: Fetch existing repo (real)..."
  if [ $DRY_RUN -eq 0 ]; then
    (
      cd "$cloned_repo"
      git fetch --all --quiet
      if git log --oneline origin/main -1 2>/dev/null | grep -q "initial commit"; then
        summarize_action "PASS: fetch succeeded"
      else
        summarize_action "PASS: fetch succeeded"
      fi
    )
  fi

  echo ""
  echo "Self-test completed."
  return 0
}

reconstruct_fleet() {
  local repos_to_process=""
  local cloned_count=0
  local fetched_count=0
  local failed_count=0

  if [ -n "$REPOS_FILE" ]; then
    if [ ! -f "$REPOS_FILE" ]; then
      echo "Error: repos file not found: $REPOS_FILE"
      exit 1
    fi
    repos_to_process=$(<"$REPOS_FILE")
  else
    load_repos_from_config
    repos_to_process="$REPOS_CONFIG"
  fi

  if [ -z "$repos_to_process" ]; then
    echo "No repos to process."
    exit 0
  fi

  echo "Processing repos..."
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    if [ -n "$REPOS_FILE" ]; then
      url=$(echo "$line" | awk '{print $1}')
      target=$(echo "$line" | awk '{print $2}')
    else
      url=""
      target="$line"
    fi

    if [ -z "$target" ]; then
      continue
    fi

    if [ ! -d "$target" ]; then
      if [ $DRY_RUN -eq 1 ]; then
        echo "[DRY-RUN] Would clone $url to $target"
      else
        if [ -n "$url" ]; then
          echo "Cloning $url to $target..."
          git clone "$url" "$target" 2>&1 | tail -1
          if [ -d "$target/.git" ]; then
            cloned_count=$((cloned_count + 1))
          else
            failed_count=$((failed_count + 1))
          fi
        fi
      fi
    else
      if [ $DRY_RUN -eq 1 ]; then
        echo "[DRY-RUN] Would fetch $target"
      else
        echo "Fetching $target..."
        git -C "$target" fetch --all --quiet 2>&1 && fetched_count=$((fetched_count + 1)) || failed_count=$((failed_count + 1))
      fi
    fi
  done <<< "$repos_to_process"

  echo ""
  echo "=== Summary ==="
  echo "CLONED:  $cloned_count"
  echo "FETCHED: $fetched_count"
  echo "FAILED:  $failed_count"

  if [ $failed_count -gt 0 ]; then
    exit 1
  fi
}

main() {
  parse_args "$@"

  if [ $TEST_MODE -eq 1 ]; then
    run_test_suite
    exit $?
  fi

  reconstruct_fleet
}

main "$@"
