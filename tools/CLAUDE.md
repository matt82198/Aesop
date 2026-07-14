# tools/ — Build utilities

Local-only Python (stdlib only, no external deps), bash (POSIX, CRLF-safe). Never print secrets — report by pattern name/location only.

## FILES

**Locking & atomicity**:
- `lock.mjs` — Fail-closed atomic lock acquisition (exponential backoff + stale-lock detection) for PROPOSALS.md and related single-writer operations

**Secret scanning & compliance**:
- `secret_scan.py` — Pre-push secret/credential detection gate; scans staged, history, or paths by regex + filename patterns
- `scanner_selftest.py` — Regression harness for secret_scan.py; validates TP/FP vectors and self-scan cleanliness
- `prepublish_scan.py` — Pre-publish gate running full git history + staged-changes scans; exit 0 only if CLEAR-TO-PUBLISH
- `metrics_gate.py` — PR gate for numeric claims in *.md files; verifies hard percentages/multipliers/dollar amounts via source comments

**Browser-level verification (CI gates)**:
- `verify_dash.py` — Browser proof for realtime SSE dashboard; validates console errors, backlog rendering, live SSE updates (use `--allow-skip` in browserless environments)
- `verify_submit_encoding.py` — Browser proof for /submit UTF-8 inbox bootstrap; validates encoding on Windows and real CSRF flow (use `--allow-skip` in browserless environments)

**CI/merge operations**:
- `ci_merge_wait.py` — CI-gated merge helper; polls gh pr view until checks conclude (SUCCESS/FAILURE), then merges ONLY if SUCCESS (structurally unreachable otherwise)
- `metrics_gate.py` — NO-UNVERIFIED-METRICS gate; scans git diff for hard numeric claims (%, multipliers, $) in markdown that lack verification comments

**Alerting**:
- `alert_bridge.py` — Slack/Discord webhook bridge; scans SECURITY-ALERTS.log (>= min_severity) + heartbeat staleness, POSTs opt-in (cursor-idempotent, webhook URL masked). Called per-cycle by run-watchdog.sh.

**Orchestration infrastructure**:
- `proposals.mjs` — Proposal lifecycle manager (list/accept/reject); uses fail-closed locking for atomic state updates
- `power_selftest.py` — Health check harness for /power bootstrap; validates hooks, brain, heartbeats, decisions, and scanner
- `buildlog.py` — Uniform BUILDLOG.md appender; ensures consistent timestamp + message + git HEAD ref formatting
- `ensure_state.py` — Scaffold STATE.md and BUILDLOG.md templates in state directory if missing
- `fleet_ledger.py` — Append-only ledger of agent runs, resource use, and verdicts; supports harvest (scan tasks) and rotate (archive)
- `heartbeat.py` — Single-instance loop liveness registry; write beats to state/.heartbeats/<name>, check staleness across fleet
- `stall_check.py` — Automated silent-hang detector; scans agent transcript mtimes to identify stalled agents, feeds watchdog monitoring
- `inbox_drain.py` — Drain UI inbox submissions; tracks processed dashboard work items (queue while no session running)
- `orchestrator_status.py` — Atomic writer for state/orchestrator-status.json (set/clear activity+phase); feeds the dashboard status panel

**Repository operations**:
- `reconstitute.sh` — Clone or fetch repos from config (tab/space-delimited); validates clone targets against fleet-root (physical paths, security)
- `eod_sweep.py` — End-of-day safety check; scans repos for dirty trees, unpushed commits, untracked files; optional auto-push

**Utilities**:
- `agent-forensics.sh` — Incident forensics / behavior reconstruction; read-only git plumbing to snapshot or diff behavior-controlling files
- `launch_tui.py` — Spawn bash TUI script in detached terminal; finds terminal (Git Bash → Windows Terminal), idempotent via pidfile
- `rotate_logs.py` — Log rotation utility; archives oldest lines when file exceeds size/line thresholds; ensures no data loss

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

## heartbeat.py — Single-instance loop liveness registry

Fleet-wide heartbeat tracking for monitoring loop freshness. Write heartbeat "beat" to registry, check all beats for staleness.

- `heartbeat.py beat <name> [status] [--state-dir DIR] [--brain]` — write epoch to state/.heartbeats/<name> (or ~/.claude/.heartbeats with --brain)
- `heartbeat.py check [--max-age SEC] [--state-dir DIR]` — check all beats, exit 0 if all alive

## stall_check.py — Automated silent-hang detector for agent transcripts

Scans agent transcript files (agent-*.jsonl) by mtime to detect stalled/silent-hanging agents.

- `stall_check.py [--transcripts-root DIR] [--threshold-seconds SEC] [--json] [--exit-nonzero-on-stall]`

Options:
- `--transcripts-root DIR` — Root directory to scan; defaults to AESOP_TRANSCRIPTS_ROOT env var or ~/.claude/projects
- `--threshold-seconds SEC` — Max age (seconds) for a "fresh" transcript (default: 600); transcripts older are flagged as stalled
- `--json` — Output as JSON list of {agent_id, age_seconds, stalled, last_mtime} instead of human table
- `--exit-nonzero-on-stall` — Exit 1 if any agent is stalled (for CI/monitor integration); default always exits 0

Exit: 0 always (or 1 if --exit-nonzero-on-stall + stalls found). Output: human table or JSON; reports "no transcripts found" gracefully.

## buildlog.py — Uniform BUILDLOG entry appender

Ensures consistent BUILDLOG.md formatting across orchestrated work: timestamp + message + optional git HEAD ref.

- `buildlog.py "<message>" [--state-dir DIR] [--head] [--repo-path PATH]` — append entry to state/BUILDLOG.md

## ensure_state.py — Scaffold checkpointing directories

Creates STATE.md and BUILDLOG.md templates in state directory if missing.

- `ensure_state.py --state-dir DIR` — scaffold templates

## fleet_ledger.py — Outcome audit trail for dispatched agents

Append-only ledger of agent runs, resource use, and verdicts. Supports harvest (scan temp tasks) and rotate (archive old lines).

- `fleet_ledger.py append <ts> <agent_type> <model> <dur_sec> <tokens_in> <tokens_out> [verdict]`
- `fleet_ledger.py harvest` — scan session tasks and append missing outcomes
- `fleet_ledger.py rotate` — archive old lines when ledger exceeds ~200 lines

## scanner_selftest.py — Regression harness for secret_scan.py

Validates scanner against TP/FP test vectors. Ensures self-scan is clean (no pragma reliance).

- `python scanner_selftest.py [--temp-dir DIR]` — run full test suite, exit 0 only if all pass

## prepublish_scan.py — Pre-publish gate (history + staged)

Runs full git history and staged-changes scans before public release. Both must pass.

- `prepublish_scan.py [--repo PATH]` — scan full history + staged changes, exit 0 only if CLEAR-TO-PUBLISH

## eod_sweep.py — End-of-day repository safety check

Scans listed repos for: dirty working tree, unpushed commits, untracked files. Optional auto-push on safe repos.

- `eod_sweep.py [--repos PATHS] [--readonly-repos PATHS] [--fix-push]` — check repo health, optionally push

## orchestrator_status.py — Atomic orchestrator status updates (wave-8+)

Manages orchestrator heartbeat and activity tracking for SSE status section and wave-9+ multi-orchestrator coordination.

- `python orchestrator_status.py set --activity "dispatching wave-8" --phase audit [--id main --role orchestrator]` — atomically write status
- `python orchestrator_status.py clear` — remove status file

Writes `state/orchestrator-status.json` atomically (temp+replace). Forward-compatible with bare-object → list normalization in serve.py. Exit: 0=success, 1=error.

## ci_merge_wait.py — CI-gated merge helper

Polls gh pr view until all status checks conclude (SUCCESS/FAILURE), then merges ONLY if all checks pass. The `gh pr merge` call is STRUCTURALLY UNREACHABLE unless CI status is SUCCESS — this prevents merge-on-CI-failure edge cases (e.g., wave-7 PR #80).

- `python ci_merge_wait.py <PR-number> [--timeout SECONDS] [--poll SECONDS] [--merge-method merge|squash|rebase]`

Exit codes:
- 0 = PR merged successfully
- 2 = CI checks failed (do NOT merge, prints which check failed)
- 3 = Timeout waiting for CI to conclude
- 4 = PR not mergeable or has merge conflicts

Requires: `gh` CLI available on PATH. Gracefully exits with error if gh is missing.

Implementation note: This is the reusable form of the orchestrator's merge-gating discipline (buildsystem Phase 1). Core invariant: the merge call is STRUCTURALLY UNREACHABLE on any status other than SUCCESS.

## Invariants

- **Dependency-light**: Python tools must work on base Python 3 (no pip installs).
- **CRLF-safe shell**: no line continuations in .sh scripts; Git Bash + Linux compatible.
- **Never print secrets**: mask as pattern name + masked value only.
- **Config-driven paths**: heartbeat/ledger/logs use AESOP_STATE_ROOT env var (default ./state) or CLI args; no hardcoded personal paths.
- **Fragment-assembled secrets in tests**: scanner_selftest.py concatenates dummy secrets at runtime so pattern text never appears contiguously (self-scan invariant).
- **verify_*.py are mandatory CI gates**: verify_dash.py and verify_submit_encoding.py are required pre-push gates; use `--allow-skip` only in truly browserless environments (CI must run both).
- **lock.mjs is the ONLY lock implementation**: never reimplement locking in proposals.mjs or elsewhere; all proposals/state updates must use fail-closed lock.mjs with exponential backoff + stale-lock breaking.
