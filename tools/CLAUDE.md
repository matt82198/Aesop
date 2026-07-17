# tools/ — Build utilities

Local-only Python (stdlib only, no external deps), bash (POSIX, CRLF-safe). Never print secrets — report by pattern name/location only.

## FILES

- `alert_bridge.py` — Slack/Discord webhook bridge for SECURITY-ALERTS
- `bench_runner.py` — Held-out benchmark runner + scorer with accuracy + cost axis (offline mock runner; pluggable Haiku/Sonnet/Opus runners return text or (text, usage))
- `buildlog.py` — Uniform BUILDLOG.md appender
- `ci_merge_wait.py` — CI-gated merge helper (polls gh pr view until SUCCESS)
- `common.py` — Shared utilities (state directory resolution, heartbeat staleness checks)
- `cost_ceiling.py` — Cost-ceiling checker: trips the HALT kill-switch when configured token limits are exceeded
- `ensure_state.py` — Scaffold STATE.md and BUILDLOG.md templates
- `eod_sweep.py` — End-of-day safety check (dirty trees, unpushed commits)
- `fleet_ledger.py` — Append-only cost ledger with harvest/rotate
- `fleet_prompt_extractor.py` — Extract and deduplicate Agent/Task spawn prompts
- `halt.py` — Kill-switch: writes/reads/clears the `.HALT` sentinel that daemons/dispatch check to stop the fleet
- `healthcheck.py` — Fleet health aggregator (heartbeat/alert/orchestrator status)
- `heartbeat.py` — Single-instance loop liveness registry
- `inbox_drain.py` — Drain UI inbox submissions
- `launch_tui.py` — Spawn bash TUI script in detached terminal
- `lock.mjs` — Fail-closed atomic lock acquisition (exponential backoff + stale-lock detection)
- `metrics_gate.py` — PR gate for hard numeric claims in markdown
- `orchestrator_status.py` — Atomic orchestrator status updates
- `power_selftest.py` — Health check harness for /power bootstrap
- `prepublish_scan.py` — Pre-publish full history + staged-changes scan gate
- `proposals.mjs` — Proposal lifecycle manager (list/accept/reject)
- `reconcile.py` — Detect/resolve drift between git STATE.md (phase) and the state_store projection (git-authoritative; --resolve appends to SQLite only)
- `reconstitute.sh` — Clone/fetch repos from config with security validation
- `rotate_logs.py` — Log rotation utility with size/line thresholds
- `scanner_selftest.py` — Regression harness for secret_scan.py
- `secret_scan.py` — Pre-push secret/credential detection gate
- `self_stats.py` — Git-derived metrics counter + README block generator
- `session_usage_summary.py` — Aggregate token usage across session transcripts
- `stall_check.py` — Automated agent transcript stall detector
- `svg_to_png.mjs` — Rasterize SVG to PNG via @resvg/resvg-js (with lazy import error handling)
- `transcript_replay.py` — Replay post-commit edits from transcripts to recover work
- `transcript_timeline.py` — Extract Write/Edit/Read timeline from transcripts
- `verify_dash.py` — Browser proof for realtime SSE dashboard
- `verify_submit_encoding.py` — Browser proof for /submit UTF-8 inbox bootstrap
- `verify_prboard.py` — Browser proof for the Wave PR Board (/api/wave/prs), gh stubbed via AESOP_GH_BIN
- `verify_agent_inspector.py` — Browser proof for the Agent Inspector drawer (/api/agent?id=), agents + transcript stubbed via a temp AESOP_ROOT
- `agent-forensics.sh` — Incident forensics / behavior reconstruction

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
