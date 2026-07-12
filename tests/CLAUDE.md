# tests/ — Test suites and fixtures

**Purpose**: Automated test suites across shell, Node.js, and Python to verify daemon machinery, CLI scaffolder, config drift, and security contracts.

## Files & Harnesses

- **test_pre_push_policy.sh** — Hook self-test; verifies branch policy and audit logging (run: `bash tests/test_pre_push_policy.sh`)
- **test-run-watchdog.sh** — Hermetic watchdog daemon test; mocks cycle command (run: `bash tests/test-run-watchdog.sh`)
- **backup-fleet.test.sh** — Backup worker test suite (run: `bash tests/backup-fleet.test.sh`)
- **test_reconstitute.sh** — Reconstitute script self-test suite (run: `bash tests/test_reconstitute.sh`)
- **test_reconstitute_fixes.sh** — Security & architecture fixes regression suite for target validation, URL validation, and legacy space-delimited targets (run: `bash tests/test_reconstitute_fixes.sh`)
- **config-doc-drift.test.mjs** — Node.js test ensuring config keys documented in code are present in aesop.config.example.json (run: `node --test tests/config-doc-drift.test.mjs`)
- **domain-map-drift.test.mjs** — Node.js test ensuring all code directories have domain-map entries in root CLAUDE.md (run: `node --test tests/domain-map-drift.test.mjs`)

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
