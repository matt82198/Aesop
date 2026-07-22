<p align="center">
  <img src="https://raw.githubusercontent.com/matt82198/aesop/main/assets/logo.png" alt="Aesop" width="420">
</p>

<p align="center">
  <em>Autonomous Developer for Any Repository</em>
</p>

<p align="center">
  <a href="https://github.com/matt82198/aesop/actions/workflows/ci.yml"><img src="https://github.com/matt82198/aesop/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://www.npmjs.com/package/@matt82198/aesop"><img src="https://img.shields.io/npm/v/@matt82198/aesop" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-orange.svg" alt="License: PolyForm Strict 1.0.0 (source-available)"></a>
</p>

**Aesop** is a source-available autonomous developer that crawls into any repository and orchestrates intelligent work—**ranking tasks, dispatching parallel Haiku agents, verifying merges, auditing the work, and feeding the next iteration.**

What makes Aesop different: **durable state persists across multiple instances**, so your whole team uses one coordinated system. The state layer (`state_store/`) runs append-only events in SQLite (concurrent, transactional), rendered to git for checkpoints and hand-offs. Pair with [/power](#use-with-claude-code) (system init) and [/buildsystem](#core-concepts-and-operations) (the wave loop), and Aesop runs your delivery cycle—on any repository, any codebase shape, indefinitely. **This repo's own PRs are built by Aesop's own loop.** Dogfooding, not doctrine.

As of **0.1.0**, that loop has carried the project to an installable, tested, audited, and benchmarked stable release—the fleet running the wave loop on its own, under a human who sets goals and owns the outward gates. The claims below are backed by committed artifacts you can check, not adjectives. See [Milestone: it shipped itself](#milestone-it-shipped-itself-010).

**Cost-optimized multi-agent dispatch** (Haiku-first subagents, lean orchestrator) · **Durable state** (SQLite events + git exports, survives wipes) · **Observable machinery** (every agent run logged, every cost tracked) · **Live dashboard** (real-time fleet health at http://localhost:8770) · **Security gates** (secret-scan blocks pushes, CI validates each merge).

## Milestone: it shipped itself (0.1.0)

Aesop reached its first release candidate by running its own wave loop—**audit → parallel build → verify → merge-train**—across the backlog that produced it. This is the version where the load-bearing claims stopped being illustrations and became measurements. The word "autonomous" has a precise, deliberately narrow meaning here.

**What "autonomous" means here (and what it doesn't).** The *fleet* autonomously runs the wave loop: it ranks work, dispatches parallel Haiku workers on file-disjoint domains, verifies merges, and feeds the next wave from a closing audit. A *human* sets the goals and owns every outward gate—npm publish, tagged releases, and history rewrites all stay human-approved. It is a supervised loop, not an unsupervised agent, and not AGI. The true model-dispatch core runs inside the Claude Code harness, which lives outside this repo; what ships here is the harness around it—orchestration, guardrails, dashboard, and tooling.

The differentiator is not "an AI wrote code." It's that the credibility and safety claims come with receipts:

| Claim | Evidence (committed, checkable) | Honest caveat |
| --- | --- | --- |
| **Haiku is good enough for fleet judgment** | Across 39 held-out judgment tasks, Haiku scored **39/39** vs Opus **38/39** at ~1/3 the per-token cost — measured by a plain-Python scorer with no model in the grading loop. See [`bench/results/`](./bench/results/). | Curated set, **not** sampled from real fleet transcripts (N=39). The benchmark found *no* task where Opus beats Haiku — so it proves sufficiency for these shapes, not parity at the reasoning frontier. |
| **Audits don't hallucinate findings** | A full release audit was run with adversarial verification of every finding: **0 hallucinated issues**, closing the prior all-Haiku severity-inflation risk. | An internal audit, not a third-party one. |
| **Kill-switch actually stops the fleet** | The fleet-wide halt is wired into the live dispatch path and proven end-to-end — one signal **aborted a real wave with zero workers spawned**. See [`tools/halt.py`](./tools/halt.py). | Operator-triggered; it is a manual brake, not an autonomous safety monitor. |
| **A cost ceiling brakes runaway spend** | Dispatch halts when a per-wave budget is exceeded. See [`tools/cost_ceiling.py`](./tools/cost_ceiling.py). | A brake on a *configured* ceiling, **not yet tied to live token spend**. |
| **The package installs and reproduces** | A **~409 kB** npm tarball (measured via `npm pack`) builds and validates from a fresh clone in CI. See [docs/reproduce.md](./docs/reproduce.md). | UI browser-proofs (Playwright) and real-model runs need local setup / API keys; they don't run in the offline reproduce job. |

**Nobody outside this project has reproduced these results yet.** The evidence is committed so a skeptical reader can check it — that transparency is the point, not a substitute for independent replication. For the full, unhedged account of what is and isn't proven, read [docs/autonomous-swe.md](./docs/autonomous-swe.md) and the ["Honest limits" section of the release notes](./RELEASE-NOTES.md#honest-limits).

## Core Concepts and Operations

### What /power Does

`/power` initializes Aesop into a fresh repository. It:
- Loads your orchestrator brain (cardinal rules, domain map, team memory, system state)
- Verifies the system is healthy (filesystem, git, API keys, watchdog)
- Outputs a health brief and next-step recommendations

Run `/power` at the start of each session when using Claude Code. It's idempotent—safe to run multiple times. Setup once:

```bash
cp -r skills/power/ ~/.claude/skills/power/
```

Then in Claude Code, type `/power` to initialize.

### What /buildsystem Does

`/buildsystem` runs **one complete wave cycle** of the autonomous delivery loop. It:
1. **Ranks** the backlog (priority, dependencies, team affinity)
2. **Dispatches** parallel Haiku agents on file-disjoint domains (tests, build, docs, UI, review, etc.)
3. **Verifies** each merge (CI, security scans, audit spot-checks)
4. **Checkpoints** (STATE.md + BUILDLOG.md committed to git, survive wipes)
5. **Audits** fleet health and feeds next backlog (monitor signals, signal collectors, findings)

This is **not** a one-off fix or a single pass—it's the repeatable loop that runs your delivery cycle indefinitely, with each wave learning from the prior audit. You can run `/buildsystem` once per wave (typically 30 min–2 hours per wave depending on backlog size and scope).

See [docs/HOW-THE-LOOP-WORKS.md](./docs/HOW-THE-LOOP-WORKS.md) for a concrete walkthrough of one complete cycle.

### Team State & Multi-Instance Vision

**Current Status (0.1.0)**: Single-instance proven. A team uses Aesop by designating one operator who runs the wave loop. State is durably checkpointed in git (STATE.md, BUILDLOG.md, tracker.json exports).

**In Design**: Multi-instance coordination via the state_store substrate. The event-sourced SQLite layer (`state_store/`) is production-ready but currently opt-in. A future release will enable multiple Aesop instances (e.g., per-team subgroups, geographic regions, or specialized fleets) to coordinate around a single source of truth—a Postgres-backed event log, with git as a diffable export. See [docs/TEAM-STATE.md](./docs/TEAM-STATE.md) (design in progress) for the vision and current architecture decisions.

## Why Aesop?

Multi-agent AI fleets hit two walls: all-Opus orchestrators cost $10k+ per wave, and machine crashes lose state—losing work and context on restart. Aesop solves both:

- **Haiku-first dispatch** cuts costs to ~1/3 of Opus (Haiku subagents, Opus orchestrator).
- **Durable state** (SQLite event log + git-rendered exports) survives machine wipes with zero data loss and enables team/multi-instance coordination.
- **Portable orchestration** works on any repository; no custom agents per repo needed.

```
ranked backlog
     ↓
parallel haiku fleet (worktree-isolated)
  [test] [build] [docs] [ui] [review] ...
     ↓
integration-branch merge train
     ↓
checkpoint (STATE.md + BUILDLOG.md)
     ↓
audit + fleet-ops monitoring
     ↓
(feeds next wave's backlog)
```

(See [assets/wave-cycle-diagram.txt](./assets/wave-cycle-diagram.txt) for the cycle reference.)

## What You Get

- **Parallel Haiku fleets** — Cheap, scoped subagents dispatch in parallel; orchestrator stays lean on main thread.
- **Durable state** — STATE.md + BUILDLOG.md checkpoints survive machine wipes; re-sync on resume, zero data loss.
- **Observable & auditable** — Every agent run logged, every cost tracked, every security event triaged.
- **Self-healing watchdog** — Runs every 150s: backs up work, scans for secrets, detects drift, restores on reboot.
- **Live web dashboard** — Real-time fleet health, security alerts, work-item kanban at `http://localhost:8770`.
- **Secret-scan gates** — Pre-push hook blocks leaks; audit trail logged. Pair with GitHub branch protection for enforcement.
- **Read-only MCP Fleet Server** — Expose fleet status, active agents, work items, and cost metrics to Claude Code (fleet_status, fleet_agents, fleet_tracker, fleet_cost tools). See [mcp/CLAUDE.md](./mcp/CLAUDE.md) for setup.
- **Multi-model portability** — AgentDriver abstraction decouples the wave loop from Claude Code; drivers for Claude Code, OpenAI-compatible backends (Ollama, OpenRouter), and Codex. Honest verification tiers: weaker backends get more checking. See [driver/README.md](./driver/README.md).
- **Self-diagnosing npm publish** — OIDC token generation and publish reliability verified on each release; workflow surfaces diagnostics inline.
- **Verification & quality tooling** — mutation_test.py for test-quality assessment, defect_escape.py for first-try-green telemetry, held-out benchmark for robustness, and adversarial review to break and harden the orchestration loop.

## Get Started (3 steps, 5 min)

**Note:** Aesop's first stable release is `0.1.0`, published to npm under the `latest` tag — a plain `npx @matt82198/aesop` or `npm install @matt82198/aesop` pulls it. Earlier prereleases remain available under the `@rc` and `@beta` tags.

### Quickest path: npx scaffold

```bash
npx @matt82198/aesop my-fleet \
  --name "my-api" \
  --repos "/path/to/repo1,/path/to/repo2"
cd my-fleet

# Start the daemon
bash daemons/run-watchdog.sh --once

# Launch dashboard on localhost:8770
python ui/serve.py
```

Pre-push hook auto-installed. See [docs/HOOK-INSTALL.md](./docs/HOOK-INSTALL.md) for branch protection pairing.

**State Store**: Aesop uses an event-sourced SQLite WAL backing store (`state_store/`) for durable state persistence. The `tracker.json` file is automatically re-rendered as an export for git-friendly checkpointing. Mutations follow a dual-path model: append new events via the StateAPI, then rendered exports for external consumption.

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
watchdog backs up & gates        Heartbeat, secret-scan, push to backup branch; merging is orchestrator/human-driven
  ↓
monitor/collect-signals.mjs     Audits orchestration health, feeds next wave's backlog
  ↓
STATE.md + BUILDLOG.md          Git-committed, survives machine wipes
```

See [docs/DISPATCH-MODEL.md](./docs/DISPATCH-MODEL.md) for cost analysis and parallel patterns.

<!-- STATS:START -->

## Aesop builds itself

Aesop is built entirely by its own `/buildsystem` wave cycle—running parallel Haiku fleets across ranked backlog items, verifying merges, auditing orchestration health. These stats are the receipts: all numbers computed LIVE from git, verified by anyone who clones.

| Metric | Value |
| --- | --- |
| Merged PRs | 190 <!-- metrics-verified: self_stats.py (git log) --> |
| Total Commits | 635 <!-- metrics-verified: self_stats.py (git log) --> |
| Project Age | 9 days <!-- metrics-verified: self_stats.py (git log) --> |
| Waves | 30 <!-- metrics-verified: self_stats.py (git log) --> |
| Insertions + Deletions | 124,759 <!-- metrics-verified: self_stats.py (git log) --> |
| Files Tracked | 416 <!-- metrics-verified: self_stats.py (git log) --> |
| Distinct Co-authors | 9 <!-- metrics-verified: self_stats.py (git log) --> |

<!-- STATS:END -->






## Recommended Agents

Aesop pairs well with the open-source catalog of ~130 community-authored specialized agent definitions (TDD orchestrators, security reviewers, performance engineers, etc.). For optimal results, install agents from the upstream source and pair them with Aesop's cost-optimized Haiku dispatch. This is optional; Aesop works standalone with general-purpose Claude Code agents.

## Use with Claude Code

If you're using **Claude Code**, invoke `/power` at the start of each session. It loads your orchestrator brain (cardinal rules, domain map, team memory, system state) and outputs a health brief. Setup once:

```bash
# Copy the /power skill and optional /healthcheck skill
cp -r skills/power/ ~/.claude/skills/power/
cp -r skills/healthcheck/ ~/.claude/skills/healthcheck/
```

Then in Claude Code, type `/power` or `/buildsystem` to start a wave cycle. Use `/healthcheck` to audit fleet machinery health before running waves. See [skills/power/SKILL.md](./skills/power/SKILL.md) and [skills/healthcheck/SKILL.md](./skills/healthcheck/SKILL.md) for details.

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

**Host-header validation** in the dashboard UI handler prevents HTTP header injection attacks; all requests are validated against the configured origin. Private brain (`~/.claude`) is never committed to this repo. Keep `aesop.config.json` git-ignored. Implement `tools/secret_scan.py` with your security rules. See [docs/HOOK-INSTALL.md](./docs/HOOK-INSTALL.md) for setup.

## Dashboard (Wave-14 Rewrite)

The dashboard is a **React 18 + Vite + TypeScript** single-page app with four hash-routed views:

### Viewing the Dashboard
```bash
python ui/serve.py
```
Opens `http://localhost:8770` — live fleet health, security alerts, work-item kanban, cost analytics.

### Architecture
- **Backend**: Python stdlib HTTP server (`ui/handler.py`) serves the built React app + JSON/SSE APIs (`/api/state`, `/api/cost`, `/events`).
- **Frontend**: `ui/web/` (React app) is built to `dist/` (committed to git) and served as static files by the Python server.
- **CSRF protection**: Token injected into `dist/index.html` via sentinel substitution; mutations gated by `/submit` and `/api/tracker` endpoints.

### Development
```bash
cd ui/web
npm install
npm run dev        # Vite dev server with API proxy to http://localhost:8770
npm run build      # Build to dist/ (commit the dist/)
```

The dev server proxies `/data`, `/api`, `/events`, `/agent`, `/submit` to the Python backend on :8770, so the frontend can develop against live APIs.

### Views
- **Overview**: Fleet agents, security alerts, recent events.
- **Work** (`#/work`): Tracker kanban (4 lanes: proposed/ranked/in-progress/done), audit backlog progress.
- **Activity** (`#/activity`): Agent timeline, main-thread message tail (live reasoning).
- **Cost** (`#/cost`): Per-model spend/tokens, per-day bar chart, verdict scorecard (success/failure rates).

## Extending Aesop

**Custom signal collectors**: Edit `monitor/collect-signals.mjs` to add domain-specific health checks.

**Custom watchdog hooks**: Edit `daemons/backup-fleet.sh` to run linters, integrate with your CI, or customize secret-scan logic.

**Dashboard components**: Add React components in `ui/web/src/components/` or new views in `ui/web/src/views/`. Rebuild and commit `dist/`.

## Troubleshooting

| Issue | Check |
|-------|-------|
| Watchdog doesn't start | `state/FLEET-BACKUP.log` for errors; verify `AESOP_ROOT` is set |
| Dashboard shows "unavailable" | Install Node.js v18+; check `dash-extra.mjs` is in sync |
| Secret-scan blocks push | Add suppression to `tools/secret_scan.py`; no auto-bypass (by design) |
| Monitor doesn't start | Verify Node.js on PATH; check `monitor/BRIEF.md` for logs |

## Documentation

**Adopter journey** (start here):
- [docs/INSTALL.md](./docs/INSTALL.md) — Install Aesop and verify setup
- [docs/CONFIGURE.md](./docs/CONFIGURE.md) — Configure repos, ports, and brain root
- [docs/FIRST-WAVE.md](./docs/FIRST-WAVE.md) — Run your first `/power` → `/buildsystem` cycle
- [docs/CONCEPTS.md](./docs/CONCEPTS.md) — Key concepts (dispatch, state, security, governance) with links to deep dives
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — System architecture diagram and components

**Operational reference**:
- [docs/HOW-THE-LOOP-WORKS.md](./docs/HOW-THE-LOOP-WORKS.md) — Concrete walkthrough of one wave cycle
- [docs/DISPATCH-MODEL.md](./docs/DISPATCH-MODEL.md) — Cost analysis, dispatch patterns, scaling
- [docs/CHECKPOINTING.md](./docs/CHECKPOINTING.md) — STATE.md + BUILDLOG.md lifecycle, recovery on wipe
- [docs/CARDINAL-RULES.md](./docs/CARDINAL-RULES.md) — 10 foundational principles
- [docs/GOVERNANCE.md](./docs/GOVERNANCE.md) — Single-writer files, heartbeat protocol, AUTO/PROPOSE tiers
- [docs/RELIABILITY.md](./docs/RELIABILITY.md) — Reliability guarantees, pride bar, inputs-always-outputs
- [docs/HOOK-INSTALL.md](./docs/HOOK-INSTALL.md) — Secret-scan and branch protection setup

**For specific tasks**:
- [docs/FORENSICS.md](./docs/FORENSICS.md) — Debug agent failures (git-bisectable)
- [docs/RESTORE.md](./docs/RESTORE.md) — Reconstitute Aesop on a new machine
- [docs/PUBLISHING.md](./docs/PUBLISHING.md) — Release Aesop to npm
- [docs/autonomous-swe.md](./docs/autonomous-swe.md) — The 0.1.0-rc.1 milestone told honestly: what "autonomous SWE" means here, the evidence behind each claim, and the limits the project owns
- [docs/case-study-portfolio.md](./docs/case-study-portfolio.md) — How Aesop built its own portfolio site; full audit trail and cost breakdown
- [docs/TEAM-STATE.md](./docs/TEAM-STATE.md) — Multi-instance and team coordination via state_store (design in progress)

See [CHANGELOG.md](./CHANGELOG.md) and [RELEASE-NOTES.md](./RELEASE-NOTES.md) for release notes.

## Contributing

Aesop is **source-available** under the PolyForm Strict License 1.0.0, which does not permit modification or redistribution — so outside code patches can't be accepted as merged contributions. That said, **feedback is genuinely welcome**:

- **Issues and bug reports** — tell us what's broken or confusing.
- **Discussion and ideas** — feature requests, design critiques, use-case questions.

The repo develops itself via its own `/buildsystem` loop; code changes are made by the maintainer at their discretion, or by prior arrangement. See [CONTRIBUTING.md](./CONTRIBUTING.md) for details.

## License

**Source-available** under the [PolyForm Strict License 1.0.0](./LICENSE). You may read, run, and use the software for any permitted purpose, but **modification and redistribution are not permitted**. See [`LICENSE`](./LICENSE) for the full terms and the definition of permitted (noncommercial and personal) purposes.

Copyright 2026 Matt Culliton.

## References

- [Anthropic Claude API docs](https://docs.anthropic.com)
- [Claude Code CLI](https://github.com/anthropics/claude-code)
- [Git docs](https://git-scm.com/doc)

---

**Aesop**: Autonomous developer for any repository, built by Aesop itself. May your orchestrator be wise and your subagents swift.
