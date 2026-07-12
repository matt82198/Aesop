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

## Phase: `wave-6-p0-ci-landed` (2026-07-12, current)
Wave-6 P0 security fixes all merged to main (PRs #36–#41); CI-repair wave (PRs #42–#46) fixed
5 pre-existing Linux-only defects exposed by enabling the test gate. Main push-CI now fully
green (all 8 test/scan steps). Root cause documented: bash -n-only CI never executed any suite
for the repo's life. See AUDIT-BACKLOG.md for complete P0/CI-repair status + follow-ups.

Previous wave (audit #1) merged PRs #17–#35; all three phases of wave 5 now closed.

## Upcoming phases
1. **`wave-5-close`** — land + merge the 6 remaining branches and 2 ports; full
   final-catch (npm + python + all shell suites + hook/reconstitute self-tests);
   restart web dash on merged main; collapse backlog again.
2. **`audit-2`** — second re-audit vs the five pillars, now SEVEN lenses (user,
   2026-07-12): architect, security, bash, js, honest + **frontend engineer**
   (runtime wiring/update model/perf of ui+dash, real-browser via playwright) +
   **design analyst** (ui-ux-designer: hierarchy, interaction, usability). UI
   findings/fixes always go to typed frontend specialists with playwright proof,
   never generic Haikus. Clean → one more; findings → wave 6 branch-per-item.
   (2 consecutive cleans end the loop.)
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
1. Wave-6 P1 tier (9 items, per standing refinement loop) on green main.
2. Wave-6 P2/P3 tiers and user-decision items.
3. Re-audit (audit #3) vs five pillars post-P0–P3 landing.
4. Update this file at each phase boundary; collapse finished phases into history.
