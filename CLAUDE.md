# Aesop — Project CLAUDE.md

**What**: Open-source fable-fleet orchestration harness for Claude Code.

## Domain map

- **daemons/** — Watchdog daemon (repo backup, secret-scan gate, heartbeat)
- **dash/** — TUI dashboard (watchdog-gui.sh, real-time fleet status)
- **monitor/** — Orchestration monitor (collect-signals.mjs, CHARTER.md, AUTO/PROPOSE logic)
- **tools/** — Build utilities and extension stubs (secret_scan.py, rotate_logs.py, etc.)
- **docs/** — Architecture guides, cardinal rules, tutorials
- **state/** — Runtime durable checkpoints (git-ignored, created by daemons)

## Key principles

1. **Subagents are always Haiku** (cost optimization at scale).
2. **Orchestrator on main thread only** (durable, observable).
3. **State committed to git** (STATE.md, BUILDLOG.md survive wipes).
4. **Secret-scan gates every push** (no credentials leak).
5. **Idempotent + append-only** (safe to restart mid-cycle).
6. **Observable machinery** (every action logged, every cost tracked).

## Branch + PR discipline

- Feature/* branch only (never main/master).
- All pushes gated by secret-scan.py (exit 1 blocks).
- NOT a vault repo (credentials → your private remote).

## Setup for development

1. Clone the repo.
2. Copy `aesop.config.example.json` → `aesop.config.json` and customize.
3. Run `bash daemons/run-watchdog.sh --once` to test.
4. Launch `bash dash/watchdog-gui.sh` to verify dashboard.
5. Extend `monitor/collect-signals.mjs` with your custom signal collectors.

See README.md for full context and usage examples.
