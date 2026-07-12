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

## Audit backlog (2026-07-12) — READ AUDIT-BACKLOG.md
Five-lens specialist review (architect, bash-pro, javascript-pro, honest-opinions,
security-auditor) produced a durable, priority-ranked TODO list in **AUDIT-BACKLOG.md**
(committed, pushed). 8 P0 (security+correctness — incl. secret-scanner pragma bypass,
untracked force-push, clone-injection RCE, branch-hook wrong-branch, wrong alert dir in
ui/serve.py, watchdog TOCTOU), ~11 P1, ~5 P2, 2 needing a user decision. RESUME HERE:
dispatch one Haiku per unclaimed ⬜ item (P0 first), TDD-first, ACCEPTANCE = the test gate;
flip the checkbox and commit per green item. Coordinate the 3 reconstitute.sh items into
one agent (same function).

## Standing order (user, 2026-07-12)
Rerun the refinement loop CONTINUOUSLY until tokens exhaust or gaps dry (2 consecutive
audits finding nothing new). Each cycle: (1) collect wave results → QA (TDD evidence
required for code) → commit+push per green item; (2) re-audit vs the five pillars +
monitor/cost briefs → rank remaining gaps; (3) dispatch next Haiku wave (6-8 parallel,
disjoint ownership, TDD-first). Proactive: never idle while agents run. On session
death: resume from this file — waves in flight are listed under Phase.

## Phase
`pr-open` — PR #16 (feature/behavior-as-code → main) opened 2026-07-12 after
final-catch (leakage sweep clean, full suite green: 26 node + 16 python + shell
self-tests). Waves 1+2 complete through ae1dc4b. Conductor3 fixes on separate
branch fix/monitor-path-and-rotation (c00c4fa), proposals #9/#10 annotated.
Outstanding: dash-extra.mjs fix + tests/dash-extra.test.mjs uncommitted, awaiting
TDD failing-first evidence from its agent; commit as follow-up on this branch.
Wave-3 candidates (from audits, unclaimed): state/ auto-creation; BUILDLOG lifecycle
doc; ACTIONS.log rotation wiring (use new rotate_logs.py); commit-format check in
pre-push hook; config key for fleet repo list (reconstitute TODO); INCIDENT-LOG
correlation; CI badge in README.

Implementation map (wave 1, as shipped):
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
