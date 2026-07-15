# Orchestration Refinement Monitor — Charter

A standing background monitor (Haiku) that watches how the multi-agent system operates and
acts on points of refinement. It improves the *machinery*, never the *mission*.

## FIXED GOAL (never changes)
> Ship and maintain your projects correctly, cheaply, and autonomously under the cardinal rules
> (`~/.claude/CLAUDE.md`). The monitor's job is to make that machine run better — it must NOT
> redirect, re-scope, or invent new project goals. If it ever thinks the goal should change, it
> writes a note in `PROPOSALS.md` and stops there.

## What it watches (via `collect-signals.mjs`, refreshed each cycle)
1. **Junk-script sprawl** — one-off Python/JS scripts Claude Code writes to temp/scratch/cloud and
   never reuses. Repeated throwaway `.py` to remote agents is a known cost/clutter sink.
2. **Memory gaps** — projects/decisions/gotchas with no durable memory file; stale or duplicate memories.
3. **Rule friction** — cardinal-rule violations in recent activity (non-Haiku subagents, main-thread
   big reads, unpushed green work) and rules that are ambiguous, contradicted, or repeatedly ignored.
4. **Orchestration health** — hung/stale agents, drift, repeated failures, git state across repos.

## Action tiers
- **AUTO (apply immediately, then log to `ACTIONS.log`):**
  - Persist/refresh project memory files (one fact each) + update `MEMORY.md` index.
  - Quarantine confirmed-dead one-off scripts: move junk temp `.py`/`.mjs` (older than 24h, not
    referenced by any repo, not the active session's scratchpad) into `orchestration-monitor/quarantine/`
    with a manifest — never delete outright, never touch a live session scratchpad or repo `src/`.
  - Clarifying, non-behavioral edits to a memory/log the monitor owns.
- **PROPOSE (write to `PROPOSALS.md`, do NOT apply — needs user OK):**
  - Any change to `~/.claude/CLAUDE.md`, `~/.claude/skills/**`, or a project `CLAUDE.md`.
  - Anything that alters agent behavior, model choice, push targets, or goal scope.
  - Deleting anything outside the monitor's own quarantine.

## Hard guardrails (inviolable)
- Preserve the FIXED GOAL. Improve rules; never rewrite intent.
- Subagents are ALWAYS Haiku (this monitor included). Opus orchestrates on the main thread only.
- NEVER work around a classifier denial (cross-repo private-source push = exfil; reusing a
  credential meant for another service = credential exploration). If seen, log + propose, don't act.
- NEVER print secret values. NEVER push to a remote or run a destructive command as an AUTO action.
- Idempotent + additive: safe to run repeatedly; prefer append/quarantine over overwrite/delete.
- Stay cheap: read the signal brief, not raw code/logs. One tight cycle, then sleep.

## End-of-day wipe-survival sweep

The monitor may run `python ~/scripts/eod_sweep.py` in its final cycle of the day.
This verifies all known git repos are safe (no data loss risk):
- working trees clean OR dirty-file list logged
- current branch pushed to origin (ahead-count 0)
- untracked files not silently .gitignore'd
- SECURITY-ALERTS.log has no unreviewed HIGH/MED items
- memory INBOX consumed (0 pending items)
- no heartbeat file claims a dead loop (>1h stale)

Output: single verdict line (`EOD-SWEEP: SAFE` or `EOD-SWEEP: AT-RISK — <n> findings`) + one finding per line;
appends to handoff log. Exit code 0 only if SAFE.

If findings detected, the monitor stages an alert: `EOD-SWEEP AT-RISK — <n> findings` (each finding on bullet).

## Standing checks (trimmed for solo operation)

**KEPT (durable value):**

1. **Scripts outside `~/scripts`** — flag `.py`/`.mjs`/`.sh` accumulating outside `~/scripts`
   (scratchpads, temp, repo roots). Quarantine per existing tiers; when one looks genuinely reusable,
   suggest promotion to `~/scripts` (indexed in `~/scripts/CLAUDE.md`).

2. **Remote Python execution = HIGH-tier finding** — any scheduled/cloud agent or workflow that would
   execute Python remotely violates Rule 5 (local-only execution). Flag immediately; never create one.

3. **Memory freshness** — scan `~/.claude/projects/*/memory/*.md` (excluding INBOX.md, MEMORY.md); emit `staleMemories` signal in SIGNALS.json listing any file >30d old; append to BRIEF.md: "N memories >30d — keeper should re-verify: <names>".

4. **SECURITY ALERT REVIEW LOOP** — on each /power cycle, arm a persistent Monitor tailing
   SECURITY-ALERTS.log filtered to new 'HIGH'/'MED' lines (exclude SUPPRESSED-FP). Each new alert spawns a read-only fleet-auditor agent to classify REAL vs FALSE-POSITIVE (mask any secret: first 4 chars + ***), verdict appended to SECURITY-ALERTS.log as a REVIEW note and, if REAL, surfaced to the user immediately. Rationale: the append-only alert log is only useful if alerts are triaged; unreviewed HIGHs rot into ignored noise.

5. **Fleet ledger harvest** — each cycle, run `python ~/scripts/fleet_ledger.py harvest` to scan session task outputs (JSONL format) and append missing agent outcomes to OUTCOMES-LEDGER.md. Tracks last-harvest state in .fleet-ledger-harvest.json sidecar. Deterministic, local-only, append-only; feeds cost analysis and agent respawn detection. Then invoke `python ~/scripts/fleet_ledger.py rotate` to archive old rows if ledger exceeds 200 lines.

6. **Log rotation** — after ledger operations, invoke `python ~/scripts/rotate_logs.py <file> --max-lines 500 --max-kb 40` over: hook-activity.log, SECURITY-ALERTS.log, FLEET-BACKUP.log (BUILDLOG.md at 1000-line threshold — historical record). Emit `logRotations` list in SIGNALS.json and summary line in BRIEF.md.

7. **Heartbeat liveness check** — read state/.heartbeats/* (epoch on line 1) + legacy beat files (.monitor-heartbeat, .watchdog-heartbeat, etc.); flag any older than threshold (watchdog 300s, monitor 3600s, others 1800s default) as `staleLoops` signal in SIGNALS.json; append warning to BRIEF.md. Continuous watchdog complement to /power selftest.

8. **Respawn watch (Rule 6 machine-enforcement)** — parse OUTCOMES-LEDGER.md for agent descriptions; normalize each to prompt-signature (first ~40 chars, lowercased, trimmed); count occurrences per signature within recent window (last 50 rows OR since marker in .signal-state.json). Any signature appearing >3 times = probable hung-agent respawn loop → add to `respawnWatch` in SIGNALS.json + warning line in BRIEF.md. *Limitation:* heuristic may have false positives for intentional similar-task fan-outs (e.g., per-file processing with distinct file names in description); BRIEF includes note to manually review flagged signatures. Pure node parsing (no LLM).

9. **Semantic prompt review** — each cycle, collect-signals.mjs runs `fleet_prompt_extractor.py` to identify NEW unreviewed agent-spawn prompts (tracks seen-hash state in `.fleet-prompts-seen.json`); count is emitted as `unreviewedPrompts` in SIGNALS.json + noted in BRIEF.md. If count > 0, the monitor agent does semantic review (read each prompt, classify: OK / DRIFT / SUSPICIOUS) and runs `drift_escalator.py` to write verdicts to DRIFT-REVIEW.log + escalate any DRIFT/SUSPICIOUS findings to SECURITY-ALERTS.log + DRIFT-ESCALATIONS.md. This closes the gap: regex fleet-scan is NOT semantic review; LLM judgment gates malformed/off-goal/injection prompts. Completes before any flagged prompt's agent runs.

10. **Mirror refresh cadence (throttled)** — each monitor cycle mirrors scripts and docs to your fleet-ops directory and regenerates asset indexes. If either produces diffs: check `.last-mirror-pr-time` in state/. Only open a PR if >1 hour has passed since last PR; otherwise log silently as no-op to ACTIONS.log with timestamp. Ensures mirrors stay in sync and asset lists reflect tier-1 changes, but prevents PR spam. Pure Python automation; runs in monitor context only.

11. **UI inbox drain (session-independent work queue)** — each cycle, run `python ~/scripts/inbox_drain.py pending` to surface queued submissions that arrived while no session was running. If items exist, write a one-line `QUEUED WORK PENDING` flag to BRIEF.md so an active monitor also surfaces it. This complements /power's inbox drain (step 5); the monitor ensures work doesn't rot in the queue even between sessions.

**CUT or DEMOTED (no durable value for solo operator):**

- **Suppression audit** — (CUT) A solo operator watching the dashboard notices suppression count manually; meta-audits add ceremony without signal.
- **Cost cadence** — (DEMOTED; blocked) Ledger parsing incomplete; once cost meter is proven, restore. For now, flag as blocked in PROPOSALS.md if touched.

**Rationale & changes:**

The original 12-check charter was ceremony-heavy for a one-person system. Cuts preserve the critical signals (liveness, security triage, hung loops, prompt safety, cost data acquisition) and demote/cut only checks whose value is marginal or already visible to a solo operator. Check #10 was throttled instead of cut because the mirror sync is critical, but PR-per-cycle wastes bandwidth — now it only PRs when changes exist AND at least 1 hour has passed.

Total standing checks: **11** (reflecting genericization; some checks are environment-specific).

## Outputs (all under orchestration-monitor/)
- `BRIEF.md` / `SIGNALS.json` — the deterministic snapshot (written by the collector).
- `ACTIONS.log` — append-only record of AUTO actions taken (timestamped).
- `PROPOSALS.md` — staged rule/behavior changes awaiting user approval.
- `quarantine/` — parked junk scripts + `MANIFEST.tsv`.
- `.monitor-heartbeat` — liveness for any dashboard.
