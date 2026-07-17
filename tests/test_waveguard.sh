#!/usr/bin/env bash
set -uo pipefail

run_tests() {
  local test_passed=0
  local test_failed=0
  local tmpdir
  local hooks_dir="$1"
  local install_script="$1/install-waveguard.sh"
  tmpdir=$(mktemp -d)
  trap "rm -rf '$tmpdir'" EXIT

  printf '\n=== Test 1: Commit allowed when marker absent ===\n'
  (
    cd "$tmpdir" || exit 1
    mkdir -p test_repo
    cd test_repo || exit 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    echo "dummy" > file.txt
    git add file.txt

    if git commit -q -m "initial commit"; then
      printf 'PASS: Commit allowed when marker absent\n'
    else
      printf 'FAIL: Commit should succeed when marker absent\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 2: Install hook and verify it exists ===\n'
  (
    cd "$tmpdir/test_repo" || exit 1
    mkdir -p hooks
    cp "$hooks_dir/pre-commit-waveguard.sh" hooks/pre-commit-waveguard.sh
    bash "$install_script" >/dev/null 2>&1

    if [ ! -f ".git/hooks/pre-commit" ]; then
      printf 'FAIL: Hook not installed\n'
      exit 1
    fi

    if [ ! -x ".git/hooks/pre-commit" ]; then
      printf 'FAIL: Hook not executable\n'
      exit 1
    fi

    printf 'PASS: Hook installed and executable\n'
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 3: Commit rejected when marker present ===\n'
  (
    test_repo_3="$tmpdir/test_repo_3"
    mkdir -p "$test_repo_3"
    cd "$test_repo_3" || exit 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    mkdir -p hooks
    cp "$hooks_dir/pre-commit-waveguard.sh" hooks/pre-commit-waveguard.sh
    bash "$install_script" >/dev/null 2>&1

    mkdir -p state
    touch state/.wave-in-flight

    export AESOP_ROOT="$test_repo_3"
    echo "dummy" > file.txt
    git add file.txt
    git commit -q -m "init" || true

    echo "test content" > file2.txt
    git add file2.txt

    if git commit -q -m "test commit with marker"; then
      printf 'FAIL: Commit should be rejected when marker present\n'
      exit 1
    else
      printf 'PASS: Commit rejected when marker present\n'
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 4: Error message is clear ===\n'
  (
    test_repo_4="$tmpdir/test_repo_4"
    mkdir -p "$test_repo_4"
    cd "$test_repo_4" || exit 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    mkdir -p hooks
    cp "$hooks_dir/pre-commit-waveguard.sh" hooks/pre-commit-waveguard.sh
    bash "$install_script" >/dev/null 2>&1

    mkdir -p state
    touch state/.wave-in-flight

    export AESOP_ROOT="$test_repo_4"
    echo "dummy" > file.txt
    git add file.txt
    git commit -q -m "init" || true

    echo "test" > file3.txt
    git add file3.txt

    output=$(git commit -m "test" 2>&1 || true)

    if printf '%s' "$output" | grep -q "Wave in flight"; then
      printf 'PASS: Error message contains expected text\n'
    else
      printf 'FAIL: Error message missing or unclear\n'
      printf 'Output was: %s\n' "$output"
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 5: Commit allowed after marker removed ===\n'
  (
    test_repo_5="$tmpdir/test_repo_5"
    mkdir -p "$test_repo_5"
    cd "$test_repo_5" || exit 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    mkdir -p hooks
    cp "$hooks_dir/pre-commit-waveguard.sh" hooks/pre-commit-waveguard.sh
    bash "$install_script" >/dev/null 2>&1

    mkdir -p state
    touch state/.wave-in-flight

    export AESOP_ROOT="$test_repo_5"
    echo "dummy" > file.txt
    git add file.txt
    git commit -q -m "init" || true

    echo "test" > file4.txt
    git add file4.txt

    git commit -q -m "test" 2>&1 || true

    rm state/.wave-in-flight

    echo "test after marker removed" > file5.txt
    git add file5.txt

    if git commit -q -m "test after marker removed"; then
      printf 'PASS: Commit allowed after marker removed\n'
    else
      printf 'FAIL: Commit should succeed after marker removed\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 6: Installer idempotency (can run multiple times) ===\n'
  (
    test_repo_6="$tmpdir/test_repo_6"
    mkdir -p "$test_repo_6"
    cd "$test_repo_6" || exit 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    mkdir -p hooks
    cp "$hooks_dir/pre-commit-waveguard.sh" hooks/pre-commit-waveguard.sh

    bash "$install_script" >/dev/null 2>&1
    first_install_exit=$?

    bash "$install_script" >/dev/null 2>&1
    second_install_exit=$?

    if [ $first_install_exit -eq 0 ] && [ $second_install_exit -eq 0 ]; then
      printf 'PASS: Installer runs idempotently\n'
    else
      printf 'FAIL: Installer failed on second run\n'
      exit 1
    fi
  )
  if [ $? -eq 0 ]; then
    test_passed=$((test_passed + 1))
  else
    test_failed=$((test_failed + 1))
  fi

  printf '\n=== Test 7: Marker is worktree-relative — a sibling worktree commit is ALLOWED while primary has the marker (wave-24 regression) ===\n'
  (
    # Primary repo with the marker set (simulating a wave in flight).
    primary="$tmpdir/wt_primary"
    mkdir -p "$primary"
    cd "$primary" || exit 1
    git init -q
    git config user.email t@t; git config user.name t
    mkdir -p hooks state
    cp "$hooks_dir/pre-commit-waveguard.sh" hooks/pre-commit-waveguard.sh
    echo "seed" > seed.txt && git add . && git commit -q -m seed
    bash "$install_script" >/dev/null 2>&1
    touch state/.wave-in-flight   # wave in flight in the PRIMARY tree

    # Confirm the PRIMARY tree is blocked (marker present in its own toplevel).
    echo p > pfile.txt && git add pfile.txt
    if git commit -q -m "primary during wave" 2>&1; then
      printf 'FAIL: primary-tree commit should be blocked while marker present\n'; exit 1
    fi

    # A sibling WORKTREE does NOT carry the git-ignored marker, so its commit must be ALLOWED
    # even though the primary has one. (The old AESOP_ROOT-hardcoded hook wrongly blocked this —
    # the wave-24 fleet-block incident.)
    wt="$tmpdir/wt_sibling"
    git worktree add -q "$wt" -b sibling 2>/dev/null
    cd "$wt" || exit 1
    echo w > wfile.txt && git add wfile.txt
    if git commit -q -m "sibling worktree during wave" 2>&1; then
      printf 'PASS: sibling-worktree commit allowed while primary marker set\n'
    else
      printf 'FAIL: sibling-worktree commit was wrongly blocked (wave-24 regression)\n'; exit 1
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
    printf '\nAll 7 tests passed.\n'
    return 0
  else
    printf '\nSome tests failed.\n'
    return 1
  fi
}

main() {
  local repo_root
  repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
  if [ -z "$repo_root" ]; then
    printf 'Error: Not in a git repository\n' >&2
    return 1
  fi

  local hooks_dir="$repo_root/hooks"
  if [ ! -f "$hooks_dir/pre-commit-waveguard.sh" ]; then
    printf 'Error: Hook source not found at %s/pre-commit-waveguard.sh\n' "$hooks_dir" >&2
    return 1
  fi

  if [ ! -f "$hooks_dir/install-waveguard.sh" ]; then
    printf 'Error: Installer not found at %s/install-waveguard.sh\n' "$hooks_dir" >&2
    return 1
  fi

  run_tests "$hooks_dir"
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  main "$@"
fi
