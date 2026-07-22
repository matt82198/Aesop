# Aesop 0.2.0

**Multi-model orchestration portability shipped.** AgentDriver Phase 1-3 enables orchestration to work with any backend: Claude Code (reference), OpenAI-compatible services (Ollama, OpenRouter, Hugging Face Inference, etc.), and extensible driver architecture for future backends. Verification safety auto-adapts to backend capability — weaker models get stronger safety checking without code changes. Multi-instance identity and lease-by-append coordination enable team-scale deployments on single-machine SQLite.

A source-available, portable orchestration harness for any coding-capable backend; durable git-backed state for team coordination; Haiku-first cost optimization; and transparent verification that adapts to driver capability.

---

## What's New in 0.2.0

**Multi-model driver abstraction:**
- **AgentDriver Phase 1-3 complete.** Three production drivers ship: Claude Code reference adapter (full capability), OpenAI-compatible driver (Ollama, OpenRouter, local Hugging Face), and Phase 3 wave bridge for end-to-end task execution with verified-honest decisions.
- **Backend configuration.** Single `aesop.config.json` file configures model, base_url, and API key for any OpenAI-compatible backend; no code changes required.
- **Honest verification-tier system.** Weaker backends automatically get higher verification (tier 2→tier 4); orchestrator probes backend capability at startup and adapts safety rigor transparently.

**Team-scale coordination:**
- **Multi-instance identity & claims.** Instance ID tagging (hostname:pid:nonce) and lease-by-append state mutations enable safe multi-writer coordination on shared git repo and SQLite without collisions.
- **Cost-ceiling enforcement.** Per-wave spend limit enforced at dispatch time; blocks work if budget exceeded, preventing runaway costs.

**Observability and extensibility:**
- **Transcript-sampled benchmark Phase 1.** Infrastructure extracts coding tasks from real Claude Code transcripts; benchmark grows dynamically beyond hand-written examples.
- **Backend config & role resolution.** `backend_config.py` maps per-deployment model roles (worker/setup/verify) without orchestrator changes.

## What's Fixed Since 0.1.1

- Authorization header cross-origin stripping (PR #221): Blocks Authorization headers on cross-origin redirects to prevent credential leakage; security hardening.
- Secret-scan fail-closed on read errors (PR #226): `secret_scan.py` now fails CLOSED when unable to read files or git data, blocking pushes instead of silently passing.
- Driver subsystem in npm package (PR #220): Multi-model AgentDriver backend abstraction now ships in the npm package.
- CI/publish Node version parity (PR #225): Unified Node.js version across CI and npm publish workflows for reproducible builds.
- Adversarial-review safety fixes (wave-32): Multiple orchestration loop hardening fixes identified and validated by external review.

## Install

```bash
npx @matt82198/aesop my-fleet --name "my-orchestration" --repos "/path/to/coding/repo"
```

Then configure your backend in `aesop.config.json`:

```json
{
  "backend": {
    "driver": "openai-compatible",  // or "claude-code" for Claude Code
    "model": "mistral-small",       // or any OpenAI-compatible model
    "base_url": "http://localhost:1234/v1",  // Ollama local endpoint
    "api_key": "not-needed"
  }
}
```

## Honest Limits

- **Small-N benchmark.** The Haiku≈Opus result in 0.1.0 was measured over 39 judgment tasks — directional for this workload, not universal. Benchmark grows with Phase 1 transcript sampling.
- **Out-of-repo dispatch core.** Orchestration loop runs via Claude Code and your operator workflow; this package ships harness, guardrails, dashboard, and tooling.
- **Early 0.x.** This is stable 0.2.0; APIs, config, and dashboard contracts may evolve across future 0.x versions. Pin exact version if you need stability.
- **Single-box SQLite.** State lives in git + local SQLite; multi-machine deployments use git as serializer with lease-by-append claims. Postgres/hosted control plane unscheduled.
- **Driver extensibility proof.** Three drivers (Claude Code, OpenAI-compatible, bridge) demonstrated end-to-end. Fourth-driver proof (local Ollama) not yet shipped; on roadmap.

See [CHANGELOG.md](./CHANGELOG.md) for the full itemized list.

---

# Aesop 0.1.1

**Patch release for production adopters.** Aesop 0.1.1 addresses first-hour blockers discovered
during 0.1.0 adoption and adds critical production observability: port-conflict detection,
doctor preflight validation, wave-dispatch performance fixes, OUTCOMES-LEDGER for fleet
analytics, gitignore-aware secret scanning, CI workflow linting, and the full aesop fleet CLI.
A source-available, self-building orchestration harness for Claude Code with a plain-file
"brain", git as the durable state layer, cheap Haiku-first subagent fleets, and guardrails
enforced in code.

## What's in 0.1.1

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
- **CI workflow linter.** New `tools/ci_workflow_lint.py` statically validates GitHub Actions YAML (lockfile + suite-coverage checks)
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

See [CHANGELOG.md](./CHANGELOG.md) for full details.
