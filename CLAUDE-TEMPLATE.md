# Team Brain Template

**What**: [Your project name/purpose here]. Customize this to describe your fleet.

## Operating principles

This fleet follows the **Cardinal Rules** for multi-agent orchestration:

1. **Subagents are always Haiku** (cost optimization at scale).
2. **Orchestrator on main thread only** (durable, observable).
3. **State committed to git** (STATE.md, BUILDLOG.md survive wipes).
4. **Secret-scan gates every push** (no credentials leak).
5. **Idempotent + append-only** (safe to restart mid-cycle).
6. **Observable machinery** (every action logged, every cost tracked).

Read `docs/CARDINAL-RULES.md` for full text. See `docs/GOVERNANCE.md` for single-writer discipline, heartbeat patterns, and inbox coordination.

## Domain map (customize per team)

- **daemons/** — Watchdog + backup machinery
- **docs/** — Architecture guides and tribal knowledge
- **tools/** — [Your custom tools here]
- **[repo-1]/** — [Your first tracked repo and its domains]
- **[repo-2]/** — [Your second tracked repo]

## Memory structure

Team facts live in `~/.claude/MEMORY.md` (index) and individual files in `~/.claude/memory/`. See `docs/MEMORY-TEMPLATE.md` for the indexing format and frontmatter structure.

## First-time setup

1. Clone the repo.
2. Copy `aesop.config.example.json` → `aesop.config.json`; edit paths and repos.
3. Copy this file: `cp CLAUDE-TEMPLATE.md ~/.claude/CLAUDE.md` and customize domains.
4. Copy memory index: `cp docs/MEMORY-TEMPLATE.md ~/.claude/MEMORY.md`.
5. Run: `bash daemons/run-watchdog.sh --once` (test).
6. Launch: `python ui/serve.py` (dashboard on localhost:8770).

See README.md for full walkthrough and troubleshooting.
