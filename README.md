<p align="center">
  <img src="https://raw.githubusercontent.com/matt82198/aesop/main/assets/logo.png" alt="Aesop" width="420">
</p>

<p align="center">
  <em>Fable-Fleet Orchestration Harness</em>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@matt82198/aesop"><img src="https://img.shields.io/npm/v/@matt82198/aesop/beta" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/npm/l/@matt82198/aesop" alt="license"></a>
  <a href="https://github.com/matt82198/aesop/actions/workflows/ci.yml"><img src="https://github.com/matt82198/aesop/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

**Aesop** is an open-source orchestration harness for Claude Code, implementing a cost-optimized, self-healing multi-agent dispatch system. One orchestrator model (Opus/Sonnet) directs a fleet of cheap subagents (Haiku) across durable, observable machinery.

The naming is a conceit: Aesop directs the Fables (the AI models). Like the tortoise and the hare, Aesop favors the slow, deliberate orchestrator directing a fleet of fast, cheap agents toward reliable outcomes.

## Origin

Aesop began as damage control: an endpoint-security agent kept deleting work mid-session, so everything was forced into git—committed continuously, pushed constantly, reconstructable from nothing but the remotes. What started as a survival mechanism against a machine that wiped itself grew into a full multi-agent orchestration system—and one worth sharing.

## What it is

A filesystem-first orchestration system that:

- **Dispatch pattern**: Opus orchestrator on the main thread coordinates tiny scoped tasks to Haiku subagents (1/3 the token cost).
- **Durable state**: git-committed checkpoints (STATE.md, BUILDLOG.md) survive machine wipes and interruptions.
- **Observable machinery**: every agent run logged, every cost tracked, every security breach detected.
- **Self-healing watchdog**: runs every 150s, backs up work, scans for secrets and drift, restores on reboot.
- **Refinement monitor**: standing Haiku loop that watches orchestration health and auto-acts on rule friction.
- **TUI dashboard**: real-time fleet status, security alerts, heartbeat liveness.

## Behavior as Code: Five Pillars

Aesop ships behavior as versioned, portable, diffable filesystem artifacts in git—enabling review, versioning, inheritance, enforcement, and forensics over how agents work. The implementation consists of five integrated capabilities:

1. **Onboarding-by-clone** — [CLAUDE-TEMPLATE.md](./CLAUDE-TEMPLATE.md) and [docs/MEMORY-TEMPLATE.md](./docs/MEMORY-TEMPLATE.md) scaffold team brains; sync via `bin/cli.js`. The pre-push hook is **auto-installed during scaffold**.
2. **Guardrails-in-code** — [hooks/pre-push-policy.sh](./hooks/pre-push-policy.sh) enforces branch discipline and secret-scanning gates; auto-installed into `.git/hooks/pre-push` during scaffold (idempotent, preserves customizations); audit trail in [state/SECURITY-AUDIT.log](./state/SECURITY-AUDIT.log).
3. **Behavioral PRs** — [.github/pull_request_template.md](./.github/pull_request_template.md) enforces behavioral-change descriptions; [docs/BEHAVIORAL-PR-REVIEW.md](./docs/BEHAVIORAL-PR-REVIEW.md) provides the checklist; [CONTRIBUTING.md](./CONTRIBUTING.md) documents the process.
4. **Forensic replay** — [tools/agent-forensics.sh](./tools/agent-forensics.sh) reconstructs behavior at any commit with `--diff behavior-surface` mode; [docs/FORENSICS.md](./docs/FORENSICS.md) shows git-bisect recipes.
5. **Cross-machine continuity** — [docs/RESTORE.md](./docs/RESTORE.md) reconstitution playbook for recovery on new machines.

## Install & Quick Start

**Note:** Aesop is currently in beta. Install the prerelease version with the `@beta` npm tag to get the latest development release (0.1.0-beta.1+).

### Option 1: One command (fastest)

Scaffold your fleet with a single command. No manual editing required—CLAUDE.md and aesop.config.json are pre-generated with your project info:

```bash
npx @matt82198/aesop@beta my-fleet --name "my-api" \
  --domains "api,worker" \
  --repos "/path/to/repo1,/path/to/repo2"
cd my-fleet

# Start the daemon
bash daemons/run-watchdog.sh --once

# Launch the dashboard
python ui/serve.py
```

Open `http://localhost:8770` to monitor your fleet. The pre-push hook is auto-installed and enforces branch protection and secret scanning. See [docs/HOOK-INSTALL.md](./docs/HOOK-INSTALL.md) for details.

### Option 1B: Manual setup (customize before scaffold)

Scaffold the template first, then edit the config:

```bash
# Create a new aesop fleet directory
# Using @beta tag to install the latest prerelease version (0.1.0-beta.1)
npx @matt82198/aesop@beta my-fleet
cd my-fleet

# Configure
cp aesop.config.example.json aesop.config.json
# Edit aesop.config.json with your paths and repos

# Start the daemon
bash daemons/run-watchdog.sh --once

# Launch the dashboard
python ui/serve.py
```

Alternatively, install globally:
```bash
npm install -g @matt82198/aesop@beta
aesop my-fleet
```

### Option 2: git clone (For development or full customization)

```bash
git clone https://github.com/matt82198/aesop ~/aesop
cd ~/aesop
cp aesop.config.example.json aesop.config.json
# Edit aesop.config.json with your paths and repos

# Start the daemon (Bash)
export AESOP_ROOT=$HOME/aesop
bash $AESOP_ROOT/daemons/run-watchdog.sh --once

# Or on Windows (PowerShell):
$env:AESOP_ROOT = "$HOME\aesop"
bash $env:AESOP_ROOT/daemons/run-watchdog.sh --once

# Launch the dashboard
python ui/serve.py
```

## Architecture

### Directory layout

```
aesop/
  skills/           # Orchestration skills (/power priming skill)
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

#### 3. Launch the Web Dashboard (Primary Interface)

The web dashboard is the recommended way to monitor your fleet. It provides real-time observability, security alerts, and inbox integration in a modern, responsive interface.

```bash
python $AESOP_ROOT/ui/serve.py
```

Opens `http://localhost:8770` with:
- Real-time daemon heartbeats and liveness
- Active subagent tracking
- Security alerts panel
- Recent events log
- Inbox for orchestrator communication
- Repository sync status

See `ui/README.md` for configuration, environment variables, and troubleshooting.

#### (Optional) Legacy TUI Dashboard

If you prefer a terminal-based interface:

```bash
# On Windows (in a dedicated terminal):
Start-Process "C:\Program Files\Git\git-bash.exe" -ArgumentList '-c', 'bash /c/Users/you/aesop/dash/watchdog-gui.sh'

# On Unix:
bash ~/aesop/dash/watchdog-gui.sh &
```

Note: The TUI is maintained for backward compatibility but is not actively developed. The web dashboard is recommended for new deployments.

#### 4. Arm the monitor loop

```bash
# If using Claude Code, add to your CLAUDE.md or invoke via /power:
# Runs collect-signals.mjs every cycle, emits BRIEF.md + SIGNALS.json,
# then acts on AUTO-tier findings or stages PROPOSE-tier changes.
```

### Prime your orchestrator (/power)

If you're using **Claude Code**, the `/power` skill primes your orchestrator's filesystem brain in one call. It loads all operating rules, dispatch models, memory, and project state from disk and produces a compact health brief.

**Setup** (required once):
```bash
# Copy the /power skill into your Claude Code skills directory
cp -r skills/power/ ~/.claude/skills/power/
```

**Usage** (every session):
```bash
# In Claude Code, invoke:
/power

# This loads:
# - ~/.claude/CLAUDE.md (cardinal rules, domain map)
# - ~/.claude/MEMORY.md + ~/.claude/memory/* (team facts)
# - Aesop machinery state (heartbeats, proposals, durable checkpoints)
# - Project-specific CLAUDE.md (this repo's domain map)

# Output: brief health report with system status and next steps
```

The `/power` skill is self-contained and gracefully degrades when targets are absent. See [skills/power/SKILL.md](./skills/power/SKILL.md) for full details.

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

### 2. Initialize your brain (Claude Code team memory)

The team brain is your private copy of `CLAUDE.md` and `MEMORY.md` that lives in `~/.claude/`. Copy the templates and customize for your team:

```bash
# Create the memory directory
mkdir -p ~/.claude/memory

# Copy and customize the template files
cp CLAUDE-TEMPLATE.md ~/.claude/CLAUDE.md
cp docs/MEMORY-TEMPLATE.md ~/.claude/MEMORY.md

# Edit both files with your team info
# ~/.claude/CLAUDE.md: Add your domains, cardinal rules, and setup steps
# ~/.claude/MEMORY.md: Add team facts (one per file in ~/.claude/memory/)
```

After copying, edit `~/.claude/CLAUDE.md` to reflect your project domains, team principles, and setup steps. Edit `~/.claude/MEMORY.md` to index your team's persistent knowledge and facts.

### 3. Create required directories

```bash
mkdir -p ~/aesop/state
mkdir -p ~/.heartbeats
```

### 4. (Optional) Add your secret-scan script

If you have a security scanner, drop it at `aesop/tools/secret_scan.py`. The watchdog will call it before pushing.

Example stub:
```python
#!/usr/bin/env python3
import sys
sys.exit(0)  # TODO: implement secret scanning
```

### 5. Start the daemon

```bash
export AESOP_ROOT=$HOME/aesop
bash $AESOP_ROOT/daemons/run-watchdog.sh &
```

Test mode: `bash $AESOP_ROOT/daemons/run-watchdog.sh --once`

### 6. Launch the dashboard

```bash
bash ~/aesop/dash/watchdog-gui.sh
```

### 7. Arm the monitor (optional)

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

### Pre-Push Hook: Local Convenience Defense Only

The pre-push hook (`hooks/pre-push-policy.sh`) enforces branch discipline and secret scanning **locally**. It is **bypassable**:
- Any developer can use `git push --no-verify` to skip it.
- The audit log is stored locally and can be edited or deleted.

**For real enforcement, pair with server-side branch protection** (e.g., GitHub protected branches):

1. **GitHub Protected Branches**: Navigate to Settings > Branches and create a rule for `main` with:
   - ✓ Require pull request reviews before merging
   - ✓ Require status checks to pass before merging
   - ✓ Require branches to be up to date before merging
   - ✓ Restrict pushes to (Admins only)

2. **Audit Log Integrity**: The hook maintains a hash-chain audit log (each event includes SHA-256 of the previous entry). Verify integrity with:
   ```bash
   bash hooks/pre-push-policy.sh --verify-audit-log
   ```
   **Note**: This detects accidental corruption but is not cryptographic protection against a determined attacker with file system access. For production auditability, centralize logs to an immutable remote service (CloudWatch, Datadog, or a dedicated log server).

See [docs/HOOK-INSTALL.md](./docs/HOOK-INSTALL.md) for full configuration details.

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

See [CHANGELOG.md](./CHANGELOG.md) for release notes and version history.

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
