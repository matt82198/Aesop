# Daemons — Domain Brief

**Purpose**: Long-running backup and secret-scan daemon machinery for fleet-wide repo safety.

## Files

- **run-watchdog.sh** (1.5K): Interactive daemon supervisor; spawns backup-fleet.sh every 150s, maintains heartbeat guard (200s dedupe window), logs to FLEET-BACKUP.log. Traps INT/TERM cleanly.
- **backup-fleet.sh** (5K): Core backup worker; discovers repos (~/.*, ~/*, ~/dev/*), stashes uncommitted work to backup/* branches, pushes unpushed commits, scans tracked files for secrets. Blocks push if secret-scan fails (marks BLOCKED state).

## Contracts

**Env vars consumed**: `AESOP_ROOT` (defaults to `.`) — root of project; prepends to all state/ and tools/ paths.

**State files written** (git-ignored, ephemeral):
- `$AESOP_ROOT/state/.watchdog-heartbeat` — epoch seconds; dedupe guard (200s window).
- `$AESOP_ROOT/state/.watchdog-repos.json` — per-cycle snapshot: [{repo, state: CLEAN|PUSHED|SNAPSHOTTED|BLOCKED, age}].
- `$AESOP_ROOT/state/FLEET-BACKUP.log` — append-only; cycle start/end, repo statuses, secret-scan blocks.

**Exit behaviors**: run-watchdog exits 0 always (trap handles clean shutdown). backup-fleet exits 0 even on secret-scan block (marks repo BLOCKED, continues).

**Cadence**: 150s cycle; heartbeat dedupe within 200s.

## Invariants & Gotchas

1. **Single-instance guard**: Heartbeat check prevents duplicate daemons. Delete .watchdog-heartbeat to force restart.
2. **CRLF-safe, no line continuations**: Use POSIX-safe heredocs; never add `\` for line wrap.
3. **Secret-scan gate**: `scan_tracked_files()` calls `$AESOP_ROOT/tools/secret_scan.py` on staged/modified files; non-0 exit blocks push, marks repo BLOCKED.
4. **Append-only logs**: FLEET-BACKUP.log only grows; rotate via tools/rotate_logs.py.
5. **Path dedup via realpath**: Avoids processing symlinked repos or dot-dir aliases twice.

See ../CLAUDE.md for project domain map, cardinal rules, and secret-scan principles.
