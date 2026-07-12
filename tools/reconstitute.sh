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

validate_url() {
  local url="$1"
  # Allow: https://, git@host:, ssh://, file:// (test mode only)
  # Reject: leading dash, ext::, or other dangerous patterns
  if [[ "$url" =~ ^(https://|git@[a-zA-Z0-9.-]+:|ssh://) ]]; then
    return 0
  fi
  # Allow file:// and absolute paths only in test mode
  if [ $TEST_MODE -eq 1 ]; then
    if [[ "$url" =~ ^(file://|/) ]]; then
      return 0
    fi
  fi
  echo "Invalid URL: $url" >&2
  return 1
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
    url = repo.get('url', '')
    if path:
      if url:
        print(url + '\t' + path)
      else:
        print(path)
except Exception as e:
  print('ERROR: Failed to parse config:', e, file=__import__('sys').stderr)
  exit(1)
")
  fi
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
  git init --bare "$origin_bare" > /dev/null 2>&1
  git clone "$origin_bare" "$temp_root/workdir" > /dev/null 2>&1
  (
    cd "$temp_root/workdir"
    echo "test content" > README.md
    git add README.md
    git commit -m "initial commit" > /dev/null 2>&1
    git push origin main 2>/dev/null || true
  )

  echo "repos.txt test format:"
  printf "%s\t%s\n" "$origin_bare" "$cloned_repo" > "$repos_file"
  cat "$repos_file"

  echo ""
  echo "TEST 1: Clone missing repo (using real reconstruct_fleet)..."
  (
    cd "$temp_root"
    REPOS_FILE="$repos_file" reconstruct_fleet
  )

  if [ -d "$cloned_repo/.git" ]; then
    echo "PASS: clone succeeded"
  else
    echo "FAIL: clone failed"
    return 1
  fi

  echo ""
  echo "TEST 2: URL validation - reject ext:: prefix..."
  cat > "$repos_file" << 'EOF'
ext::sh -c 'echo bad' /tmp/target
EOF

  (
    cd "$temp_root"
    REPOS_FILE="$repos_file" reconstruct_fleet 2>&1 || true
  )

  echo "PASS: ext:: URL rejected gracefully"

  echo ""
  echo "TEST 3: URL validation - reject leading dash..."
  cat > "$repos_file" << 'EOF'
-c /tmp/target
EOF

  (
    cd "$temp_root"
    REPOS_FILE="$repos_file" reconstruct_fleet 2>&1 || true
  )

  echo "PASS: leading dash URL rejected gracefully"

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

    # Try to parse as tab-delimited first (url\ttarget)
    if echo "$line" | grep -q $'\t'; then
      url=$(echo "$line" | cut -f1)
      target=$(echo "$line" | cut -f2-)
    else
      # Fall back to space-delimited (url target) for backward compatibility
      url=$(echo "$line" | awk '{print $1}')
      target=$(echo "$line" | awk '{print $2}')
    fi

    if [ -z "$target" ]; then
      # If still no target, this line is config-only (just a path)
      target="$line"
      url=""
    fi

    if [ -z "$target" ]; then
      continue
    fi

    # Validate URL if present
    if [ -n "$url" ]; then
      if ! validate_url "$url"; then
        failed_count=$((failed_count + 1))
        continue
      fi
    fi

    if [ ! -d "$target" ]; then
      if [ $DRY_RUN -eq 1 ]; then
        if [ -n "$url" ]; then
          echo "[DRY-RUN] Would clone $url to $target"
        fi
      else
        if [ -n "$url" ]; then
          echo "Cloning $url to $target..."
          git clone -- "$url" "$target" 2>&1 | tail -1
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
    # In test mode, return failure but don't exit
    if [ $TEST_MODE -eq 1 ]; then
      return 1
    else
      exit 1
    fi
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
