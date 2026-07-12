# STATE — aesop refinement loop

## Intent
Aesop is the reference implementation of the thesis: **agent behavior is source code** —
rules, memory, hooks, and checkpoints are versioned, portable, diffable filesystem
artifacts in git, so review/versioning/inheritance/enforcement/forensics apply to how
agents work. Single-user survival hack → cross-team product.

## Locked decisions (user, 2026-07-12)
- Thesis fixed as the development goal; refinement loop prioritizes the five pillars:
  1. **Onboarding-by-clone** — clone the team brain, agent primed instantly.
  2. **Guardrails-in-code** — hooks as enforced, auditable org policy (not memos).
  3. **Behavioral PRs** — rule/memory changes flow proposal → review → merge → fleet-wide.
  4. **Forensic replay** — checkout rules+memory at a commit; agent failures are bisectable.
  5. **Cross-machine continuity** — brain reconstitutes from remotes; compute disposable.
- Orchestrator (Fable) main-thread; subagents Haiku; TDD-first; feature branch only.

## Phase
`audit` — five read-only pillar auditors fanned out 2026-07-12; each returns
WHAT EXISTS / GAPS / SMALLEST SHIPPABLE. Monitor + memory keeper running in background.

## NEXT STEPS
1. Synthesize five audit briefs; rank smallest-shippable items by pillar impact.
2. Dispatch Haiku implementers (disjoint file ownership, TDD where testable).
3. QA loop (review → bugfix → lint) until green; Fable final-catch.
4. Commit + push each green item (secret-scan gated); PR to main.
5. Update this file at each phase boundary; append snapshots to BUILDLOG below convention.
