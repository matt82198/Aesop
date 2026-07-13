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

## Phase: `audit-3-complete / wave-7-backlog-seeded` (2026-07-12, current)
Four-lens re-audit (audit #3) completed post-wave-6: NOT clean → 7 items (1 P1, 6 P2).
2 quick-wins fixed in PR #64 already merged to main; remaining 7 items seeded in wave-7
backlog below. Loop continues. See AUDIT-BACKLOG.md Wave 7 for full ranked backlog.

Previous: Wave-6 P0 security fixes all merged (PRs #36–#41); CI-repair wave (PRs #42–#46) fixed
5 Linux-only defects. Main push-CI fully green (all 8 test/scan steps).

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
1. Wave-7 items below (see AUDIT-BACKLOG.md Wave 7); branch-per-item, TDD-first.
2. Start with the fail-open lock (P1 item 1): needs a **fail-closed-vs-queue decision**
   (recommendation: fail-closed for integrity-critical PROPOSALS.md/audit writes).
3. Wave-7 P2 tier dispatch (6 items: accessibility, color semantics, bare excepts, 
   ThreadingHTTPServer unbounded, docs/CLAUDE.md drift, lock pid-write atomicity).
4. Post-P2 landing: re-audit (audit #4) vs five pillars. (2 consecutive cleans end loop.)
