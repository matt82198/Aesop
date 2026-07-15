# Changelog

All notable changes to Aesop are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (Wave-16/17 in-flight)
- CLAUDE.md minimization and domain map refinements (PR #151).
- Isolation detector and machinery/scripts port (PR #150).
- MCP server and scan/ directory shipping in npm package.
- README stats refresh and agent-catalog reference.

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
