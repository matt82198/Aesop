# {{PROJECT_NAME}} — Multi-Agent Orchestration Brain

**What**: {{PROJECT_NAME}} is a {{DOMAIN_LIST}} system orchestrated through cost-optimized multi-agent dispatch.
This is the team's durable brain: cardinal rules, domain map, and memory indexed here.

## Cardinal Rules (how we work reliably at scale)

These six rules keep our fleet fast, cheap, and unbreakable:

1. **Subagents are always Haiku** (cost optimization at scale). Orchestrator (Opus/Sonnet) on main thread only.
2. **Orchestrator is durable**: STATE.md + BUILDLOG.md committed to git; survive wipes and interruptions.
3. **State gates everything**: No decision without git commit + push. Diff = behavior record.
4. **Secret-scan gates every push**: `tools/secret_scan.py` blocks credentials. No override, no exceptions.
5. **Idempotent + append-only**: Safe to restart mid-cycle. BUILDLOG.md never rewrites, only appends.
6. **Observable machinery**: Every agent dispatch logged. Every cost tracked. Every security event audited.

Read `docs/CARDINAL-RULES.md` for the full 10 rules and rationale. Single-writer discipline and heartbeat patterns are in `docs/GOVERNANCE.md`.

## Domain Map (our system structure)

Each domain maps to one Haiku subagent. Orchestrator dispatch = tiny, scoped, cheap.

{{DOMAINS}}

## Team Memory Structure

Facts live in `~/.claude/MEMORY.md` (index) and individual files in `~/.claude/memory/`.

**Fact format**:
```
---
name: [Title]
description: [1-line hook]
type: [user|feedback|project|reference]
---
[Content]
```

**Types**:
- `user` — who you are, team composition
- `feedback` — decisions, learnings, constraints
- `project` — repo-specific, {{PROJECT_NAME}} setup
- `reference` — patterns, how-tos, runbooks

See `docs/MEMORY-TEMPLATE.md` for full indexing format.

## Initial Setup Checklist

1. **Brain directory** (your private persistent memory):
   ```bash
   mkdir -p ~/.claude/memory
   # Edit ~/.claude/CLAUDE.md with your domains and team info
   # Edit ~/.claude/MEMORY.md with your facts
   ```

2. **Configuration**:
   ```bash
   cp aesop.config.example.json aesop.config.json
   # Edit paths, repos, cycle times per your setup
   ```

3. **Directory structure**:
   ```bash
   mkdir -p ~/{{PROJECT_NAME}}/state
   mkdir -p ~/.heartbeats
   ```

4. **Test the watchdog**:
   ```bash
   export AESOP_ROOT=$HOME/{{PROJECT_NAME}}
   bash $AESOP_ROOT/daemons/run-watchdog.sh --once
   ```

5. **Launch the dashboard**:
   ```bash
   python $AESOP_ROOT/ui/serve.py
   # Opens http://localhost:8770
   ```

6. **(Optional) Arm the monitor**:
   ```bash
   # In your Claude Code orchestrator loop, run:
   export AESOP_ROOT=$HOME/{{PROJECT_NAME}}
   node $AESOP_ROOT/monitor/collect-signals.mjs
   ```

## Repo Map

Your tracked repositories (from aesop.config.json):

{{REPO_LIST}}

Each repo in the list will be discovered by the watchdog, backed up to `backup/wip-*` branches, and secret-scanned before push.

## Key Files & Paths

- **This file**: `~/.claude/CLAUDE.md` — your team brain
- **Memory index**: `~/.claude/MEMORY.md` — indexed facts
- **Memory directory**: `~/.claude/memory/` — individual fact files
- **Orchestrator config**: `~/{{PROJECT_NAME}}/aesop.config.json` (git-ignored)
- **Durable state**: `~/{{PROJECT_NAME}}/state/` — STATE.md, BUILDLOG.md (committed)
- **Watchdog heartbeat**: `~/.heartbeats/.watchdog-heartbeat` (epoch timestamp)
- **Monitor heartbeat**: `~/.heartbeats/.monitor-heartbeat` (epoch timestamp)

## See Also

- `docs/CARDINAL-RULES.md` — full 10 rules with rationale
- `docs/DISPATCH-MODEL.md` — cost analysis + parallel patterns
- `docs/GOVERNANCE.md` — single-writer discipline, inbox, loops
- `docs/MEMORY-TEMPLATE.md` — memory structure and frontmatter
- `README.md` — full walkthrough and troubleshooting

---

**Onboarding ready.** Your fleet is live when BUILDLOG.md shows the first dispatch.
