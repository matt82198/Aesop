# daemons/ — Watchdog daemon

**Purpose**: Long-running backup, push, and secret-scan daemon ensuring fleet-wide repo safety.

## Universal rules (every domain)
- Feature branch only, never main; every push gated by `python tools/secret_scan.py --staged` exit 0.
- Tests never pollute cwd or global git config; temp dirs only; dummy secrets are runtime-concatenated, never literal.
- In worktrees use ABSOLUTE paths under the worktree for every write.
- Domain docs stay minimal-but-complete; update this file in the same PR as code it describes.

## Files

- **run-watchdog.sh**: Daemon supervisor (1.7K); spawns backup-fleet.sh every 150s with atomic lockfile guard, maintains heartbeat, logs to FLEET-BACKUP.log, posts security alerts via alert_bridge.py (opt-in). Traps INT/TERM cleanly. **BASH_SOURCE exec-guard** (line ~272): `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi` — allows sourcing for test reuse without triggering a cycle.
- **backup-fleet.sh**: Core backup worker (5K); discovers repos (~/.*, ~/*, ~/dev/*), stashes uncommitted work to backup/* branches, pushes unpushed commits, scans tracked/untracked files for secrets. Blocks push if secret-scan fails. **Set -u pipefail** at top; no side effects on source.

## State files & contracts (git-ignored)

- `$AESOP_ROOT/state/.watchdog-heartbeat`: Unix epoch seconds; dedupe guard (200s window).
- `$AESOP_ROOT/state/.watchdog-lock/`: Atomic lockfile dir (mkdir-based, POSIX atomic). Contains `timestamp` (epoch) and `pid` files; stale if >300s old or process dead (atomic reclaim logic in acquire_lock()).
- `$AESOP_ROOT/state/.watchdog-repos.json`: Per-cycle snapshot [{repo, state: CLEAN|PUSHED|SNAPSHOTTED|BLOCKED, age}] with JSON-escaped repo names (backslash/quote/newline/control chars).
- `$AESOP_ROOT/state/FLEET-BACKUP.log`: Append-only; cycle start/end, repo statuses, secret-scan blocks, monitor staleness signals.
- `$AESOP_ROOT/state/SECURITY-ALERTS.log`: Append-only security alerts (read by alert_bridge.py for Slack/Discord webhooks).
- `$AESOP_ROOT/state/.alert-bridge-cursor`: Line number of last sent alert (idempotent dispatch).
- `$AESOP_ROOT/state/.HALT`: Kill-switch sentinel (JSON {reason}); checked at cycle start; any cycle halted logs "HALTED: <reason>" and skips all work until cleared.

## Environment variables

- `AESOP_ROOT` (default: `.`): Project root; prepends to all state/ and tools/ paths.
- `AESOP_WATCHDOG_CYCLE_CMD`: Override backup-fleet.sh invocation (test override); if set, runs as `bash -c "$AESOP_WATCHDOG_CYCLE_CMD"`.

## Invariants & Style

1. **Single-instance guard**: run-watchdog.sh uses atomic mkdir ($LOCK_DIR) to prevent concurrent daemons (both daemon and --once modes). Stale-lock recovery at 300s threshold; crashed holder won't wedge forever.
2. **CRLF-safe, no line continuations**: Use POSIX-safe heredocs (no backslash wrapping); scripts must work on Windows/CRLF systems.
3. **Append-only logs**: FLEET-BACKUP.log only grows; rotate via tools/rotate_logs.py if >20KB.
4. **Secret-scan gate**: `scan_tracked_files()` and `scan_unpushed_commits()` call tools/secret_scan.py; non-0 exit blocks push, marks repo BLOCKED.
5. **Exit always 0**: run-watchdog exits 0 always (trap cleans up); backup-fleet exits 0 even on secret-scan block.
6. **Path dedup via realpath**: Avoids processing symlinked repos twice.
7. **Alert Bridge integration**: After backup-fleet.sh cycles, run-watchdog calls `python tools/alert_bridge.py --scan || true` to post HIGH/CRITICAL alerts and heartbeat staleness. No-op if webhook_url missing in aesop.config.json (opt-in feature). Cursor file ensures idempotent dispatch.
8. **Cycle cadence**: 150s between cycles; heartbeat dedupe within 200s window.

## Testing

**Run all daemons tests** (hermetic, uses mktemp fixtures):
```bash
bash tests/test-run-watchdog.sh
bash tests/test-run-watchdog-lockguard.sh
bash tests/test-run-watchdog-halt.sh
bash tests/backup-fleet.test.sh
```

Or via npm:
```bash
npm run test:sh
```

Tests never touch real AESOP_ROOT/state; all invocations point at throwaway mktemp dirs. REPO_ROOT locates the script under test only.

## Dropped (reason)
- Alert Bridge details (wave-14 feature; see tools/alert_bridge.py for implementation)
- Config parsing details (see aesop.config.json structure in root CLAUDE.md)
- Per-function implementation details (inlined only contracts/interfaces above)

Map of all domains: /CLAUDE.md
