# daemons/ — Watchdog daemon

**Purpose**: Long-running backup and secret-scan daemon for fleet-wide repo safety.

## Files

- **run-watchdog.sh** (1.7K): Interactive daemon supervisor; spawns backup-fleet.sh every 150s, maintains heartbeat guard (200s dedupe window), logs to FLEET-BACKUP.log. Calls tools/alert_bridge.py --scan after each cycle to post HIGH/CRITICAL alerts to Slack/Discord (opt-in). Traps INT/TERM cleanly.
- **backup-fleet.sh** (5K): Core backup worker; discovers repos (~/.*, ~/*, ~/dev/*), stashes uncommitted work to backup/* branches, pushes unpushed commits, scans tracked files for secrets. Blocks push if secret-scan fails (marks BLOCKED state).

## Contracts

**Env vars consumed**: `AESOP_ROOT` (defaults to `.`) — root of project; prepends to all state/ and tools/ paths.

**State files written** (git-ignored):
- `$AESOP_ROOT/state/.watchdog-heartbeat` — epoch seconds; dedupe guard (200s window).
- `$AESOP_ROOT/state/.watchdog-repos.json` — per-cycle snapshot: [{repo, state: CLEAN|PUSHED|SNAPSHOTTED|BLOCKED, age}].
- `$AESOP_ROOT/state/FLEET-BACKUP.log` — append-only; cycle start/end, repo statuses, secret-scan blocks.
- `$AESOP_ROOT/state/SECURITY-ALERTS.log` — append-only; security alerts (read by alert_bridge.py to post to webhooks).
- `$AESOP_ROOT/state/.alert-bridge-cursor` — line number of last sent alert (ensures idempotent alert dispatch).

**Exit behaviors**: run-watchdog exits 0 always (trap handles clean shutdown). backup-fleet exits 0 even on secret-scan block (marks repo BLOCKED, continues).

**Cadence**: 150s cycle; heartbeat dedupe within 200s.

## Invariants & Gotchas

1. **Single-instance guard (atomic lock)**: run-watchdog.sh uses atomic mkdir-based lockfile (`.watchdog-lock/`) to prevent concurrent daemons.
   - Atomic acquire: `mkdir $LOCK_DIR` is guaranteed atomic on POSIX systems (returns 0 only to first caller).
   - Stale-lock recovery: Crashed holder won't wedge daemon forever; lock older than 300s is reclaimed atomically.
   - Guards both daemon mode and `--once` mode (no bypass).
2. **Testing override**: Set `AESOP_WATCHDOG_CYCLE_CMD` env var to replace backup-fleet.sh invocation (allows tests to use mock cycle without running real backup).
3. **CRLF-safe, no line continuations**: Use POSIX-safe heredocs; never add `\` for line wrap.
4. **Secret-scan gate**: `scan_tracked_files()` calls `$AESOP_ROOT/tools/secret_scan.py` on tracked modifications and untracked files; non-0 exit blocks push, marks repo BLOCKED.
5. **Append-only logs**: FLEET-BACKUP.log only grows; rotate via tools/rotate_logs.py.
6. **Path dedup via realpath**: Avoids processing symlinked repos or dot-dir aliases twice.
7. **Alert Bridge integration** (NEW wave-14): After each backup-fleet.sh cycle, run-watchdog.sh calls `python $AESOP_ROOT/tools/alert_bridge.py --scan || true` to post HIGH/CRITICAL security alerts and heartbeat staleness to Slack/Discord. No-op if webhook_url null/absent in aesop.config.json (feature opt-in). Uses cursor file for idempotent dispatch (no re-sends). See tools/alert_bridge.py for details.
