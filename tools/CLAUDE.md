# tools/ — Build utilities

Local-only Python (stdlib only, no external deps), bash (POSIX, CRLF-safe). Never print secrets — report by pattern name/location only.

## secret_scan.py — Pre-push secret/credential detection gate

Scans staged/history/paths for secrets by regex pattern and credential filenames; blocks pushes on findings.

- `secret_scan.py --staged [--repo PATH]` — scan git staged files
- `secret_scan.py --history [--repo PATH]` — scan all git history blobs
- `secret_scan.py PATH [PATH...]` — scan files/dirs directly (recurse)

Exit: 0=clean, 1=findings, 2=usage error. Output masks secrets as `xxxx...`.

**Pragma escape** (pattern findings only; credential filenames always fatal):
```
# secretscan: allow-pattern-docs
```
Mark file's first 10 lines to report rule-based findings as ALLOWED-DOC (non-fatal). Use only for deliberate pattern documentation.

## agent-forensics.sh — Incident forensics / behavior reconstruction

Read-only git plumbing; reconstructs agent behavior snapshot or diffs behavior-controlling files.

- `bash tools/agent-forensics.sh <commit>` — print commit header, rules snapshot, CLAUDE.md, STATE.md, last 30 lines of BUILDLOG.md
- `bash tools/agent-forensics.sh --diff <commitA> <commitB>` — diff CLAUDE.md, STATE.md, docs/, monitor/CHARTER.md, hooks/ between commits

Exit: 0=success, 1=error (never raw git traces). Requires: git, head, tail, wc, grep.

## launch_tui.py — Spawn bash TUI script in detached terminal

Finds terminal (prefer Git Bash → Windows Terminal wt.exe), spawns script detached, idempotent via pidfile.

- `python launch_tui.py --script <path> [--title <title>] [--pidfile <path>]`

Exit: 0=success, 1=error. Output: exactly one line (`spawned (pid N)` or `already running (pid N)` or ERROR).

## power_selftest.py — Health check harness for /power bootstrap

Validates hooks (settings.json), brain (git status), heartbeats (state/ beat files), decisions/inbox counts, and secret scanner.

- `python power_selftest.py` — run all checks and print summary line + bullets for non-OK items

Configuration via `aesop.config.json` or env vars: `BRAIN_ROOT`, `AESOP_STATE_ROOT`, `SCRIPTS_ROOT`.
Gracefully degrades when targets don't exist (reports `n/a` instead of crashing).

Exit: 0=OK/DEGRADED, 1=FAIL. Output: `POWER-SELFTEST: OK|DEGRADED|FAIL — <checks>` + optional bullets.

## inbox_drain.py — Drain UI inbox submissions

Tracks processed dashboard submissions (work items queued while no session was running).

- `python inbox_drain.py pending` — list unprocessed inbox items
- `python inbox_drain.py mark <ISO-ts>` — mark one item processed
- `python inbox_drain.py mark-all` — mark all pending items processed

Configuration via `aesop.config.json` or env vars: `AESOP_INBOX_PATH`, `AESOP_INBOX_SEEN_PATH`, `AESOP_STATE_ROOT`.
Gracefully handles missing inbox/seen files (no crash).

Exit: 0 always. Output: `pending` lists items one per line; `mark`/`mark-all` prints summary to stderr.

## Invariants

- **Dependency-light**: Python tools must work on base Python 3 (no pip installs).
- **CRLF-safe shell**: no line continuations in .sh scripts; Git Bash + Linux compatible.
- **Never print secrets**: mask as pattern name + masked value only.
