# tests/ — Test suites and fixtures

**Purpose**: Automated test suites across shell, Node.js, and Python to verify daemon machinery, CLI scaffolder, config drift, and security contracts.

## Test Suites

Shell (7): backup-fleet, dash-watchdog-gui, test-run-watchdog, test_agent_forensics, test_pre_push_policy, test_reconstitute, test_reconstitute_fixes.
Node.js (14): cli-config, collect-signals, config-doc-drift, dash-agents-panel, dash-extra, domain-map-drift, force-model-policy, lock, mcp-fleet, packaging-portability, proposals, scaffold-hook-install, scaffold-onboarding, wizard.
Python (44): Serve/UI (test_agent_detail_roundtrip, test_agents, test_api_state, test_api_tracker, test_collectors, test_launch_tui, test_render, test_serve, test_serve_agent_security, test_serve_sse, test_serve_wave8_fixes, test_sse_cost_reliability, test_sse_unit, test_ui_cost, test_ui_hardening, test_wave13_ui_correctness), Tracker (test_tracker_csrf, test_tracker_isolation, test_tracker_sse), Security (test_csrf_https_origins, test_secret_scan, test_secret_scan_gaps, test_symlink_guard), State (test_state_store, test_state_store_hardening), Tools/Scripts/Individual (test_alert_bridge, test_ci_merge_wait, test_healthcheck, test_metrics_gate, test_rotate_logs, test_self_stats, test_stall_check, test_tools_buildlog, test_tools_common, test_tools_ensure_state, test_tools_eod_sweep, test_tools_fleet_ledger, test_tools_heartbeat, test_tools_importable, test_tools_inbox_drain, test_tools_orchestrator_status, test_tools_power_selftest, test_tools_prepublish_scan, test_tools_scanner_selftest).

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
