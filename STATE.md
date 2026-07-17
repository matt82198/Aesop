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

## Phase: `wave-29-ci-fix` (2026-07-17, current)
Waves 25–29 shipped the credibility & safety pillar, answering the user critique (orchestration
core untested, Haiku-sufficiency unmeasured, no cost ceiling / kill switch under autonomous self-merge):
- **Wave-25** (PR #166): Opus-VERIFIED audit — 18/18 confirmed (0 hallucinations, vs wave-24's 4
  fake P0s), 16 fixes, no P0/P1.
- **Wave-26** (PR #167): `.HALT` kill-switch (`tools/halt.py`) + `tools/cost_ceiling.py`,
  orchestration-core tests, test-hygiene enforcement, held-out benchmark scaffold.
- **Wave-27** (PR #168): first REAL benchmark run (extraction — Haiku=Sonnet=Opus 12/12; honestly
  too easy to discriminate); dashboard cp1252 crash fixed.
- **Brake wired into dispatch** (claude-config `d69267d`): kill-switch/cost-ceiling gate in
  `wave-flat-dispatch.template.mjs`, PROVEN aborting a real dispatch (0 workers spawned; cleared cleanly).
- **Wave-28** (PR #169): state reconcile primitive (STATE.md↔state_store, git-authoritative, disjoint
  confirmed), cost-ceiling hardening (daily=today-UTC, shared ledger parser), repro-from-clean-clone CI;
  + judgment benchmark v2 — **Haiku/Sonnet 11/11, Opus 10/11** (harder set discriminates AND favored
  the cheap model; N=11, rubric-compliance caveat).
- **Wave-29** (PR #171): pure-docs PRs no longer deadlock (`ci` runs on every PR; skipped required
  checks were the root cause).

## Upcoming (wave-30 seed — full list in conductor3/WAVE27-SEED.md)
1. Larger-N + real-transcript-sampled judgment benchmark + a recorded cost axis, before asserting
   "Haiku sufficient for judgment" rather than suggesting it.
2. Wire phase_set events at wave-close so reconcile.py runs against a real populated state store.
3. UX/UI feature wave (deferred since wave-26): the 19 ideation candidates.
4. Re-add the docs-only CI speed optimization CORRECTLY (aggregator or step-gating) — wave-29 removed
   the broken skip for safety, trading ~2min CI on docs PRs.
5. **`release-candidate`** — full final-catch, version bump, tag, CI badge, curated release notes.

## Phase history (collapsed)
- `pr-open` → PR #16 opened after waves 1–2 (onboarding/policy/behavioral-PR/forensics/
  continuity scaffolding + rotate_logs, reconstitute, model-policy hook).
- `wave-3-p0-inflight` → all 8 P0 + P1/P2 audit items dispatched and landed.
- `backlog-cleared` → 26/26 items ✅, final-catch green, live gate + /power dashboard
  default (web :8770) + brain hook re-synced.
- `merged-wave4-open` → PR #16 merged (`f259c4f`); branch-per-item adopted; audit #1
  dispatched.
- `waves-25-29` → credibility & safety pillar shipped (PRs #166–#171): verified audit, kill-switch
  built + wired into dispatch + PROVEN, 2 real benchmark runs (extraction tie, judgment favored
  Haiku), reconcile primitive, cost-ceiling hardening, repro CI, docs-deadlock CI fix.

## NEXT STEPS (wave-30)
1. **Larger-N judgment benchmark** — sample judgment tasks from real fleet transcripts + record a
   cost axis (bench/ v3), so "Haiku sufficient for judgment" can be asserted, not just suggested.
   Current evidence (N=11): Haiku/Sonnet 11/11, Opus 10/11 — suggestive, not conclusive.
2. **phase_set event emission** — reconcile.py has the primitive; add a wave-close hook that emits
   a phase_set event so it runs against a populated state store instead of reporting drift-on-first-use.
3. **UX/UI feature wave** — the 19 ideation candidates (memory: waves-need-ux-ui-features); route to
   general-purpose Haiku with playwright proof, not the delegating specialists.
4. **Docs-only CI speed** (optional) — re-add the fast-path correctly (aggregator/step-gating);
   wave-29 traded it for safety (ci now runs full ~2min on docs PRs).
5. **Deeper still-open critique items** — orchestration core is only partially in-repo-testable (true
   model dispatch lives in the harness); external reproduction now has a repro.yml but no third party
   has run it. Both are structural, not quick fixes — track honestly.
