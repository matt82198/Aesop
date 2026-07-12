# Aesop Dashboard — Domain CLAUDE.md

**Purpose**: Real-time TUI fleet monitoring — watchdog daemon + agent activity display.

## Files

- **watchdog-gui.sh** — Read-only terminal UI (4s refresh, double-buffered, no flicker). Displays daemon status, backed-up repos, heartbeats, recent events. Launch in own window; never inside tool shell. CRLF-safe (no line continuations).
- **dash-extra.mjs** — Node.js agent activity detector. Scans AESOP_TRANSCRIPTS_ROOT for agent-*.jsonl files (last 12 min). TUI output by default; --json for web endpoints. Requires node on PATH (unavailable fallback if missing).

## State contracts

**watchdog-gui.sh reads (heartbeat staleness thresholds applied):**
- `state/.watchdog-heartbeat` (epoch, threshold: 300s for watchdog) 
- `state/FLEET-BACKUP.log` (append-only, tail 3 lines)
- `state/SECURITY-ALERTS.log` (counts HIGH/MED, grep filtering RESOLVED-FP)
- `state/.watchdog-repos.json` (jq-parsed, status per repo)
- `state/.heartbeats/*` (epoch, per-agent thresholds: 3600s monitor, 300s watchdog, 1800s default)

**dash-extra.mjs reads:**
- `~/.claude/projects/**/ agent-*.jsonl` (modified time, <12min filter, top 8 recent)
- `scan/SECURITY-ALERTS.log` (severity classification: HIGH/MED/DRIFT) ← **BUG: should be state/**

**Refresh cadence:**
- watchdog-gui.sh: 4s loop (infinite, Ctrl-C to exit)
- dash-extra.mjs: called on-demand (no built-in loop)

## Invariants & TUI conventions

- **Never modify fleet state** — both tools are read-only dashboards.
- **Infinite loop design** — watchdog-gui.sh runs forever; launch in dedicated terminal window, never inside tool shells.
- **CRLF-safe** — no bash line continuations; portable POSIX.
- **Node optional** — dash-extra.mjs gracefully prints "unavailable" if node missing; doesn't fail watchdog-gui.sh.

See ../CLAUDE.md for watchdog daemon, state file definitions, and secret-scan policy.

## Recursion signal

**No** — domain is shallow (two complementary display tools). No sub-CLAUDE.md needed.

## On-disk contradictions

**dash-extra.mjs path bug:** Line 14 references `scan/SECURITY-ALERTS.log`, but:
- watchdog-gui.sh line 20 reads from `state/SECURITY-ALERTS.log`
- collect-signals.mjs (monitor/) line 179 expects `state/SECURITY-ALERTS.log`
- .gitignore ignores state/ only, not scan/
- Daemons (backup-fleet.sh) write heartbeat/repos to state/ exclusively

**Recommend:** Fix dash-extra.mjs line 14: change `'scan'` to `'state'` in SCAN_DIR path.
