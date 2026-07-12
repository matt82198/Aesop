# Forensics: Making Agent Failures Git-Bisectable

## The Pillar

Agent behavior is source code. When an agent misbehaves, you can reconstruct exactly what rules, memory, and policies were active at the time of failure — then bisect the codebase to find the commit that broke it. This turns vague "the agent was weird yesterday" into a reproducible root cause.

**Key principle**: Rules (CARDINAL-RULES.md, CLAUDE.md), checkpoints (STATE.md, BUILDLOG.md), and policies (hooks/, monitor/CHARTER.md) are the agent's executable spec. Versioning them in git means agent failures become debuggable like code regressions.

## Tools

### `tools/agent-forensics.sh`

Read-only incident-forensics tool. Reconstructs agent behavior from git history using only git plumbing (no checkout, no working-tree mutation).

**Usage:**

```bash
# Snapshot agent behavior at a commit
bash tools/agent-forensics.sh <commit>

# Show what behavior changed between two commits
bash tools/agent-forensics.sh --diff <commitA> <commitB>
```

**Output:**
- Commit header (hash, date, subject)
- First ~40 lines of rules (docs/CARDINAL-RULES.md)
- CLAUDE.md snapshot (if present)
- STATE.md snapshot (if present)
- Last 30 lines of BUILDLOG.md (if tracked)
- For `--diff`: side-by-side changes in CLAUDE.md, STATE.md, docs/, hooks/, monitor/CHARTER.md

**Exit codes:**
- `0` on success
- `1` on error (unknown commit, I/O failure); clean error message printed to stderr, never raw stack traces

**Examples:**

```bash
# Forensics at HEAD
bash tools/agent-forensics.sh HEAD

# Forensics at a specific commit
bash tools/agent-forensics.sh 858ac08

# What changed in behavior between two releases?
bash tools/agent-forensics.sh --diff v0.1.0-beta.2 v0.1.0-beta.3
```

## Recipe: Bisect an Agent Regression

When an agent's behavior regressed (e.g., "rules started being ignored on July 10"):

1. **Identify the failure time window.** (e.g., "agent started proposing without filtering on 2026-07-10 18:00 UTC")

2. **Run forensics at the last known-good commit** and the first known-bad commit:
   ```bash
   bash tools/agent-forensics.sh <good-commit>
   bash tools/agent-forensics.sh <bad-commit>
   ```
   Compare the output manually. Often you'll spot the culprit immediately (e.g., a rule was deleted, CLAUDE.md lost a policy).

3. **If manual inspection doesn't find it, bisect:**
   ```bash
   git bisect start
   git bisect bad <bad-commit>
   git bisect good <good-commit>
   ```

4. **Write a behavior predicate** (a test that reproduces the failure):
   ```bash
   # Example: check that docs/CARDINAL-RULES.md mentions "Haiku" at this commit
   git bisect run bash -c '
     git show HEAD:docs/CARDINAL-RULES.md | grep -q "Haiku" && exit 0 || exit 1
   '
   ```
   Bisect will pin-point the exact commit that broke the behavior.

5. **Review the offending commit** using `--diff`:
   ```bash
   bash tools/agent-forensics.sh --diff <parent-of-bad> <bad-commit>
   ```

6. **Fix the issue** (restore the rule, reinstate the policy, etc.) in a new commit on a feature branch.

## What to Check When an Incident Happens

### Incident Discovery
1. Capture the **current behavior** (what went wrong, when, which agent):
   - Run `bash tools/agent-forensics.sh HEAD` to see rules + state at time of report.
   - Check logs in `state/FLEET-BACKUP.log`, `state/ACTIONS.log`, or agent transcript.
   - Note the **exact timestamp** of the first wrong behavior.

2. **Cross-reference the timestamp** with `git log --since="<time>"` to find commits near that time.

### Root Cause Narrowing
3. **Did a rule change?**
   ```bash
   git log -p --since="<before-incident>" -- docs/CARDINAL-RULES.md CLAUDE.md | head -100
   ```
   Look for deletions, edits to retry logic, dispatch budgets, or policy changes.

4. **Did state get corrupted?**
   ```bash
   bash tools/agent-forensics.sh <commit-before-incident>
   bash tools/agent-forensics.sh <commit-at-incident>
   # Compare STATE.md and BUILDLOG.md for anomalies (e.g., PHASE stuck, cost spike)
   ```

5. **Did a hook fail silently?**
   ```bash
   git log -p --since="<before-incident>" -- hooks/ monitor/CHARTER.md
   cat state/SECURITY-AUDIT.log | tail -50
   ```

### Confirmation via Bisect
6. Once you have a suspect commit or time range, use the bisect recipe above to narrow it down.

7. **Write the fix** in a feature branch. Update CLAUDE.md if the rule itself was wrong; add an explanatory comment referencing the incident date.

8. **Add a regression test:** if the incident was "agent ignored retry cap," add a check in pre-push-policy.sh or a future test-harness to catch that rule drifting again.

## Durable Artifacts to Check

| File | Purpose | Checked via |
|------|---------|-------------|
| **docs/CARDINAL-RULES.md** | Dispatch, cost, retry, TDD policy | `bash tools/agent-forensics.sh <commit>` |
| **CLAUDE.md** | Project-level rules, branch discipline, commit gates | manual forensics; git log |
| **STATE.md** | Current phase, locked decisions, next steps | forensics snapshot |
| **BUILDLOG.md** | Append-only cycle log (cost, actions, phase changes) | forensics (last 5 entries) |
| **hooks/** | Pre-push policy, secret-scan gate, lint checks | git show or forensics --diff |
| **monitor/CHARTER.md** | Orchestration monitor config (AUTO/PROPOSE thresholds) | forensics --diff |

## Example: Debugging a Cost Spike

**Symptom**: Agent token spend jumped from 50k to 200k tokens on 2026-07-10.

1. Run forensics at the spike time:
   ```bash
   bash tools/agent-forensics.sh <commit-on-2026-07-10>
   ```
   Check STATE.md and BUILDLOG.md. Look for:
   - Did `parallelism` increase? (more agents spawned → more tokens)
   - Did `retries` increase? (retry cap lowered → more respawns)
   - Did `model` change to Opus? (rule 1 violation)

2. Narrow the window:
   ```bash
   git log --oneline --since="2026-07-09" --until="2026-07-11"
   bash tools/agent-forensics.sh --diff <2026-07-09-commit> <2026-07-10-spike-commit>
   ```

3. If a rule changed (e.g., retries bumped from 3 to 6), fix it:
   ```bash
   git log -p --since="2026-07-09" -- docs/CARDINAL-RULES.md | grep -A5 -B5 retries
   ```

4. Restore or correct the rule, commit, and monitor spend in the next cycle.

## See Also

- **docs/CARDINAL-RULES.md** — The executable spec for agent behavior.
- **docs/DISPATCH-MODEL.md** — Cost levers, parallelism, watchdog stall detection.
- **docs/GOVERNANCE.md** — Memory/state single-writer guarantees, proposal flow.
- **README.md** — Quick start; includes examples of running forensics on a live incident.
