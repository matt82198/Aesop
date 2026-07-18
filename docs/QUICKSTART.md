# Quickstart: 5 Minutes to Your First Wave

Get from `npx @matt82198/aesop` to a working wave cycle: scaffold, verify, run the orchestrator skills, and watch it work.

---

## Step 1: Scaffold

```bash
cd ~/my-repo
npx @matt82198/aesop .
```

Or if your repo is new:
```bash
npx @matt82198/aesop my-fleet && cd my-fleet
```

This installs daemons, skills, config, and a pre-push hook. Edit `aesop.config.json` to add repos.

---

## Step 2: Verify & Test

```bash
npx @matt82198/aesop doctor          # Preflight: Git, Node, Python, CLI, skills
bash daemons/run-watchdog.sh --once  # Test the watchdog daemon
```

Expected: all green. See [INSTALL.md](INSTALL.md) if not.

---

## Step 3: Launch Dashboard (Optional)

```bash
npx @matt82198/aesop dash  # Opens http://localhost:8770
```

Monitor waves in real-time. View logs, agents, heartbeats, backlog.

---

## Step 4: Run Your First Wave (in Claude Code)

### Priming
```
/power
```
Loads orchestrator brain, verifies system health, outputs next steps.

### Orchestrating
```
/buildsystem
```
Runs one complete iteration: ranks backlog → dispatches Haiku agents → verifies merges → checkpoints state → audits fleet. Typically 30 min–2 hours.

---

## Key Concepts

**Local + Claude Code**: Orchestrator runs in Claude Code; subagents are Haiku dispatched via `/buildsystem`. Daemons run locally (watchdog, dashboard).

**State survives wipes**: `STATE.md` and `BUILDLOG.md` are committed to git. Resume anytime.

**Cost**: ~$0.03–$0.05 per wave (1 Opus + 5–8 Haikus).

**No modification of your repos**: Each agent works in a sibling worktree. Primary tree stays clean.

---

## Next Steps

- [CONFIGURE.md](CONFIGURE.md) — Customize repos and ports
- [CONCEPTS.md](CONCEPTS.md) — Dispatch model and architecture
- [FIRST-WAVE.md](FIRST-WAVE.md) — Detailed expectations and monitoring
- [ANY-REPO.md](ANY-REPO.md) — Adapt to any codebase (no stack lock-in)
- [HOW-THE-LOOP-WORKS.md](HOW-THE-LOOP-WORKS.md) — Concrete walkthrough

**Troubleshooting**: [INSTALL.md#troubleshooting](INSTALL.md)
