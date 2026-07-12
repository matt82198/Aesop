# tools/ — Build utilities and extension stubs

Local-only Python (stdlib only, no external deps), bash (POSIX, CRLF-safe). Never print secrets—report by pattern name/location only. See ../CLAUDE.md for project conventions.

## secret_scan.py — Pre-push secret/credential detection gate

Scans staged/history/paths for secrets by regex pattern and credential filenames; blocks pushes on findings.

- `secret_scan.py --staged [--repo PATH]` — scan git staged files
- `secret_scan.py --history [--repo PATH]` — scan all git history blobs
- `secret_scan.py PATH [PATH...]` — scan files/dirs directly (recurse)

Exit: 0=clean, 1=findings, 2=usage error. Output masks secrets as `xxxx...`.

Pragma escape (pattern findings only; credential filenames always fatal):
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

## Invariants

- **Dependency-light**: Python tools must work on base Python 3 (no pip installs).
- **CRLF-safe shell**: no line continuations in .sh scripts; Git Bash + Linux compatible.
- **Never print secrets**: mask as pattern name + masked value only.

## Recursion signal

No. Tools are tightly scoped utilities (secret scanning, forensics, TUI spawning); no sub-domain dense enough to warrant separate CLAUDE.md.
