# tools/ — Build utilities

Local-only Python (stdlib only, no external deps), bash (POSIX, CRLF-safe). Never print secrets — report by pattern name/location only.

## FILES

- `lock.mjs` — Fail-closed atomic lock acquisition (exponential backoff + stale-lock detection)
- `secret_scan.py` — Pre-push secret/credential detection gate
- `scanner_selftest.py` — Regression harness for secret_scan.py
- `prepublish_scan.py` — Pre-publish full history + staged-changes scan gate
- `metrics_gate.py` — PR gate for hard numeric claims in markdown
- `self_stats.py` — Git-derived metrics counter + README block generator
- `verify_dash.py` — Browser proof for realtime SSE dashboard
- `verify_submit_encoding.py` — Browser proof for /submit UTF-8 inbox bootstrap
- `ci_merge_wait.py` — CI-gated merge helper (polls gh pr view until SUCCESS)
- `alert_bridge.py` — Slack/Discord webhook bridge for SECURITY-ALERTS
- `proposals.mjs` — Proposal lifecycle manager (list/accept/reject)
- `power_selftest.py` — Health check harness for /power bootstrap
- `healthcheck.py` — Fleet health aggregator (heartbeat/alert/orchestrator status)
- `buildlog.py` — Uniform BUILDLOG.md appender
- `ensure_state.py` — Scaffold STATE.md and BUILDLOG.md templates
- `fleet_ledger.py` — Append-only cost ledger with harvest/rotate
- `heartbeat.py` — Single-instance loop liveness registry
- `stall_check.py` — Automated agent transcript stall detector
- `inbox_drain.py` — Drain UI inbox submissions
- `orchestrator_status.py` — Atomic orchestrator status updates
- `reconstitute.sh` — Clone/fetch repos from config with security validation
- `eod_sweep.py` — End-of-day safety check (dirty trees, unpushed commits)
- `agent-forensics.sh` — Incident forensics / behavior reconstruction
- `launch_tui.py` — Spawn bash TUI script in detached terminal
- `rotate_logs.py` — Log rotation utility with size/line thresholds

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


## Invariants

- **Dependency-light**: Python tools must work on base Python 3 (no pip installs).
- **CRLF-safe shell**: no line continuations in .sh scripts; Git Bash + Linux compatible.
- **Never print secrets**: mask as pattern name + masked value only.
- **Config-driven paths**: heartbeat/ledger/logs use AESOP_STATE_ROOT env var (default ./state) or CLI args; no hardcoded personal paths.
- **Fragment-assembled secrets in tests**: scanner_selftest.py concatenates dummy secrets at runtime so pattern text never appears contiguously (self-scan invariant).
- **verify_*.py are mandatory CI gates**: verify_dash.py and verify_submit_encoding.py are required pre-push gates; use `--allow-skip` only in truly browserless environments (CI must run both).
- **lock.mjs is the ONLY lock implementation**: never reimplement locking in proposals.mjs or elsewhere; all proposals/state updates must use fail-closed lock.mjs with exponential backoff + stale-lock breaking.
