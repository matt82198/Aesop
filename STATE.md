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

## Phase: `stable-0.1.1-on-main` (2026-07-18, current)
**0.1.1 on main** (npm publish USER-GATED: `gh release create v0.1.1 --notes-file RELEASE-NOTES.md`);
0.1.0 live on npm @latest. This session shipped rc.2->rc.8 + integration train, then the two pillars:
- **Scope-minification** (PR #196, user #1): one CLAUDE.md per Haiku task, root = pure map, adversarially lossless-verified.
- **Center-verification** (PR #202): the answer to the "over-engineered shell, hoped-for center" critique —
  adversarialReview template phase (break-it-vs-spec per shipped item), mutation_test.py (flags tautological
  tests), defect_escape.py (first-try-green as telemetry), hidden-case coding bench. MEASURED: first-try-green 43%,
  0 logic bugs caught by authoring-Haiku's own tests, 6 P1 shipped green -> "green = assembles+passes-own-tests, NOT correct".
Also this session: accumulated rc.4-rc.8 audit (adversarial-verified), first-hour adopter fixes, dispatch-visibility
panel, claudemd_lint + portability CI gates, durable scheduled-task monitor (root-caused the always-dying loop),
ci_merge_wait STALE-bug fix. Org waves: GitHub/portfolio/Medium all current.

## NEXT STEPS
- Flip `adversarialReview: true` as the standing dispatch default (dogfood it on the next wave).
- Adversarial-found P2s queued (plans/audit-rc4-rc8-backlog.md): fleet_ledger timestamp-injection, wave_preflight/common.py
  future-date fresh-forever, test-hygiene root cause (tests writing mangled cwd paths).
- Multi-tool portability (spike, plans/spike-multitool-portability.md): 5-op AgentDriver; open-models REQUIRE the
  verification layer first. 0.2.0 initiative.
- npm publish 0.1.1 (USER-GATED).

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
- `waves-25-to-rc1` → published @matt82198/aesop@0.1.0-rc.1 (npm dist-tag `rc`, OIDC trusted publishing);
  GitHub release v0.1.0-rc.1; relicensed to PolyForm Strict 1.0.0 (SOURCE-AVAILABLE); benchmark
  measured (Haiku 39/39 vs Opus 38/39); kill-switch proven on a real wave; state-layer primitive
  audited-clean. 5 honest open residuals: benchmark (curated→transcript-sampled + latency); cost-ceiling
  (brake→live wiring); state_store sqlite CI sharding; model-dispatch core (structural, out-of-repo);
  third-party reproduce.yml untested.

## NEXT STEPS (wave-rc.2)
Honest open residuals — tracked, not ignored:
1. **Benchmark scope (curated → real-transcript-sampled)** — Current evidence (N=39) is a curated judgment set,
   not a transcript sample from live fleet. Next: sample judgment tasks from real aesop/conductor3 fleet transcripts,
   add a latency axis (response time cost), then assert "Haiku sufficient for judgment" + latency profile.
2. **Cost-ceiling: brake → live wiring** — The ceiling.py exists and is configurable, but the dispatch loop
   does not yet query it per-turn or enforce it as a live budget-guard. Wire cost-ceiling into the dispatch
   loop so per-item/per-wave spend is bounded LIVE, not just brake-able post-facto.
3. **State_store sqlite concurrency under CI sharding** — tests/test_state_store.py's concurrent-append test
   flakes under parallel CI shards (database locked). Fix: per-shard DB isolation (separate .db per shard) or
   timeout + retry logic on OperationalError (database is locked).
4. **Model-dispatch core out-of-repo (structural)** — True model routing/agent-type selection lives in the Claude
   Code harness, not in aesop. This is a cross-product concern requiring upstream movement; tracked for visibility
   but not actionable in-repo.
5. **Third-party reproduce.yml untested** — No external user has run the reproduce.yml end-to-end from a clean clone
   yet. Post-release: solicit a user run + gather feedback on UX, missing docs, env assumptions, etc.
