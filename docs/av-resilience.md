# Antivirus (AV) Resilience & Behavioral Engine Design Patterns

## Problem Statement

Antivirus and behavioral-analysis engines (SentinelOne, Windows Defender, etc.) may:
- **Delete tool binaries mid-session** when they trigger heuristic alerts (Claude Code, git-bash, node, python)
- **Suspend processes** during scanning, causing temporary hangs or failed tool invocations
- **Block file writes** to protected directories, silently failing git operations or log appends
- **Trigger false positives** on legitimate automation workflows (agent dispatch, secret scanning, process spawning)

This is not a security breach—it's a *compatibility* problem with legitimate automation tools. Aesop must survive these disruptions gracefully.

---

## Design Principles

### 1. **Continuous Push Discipline**
- **Every cycle completes a push**, not just a stash or backup. If one file blocks due to AV, push the rest.
- **Philosophy**: A partially-pushed state (some repos synced, some stalled) is **better** than no push at all.
- **Implementation**:
  - `daemons/backup-fleet.sh` processes repos independently; one BLOCKED repo doesn't stall others.
  - `state/FLEET-BACKUP.log` logs each outcome (CLEAN, PUSHED, SNAPSHOTTED, BLOCKED) per repo.
  - Watchdog cycle completes successfully even if 1 of 10 repos fails.

### 2. **Surgical Single-File Recovery**
- **Minimize scope of recovery**. If a binary is deleted, re-fetch only that one binary, not the whole toolchain.
- **Pattern**:
  - Monitor tool invocation failures: `python: command not found`, `git: not found`.
  - Trigger minimal reinstall: `apt-get install python`, `git clone <tool>`.
  - Resume immediately without waiting for manual intervention.
- **Why**: Batch slowdowns (full OS update, system restart) are much worse than targeted tool recovery.

### 3. **Avoid Mass Process Kills**
- **Anti-pattern**: Restarting the orchestrator, killing all agents, wiping state when one process hangs.
- **Pattern**: 
  - Use tight heartbeat timeouts (300s for watchdog, 3600s for monitor).
  - Kill **only** the stalled agent by its PID; main orchestrator stays alive.
  - Log the kill and its reason (e.g., "heartbeat age 450s > threshold 300s").
  - Resume the agent or defer to next cycle.

### 4. **Idempotent Push Refs**
- **Backup refs are date-stamped, not timestamped**: `backup/wip-20260711`, not `backup/wip-20260711-134521`.
- **Why**: Multiple backup attempts on the same day write to the same ref, so git naturally deduplicates them.
- **Recovery**: If a push partially fails and the process dies, the next cycle tries again to the same ref and succeeds without creating orphaned branches.

### 5. **Tracked-Files-Only Secret Scanning**
- **Scan only modified files**, not the entire repo (which includes .gitignored binaries, node_modules, build artifacts).
- **Pattern**:
  ```bash
  git diff --name-only HEAD | xargs secret_scan.py
  git ls-files -m | xargs secret_scan.py
  ```
- **Why**: 
  - AV engines sometimes block access to large binary files during scanning. Scanning a 500MB node_modules triggers false-positive rate.
  - Scanning only tracked changes is **faster** and **more reliable** than full-directory scans.
  - Mirrors what a push gate would actually check (`git diff` before commit).

---

## Failure Modes & Recovery

### Scenario 1: Binary Deletion Mid-Cycle

**What happens:**
```bash
$ bash /path/to/aesop/daemons/backup-fleet.sh
[2026-07-11 10:30:15] === cycle start ===
[2026-07-11 10:30:16] SentinelOne deletes git.exe (false positive on automation)
$ git fetch -q
bash: git: command not found
[2026-07-11 10:30:17] BLOCKED: my-project-repo
```

**Recovery:**
1. Watchdog detects BLOCKED outcome → logs to FLEET-BACKUP.log.
2. Next cycle (150s later) detects repo is touched (uncommitted files remain).
3. Retry `is_touched()` → re-fetch → get `command not found` again.
4. **Manual intervention path**: User or admin runs:
   ```bash
   # Re-install git (OS-specific)
   winget install Git.Git  # Windows
   apt-get install git      # Linux
   ```
5. Next watchdog cycle succeeds (binary is back).

**Design choice**: Watchdog logs but doesn't auto-repair missing binaries (policy: fail safely, log clearly, resume on next cycle).

---

### Scenario 2: Process Suspension During Secret Scan

**What happens:**
```bash
$ python secret_scan.py file1.py file2.py file3.py
# AV engine suspends python.exe during scan of large file
[waiting indefinitely or timing out after 30s]
```

**Recovery:**
1. `scan_tracked_files()` runs with implicit timeout (scan completes or fails).
2. If timeout, `scan_tracked_files` returns non-zero exit code → BLOCKED outcome.
3. Files remain uncommitted (no push attempt).
4. **Recommendation**: Tune secret-scan to scan **only staged files** (via `git diff --cached`), reducing scope.

---

### Scenario 3: Orchestrator Heartbeat Stale

**What happens:**
```bash
# Watchdog daemon hung (AV locked python.exe; backup-fleet.sh stalled)
# Heartbeat timestamp = 1720680915 (5 minutes ago)
$ cat state/.watchdog-heartbeat
1720680915
$ date +%s
1720681215  # Current time, 300s later
# Dashboard threshold = 300s for watchdog
# Status: STALE
```

**Recovery:**
1. Dashboard shows `STALE (age: 300s+)` in red.
2. User checks logs (`state/FLEET-BACKUP.log`) to diagnose why daemon stalled.
3. Options:
   - **If binary is missing**: Reinstall and restart watchdog.
   - **If process is hung**: Kill it (`pkill -f run-watchdog.sh`) and restart.
   - **If it's a false stall**: Wait for next cycle (watchdog usually recovers).
4. Restart watchdog:
   ```bash
   bash $AESOP_ROOT/daemons/run-watchdog.sh
   ```

---

## Best Practices

### For Aesop Operators

1. **Monitor the dashboard**. STALE heartbeats are your canary in the coal mine.
2. **Review FLEET-BACKUP.log** weekly for BLOCKED outcomes. Investigate patterns.
3. **Keep security scanner narrow**: Scan only staged files (`--staged`), not entire repos.
4. **Whitelist Aesop tools in your AV**:
   - `C:\Program Files\Git\bin\bash.exe`
   - `python.exe` (if Python is on PATH)
   - Node.js (if using orchestration monitor)
   - The Aesop root directory itself (read-only, no execution harm)

### For Aesop Developers

1. **Test against real AV**. Spin up a test VM with SentinelOne or similar and deliberately trigger false positives.
2. **Log all process invocations**. Include PID, command, exit code, stderr (first 100 chars).
3. **Use tight timeouts** (30s for secret scans, 5s for git commands). Fail fast, don't hang.
4. **Implement single-instance guards** via heartbeat files. Don't spawn multiple instances of the same daemon.
5. **Design for recovery**: Every log entry should make it obvious to a human or script *why* something failed and *what to do next*.

---

## Configuration & Tuning

### Heartbeat Thresholds (seconds)

Tune these based on your infrastructure speed:

```bash
get_hb_threshold() {
  local name="$1"
  case "$name" in
    *monitor*)  echo 3600 ;;   # Orchestration monitor: 1 hour (low-frequency signal collection)
    *watchdog*) echo 300  ;;   # Watchdog daemon: 5 minutes (tight, frequent backup cycles)
    *backup*)   echo 300  ;;   # Backup script: 5 minutes (same cadence as watchdog)
    *)          echo 300  ;;   # Default: 5 minutes
  esac
}
```

- **Increase thresholds** if your infrastructure is slow (slow disks, high load, slow network).
- **Decrease thresholds** if you want faster failure detection (but risk false STALE alerts during heavy AV scans).

### Secret Scanning Scope

Change `scan_tracked_files()` to scan only staged files instead of modified files:

```bash
scan_tracked_files() {
  local repo="$1"
  # Alternative: scan only files staged for commit
  git diff --cached --name-only 2>/dev/null | xargs -r secret_scan.py
}
```

### Logging Detail

Increase logging verbosity to diagnose AV conflicts:

```bash
log "git fetch returned $?: $(cd $repo && git fetch -q origin 2>&1 | head -c 100)"
```

---

## Testing & Validation

### Test Case: Simulate Binary Deletion

```bash
# 1. Start watchdog in background
bash $AESOP_ROOT/daemons/run-watchdog.sh &
WATCHDOG_PID=$!

# 2. Simulate git deletion
mv /c/Program\ Files/Git/bin/git.exe /tmp/git.exe.bak

# 3. Wait for next cycle
sleep 160

# 4. Check logs
tail -20 $AESOP_ROOT/state/FLEET-BACKUP.log

# 5. Restore git
mv /tmp/git.exe.bak /c/Program\ Files/Git/bin/git.exe

# 6. Next cycle should recover
sleep 160
tail -10 $AESOP_ROOT/state/FLEET-BACKUP.log
```

### Expected Output

```
[2026-07-11 10:30:15] === cycle start ===
[2026-07-11 10:30:16] BLOCKED: my-repo
[2026-07-11 10:30:16] === cycle end ===
[2026-07-11 10:32:16] === cycle start ===
[2026-07-11 10:32:17] CLEAN: my-repo   # (or PUSHED if changes made during downtime)
[2026-07-11 10:32:17] === cycle end ===
```

---

## References

- [SentinelOne Behavioral Engine False Positives](https://community.sentinelone.com/)
- [Windows Defender ASR Rules](https://learn.microsoft.com/en-us/windows/security/threat-protection/microsoft-defender-atp/attack-surface-reduction)
- [Git Best Practices for Automation](https://git-scm.com/docs/git-var)
- Aesop docs/STATE-MACHINE.md — Durable checkpointing recovery
- Cardinal Rule 3 (main CLAUDE.md) — "Reliability core: Inputs ALWAYS produce outputs"
