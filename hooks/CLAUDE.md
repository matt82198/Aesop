# hooks/ — Installable org-policy git pre-push enforcement

**Purpose**: Ship executable git hooks that gate pushes with organization security policies (branch protection, secret scanning).

## Hook: pre-push-policy.sh

Runs on `git push` via `.git/hooks/pre-push` symlink or copy.

**Checks & Exit Contract**:
1. `check_branch_policy()` — blocks direct pushes to main/master; exit 1 on violation
2. `check_secret_scan()` — runs `tools/secret_scan.py --staged`; exit 1 on failure
3. Both trigger `log_block()` to append audit record before exit

**Audit-Ledger Contract**:
- Path: `${AESOP_ROOT:-$HOME/aesop}/state/SECURITY-AUDIT.log` (append-only, git-ignored)
- Format: JSON-lines (one record per line)
- Schema: `{"ts":"2025-07-12T14:32:01Z","repo":"aesop","event":"push_blocked","reason":"secret_scan_failure","user":"alice"}`
- All string values must be json_escaped (backslash → `\\`, quote → `\"`)

**Self-Test Convention**:
- `bash hooks/pre-push-policy.sh --test` runs the self-test suite, including:
  1. Branch policy blocks main/master
  2. Branch policy allows feature/* branches
  3. Audit log JSON format is valid
  4. JSON escaping handles special chars (quotes, backslashes)
  5. stdin handling (git pre-push pipe) doesn't crash hook
- Exit 0 = all pass; exit 1 = any fail

**Installation**:
- See `docs/HOOK-INSTALL.md` for symlink (Linux/macOS/Git Bash) and copy (Windows) methods
- Test with `bash hooks/pre-push-policy.sh --test` before org distribution

## Hook: hooks/claude/force-model-policy.mjs

Claude Code hook enforcing subagent Haiku dispatch (cost optimization).

**Trigger**: On skill invocation or task delegation from main orchestrator thread. Examines Claude API request and enforces model constraint.

**Policy**:
- **Main orchestrator** (Fable/Opus on primary): no override (uses native model)
- **Subagent dispatch** (fleet workers): **enforce Haiku** (claude-haiku-4-5-*). Exit 1 on non-Haiku model request.
- **Specialists** (typed dispatches): Pin model to Haiku in the dispatch call; hook validates + blocks if violated.

**Logging**:
- On policy violation: log to `state/SECURITY-ALERTS.log` with timestamp, model-name, worker-id, and reason.
- No alerts on compliant requests.

**Self-Test**:
- `node hooks/claude/force-model-policy.mjs --test` validates:
  1. Haiku model allowed on subagents
  2. Non-Haiku (e.g., Opus) blocked on subagents
  3. Orchestrator not subject to policy
  4. JSON logging format is valid
- Exit 0 = all pass; exit 1 = any fail

## Invariants

- POSIX sh compatible, CRLF-safe (no line continuations)
- Tolerate git pre-push stdin (ref list) + optional args without choking
- Fail-open only for missing optional tooling (secret_scan.py absent → allow); fail-closed for policy checks
- Use `AESOP_ROOT` env var or `$HOME/aesop` fallback; no hardcoded machine paths/usernames
