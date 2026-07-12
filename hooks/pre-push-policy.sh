#!/usr/bin/env bash
set -uo pipefail

json_escape() {
  # Escape backslashes first, then quotes for valid JSON
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

get_previous_hash() {
  local audit_log="$1"
  if [ ! -f "$audit_log" ] || [ ! -s "$audit_log" ]; then
    printf 'GENESIS'
  else
    tail -n 1 "$audit_log" | tr -d '\n' | sha256sum | awk '{print $1}'
  fi
}

verify_audit_log() {
  local audit_log="$1"
  if [ ! -f "$audit_log" ]; then
    printf 'Error: Audit log not found at %s\n' "$audit_log" >&2
    return 1
  fi

  if [ ! -s "$audit_log" ]; then
    printf 'Audit log is empty or does not exist\n'
    return 0
  fi

  local line_num=0
  local prev_line=""
  local expected_hash=""
  local actual_prev_hash=""

  while IFS= read -r line; do
    line_num=$((line_num + 1))

    if [ $line_num -eq 1 ]; then
      expected_hash="GENESIS"
    else
      expected_hash=$(printf '%s' "$prev_line" | sha256sum | awk '{print $1}')
    fi

    actual_prev_hash=$(printf '%s' "$line" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('prev_hash', 'MISSING'))" 2>/dev/null)

    if [ "$actual_prev_hash" = "MISSING" ]; then
      printf 'Error: Line %d missing prev_hash field\n' "$line_num" >&2
      return 1
    fi

    if [ "$actual_prev_hash" != "$expected_hash" ]; then
      printf 'Error: Hash chain broken at line %d\n' "$line_num" >&2
      printf '  Expected prev_hash: %s\n' "$expected_hash" >&2
      printf '  Actual prev_hash: %s\n' "$actual_prev_hash" >&2
      return 1
    fi

    prev_line="$line"
  done < "$audit_log"

  if [ $line_num -gt 0 ]; then
    printf 'Audit log verification OK (%d entries)\n' "$line_num"
  fi
  return 0
}

check_branch_policy() {
  # Parse git pre-push stdin to check if any remote-ref targets main or master
  # Format: <local-ref> <local-sha> <remote-ref> <remote-sha>
  # This catches attempts like: git push origin HEAD:main (even from feature branch)
  while IFS=' ' read -r local_ref local_sha remote_ref remote_sha; do
    # Skip empty lines
    if [ -z "$remote_ref" ]; then
      continue
    fi

    # Block if attempting to push to main or master
    if [ "$remote_ref" = "refs/heads/main" ] || [ "$remote_ref" = "refs/heads/master" ]; then
      return 1
    fi
  done

  # If no protected branch in stdin, also check current branch as fallback
  # (for safety, in case stdin is empty or hook runs without git pre-push)
  local current_branch
  current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

  if [ "$current_branch" = "main" ] || [ "$current_branch" = "master" ]; then
    return 1
  fi

  return 0
}

check_secret_scan() {
  local scan_bin
  if command -v python >/dev/null 2>&1; then
    scan_bin="python"
  elif command -v python3 >/dev/null 2>&1; then
    scan_bin="python3"
  else
    scan_bin="python"
  fi

  local aesop_root="${AESOP_ROOT:-$HOME/aesop}"
  local scan_script="$aesop_root/tools/secret_scan.py"

  if [ ! -f "$scan_script" ]; then
    # Scanner not found: log event and warn to stderr, but don't block (fail-open)
    log_event "secret_scan_unavailable"
    printf 'Warning: secret_scan.py not found at %s\n' "$scan_script" >&2
    return 0
  fi

  # Run scanner and capture output; surface ALLOWED-DOC lines to stderr for visibility
  local scan_output
  scan_output=$("$scan_bin" "$scan_script" --staged 2>&1)
  local exit_code=$?

  # Surface all output including ALLOWED-DOC findings to stderr
  if [ -n "$scan_output" ]; then
    printf '%s\n' "$scan_output" >&2
  fi

  return $exit_code
}

log_event() {
  local event_type="$1"
  local aesop_root="${AESOP_ROOT:-$HOME/aesop}"
  local state_dir="$aesop_root/state"
  local audit_log="$state_dir/SECURITY-AUDIT.log"
  local ts
  ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  local repo_name
  repo_name=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || echo 'unknown')")
  local user
  user=$(git config user.name 2>/dev/null || echo "unknown")
  local prev_hash
  prev_hash=$(get_previous_hash "$audit_log")

  mkdir -p "$state_dir" 2>/dev/null

  printf '{"prev_hash":"%s","ts":"%s","repo":"%s","event":"%s","user":"%s"}\n' "$prev_hash" "$ts" "$repo_name" "$(json_escape "$event_type")" "$(json_escape "$user")" >> "$audit_log" 2>/dev/null
}

log_block() {
  local reason="$1"
  local aesop_root="${AESOP_ROOT:-$HOME/aesop}"
  local state_dir="$aesop_root/state"
  local audit_log="$state_dir/SECURITY-AUDIT.log"
  local ts
  ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  local repo_name
  repo_name=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || echo 'unknown')")
  local user
  user=$(git config user.name 2>/dev/null || echo "unknown")
  local prev_hash
  prev_hash=$(get_previous_hash "$audit_log")

  mkdir -p "$state_dir" 2>/dev/null

  printf '{"prev_hash":"%s","ts":"%s","repo":"%s","event":"push_blocked","reason":"%s","user":"%s"}\n' "$prev_hash" "$ts" "$repo_name" "$(json_escape "$reason")" "$(json_escape "$user")" >> "$audit_log" 2>/dev/null
}

run_test_mode() {
  local test_passed=0
  local test_failed=0
  local tmpdir
  tmpdir=$(mktemp -d)
  trap "rm -rf '$tmpdir'" EXIT

  printf '\n=== Test 1: Branch policy check ===\n'
  (
    cd "$tmpdir" || exit 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    echo "dummy" > file.txt
    git add file.txt
    git commit -q -m "initial"
    git checkout -q -b main 2>/dev/null || git branch -M main

    if check_branch_policy; then
      printf 'FAIL: Should have blocked on main branch\n'
      exit 1
    fi
    printf 'PASS: Correctly blocked on main branch\n'
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 2: Branch policy allows feature branches ===\n'
  (
    cd "$tmpdir" || exit 1
    git checkout -q -b feature/test 2>/dev/null

    if check_branch_policy; then
      printf 'PASS: Correctly allowed feature branch\n'
    else
      printf 'FAIL: Should have allowed feature branch\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 3: Audit log format ===\n'
  (
    export AESOP_ROOT="$tmpdir/aesop"
    mkdir -p "$AESOP_ROOT/state"
    log_block "test_reason"

    if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
      printf 'FAIL: Audit log not created\n'
      exit 1
    fi

    audit_line=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")
    if ! printf '%s' "$audit_line" | python3 -m json.tool >/dev/null 2>&1; then
      printf 'FAIL: Audit log entry is not valid JSON\n'
      printf 'Entry: %s\n' "$audit_line"
      exit 1
    fi

    if printf '%s' "$audit_line" | grep -q '"event":"push_blocked"'; then
      printf 'PASS: Audit log entry valid JSON with correct event type\n'
    else
      printf 'FAIL: Audit log entry missing correct event\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 4: JSON escaping with special characters ===\n'
  (
    export AESOP_ROOT="$tmpdir/aesop"
    mkdir -p "$AESOP_ROOT/state"
    git config user.name 'John "Jack" Doe'
    log_block "reason_with_backslash\\test"

    if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
      printf 'FAIL: Audit log not created for special chars test\n'
      exit 1
    fi

    audit_line=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")
    if ! printf '%s' "$audit_line" | python3 -m json.tool >/dev/null 2>&1; then
      printf 'FAIL: JSON with escaped chars is invalid\n'
      printf 'Entry: %s\n' "$audit_line"
      exit 1
    fi

    if printf '%s' "$audit_line" | grep -q 'John.*Jack.*Doe'; then
      printf 'PASS: JSON correctly escapes quotes in user names\n'
    else
      printf 'FAIL: JSON escaping incomplete\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 5: stdin handling (git hook compatibility) ===\n'
  (
    cd "$tmpdir" || exit 1
    git checkout -q feature/test 2>/dev/null

    # Simulate git pre-push stdin with ref info
    local_sha=$(git rev-parse HEAD 2>/dev/null || echo "0000000")
    printf '%s\n' "refs/heads/feature/test $local_sha refs/heads/feature/test 0000000000000000000000000000000000000000" | {
      if check_branch_policy >/dev/null 2>&1; then
        printf 'PASS: Hook accepts stdin without choking\n'
      else
        printf 'FAIL: Hook failed with stdin input\n'
        exit 1
      fi
    }
  ) || {
    printf 'FAIL: stdin test exited with error\n'
    test_failed=$((test_failed + 1))
  }
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  fi

  printf '\n=== Test 6: stdin refspec bypass detection (HEAD:main) ===\n'
  (
    cd "$tmpdir" || exit 1
    git checkout -q feature/test 2>/dev/null || git checkout -q -b feature/bypass_test 2>/dev/null

    # Simulate git pre-push stdin for: git push origin HEAD:main
    # This is an explicit refspec that pushes to main even though local HEAD is feature/test
    # The fixed check_branch_policy MUST block this by checking remote-ref in stdin
    local_sha=$(git rev-parse HEAD 2>/dev/null || echo "0000000")
    remote_main_sha="0000000000000000000000000000000000000000"

    # Stdin format: <local-ref> <local-sha> <remote-ref> <remote-sha>
    # For "git push origin HEAD:main": refs/heads/feature/test <sha> refs/heads/main 0000...
    printf '%s\n' "refs/heads/feature/test $local_sha refs/heads/main $remote_main_sha" | {
      if check_branch_policy >/dev/null 2>&1; then
        printf 'FAIL: Should have blocked push to main via stdin refspec\n'
        exit 1
      else
        printf 'PASS: Correctly blocked push to main via stdin refspec\n'
      fi
    }
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 7: Secret scan unavailable logs audit event ===\n'
  (
    export AESOP_ROOT="$tmpdir/aesop_no_scanner"
    mkdir -p "$AESOP_ROOT/state"

    # Capture stderr to verify warning is printed
    stderr_output=$( { check_secret_scan; } 2>&1 1>/dev/null )
    exit_code=$?

    # Should return 0 (fail-open)
    if [ "$exit_code" -ne 0 ]; then
      printf 'FAIL: check_secret_scan should return 0 when scanner missing (fail-open)\n'
      exit 1
    fi

    # Should have logged a "secret_scan_unavailable" event
    if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
      printf 'FAIL: Audit log not created when scanner is unavailable\n'
      exit 1
    fi

    audit_line=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")

    # Verify JSON is valid
    if ! printf '%s' "$audit_line" | python3 -m json.tool >/dev/null 2>&1; then
      printf 'FAIL: Audit log entry is not valid JSON\n'
      printf 'Entry: %s\n' "$audit_line"
      exit 1
    fi

    # Verify event type is "secret_scan_unavailable"
    if ! printf '%s' "$audit_line" | grep -q '"event":"secret_scan_unavailable"'; then
      printf 'FAIL: Audit log entry missing correct event type\n'
      printf 'Expected event: "secret_scan_unavailable"\n'
      printf 'Entry: %s\n' "$audit_line"
      exit 1
    fi

    # Verify a warning was printed to stderr
    if ! printf '%s' "$stderr_output" | grep -q -i 'unavailable\|missing\|not found'; then
      printf 'FAIL: No warning message printed to stderr\n'
      printf 'stderr was: %s\n' "$stderr_output"
      exit 1
    fi

    printf 'PASS: Secret scan unavailable logged with event and stderr warning\n'
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 8: Hash-chain audit log (GENESIS first event) ===\n'
  (
    export AESOP_ROOT="$tmpdir/aesop_hashchain"
    mkdir -p "$AESOP_ROOT/state"
    log_block "test_block_1"

    if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
      printf 'FAIL: Audit log not created\n'
      exit 1
    fi

    audit_line=$(tail -n 1 "$AESOP_ROOT/state/SECURITY-AUDIT.log")
    if ! printf '%s' "$audit_line" | grep -q '"prev_hash":"GENESIS"'; then
      printf 'FAIL: First event should have prev_hash=GENESIS\n'
      printf 'Entry: %s\n' "$audit_line"
      exit 1
    fi

    if ! printf '%s' "$audit_line" | python3 -m json.tool >/dev/null 2>&1; then
      printf 'FAIL: Hash-chained entry is not valid JSON\n'
      printf 'Entry: %s\n' "$audit_line"
      exit 1
    fi

    printf 'PASS: First event has GENESIS prev_hash and valid JSON\n'
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 9: Hash-chain builds across 2+ events ===\n'
  (
    export AESOP_ROOT="$tmpdir/aesop_hashchain2"
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

    line1_hash=$(printf '%s' "$line1" | tr -d '\n' | sha256sum | awk '{print $1}')
    line2_prev=$(printf '%s' "$line2" | python3 -c "import sys, json; print(json.load(sys.stdin).get('prev_hash', ''))")

    if [ "$line1_hash" != "$line2_prev" ]; then
      printf 'FAIL: Second event prev_hash does not match first line hash\n'
      printf 'Expected: %s\n' "$line1_hash"
      printf 'Got: %s\n' "$line2_prev"
      exit 1
    fi

    printf 'PASS: Hash chain builds correctly across 2 events\n'
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 10: verify-audit-log passes on intact chain ===\n'
  (
    export AESOP_ROOT="$tmpdir/aesop_verify"
    mkdir -p "$AESOP_ROOT/state"
    log_block "entry_1"
    log_block "entry_2"
    log_event "entry_3"

    if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
      printf 'FAIL: Audit log not created\n'
      exit 1
    fi

    if verify_audit_log "$AESOP_ROOT/state/SECURITY-AUDIT.log" >/dev/null 2>&1; then
      printf 'PASS: Verification passed on intact chain\n'
    else
      printf 'FAIL: Verification should pass on intact chain\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 11: verify-audit-log detects tampered line ===\n'
  (
    export AESOP_ROOT="$tmpdir/aesop_tamper"
    mkdir -p "$AESOP_ROOT/state"
    log_block "entry_1"
    log_block "entry_2"
    log_block "entry_3"

    if [ ! -f "$AESOP_ROOT/state/SECURITY-AUDIT.log" ]; then
      printf 'FAIL: Audit log not created\n'
      exit 1
    fi

    sed -i '2s/"reason":"[^"]*"/"reason":"TAMPERED"/g' "$AESOP_ROOT/state/SECURITY-AUDIT.log"

    if ! verify_audit_log "$AESOP_ROOT/state/SECURITY-AUDIT.log" >/dev/null 2>&1; then
      printf 'PASS: Verification detected tampered middle line\n'
    else
      printf 'FAIL: Verification should detect tampering\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test Results ===\n'
  printf 'PASSED: %d\n' "$test_passed"
  printf 'FAILED: %d\n' "$test_failed"

  if [ "$test_failed" -eq 0 ]; then
    printf '\nAll 11 tests passed.\n'
    return 0
  else
    printf '\nSome tests failed.\n'
    return 1
  fi
}

main() {
  if [ "${1:-}" = "--test" ]; then
    run_test_mode
    exit $?
  fi

  if [ "${1:-}" = "--verify-audit-log" ]; then
    local audit_log="${2:-${AESOP_ROOT:-$HOME/aesop}/state/SECURITY-AUDIT.log}"
    verify_audit_log "$audit_log"
    exit $?
  fi

  # git pre-push provides ref info on stdin, pass it to check_branch_policy
  if ! check_branch_policy; then
    printf 'Error: Push to main/master is blocked by policy\n' >&2
    log_block "push_to_protected_branch"
    exit 1
  fi

  if ! check_secret_scan; then
    printf 'Error: Secret scan failed. Push blocked.\n' >&2
    log_block "secret_scan_failure"
    exit 1
  fi

  exit 0
}

main "$@"
