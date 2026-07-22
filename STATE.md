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

## Phase: `wave-28-round1-built` (2026-07-22, current)
**v0.2.0 RELEASED by user** (npm latest; publish.yml OIDC green). **0.3.0 gates locked (user)**: (1) a
non-Claude core runs a full wave cycle, (2) a fresh /refinesystem clean pass immediately pre-release.
Wave-28 round 1: 12 lanes built+pushed (4 verified P1 fixes; WS3a wave_scheduler pilot — survived a
6-P1 NO-GO break-it review, all fixed fail-closed; windows parity; stateapi CI ratchet gate live;
docs/templates/preflight/transport lanes; merge_wait helper in ~/scripts). Scanner episode resolved by
USER DECISION: narrow REDACTION_SOURCE_FILES exemption (PR #322) — single file, single rule, findings
still reported; obfuscation removed. Live accuracy measured: gpt-4o-mini 32/32 (PR #321).
/refinesystem skill created (the hardening loop, separate from /buildsystem); round-1 lens fleet
(adversarial-on-fixes, scanner-exemption review, security expert, regression sweep, analyst, delta
audit) dispatched over the wave-28 surface. Train-28 assembling.

## NEXT STEPS (wave-28)
- Lead: verified P1 fixes (wave_loop add-residue unstage; cost_projection fired_alert honesty; reproduce.js
  'Missing:' classifier; stateapi_lint posix-normalized keys + baseline regen) → then wire stateapi_lint into
  CI and start the 32-violation burn-down.
- Windows python-parity lane (job red: cost_ceiling ledger perms, tracker SSE WinError 10053, collector
  NoneType); promote job to required after 5 green merges.
- P2s: read_api dead fallback delete, redaction URL-credential pattern, state_store/CLAUDE.md read_api entry,
  CHANGELOG wave-27 backfill, projection/ceiling window contract, explicit-repo-required preflight.
- USER-GATED: cut 0.2.0 — `gh release create v0.2.0 --notes-file RELEASE-NOTES.md` (publish.yml OIDC -> npm);
  WS1c outreach; live accuracy run (`python bench/accuracy_harness.py --mode live`, ~$5-10); external
  benchmark validation spend (wave-29, ~$200-500 grading).
- Tracked defers: state fragmentation, StateAPI boundary, proof-harness consolidation, MAX_PATH deep-state note,
  bench validation of tool_use_accuracy (wave-27 release gate candidate), tripwire root-stray widening,
  codex max_tokens bound, falsifiability script pytest-discovery footnote.

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
