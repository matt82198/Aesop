#!/bin/bash
# TDD test for run-watchdog.sh empty/corrupt lock timestamp handling (P3 hardening)
# Ensures that an empty lock timestamp file is detected, logged, and treated as stale
#
# HERMETIC: like test-run-watchdog.sh, uses a throwaway AESOP_ROOT fixture
# (mktemp -d), never touching the real project checkout. REPO_ROOT is used ONLY
# to locate the script under test.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR=$(mktemp -d)
AESOP_ROOT="${TMP_DIR}"
TEST_STATE_DIR="${TMP_DIR}/state"
CYCLE_COUNTER="${TMP_DIR}/cycle-counter"

# Cleanup on exit
trap "rm -rf ${TMP_DIR}" EXIT

# Setup
mkdir -p "${TEST_STATE_DIR}"
echo "0" > "${CYCLE_COUNTER}"

# Mock cycle script that increments a counter
MOCK_CYCLE="${TMP_DIR}/mock-cycle.sh"
cat > "${MOCK_CYCLE}" << 'EOFMOCK'
#!/bin/bash
COUNTER_FILE="$1"
if [ -z "$COUNTER_FILE" ]; then
  echo "Usage: mock-cycle.sh <counter-file>" >&2
  exit 1
fi
COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
echo $((COUNT + 1)) > "$COUNTER_FILE"
echo "[mock-cycle] Counter incremented to $((COUNT + 1))"
EOFMOCK
chmod +x "${MOCK_CYCLE}"

echo "=== Test: Empty lock timestamp file triggers stale reclaim (P3 hardening) ==="

# Create lock dir with an EMPTY timestamp file and a valid PID
LOCK_DIR="${TEST_STATE_DIR}/.watchdog-lock"
mkdir -p "$LOCK_DIR"
# Write empty timestamp file (no content) — this is the bug scenario
touch "$LOCK_DIR/timestamp"
# Write a fake PID for completeness
echo "9999" > "$LOCK_DIR/pid"

echo "Created lock with empty timestamp file:"
ls -la "$LOCK_DIR"
echo "Timestamp file content: '$(cat "$LOCK_DIR/timestamp")'"

# Run watchdog with the empty timestamp lock present
OUT=$(mktemp)
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${REPO_ROOT}/daemons/run-watchdog.sh" --once > "$OUT" 2>&1
EXIT_CODE=$?

CYCLE_RUN_COUNT=$(cat "${CYCLE_COUNTER}")
echo "Exit code: $EXIT_CODE"
echo "Cycle run count: $CYCLE_RUN_COUNT"
echo "Output:"
cat "$OUT"
echo ""

# Assertion 1: Cycle should have run (lock was reclaimed)
if [ "$CYCLE_RUN_COUNT" != "1" ]; then
  echo "FAIL: Expected cycle to run (lock reclaimed), but count=$CYCLE_RUN_COUNT"
  exit 1
fi
echo "PASS: Cycle ran (empty timestamp lock was reclaimed)"

# Assertion 2: Log message must appear reporting empty/corrupt timestamp
if ! grep -q "empty/corrupt lock timestamp" "$OUT" 2>/dev/null; then
  echo "FAIL: Expected 'empty/corrupt lock timestamp' message in output, but not found"
  echo "Full output was:"
  cat "$OUT"
  exit 1
fi
echo "PASS: 'empty/corrupt lock timestamp — treating lock as stale' message appeared"

# Assertion 3: Reclaim message should also appear
if ! grep -q "reclaimed" "$OUT" 2>/dev/null; then
  echo "FAIL: Expected 'reclaimed' message in output, but not found"
  exit 1
fi
echo "PASS: Lock reclaim message appeared"

rm -f "$OUT"

echo ""
echo "=== Test: Empty timestamp in Case 2 (pid file missing, timestamp empty) ==="

# Clean state
rm -rf "${TEST_STATE_DIR}"
mkdir -p "${TEST_STATE_DIR}"
echo "0" > "${CYCLE_COUNTER}"

# Create lock dir with ONLY an empty timestamp file (no pid)
LOCK_DIR="${TEST_STATE_DIR}/.watchdog-lock"
mkdir -p "$LOCK_DIR"
touch "$LOCK_DIR/timestamp"
# No pid file — this tests the Case 2 branch

echo "Created lock with empty timestamp (no pid file):"
ls -la "$LOCK_DIR"

OUT2=$(mktemp)
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${REPO_ROOT}/daemons/run-watchdog.sh" --once > "$OUT2" 2>&1
EXIT_CODE2=$?

CYCLE_RUN_COUNT=$(cat "${CYCLE_COUNTER}")
echo "Exit code: $EXIT_CODE2"
echo "Cycle run count: $CYCLE_RUN_COUNT"
echo "Output:"
cat "$OUT2"
echo ""

# Assertion 1: Cycle should have run
if [ "$CYCLE_RUN_COUNT" != "1" ]; then
  echo "FAIL: Expected cycle to run in Case 2, but count=$CYCLE_RUN_COUNT"
  exit 1
fi
echo "PASS: Cycle ran (empty timestamp in Case 2 was treated as stale)"

# Assertion 2: Log message should appear
if ! grep -q "empty/corrupt lock timestamp" "$OUT2" 2>/dev/null; then
  echo "FAIL: Expected 'empty/corrupt lock timestamp' message in Case 2 output, but not found"
  exit 1
fi
echo "PASS: 'empty/corrupt lock timestamp' message appeared in Case 2"

rm -f "$OUT2"

echo ""
echo "=== All empty/corrupt timestamp tests passed ==="
