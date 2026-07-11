# Aesop — Fable-Fleet Orchestration Harness

**Aesop** is an open-source orchestration harness for Claude Code, implementing a cost-optimized, self-healing multi-agent dispatch system. One orchestrator model (Opus/Sonnet) directs a fleet of cheap subagents (Haiku) across durable, observable machinery.

The naming is a conceit: Aesop directs the Fables (the AI models). Like the tortoise and the hare, Aesop favors the slow, deliberate orchestrator directing a fleet of fast, cheap agents toward reliable outcomes.

## What it is

A filesystem-first orchestration system that:

- **Dispatch pattern**: Opus orchestrator on the main thread coordinates tiny scoped tasks to Haiku subagents (1/3 the token cost).
- **Durable state**: git-committed checkpoints (STATE.md, BUILDLOG.md) survive machine wipes and interruptions.
- **Observable machinery**: every agent run logged, every cost tracked, every security breach detected.
- **Self-healing watchdog**: runs every 150s, backs up work, scans for secrets and drift, restores on reboot.
- **Refinement monitor**: standing Haiku loop that watches orchestration health and auto-acts on rule friction.
- **TUI dashboard**: real-time fleet status, security alerts, heartbeat liveness.

## Architecture

### Directory layout

```
aesop/
  daemons/          # Watchdog daemon + backup scripts
  dash/             # TUI dashboard (watchdog-gui.sh)
  monitor/          # Orchestration monitor (collect-signals.mjs, CHARTER.md)
  tools/            # Build utilities (stubs for extend)
  docs/             # Migration guides, deep-dives
  state/            # Durable checkpoints (created at runtime)
  aesop.config.json # Your local configuration (git-ignored)
```

### Operating the harness

#### 1. Bootstrap

```bash
git clone <aesop-repo> ~/aesop
cd ~/aesop
cp aesop.config.example.json aesop.config.json
# Edit aesop.config.json with your paths and repos
```

#### 2. Start the watchdog daemon

```bash
export AESOP_ROOT=$HOME/aesop
bash $AESOP_ROOT/daemons/run-watchdog.sh &
```

Runs every 150s: discovers changed repos, stashes uncommitted work, pushes backups to `backup/wip-*` branches, runs secret-scan gate.

#### 3. Launch the TUI dashboard

```bash
# On Windows:
Start-Process "C:\Program Files\Git\git-bash.exe" -ArgumentList '-c', 'bash /c/Users/you/aesop/dash/watchdog-gui.sh'

# On Unix:
bash ~/aesop/dash/watchdog-gui.sh &
```

Real-time display: repo sync status, fleet heartbeats, security alerts, backup events.

#### 4. Arm the monitor loop

```bash
# If using Claude Code, add to your CLAUDE.md or invoke via /power:
# Runs collect-signals.mjs every cycle, emits BRIEF.md + SIGNALS.json,
# then acts on AUTO-tier findings or stages PROPOSE-tier changes.
```

## Cardinal Rules (abridged)

Read `docs/CARDINAL-RULES.md` for the full text. Core principles:

1. **Dispatch**: Haiku subagents only (cost lever). Opus orchestrates main-thread only.
2. **TDD-first**: Fail tests before implementation. Tiny scoped domains; one Haiku per domain.
3. **Reliability**: Every input produces output (brief/log/heartbeat/FAILED). Never wait.
4. **Durable state**: STATE.md + BUILDLOG.md checkpoints survive wipes. Re-sync on resume.
5. **Push discipline**: feature/branch → PR (never main). Continuously push green work.
6. **Control files**: Single-writer discipline (STATE.md orchestrator, MEMORY.md keeper, BUILDLOG.md append-only).
7. **Local execution**: Python runs locally only (no cloud runners). Reusable scripts in ~/scripts.
8. **Secret gates**: `secret_scan.py` blocks every push. No credentials in repos.
9. **Observability**: Every agent run logged, every cost tracked, every security event triaged.

## Requirements

- **Claude Code CLI** (v0.1+): the agent-spawning harness.
- **Git** (v2.40+): version control for durable state.
- **Bash** (v4+): scripting (Git Bash on Windows, bash on Unix).
- **Node.js** (v18+): for monitor signal collection and dashboard extras.
- **Python** (v3.10+): for log rotation, secret-scan, and custom tooling.
- **jq** (optional): JSON parsing in TUI dashboard.

## Setup Walkthrough

### 1. Edit your configuration

```bash
cp aesop.config.example.json aesop.config.json
```

Edit `aesop.config.json`:
- Set `aesop_root`, `brain_root`, `scripts_root`, `temp_root` to your paths.
- List your project repos under `repos[]`.
- Tune watchdog and monitor cycle times.
- Disable secret-scan if you don't have `tools/secret_scan.py` yet.

### 2. Create required directories

```bash
mkdir -p ~/aesop/state
mkdir -p ~/.heartbeats
```

### 3. (Optional) Add your secret-scan script

If you have a security scanner, drop it at `aesop/tools/secret_scan.py`. The watchdog will call it before pushing.

Example stub:
```python
#!/usr/bin/env python3
import sys
sys.exit(0)  # TODO: implement secret scanning
```

### 4. Start the daemon

```bash
export AESOP_ROOT=$HOME/aesop
bash $AESOP_ROOT/daemons/run-watchdog.sh &
```

Test mode: `bash $AESOP_ROOT/daemons/run-watchdog.sh --once`

### 5. Launch the dashboard

```bash
bash ~/aesop/dash/watchdog-gui.sh
```

### 6. Arm the monitor (optional)

If you're using Claude Code, add this to your orchestrator loop:
```bash
export AESOP_ROOT=$HOME/aesop
node $AESOP_ROOT/monitor/collect-signals.mjs
```

The monitor will read `BRIEF.md` and `SIGNALS.json` each cycle and act on findings.

## Usage Patterns

### Dispatch model (how to scale cheaply)

```plaintext
Orchestrator (main thread)
  ├─ Haiku subagent 1 (domain A: tests)
  ├─ Haiku subagent 2 (domain B: build)
  ├─ Haiku subagent 3 (domain C: review)
  └─ Haiku subagent 4 (domain D: docs)
```

Each subagent is **tiny**, **scoped**, and **disposable**. Total cost: ~25% of all-Opus fleet.

### Action tiers (AUTO vs PROPOSE)

- **AUTO**: immediate + logged (read-only checks, appends to logs, heartbeat updates).
- **PROPOSE**: staged in `monitor/PROPOSALS.md`, requires user approval before execution.

### Heartbeat pattern

Daemons write epoch-seconds to `.heartbeat` files. The dashboard reads these to detect stalls:
- Watchdog: alert if >300s old.
- Monitor: alert if >3600s old.
- Custom loops: check before spawning (skip if <200s).

## Security & Privacy

**⚠️ Important**: This harness assumes a **private brain directory** (`~/.claude`) that is **NEVER committed** to this repo. Your cardinal rules, agent catalog, and memory belong in your private remote (e.g., `claude-config`).

- `aesop.config.json` is git-ignored (keep your paths secret).
- `state/` and `.log` files are git-ignored (keep runtime data local).
- Implement `tools/secret_scan.py` with your own security rules.
- Use `secret_scan.py` as a gate on every push (don't bypass).

## Extension points

### Add a custom signal collector

Edit `monitor/collect-signals.mjs`:
```javascript
// Example: detect junk scripts
function findJunkScripts() {
  const junk = fs.readdirSync('/tmp').filter(f => f.endsWith('.py'));
  return junk;
}

// Then add to signals:
signals.junkScripts = findJunkScripts();
```

### Customize the watchdog

Edit `daemons/backup-fleet.sh`:
- Parse `aesop.config.json` to discover repos dynamically.
- Add per-repo hooks (e.g., run linters before backup).
- Implement your own secret-scan gate.

### Extend the dashboard

Edit `dash/watchdog-gui.sh`:
- Add panels for CPU/memory/disk usage.
- Integrate with your monitoring system.
- Color-code alerts by severity.

## Troubleshooting

### Watchdog doesn't start

Check `state/FLEET-BACKUP.log` for errors. Verify `AESOP_ROOT` is set correctly.

### Dashboard shows "unavailable"

- If you see `(agents/processes panel unavailable)`, `node` is missing or `dash-extra.mjs` is not in sync.
- Install Node.js v18+ and re-run.

### Secret-scan blocks a legitimate push

Add a suppression to your `tools/secret_scan.py`. Aesop never auto-bypasses gates (by design).

### Monitor doesn't start

Ensure Node.js is on PATH and `collect-signals.mjs` has execute permissions. Check `monitor/BRIEF.md` for the latest cycle log.

## Architecture deep-dives

See `docs/` for detailed guides:
- `CARDINAL-RULES.md` — full text of the 10 cardinal rules.
- `DISPATCH-MODEL.md` — cost analysis and parallel orchestration patterns.
- `STATE-MACHINE.md` — how STATE.md and BUILDLOG.md survive wipes.
- `MONITOR-GOVERNANCE.md` — monitor AUTO/PROPOSE tiers and approval flow.

## License

MIT License. See `LICENSE` file.

## Contributing

Aesop is open-source and welcomes improvements. To contribute:

1. Fork this repo.
2. Create a feature branch: `git checkout -b feature/your-idea`.
3. Add tests (TDD first).
4. Commit with clear messages.
5. Push to origin and open a PR.

Maintain the cardinal rules: keep subagents cheap (Haiku), orchestrator lean, state durable, and machinery observable.

## References

- [Anthropic Claude API](https://docs.anthropic.com)
- [Claude Code CLI](https://github.com/anthropics/claude-code)
- [Git documentation](https://git-scm.com/doc)
- Inspiration: "The Missing Memory Layer", "Agent Cost Trauma", "120 Words to Shipped" (publications on AI orchestration patterns).

---

**Aesop Contributors**  
Built with the fable-fleet dispatch model in mind. May your orchestrator be wise and your subagents swift.
