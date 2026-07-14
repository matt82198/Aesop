# tests/ — Test suites and fixtures

**Purpose**: Automated test suites across shell, Node.js, and Python to verify daemon machinery, CLI scaffolder, config drift, and security contracts.

## Shell Test Suites (7 files)

- **backup-fleet.test.sh** — Backup worker test suite; verifies NUL protocol safety, json_escape handling (run: `bash tests/backup-fleet.test.sh`)
- **dash-watchdog-gui.test.sh** — TUI dashboard self-test; verifies printf %s escaping, color codes, log tail rendering (run: `bash tests/dash-watchdog-gui.test.sh`)
- **test-run-watchdog.sh** — Hermetic watchdog daemon test; mocks backup cycle command, verifies lease/release semantics, stale-lock reclaim (run: `bash tests/test-run-watchdog.sh`)
- **test_agent_forensics.sh** — Agent forensics script test; verifies commit replay, diff-behavior mode (run: `bash tests/test_agent_forensics.sh`)
- **test_pre_push_policy.sh** — Hook pre-push-policy.sh self-test; verifies branch policy, audit logging, sha256sum fallback, and lock ownership (run: `bash tests/test_pre_push_policy.sh`)
- **test_reconstitute.sh** — Reconstitute script self-test suite; validates url/target paths, tests legacy space-delimited targets (run: `bash tests/test_reconstitute.sh`)
- **test_reconstitute_fixes.sh** — Security regression suite for target-path validation, symlink/junction traversal guards (run: `bash tests/test_reconstitute_fixes.sh`)

## Node.js Test Suites (10 files)

- **collect-signals.test.mjs** — Monitor signal collection test; verifies stale-lock reclaim, async heartbeat updates (run: `node --test tests/collect-signals.test.mjs`)
- **config-doc-drift.test.mjs** — Ensures config keys documented in code are present in aesop.config.example.json (run: `node --test tests/config-doc-drift.test.mjs`)
- **dash-agents-panel.test.mjs** — Agents panel clickable rows test; verifies row data parsing, XSS safety (run: `node --test tests/dash-agents-panel.test.mjs`)
- **dash-extra.test.mjs** — Dashboard extras test; verifies agents panel, token counting, activity tracking (run: `node --test tests/dash-extra.test.mjs`)
- **domain-map-drift.test.mjs** — Ensures all code directories have domain-map entries in root CLAUDE.md (run: `node --test tests/domain-map-drift.test.mjs`)
- **force-model-policy.test.mjs** — Force-model policy enforcement test; verifies subagent Haiku pinning (run: `node --test tests/force-model-policy.test.mjs`)
- **lock.test.mjs** — Atomic lock acquisition test; verifies fail-closed semantics and PID-liveness checks (run: `node --test tests/lock.test.mjs`)
- **proposals.test.mjs** — Monitor proposals.mjs concurrency test; verifies lock safety, emit/accept/reject atomicity (run: `node --test tests/proposals.test.mjs`)
- **scaffold-hook-install.test.mjs** — CLI hook auto-install test; verifies idempotent hook setup, symlink guards (run: `node --test tests/scaffold-hook-install.test.mjs`)
- **scaffold-onboarding.test.mjs** — CLI onboarding scaffold test; verifies template generation, config init (run: `node --test tests/scaffold-onboarding.test.mjs`)

## Python Test Suites (29 files)

**Serve/UI Module Tests** (11 files)
- **test_agents.py** — agents.py module test; verifies transcript reading and agent-id path-traversal guards (run: `python tests/test_agents.py`)
- **test_api_tracker.py** — Tracker API endpoint tests; verifies CRUD routes, state persistence (run: `python tests/test_api_tracker.py`)
- **test_collectors.py** — collectors.py module test; verifies heartbeat/repo/event/alert/message collection (run: `python tests/test_collectors.py`)
- **test_launch_tui.py** — launch_tui.py unittest; verifies TUI subprocess launch, cleanup (run: `python tests/test_launch_tui.py`)
- **test_pr_link_xss.py** — Tracker XSS prevention test; verifies pr_link whitelist (http/https, blocks javascript:) (run: `python tests/test_pr_link_xss.py`)
- **test_render.py** — render.py template substitution test; verifies CSRF token injection, no format-string expansion (run: `python tests/test_render.py`)
- **test_serve.py** — serve.py unittest; verifies app initialization, SSE setup (run: `python tests/test_serve.py`)
- **test_serve_agent_security.py** — serve.py path-traversal guard test; verifies /agent endpoint input validation (run: `python tests/test_serve_agent_security.py`)
- **test_serve_sse.py** — SSE event stream unittest; verifies bounded queue, connection limits (run: `python tests/test_serve_sse.py`)
- **test_serve_wave8_fixes.py** — Wave-8 UI hardening regression suite; verifies encode fixes, stability patches (run: `python tests/test_serve_wave8_fixes.py`)
- **test_sse_unit.py** — sse.py broadcast and keepalive test; verifies collector-loop timing, client registry (run: `python tests/test_sse_unit.py`)

**Tracker Tests** (3 files)
- **test_tracker_csrf.py** — CSRF token validation test; verifies /submit endpoint origin/header checks (run: `python tests/test_tracker_csrf.py`)
- **test_tracker_isolation.py** — Test-fixture state isolation; verifies no cross-test data leakage via .ui-session-token (run: `python tests/test_tracker_isolation.py`)
- **test_tracker_sse.py** — Tracker SSE integration; verifies create/update/delete emit events correctly (run: `python tests/test_tracker_sse.py`)

**Tools/Scripts Module Tests** (11 files)
- **test_tools_buildlog.py** — tools/buildlog.py append-only log test (run: `python tests/test_tools_buildlog.py`)
- **test_tools_ensure_state.py** — tools/ensure_state.py state-checkpoint self-test (run: `python tests/test_tools_ensure_state.py`)
- **test_tools_eod_sweep.py** — tools/eod_sweep.py daily sweep logic test (run: `python tests/test_tools_eod_sweep.py`)
- **test_tools_fleet_ledger.py** — tools/fleet_ledger.py cost-tracking ledger test (run: `python tests/test_tools_fleet_ledger.py`)
- **test_tools_heartbeat.py** — tools/heartbeat.py liveness-stamp test (run: `python tests/test_tools_heartbeat.py`)
- **test_tools_importable.py** — Import-safety check for all tools/ modules (run: `python tests/test_tools_importable.py`)
- **test_tools_inbox_drain.py** — tools/inbox_drain.py inbox consumption test (run: `python tests/test_tools_inbox_drain.py`)
- **test_tools_orchestrator_status.py** — tools/orchestrator_status.py status snapshot test (run: `python tests/test_tools_orchestrator_status.py`)
- **test_tools_power_selftest.py** — /power skill self-test via tool entrypoint (run: `python tests/test_tools_power_selftest.py`)
- **test_tools_prepublish_scan.py** — tools/prepublish_scan.py pre-push scan simulation (run: `python tests/test_tools_prepublish_scan.py`)
- **test_tools_scanner_selftest.py** — tools/scanner_selftest.py signal-collection validator (run: `python tests/test_tools_scanner_selftest.py`)

**Individual Tool Tests** (4 files)
- **test_ci_merge_wait.py** — tools/ci_merge_wait.py CI gate waiter test (run: `python tests/test_ci_merge_wait.py`)
- **test_rotate_logs.py** — tools/rotate_logs.py unittest; verifies log rotation, keep-count guards (run: `python tests/test_rotate_logs.py`)
- **test_secret_scan.py** — tools/secret_scan.py unittest; verifies key detection, binary skip, .gitignore scoping (run: `python tests/test_secret_scan.py`)
- **test_stall_check.py** — tools/stall_check.py agent-stall detector test (run: `python tests/test_stall_check.py`)

## Test Harness Integration

**npm scripts orchestration** (package.json):
- `npm run test:node` — runs all `*.test.mjs` files via node --test
- `npm run test:sh` — runs all shell test suites in sequence
- `npm run test:py` — runs all Python unittest suites
- `npm run test:all` — runs all three harnesses in order

**CI integration** (.github/workflows/ci.yml):
- "Run Node.js tests" → `npm run test:node`
- "Run shell test suites" → `npm run test:sh`
- "Run Python tests" → `npm run test:py`
- Plus individual hook and tool self-tests

## Invariants & Conventions

- **Hermetic tests**: Shell tests use mktemp for isolation; no persistent side effects
- **Fixtures**: Dummy secrets assembled at test time (never committed), validated via secret_scan.py pragma
- **HEAD-independent**: All tests run regardless of current git branch (CI runs on HEAD=main)
- **Fail-open on missing tools**: Tests skip if optional tooling unavailable (e.g., node missing)
- **Self-test convention**: Hooks and tools (reconstitute.sh, pre-push-policy.sh) include `--test` mode for inline validation
- **Concurrency-safe**: Tests use locking (proposals, collect-signals) to prevent flaky races
