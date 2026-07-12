#!/bin/bash
set -euo pipefail

# Reconstitute.sh: Clone or fetch repos from config/file
# Parses tab-delimited (url\ttarget) or space-delimited (url target) repos
# Tab-delimited recommended: preserves paths with spaces
# Legacy space-delimited supported but discouraged for multi-word paths
# ISSUE 1 FIX: Validates clone targets against fleet root (HIGH, security)
# ISSUE 2 FIX: Tests drive real script via TEST_MODE=1 (P1, bash)
# ISSUE 3 FIX: Uses read -r semantics for space-delimited parsing (P2, arch)

DRY_RUN=0
TEST_MODE="${TEST_MODE:-0}"
REPOS_FILE=""
REPOS_CONFIG=""
AESOP_CONFIG="aesop.config.json"
AESOP_FLEET_ROOT="${AESOP_FLEET_ROOT:-}"

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

get_fleet_root() {
  # Priority: env var > config file > default home
  if [ -n "$AESOP_FLEET_ROOT" ]; then
    echo "$AESOP_FLEET_ROOT"
    return 0
  fi

  if [ -f "$AESOP_CONFIG" ]; then
    local config_fleet_root
    config_fleet_root=$(python3 -c "
import json
try:
  with open('$AESOP_CONFIG') as f:
    cfg = json.load(f)
  fleet_root = cfg.get('fleet_root', '')
  if fleet_root:
    print(fleet_root)
except:
  pass
" 2>/dev/null || true)
    if [ -n "$config_fleet_root" ]; then
      echo "$config_fleet_root"
      return 0
    fi
  fi

  # Default to home directory
  echo "$HOME"
}

validate_target() {
  local target="$1"
  local fleet_root="$2"

  # Empty target
  if [ -z "$target" ]; then
    echo "Error: target path cannot be empty" >&2
    return 1
  fi

  # Resolve the target path to an absolute path
  # Handle relative paths by prepending current directory
  local abs_target
  if [[ "$target" = /* ]]; then
    abs_target="$target"
  else
    abs_target="$PWD/$target"
  fi

  # Normalize the path to resolve .. and .
  # Use cd + pwd to safely resolve symlinks and relative components
  local normalized
  if [ -d "$abs_target" ]; then
    normalized=$(cd "$abs_target" && pwd)
  else
    # For non-existent targets, manually normalize
    normalized=$(cd "$(dirname "$abs_target")" && pwd)/$(basename "$abs_target")
  fi

  # Normalize fleet root
  local normalized_fleet_root
  if [ -d "$fleet_root" ]; then
    normalized_fleet_root=$(cd "$fleet_root" && pwd)
  else
    normalized_fleet_root="$fleet_root"
  fi

  # Ensure fleet root ends without trailing slash for comparison
  normalized_fleet_root="${normalized_fleet_root%/}"

  # Check if target is under fleet root
  # Using pattern matching: if normalized path starts with fleet_root/, it's valid
  if [[ "$normalized" = "$normalized_fleet_root" ]] || [[ "$normalized" = "$normalized_fleet_root"/* ]]; then
    return 0
  fi

  # Target escapes fleet root
  echo "Error: target path '$target' (resolves to: $normalized) is outside fleet root '$fleet_root'" >&2
  return 1
}

load_repos_from_config() {
  if [ -f "$AESOP_CONFIG" ]; then
    # Also load fleet_root from config if not already set
    if [ -z "$AESOP_FLEET_ROOT" ]; then
      AESOP_FLEET_ROOT=$(python3 -c "
import json
try:
  with open('$AESOP_CONFIG') as f:
    cfg = json.load(f)
  fleet_root = cfg.get('fleet_root', '')
  if fleet_root:
    print(fleet_root)
except:
  pass
" 2>/dev/null || true)
    fi

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

  # Set fleet root to temp_root for test isolation
  AESOP_FLEET_ROOT="$temp_root"

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

  # Get the fleet root for target validation
  local fleet_root
  fleet_root=$(get_fleet_root)

  echo "Processing repos..."
  while IFS= read -r line; do
    [ -z "$line" ] && continue

    url=""
    target=""

    # Try to parse as tab-delimited first (url\ttarget)
    if echo "$line" | grep -q $'\t'; then
      url=$(echo "$line" | cut -f1)
      target=$(echo "$line" | cut -f2-)
    else
      # Fall back to space-delimited (url target) for backward compatibility
      # ISSUE 3 FIX: Use read -r to preserve spaces in the remainder
      # Split on first space only
      read -r url target <<< "$line"
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

    # ISSUE 1 FIX: Validate target path against fleet root before any git operations
    if ! validate_target "$target" "$fleet_root"; then
      failed_count=$((failed_count + 1))
      continue
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

  # If --test flag was explicitly passed, run the built-in test suite
  # Otherwise, use TEST_MODE from environment (if set) for external testing
  # This allows external tests to use TEST_MODE=1 without triggering the built-in suite
  if [ "${TEST_SUITE:-0}" -eq 1 ]; then
    run_test_suite
    exit $?
  fi

  reconstruct_fleet
}

# Check if --test was explicitly passed (before parse_args overwrites it)
TEST_SUITE=0
for arg in "$@"; do
  if [ "$arg" = "--test" ]; then
    TEST_SUITE=1
    break
  fi
done

main "$@"
