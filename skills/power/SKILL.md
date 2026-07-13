---
name: power
description: Prime the "filesystem brain" — load all operating rules, behaviors, the multi-agent dispatch model, memory, and the current project's semantics from disk. Report a compact primed brief with system health and next steps.
version: 1.0.0
---

# Power — prime the filesystem brain

Everything that governs how I should behave lives on disk. This skill reads it, internalizes it,
and reports a compact "primed" summary — **without inflating context** (code is read via subagents
that return briefs, not dumped raw).

The principle: **all rules can be abstracted to consistent agent behavior.** Rules are files;
reading them = becoming the agent the files describe.

**Scope: this is a priming skill for aesop orchestration itself** — rules, dispatch model, memory,
machinery health. Running it does NOT imply any particular project is being worked on. Project
state loads only when the session is actually resuming that project (step 3); deferred projects
are rolled up to counts, never item-by-item — and their repos/daemons are left untouched.

## Procedure (run in order)

### 1. Load global rules + dispatch model
Read these directly (they are small and authoritative):
- `~/.claude/CLAUDE.md` — the **cardinal rules** (autonomous continuation, dispatch model, 
  durable checkpointing, build env). These override defaults.
- Any project-local `CLAUDE.md` in the current working directory and its parents.

Then run the **brain integrity check**: `~/.claude` should be a git repo (if you version it). 
Check `git -C ~/.claude status --porcelain` and ahead/behind vs origin:
- Deliberate uncommitted rule/hook/skill/memory changes → commit + push now (gated by 
  `python <project-root>/tools/secret_scan.py --staged`);
- **Unexpected** modifications or deletions → report as alert — stop, diff against remote, restore 
  before continuing (core defense: don't let tooling shadow your rules).

Also check for unactioned entries in `~/.claude/PROPOSALS.md` or similar and surface a 
one-line summary of each in the primed report.

Internalize the **dispatch model** and apply it for the rest of the session. Document
the dispatch model's key invariants locally (in your private repo's `CLAUDE.md`, 
if you version `~/.claude`), for example:
- **Subagents model** (Haiku vs specialists vs orchestrator tier)
- **Parallelism defaults** (e.g., fan out 6–8 Haikus per domain)
- **TDD-first discipline** and checkpointing (STATE.md, BUILDLOG.md)
- **Observable machinery**: every action logged, every cost tracked

### 2. Load memory
- Read `~/.claude/memory/MEMORY.md` (the index, or use your configured path).
- For any memory entry whose one-line hook is relevant to the current task/project, 
  read that memory file.
- Treat recalled memories as background context that reflects when they were written — 
  **verify any file/flag/path they name still exists before relying on it.**

### 3. Load the active project's state
If working inside (or resuming) a known project, read its durable checkpoint first:
- Look for a `STATE.md` and `BUILDLOG.md` in the project root or a handoff folder.
- `STATE.md` is the source of truth for intent, locked decisions, contracts, and **NEXT STEPS**.
- Re-sync from disk (git log, file state) — never trust stale assumptions.

### 4. Codebase semantics — already-primed vs first-time init
**First check whether this codebase has been primed before**: does it already carry its scoped
`.md` layer (a project-root `CLAUDE.md`, domain `CLAUDE.md` units, a `STATE.md`)?

- **Already primed** (has `CLAUDE.md`s and optionally `STATE.md`): do NOT re-investigate the code. 
  The `.md` layer IS the persisted semantic memory — the project `CLAUDE.md`s are sufficient; 
  the codebase is simply **ready to work**. Only re-scan a specific domain if its `CLAUDE.md` 
  is contradicted by on-disk reality (then fix the `.md`, which is the bug).
- **First time / not primed** (no scoped `.md`s found): run **init-prime** — fan out Haiku 
  subagents to read the whole codebase (briefs only, never raw dumps) and **autonomously write 
  the scoped `.md` layer it needs**:
  - a project-root `CLAUDE.md`: purpose, build/run commands + toolchain, top gotchas
  - smallest self-contained **domain `CLAUDE.md` units** (minimal, never lossy) — module layout, 
    key contracts, domain logic, non-obvious invariants
  - a `STATE.md` checkpoint seed if the work warrants it
  
  Commit + push the new `.md`s (secret-scan gated). Every future `/power` on that codebase 
  then takes the already-primed fast path.

### 5. Report "primed" (compact)
Output a short brief, not a wall of text:

- **Drain the UI inbox first** (if configured in `aesop.config.json`): run 
  `python <project-root>/tools/inbox_drain.py pending`. If items exist, surface each under 
  a **"QUEUED FROM DASHBOARD"** heading as `[ISO-ts] text` one-liners. Mark them processed 
  (`python <project-root>/tools/inbox_drain.py mark-all`) after actioning.
- **Health line first**: run `python <project-root>/tools/power_selftest.py` and lead with its 
  `POWER-SELFTEST:` line (hooks, brain push state, heartbeats, decisions, scanner state).
  Bullet anything non-OK.
- **Open decisions**: surface each ACTIVE line of any decisions/proposals file and any 
  unactioned inbox entries as one-liners (rolled-up counts for deferred items, never item-by-item).
- **Rules loaded**: dispatch model + any project-specific overrides in one or two lines.
- **Project**: name, purpose, status, repo, key paths.
- **Semantics**: the domain model + main flow in a few bullets.
- **Gotchas**: the verified ones that change how I act.
- **Next steps**: from `STATE.md`, ready to execute (autonomously, per the dispatch model).

### 6. Project app launch (if applicable)
After reporting primed, bring the active project's runnable app up in the BACKGROUND if it has one.
Make it **idempotent**: if the port is already serving a healthy instance, skip the start and 
just report the URL.

**Pattern** (project adopters fill in their own):
- Define a `run` skill or script in your project (or use an existing `start`/`run` command).
- Detect if the service is already healthy (e.g., `curl -s -o /dev/null -w '%{http_code}' http://localhost:PORT/`).
- If healthy (200), skip startup and just report the URL.
- If not healthy, start the service in the background via Bash with `run_in_background: true`.
- Poll readiness WITHOUT blocking sleep: use curl retries or a cheap probe loop.
- Report the URL + background task ID so it can be stopped on request.

**DO NOT** hardcode personal app paths (e.g., Spring Boot repos, IDEs, personal tools). 
Instead, document in your project's `CLAUDE.md` how to launch the app, and reference that 
in your local version of this skill or a project-specific override.

### 6b. Machinery health — orchestration monitor (optional)
If your project uses an orchestration monitor, spin up a **background Haiku agent** that:
1. Collects health signals (cheap, deterministic)
2. Reads only that brief and acts per a charter — AUTO-applies safe refinements and stages 
   rule/behavior changes to a `PROPOSALS.md` for review
3. Self-paces via ScheduleWakeup and beats a heartbeat

Skip if `.monitor-heartbeat` is already <300s old. Announce its task id so it can be paused/stopped.

### 7. Standing dev loops (optional; only when actively developing)
If the session is doing active development (writing/changing code — not just answering questions),
keep these background loops running continuously. They are the "tail": cheap, persistent, 
append-only, and never inflate the main context.

**Patterns** (project adopters fill in their own):

1. **Build/status + backup watchdog** (background bash loop) — appends timestamped git/test/build
   snapshots. For example, if your project has a `daemons/` folder with a `run-watchdog.sh`, 
   launch that via Bash with `run_in_background: true` and let it beat a heartbeat so you know 
   it is live. Stop with TaskStop when development pauses.

2. **Memory keeper** (Haiku, background) — as new decisions, contracts, or gotchas emerge, 
   updates the relevant memory files compactly (one fact per memory; never bloat). Re-invoke 
   via SendMessage to keep context.

3. **Continuous QA loop** — after each feature reaches a checkpoint: **Haiku reviews → 
   Haiku bugfixes → Haiku lint/format**, looping until the build is green and review is clean, 
   with **Opus orchestrator final-catch** before merge. TDD-first: failing tests before code.

4. **Tail-drift alignment** (Haiku, background) — periodically checks in-flight agents' output 
   against their domain `CLAUDE.md` contract, and realigns anything drifting.

5. **Hung-Haiku watchdog** (orchestrator's main thread, NOT a subagent) — keep watching every 
   spawned Haiku for stalls. On hang: TaskStop it and relaunch from checkpoint or respawn.

Launch any that aren't already running; **stop them with TaskStop when development pauses**.

Mechanism: use background `Agent` (run_in_background) for keeper/drift loops, `Monitor` for 
the watchdog, and self-pace longer cycles with `/loop` skill or `ScheduleWakeup`. 
Always announce which loops were started (and their task IDs) so they can be paused/stopped.

## Notes
- If no project context exists yet, steps 1–2 still apply; skip 3–4 and say so.
- Steps 1–5 always run on `/power`; **step 6 (launch app) runs only if the active project has one**;
  **step 6b (monitor) runs only if configured**; step 7 (dev loops) runs only during active development.
- Prefer subagents for anything large; the goal is a *brain*, not a *dump*.
- After priming, proceed under the dispatch model (continue approved work autonomously; stop only 
  for genuine decisions or unauthorized outward/destructive actions).
