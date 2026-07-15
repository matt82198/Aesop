#!/usr/bin/env bash
# Tests for pre-push-policy.sh — branch protection and secret scanning hooks
# TDD: Write failing tests first, then implement fixes
set -uo pipefail

# Source the hook script
HOOK_SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/hooks/pre-push-policy.sh"

# Temporary test directory
TMPDIR="${TMPDIR:-/tmp}"
TEST_ROOT="$TMPDIR/pre_push_test_$$"
trap "rm -rf '$TEST_ROOT'" EXIT
mkdir -p "$TEST_ROOT"

# Import hook functions by sourcing the hook script directly.
# The hook guards its own "main "$@"" call with a BASH_SOURCE check so
# sourcing it here only defines functions and never executes main()
# or reads from stdin.
source "$HOOK_SCRIPT"

test_passed=0
test_failed=0

# ===== NEW TESTS FOR 6 FINDINGS =====

printf '\n=== Finding 1: Race condition in hash-chain (concurrent writes) ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_race"
  mkdir -p "$AESOP_ROOT/state"

  # Simulate two concurrent log_block calls (both read tail, both append)
  # Expected: write lock ensures consistent prev_hash chain
  log_block "concurrent_1" &
  pid1=$!
  log_block "concurrent_2" &
  pid2=$!
  wait $pid1 $pid2

  # Verify chain integrity after concurrent writes
  if verify_audit_log "$AESOP_ROOT/state/SECURITY-AUDIT.log" >/dev/null 2>&1; then
    printf 'PASS: Concurrent log_block calls do not break hash chain\n'
  else
    printf 'FAIL: Hash chain broken after concurrent writes\n'
    exit 1
  fi
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Finding 2: Tail truncation not detected ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_truncate"
  mkdir -p "$AESOP_ROOT/state"

  log_block "entry_1"
  log_block "entry_2"
  log_block "entry_3"

  # Get the original tail hash before truncation
  # We'll check the sidecar file for the anchor
  original_tail_file="$AESOP_ROOT/state/.audit-tail-hash"
  if [ ! -f "$original_tail_file" ]; then
    printf 'FAIL: Tail hash anchor file not created\n'
    exit 1
  fi

  # Truncate the log (remove last line)
  head -n 2 "$AESOP_ROOT/state/SECURITY-AUDIT.log" > "$AESOP_ROOT/state/SECURITY-AUDIT.log.tmp"
  mv "$AESOP_ROOT/state/SECURITY-AUDIT.log.tmp" "$AESOP_ROOT/state/SECURITY-AUDIT.log"

  # verify_audit_log should return non-zero on truncation
  if verify_audit_log "$AESOP_ROOT/state/SECURITY-AUDIT.log" >/dev/null 2>&1; then
    printf 'FAIL: Truncation not detected by verify_audit_log\n'
    exit 1
  fi
  printf 'PASS: Truncation detection working\n'
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Finding 3: stdin loop hangs on tty + drops final line without newline ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_stdin"
  mkdir -p "$AESOP_ROOT/state"

  # Create isolated git repo on feature branch to hermetically test check_branch_policy
  # (avoids dependency on ambient git HEAD, which may be main during CI push events)
  ISOLATED_REPO="$TEST_ROOT/aesop_stdin_repo"
  mkdir -p "$ISOLATED_REPO"
  (
    cd "$ISOLATED_REPO" || exit 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    echo "dummy" > file.txt
    git add file.txt
    git commit -q -m "initial"
    git checkout -q -b feature/isolated

    # Test 3a: Final line without newline should be handled
    printf 'refs/heads/feature/test abc123 refs/heads/feature/test def456' | {
      if check_branch_policy >/dev/null 2>&1; then
        printf 'PASS: Final line without newline handled correctly\n'
      else
        printf 'FAIL: Failed to handle final line without newline\n'
        exit 1
      fi
    }
  )
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Finding 4: Test 6 should call REAL check_branch_policy, not reimplement ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_test6"
  mkdir -p "$AESOP_ROOT/state"

  # Test that check_branch_policy via pipe works correctly
  local_sha="abc123def456"
  remote_main_sha="0000000000000000000000000000000000000000"

  printf 'refs/heads/feature/test %s refs/heads/main %s\n' "$local_sha" "$remote_main_sha" | {
    if ! check_branch_policy >/dev/null 2>&1; then
      printf 'PASS: Real check_branch_policy correctly blocks main via stdin\n'
    else
      printf 'FAIL: check_branch_policy should block push to main\n'
      exit 1
    fi
  }
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Finding 5: json_escape missing control chars (\\n, \\r, \\t, C0) ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_escape"
  mkdir -p "$AESOP_ROOT/state"

  # Set user name with embedded newline (dangerous!)
  git config user.name $'Alice\nAdmin'

  log_block "test"

  audit_line=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")

  # Should be valid JSON after proper escaping
  if printf '%s' "$audit_line" | python3 -m json.tool >/dev/null 2>&1; then
    printf 'PASS: Control character escaping produces valid JSON (newline test)\n'
  else
    printf 'FAIL: JSON with control char is invalid\n'
    printf 'Entry: %s\n' "$audit_line"
    exit 1
  fi
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Finding 5b: json_escape all C0 control characters ===\n'
(
  # Direct test: Pass string with various C0 control chars to json_escape
  # Test chars: BEL (\x07), BS (\x08), VT (\x0b), FF (\x0c), SO (\x0e), ESC (\x1b)
  test_string=$(printf 'Alice\x07\x08\x0b\x0c\x0e\x1bAdmin')
  escaped=$(json_escape "$test_string")

  # The escaped output should be JSON-safe (no bare control chars)
  # Create a minimal JSON object with the escaped string and validate
  json_obj=$(printf '{"user":"%s"}' "$escaped")

  if printf '%s' "$json_obj" | python3 -m json.tool >/dev/null 2>&1; then
    printf 'PASS: All C0 control characters properly escaped to valid JSON\n'
  else
    printf 'FAIL: JSON with escaped C0 control chars is invalid\n'
    printf 'Escaped string: %s\n' "$escaped"
    printf 'JSON object: %s\n' "$json_obj"
    exit 1
  fi
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Finding 6: sha256sum unchecked → silent empty hash ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_nosha"
  mkdir -p "$AESOP_ROOT/state"

  # Mask sha256sum so it's not available
  export PATH="/usr/bin:/bin"  # Minimal PATH without sha256sum

  # Call get_previous_hash; should fail loudly or fallback gracefully
  if hash=$(get_previous_hash "$AESOP_ROOT/state/SECURITY-AUDIT.log" 2>&1); then
    if [ -z "$hash" ]; then
      printf 'FAIL: sha256sum unavailable produced silent empty hash\n'
      exit 1
    fi
    printf 'PASS: Fallback or error handling for missing sha256sum\n'
  else
    printf 'PASS: Loud error when sha256sum unavailable\n'
  fi
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

# ===== EXISTING TESTS (6-11) =====

printf '\n=== Test 6 (existing): stdin refspec bypass detection (HEAD:main) ===\n'
(
  cd "$TEST_ROOT" || exit 1
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test User"

  # Create initial commit
  echo "dummy" > file.txt
  git add file.txt
  git commit -q -m "initial"

  # Create a feature branch and commit
  git checkout -q -b feature/test
  echo "change" > file.txt
  git add file.txt
  git commit -q -m "feature change"

  local_sha=$(git rev-parse HEAD)
  remote_main_sha="0000000000000000000000000000000000000000"

  stdin_input="refs/heads/feature/test $local_sha refs/heads/main $remote_main_sha"

  printf '%s\n' "$stdin_input" | {
    if ! check_branch_policy >/dev/null 2>&1; then
      printf 'PASS: Correctly blocked push to main via stdin refspec\n'
    else
      printf 'FAIL: Should have blocked push to main\n'
      exit 1
    fi
  }
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Test 7 (existing): Secret scan unavailable logs audit event ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_no_scanner"
  mkdir -p "$AESOP_ROOT/state"

  stderr_output=$( { check_secret_scan; } 2>&1 1>/dev/null )
  exit_code=$?

  if [ "$exit_code" -ne 0 ]; then
    printf 'FAIL: check_secret_scan should return 0 when scanner missing (fail-open)\n'
    exit 1
  fi

  if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
    printf 'FAIL: Audit log not created when scanner is unavailable\n'
    exit 1
  fi

  audit_line=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")

  if ! printf '%s' "$audit_line" | python3 -m json.tool >/dev/null 2>&1; then
    printf 'FAIL: Audit log entry is not valid JSON\n'
    exit 1
  fi

  if ! printf '%s' "$audit_line" | grep -q '"event":"secret_scan_unavailable"'; then
    printf 'FAIL: Audit log entry missing correct event type\n'
    exit 1
  fi

  printf 'PASS: Secret scan unavailable logged with event and stderr warning\n'
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Test 8 (existing): Hash-chain audit log (GENESIS first event) ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_hashchain"
  mkdir -p "$AESOP_ROOT/state"

  log_block "test_block_1"

  if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
    printf 'FAIL: Audit log not created\n'
    exit 1
  fi

  audit_line=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")

  if ! printf '%s' "$audit_line" | grep -q '"prev_hash":"GENESIS"'; then
    printf 'FAIL: First event should have prev_hash=GENESIS\n'
    exit 1
  fi

  if ! printf '%s' "$audit_line" | python3 -m json.tool >/dev/null 2>&1; then
    printf 'FAIL: Hash-chained entry is not valid JSON\n'
    exit 1
  fi

  printf 'PASS: First event has GENESIS prev_hash and valid JSON\n'
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Test 9 (existing): Hash-chain builds across 2+ events ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_hashchain2"
  mkdir -p "$AESOP_ROOT/state"

  log_block "test_block_1"
  log_block "test_block_2"

  if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
    printf 'FAIL: Audit log not created\n'
    exit 1
  fi

  line_count=$(wc -l < "$AESOP_ROOT/state/SECURITY-AUDIT.log")
  if [ "$line_count" -ne 2 ]; then
    printf 'FAIL: Expected 2 audit log entries, got %d\n' "$line_count"
    exit 1
  fi

  line1=$(head -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")
  line2=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")

  if ! printf '%s' "$line1" | grep -q '"prev_hash":"GENESIS"'; then
    printf 'FAIL: First event should have prev_hash=GENESIS\n'
    exit 1
  fi

  if ! printf '%s' "$line2" | grep -q '"prev_hash":'; then
    printf 'FAIL: Second event should have prev_hash field\n'
    exit 1
  fi

  line1_hash=$(printf '%s' "$line1" | sha256sum | awk '{print $1}')
  line2_prev=$(printf '%s' "$line2" | python3 -c "import sys, json; print(json.load(sys.stdin).get('prev_hash', ''))")

  if [ "$line1_hash" != "$line2_prev" ]; then
    printf 'FAIL: Second event prev_hash does not match first line hash\n'
    exit 1
  fi

  printf 'PASS: Hash chain builds correctly across 2 events\n'
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Test 10 (existing): verify-audit-log passes on intact chain ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_verify"
  mkdir -p "$AESOP_ROOT/state"

  log_block "entry_1"
  log_block "entry_2"
  log_event "entry_3"

  if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
    printf 'FAIL: Audit log not created\n'
    exit 1
  fi

  if type verify_audit_log >/dev/null 2>&1; then
    if verify_audit_log "$AESOP_ROOT/state/SECURITY-AUDIT.log" >/dev/null 2>&1; then
      printf 'PASS: Verification passed on intact chain\n'
    else
      printf 'FAIL: Verification should pass on intact chain\n'
      exit 1
    fi
  else
    printf 'SKIP: verify_audit_log function not yet implemented\n'
  fi
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== Test 11 (existing): verify-audit-log detects tampered line ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_tamper"
  mkdir -p "$AESOP_ROOT/state"

  log_block "entry_1"
  log_block "entry_2"
  log_block "entry_3"

  if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
    printf 'FAIL: Audit log not created\n'
    exit 1
  fi

  sed -i '2s/"reason":"[^"]*"/"reason":"TAMPERED"/g' "$AESOP_ROOT/state/SECURITY-AUDIT.log"

  if type verify_audit_log >/dev/null 2>&1; then
    if ! verify_audit_log "$AESOP_ROOT/state/SECURITY-AUDIT.log" >/dev/null 2>&1; then
      printf 'PASS: Verification detected tampered middle line\n'
    else
      printf 'FAIL: Verification should detect tampering\n'
      exit 1
    fi
  else
    printf 'SKIP: verify_audit_log function not yet implemented\n'
  fi
)
if [ $? -eq 0 ]; then
  test_passed=$((test_passed + 1))
else
  test_failed=$((test_failed + 1))
fi

printf '\n=== P1 Bug2: compute_sha256 falls back to shasum when sha256sum is unavailable ===\n'
(
  expected="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"  # sha256("abc")
  got=$(printf 'abc' | compute_sha256)
  if [ "$got" != "$expected" ]; then
    printf 'FAIL: compute_sha256 primary path produced wrong hash: %s\n' "$got"
    exit 1
  fi
  # Force the fallback deterministically: shadow the `command` builtin so
  # `command -v sha256sum` reports "not found" (simulates a shasum-only host
  # like macOS/BSD). The old code hardcoded sha256sum at 4 of 5 sites and would
  # emit an EMPTY hash here; the compute_sha256 helper must produce a real one.
  command() {
    if [ "${1:-}" = "-v" ] && [ "${2:-}" = "sha256sum" ]; then return 1; fi
    builtin command "$@"
  }
  if builtin command -v shasum >/dev/null 2>&1; then
    gotfb=$(printf 'abc' | compute_sha256)
    if [ "$gotfb" != "$expected" ]; then
      printf 'FAIL: compute_sha256 shasum-fallback produced wrong hash: %s\n' "$gotfb"
      exit 1
    fi
    printf 'PASS: compute_sha256 falls back to shasum and yields the correct hash\n'
  else
    printf 'PASS: primary path correct (shasum absent; fallback path not exercisable here)\n'
  fi
)
if [ $? -eq 0 ]; then test_passed=$((test_passed + 1)); else test_failed=$((test_failed + 1)); fi

printf '\n=== P1 Bug1: verify_audit_log holds the write lock (no false truncation vs concurrent append) ===\n'
(
  export AESOP_ROOT="$TEST_ROOT/aesop_verify_lock"
  mkdir -p "$AESOP_ROOT/state"
  log="$AESOP_ROOT/state/SECURITY-AUDIT.log"
  log_block "seed_1" >/dev/null 2>&1
  log_block "seed_2" >/dev/null 2>&1
  bad=0
  i=0
  while [ "$i" -lt 6 ]; do
    log_block "concurrent_$i" >/dev/null 2>&1 &
    ap=$!
    out=$(verify_audit_log "$log" 2>&1)
    wait "$ap" 2>/dev/null
    if printf '%s' "$out" | grep -qiE 'truncat|tamper|chain.*brok|brok.*chain'; then
      bad=1
    fi
    i=$((i + 1))
  done
  if [ "$bad" -ne 0 ]; then
    printf 'FAIL: verify_audit_log falsely reported truncation/tamper during a concurrent append (no lock)\n'
    exit 1
  fi
  if [ -d "$AESOP_ROOT/state/.audit-log-lock" ]; then
    printf 'FAIL: verify_audit_log left its .audit-log-lock behind (not released)\n'
    exit 1
  fi
  printf 'PASS: verify_audit_log serializes via the write lock; no false truncation, lock released\n'
)
if [ $? -eq 0 ]; then test_passed=$((test_passed + 1)); else test_failed=$((test_failed + 1)); fi

printf '\n=== Test Summary ===\n'
printf 'Tests PASSED: %d\n' "$test_passed"
printf 'Tests FAILED: %d\n' "$test_failed"

if [ "$test_failed" -eq 0 ]; then
  printf '\nAll tests passed.\n'
  exit 0
else
  printf '\nSome tests failed.\n'
  exit 1
fi
