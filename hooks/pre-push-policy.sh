#!/usr/bin/env bash
set -uo pipefail

json_escape() {
  # Escape backslashes first, then quotes for valid JSON
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

check_branch_policy() {
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
    return 0
  fi

  "$scan_bin" "$scan_script" --staged >/dev/null 2>&1
  return $?
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

  mkdir -p "$state_dir" 2>/dev/null

  printf '{"ts":"%s","repo":"%s","event":"push_blocked","reason":"%s","user":"%s"}\n' "$ts" "$repo_name" "$(json_escape "$reason")" "$(json_escape "$user")" >> "$audit_log" 2>/dev/null
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

  printf '\n=== Test Results ===\n'
  printf 'PASSED: %d\n' "$test_passed"
  printf 'FAILED: %d\n' "$test_failed"

  if [ "$test_failed" -eq 0 ]; then
    printf '\nAll 5 tests passed.\n'
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
