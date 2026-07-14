# Changelog

All notable changes to Aesop are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-beta.4] - Unreleased

### Added (Wave-13)
- UI correctness hardening: a11y improvements, contrast fixes, dead marquee removal, monitor-status class.
- Dashboard UX: accessibility fixes, keyboard navigation improvements.
- npm packaging fixes: dependency alignment, build optimization.
- Docs currency: dead-link sweep, reference updates, HOW-THE-LOOP-WORKS clarifications.
- Test/CI wiring: doc-drift and domain-map test verification.
- Machinery gates: secret-scan enforcement, pre-push hook gating.

## [Unreleased]

### Added
- **Stall Detection** (wave-12): `tools/stall_check.py` silent-hang detection for the agent watchdog.
- **CI-Gated Merge Helper** (wave-12): `tools/ci_merge_wait.py` awaits CI success before merge.

### Fixed
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
