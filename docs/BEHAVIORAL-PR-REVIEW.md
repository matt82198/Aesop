# Behavioral PR Review Checklist

For pull requests that modify operational rules, agent behavior, monitoring, or orchestration policy, follow this checklist **before merging**.

## 1. Rule & Cardinal Alignment

- [ ] Rule named explicitly (e.g., "Rule 3: Reliability core" or "Cardinal Rule 1: Dispatch model")
- [ ] PR title and description clearly state which rule(s) are affected
- [ ] Change aligns with (or explicitly updates) `docs/CARDINAL-RULES.md`
- [ ] No contradictions with other cardinal rules or guardrails

## 2. Blast Radius & Impact

- [ ] Impact scope documented (e.g., "affects all new monitor cycles", "affects heartbeat thresholds only", "no impact on running agents")
- [ ] Backward compatibility assessed (breaking changes require migration plan)
- [ ] Dependent systems identified (e.g., if monitor behavior changes, does ACTIONS.log parsing break?)
- [ ] Risk of silent failures assessed (e.g., does fallback-to-default mask issues?)

## 3. Verification & Testing

- [ ] Reproducible test steps provided (not "tested locally" — state what was tested)
- [ ] Test output attached or described (e.g., "ran `node monitor/collect-signals.mjs` twice, no duplicate PROPOSALS.md entries")
- [ ] Idempotency verified if applicable (safe to run multiple times in same cycle?)
- [ ] Edge cases covered (what if config missing? what if file unreadable?)

## 4. Rollback & Recovery

- [ ] Rollback plan documented (e.g., "revert commit + clear `.signal-state.json` + restart monitor")
- [ ] Rollback tested if possible (e.g., apply change, verify it works, revert, verify rollback works)
- [ ] No irreversible side effects (don't delete files without append-only logging first)

## 5. Single-Writer & Proposal Provenance

- [ ] If PROPOSALS.md or ACTIONS.log touched: confirm monitor still writes atomically (append-only)
- [ ] If new proposal emission logic added: confirm idempotency (no duplicate proposals from re-runs)
- [ ] If proposal came from monitor-collected signal: CHARTER.md action tier justified (AUTO vs PROPOSE)
- [ ] If proposal came from human: documented in PROPOSALS.md (what human, when, why)

## 6. Documentation & Handoff

- [ ] Related doc updated (CHARTER.md, CARDINAL-RULES.md, GOVERNANCE.md, etc.)
- [ ] Code comments added for non-obvious rule enforcement logic
- [ ] Affected stakeholders notified (e.g., if monitor behavior changes, note in CONTRIBUTING.md)

---

## Worked Example: Cost-cap-per-repo Change

**PR Title:** `feat(dispatch): Enforce Haiku cost cap per-repo instead of global`

**Rule affected:** Cardinal Rule 1 (dispatch model), Rule 6 (commit discipline)

**Blast radius:** All new agent dispatches via claude-code-cli; existing running agents unaffected

**Verification:**
- Ran dispatch-test-harness.sh with 3 mock repos, 5 Haiku spawns per repo
- Confirmed ledger recorded per-repo cost separately
- Rolled back, confirmed ledger reverted to single global entry
- No test script in package.json; test via integration harness

**Rollback:** Revert commit, clear `~/.claude/projects/*/FLEET-LEDGER.md`, restart orchestrator

**Documentation:** Updated DISPATCH-MODEL.md section "Cost tracking" with new per-repo tracking format

**Result:** ✓ Merged after review

---

## When to Request Changes (🔴 Critical)

- Missing verification or test steps
- Rollback plan untested or implausible
- Proposal came from monitor but action tier (AUTO/PROPOSE) unjustified
- Change introduces hardcoded paths, secrets, or usernames
- Backward-incompatible change with no migration documented
- Cardinal rule contradiction or guardrail violation

## When to Suggest (💡 Consider)

- Minor documentation clarification
- Additional edge case to test (not required, but good to consider)
- Related code that could benefit from similar fix (out of scope for this PR, open separate issue)

## Proposal lifecycle

Use `node tools/proposals.mjs list` to review pending proposals in monitor/PROPOSALS.md. To approve a proposal, run `node tools/proposals.mjs accept <signal-key>` (moves block to PROPOSALS-LOG.md under `## ACCEPTED <timestamp>`); to decline, run `reject <signal-key>` instead. Both commands are idempotent: re-running on an already-moved proposal is a no-op.
