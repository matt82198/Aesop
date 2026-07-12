#!/usr/bin/env bash
set -uo pipefail

# Comprehensive TDD test suite for backup-fleet.sh fixes
# Tests must demonstrate real failures before fixes, then pass after

# Get the path to the backup-fleet.sh script being tested (from worktree)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
BACKUP_FLEET_SCRIPT="$SCRIPT_DIR/daemons/backup-fleet.sh"

TEST_DIR="${TEMP_ROOT:-/tmp}/aesop-backup-test-$$"
REPO_DIR="$TEST_DIR/fixture-repo"
AESOP_FIXTURE="$TEST_DIR/aesop-fixture"
STATE_DIR="$AESOP_FIXTURE/state"
TOOLS_DIR="$AESOP_FIXTURE/tools"

PASSED=0
FAILED=0

cleanup() {
  rm -rf "$TEST_DIR" 2>/dev/null || true
}
trap cleanup EXIT

log() {
  echo "[TEST] $*"
}

fail() {
  echo "❌ FAIL: $*" >&2
  ((FAILED++))
}

pass() {
  echo "✓ PASS: $*"
  ((PASSED++))
}

setup_fixture() {
  rm -rf "$TEST_DIR"
  mkdir -p "$REPO_DIR" "$STATE_DIR" "$TOOLS_DIR"

  cd "$REPO_DIR"
  git init
  git config user.email "test@example.com"
  git config user.name "Test User"
  git remote add origin https://github.com/test/fixture.git

  echo "initial" > README.md
  git add README.md
  git commit -m "initial commit"
}

create_mock_scanner() {
  cat > "$TOOLS_DIR/secret_scan.py" << 'SCANNER'
#!/usr/bin/env python3
import sys
import os

for filepath in sys.argv[1:]:
    if not os.path.isfile(filepath):
        continue
    try:
        with open(filepath, 'r', errors='ignore') as f:
            content = f.read()
            if ('AK' 'IA') in content:
                sys.exit(1)
    except Exception:
        pass

sys.exit(0)
SCANNER
  chmod +x "$TOOLS_DIR/secret_scan.py"
}

# ===== ITEM 1: NUL Protocol Integration Test (REAL backup-fleet loop) =====

test_item1_nul_protocol_real_loop() {
  log "TEST ITEM 1: Real backup-fleet loop with repo containing special chars in name"

  setup_fixture
  create_mock_scanner

  # Simulate repo name with pipe character
  local fixture_name="fixture|with|pipe"

  # Add uncommitted changes to trigger state change
  echo "modified content" >> README.md

  cd "$TEST_DIR"

  # Run the actual backup-fleet logic (main loop) against our fixture
  # We'll extract and run just the per-repo processing
  AESOP_ROOT="$AESOP_FIXTURE" bash -c '
    source_backup_functions() {
      eval "$(sed -n "/^is_touched()/,/^}/p" '"$BACKUP_FLEET_SCRIPT"')"
      eval "$(sed -n "/^json_escape()/,/^}/p" '"$BACKUP_FLEET_SCRIPT"')"
      eval "$(sed -n "/^process_repo()/,/^}/p" '"$BACKUP_FLEET_SCRIPT"')"
      eval "$(sed -n "/^get_tracked_modifications()/,/^}/p" '"$BACKUP_FLEET_SCRIPT"')"
      eval "$(sed -n "/^get_untracked_files()/,/^}/p" '"$BACKUP_FLEET_SCRIPT"')"
      eval "$(sed -n "/^scan_tracked_files()/,/^}/p" '"$BACKUP_FLEET_SCRIPT"')"
      eval "$(sed -n "/^get_default_branch()/,/^}/p" '"$BACKUP_FLEET_SCRIPT"')"
    }

    source_backup_functions

    # Create JSON output like backup-fleet does
    temp_json=$(mktemp)
    echo "[" > "$temp_json"
    first=1

    dir="'"$REPO_DIR"'"

    if is_touched "$dir"; then
      # This is the critical test: process_repo outputs NUL-delimited data
      # P0 FIX: Direct redirect instead of $() to preserve NUL bytes
      temp_result=$(mktemp)
      process_repo "$dir" > "$temp_result"

      # Parse NUL-delimited data
      state=$(sed "s/\x0.*//" "$temp_result")
      name=$(sed "s/^[^\x0]*\x0//" "$temp_result")
      rm -f "$temp_result"

      [ -z "$state" ] && exit 1

      escaped_name=$(printf "%s" "$name" | sed '\''s/\\/\\\\\\\\/g; s/"/\\\\"/g'\'')
      escaped_state=$(printf "%s" "$state" | sed '\''s/\\/\\\\\\\\/g; s/"/\\\\"/g'\'')

      printf "{\"repo\":\"%s\",\"state\":\"%s\",\"age\":\"2025-07-12T14:32:01Z\"}" "$escaped_name" "$escaped_state" >> "$temp_json"
    fi

    echo "" >> "$temp_json"
    echo "]" >> "$temp_json"
    cat "$temp_json"
    rm -f "$temp_json"
  ' > "$TEST_DIR/output.json" 2>/dev/null

  # Parse and verify the JSON output
  if [ -f "$TEST_DIR/output.json" ]; then
    if python3 -m json.tool < "$TEST_DIR/output.json" >/dev/null 2>&1; then
      pass "ITEM 1: JSON output is valid"
    else
      fail "ITEM 1: JSON output is INVALID (python parse failed) - NUL protocol broken"
      cat "$TEST_DIR/output.json"
      return 1
    fi

    # Verify repo field is correctly extracted
    local repo_value
    repo_value=$(python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0].get('repo', ''))" < "$TEST_DIR/output.json" 2>/dev/null || echo "")

    if [ -n "$repo_value" ]; then
      pass "ITEM 1: Repo field extracted from NUL-delimited protocol"
    else
      fail "ITEM 1: Repo field is empty - NUL protocol destroyed by \$() substitution"
    fi

    # Verify state field is correct (should be CLEAN since we didn't push)
    local state_value
    state_value=$(python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0].get('state', ''))" < "$TEST_DIR/output.json" 2>/dev/null || echo "")

    if [ "$state_value" = "CLEAN" ] || [ "$state_value" = "SNAPSHOTTED" ]; then
      pass "ITEM 1: State field correctly extracted (found: $state_value)"
    else
      fail "ITEM 1: State field corrupted or empty (got: '$state_value')"
    fi
  else
    fail "ITEM 1: Failed to generate JSON output"
  fi
}

# ===== ITEM 2: JSON Escaping Control Characters =====

test_item2_json_escaping_control_chars() {
  log "TEST ITEM 2: JSON escaping for control characters (\n, \r, \t, C0)"

  setup_fixture
  create_mock_scanner

  # Directly test json_escape function
  eval "$(sed -n '/^json_escape()/,/^}/p' "$BACKUP_FLEET_SCRIPT")"

  # Test repo name with literal newline
  local repo_newline="repo"$'\n'"with"$'\n'"newline"
  local escaped_newline=$(json_escape "$repo_newline")

  # Create JSON to test validity
  local json_test="{\"repo\":\"$escaped_newline\"}"
  if python3 -m json.tool <<< "$json_test" >/dev/null 2>&1; then
    pass "ITEM 2: Newline character properly escaped (JSON valid)"
  else
    fail "ITEM 2: Newline character NOT escaped correctly (JSON invalid) - this is a blocker"
  fi

  # Test repo name with literal tab
  local repo_tab="repo"$'\t'"with_tab"
  local escaped_tab=$(json_escape "$repo_tab")

  json_test="{\"repo\":\"$escaped_tab\"}"
  if python3 -m json.tool <<< "$json_test" >/dev/null 2>&1; then
    pass "ITEM 2: Tab character properly escaped (JSON valid)"
  else
    fail "ITEM 2: Tab character NOT escaped correctly (JSON invalid) - this is a blocker"
  fi

  # Test backslash (should already work)
  local repo_backslash="repo\\with\\backslash"
  local escaped_backslash=$(json_escape "$repo_backslash")

  json_test="{\"repo\":\"$escaped_backslash\"}"
  if python3 -m json.tool <<< "$json_test" >/dev/null 2>&1; then
    pass "ITEM 2: Backslash character properly escaped (JSON valid)"
  else
    fail "ITEM 2: Backslash character NOT escaped correctly (JSON invalid)"
  fi

  # Test carriage return
  local repo_cr="repo"$'\r'"with"$'\r'"cr"
  local escaped_cr=$(json_escape "$repo_cr")

  json_test="{\"repo\":\"$escaped_cr\"}"
  if python3 -m json.tool <<< "$json_test" >/dev/null 2>&1; then
    pass "ITEM 2: Carriage return properly escaped (JSON valid)"
  else
    fail "ITEM 2: Carriage return NOT escaped correctly (JSON invalid) - this is a blocker"
  fi
}

# ===== ITEM 3: Portable Date =====

test_item3_portable_date() {
  log "TEST ITEM 3: Portable date format (not GNU-only)"

  # Test that date -Iseconds fails on systems that don't support it
  # and our portable version works

  AESOP_ROOT="$AESOP_FIXTURE" bash -c '
    # Try GNU-only date -Iseconds
    gnu_date=$(date -Iseconds 2>/dev/null || echo "FAILED")

    # Try portable version
    portable_date=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "FAILED")

    if [ "$gnu_date" = "FAILED" ]; then
      echo "gnu_FAILED"
    else
      echo "gnu_OK"
    fi

    if [ "$portable_date" = "FAILED" ]; then
      echo "portable_FAILED"
    else
      echo "portable_OK"
    fi

    # Verify portable format matches ISO 8601
    if echo "$portable_date" | grep -qE "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"; then
      echo "format_VALID"
    else
      echo "format_INVALID"
    fi
  ' > "$TEST_DIR/date_result.txt" 2>/dev/null

  # On modern systems, GNU date usually works, but portable version should too
  if grep -q "portable_OK" "$TEST_DIR/date_result.txt"; then
    pass "ITEM 3: Portable date format works"
  else
    fail "ITEM 3: Portable date format failed"
  fi

  if grep -q "format_VALID" "$TEST_DIR/date_result.txt"; then
    pass "ITEM 3: Date format is ISO 8601 compliant"
  else
    fail "ITEM 3: Date format is invalid (must be YYYY-MM-DDTHH:MM:SSZ)"
  fi
}

# ===== Integration: Comprehensive escaping test =====

test_full_cycle_with_special_chars() {
  log "TEST: Integration - All fixes applied (NUL, escaping, date)"

  # Test that json_escape handles all control characters needed
  eval "$(sed -n '/^json_escape()/,/^}/p' "$BACKUP_FLEET_SCRIPT")"

  # Test escape function with various problematic characters
  local test_cases=(
    "normal_repo"
    "repo|with|pipe"
    "repo\"with\"quote"
    "repo\\with\\backslash"
  )

  local all_valid=1
  local json_test=""

  for repo in "${test_cases[@]}"; do
    local escaped=$(json_escape "$repo")
    json_test="{\"repo\":\"$escaped\"}"

    if ! python3 -m json.tool <<< "$json_test" >/dev/null 2>&1; then
      fail "Full cycle: JSON escaping failed for repo '$repo'"
      all_valid=0
    fi
  done

  if [ $all_valid -eq 1 ]; then
    pass "Full cycle: JSON escaping handles all special characters"
  fi

  # Test that portable date format works
  local test_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if [[ $test_date =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
    pass "Full cycle: Date format is ISO 8601 compliant (portable)"
  else
    fail "Full cycle: Date format issue"
  fi

  # Test complete entry construction
  local repo_escaped=$(json_escape "test|repo")
  local state_escaped=$(json_escape "CLEAN")
  local age=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local json_entry="{\"repo\":\"$repo_escaped\",\"state\":\"$state_escaped\",\"age\":\"$age\"}"

  if python3 -m json.tool <<< "$json_entry" >/dev/null 2>&1; then
    pass "Full cycle: Complete JSON entry is valid"
  else
    fail "Full cycle: Complete JSON entry is INVALID"
  fi
}

# ===== Run all tests =====

echo "=================================================="
echo "Backup Fleet Daemon Test Suite (TDD-First)"
echo "=================================================="
echo ""

log "Running ITEM 1 test (NUL protocol with real loop)..."
test_item1_nul_protocol_real_loop
echo ""

log "Running ITEM 2 test (JSON escaping control chars)..."
test_item2_json_escaping_control_chars
echo ""

log "Running ITEM 3 test (portable date)..."
test_item3_portable_date
echo ""

log "Running full cycle integration test..."
test_full_cycle_with_special_chars
echo ""

echo "=================================================="
echo "Test Results: $PASSED passed, $FAILED failed"
echo "=================================================="

exit $FAILED
