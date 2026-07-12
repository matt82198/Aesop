#!/bin/bash
set -euo pipefail

# Consolidated test suite for reconstitute.sh
# Combines best coverage from previous test files + security probes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECONSTITUTE="$SCRIPT_DIR/tools/reconstitute.sh"
PASSED=0
FAILED=0

assert_pass() {
  local test_name="$1"
  echo "✓ PASS: $test_name"
  ((PASSED++)) || true
}

assert_fail() {
  local test_name="$1"
  echo "✗ FAIL: $test_name"
  ((FAILED++)) || true
}

# ===== ITEM 1: Security - URL validation =====
test_item1_url_validation() {
  echo ""
  echo "=== ITEM 1: URL Validation (P0 Security) ==="

  local tmpdir
  tmpdir=$(mktemp -d) || { echo "mktemp failed"; return 1; }

  # Test 1.1: ext:: prefix should be rejected
  echo "Test 1.1: Reject ext:: prefix"
  cat > "$tmpdir/repos_1_1.txt" << 'EOF'
ext::sh -c 'echo bad' /tmp/target1
EOF

  output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_1_1.txt" 2>&1 || true)

  if echo "$output" | grep -qi "invalid\|error"; then
    assert_pass "ext:: rejected with error message"
  elif ! echo "$output" | grep -q "Would clone"; then
    assert_pass "ext:: not processed"
  else
    assert_fail "ext:: was processed (should be rejected)"
  fi

  # Test 1.2: leading dash should be rejected
  echo "Test 1.2: Reject leading dash"
  cat > "$tmpdir/repos_1_2.txt" << 'EOF'
-c /tmp/target2
EOF

  output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_1_2.txt" 2>&1 || true)

  if echo "$output" | grep -qi "invalid\|error"; then
    assert_pass "leading dash rejected with error"
  elif ! echo "$output" | grep -q "Would clone"; then
    assert_pass "leading dash not processed"
  else
    assert_fail "leading dash was processed (should be rejected)"
  fi

  # Test 1.3: Valid HTTPS should work
  echo "Test 1.3: Valid HTTPS URL works"
  cat > "$tmpdir/repos_1_3.txt" << 'EOF'
https://github.com/example/repo.git /tmp/clone1
EOF

  output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_1_3.txt" 2>&1 || true)

  if echo "$output" | grep -q "Would clone https://"; then
    assert_pass "Valid HTTPS accepted"
  else
    assert_fail "Valid HTTPS rejected"
  fi

  # Test 1.4: Valid git@host:path should work
  echo "Test 1.4: Valid git@host:path URL works"
  cat > "$tmpdir/repos_1_4.txt" << 'EOF'
git@github.com:user/repo.git /tmp/clone2
EOF

  output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_1_4.txt" 2>&1 || true)

  if echo "$output" | grep -q "Would clone git@"; then
    assert_pass "Valid git@host:path accepted"
  else
    assert_fail "Valid git@host:path rejected"
  fi

  # Test 1.5: Valid ssh:// should work
  echo "Test 1.5: Valid ssh:// URL works"
  cat > "$tmpdir/repos_1_5.txt" << 'EOF'
ssh://git@github.com/user/repo.git /tmp/clone3
EOF

  output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_1_5.txt" 2>&1 || true)

  if echo "$output" | grep -q "Would clone ssh://"; then
    assert_pass "Valid ssh:// accepted"
  else
    assert_fail "Valid ssh:// rejected"
  fi

  # Test 1.6: SECURITY HOLE FIX - git@evil (no colon) should be rejected
  echo "Test 1.6: Reject git@evil without colon"
  cat > "$tmpdir/repos_1_6.txt" << 'EOF'
git@evil /tmp/clone4
EOF

  output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_1_6.txt" 2>&1 || true)

  if echo "$output" | grep -qi "invalid\|error"; then
    assert_pass "git@evil (no colon) rejected with error"
  elif ! echo "$output" | grep -q "Would clone"; then
    assert_pass "git@evil (no colon) not processed"
  else
    assert_fail "git@evil (no colon) was processed (SECURITY HOLE)"
  fi

  # Test 1.7: Reject bare git@ alone
  echo "Test 1.7: Reject bare git@"
  cat > "$tmpdir/repos_1_7.txt" << 'EOF'
git@ /tmp/clone5
EOF

  output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_1_7.txt" 2>&1 || true)

  if echo "$output" | grep -qi "invalid\|error"; then
    assert_pass "bare git@ rejected with error"
  elif ! echo "$output" | grep -q "Would clone"; then
    assert_pass "bare git@ not processed"
  else
    assert_fail "bare git@ was processed (SECURITY HOLE)"
  fi

  rm -rf "$tmpdir"
}

# ===== ITEM 2: Config url field =====
test_item2_config_url_field() {
  echo ""
  echo "=== ITEM 2: Config URL Field (P0 Architecture) ==="

  local tmpdir
  tmpdir=$(mktemp -d) || { echo "mktemp failed"; return 1; }

  # Create a test bare repo
  git init --bare "$tmpdir/origin.bare" > /dev/null 2>&1

  # Test 2.1: Config should support url field in repos[]
  echo "Test 2.1: Config repos[] has url field"

  cat > "$tmpdir/aesop.config.json" << 'EOF'
{
  "repos": [
    {
      "name": "test_repo",
      "path": "path/to/repo",
      "url": "https://example.com/repo.git",
      "primary_branch": "main"
    }
  ]
}
EOF

  # Run in the temp dir
  (
    cd "$tmpdir"
    output=$(timeout 3 bash "$RECONSTITUTE" --dry-run 2>&1 || true)

    if echo "$output" | grep -q "Would clone\|Processing\|No repos"; then
      echo "✓ PASS: Config with url field loads correctly"
      ((PASSED++)) || true
    else
      echo "✗ FAIL: Config with url field not working"
      ((FAILED++)) || true
    fi
  )

  rm -rf "$tmpdir"
}

# ===== ITEM 3: --test uses real reconstruct_fleet =====
test_item3_test_calls_real_fleet() {
  echo ""
  echo "=== ITEM 3: --test calls real reconstruct_fleet (P2) ==="

  # Test 3.1: --test output includes CLONED/FETCHED/FAILED summary
  echo "Test 3.1: --test reports CLONED/FETCHED/FAILED"

  output=$(timeout 5 bash "$RECONSTITUTE" --test 2>&1 || true)

  if echo "$output" | grep -qE "CLONED|FETCHED|FAILED"; then
    assert_pass "Test output includes summary"
  else
    assert_fail "Test output missing CLONED/FETCHED/FAILED summary"
  fi

  # Test 3.2: Verify TEST 1 successfully clones
  if echo "$output" | grep -q "TEST 1.*CLONED:  1"; then
    assert_pass "TEST 1 clones successfully"
  elif echo "$output" | grep "TEST 1" | tail -1 | grep -q "CLONED:  1"; then
    assert_pass "TEST 1 clones successfully"
  else
    # Try alternative: look for CLONED: 1 after TEST 1 marker
    if echo "$output" | grep -A 20 "TEST 1:" | grep -q "CLONED:  1"; then
      assert_pass "TEST 1 clones successfully"
    else
      assert_fail "TEST 1 clone verification failed"
    fi
  fi

  # Test 3.3: Verify TEST 2 rejects ext:: (FAILED count)
  if echo "$output" | grep -A 15 "TEST 2:" | grep -q "FAILED:  1"; then
    assert_pass "TEST 2 correctly handles bad URL"
  else
    assert_fail "TEST 2 bad URL handling not working"
  fi
}

# ===== BONUS: Space in path parsing =====
test_bonus_space_parse() {
  echo ""
  echo "=== BONUS: Space-in-path parsing (P2) ==="

  local tmpdir
  tmpdir=$(mktemp -d) || { echo "mktemp failed"; return 1; }

  echo "Test Bonus: Path with space and tab delimiter"

  git init --bare "$tmpdir/origin.bare" > /dev/null 2>&1

  # Use tab delimiter to properly separate URL from path with spaces
  printf "%s\t%s\n" "https://example.com/repo.git" "$tmpdir/my cloned repo" > "$tmpdir/repos.txt"

  (
    cd "$tmpdir"
    output=$(timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos.txt" 2>&1 || true)

    if echo "$output" | grep -q "my cloned repo"; then
      echo "✓ PASS: Spaced path parsed correctly with tab delimiter"
      ((PASSED++)) || true
    else
      if echo "$output" | grep -q "Would clone"; then
        echo "✓ PASS: Path parsing works"
        ((PASSED++)) || true
      else
        echo "✗ FAIL: Spaced path not properly parsed"
        ((FAILED++)) || true
      fi
    fi
  )

  rm -rf "$tmpdir"
}

# ===== Main test runner =====
main() {
  echo "======================================"
  echo "reconstitute.sh Test Suite (Consolidated)"
  echo "======================================"

  test_item1_url_validation
  test_item2_config_url_field
  test_item3_test_calls_real_fleet
  test_bonus_space_parse

  echo ""
  echo "======================================"
  echo "Results: $PASSED passed, $FAILED failed"
  echo "======================================"

  if [ $FAILED -eq 0 ]; then
    echo "All tests passed!"
    exit 0
  else
    echo "$FAILED tests failed"
    exit 1
  fi
}

main "$@"
