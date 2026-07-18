---
name: buildsystem
description: Execute one orchestrated development wave — rank backlog, dispatch Haiku fleet in parallel, merge train, checkpoint, closing audit.
version: 1.0.0
---

# Buildsystem — Orchestrated Development Wave

This skill automates one complete development wave: backlog prioritization, parallel Haiku agent dispatch, code review, merge train, and state checkpoint. It reads your `CLAUDE.md` rules and project backlog, then orchestrates a fleet of small, focused agents to deliver working features or fixes.

**Core principle**: A wave is a bounded unit of work (2–4 hours) that delivers measurable progress. The orchestrator dispatches independent Haiku agents to parallel worktrees, each agent works in isolation, all agents converge on a merge train, and the wave closes with a checkpoint and audit.

---

## Quick Start

### Prerequisites

Before running `/buildsystem`, ensure:

1. **Repository is primed** — Run `/power` first to load your CLAUDE.md layer and confirm orchestrator brain health
2. **Backlog exists** — Create a ranked backlog in `state/BACKLOG.md` or document your work items in the active `STATE.md`
3. **Aesop is initialized** — Config file (`aesop.config.json`), watchdog running, state directory populated

### One Command

```bash
/buildsystem
```

The orchestrator reads your backlog, dispatches agents, monitors progress, and delivers a closed wave with merged PRs.

---

## Wave Phases

### Phase 0: Preflight (1–2 min)

The orchestrator validates setup:
- Confirms CLAUDE.md is loaded and rules are understood
- Checks watchdog heartbeat (healthy daemon)
- Validates backlog format and work-item sizing
- Confirms all repos in config are cloned and clean
- Detects any active uncommitted work or stale agent directories

**Output**: Preflight report (green/red status, any blockers)

If blockers exist, the wave aborts with remediation steps.

### Phase 1: Backlog Rank & Dispatch (5–10 min)

The orchestrator reads the backlog and assigns agents:
- Rank work by priority (P1/P2/P3) and dependencies
- Assign each item to an agent type (backend-dev, frontend-dev, test-bot, docs-agent, etc.)
- Estimate size (Haiku time, ~3–10 min per item)
- Create work orders for each agent

**Output**: Dispatch summary showing which agent works on which item

The orchestrator then spawns 3–8 Haiku agents in parallel, each with its own worktree and task brief.

### Phase 2: Fleet Execution (30–90 min)

Haiku agents work independently in parallel:
- Each agent runs in its own worktree (no conflicts)
- Implements the feature/fix
- Writes tests and runs local verification
- Commits to its feature branch (not main)
- Pushes to origin

The orchestrator monitors:
- Agent heartbeats (alive/stalled detection)
- Build/test results (compile, unit tests)
- Token usage and cost
- Agent runtime (total time, cost per agent)

**Output**: Real-time agent status, progress updates

### Phase 3: Code Review & Integration (10–30 min)

Pull requests are created automatically as agents push. The orchestrator:
- Collects all PRs from this wave
- Routes them through review (linters, unit tests, integration tests)
- Approves and merges PRs that pass (green CI)
- Flags PRs with failures for manual triage

**Output**: Merge train progress, any PRs awaiting triage

### Phase 4: Checkpoint & Audit (2–5 min)

The wave closes:
- Confirms all work is merged to main
- Updates `STATE.md` with phase completion, NEXT STEPS
- Appends summary line to `BUILDLOG.md`
- Runs closing audit (security scan, coverage, test count, code quality metrics)
- Commits and pushes checkpoint files

**Output**: Wave closed, audit report, ready for next wave

---

## Backlog Format

Create a `state/BACKLOG.md` file or update `STATE.md` with your ranked work:

```markdown
# Wave 15 Backlog

## P1: Critical

- [ ] Fix secret-scan gate hang (blocking CI) — backend-dev — 5min
- [ ] Update MEMORY.md with wave-15 learnings — docs-agent — 3min

## P2: Features

- [ ] Add cost-ceiling dashboard widget — frontend-dev — 8min
- [ ] Implement fleet-ops monitoring — backend-dev — 10min

## P3: Tech Debt

- [ ] Refactor monitor/collect-signals.mjs (duplicate checks) — backend-dev — 15min
- [ ] Add type hints to Python tools — test-bot — 10min
```

**Sizing guide**:
- **3–5 min**: Typo fix, simple config change, one-line refactor
- **5–10 min**: New function, small feature, unit test
- **10–15 min**: Module refactor, feature with 2–3 functions
- **15+ min**: Split into smaller items (waves work best in 30–90 min total)

**Priorities**:
- **P1**: Blockers, security fixes, showstoppers
- **P2**: Features, quality, important bug fixes
- **P3**: Tech debt, docs, refactoring, minor improvements

---

## Work-Order Contract

Each agent receives a work order (brief) describing:

```
Agent: haiku-backend-dev-5
Task: Fix secret-scan gate hang (blocking CI)
Backlog Item: Wave 15 / P1
Time Budget: 5 min (0 buffer)
Scope: Identify why secret_scan.py times out on large staged files; implement fast path or raise limit.
  - Reproduce: git add large-file && git push (hangs at secret-scan gate)
  - Change: Modify tools/secret_scan.py line 42 OR config file
  - Test: Verify gate completes within 10s for fixture data
  - Commit message: fix(security): secret-scan gate timeout on large files
Constraints:
  - Never modify CLAUDE.md or STATE.md
  - Must pass pre-commit hook
  - Use Haiku best-effort only (no external calls, no model training)
```

The agent reads the work order, implements the change, commits, and pushes the feature branch. The orchestrator then integrates the work.

---

## Orchestrator Isolation & Safety

### Disjoint File Ownership (Preflight Guard)

The orchestrator enforces a critical safety invariant: **no two agents should modify the same file in a single wave**.

Before dispatch, the preflight verifies:
- Each backlog item is assigned to exactly one agent
- No two items touch the same file or directory (checked via domain map)
- If overlap is detected, the wave aborts with a remediation plan (reorder/resplit items)

This guard is the Preflight phase of `skills/buildsystem/wave-flat-dispatch.template.mjs` (ships with aesop): it refuses to dispatch when two manifest items own the same file, returning `{aborted: true, reason: 'ownership_overlap'}` before any worker spawns.

### Worktree Isolation

Each agent runs in its own git worktree (`aesop-wt-<wave>-<agent-id>/`):
- Independent branch, independent HEAD, independent working directory
- No git conflicts (git worktree is designed for this)
- Automatic cleanup after wave closes
- Zero cross-agent interference

### Single-Merge Serialization

All PRs from a wave merge through a serial merge train:
- First agent to reach green CI merges
- Next agent waits for main to stabilize, re-tests, then merges
- Prevents race conditions (all PRs are based on stable main at merge time)

---

## Monitoring & Cost

The dashboard (`aesop dashboard`) shows real-time wave progress:
- **Phase**: Current phase (dispatch, execution, review, checkpoint)
- **Agents**: Running agents, age, tokens used, task
- **PRs**: Open PRs this wave, pass/fail status, review progress
- **Cost**: Total tokens, per-agent cost, cost vs budget
- **ETA**: Estimated wave completion time

The orchestrator emits heartbeats every 10s so you can monitor progress without polling.

---

## Failure & Remediation

### Agent Stalls

If an agent hasn't updated its heartbeat for 5 min, the orchestrator:
1. Checks the agent's transcript (last 50 lines of .claude/transcript.jsonl)
2. Determines if the agent is:
   - **Stuck in a loop** (repeating the same error)
   - **Waiting for input** (blocked on a prompt, should never happen)
   - **Genuinely stalled** (no heartbeat for 10+ min)
3. Terminates the stalled agent and reports the failure
4. Optionally retries the work item (if within retry budget: 2 retries max)

### PR Failures

If a PR doesn't pass CI (linter, test failures):
1. The orchestrator collects the failure reason from CI logs
2. Routes the PR to a human reviewer or re-dispatch a fix agent
3. Documents the failure in BUILDLOG.md for the wave audit
4. Tracks retries to avoid infinite loops

### Preflight Blockers

If preflight detects blockers:
- Reports the blocker with remediation steps
- Aborts the wave (safe-fail)
- Suggests fixes (e.g., "split item X into X.1 and X.2" or "commit pending work first")

---

## Closing Audit

At wave end, the orchestrator runs a closing audit:

**Security**: Runs secret-scan on all merged code (no secrets shipped)

**Coverage**: Compares test coverage before/after wave (target: no decrease)

**Quality**: Counts:
- Total files changed
- Total LOC changed
- Total commits
- Total agent time (sum of all agent runtimes)
- PR review cycle time (avg time from push to merge)

**Output**: Audit report in `state/BUILDLOG.md`, sample:

```
Wave 15 closed (phase 4/4)
  Agents: 5 (haiku-backend-dev-1, haiku-frontend-dev-1, haiku-test-bot-1, haiku-docs-agent-1, haiku-backend-dev-2)
  Time: 87 min (dispatch 6m, exec 65m, review 12m, checkpoint 4m)
  Backlog: 7 items, 1 skipped (P1: 2/2, P2: 4/4, P3: 1/1)
  PRs: 6 merged, 0 failed, 1 retry
  Coverage: 82% → 84% (+2%)
  Security: clean
  NEXT STEPS: (1) review MEMORY.md updates, (2) stage wave-16 backlog
```

---

## Best Practices

1. **Size work for Haiku** — Each item should take 1–2 Haiku tokens (3–10 min). Too large and agents will fail mid-task.

2. **Use domain map** — Ensure your `CLAUDE.md` layer has a clear domain map so the preflight guard can validate assignments.

3. **One wave per session** — Run `/buildsystem` once per session (not repeatedly). Use the closing audit to inform the next wave.

4. **Monitor in real-time** — Open the dashboard (`aesop dashboard`) to watch agents work. This builds confidence and catches stalls early.

5. **Commit backlog to git** — Keep your backlog (`state/BACKLOG.md`) in git so wave history is durable and reviewable.

6. **Review NEXT STEPS** — After wave closes, read `STATE.md` NEXT STEPS and `BUILDLOG.md` audit report to plan the next wave.

---

## Troubleshooting

### Wave hangs on Phase 1 (dispatch)

**Cause**: Backlog parsing error or domain-map conflict detected.

**Fix**:
1. Check `state/BACKLOG.md` format (YAML or markdown, consistent)
2. Verify each item has: `- [ ] Title — agent-type — time-estimate`
3. Run `aesop doctor` to verify domain map
4. Retry: `/buildsystem`

### Wave reports "Preflight blockers"

**Cause**: Uncommitted work, repo not clean, or agent directory conflict.

**Fix**:
1. Commit all pending work: `git add -A && git commit -m "checkpoint: pending work"` (in each repo)
2. Confirm watchdog is running: `bash daemons/run-watchdog.sh --once`
3. Clean up stale worktrees: `git worktree prune`
4. Retry: `/buildsystem`

### Agent stalls mid-task

**Cause**: Infinite loop, network issue, or model rate-limit.

**Fix**:
1. Check agent transcript: `tail -50 <wave-workdir>/transcript.jsonl`
2. Understand the loop (repeating error?) and file an issue
3. Manually fix the work item or retry in next wave
4. Document the failure in BUILDLOG.md

### PR fails CI (linter/test)

**Cause**: Agent didn't run tests locally or introduced a bug.

**Fix**:
1. Review the PR diff and CI logs
2. Comment on the PR with remediation
3. Assign a fix agent or manually fix
4. Retry: `/buildsystem wave-<N>-retry` to re-merge just this PR

---

## See Also

- **[/power skill](../power/SKILL.md)** — Prime your orchestrator brain before running a wave
- **[FIRST-WAVE.md](../docs/FIRST-WAVE.md)** — Tutorial on running your first wave
- **[CLAUDE.md format](../docs/CONFIGURE.md#claudemd-layer)** — Document your codebase for agents
- **[Wave architecture](../docs/ARCHITECTURE.md#wave-cycle)** — Deep dive on the orchestration model
