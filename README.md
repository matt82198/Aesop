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

**Aesop** is an open-source orchestration harness for Claude Code that builds itself. It runs a `/buildsystem` wave cycle—ranking a backlog, fanning out parallel Haiku agents (1/3 the cost of Opus), watchdogging them, verifying merges, then feeding the next wave via audit + ideation + fleet-ops monitoring. **This repo's own PRs are built by Aesop's own loop.** Dogfooding, not doctrine.

What you get: **cost-optimized multi-agent dispatch** (Haiku-first subagents, lean orchestrator), **durable state** (git-committed checkpoints survive wipes), **observable machinery** (every agent run logged, every cost tracked), **live dashboard** (real-time fleet health at http://localhost:8770), and **security gates** (secret-scan blocks pushes, CI validates each merge).

## What You Get

- **Parallel Haiku fleets** — Cheap, scoped subagents dispatch in parallel; orchestrator stays lean on main thread.
- **Durable state** — STATE.md + BUILDLOG.md checkpoints survive machine wipes; re-sync on resume, zero data loss.
- **Observable & auditable** — Every agent run logged, every cost tracked, every security event triaged.
- **Self-healing watchdog** — Runs every 150s: backs up work, scans for secrets, detects drift, restores on reboot.
- **Live web dashboard** — Real-time fleet health, security alerts, work-item kanban at `http://localhost:8770`.
- **Secret-scan gates** — Pre-push hook blocks leaks; audit trail logged. Pair with GitHub branch protection for enforcement.

## Get Started (3 steps, 5 min)

**Note:** Aesop is in beta. Install the `@beta` tag for the latest prerelease (0.1.0-beta.1+).

### Quickest path: npx scaffold

```bash
npx @matt82198/aesop@beta my-fleet \
  --name "my-api" \
  --repos "/path/to/repo1,/path/to/repo2"
cd my-fleet

# Start the daemon
bash daemons/run-watchdog.sh --once

# Launch dashboard on localhost:8770
python ui/serve.py
```

Pre-push hook auto-installed. See [docs/HOOK-INSTALL.md](./docs/HOOK-INSTALL.md) for branch protection pairing.

### Or: git clone for hacking

```bash
git clone https://github.com/matt82198/aesop ~/aesop
cd ~/aesop
cp aesop.config.example.json aesop.config.json
# Edit paths and repos

export AESOP_ROOT=$HOME/aesop
bash $AESOP_ROOT/daemons/run-watchdog.sh --once
python ui/serve.py
```

## How It Works

```
daemons/run-watchdog.sh         Every 150s: backs up work, scans secrets, detects drift
  ↓
orchestrator (via Claude Code)  Reads backlog, dispatches Haiku subagents in parallel
  ↓
parallel Haiku fleet            Tiny, scoped domains (tests, build, review, docs, etc.)
  ↓
watchdog verifies & merges      GREEN → push to main
  ↓
monitor/collect-signals.mjs     Audits orchestration health, feeds next wave's backlog
  ↓
STATE.md + BUILDLOG.md          Git-committed, survives machine wipes
```

See [docs/DISPATCH-MODEL.md](./docs/DISPATCH-MODEL.md) for cost analysis and parallel patterns.

## Use with Claude Code

If you're using **Claude Code**, invoke `/power` at the start of each session. It loads your orchestrator brain (cardinal rules, domain map, team memory, system state) and outputs a health brief. Setup once:

```bash
# Copy the /power skill
cp -r skills/power/ ~/.claude/skills/power/
```

Then in Claude Code, type `/power` or `/buildsystem` to start a wave cycle. See [skills/power/SKILL.md](./skills/power/SKILL.md) for details.

## Core Principles

1. **Haiku-first dispatch** — Subagents always cheap; orchestrator stays lean on main thread.
2. **Durable state** — STATE.md + BUILDLOG.md survive wipes; re-sync on resume.
3. **Observable** — Every agent run logged, every cost tracked, every security event triaged.
4. **TDD-first** — Fail tests before implementation; one Haiku per scoped domain.
5. **Never wait** — Dispatch work in parallel; connect with heartbeats, not polling.
6. **Push discipline** — feature/* branches only; secret-scan gates every push.

Read [docs/CARDINAL-RULES.md](./docs/CARDINAL-RULES.md) for the full text.

## Requirements

- Claude Code CLI (v0.1+)
- Git (v2.40+)
- Bash (v4+) or Git Bash on Windows
- Node.js (v18+) for dashboard and monitor
- Python (v3.10+) for log rotation and secret-scan
- jq (optional) for TUI dashboard

## Scaling Cheaply

The **dispatch model** fans work across parallel Haiku subagents (each 1/3 the cost of Opus). The orchestrator stays lean on the main thread, coordinating via durable STATE.md. Result: ~25% the cost of an all-Opus fleet.

**Action tiers**: AUTO (immediate, logged) for read-only checks and appends; PROPOSE (staged in `monitor/PROPOSALS.md`) for changes requiring approval. See [docs/GOVERNANCE.md](./docs/GOVERNANCE.md).

## Security

The pre-push hook (`hooks/pre-push-policy.sh`) enforces branch discipline and secret scanning locally. It is bypassable (use `--no-verify` to skip), so **pair it with GitHub branch protection** for real enforcement:

```
Settings > Branches > main
  ✓ Require pull request reviews
  ✓ Require status checks to pass
  ✓ Dismiss stale PR approvals
  ✓ Restrict pushes to (Admins only)
```

Private brain (`~/.claude`) is never committed to this repo. Keep `aesop.config.json` git-ignored. Implement `tools/secret_scan.py` with your security rules. See [docs/HOOK-INSTALL.md](./docs/HOOK-INSTALL.md) for setup.

## Extending Aesop

**Custom signal collectors**: Edit `monitor/collect-signals.mjs` to add domain-specific health checks.

**Custom watchdog hooks**: Edit `daemons/backup-fleet.sh` to run linters, integrate with your CI, or customize secret-scan logic.

**Dashboard panels**: Edit `ui/serve.py` or `dash/watchdog-gui.sh` to surface your metrics.

## Troubleshooting

| Issue | Check |
|-------|-------|
| Watchdog doesn't start | `state/FLEET-BACKUP.log` for errors; verify `AESOP_ROOT` is set |
| Dashboard shows "unavailable" | Install Node.js v18+; check `dash-extra.mjs` is in sync |
| Secret-scan blocks push | Add suppression to `tools/secret_scan.py`; no auto-bypass (by design) |
| Monitor doesn't start | Verify Node.js on PATH; check `monitor/BRIEF.md` for logs |

For deeper docs, see `docs/`:
- `CARDINAL-RULES.md` — full 10 principles
- `DISPATCH-MODEL.md` — cost analysis and patterns
- `CHECKPOINTING.md` — how STATE.md + BUILDLOG.md survive wipes
- `GOVERNANCE.md` — AUTO/PROPOSE tiers

See [CHANGELOG.md](./CHANGELOG.md) for release notes.

## Contributing

Aesop welcomes improvements. The repo uses its own `/buildsystem` loop for development—PRs from `feature/*` branches are built, tested, and merged by Aesop itself. To contribute:

1. Fork and create a `feature/*` branch.
2. Write failing tests first (TDD).
3. Open a PR; Aesop's wave cycle will verify and merge.

Maintain the core principles: **Haiku-first** subagents, **lean** orchestrator, **durable** state, **observable** machinery.

## License

MIT. See `LICENSE`.

## References

- [Anthropic Claude API docs](https://docs.anthropic.com)
- [Claude Code CLI](https://github.com/anthropics/claude-code)
- [Git docs](https://git-scm.com/doc)

---

**Aesop**: Fable-fleet orchestration, built by Aesop itself. May your orchestrator be wise and your subagents swift.
