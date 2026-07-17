# Changelog

All notable changes to Aesop are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-17

First stable release. This is the graduation of `0.1.0-rc.1` to a stable version with the
same feature set — no code changes beyond the version/documentation promotion. It publishes to
npm under the `latest` dist-tag. Highlights carried from rc.1: verified Opus audit (0
hallucinated findings), kill-switch wired into the live dispatch path, cost-ceiling guardrail,
a measured held-out benchmark (39 judgment tasks, Haiku on par with Opus at ~1/3 the cost),
the state-reconcile primitive, browser-proven dashboard views (Wave PR Board + Agent
Inspector), a source-available license, and a slim, reproducible ~409 kB npm package. See the
[0.1.0-rc.1] entry below for the full itemized list, and RELEASE-NOTES.md for the honest-limits
account (small-N benchmark, cost-ceiling not yet tied to live token spend, local-first).

## [0.1.0-rc.1] - 2026-07-17

First release candidate. The dispatch-model claims are now backed by measurement, the
kill-switch and cost-ceiling are wired into the live dispatch path and proven, and the npm
package ships slim and reproducible from a clean clone.

### Added
- **Verified Opus audit** (wave.26): Full release audit run with adversarial verification — 0 hallucinated findings, closing out the all-Haiku severity-inflation risk (wave-24: 4 reported P0s, 0 real).
- **Kill-switch wired into dispatch** (wave.27): Fleet-wide halt control is now wired into the dispatch path and proven end-to-end — an operator can stop all agents from a single signal.
- **Cost-ceiling guardrail** (wave.27): Per-wave spend ceiling halts dispatch when the configured budget is exceeded.
- **Held-out benchmark measured** (wave.28): Real offline benchmark scorer (`tools/bench_runner.py`) over a held-out ground-truth set of 39 judgment tasks — Haiku scores on par with Opus at roughly 1/3 the cost, replacing the previously illustrative numbers.
- **State-reconcile primitive** (wave.29): A reconcile primitive compares tracker state against shipped work so already-done items are not re-dispatched at wave open.
- **Reproduce-from-clean-clone CI** (wave.30): CI job builds and validates the package from a fresh clone, proving the tarball is reproducible and self-contained.
- **Wave PR Board** (wave.31): Dashboard view aggregating per-wave PR status for at-a-glance merge-train visibility (browser-proven).
- **Agent Inspector** (wave.31): Drill-down dashboard view exposing individual agent transcripts, cost, and lifecycle (browser-proven).

### Changed
- **npm package slimmed** (wave.30): Package trimmed to ~400 kB by excluding UI source and node_modules; only built artifacts (`ui/web/dist/`), Python, tools, and docs ship.
- **Adversarially-verified audits** (wave.25): Full audits now verify Haiku-reported findings before scheduling fixes.
- **Tracker reconciliation at wave open** (wave.29): Wave startup reconciles the tracker against shipped work so already-done items are not re-dispatched.

### Fixed
- **CI docs-only deadlock** (wave.30): Broke a docs-gate deadlock that could mask HEAD failures in the CI pipeline.
- **Waveguard worktree marker resolution** (#165): Fixed pre-commit hook to resolve marker to current worktree instead of hardcoded primary tree path (wave-24 fleet-block incident).

### Tests
- **Waveguard regression test** (#165): Added Test 7 to prove worktree commits pass while primary tree writes remain blocked by waveguard (wave-24 regression).

## [0.1.0-wave.23] - 2026-07-15

### Added
- **Adopter-focused documentation restructure** (#164): Reorganized docs into adopter journey with architecture diagram (Mermaid) to improve onboarding clarity.
- **Runtime CLI subcommands** (#164): Added `aesop watch`, `aesop dash`, and `aesop status` to CLI for real-time fleet monitoring.
- **Pre-commit waveguard hook** (#164): New write-guard hook prevents stray primary-tree writes during active wave builds; blocks commits outside worktrees.

### Fixed
- **Tracker projection snapshotting** (#164): Fixed O(n²) replay latency in tracker-snapshotting by caching projection state (wave-19 P2).
- **Log rotation race condition** (#164): Made `rotate_logs` atomic to prevent concurrent write race when logs exceed size limits.
- **Dashboard transcript cache** (#164): Optimized `dash-extra.mjs` by caching transcript metadata (path, size, mtime) to reduce redundant reads.
- **Monitor signal deduplication** (#164): Eliminated double-read of SECURITY-ALERTS.log in monitor signal collector to reduce noise.

### Documentation
- **Architecture diagram** (#164): Added Mermaid diagram showing fleet machinery layers (orchestrator → monitor → daemons → state).
- **Adopter journey** (#164): Restructured README and docs to guide new adopters through setup → operations → troubleshooting workflows.

## [0.1.0-wave.22] - 2026-07-15

### Added
- **GitHub docs overhaul** (#163): Complete README rewrite with "Why Aesop?" problem statement and architectural overview for discoverability.
- **Aesop doctor preflight** (#163): New `aesop doctor` subcommand validates configuration, hooks, and state-store health before running waves.
- **Self-building stats automation** (#163): Extended `self_stats.py` to regenerate `stats.json` and detect README stats drift; auto-regenerate in CI.
- **TypeScript type safety** (#163): Added `tsc --noEmit` CI gate to catch UI type errors before merge.

### Changed
- **Stats drift enforcement** (#163): README stats block now auto-reconciled by CI; stale stats block push gate enforces freshness.

### Fixed
- **TypeScript compiler warnings** (#163): Resolved unused variable and type mismatch warnings in UI layer.

### Documentation
- **README landing rewrite** (#163): Replaced generic boilerplate with concrete "Why Aesop exists" section explaining multi-agent durability and cost optimization.
- **CHANGELOG reconciliation** (#163): Added missing wave 16-20 dated entries and reorganized unreleased backlog to reflect actual shipped state.

## [0.1.0-wave.21] - 2026-07-15

### Added
- **CI performance optimization** (#161): Implemented path-based build filters to skip CI on docs-only changes; added Python test parallelization for faster feedback.
- **Fleet ledger instrumentation** (#161): Added phase and wave tagging to cost ledger for better fleet operations analytics and wave closure reporting.

### Changed
- **CI trigger-level filtering** (#161): Removed `paths-ignore` from trigger layer (was silently blocking required checks) and moved filtering to job level for correctness.

### Fixed
- **Python test parallelization** (#161): Parallel test runner now properly isolates test fixtures and state to prevent race conditions.

### Documentation
- **CI filtering best practices** (#161): Documented correct pattern for docs-only CI bypass (job-level, not trigger-level, to preserve required-check semantics).

## [0.1.0-wave.20] - 2026-07-15

### Added
- **Fail-closed push gate** (#160): Secret-scan gate now blocks pushes on timeout, preventing silent failures that allow commits to bypass scanning.
- **UI liveness improvements** (#160): Enhanced SSE cost collection and HealthHeader status display with better timeout handling.
- **CI state classification** (#160): Improved `ci_merge_wait` handling to distinguish real CI status (success/failure) from temporary waits.
- **Daemon portability fixes** (#160): Fixed `backup-fleet` and `run-watchdog` for Linux CI environments (path handling, process detection).
- **Host normalization** (#160): Added consistent URL normalization in UI handler and monitor collectors to reduce false positives.
- **Monitor cursor improvements** (#160): Enhanced monitor signal collection with better state tracking and recovery.

### Documentation
- **Currency updates** (#160): README and docs refresh for wave 20 machinery improvements.

### Fixed
- **UI handler robustness** (#160): Improved error handling in SSE cost collection and API state rendering.
- **Test harness** (#160): Additional coverage for CI merge state handling and daemon portability.

## [0.1.0-wave.19] - 2026-07-15

### Added
- **Secret-scan range push gate** (#165): Enhanced push hook with per-range verification to block partial/corrupted scans and prevent silent gate bypasses.
- **Host-header guard** (#163): HTTP host validation in UI handler to prevent header injection attacks.
- **CI merge classification** (#162): `ci_merge_wait` now distinguishes real CI status (success/failure) vs temporary waits, improving integration reliability.
- **Scaffolder manifest completeness** (#161): All 10 template directories (state_store, skills, mcp, scan) verified in npm package; consistent onboarding experience.
- **UI collector efficiency** (#164): Optimized agent and cost data collection for better freshness and reduced polling overhead; improved SSE contract.
- **Stall-check test rewrite** (#160): Migrated bare test functions to unittest.TestCase for CI compatibility and better failure reporting.
- **npm publish OIDC diagnostics** (#158): Self-diagnosing workflow for OIDC token generation and npm publish reliability.

## [0.1.0-wave.18] - 2026-07-15

### Added
- **Comprehensive audit fixes**: 8-lens security, correctness, a11y, density, shippability, docs, and tools audit with 13 targeted fixes.
- **Watchdog robustness** (#155): Improved `backup-fleet` and `run-watchdog` daemon stability with better error handling and signal detection.
- **Pre-push policy hardening** (#155): Enhanced branch protection and secret-scan enforcement in hook execution.
- **Config management** (#155): Improved aesop.config.json parsing and CLI handling for reliability.
- **State store hardening** (#155): Fixed concurrency edge cases, improved error recovery, and validated persistence.

### Fixed
- **Security gates** (#155): Fixed secret-scan coverage gaps (node_modules, dynamic content); improved push hook reliability.
- **a11y and UI hardening** (#155): Fixed contrast, keyboard navigation, and state-update timing issues.
- **Test infrastructure** (#155): Added comprehensive test coverage for daemons, state store, SSE reliability, UI hardening, and tools.

## [0.1.0-wave.17] - 2026-07-15

### Added
- **Fleet-ops templates** (#153): Example documents for fleet analysis, recommendations, and proposal tracking to guide operations workflows.
- **Tools suite expansion** (#153): New Python and Node tools for fleet operations:
  - `transcript_replay.py`: Replay agent transcripts with event timing
  - `transcript_timeline.py`: Extract and visualize agent activity timelines
  - `fleet_prompt_extractor.py`: Extract and categorize fleet prompts for analysis
  - `svg_to_png.mjs`: Convert SVG charts to PNG for documentation
  - `session_usage_summary.py`: Aggregate session token usage across fleet
- **CI merge wait improvements** (#153): Enhanced `ci_merge_wait` detection with better status classification.
- **Machinery port** (#153): Completed isolation violation detector, health checks, and signal collection for orchestration monitor.
- **Shippability fixes** (#153): Fixed daemon portability and improved bootstrap process.

### Documentation
- **Fleet-ops guidance** (#153): Added templates and examples for monitoring, analysis, and recommendations workflows.

## [0.1.0-wave.16] - 2026-07-15

### Added
- **Isolation-violation detector** (#152): Monitor now detects and reports when worktrees modify shared state (repository contamination checker).
- **Monitor signal collection** (#152): Enhanced `collect-signals.mjs` with isolation detection and improved signal accuracy.

### Documentation
- **CLAUDE.md minimization** (#151): Streamlined domain-specific documentation; archived cancelled tiered-cognition spike; improved maintainability.
- **Domain map refinement** (#151): Clarified tool, test, and UI layer responsibilities and ownership.

## [0.1.0-beta.5] - 2026-07-15

### Added (Wave-15)
- **State-Sourced State Layer** (#134, #135): Event-sourced SQLite WAL backing store with projections; tracker.json re-rendered as export for git integration; dual-path mutations via StateAPI.
- **Self-Building Stats** (#130): `tools/self_stats.py` computes verified repository metrics (merged PRs, commits, waves, files, coauthors) live from git; README stats block auto-populated via CI drift gate.
- **MCP Fleet Server** (#121): Read-only MCP server exposing fleet status, agents, tracker, costs for external Claude integrations.
- **Alert Webhook Bridge** (#120): Incoming HTTP webhook relay to monitor alerts; configurable signing + filtering.
- **Onboarding Wizard** (#127): Interactive CLI scaffolder with guided config, hook setup, repo discovery.
- **Healthcheck Skill** (#126): Liveness probe skill for orchestrator health; integrated into monitor signal collection.
- **Symlink/Junction Coverage** (#125): Test coverage for path-traversal guards; validates symlink/junction rejection in backup and UI handlers.

### Changed (Wave-15)
- **Agent Detail Rendering** (#128): Transcript lookup fixed for parallel agent teams; handles multi-file agent logs.
- **CI Cascade** (#122, #131, #132, #133): Tools-index alert bridge integration; SSE transcript fixture isolation; favicon verification; node_modules secret-scan gate.

### Fixed (Wave-15)
- **Socket Race** (#129): stderr noise from concurrent SSE keepalive; added locking around socket writes.
- **State Store Concurrency Seams** (#138): Inbox-drain deduplication, render-failure recovery, migration guard.
- **CSRF HTTPS Origins** (#137): Accept https loopback origins in CSRF validation.
- **CI/Daemon Machinery** (#136): Dist-freshness gate enforcement; watchdog script-relative path fix.
- **Dashboard UX Hardening** (#141): Stale-data timestamps, empty states, lane badges, a11y improvements.

### Documentation (Wave-15)
- **RELEASING.md** (#140): Release process documentation; npm publish and CI merge procedures.
- **Currency Sweep** (#140): CHANGELOG #113–#135 documentation; README state_store and stats updates; CLAUDE.md drift correction; beta.5 preparation.
- **Portfolio Case Study** (#139): Matt Culliton personal portfolio documentation; agent-fleet-built showcase.

## [0.1.0-beta.4] - 2026-07-14

### Added (Wave-13)
- UI correctness hardening: a11y improvements, contrast fixes, dead marquee removal, monitor-status class.
- Dashboard UX: accessibility fixes, keyboard navigation improvements.
- npm packaging fixes: dependency alignment, build optimization.
- Docs currency: dead-link sweep, reference updates, HOW-THE-LOOP-WORKS clarifications.
- Test/CI wiring: doc-drift and domain-map test verification.
- Machinery gates: secret-scan enforcement, pre-push hook gating.

### Added (Wave-14)
- **Dashboard Rewrite**: Complete React 18 + Vite + TypeScript redesign with 4 hash-routed views (Overview, Work, Activity, Cost), sticky health header, live SSE updates, light/dark theming with WCAG AA contrast, keyboard navigation, and `aria-live` regions.
- **Frontend Architecture**: Zero runtime dependencies beyond React/React-dom; Vite dev server with API proxy; committed `dist/` serves as authoritative build with content-hashed assets and immutable cache headers.
- **Backend Additions**: `/api/state` consolidated first-paint snapshot (one round trip), `/api/session` for Vite dev server CSRF fallback, `/api/cost` cost/scorecard collector from `OUTCOMES-LEDGER.md` with optional pricing map and per-model/per-day aggregates.
- **Cost Analytics**: Per-model token totals, per-day bar chart (pure SVG), verdict scorecard (success/failure/hung rates), configurable pricing estimates from `aesop.config.json`.
- **Testing Infrastructure**: Vitest + Testing Library component tests, rewritten `tools/verify_dash.py` (Playwright) with data-testid-based assertions, CI drift gate for committed dist, a11y/theme verification in CI.

### Changed (Wave-14)
- **Dashboard Cutover**: `ui/templates/dashboard.html` deleted; `ui/handler.py` serve_html now returns hard 500 if dist missing (no fallback).
- **Render Module**: `render.py` requires `template_path` parameter (no legacy default); raises TypeError if called without it.
- **API Contract**: SSE emits 6 sections (added `cost`); `/api/state` returns consolidated snapshot for optimal first paint.

### Fixed (Wave-14)
- **Wave-12 Stability**: Swallowed failures now loud; `sse.reset_state()` locked for concurrent test isolation; tracker writes in tempdir; symlink/path-injection guards in rotate-logs.
- **Wave-11 Security**: Dangling symlink inbox rejection; real handler exercise over HTTP; staged merge tier + model policy hook.

## [Wave-10] - 2026-07-10

### Added
- **UI API Package** (`ui/api/`): Extracted mutation-gate helpers (`validate_mutation()`, `append_to_inbox()`, tracker CRUD handlers) from monolithic handler.py for direct unit testing.
- **Work-item Tracker**: 4-lane kanban (proposed | ranked | in-progress | done) with full CRUD API and SSE updates, priority chips (P0-P3), expandable item details.
- **Orchestrator Status Panel**: Real-time activity, phase, age display with stale detection (>30m).
- **Dashboard ASCII Banner**: Animated audit-phase indicator (tortoise + magnifying glass).
- **UI Module Refactoring**: Split monolithic `serve.py` → focused modules (`config.py`, `csrf.py`, `render.py`, `handler.py`, `collectors.py`, `agents.py`, `sse.py`).

### Improved
- **Security**: CSRF on /api/tracker create; XSS whitelist for pr_link (http/https only, blocks javascript:); fail-closed lock with PID liveness.
- **Stability**: SSE exception handling; timezone-aware datetime; stale lock timestamp spoofing prevention.

## [Wave-9] - 2026-06-30

### Added
- **UI Module Split**: Monolithic `serve.py` refactored into composable modules for maintainability and direct testing (config, csrf, render, handler, collectors, agents, sse).
- **Real Handler Tests**: Seam tests exercising render, collectors, agents without full HTTP coupling (wave-10 P0 foundation).

## [0.1.0-beta.3] - 2026-07-12

### Added
- Hardened rule documentation (CARDINAL-RULES, DISPATCH-MODEL, GOVERNANCE.md).
- Real orchestration monitor with 10 standing health checks (replaced stub).

### Improved
- Production observability infrastructure.

---

## Initial Release

This is the first public release of Aesop, a clean-room open-source implementation of the fable-fleet orchestration harness. The codebase includes:

- The complete orchestration engine with watchdog and monitor
- Web dashboard for fleet observability
- Legacy TUI interface (bash + jq)
- Configuration framework and examples
- Comprehensive documentation and guides
- MIT License (© 2026 Matt Culliton)

Aesop is production-ready and implements the complete cardinal rules for cost-optimized, durable multi-agent coordination.
