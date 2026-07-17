# Installation & Setup

**TL;DR**: Install Aesop in ~5 minutes using `npx`, set your repos, then verify with a single watchdog test run.

---

## Prerequisites

Before you start, make sure you have:

- **Claude Code CLI** (v0.1+) — the orchestration harness integration
- **Git** (v2.40+) — version control and worktree support
- **Bash** (v4+) or Git Bash on Windows — shell scripting support
- **Node.js** (v18+) — for dashboard and monitor signals
- **Python** (v3.10+) — for secret-scan and log rotation
- **jq** (optional) — for TUI dashboard parsing

Check your versions:
```bash
claude --version
git --version
bash --version
node --version
python3 --version
```

---

## Quick Start: npx Scaffold (Recommended)

The fastest way to get started is to use the Aesop template scaffolder. It creates a preconfigured aesop harness in a new directory.

### Step 1: Scaffold the harness

```bash
npx @matt82198/aesop my-fleet \
  --name "my-api" \
  --repos "/path/to/repo1,/path/to/repo2"
```

This creates a `my-fleet/` directory with:
- `daemons/` — watchdog, backup, secret-scan
- `skills/` — /power and /buildsystem skill templates
- `monitor/` — signal collectors
- `ui/` — web dashboard
- `aesop.config.json` — your configuration
- `state/` — runtime checkpoints (git-ignored)
- Pre-installed pre-push hook in `.git/hooks/`

### Step 2: Install orchestrator skills

Copy the skill definitions to your Claude Code home directory:

```bash
cd my-fleet

# Copy /power skill (orchestrator brain)
cp -r skills/power/ ~/.claude/skills/power/

# Copy /buildsystem skill (wave cycle automation)
cp -r skills/buildsystem/ ~/.claude/skills/buildsystem/
```

### Step 3: Verify the installation

Run the watchdog once to test everything:

```bash
bash daemons/run-watchdog.sh --once
```

Expected output:
```
[watchdog] backing up fleet state...
[watchdog] scanning for secrets...
[watchdog] drift check: (files checked) ✓
[watchdog] all clear
```

If you see errors, check the logs in `state/FLEET-BACKUP.log`.

---

## Manual Setup: Git Clone (For Development)

If you're hacking on Aesop itself, clone the repo and set up manually:

### Step 1: Clone and configure

```bash
git clone https://github.com/matt82198/aesop ~/my-aesop
cd ~/my-aesop

# Create your configuration
cp aesop.config.example.json aesop.config.json
```

### Step 2: Edit aesop.config.json

Open `aesop.config.json` and customize for your repos (see [CONFIGURE.md](CONFIGURE.md) for full details):

```json
{
  "aesopRoot": "/home/user/my-aesop",
  "braindRoot": "/home/user/.claude",
  "repos": [
    {
      "path": "/home/user/my-repo1",
      "name": "my-api"
    },
    {
      "path": "/home/user/my-repo2",
      "name": "my-frontend"
    }
  ],
  "dashboardPort": 8770,
  "dashboardOrigin": "http://localhost:8770"
}
```

### Step 3: Install skills and test

```bash
# Copy skills to Claude Code
cp -r skills/power/ ~/.claude/skills/power/
cp -r skills/buildsystem/ ~/.claude/skills/buildsystem/

# Set environment variable (add to ~/.bashrc or ~/.zprofile)
export AESOP_ROOT=/home/user/my-aesop

# Verify
bash $AESOP_ROOT/daemons/run-watchdog.sh --once
```

---

## What Gets Created

After setup, you'll have:

### Main directories

- **daemons/** — Background watchdog (runs every 150s)
  - `run-watchdog.sh` — main daemon loop
  - `backup-fleet.sh` — backs up work to a safe branch
  - `secret-scan.py` — blocks pushes with detected credentials

- **state/** — Runtime checkpoints (git-ignored)
  - `STATE.md` — current phase and NEXT STEPS
  - `BUILDLOG.md` — append-only progress log
  - `.watchdog-heartbeat` — daemon liveness marker

- **skills/** — Claude Code orchestration skills
  - `power/` — /power skill template (prime orchestrator brain)
  - `buildsystem/` — /buildsystem skill template (wave cycle automation)

- **monitor/** — Signal collectors
  - `collect-signals.mjs` — health checks (extensible)

- **ui/** — Web dashboard
  - `serve.py` — Python backend (JSON/SSE APIs)
  - `web/` — React frontend (hash-routed SPA)

- **hooks/** — Git pre-push policies
  - `pre-push-policy.sh` — branch discipline + secret-scan enforcement

- **.git/hooks/pre-push** — Auto-installed pre-push hook (configured during setup)

### Configuration files

- **aesop.config.json** — Main configuration (git-ignored, never commit credentials)
  - `aesopRoot` — path to this harness directory
  - `braindRoot` — path to Claude Code home (`~/.claude`)
  - `repos` — list of monitored repositories
  - `dashboardPort` — web dashboard port (default: 8770)
  - `dashboardOrigin` — CORS origin validation

- **aesop.config.example.json** — Template with defaults (commit this, use as reference)

---

## Environment Variables

Optional environment variables you can set in your shell:

```bash
# Point to the Aesop harness root (used by daemons)
export AESOP_ROOT=/home/user/my-aesop

# Optional: custom location for Claude Code home
export CLAUDE_CODE_HOME=/home/user/.claude

# Optional: enable debug output in daemons
export DEBUG=1
```

---

## Pre-push Hook Installation

The `npx` scaffold installs the pre-push hook automatically. If you cloned the repo manually, install it:

```bash
mkdir -p .git/hooks
cp hooks/pre-push-policy.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

The hook enforces:
- Feature branches only (never direct pushes to `main`/`master`)
- Secret scanning (blocks commits with detected credentials)

To bypass during testing: `git push --no-verify` (not recommended for production).

---

## Next Steps

1. **Read [CONFIGURE.md](CONFIGURE.md)** — Customize repos, ports, and brain root
2. **Run [FIRST-WAVE.md](FIRST-WAVE.md)** — Test a full `/power` → `/buildsystem` cycle
3. **Understand [CONCEPTS.md](CONCEPTS.md)** — Learn the dispatch model and state model
4. **Explore the dashboard** — `python3 ui/serve.py` then open http://localhost:8770

For troubleshooting, see the [Aesop README](../README.md#troubleshooting) or [GOVERNANCE.md](GOVERNANCE.md) for operational policies.
