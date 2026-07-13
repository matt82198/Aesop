# tests/ — Test suites and fixtures

**Purpose**: Automated test suites across shell, Node.js, and Python to verify daemon machinery, CLI scaffolder, config drift, and security contracts.

## Shell Test Suites (7 files)

- **test_pre_push_policy.sh** — Hook pre-push-policy.sh self-test; verifies branch policy, audit logging, sha256sum fallback, and lock ownership (run: `bash tests/test_pre_push_policy.sh`)
- **test-run-watchdog.sh** — Hermetic watchdog daemon test; mocks backup cycle command, verifies lease/release semantics, stale-lock reclaim (run: `bash tests/test-run-watchdog.sh`)
- **test_reconstitute.sh** — Reconstitute script self-test suite; validates url/target paths, tests legacy space-delimited targets (run: `bash tests/test_reconstitute.sh`)
- **test_reconstitute_fixes.sh** — Security regression suite for target-path validation, symlink/junction traversal guards (run: `bash tests/test_reconstitute_fixes.sh`)
- **backup-fleet.test.sh** — Backup worker test suite; verifies NUL protocol safety, json_escape handling (run: `bash tests/backup-fleet.test.sh`)
- **dash-watchdog-gui.test.sh** — TUI dashboard self-test; verifies printf %s escaping, color codes, log tail rendering (run: `bash tests/dash-watchdog-gui.test.sh`)
- **test_agent_forensics.sh** — Agent forensics script test; verifies commit replay, diff-behavior mode (run: `bash tests/test_agent_forensics.sh`)

## Node.js Test Suites (9 files)

- **config-doc-drift.test.mjs** — Ensures config keys documented in code are present in aesop.config.example.json (run: `node --test tests/config-doc-drift.test.mjs`)
- **domain-map-drift.test.mjs** — Ensures all code directories have domain-map entries in root CLAUDE.md (run: `node --test tests/domain-map-drift.test.mjs`)
- **proposals.test.mjs** — Monitor proposals.mjs concurrency test; verifies lock safety, emit/accept/reject atomicity (run: `node --test tests/proposals.test.mjs`)
- **collect-signals.test.mjs** — Monitor signal collection test; verifies stale-lock reclaim, async heartbeat updates (run: `node --test tests/collect-signals.test.mjs`)
- **dash-extra.test.mjs** — Dashboard extras test; verifies agents panel, token counting, activity tracking (run: `node --test tests/dash-extra.test.mjs`)
- **dash-agents-panel.test.mjs** — Agents panel clickable rows test; verifies row data parsing, XSS safety (run: `node --test tests/dash-agents-panel.test.mjs`)
- **force-model-policy.test.mjs** — Force-model policy enforcement test; verifies subagent Haiku pinning (run: `node --test tests/force-model-policy.test.mjs`)
- **scaffold-hook-install.test.mjs** — CLI hook auto-install test; verifies idempotent hook setup, symlink guards (run: `node --test tests/scaffold-hook-install.test.mjs`)
- **scaffold-onboarding.test.mjs** — CLI onboarding scaffold test; verifies template generation, config init (run: `node --test tests/scaffold-onboarding.test.mjs`)

## Python Test Suites (6 files)

- **test_secret_scan.py** — secret_scan.py unittest; verifies key detection, binary skip, .gitignore scoping (run: `python tests/test_secret_scan.py`)
- **test_rotate_logs.py** — rotate_logs.py unittest; verifies log rotation, keep-count guards (run: `python tests/test_rotate_logs.py`)
- **test_launch_tui.py** — launch_tui.py unittest; verifies TUI subprocess launch, cleanup (run: `python tests/test_launch_tui.py`)
- **test_serve.py** — serve.py unittest; verifies app initialization, SSE setup (run: `python tests/test_serve.py`)
- **test_serve_sse.py** — SSE event stream unittest; verifies bounded queue, connection limits (run: `python tests/test_serve_sse.py`)
- **test_serve_agent_security.py** — serve.py path-traversal guard test; verifies /agent endpoint input validation (run: `python tests/test_serve_agent_security.py`)

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
