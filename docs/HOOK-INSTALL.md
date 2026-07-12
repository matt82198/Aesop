# Git Pre-Push Hook Installation Guide

**Ship a hook, not a memo.** This guide explains how to install and customize the pre-push policy hook that turns organizational security rules into executable code.

## What the Hook Does

`hooks/pre-push-policy.sh` enforces two checks at git push time:

1. **Branch Policy**: Blocks direct pushes to `main` or `master` branches (feature branches only).
2. **Secret Scan**: Runs `tools/secret_scan.py --staged` to detect credentials before they reach the remote.

Both blocks append a JSON audit record to `state/SECURITY-AUDIT.log` with timestamp, repo, reason, and user — creating a reviewable trail of policy enforcement.

## Installation

### Option 1: Symlink (Linux / macOS / Git Bash on Windows)

The cleanest method — hook stays in sync with repo updates:

```bash
ln -s ../../hooks/pre-push-policy.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

### Option 2: Copy (Windows, or to break sync)

Copy the hook directly into `.git/hooks/`:

```powershell
Copy-Item hooks\pre-push-policy.sh .git\hooks\pre-push
```

On Windows PowerShell, mark it executable if your git respects file mode:

```bash
git config core.filemode false
```

## Testing

Before committing to org-wide deployment, verify the hook works:

```bash
bash hooks/pre-push-policy.sh --test
```

Expected output: **PASS** for all three checks (branch policy, feature branch allowance, audit log format).

## Audit Log Format

Each block writes one JSON line to `${AESOP_ROOT:-$HOME/aesop}/state/SECURITY-AUDIT.log`:

```json
{"ts":"2025-07-12T14:32:01Z","repo":"aesop","event":"push_blocked","reason":"secret_scan_failure","user":"alice"}
```

**Fields:**
- `ts`: ISO-8601 UTC timestamp
- `repo`: Repository basename
- `event`: Always `push_blocked`
- `reason`: `push_to_protected_branch` or `secret_scan_failure`
- `user`: Git user.name (fallback: "unknown")

Parse the log with standard JSON tools:

```bash
cat state/SECURITY-AUDIT.log | jq '.reason' | sort | uniq -c
```

## Org Distribution & Customization

### Standard Distribution

1. Commit the hook to a shared repo or policy repository.
2. Instruct teams to symlink or copy per option above.
3. Communicate audit log location and parsing examples.

### Customizing Checks

To add org-specific rules (e.g., branch naming conventions, required CI status):

1. Edit `hooks/pre-push-policy.sh` and add a new check function:
   ```bash
   check_my_org_policy() {
     # your logic here
     return 0 or 1
   }
   ```

2. Call it from `main()` before exit, and log blocks:
   ```bash
   if ! check_my_org_policy; then
     log_block "my_org_policy_violation"
     exit 1
   fi
   ```

3. Update `run_test_mode()` to include test cases for the new check.

4. Commit and redistribute.

### Disabling in CI/CD

If CI systems need to bypass the hook (e.g., for automated releases), set:

```bash
export GIT_SKIP_HOOKS=pre-push
git push
```

Or use `git push --no-verify` (explicitly allowing humans to opt out).

## Audit Log Rotation

The audit log is append-only. For long-running deployments, consider log rotation:

```bash
if [ -f state/SECURITY-AUDIT.log ] && [ $(stat -f%z state/SECURITY-AUDIT.log 2>/dev/null || stat -c%s state/SECURITY-AUDIT.log) -gt 1000000 ]; then
  mv state/SECURITY-AUDIT.log "state/SECURITY-AUDIT.$(date +%Y%m%d-%H%M%S).log"
fi
```

## Troubleshooting

**Hook not running?**
- Verify `.git/hooks/pre-push` exists and is executable: `ls -la .git/hooks/pre-push`
- Check symlink target if using option 1: `readlink .git/hooks/pre-push`
- Git version must be 1.8.2+; run `git --version`

**"Push blocked" but no reason in audit log?**
- Check `${AESOP_ROOT:-$HOME/aesop}/state/` directory exists and is writable.
- Verify git config: `git config user.name` is not empty.

**Secret scan warns but doesn't block?**
- `secret_scan.py` must exist at `AESOP_ROOT/tools/secret_scan.py`.
- If missing, the hook warns but allows push (fail-open default).
- For fail-closed behavior, edit the hook and remove the early `return 0`.

## References

- Hook source: `hooks/pre-push-policy.sh`
- Secret scanner: `tools/secret_scan.py`
- Audit log location: `state/SECURITY-AUDIT.log` (git-ignored)
- Cardinal rule: [CARDINAL-RULES.md](./CARDINAL-RULES.md)
