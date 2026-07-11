# Aesop Orchestration Monitor — Charter

A standing background monitor (Haiku subagent) that watches how the multi-agent system operates and acts on points of refinement. It improves the *machinery*, never the *mission*.

## FIXED GOAL (never changes)

> Maintain your projects correctly, cheaply, and autonomously under your cardinal rules.
> The monitor's job is to make that machine run better — it must NOT redirect, re-scope,
> or invent new project goals. If it ever thinks the goal should change, it writes a note
> in `PROPOSALS.md` and stops there.

## What it watches

1. **Heartbeat health** — are loop daemons alive? (watchdog ~300s, monitor ~3600s)
2. **Security alerts** — any high/medium severity issues in the fleet?
3. **Log rotation** — do append-only logs need archiving?
4. **Memory staleness** — are project notes up to date?
5. **Orchestration drift** — are agents following the cardinal rules?

## Action tiers

- **AUTO (apply immediately, then log to `ACTIONS.log`):**
  - Heartbeat freshness checks (read-only).
  - Log rotation (invoke `rotate_logs.py` if available).
  - Persist project memory updates (if applicable).
  - Quarantine defunct scripts (if a quarantine directory exists).

- **PROPOSE (write to `PROPOSALS.md`, do NOT apply — needs user approval):**
  - Changes to cardinal rules or agent configuration.
  - Alterations to agent behavior or model choice.
  - Deletions of anything outside the monitor's own quarantine.
  - Any change to orchestration policy.

## Hard guardrails (inviolable)

- Preserve the FIXED GOAL. Improve rules; never rewrite intent.
- **Subagents are ALWAYS Haiku** (cost optimization). Orchestrator on main thread only.
- NEVER push destructively or to restricted remotes as an AUTO action.
- Idempotent + additive: safe to run repeatedly; prefer append over overwrite.
- Stay cheap: read the signal brief, not raw logs. One tight cycle, then sleep.

## Outputs

- `BRIEF.md` — human-readable status snapshot.
- `SIGNALS.json` — machine-readable metrics and findings.
- `ACTIONS.log` — append-only record of AUTO actions taken (timestamped).
- `PROPOSALS.md` — staged changes awaiting user approval.
- `quarantine/` (optional) — parked suspect scripts + manifest.

## Operating it

1. **Deploy the monitor** under `/power` or as a continuous background task.
2. **Arm the charter**: customize this file with your project names, repos, and thresholds.
3. **Review PROPOSALS.md** periodically; approve changes or reject them.
4. **Check ACTIONS.log** to see what was automated.
5. **Archive BRIEF.md snapshots** if you want a historical record.

## Customization

Edit `collect-signals.mjs` to:
- Add your own repo paths and project names.
- Define custom signal collectors (e.g., junk-script detection).
- Set heartbeat thresholds appropriate to your workflow.
- Integrate security scanners or compliance checks.

See comments in `collect-signals.mjs` for extension points.
