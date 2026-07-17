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

## Phase: `wave-26-credibility-safety` (2026-07-16, current)
Wave-25 CLOSED (2026-07-16, commit 53212d9 PR #166): Opus audit found 18/18 confirmed findings,
16 unique fixed (secret-gate fail-closed, tests-run, py-portability, gitattributes, claudemd-drift,
docs-currency, rotate-claim). No P0/P1. Wave-26 in progress: credibility & safety pillar.

**Wave-26 focus**: Address user critique that orchestration core is untested, Haiku sufficiency
claim unmeasured, no cost ceiling / kill switch despite autonomous self-merge. Rigor required:
genuine measurement, not theater. Held-out benchmark scaffold, cost-ceiling enforcement,
orchestration test harness (monitor loop tested), guard-rails verified under load.

## Upcoming phases
1. **`wave-26-measurement`** — Orchestration core instrumentation (monitor loop, lock contention,
   heartbeat staleness, cost/token tracking per agent + fleet). Held-out benchmark fixture
   (sealed input, measure cold-start + per-cycle time/tokens). Cost ceiling gates (set $/cycle
   limit; agent scales adaptively). Kill-switch wiring (orchestrator pause/resume via sentinel
   file or state-push). Guard-rail harness tests under load (concurrent writes, flaky I/O,
   network delays). Subagent-model verification (spot-check Haiku adequacy vs Opus on a few
   items; measure delta). Report honestly: what was/wasn't proved.
2. **`wave-27-reconciliation`** — State-layer deep rework: move state off git (event-sourced SQLite
   BUILDLOG/AUDIT ledger) + batch git to wave boundary (latency + team scale). Reproduce-from-
   clean-clone CI fixture (verify onboarded checkout can replay full wave with no ambient state).
3. **`wave-28-enforcement`** — Guardrail harness codification (branch discipline, secret gates,
   cost ceilings as exit-1 blocks in pre-push hook + CI). Review/audit loop metrics (P0/P1
   escape rate, fix latency, Opus vs Haiku quality delta). Automated enforcement tests.
4. **`release-candidate`** — Full final-catch (all suites green), version bump, tag, CI badge,
   release notes curated from the backlog's wave-by-wave history.

## Phase history (collapsed)
- `pr-open` → PR #16 opened after waves 1–2 (onboarding/policy/behavioral-PR/forensics/
  continuity scaffolding + rotate_logs, reconstitute, model-policy hook).
- `wave-3-p0-inflight` → all 8 P0 + P1/P2 audit items dispatched and landed.
- `backlog-cleared` → 26/26 items ✅, final-catch green, live gate + /power dashboard
  default (web :8770) + brain hook re-synced.
- `merged-wave4-open` → PR #16 merged (`f259c4f`); branch-per-item adopted; audit #1
  dispatched.

## NEXT STEPS (wave-26)
1. **Orchestration harness instrumentation** — Add telemetry to monitor loop (lock wait times,
   write coalescing, heartbeat cadence). Cost tracking per agent + fleet. Cold-start timing.
2. **Held-out benchmark scaffold** — Sealed input fixture (e.g. standard backlog); measure
   wave time/tokens cold vs warm. Commit baseline to git; CI runs post-merge to detect drift.
3. **Cost ceiling enforcement** — Configurable $/cycle budget; agent scale adapts (fewer
   parallel, smaller footprint per agent) when approaching limit. Test: exceed limit → adapt.
4. **Kill-switch wiring** — Sentinel file or API endpoint to pause/resume orchestrator mid-wave
   without losing state. Verify: pause stops new agent dispatch; resume resumes cleanly.
5. **Subagent-model verification** — A/B spot-check: Haiku vs Opus on 3–5 representative items
   (e.g. one UI fix, one test, one docs). Measure latency/quality/cost delta objectively.
   Publish honest verdict: sufficiency confirmed or model reclassification needed.
6. **Guard-rail load tests** — Concurrent writes (monitor + UI emitting proposals), flaky I/O
   (delayed responses), network jitter. Verify locks hold, no data loss, no silent failures.

**Wave-27 deferrals** (not wave-26; backlog for wave-27 kickoff):
- State-layer rework: event-sourced SQLite (BUILDLOG/AUDIT ledger off git); batch git at
  wave boundary.
- Reproduce-from-clean-clone CI: verify onboarded checkout replays wave without ambient state.
