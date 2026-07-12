# Changelog

All notable changes to Aesop are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-beta.3] - 2026-07-12

### Added
- Hardened rule documentation (CARDINAL-RULES, DISPATCH-MODEL, new GOVERNANCE.md)
- Real orchestration monitor signal collector with 10 standing health checks (replaces stub monitor)

### Improved
- Enhanced monitoring infrastructure for production observability

## [Unreleased]

### Added

#### Dashboard Integrations
- **`dash/dash-extra.mjs`**: Fleet agent detector scans transcripts for running agents, enables web dashboard agent panel. Detects agents in last 12 minutes, color-codes by alert severity, outputs JSON for REST endpoint or TUI text for terminal.
- **`tools/secret_scan.py`**: Pre-push secret/credential detection gate with comprehensive pattern library (PEM keys, AWS/GitHub/Slack/OpenAI tokens, .env patterns, credential filenames). Supports `--staged`, `--history`, and direct path scanning. Pragma escape hatch for allow-pattern-docs. Exit 1 blocks push on findings.

### Improved
- Web dashboard now properly detects and displays running subagents via `dash-extra.mjs`
- Secret-scan gate now active in watchdog cycle; blocks any push with unscanned credentials

## [1.0.0] - 2026-07-11

### Added

#### Web Dashboard (Primary Interface)
- Modern, responsive HTML dashboard replacing terminal UI
- Real-time fleet monitoring with 3-second refresh cycles
- Heartbeat liveness detection for daemon health
- Security alerts panel with unreviewed event tracking
- Inbox integration for direct orchestrator communication
- Agent tracking with status and runtime hints
- **Agent detail expansion**: Click agent rows to view full dispatch prompts, dispatcher, model, and message counts
- **GET /agent endpoint**: RESTful query for agent metadata and full dispatch details
- Repository synchronization status display
- Recent events log with the latest 8 backup operations
- Transcript integration showing main-thread conversation history
- Configurable port (default 8770) via environment variables
- Zero external dependencies (Python 3.10+ stdlib only)

#### Orchestration Engine
- Fable-fleet dispatch model (orchestrator + Haiku subagents)
- Cost-optimized multi-agent coordination
- Durable git-committed state (STATE.md, BUILDLOG.md)
- Autonomous watchdog daemon with 150-second cycle
- Secret-scan gate on every push (configurable via `tools/secret_scan.py`)
- Heartbeat-based liveness detection (300s watchdog, 3600s monitor)
- Append-only BUILDLOG for recovery and audit trails

#### Refinement Monitor
- Standing orchestration health monitor (Haiku loop)
- Dual-action tier system (AUTO for immediate, PROPOSE for staged)
- Signal collection and drift detection
- Automated health checks and rule-friction analysis
- Extensible signal collectors via `monitor/collect-signals.mjs`

#### State Machine & Durability
- Filesystem-first checkpoint design
- Git-committed STATE.md and BUILDLOG.md
- Recovery from machine wipes and interruptions
- Single-writer control file discipline
- Idempotent restart semantics

#### Security & Observability
- Configurable secret-scan gate (blocks pushes on policy violation)
- Observable machinery (every agent run logged, every cost tracked)
- Security alert collection and triaging
- AV-resilience patterns for Windows environments
- Support for dot-directory backup discovery

#### Documentation
- Cardinal Rules guide (10 principles for cost-optimized orchestration)
- Dispatch Model documentation (cost analysis, parallel patterns)
- State Machine guide (durability and recovery)
- AV-Resilience guide (Windows security software compatibility)
- Quickstart walkthrough and setup guide
- Architecture deep-dives for extend points

#### TUI Dashboard (Legacy Alternative)
- Terminal-based dashboard via `dash/watchdog-gui.sh`
- Real-time fleet status display
- Agent activity tracking
- Alert visualization
- Optional jq dependency for JSON parsing

### Configuration

#### aesop.config.json Schema
```json
{
  "aesop_root": "/path/to/aesop",
  "state_root": "/path/to/state",
  "scan_root": "/path/to/scan",
  "transcripts_root": "/path/to/transcripts",
  "repos": [
    {
      "path": "/path/to/repo",
      "name": "repo-name"
    }
  ],
  "watchdog_cycle_secs": 150,
  "monitor_cycle_secs": 300,
  "heartbeat_stale_threshold_secs": 300
}
```

### Development & Extension

- Plugin architecture for custom signal collectors
- Hook points for watchdog customization
- Dashboard extensibility via JavaScript injection
- Secret-scan policy implementation examples
- Support for Haiku-per-domain decomposition

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
