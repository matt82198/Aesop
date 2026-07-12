# STATE — aesop refinement loop

## Intent
Aesop is the reference implementation of the thesis: **agent behavior is source code** —
rules, memory, hooks, and checkpoints are versioned, portable, diffable filesystem
artifacts in git, so review/versioning/inheritance/enforcement/forensics apply to how
agents work. Single-user survival hack → cross-team product.

## Locked decisions (user, 2026-07-12)
- Thesis fixed as the development goal; refinement loop prioritizes the five pillars:
  onboarding-by-clone · guardrails-in-code · behavioral PRs · forensic replay ·
  cross-machine continuity.
- Orchestrator (Fable) main-thread; subagents Haiku; TDD-first.
- **Branch-per-item**: every backlog item gets its own branch + PR cut from main
  (worktree isolation for parallel implementers; agents must NEVER git-checkout in the
  primary working tree). Mega-branches retired with PR #16.
- Domain CLAUDE.mds collapsed into root (lossless); monitor extended_signals default off.

## Standing order (user, 2026-07-12)
Rerun the refinement loop CONTINUOUSLY until tokens exhaust or gaps dry (2 consecutive
audits finding nothing new). Cycle: land wave → five-lens re-audit → dedupe → dispatch
per-item branches → merge green PRs. Never idle while agents run. On session death:
resume from this file + AUDIT-BACKLOG.md.

## Phase: `wave-5-landing` (2026-07-12, current)
Audit #1 (post-clear five-lens re-audit) produced 9 item-branches + 2 cross-repo ports —
see AUDIT-BACKLOG.md for live statuses. Merged so far: PRs #17–#24. In flight:
fix/backup-fleet-nul-protocol, fix/monitor-proposals-races, fix/audit-log-hardening,
fix/reconstitute-target-validation, fix/ci-run-all-suites, feat/dash-agents-panel,
plus the two ports (~/scripts scanner skip-fix; conductor3 lock-ownership re-port —
conductor3 branch fix/watchdog-atomic-lock MUST NOT merge without it).
INCIDENT (resolved): 3 concurrent conductor3 watchdog daemons raced backup cycles and
twice reverted uncommitted aesop working-tree files (~13:30–13:50); instances killed,
single daemon restarted, atomic-lock port on the conductor3 branch. Forensics:
conductor3 FLEET-BACKUP.log:554-568.

## Upcoming phases
1. **`wave-5-close`** — land + merge the 6 remaining branches and 2 ports; full
   final-catch (npm + python + all shell suites + hook/reconstitute self-tests);
   restart web dash on merged main; collapse backlog again.
2. **`audit-2`** — second five-lens re-audit vs the five pillars. Clean → one more;
   findings → dispatch wave 6 branch-per-item. (2 consecutive cleans end the loop.)
3. **`release`** — version bump + tag (next beta), npm publish check, CI badge in
   README, release notes from the backlog's cleared history.
4. **`ops-hardening` (candidates, unclaimed)** — BUILDLOG lifecycle doc; INCIDENT-LOG
   correlation; commit-format check in pre-push hook; merge conductor3 branches
   (fix/watchdog-atomic-lock, fix/monitor-path-and-rotation) + daemon restart on the
   fixed script; SIGNALS.json consumer integration (serve.py reading monitor brief).

## Phase history (collapsed)
- `pr-open` → PR #16 opened after waves 1–2 (onboarding/policy/behavioral-PR/forensics/
  continuity scaffolding + rotate_logs, reconstitute, model-policy hook).
- `wave-3-p0-inflight` → all 8 P0 + P1/P2 audit items dispatched and landed.
- `backlog-cleared` → 26/26 items ✅, final-catch green, live gate + /power dashboard
  default (web :8770) + brain hook re-synced.
- `merged-wave4-open` → PR #16 merged (`f259c4f`); branch-per-item adopted; audit #1
  dispatched.

## NEXT STEPS
1. Merge remaining wave-5 PRs as they go green; flip backlog boxes per merge.
2. Wave-5 final-catch on merged main; then launch audit #2.
3. Keep the web dash (:8770) restarted onto merged main after UI-touching merges.
4. Update this file at each phase boundary; collapse finished phases into history.
