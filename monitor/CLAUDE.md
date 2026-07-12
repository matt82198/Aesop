# Aesop Monitor — CLAUDE.md

**Purpose:** Continuous background signal collector and refinement proposer — watches fleet machinery health deterministically (Node.js, no LLM), emits cycle snapshots, and proposes rule changes via append-only PROPOSALS.md; GOAL IS FIXED (improve machinery, never mission).

## Files

- **CHARTER.md** — Governance document; defines 10 signal checks, action tiers (AUTO/PROPOSE), outputs, single-instance guard, single-writer discipline. Read-only; behavior changes only via PROPOSALS/behavioral-PR flow.
- **collect-signals.mjs** — Deterministic signal collector (Node.js built-ins only); emits BRIEF.md + SIGNALS.json each cycle; reads config from env or aesop.config.json.
- **BRIEF.md** — Human-readable cycle snapshot (heartbeats, git state, memory freshness, log rotation, junk sprawl, stray scripts, security alerts, respawn watch, cost cadence, unreviewed prompts); overwritten each cycle; runtime.
- **SIGNALS.json** — Machine-readable metrics (same signal keys as BRIEF); JSON; overwritten each cycle; runtime.
- **PROPOSALS.md** — Structured inbox for user approval (idempotent per signal key, append-only); never edited by monitor after emission; tracks respawn-watch-breach, stray-repo-scripts, security-alerts-high-med, stale-memory-files; gitignored.
- **ACTIONS.log** — Append-only log of AUTO tier actions taken (heartbeat updates, log rotation invokes, junk quarantine); runtime; gitignored.
- **.monitor-heartbeat** — Epoch timestamp (line 1) for single-instance liveness check (<300s = skip cycle); runtime; gitignored.
- **.signal-state.json** — Sidecar state (cycleCount, etc.); runtime; gitignored.

## Contracts

**Signal keys collected:** heartbeats, git, memory, logs, junk, strayRepo, alerts, respawnWatch, costTick, unreviewedPrompts. Outputs: BRIEF.md (human), SIGNALS.json (machine); both runtime/gitignored. PROPOSALS.md (tracked, append-only); ACTIONS.log (runtime/gitignored).

**AUTO tier actions** (apply immediately, log to ACTIONS.log): heartbeat checks (read-only); log rotation (invoke rotate_logs.py if available, fail-open); heartbeat write (.monitor-heartbeat update); junk script quarantine (move old temp .py/.mjs to monitor/quarantine/ + manifest).

**PROPOSE tier actions** (write to PROPOSALS.md, await user approval): rule changes, agent config changes, deletions outside monitor/quarantine/, orchestration policy changes.

**Idempotency rule:** Proposal emission keyed on signal key (e.g., 'respawn-watch-breach'); only emitted if not already present in PROPOSALS.md (check: `**Signal:** <key>` exists). Idempotent + append-only; safe to run repeatedly.

## Invariants & Gotchas

- CHARTER.md is authority; monitor logic is faithful to it; never edit CHARTER.md or collect-signals.mjs directly — propose via PROPOSALS.md.
- Goal is FIXED (improve machinery, never mission); if monitor thinks goal should change, it writes note to PROPOSALS.md and stops.
- Single-instance guard via .monitor-heartbeat; if <300s old, skip cycle.
- Single-writer discipline: only monitor writes BRIEF.md, SIGNALS.json, ACTIONS.log, .monitor-heartbeat, .signal-state.json.
- Config from env (AESOP_ROOT, BRAIN_ROOT, SCRIPTS_ROOT, TEMP_ROOT) or aesop.config.json; falls back to safe defaults.
- Robust to missing files; treats missing dirs/logs as empty, never crashes.
- Node.js only (no Python, no LLM, no cloud); deterministic + cheap.

See ../CLAUDE.md for fleet context (watchdog, dash, daemons, tools, docs).

## Recursion Signal

**No** — monitor is self-contained single-concern domain; 10 signal checks + 1 proposal emitter; no sub-areas warrant separate CLAUDE.md.
