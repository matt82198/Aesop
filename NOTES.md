# Aesop Technical Notes

## Audit-Log Truncation-Anchor Trust Model

### Overview

The aesop pre-push hook (`hooks/pre-push-policy.sh`) implements a multi-layered audit logging system that defends the integrity of push-event records through hash-chaining and truncation detection. This document describes the trust model and its limitations clearly.

### Components

#### 1. Hash Chain (In-Band Tamper Detection)

Each audit log entry is a JSON-formatted line that includes a `prev_hash` field containing the SHA256 hash of the previous entry:

```json
{"seq":1,"prev_hash":"GENESIS","ts":"...","repo":"...","event":"...","user":"..."}
{"seq":2,"prev_hash":"abc123def...","ts":"...","repo":"...","event":"...","user":"..."}
```

**How it works:**
- The first entry uses `prev_hash: "GENESIS"` as the initial anchor.
- Each subsequent entry chains the SHA256 hash of its predecessor, creating a linked chain.
- The `verify_audit_log()` function (line 93 in pre-push-policy.sh) reconstructs each hash and validates the chain linearly.
- If any entry is modified, its hash changes, breaking the chain immediately on re-verification.
- Sequence numbers (`seq` field) are also monotonically increasing, detecting silent drops.

**Detection capability:** Catches any entry-level tampering (modification of fields, deletion of middle entries, reordering).

#### 2. Truncation Anchor (Accidental Truncation Detection)

A sidecar file `.audit-tail-hash` stores the SHA256 hash of the last line in the audit log:

```bash
# After each log write (lines 267-269 or 304-306 in pre-push-policy.sh)
tail -n 1 "$audit_log" | tr -d '\n' | sha256sum | awk '{print $1}' > "$state_dir/.audit-tail-hash"
```

**How it works:**
- Every time a new entry is appended, the tail hash is updated atomically in the sidecar.
- On verification (line 151-160), the stored tail hash is compared to the hash of the current last line.
- If the log was truncated (last N lines removed), the sidecar will still hold the old tail hash, and the mismatch is detected.

**Detection capability:** Catches accidental truncation (e.g., log rotation failures, out-of-disk recovery, file corruption).

#### 3. Atomic Write Lock

The `acquire_audit_lock()` function (line 16) uses atomic `mkdir` to guard read-modify-append operations:

```bash
mkdir "$lock_dir" 2>/dev/null  # Atomic: only first caller succeeds
```

This prevents concurrent writers from interleaving entries or corrupting the JSON format. Stale locks (>300s old) are forcibly reclaimed.

#### 4. Git History as Final Authority

The audit log file (`state/SECURITY-AUDIT.log`) must be committed to the repository's git history. This ensures:
- A cryptographically signed, distributed copy in git objects.
- Immutability via git's content-addressed storage.
- Auditability across all machines that have cloned or pulled the repository.

**Critical:** Any forensic investigation should verify against git history, not just the local filesystem state.

### Trust Model Summary

| Layer | Detects | Mechanism |
|-------|---------|-----------|
| Hash chain | Entry tampering, deletion, reordering | SHA256 chaining + seq monotonicity |
| Truncation anchor | Accidental log truncation | Sidecar tail-hash comparison |
| Atomic lock | Concurrent write corruption | POSIX-atomic mkdir + 300s staleness recovery |
| Git history | Replay, off-box tampering, distributed audit | Content-addressed git objects + signatures |

### Limitations (Structural, Not Oversights)

**An adversary with local root or the ability to modify git hooks can defeat this model:**

1. **`--no-verify` bypass:** An attacker with shell access can run `git push --no-verify` to skip the pre-push hook entirely, preventing any audit event from being logged.

2. **Direct filesystem tampering:** An attacker with write access to `state/SECURITY-AUDIT.log` or `.audit-tail-hash` can modify the log directly, craft a new hash chain, and re-sign it.

3. **Hook modification:** The hook itself can be replaced with a version that logs false events or skips verification.

**These are not fixable locally** because the local machine is under attacker control. If an adversary owns root on the box, they own everything:
- The filesystem (including audit logs and sidecars)
- The git hooks and git configuration
- The audit-verification logic itself

**Defense scope:** The hash chain and truncation anchor defend against:
- **Accidental truncation** (filesystem/disk errors, log-rotation bugs)
- **Casual tampering** (modifying fields without recalculating hashes)
- **Human error** (accidentally deleting or corrupting the audit log)

They do *not* defend against a determined local root adversary.

### Verification Workflow

To verify the integrity of an audit log:

```bash
# Check in-band hash chain and truncation anchor
bash hooks/pre-push-policy.sh --verify-audit-log state/SECURITY-AUDIT.log

# Cross-check against git history (if the log is committed)
git log -p -- state/SECURITY-AUDIT.log | grep '{"seq'
```

If the hook reports "Hash chain broken" or "TRUNCATION SUSPECTED," the log has been tampered with or truncated. Investigation should then compare against any distributed copies in git remotes.

### References

- `hooks/pre-push-policy.sh` — Hook implementation (hash chain, truncation anchor, atomic lock)
- `tools/secret_scan.py` — Secret detection gate (logged when invoked)
- `daemons/run-watchdog.sh` — Log rotation and audit-log creation on backup cycles
