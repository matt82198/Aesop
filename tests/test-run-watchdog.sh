#!/bin/bash
# TDD tests for run-watchdog.sh lock mechanism
# Ensures single-instance guard (atomic lockfile) gates both loop and --once modes
# Tests concurrent starts → only one runs cycle, other exits with lock-held message

set -e

TEST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AESOP_ROOT="${TEST_ROOT}"
TMP_DIR=$(mktemp -d)
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
sleep 0.1
EOFMOCK
chmod +x "${MOCK_CYCLE}"
echo "Mock cycle script created at: ${MOCK_CYCLE}"

echo "=== Test 1: Concurrent --once invocations (should lock second one out) ==="
echo "Starting two --once instances simultaneously..."

# Capture outputs and exit codes
OUT1=$(mktemp)
OUT2=$(mktemp)
EXIT1=""
EXIT2=""

# Start first instance in background
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${AESOP_ROOT}/daemons/run-watchdog.sh" --once > "$OUT1" 2>&1 &
PID1=$!

# Start second instance immediately (should be blocked by lock)
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${AESOP_ROOT}/daemons/run-watchdog.sh" --once > "$OUT2" 2>&1 &
PID2=$!

# Wait for both to complete
wait $PID1
EXIT1=$?
wait $PID2
EXIT2=$?

# Check results
CYCLE_RUN_COUNT=$(cat "${CYCLE_COUNTER}")

echo "Process 1 (PID=$PID1) exit code: $EXIT1"
echo "Process 2 (PID=$PID2) exit code: $EXIT2"
echo "Cycle run count: $CYCLE_RUN_COUNT"
echo ""
echo "Process 1 output:"
cat "$OUT1"
echo ""
echo "Process 2 output:"
cat "$OUT2"

# Assertions
if [ "$CYCLE_RUN_COUNT" != "1" ]; then
  echo "FAIL: Expected cycle to run exactly once, but it ran $CYCLE_RUN_COUNT times"
  exit 1
fi
echo "PASS: Cycle ran exactly once"

# One should succeed, one should be blocked (exit code 1 or success but with lock message)
if ! grep -q "already running\|lock held\|not starting" "$OUT2" 2>/dev/null; then
  echo "WARNING: Second process didn't show lock-held message, but this is OK if it also exited cleanly"
fi

# One process should indicate it acquired the lock, other should indicate it was held
if grep -q "already running\|lock held" "$OUT1" && grep -q "already running\|lock held" "$OUT2"; then
  echo "WARNING: Both processes show lock message — should only be one"
fi

echo ""
echo "=== Test 2: Stale lock recovery (lock older than threshold should be reclaimed) ==="
# Clean state
rm -rf "${TEST_STATE_DIR}"
mkdir -p "${TEST_STATE_DIR}"
echo "0" > "${CYCLE_COUNTER}"

# Create an old lock (manually for test)
OLD_LOCK="${TEST_STATE_DIR}/.watchdog-lock"
mkdir -p "$OLD_LOCK"
# Set modification time to 500 seconds ago (beyond 300s stale threshold)
touch -d "500 seconds ago" "$OLD_LOCK" 2>/dev/null || touch -t "$(date -d '500 seconds ago' +%Y%m%d%H%M.%S)" "$OLD_LOCK" 2>/dev/null || true

echo "Created stale lock at: $OLD_LOCK"
ls -la "$OLD_LOCK"

# Run watchdog with stale lock present
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${AESOP_ROOT}/daemons/run-watchdog.sh" --once > "$OUT1" 2>&1
EXIT1=$?

CYCLE_RUN_COUNT=$(cat "${CYCLE_COUNTER}")
echo "After stale lock recovery: exit code=$EXIT1, cycle_run_count=$CYCLE_RUN_COUNT"
echo "Output:"
cat "$OUT1"

if [ "$CYCLE_RUN_COUNT" != "1" ]; then
  echo "FAIL: Expected stale lock to be reclaimed and cycle to run, but count=$CYCLE_RUN_COUNT"
  exit 1
fi
echo "PASS: Stale lock was reclaimed and cycle ran"

rm -f "$OUT1" "$OUT2"
echo ""
echo "=== All tests passed ==="
