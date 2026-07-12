## Description

Briefly describe what this PR does and why it's needed.

## Type of Change

- [ ] New feature
- [ ] Bug fix
- [ ] Documentation update
- [ ] Behavioral change (rule, hook, memory convention) — see section below

## Behavioral Change?

**IMPORTANT:** If this PR modifies operational rules, hooks, agent configuration, or memory conventions (anything in `CLAUDE.md`, `docs/`, monitoring behavior, or dispatch model), complete this section.

- **Rule or behavior changed:** _(e.g., "Haiku cost cap now enforced per-repo instead of global")_
- **Cardinal rule(s) affected:** _(List which rules in `docs/CARDINAL-RULES.md`)_
- **Impact radius:** _(e.g., "affects all new agent dispatches", "affects monitor signal collection", "no impact on running agents")_
- **How tested:** _(e.g., "ran collect-signals.mjs twice, confirmed no duplicate PROPOSALS.md entries"; "manual orchestration test with 3 Haiku subagents")_
- **Rollback plan:** _(e.g., "revert to previous version and restart monitor", "clear .signal-state.json and re-run monitor cycle")_

**See:** [`docs/BEHAVIORAL-PR-REVIEW.md`](../../docs/BEHAVIORAL-PR-REVIEW.md) for reviewer checklist.

If this does NOT change any rules or behavior, you may leave this section empty.

## Testing

- [ ] Manually tested (describe: _______)
- [ ] Monitor/watchdog test passed (if applicable)
- [ ] No new secrets or hardcoded paths introduced
- [ ] Documentation updated

## Checklist

- [ ] Code follows the style guide (CONTRIBUTING.md)
- [ ] No hardcoded local paths, usernames, or secrets
- [ ] Changes are backward compatible (or migration documented)
- [ ] CHANGELOG.md updated (if user-facing)
