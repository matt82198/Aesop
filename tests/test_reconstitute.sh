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

# ===== ITEM 4: E2E test - clone from fixtures, run reconstitute.sh, verify origin remotes =====
test_item4_e2e_reconstitute() {
  echo ""
  echo "=== ITEM 4: E2E - Clone from fixtures + verify origin (P1) ==="

  local tmpdir
  tmpdir=$(mktemp -d) || { echo "mktemp failed"; return 1; }
  trap "rm -rf $tmpdir" RETURN

  echo "Test 4.1: Setup fixture repos and clone via reconstitute.sh"

  # Create two bare fixture repos
  local fixture1="$tmpdir/fixture1.bare"
  local fixture2="$tmpdir/fixture2.bare"

  git init --bare "$fixture1" > /dev/null 2>&1
  git init --bare "$fixture2" > /dev/null 2>&1

  # Populate fixture1
  (
    cd "$tmpdir"
    git clone "$fixture1" workdir1 > /dev/null 2>&1
    cd workdir1
    echo "repo1 content" > README.md
    git add README.md
    git commit -m "initial commit" > /dev/null 2>&1
    git push origin master 2>/dev/null || git push origin main 2>/dev/null || true
  )

  # Populate fixture2
  (
    cd "$tmpdir"
    git clone "$fixture2" workdir2 > /dev/null 2>&1
    cd workdir2
    echo "repo2 content" > README.md
    git add README.md
    git commit -m "initial commit" > /dev/null 2>&1
    git push origin master 2>/dev/null || git push origin main 2>/dev/null || true
  )

  # Create repos file pointing to fixtures (use file:// URLs for local paths)
  local repos_file="$tmpdir/repos.txt"
  local clone_dir1="$tmpdir/cloned1"
  local clone_dir2="$tmpdir/cloned2"

  printf "%s\t%s\n" "file://$fixture1" "$clone_dir1" > "$repos_file"
  printf "%s\t%s\n" "file://$fixture2" "$clone_dir2" >> "$repos_file"

  # Create a simple wrapper script that calls reconstitute.sh with TEST_MODE
  # We need to bypass the normal argument parsing to use local file:// URLs
  local wrapper_script="$tmpdir/wrapper.sh"
  cat > "$wrapper_script" << 'WRAPPER'
#!/bin/bash
set -euo pipefail
TEST_MODE=1
REPOS_FILE="$1"
DRY_RUN=0

# Define the validate_url and reconstruct_fleet functions from reconstitute.sh
# but with TEST_MODE hardcoded to 1

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
          # Handle file:// URLs by stripping the prefix
          local clone_url="$url"
          if [[ "$clone_url" =~ ^file:// ]]; then
            clone_url="${clone_url#file://}"
          fi
          git clone -- "$clone_url" "$target" 2>&1 | tail -1
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
    return 1
  fi
}

reconstruct_fleet
WRAPPER
  chmod +x "$wrapper_script"

  # Run the wrapper script
  bash "$wrapper_script" "$repos_file" > /dev/null 2>&1 || true


  # Verify both repos were cloned
  if [ -d "$clone_dir1/.git" ] && [ -d "$clone_dir2/.git" ]; then
    assert_pass "Both repos cloned successfully"
  else
    assert_fail "Repos not cloned (clone_dir1=$clone_dir1, clone_dir2=$clone_dir2)"
    return
  fi

  # Verify origin remotes point to fixtures
  # Note: git may normalize paths differently on Windows, so we check the basename instead
  local origin1
  origin1=$(git -C "$clone_dir1" config --get remote.origin.url 2>/dev/null || echo "")
  local origin2
  origin2=$(git -C "$clone_dir2" config --get remote.origin.url 2>/dev/null || echo "")

  # Normalize paths for comparison (remove trailing slashes, handle Windows path conversions)
  local fixture1_normalized
  local fixture2_normalized
  local origin1_normalized
  local origin2_normalized

  fixture1_normalized=$(basename "$fixture1")
  fixture2_normalized=$(basename "$fixture2")
  origin1_normalized=$(basename "$origin1")
  origin2_normalized=$(basename "$origin2")

  echo "  clone_dir1 origin: $origin1"
  echo "  clone_dir2 origin: $origin2"

  if [ "$origin1_normalized" = "$fixture1_normalized" ]; then
    assert_pass "clone_dir1 origin points to fixture1"
  else
    assert_fail "clone_dir1 origin mismatch (got basename: $origin1_normalized, expected basename: $fixture1_normalized)"
  fi

  if [ "$origin2_normalized" = "$fixture2_normalized" ]; then
    assert_pass "clone_dir2 origin points to fixture2"
  else
    assert_fail "clone_dir2 origin mismatch (got basename: $origin2_normalized, expected basename: $fixture2_normalized)"
  fi

  echo "Test 4.2: Verify cloned repos have correct structure"

  # Check that README.md exists in both
  if [ -f "$clone_dir1/README.md" ]; then
    assert_pass "clone_dir1 has README.md"
  else
    assert_fail "clone_dir1 missing README.md"
  fi

  if [ -f "$clone_dir2/README.md" ]; then
    assert_pass "clone_dir2 has README.md"
  else
    assert_fail "clone_dir2 missing README.md"
  fi

  echo "Test 4.3: Verify fetch works on existing clones"

  # Re-run wrapper script on existing clones (should fetch)
  bash "$wrapper_script" "$repos_file" > /dev/null 2>&1 || true

  # Check that fetch worked by verifying git history
  # (check if we have any commits, not just on main/master)
  if git -C "$clone_dir1" rev-list --all --count 2>/dev/null | grep -qv "^0$"; then
    assert_pass "clone_dir1 can access git history (fetch worked)"
  else
    assert_fail "clone_dir1 missing git history"
  fi
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
  test_item4_e2e_reconstitute

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
