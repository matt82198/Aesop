# Aesop Orchestration Monitor — Charter

A standing background monitor (Haiku subagent) that watches how the multi-agent system operates and acts on points of refinement. It improves the *machinery*, never the *mission*.

## FIXED GOAL (never changes)

> Maintain your projects correctly, cheaply, and autonomously under your cardinal rules.
> The monitor's job is to make that machine run better — it must NOT redirect, re-scope,
> or invent new project goals. If it ever thinks the goal should change, it writes a note
> in `PROPOSALS.md` and stops there.

## Standing checks (deterministic signal collection)

Each cycle, `collect-signals.mjs` runs these checks and emits `BRIEF.md` + `SIGNALS.json`:

1. **Heartbeat liveness check** — read `.heartbeats/*` (epoch on line 1) + legacy beat files
   (`.monitor-heartbeat`, `.watchdog-heartbeat`); flag any older than threshold (watchdog 300s,
   monitor 3600s, others 1800s default) as stale loops; append warning to BRIEF.md.

2. **Git state across repos** — for each repo in config: branch, last commit, uncommitted files,
   commits ahead of remote. Identifies unpushed work and dirty state.

3. **Memory freshness** — scan project memory files (excluding index/inbox); flag any >30 days old;
   append summary to BRIEF.md ("N memories stale — keeper should re-verify").

4. **Log rotation** — check append-only logs against max-lines/max-kb thresholds (configurable,
   default 500 lines / 40 KB). If a log exceeds threshold, emit rotation signal (AUTO tier can
   invoke rotate_logs.py if available); append rotation summary to BRIEF.md.

5. **Junk-script sprawl detection** *(extended, opt-in via `monitor.extended_signals`)* — scan temp/scratch roots for throwaway `.py`/.mjs`/`.js` files
   older than 24 hours, not in a live session directory (avoid false-positives during active work).
   Count total, estimate quarantinable, list oldest. AUTO tier quarantines confirmed junk into
   `monitor/quarantine/` with manifest.

6. **Stray scripts in repo roots** *(extended, opt-in via `monitor.extended_signals`)* — scan recent commits (7d) to detect one-off `.py`/`.mjs`/`.sql`
   scripts committed directly to repo root (not under proper src/scripts paths). Flag for cleanup.

7. **Security alert review loop** — tail SECURITY-ALERTS.log for new HIGH/MED entries (skip suppressed);
   each new alert noted in BRIEF.md. Monitor agent does semantic review (REAL vs FP) each cycle.

8. **Respawn watch (Rule 6 retry cap)** *(extended, opt-in via `monitor.extended_signals`)* — parse agent spawn records; normalize descriptions to
   prompt-signatures (first ~40 chars, lowercased); count occurrences in recent window (last 50 rows).
   Flag any signature appearing >3 times as probable hung-agent loop → rule 6 cap breached.
   Limitation: heuristic may have false positives for intentional similar-task fan-outs.

9. **Cost cadence tracking** — every 3rd cycle, harvest agent spawn ledger and append cost tick
   to COST-LOG.md (cycle count, timestamp, model distribution). Flags non-haiku specializations.

10. **Unreviewed agent prompts** *(extended, opt-in via `monitor.extended_signals`)* — run fleet-prompt-extractor.py (if available) to collect NEW
    spawns since last review; emit count in SIGNALS.json + note in BRIEF.md.

## Extended signals (opt-in)

Checks 5, 6, 8, and 10 are marked as "extended" — they are disabled by default but can be
enabled via configuration:

- **Config key:** `monitor.extended_signals` (boolean, default: `false`) in aesop.config.json
- **Env override:** `AESOP_EXTENDED_SIGNALS` (string `'true'` or `'1'` to enable)
- **Precedence:** env var > config file > default (false)

When disabled, extended checks emit `{"skipped": true}` in SIGNALS.json and BRIEF.md notes them
as "extended (off)". AUTO junk-quarantine action only runs when the junk check is enabled.
PROPOSE-tier signals for extended checks (respawn-watch-breach, stray-repo-scripts) are only
emitted when extended_signals is ON.

## Action tiers

- **AUTO (apply immediately, then log to `ACTIONS.log`):**
  - Heartbeat freshness checks (read-only).
  - Log rotation (invoke rotate_logs.py if available; fail-open if not).
  - Persist heartbeat write (`.monitor-heartbeat` update after cycle).
  - Quarantine confirmed-junk scripts: move old temp `.py`/`.mjs` (not live session) into
    `monitor/quarantine/` with manifest — never delete outright (only when extended_signals is ON).

- **PROPOSE (write to `PROPOSALS.md`, do NOT apply — needs user approval):**
  - Changes to cardinal rules or agent configuration.
  - Alterations to agent behavior, model choice, or push targets.
  - Deletions of anything outside monitor's own quarantine.
  - Any change to orchestration policy.

## Hard guardrails (inviolable)

- Preserve the FIXED GOAL. Improve rules; never rewrite intent.
- **Subagents are ALWAYS Haiku** (cost optimization). Orchestrator on main thread only.
- NEVER push destructively or to restricted remotes as an AUTO action.
- NEVER edit cardinal-rules files (CLAUDE.md, skills/, agent configs) — only PROPOSE changes.
- Idempotent + additive: safe to run repeatedly; prefer append over overwrite.
- Stay cheap: read the signal brief, not raw logs. One tight cycle, then sleep.
- Robust to missing files: treat missing dirs/logs as empty, never crash.

## Outputs

- `BRIEF.md` — human-readable status snapshot (overwrite each cycle).
- `SIGNALS.json` — machine-readable metrics and findings (overwrite each cycle).
- `ACTIONS.log` — append-only record of AUTO actions taken (timestamped).
- `PROPOSALS.md` — staged changes awaiting user approval.
- `quarantine/` — parked junk scripts + `MANIFEST.tsv` (append-only).
- `.monitor-heartbeat` — epoch timestamp (line 1) for liveness.
- `.signal-state.json` — sidecar state (cycle count, seen prompts, etc.).

## Operating it

1. **Deploy the monitor** as a continuous background task (or invoke manually each cycle).
2. **Customize via config**: populate `aesop.config.json` with your repo paths, thresholds.
3. **Review PROPOSALS.md** periodically; approve changes or reject them.
4. **Check ACTIONS.log** to see what was automated.
5. **Monitor BRIEF.md** for drift signals; respond to findings.

## Customization

Edit `collect-signals.mjs` to:
- Add/remove checks based on your project needs.
- Configure paths via environment variables (AESOP_ROOT, BRAIN_ROOT, SCRIPTS_ROOT, TEMP_ROOT)
  or load from aesop.config.json.
- Set heartbeat thresholds appropriate to your workflow.
- Integrate custom signal collectors (e.g., compliance checks, custom linters).

See comments in `collect-signals.mjs` for extension points. **Keep it CRLF-safe** (no line
continuations; maintain Windows+POSIX compatibility).

## Single-instance guard

Before running, check `.monitor-heartbeat` — if <300s old, skip cycle (another monitor is running).
After cycle completes, update `.monitor-heartbeat` with current epoch. 
Override with `AESOP_MONITOR_FORCE=true` or `AESOP_MONITOR_FORCE=1` for manual runs or tests (explicit comparison, not truthiness: strings like `'0'` or `'false'` do NOT bypass the guard).

## Single-writer discipline with atomic operations

- Only the monitor edits `BRIEF.md`, `SIGNALS.json`, `ACTIONS.log`, `.monitor-heartbeat`, `.signal-state.json`.
  - Writes are atomic (temp file + rename) to prevent mid-write corruption if a kill occurs.
  - Rename is retried on EPERM/EBUSY (Windows readers holding file) with exponential backoff; .tmp is cleaned up on final failure; prior file is preserved (degrade gracefully).
- `PROPOSALS.md` uses atomic operations (mkdir-style lockfile) to prevent race conditions between concurrent appends (emitProposal) and full rewrites (accept/reject).
  - **Both emitProposal and moveProposal (accept/reject) acquire the PROPOSALS.md.lock before read-check-append/write**.
  - Lock contains pid+timestamp for staleness detection (>60s stale locks are reclaimed).
  - Lock is acquired, held during read-modify-write, released after write completes.
  - **Fail-closed (P0 wave-8 fix)**: If lock acquisition fails after timeout (default 30s, configurable via AESOP_LOCK_TIMEOUT_MS env var or config), the operation throws an error instead of proceeding. In emitProposal (monitor context), lock failures skip proposal emission for that cycle and retry next cycle. In proposals.mjs CLI (accept/reject), lock failures exit with error code 1 (caller should retry).
- Quarantine manifest is append-only; never edit entries, only add new ones.
