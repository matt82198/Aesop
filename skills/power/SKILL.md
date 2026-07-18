---
name: power
description: Initialize Aesop into ANY repo (first-run) or prime the orchestration brain (already-primed). Loads rules, memory, and project state; writes CLAUDE.md layer for unprimed repos.
version: 2.0.0
---

# Power — Initialize or Prime the Orchestration Brain

This skill makes Aesop work in ANY repository — either initializing a new codebase for the first time (init-prime) 
or loading an already-primed project's rules and state.

**Core principle**: All orchestration rules live on disk as readable `.md` files. This skill reads them, internalizes them,
and reports a compact "primed" summary — enabling autonomous dispatch under the loaded rules.

**Prerequisites**: Before running `/power`, the Aesop harness must be installed in the repository. Use the CLI to scaffold:
```bash
# Scaffold the Aesop harness (daemons, skills, tools, hooks) into your repo
npx @matt82198/aesop . --name "my-project"
# or run `npx @matt82198/aesop --help` for more options
```
The CLI automatically installs git hooks, copies all necessary directories, and generates initial config files. Then run `/power` to prime the orchestration brain.

---

## Quick Start: Two Paths

### Path 1: First Time? (Init-Prime)
If the target repository has **no CLAUDE.md layer** (i.e., no project-root `CLAUDE.md`, no domain `CLAUDE.md` units):

1. Run `/power` in the repository root (after CLI setup above)
2. Aesop will **automatically**:
   - Fan out read-only Haiku explorers to scan the codebase (briefs only, never raw dumps)
   - Write a project-root `CLAUDE.md` (purpose, build/run commands, gotchas)
   - Write smallest self-contained **domain `CLAUDE.md` units** (module layout, key contracts, invariants)
   - Write a `STATE.md` checkpoint seed if warranted
   - Commit + push the new `.md` layer (gated by secret-scan)
3. Every future `/power` run then takes the **fast path** (already-primed).

### Path 2: Already Primed?
If the repository **already has CLAUDE.md layer** (project-root + domain CLAUDE.md files ± STATE.md):

1. Run `/power` in the repository root
2. Aesop will **load the persisted semantic memory** from disk (no re-investigation needed)
3. Report a compact primed brief with health checks and next steps
4. Proceed under the loaded dispatch model

---

## Procedure (in order)

### 1. Detect priming status

**Check if this codebase has been primed before:**
- Does a project-root `CLAUDE.md` exist in the target repository root?
- Do any domain-scoped `CLAUDE.md` files exist (e.g., `src/CLAUDE.md`, `api/CLAUDE.md`)?
- Does `STATE.md` or similar checkpoint exist?

**If YES** → This codebase is **already primed**. Jump to **Step 2: Already-Primed Fast Path**.

**If NO** → This codebase is **unprimed**. Jump to **Step 2: Init-Prime Path**.

---

### 2A. Already-Primed Fast Path

For an already-primed codebase:

#### 2A.1 Load global rules + dispatch model
Read these directly (they are small and authoritative):
- `~/.claude/CLAUDE.md` — the **cardinal rules** (autonomous continuation, dispatch model, durable checkpointing, build env)
- Project-root `CLAUDE.md` in the current working directory

Then run the **brain integrity check**: if you version `~/.claude` as a git repo, check:
```bash
git -C ~/.claude status --porcelain
```
and ahead/behind vs origin. If there are:
- **Deliberate uncommitted rule/hook/skill/memory changes** → commit + push now (gated by `python <project-root>/tools/secret_scan.py --staged`)
- **Unexpected** modifications or deletions → report as alert, stop, diff against remote, restore before continuing

**Internalize the dispatch model** — document its key invariants locally in your session context (do not modify `.md` files during this step).

#### 2A.2 Load memory
- Read `~/.claude/MEMORY.md` (index) and cross-reference any entries relevant to the active project or session task
- For each recalled memory entry, read its full file
- **Verify any file/flag/path they name still exists before relying on it**

#### 2A.3 Load the active project's state
- Look for `STATE.md` or `BUILDLOG.md` in the project root
- `STATE.md` is the source of truth for intent, locked decisions, contracts, and **NEXT STEPS**
- Re-sync from disk (`git log`, file state) — never trust stale assumptions

#### 2A.4 Report "primed" (compact)
Output a short brief, not a wall of text:

- **Drain the UI inbox first** (if configured in `aesop.config.json`): run `python <project-root>/tools/inbox_drain.py pending` and surface each item as a one-liner under a **"QUEUED FROM DASHBOARD"** heading
- **Health line first**: run `python <project-root>/tools/power_selftest.py` and lead with its `POWER-SELFTEST:` line (hooks, brain push state, heartbeats, decisions, scanner state). Bullet anything non-OK.
- **Open decisions**: surface each ACTIVE line from any decisions/proposals file and unactioned inbox entries as one-liners
- **Rules loaded**: dispatch model + any project-specific overrides in one or two lines
- **Project**: name, purpose, status, repo, key paths
- **Semantics**: the domain model + main flow in a few bullets
- **Gotchas**: the verified ones that change how you act
- **Next steps**: from `STATE.md`, ready to execute (autonomously, per the dispatch model)

#### 2A.5 Project app launch (if applicable)
After reporting primed, bring the active project's runnable app up in the BACKGROUND if it has one.
Make it **idempotent**: if the port is already serving a healthy instance, skip the start and just report the URL.

**Pattern** (documented in your project's `CLAUDE.md`):
- Detect if the service is already healthy (e.g., `curl -s -o /dev/null -w '%{http_code}' http://localhost:PORT/`)
- If healthy (200), skip startup and just report the URL
- If not healthy, start the service in the background via Bash with `run_in_background: true`
- Poll readiness WITHOUT blocking sleep: use curl retries or a cheap probe loop
- Report the URL + background task ID so it can be stopped on request

**DO NOT** hardcode paths. Instead, document in the project's `CLAUDE.md` how to launch the app and reference that in this skill or a project-specific override.

#### 2A.6 Machinery health (optional)
If your project uses an orchestration monitor, spin up a **background Haiku agent** that:
1. Collects health signals (cheap, deterministic)
2. Reads the brief and acts per a charter — AUTO-applies safe refinements and stages rule/behavior changes to `PROPOSALS.md` for review
3. Self-paces via ScheduleWakeup and beats a heartbeat

Skip if `.monitor-heartbeat` is already <300s old. Announce its task id so it can be paused/stopped.

#### 2A.7 Standing dev loops (optional; only during active development)
If the session is actively developing (writing/changing code — not just answering questions),
keep these background loops running continuously. They are the "tail": cheap, persistent, append-only.

**Patterns** (documented in your project's `CLAUDE.md`):

1. **Build/status + backup watchdog** (background bash loop) — appends timestamped git/test/build snapshots. For example, if your project has a `daemons/` folder with a `run-watchdog.sh`, launch that via Bash with `run_in_background: true` and let it beat a heartbeat
2. **Memory keeper** (Haiku, background) — as new decisions, contracts, or gotchas emerge, updates relevant memory files compactly
3. **Continuous QA loop** — after each feature reaches a checkpoint: Haiku reviews → Haiku bugfixes → Haiku lint/format, looping until build is green and review is clean, with Opus orchestrator final-catch before merge
4. **Tail-drift alignment** (Haiku, background) — periodically checks in-flight agents' output against their domain `CLAUDE.md` contract, realigns if drifting
5. **Hung-Haiku watchdog** (orchestrator's main thread, NOT a subagent) — keep watching every spawned Haiku for stalls; on hang: TaskStop it and relaunch from checkpoint

Launch any that aren't already running; **stop them with TaskStop when development pauses**.

---

### 2B. Init-Prime Path

For an unprimed codebase, run the following steps **in order**:

#### 2B.1 Scan the target repository

Fan out read-only Haiku subagents to explore the codebase structure:
- **Haiku A** (30s): Repository structure, build system, entry points, main languages
- **Haiku B** (30s): Key libraries, frameworks, external dependencies
- **Haiku C** (30s): Testing strategy, CI/CD configuration, deployment targets
- **Haiku D** (30s): Known gotchas, non-obvious invariants, anti-patterns in the codebase

Each Haiku returns a **1-page brief** (never raw code dumps). Collect all four briefs.

#### 2B.2 Synthesize project-root CLAUDE.md

Using the four exploration briefs, **write a project-root `CLAUDE.md`** in the target repository. 
Include:

- **What**: 1-line project purpose + primary domain/stack
- **Key commands**: build, test, run, deploy (exactly as documented in the project)
- **Gotchas**: verified non-obvious facts that affect how you work
  - "Tests must run in isolation (no shared DB state)"
  - "Deploy requires manual approval in Slack"
  - "Docker build takes 5 minutes; cache aggressively"
- **Domain map**: 2-4 self-contained scopes, each mapping to one potential Haiku (keep it minimal; don't over-partition)
- **See Also**: pointers to ARCHITECTURE.md, CONTRIBUTING.md, etc. if they exist in the repo

**Keep the project-root CLAUDE.md small** (under 50 lines). It's a navigation map, not a textbook.

#### 2B.3 Synthesize domain CLAUDE.md units

For each domain identified in 2B.2, **write a scoped domain `CLAUDE.md`** in that module's root directory.

**Example structure**:
```
my-repo/
  CLAUDE.md              <- project-root (what, commands, gotchas, domain map)
  src/
    CLAUDE.md            <- domain 1 (API layer: contracts, invariants, entry points)
    api/
      ...
    core/
      CLAUDE.md          <- domain 2 (core logic: key abstractions, state machine)
      ...
  tests/
    CLAUDE.md            <- domain 3 (test infrastructure: harness, fixtures)
    ...
```

**Each domain CLAUDE.md includes**:
- **Module layout**: directory tree, what lives where
- **Key contracts**: public interfaces, APIs, data model
- **Domain logic**: state machine, algorithm, non-obvious invariants
- **Dependencies**: external libraries, internal cross-domain calls
- **Anti-patterns**: what NOT to do in this domain
- **Testing**: how to run tests, fixtures, mocks

**Keep each domain CLAUDE.md focused and minimal** (10-20 lines; longer ones should split further).

#### 2B.4 Write STATE.md checkpoint seed

Create a `STATE.md` in the repository root. This is the **durable checkpoint** that survives wipes and outages:

```markdown
# {{PROJECT_NAME}} — State & Next Steps

**Phase**: init-prime (first CLAUDE.md layer written)

**Intent**: {{PROJECT_NAME}} is now initialized with aesop orchestration semantics. 
All domain rules live in scoped CLAUDE.md files. Ready to dispatch first work.

**Locked decisions**:
- (none yet; updated as decisions are made)

**NEXT STEPS**:
- [ ] Review + approve the written CLAUDE.md layer
- [ ] Run `/buildsystem` to execute one example orchestration wave
- [ ] Iterate domain CLAUDE.md files as you discover invariants
```

#### 2B.5 Commit + Push

Stage all newly written files:
```bash
git add CLAUDE.md STATE.md src/CLAUDE.md core/CLAUDE.md tests/CLAUDE.md
```

Commit with a clear message:
```bash
git commit -m "init: initialize aesop orchestration semantics — project CLAUDE.md + domain units + STATE.md seed

Aesop init-prime: generated project-root CLAUDE.md (purpose, commands, gotchas), 
minimal domain CLAUDE.md units (contracts, invariants), and STATE.md checkpoint seed.

Co-Authored-By: Aesop Orchestrator <aesop@example.com>"
```

Run the **secret-scan gate**:
```bash
python <project-root>/tools/secret_scan.py --staged
```

**If gate fails** → fix the leaky files and re-commit (never override the gate).

**If gate passes** → push to the feature branch:
```bash
git push origin feat/aesop-init-prime
```

(Or to `main` if you have override permissions, but best practice: feature branch → PR → review → merge.)

#### 2B.6 Report init completion

After a successful push, report:
```
✓ Aesop init-prime complete
  - Project-root CLAUDE.md written (60 lines; purpose, commands, gotchas, 3 domains)
  - Domain CLAUDE.md units: src/, core/, tests/
  - STATE.md checkpoint seed created
  - Pushed to origin feat/aesop-init-prime (gated by secret-scan, all clear)
  
NEXT: Review the generated `.md` layer, iterate on domains, then run /buildsystem for your first orchestration wave.
```

---

## Notes

- **If no project context exists yet** (e.g., you're answering a general question about rules): Steps 1 loads global rules; skip 2 and say so.
- **Steps 1-5 always run on `/power`**; **step 6 (launch app) runs only if the active project has one**; **step 6b (monitor) runs only if configured**; **step 7 (dev loops) runs only during active development**.
- **Init-prime** writes `.md` files to the target repository (never personal/system paths). All state lives under the target repo root or configured `state_root` (see `aesop.config.json`).
- **Prefer subagents for anything large**; the goal is a *brain*, not a *dump*.
- **After priming** (either path), proceed under the loaded dispatch model (continue approved work autonomously; stop only for genuine decisions or unauthorized outward/destructive actions).
- **Portability**: all file paths are relative to the target repository or configurable via environment variables / `aesop.config.json` (never hardcoded personal paths). Use `~` notation for home-directory paths (e.g., `~/.claude`, `~/scripts`) for cross-platform compatibility (Windows, macOS, Linux). Config loaders automatically expand `~` at runtime.
