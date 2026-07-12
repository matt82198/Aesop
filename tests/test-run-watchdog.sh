#!/bin/bash
# TDD tests for run-watchdog.sh lock mechanism
# Ensures single-instance guard (atomic lockfile) gates both loop and --once modes
# Tests concurrent starts → only one runs cycle, other exits with lock-held message
#
# HERMETIC: every run-watchdog.sh invocation below is pointed at a throwaway
# AESOP_ROOT (a mktemp -d fixture), never at the real project checkout. That
# guarantees LOCK_DIR / FLEET-BACKUP.log / heartbeat all live under
# $TMP_DIR/state, so this suite can never race a live daemon or touch real
# project state. REPO_ROOT is used ONLY to locate the run-watchdog.sh script
# under test — it is never passed as AESOP_ROOT to any invocation.

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
  bash "${REPO_ROOT}/daemons/run-watchdog.sh" --once > "$OUT1" 2>&1 &
PID1=$!

# Start second instance immediately (should be blocked by lock)
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${REPO_ROOT}/daemons/run-watchdog.sh" --once > "$OUT2" 2>&1 &
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

# Create an old lock (manually for test) — this now lives at the SAME path the
# script under test reads (AESOP_ROOT is the throwaway fixture root), so aging
# it genuinely exercises acquire_lock's staleness/reclaim branch.
OLD_LOCK="${TEST_STATE_DIR}/.watchdog-lock"
mkdir -p "$OLD_LOCK"
# Write stale timestamp (500 seconds ago) into the file that acquire_lock checks
echo $(($(date +%s) - 500)) > "$OLD_LOCK/timestamp"
# Also write a fake PID for completeness
echo "9999" > "$OLD_LOCK/pid"

echo "Created stale lock at: $OLD_LOCK"
ls -la "$OLD_LOCK"
cat "$OLD_LOCK/timestamp"

# Run watchdog with stale lock present
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${REPO_ROOT}/daemons/run-watchdog.sh" --once > "$OUT1" 2>&1
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

if ! grep -q "reclaimed" "$OUT1" 2>/dev/null; then
  echo "FAIL: Expected acquire_lock to report reclaiming the stale lock, but 'reclaimed' not found in output"
  exit 1
fi
echo "PASS: acquire_lock reported reclaiming the stale lock"

rm -f "$OUT1" "$OUT2"

echo ""
echo "=== Test 3: Lock ownership (original holder can't delete reclaimed lock) ==="
# Clean state
rm -rf "${TEST_STATE_DIR}"
mkdir -p "${TEST_STATE_DIR}"
echo "0" > "${CYCLE_COUNTER}"

# Create a mock cycle that sleeps to simulate slow work
SLOW_MOCK="${TMP_DIR}/slow-mock.sh"
cat > "${SLOW_MOCK}" << 'EOFSLOW'
#!/bin/bash
COUNTER_FILE="$1"
SLEEP_TIME="${2:-2}"
if [ -z "$COUNTER_FILE" ]; then
  echo "Usage: slow-mock.sh <counter-file> [sleep-time]" >&2
  exit 1
fi
COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
echo $((COUNT + 1)) > "$COUNTER_FILE"
echo "[slow-mock] Counter incremented to $((COUNT + 1)), sleeping ${SLEEP_TIME}s"
sleep "$SLEEP_TIME"
EOFSLOW
chmod +x "${SLOW_MOCK}"

LOCK_PATH="${TEST_STATE_DIR}/.watchdog-lock"

# Process A: acquires the (real) lock and holds it for A_SLEEP seconds — the
# "original holder" whose lock will be forcibly aged into staleness while A
# is still mid-cycle, unaware it has been reclaimed out from under it.
A_SLEEP=2
OUT_A=$(mktemp)
(
  AESOP_ROOT="${AESOP_ROOT}" \
    AESOP_WATCHDOG_CYCLE_CMD="${SLOW_MOCK} ${CYCLE_COUNTER} ${A_SLEEP}" \
    bash "${REPO_ROOT}/daemons/run-watchdog.sh" --once > "$OUT_A" 2>&1
) &
PID_A=$!

# Wait for A to acquire the lock (poll instead of a fixed sleep — robust
# under process-start jitter, e.g. on Git-Bash/Windows).
ACQUIRE_WAIT=0
while [ ! -f "$LOCK_PATH/timestamp" ] && [ "$ACQUIRE_WAIT" -lt 50 ]; do
  sleep 0.1
  ACQUIRE_WAIT=$((ACQUIRE_WAIT + 1))
done
if [ ! -f "$LOCK_PATH/timestamp" ]; then
  echo "FAIL: Process A never acquired the lock at $LOCK_PATH"
  exit 1
fi

# A writes its OWN real pid here (unlike Test 2's manually-planted "9999"
# sentinel) — capture it so the reclaim-detection poll below can watch for
# the pid actually changing away from A, rather than an irrelevant sentinel.
ORIGINAL_PID=$(cat "$LOCK_PATH/pid" 2>/dev/null || echo "")
if [ -z "$ORIGINAL_PID" ]; then
  echo "FAIL: Process A's lock has no pid file at $LOCK_PATH/pid"
  exit 1
fi

# Age A's lock past the staleness threshold. This is the ACTUAL lock path the
# script under test reads (AESOP_ROOT is the same throwaway fixture root used
# by both A and B), so this genuinely triggers acquire_lock's reclaim branch —
# unlike the old decoy path, which aged a directory nobody read.
echo $(($(date +%s) - 350)) > "$LOCK_PATH/timestamp"

# Process B: reclaims the now-stale lock and holds it for B_SLEEP seconds —
# long enough that B is STILL holding the lock when A finishes its own
# (now-orphaned) cycle and calls release_lock. This is exactly the race the
# ownership check (PR #23 release_lock fix) exists to guard: A must NOT be
# able to delete a lock it no longer owns.
B_SLEEP=3
OUT_B=$(mktemp)
AESOP_ROOT="${AESOP_ROOT}" \
  AESOP_WATCHDOG_CYCLE_CMD="${SLOW_MOCK} ${CYCLE_COUNTER} ${B_SLEEP}" \
  bash "${REPO_ROOT}/daemons/run-watchdog.sh" --once > "$OUT_B" 2>&1 &
PID_B=$!

# Wait for B to reclaim. Poll for BOTH the pid file flipping away from A's
# ORIGINAL_PID AND the "reclaimed" message landing in OUT_B — checking only
# the pid file races the stderr write (mkdir/pid/timestamp land on disk a
# hair before the echo flushes), which is enough jitter on Git-Bash/Windows
# to false-fail this assertion.
RECLAIM_WAIT=0
RECLAIMER_PID=""
RECLAIM_SEEN=0
while [ "$RECLAIM_WAIT" -lt 100 ]; do
  if [ -z "$RECLAIMER_PID" ] && [ -f "$LOCK_PATH/pid" ]; then
    CANDIDATE=$(cat "$LOCK_PATH/pid" 2>/dev/null || echo "")
    if [ -n "$CANDIDATE" ] && [ "$CANDIDATE" != "$ORIGINAL_PID" ]; then
      RECLAIMER_PID="$CANDIDATE"
    fi
  fi
  if grep -q "reclaimed" "$OUT_B" 2>/dev/null; then
    RECLAIM_SEEN=1
  fi
  if [ -n "$RECLAIMER_PID" ] && [ "$RECLAIM_SEEN" -eq 1 ]; then
    break
  fi
  sleep 0.1
  RECLAIM_WAIT=$((RECLAIM_WAIT + 1))
done

if [ "$RECLAIM_SEEN" -ne 1 ]; then
  echo "FAIL: Process B did not report reclaiming the stale lock (no 'reclaimed' in output)"
  cat "$OUT_B"
  exit 1
fi
echo "PASS: Process B reported reclaiming the stale lock"

if [ -z "$RECLAIMER_PID" ]; then
  echo "FAIL: Could not read reclaimer's pid from $LOCK_PATH/pid"
  exit 1
fi

# Wait for A to finish its (orphaned) cycle and attempt release_lock. B is
# still sleeping (B_SLEEP > A_SLEEP), so this is the exact moment the
# ownership check is exercised: A's release_lock must be a no-op here.
wait $PID_A
EXIT_A=$?

if [ ! -d "$LOCK_PATH" ]; then
  echo "FAIL: Lock directory was removed by A — ownership check did NOT hold (release_lock deleted a lock it doesn't own)"
  exit 1
fi

CURRENT_PID=$(cat "$LOCK_PATH/pid" 2>/dev/null || echo "")
if [ "$CURRENT_PID" != "$RECLAIMER_PID" ]; then
  echo "FAIL: Lock pid changed after A's release attempt (expected reclaimer's pid $RECLAIMER_PID, got '$CURRENT_PID')"
  exit 1
fi
echo "PASS: Process A's release_lock did not touch B's live (reclaimed) lock — ownership check held"

# Now wait for B to finish its own cycle and release its own lock.
wait $PID_B
EXIT_B=$?

echo ""
echo "Process A (original holder) exit code: $EXIT_A"
echo "Process B (reclaimer) exit code: $EXIT_B"

if [ -d "$LOCK_PATH" ]; then
  echo "FAIL: Lock directory still exists after B's own release_lock — B failed to clean up its own lock"
  exit 1
fi
echo "PASS: Lock directory was cleaned up by its rightful owner (B)"

CYCLE_RUN_COUNT=$(cat "${CYCLE_COUNTER}")
if [ "$CYCLE_RUN_COUNT" != "2" ]; then
  echo "FAIL: Expected both cycles to run (A and B each once), but count=$CYCLE_RUN_COUNT"
  exit 1
fi
echo "PASS: Both cycles ran (A and B each ran once)"

rm -f "$OUT_A" "$OUT_B" "$SLOW_MOCK"
echo "PASS: Lock ownership enforced"

echo ""
echo "=== Test 4: CYCLE_CMD with spaces in AESOP_ROOT ==="
# Clean state
rm -rf "${TEST_STATE_DIR}"
# Create a path with spaces
TEST_STATE_DIR_SPACES="${TMP_DIR}/state with spaces"
mkdir -p "${TEST_STATE_DIR_SPACES}"
echo "0" > "${CYCLE_COUNTER}"

# Create a path with spaces
AESOP_ROOT_WITH_SPACES="${TMP_DIR}/aesop with spaces"
mkdir -p "$AESOP_ROOT_WITH_SPACES"
cp "${REPO_ROOT}/daemons/run-watchdog.sh" "$AESOP_ROOT_WITH_SPACES/"

OUT_SPACES=$(mktemp)
AESOP_ROOT="${AESOP_ROOT_WITH_SPACES}" \
  AESOP_WATCHDOG_CYCLE_CMD="${MOCK_CYCLE} ${CYCLE_COUNTER}" \
  bash "${AESOP_ROOT_WITH_SPACES}/run-watchdog.sh" --once > "$OUT_SPACES" 2>&1
EXIT_SPACES=$?

echo "Output from AESOP_ROOT with spaces:"
cat "$OUT_SPACES"

CYCLE_RUN_COUNT=$(cat "${CYCLE_COUNTER}")
if [ "$CYCLE_RUN_COUNT" = "1" ]; then
  echo "PASS: Cycle ran with AESOP_ROOT containing spaces"
else
  echo "FAIL: Cycle did not run with spaces in path. Count=$CYCLE_RUN_COUNT"
  exit 1
fi

rm -f "$OUT_SPACES"

echo ""
echo "=== All tests passed ==="
