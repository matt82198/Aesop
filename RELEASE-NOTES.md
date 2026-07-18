# Aesop 0.1.1

**Patch release for production adopters.** Aesop 0.1.1 addresses first-hour blockers discovered
during 0.1.0 adoption and adds critical production observability: port-conflict detection,
doctor preflight validation, wave-dispatch performance fixes, OUTCOMES-LEDGER for fleet
analytics, gitignore-aware secret scanning, CI workflow linting, and the full aesop fleet CLI.
A source-available, self-building orchestration harness for Claude Code with a plain-file
"brain", git as the durable state layer, cheap Haiku-first subagent fleets, and guardrails
enforced in code.

## What's in this release

**First-hour fixes for early adopters:**
- **Port-conflict detection.** CLI and doctor preflight now detect port-binding conflicts before
  dashboard startup; helpful error messages point adopters to resolution steps.
- **Doctor preflight validation.** New `aesop doctor` subcommand validates configuration, hooks,
  state store health, and port availability before wave startup — a safety harness for first runs.
- **Git init + --no-git option.** Scaffolder now supports `--no-git` flag for adopters integrating
  into existing repos without re-initializing version control; `git init` in new repos works out of the box.

**Production orchestration improvements:**
- **Wave-dispatch latency fixes.** Template self-check parallelization, postBuild hooks, and
  multi-testCmd batching provide faster feedback cycles on active waves.
- **OUTCOMES-LEDGER producer.** Append-only ledger tracks per-wave execution outcomes (dispatch
  time, duration, merge timing) for fleet analytics and historical trend analysis.
- **CI workflow linter.** New `tools/lint_workflow.py` validates GitHub Actions YAML contract
  (phase structure, job naming, cost-log artifacts); CI gate catches schema drift at merge time.
- **CI merge-wait fail-closed.** `ci_merge_wait` timeout now blocks dispatch instead of silently
  passing — prevents merging while CI is still running.

**Observability and production readiness:**
- **Gitignore-respecting secret scan.** `secret_scan.py` now respects `.gitignore` patterns;
  skips ephemeral runtime files to reduce false positives and scan time on large repos.
- **Failure drilldown + cost analytics.** Enhanced dashboard drill-down shows failure reasons,
  cost metrics per model, per-day spend bar chart (pure SVG), and verdict scorecard.
- **Aesop fleet CLI.** New `aesop fleet` subcommand suite for production fleet inspection: list
  agents, query costs, export telemetry for monitoring and troubleshooting.
- **Transcript digest + domain-map linting.** New tools for post-wave transcript summarization
  and CLAUDE.md scope enforcement (3-line max per section).

**Documentation and portability:**
- **ANY-REPO scaffolding.** Aesop now deploys into any existing Node/Python repo; includes
  setup guides, CONTRIBUTING.md, and GitHub community files (SECURITY.md, issue templates).
- **MCP cost tools.** Read-only MCP server exposes cost-ledger and cost-ceiling for external
  Claude integrations in monitoring dashboards.

## Install

```bash
npx @matt82198/aesop my-fleet --name "my-api" --repos "/path/to/repo"
```

## What's fixed since 0.1.0

- First-hour blockers: git-init, port conflicts, doctor preflight, scaffolder git-option
- Wave-dispatch latency: template self-check parallelization, postBuild, multi-testCmd
- CI merge-wait fail-closed (prevents silent merge during CI runs)
- Gitignore-respecting secret scan (fewer false positives on large repos)
- Full aesop fleet CLI for production operations
- OUTCOMES-LEDGER instrumentation for fleet analytics

## Honest limits

- **Small-N benchmark.** The Haiku≈Opus result in 0.1.0 is measured over 39 judgment tasks —
  directional evidence for this workload, not a universal law. Remains the reference point.
- **Out-of-repo dispatch core.** The orchestration loop is driven by Claude Code and your own
  operator workflow; this package ships the harness, guardrails, dashboard, and tooling, not a
  turnkey autonomous agent runtime.
- **Early 0.x, not 1.0.** This is an early stable release; APIs, config, and dashboard
  contracts may still evolve across future 0.x versions. Pin the exact version if you need
  stability.
- **Local-first.** State lives in git and local files; there is no hosted control plane. Team
  scale beyond a single machine is on the roadmap, not shipped here.

See [CHANGELOG.md](./CHANGELOG.md) for the full itemized list.
