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
`final-catch` — all five pillars implemented, QA'd, committed, pushed 2026-07-12.
QA fixes of note: RESTORE.md reset-ordering hazard; hook JSON escaping + AESOP_ROOT
default; collector .signal-state.json persistence. Remaining: Fable final-catch on
the branch diff, then PR feature/behavior-as-code → main.

Implementation map (as shipped):
1. onboarding: CLAUDE-TEMPLATE.md, docs/MEMORY-TEMPLATE.md, bin/cli.js, README.md
2. policy: hooks/pre-push-policy.sh, docs/HOOK-INSTALL.md (audit → state/SECURITY-AUDIT.log)
3. behavioral-PRs: .github/pull_request_template.md, docs/BEHAVIORAL-PR-REVIEW.md,
   CONTRIBUTING.md, monitor/collect-signals.mjs (os.tmpdir fix + PROPOSE-tier emission)
4. forensics: tools/agent-forensics.sh, docs/FORENSICS.md
5. continuity: docs/RESTORE.md
Implementers verify but do NOT commit; orchestrator commits per green item after QA.

## NEXT STEPS
1. Collect implementer results; QA loop (review → bugfix → lint) until green.
2. Fable final-catch on the full diff.
3. Commit + push each green item (secret-scan gated); PR feature/behavior-as-code → main.
4. Update this file at each phase boundary.
