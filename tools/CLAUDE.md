# tools/ — Build utilities

Local-only Python (stdlib only, no external deps), bash (POSIX, CRLF-safe).

## Universal rules (every domain)
- Feature branch only, never main; every push gated by `python tools/secret_scan.py --staged` exit 0.
- Tests never pollute cwd or global git config; temp dirs only; dummy secrets are runtime-concatenated, never literal.
- In worktrees use ABSOLUTE paths under the worktree for every write.
- Domain docs stay minimal-but-complete; update this file in the same PR as code it describes.

## Core invariants

- **Never print secrets**: mask as pattern name + masked value only; NEVER output raw credentials/tokens.
- **AESOP_STATE_ROOT**: all heartbeat/ledger/logs use `AESOP_STATE_ROOT` env var (default `./state`) or CLI args; no hardcoded personal paths.
- **Fragment-assembled secrets in tests**: `scanner_selftest.py` concatenates dummy secrets at runtime so pattern text never appears contiguously (self-scan invariant).
- **verify_*.py are mandatory CI gates**: `verify_dash.py`, `verify_submit_encoding.py`, `verify_activity_filter.py`, `verify_agent_inspector.py`, `verify_prboard.py`, `verify_failure_drilldown.py`, `verify_wave_telemetry.py` are required pre-push gates; use `--allow-skip` only in truly browserless environments (CI must run all).
- **lock.mjs is the ONLY lock implementation**: never reimplement locking in `proposals.mjs` or elsewhere; all proposals/state updates must use fail-closed `lock.mjs` with exponential backoff + stale-lock breaking.

## Tool index (one-liners)

- `alert_bridge.py` — Slack/Discord webhook bridge for SECURITY-ALERTS
- `bench_runner.py` — Held-out benchmark runner + scorer (Haiku/Sonnet/Opus pluggable)
- `buildlog.py` — Uniform BUILDLOG.md appender
- `ci_merge_wait.py` — CI-gated merge helper (polls gh pr view until SUCCESS; fail-closed: empty rollup=PENDING, --expect-checks requires ALL named checks present AND concluded, --allow-no-checks escape hatch)
- `ci_workflow_lint.py` — CI workflow linter (YAML parsing, npm ci lockfile checks, test coverage)
- `common.py` — Shared utilities (state directory resolution, heartbeat staleness)
- `cost_ceiling.py` — Cost-ceiling checker; trips HALT kill-switch on token limits exceeded
- `defect_escape.py` — Haiku code quality telemetry (fix-forward rate, first-try estimate); CLI: `--repo <path> --since <ISO date> [--json]`
- `ensure_state.py` — Scaffold STATE.md and BUILDLOG.md templates
- `eod_sweep.py` — End-of-day safety check (dirty trees, unpushed commits)
- `fleet.js` — One-shot fleet snapshot (JSON: agents, heartbeats, tracker, orchestrator status; Node STDLIB only)
- `fleet_ledger.py` — Append-only cost ledger with harvest/rotate
- `fleet_prompt_extractor.py` — Extract and deduplicate Agent/Task spawn prompts
- `git_identity_check.py` — Validate repo git user.name/user.email via --expect-name/--expect-email CLI args OR aesop.config.json identity block; verifies .git/config physically (not config cache)
- `halt.py` — Kill-switch: writes/reads/clears `.HALT` sentinel (daemons/dispatch check it)
- `healthcheck.py` — Fleet health aggregator (heartbeat/alert/orchestrator status)
- `heartbeat.py` — Single-instance loop liveness registry
- `inbox_drain.py` — Drain UI inbox submissions
- `launch_tui.py` — Spawn bash TUI script in detached terminal
- `lock.mjs` — Fail-closed atomic lock (exponential backoff + stale-lock detection)
- `metrics_gate.py` — PR gate for hard numeric claims in markdown
- `mutation_test.py` — Test quality harness via mutation testing (apply code mutations, run tests, report survived mutations as test gaps); CLI: `--target <module.py> --test <test_module.py> [--json]`; exit 0 always (advisory)
- `orchestrator_status.py` — Atomic orchestrator status updates
- `portability_check.py` — Shipped-surface gate: scan for hardcoded personal/environment paths (Windows user paths, POSIX home paths, private-machine tokens 'conductor3'/'matt8'); exit 0 clean / 1 with findings; --json output, --root flag for base directory; stdlib only
- `power_selftest.py` — Health check harness for /power bootstrap
- `prepublish_scan.py` — Pre-publish full history + staged-changes scan gate
- `proposals.mjs` — Proposal lifecycle manager (list/accept/reject via lock.mjs)
- `reconcile.py` — Detect/resolve drift (git STATE.md vs. state_store projection; git-authoritative; --resolve appends to SQLite only, never rewrites git-side state)
- `reconstitute.sh` — Clone/fetch repos from config with security validation
- `rotate_logs.py` — Log rotation utility (size/line thresholds)
- `scanner_selftest.py` — Regression harness for secret_scan.py
- `secret_scan.py` — Pre-push secret/credential detection gate (staged/history/paths)
- `self_stats.py` — Git-derived metrics counter + README block generator
- `session_usage_summary.py` — Aggregate token usage across session transcripts
- `stall_check.py` — Automated agent transcript stall detector
- `svg_to_png.mjs` — Rasterize SVG to PNG via @resvg/resvg-js (lazy import error handling)
- `transcript_digest.py` — Digest agent-*.jsonl transcripts into compact redacted per-agent briefs (state/ledger/transcripts-brief.jsonl; deterministic, idempotent, strips paths/emails/tokens)
- `claudemd_lint.py` — Lint the domain CLAUDE.md layer: doc-pointers resolve, cited npm scripts exist, runtime/state artifacts not flagged; --json (guards one-file-per-domain)
- `transcript_replay.py` — Replay post-commit edits from transcripts to recover work
- `transcript_timeline.py` — Extract Write/Edit/Read timeline from transcripts
- `verify_activity_filter.py` — Browser proof for Activity view agent status filter
- `verify_agent_inspector.py` — Browser proof for Agent Inspector drawer (/api/agent?id=)
- `verify_dash.py` — Browser proof for realtime SSE dashboard
- `verify_failure_drilldown.py` — Browser proof for wave failure drill-down feature
- `verify_prboard.py` — Browser proof for Wave PR Board (/api/wave/prs)
- `verify_submit_encoding.py` — Browser proof for /submit UTF-8 inbox bootstrap
- `verify_wave_telemetry.py` — Browser proof for wave telemetry components
- `verify_dispatch_panel.py` — Browser proof for DispatchPanel component (ui/web/dist/ + /api/wave/dispatch; Playwright/Chromium; exit 0=proven, 1=failed, --allow-skip for CI)
- `wave_preflight.py` — Wave-open readiness validator (branch/clean-tree/HALT/heartbeats/tracker; --json mode + --state-root/AESOP_STATE_ROOT split from --root; warn-level checks never flip exit 1)
- `wave_resume.py` — Mid-wave recovery: parse workflow journal.jsonl + worktree to classify items as completed (files written + tests green) vs remaining, enabling resume from last good phase instead of re-run
- `agent-forensics.sh` — Incident forensics; behavior reconstruction (read-only git plumbing)

## secret_scan.py — Pre-push gate

CLI: `secret_scan.py --staged [--repo PATH]` | `--history [--repo PATH]` | `PATH [PATH...]`

Exit: 0=clean, 1=findings, 2=error. Pragma escape (pattern findings only; filenames always fatal):
```
# secretscan: allow-pattern-docs
```

## agent-forensics.sh — Behavior forensics

CLI: `bash tools/agent-forensics.sh <commit>` (print snapshot) | `--diff <commitA> <commitB>` (diff rules/docs)

## Test commands

- **Python**: `npm run test:py` (= `python -m unittest discover -s tests`); a single module: `python -m unittest tests.test_<name>` (tests live in tests/, not tools/; the repo uses unittest, not pytest)
- **Shell**: `bash -n tools/*.sh && shellcheck tools/*.sh` (syntax + linting)
- **Node**: `node --check tools/*.mjs` (syntax validation)
- **Full suite**: `python tools/scanner_selftest.py && python tools/power_selftest.py` (mandatory CI gates)

---

Map of all domains: /CLAUDE.md
