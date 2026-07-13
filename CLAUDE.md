# Aesop — Project CLAUDE.md

**What**: Open-source fable-fleet orchestration harness for Claude Code.

## Domain map

- **skills/** — Orchestration skills (/power: priming skill) — see skills/CLAUDE.md
- **daemons/** — Watchdog daemon (repo backup, secret-scan gate, heartbeat) — see daemons/CLAUDE.md
- **dash/** — TUI dashboard (watchdog-gui.sh, real-time fleet status) — see dash/CLAUDE.md
- **monitor/** — Orchestration monitor (collect-signals.mjs, CHARTER.md, AUTO/PROPOSE logic) — see monitor/CLAUDE.md
- **tools/** — Build utilities (secret_scan.py, agent-forensics.sh, launch_tui.py, power_selftest.py, inbox_drain.py) — see tools/CLAUDE.md
- **hooks/** — Git pre-push policy enforcement (branch protection, secret scanning) — see hooks/CLAUDE.md
- **bin/** — CLI scaffolder (Node.js entry point for aesop template) — see bin/CLAUDE.md
- **ui/** — Web dashboard (serve.py, realtime SSE, CSRF protection, collector thread) — see ui/CLAUDE.md
- **tests/** — Test suites (shell, Node, Python) and fixtures — see tests/CLAUDE.md
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
