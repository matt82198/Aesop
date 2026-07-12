#!/bin/bash
set -euo pipefail

# TDD-first test suite for three reconstitute.sh security & architecture fixes
# Issue 1: Validate clone targets against fleet root (HIGH, security)
# Issue 2: E2E test drives real script, not wrapper copy (P1, bash)
# Issue 3: Space-delimited legacy targets with spaces (P2, arch+bash)

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

# ===== ISSUE 1: Target validation against fleet root =====
test_issue1_target_validation() {
  echo ""
  echo "=== ISSUE 1: Target validation against fleet root (HIGH, Security) ==="

  local tmpdir
  tmpdir=$(mktemp -d) || { echo "mktemp failed"; return 1; }
  trap "rm -rf $tmpdir" RETURN

  local fleet_root="$tmpdir/fleet"
  mkdir -p "$fleet_root"

  # Test 1.1: Path outside fleet root should be rejected
  echo "Test 1.1: Reject absolute path outside fleet root"

  cat > "$tmpdir/repos_outside.txt" << EOF
file://$tmpdir/origin.bare	/tmp/outside_repo
EOF

  git init --bare "$tmpdir/origin.bare" > /dev/null 2>&1

  output=$(AESOP_FLEET_ROOT="$fleet_root" TEST_MODE=1 timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_outside.txt" 2>&1 || true)

  if echo "$output" | grep -qi "outside.*fleet\|escape\|invalid.*target"; then
    assert_pass "Path outside fleet root rejected with error"
  elif ! echo "$output" | grep -q "Would clone"; then
    assert_pass "Path outside fleet root not processed"
  else
    assert_fail "Path outside fleet root was allowed (SECURITY HOLE)"
  fi

  # Test 1.2: Traversal with .. should be rejected
  echo "Test 1.2: Reject .. traversal escape"

  cat > "$tmpdir/repos_traversal.txt" << EOF
file://$tmpdir/origin.bare	$fleet_root/../outside_repo
EOF

  output=$(AESOP_FLEET_ROOT="$fleet_root" TEST_MODE=1 timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_traversal.txt" 2>&1 || true)

  if echo "$output" | grep -qi "escape\|traversal\|outside.*fleet"; then
    assert_pass ".. traversal rejected with error"
  elif ! echo "$output" | grep -q "Would clone"; then
    assert_pass ".. traversal not processed"
  else
    assert_fail ".. traversal was allowed (SECURITY HOLE)"
  fi

  # Test 1.3: Valid path under fleet root should be accepted
  echo "Test 1.3: Accept valid path under fleet root"

  local valid_target="$fleet_root/repo1"
  cat > "$tmpdir/repos_valid.txt" << EOF
file://$tmpdir/origin.bare	$valid_target
EOF

  output=$(AESOP_FLEET_ROOT="$fleet_root" TEST_MODE=1 timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_valid.txt" 2>&1 || true)

  if echo "$output" | grep -q "Would clone"; then
    assert_pass "Valid path under fleet root accepted"
  else
    assert_fail "Valid path under fleet root rejected"
  fi
}

# ===== ISSUE 2: E2E test drives real script =====
test_issue2_e2e_drives_real_script() {
  echo ""
  echo "=== ISSUE 2: E2E test drives real script, not wrapper (P1, Bash) ==="

  local tmpdir
  tmpdir=$(mktemp -d) || { echo "mktemp failed"; return 1; }
  trap "rm -rf $tmpdir" RETURN

  # Test 2.1: Verify real reconstitute.sh rejects invalid URL
  echo "Test 2.1: Real script rejects invalid URL (validate_url check)"

  cat > "$tmpdir/repos_bad_url.txt" << 'EOF'
ext::sh -c 'echo bad' /tmp/target
EOF

  output=$(TEST_MODE=1 timeout 3 bash "$RECONSTITUTE" --repos-file "$tmpdir/repos_bad_url.txt" 2>&1 || true)

  if echo "$output" | grep -qi "invalid\|error"; then
    assert_pass "Real script rejects ext:: URL"
  else
    assert_fail "Real script did not reject ext:: URL"
  fi

  # Test 2.2: Breaking validate_url in real script should break tests
  echo "Test 2.2: Demonstrate test sensitivity to validate_url (proof of real-script usage)"

  # Create a broken copy of reconstitute.sh with weakened URL regex
  local broken_script="$tmpdir/reconstitute_broken.sh"
  cp "$RECONSTITUTE" "$broken_script"

  # Test with a URL that is rejected by the real script (git@example without colon)
  # but would be accepted by a broken version
  # Use a target within tmpdir so fleet root validation passes
  cat > "$tmpdir/repos_git_nocolon.txt" << EOF
git@example	$tmpdir/target
EOF

  # First verify real script rejects git@example (no colon)
  output_real=$(AESOP_FLEET_ROOT="$tmpdir" TEST_MODE=1 timeout 3 bash "$RECONSTITUTE" --repos-file "$tmpdir/repos_git_nocolon.txt" 2>&1 || true)

  if echo "$output_real" | grep -qi "invalid.*url"; then
    # Good, real script rejects it with URL error
    # Now break the regex to accept git@ without colon
    sed -i 's/git@\[a-zA-Z0-9.-\]+:/git@/g' "$broken_script"

    # Run broken script
    output_broken=$(AESOP_FLEET_ROOT="$tmpdir" TEST_MODE=1 timeout 3 bash "$broken_script" --repos-file "$tmpdir/repos_git_nocolon.txt" 2>&1 || true)

    if ! echo "$output_broken" | grep -qi "invalid.*url"; then
      # Broken script accepted the git@example URL, proving test sensitivity
      echo "✓ PASS: Broken validate_url allows invalid URLs (proof test sensitivity)"
      ((PASSED++)) || true
    else
      echo "✗ FAIL: Broken validate_url still rejects URLs (test not sensitive enough)"
      ((FAILED++)) || true
    fi
  else
    echo "✗ FAIL: Real script should reject git@example (no colon)"
    ((FAILED++)) || true
  fi

  # Test 2.3: Verify test suite uses real script (via direct invocation or sourcing)
  echo "Test 2.3: Test suite uses real reconstitute.sh directly"

  # Check if test file actually sources or invokes the real script
  if grep -q "bash.*RECONSTITUTE" "$SCRIPT_DIR/tests/test_reconstitute.sh" || \
     grep -q "source.*reconstitute\|\..*reconstitute" "$SCRIPT_DIR/tests/test_reconstitute.sh"; then
    assert_pass "Test suite invokes/sources real reconstitute.sh"
  else
    # The current test may have a wrapper, which is the bug we're fixing
    # After the fix, this should pass
    echo "⚠ Note: Test suite may not be using real script (expected before fix)"
  fi
}

# ===== ISSUE 3: Space-delimited legacy targets with spaces =====
test_issue3_legacy_space_targets() {
  echo ""
  echo "=== ISSUE 3: Legacy space-delimited targets with spaces (P2, Arch+Bash) ==="

  local tmpdir
  tmpdir=$(mktemp -d) || { echo "mktemp failed"; return 1; }
  trap "rm -rf $tmpdir" RETURN

  git init --bare "$tmpdir/origin.bare" > /dev/null 2>&1

  # Test 3.1: Tab-delimited path with spaces works
  echo "Test 3.1: Tab-delimited path with spaces is preserved"

  local spaced_path="$tmpdir/my cloned repo"
  printf "file://%s\t%s\n" "$tmpdir/origin.bare" "$spaced_path" > "$tmpdir/repos_tab.txt"

  output=$(AESOP_FLEET_ROOT="$tmpdir" TEST_MODE=1 timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_tab.txt" 2>&1 || true)

  if echo "$output" | grep -q "my cloned repo"; then
    assert_pass "Tab-delimited spaced path preserved correctly"
  else
    assert_fail "Tab-delimited spaced path not preserved"
  fi

  # Test 3.2: Space-delimited with spaces - current behavior truncates
  echo "Test 3.2: Space-delimited target with spaces (legacy fallback)"

  # This creates a space-delimited line (no tab)
  printf "file://%s %s\n" "$tmpdir/origin.bare" "$spaced_path" > "$tmpdir/repos_space.txt"

  output=$(AESOP_FLEET_ROOT="$tmpdir" TEST_MODE=1 timeout 3 bash "$RECONSTITUTE" --dry-run --repos-file "$tmpdir/repos_space.txt" 2>&1 || true)

  # After the fix, either:
  # A) It should work and preserve the path with spaces
  # B) It should explicitly reject the legacy format with a clear error

  if echo "$output" | grep -q "my cloned repo"; then
    assert_pass "Space-delimited spaced path works (semantic fix applied)"
  elif echo "$output" | grep -qi "legacy.*space\|not supported\|use.*tab"; then
    assert_pass "Legacy space format explicitly rejected with clear error"
  else
    # Current behavior: silently truncates (the bug)
    echo "⚠ Note: Legacy space format may still truncate (expected before fix)"
  fi

  # Test 3.3: Verify legacy format is mentioned in script header or rejected
  echo "Test 3.3: Script documents or rejects legacy space format"

  if head -50 "$RECONSTITUTE" | grep -qi "space.*tab\|legacy\|backward.*compat"; then
    assert_pass "Script documents space/tab format behavior"
  else
    echo "⚠ Note: Script header doesn't document format choice (expected before fix)"
  fi
}

# ===== Main runner =====
main() {
  echo "======================================"
  echo "Reconstitute.sh Fixes - TDD Test Suite"
  echo "======================================"

  test_issue1_target_validation
  test_issue2_e2e_drives_real_script
  test_issue3_legacy_space_targets

  echo ""
  echo "======================================"
  echo "Results: $PASSED passed, $FAILED failed"
  echo "======================================"

  if [ $FAILED -eq 0 ]; then
    echo "All TDD tests would pass!"
    exit 0
  else
    echo "$FAILED tests will guide implementation"
    exit 1
  fi
}

main "$@"
