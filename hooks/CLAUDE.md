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

## Hook: pre-commit-waveguard.sh

Prevents accidental commits to the PRIMARY aesop tree during a wave cycle. Runs on `git commit` via `.git/hooks/pre-commit`.

**Purpose**: During orchestrated waves, the orchestrator sets a marker file (`state/.wave-in-flight`) in the PRIMARY tree only. Sibling worktrees do not inherit this marker (separate working trees), so fleet agents commit freely in worktrees while stray commits to the primary tree are rejected.

**Mechanism**:
1. **Marker Contract**: Orchestrator writes `state/.wave-in-flight` in the PRIMARY tree before dispatching wave work. The marker is git-ignored, so sibling worktrees checked out during the wave do NOT carry it.
2. **Pre-Commit Check**: Hook resolves the marker relative to the CURRENT working tree via `git rev-parse --show-toplevel` (NOT a hardcoded `$HOME/aesop` — that resolved to the primary tree from every worktree and blocked the whole fleet mid-wave, the wave-24 incident). Primary tree (has marker during a wave) → exit 1 (reject); sibling worktree (no marker) → exit 0 (allow).
3. **Override**: User or orchestrator may delete `state/.wave-in-flight` to manually allow commits to primary tree.

**Exit Contract**:
- Exit 0: Marker absent, commit allowed (normal operation)
- Exit 1: Marker present, commit blocked with clear error message

**Error Message**:
```
Error: Wave in flight. Commit from a sibling worktree, or clear <marker_path> to override.
```

**Installation**:
- Run `bash hooks/install-waveguard.sh` to idempotently install into `.git/hooks/pre-commit`.
- If a pre-commit hook already exists, installer backs it up (`.git/hooks/pre-commit.waveguard-backup`) and wraps both (waveguard first, then existing hook if present).

**Idempotency**:
- Installer checks if hook already calls waveguard; skips if already installed.
- Safe to re-run multiple times.

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
