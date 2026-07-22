<p align="center">
  <img src="https://raw.githubusercontent.com/matt82198/aesop/main/assets/logo.png" alt="Aesop" width="420">
</p>

<p align="center">
  <em>Autonomous Developer for Any Repository</em>
</p>

<p align="center">
  <a href="https://github.com/matt82198/aesop/actions/workflows/ci.yml"><img src="https://github.com/matt82198/aesop/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://www.npmjs.com/package/@matt82198/aesop"><img src="https://img.shields.io/npm/v/@matt82198/aesop" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-orange.svg" alt="License: PolyForm Strict 1.0.0 (source-available)"></a>
</p>

## What It Does

**Aesop** is a source-available orchestration harness that runs multi-agent workflows on any repository. It ranks backlog, dispatches parallel Haiku workers (scoped to disjoint file ownership), verifies merges with adversarial safety, and feeds learnings into the next wave. Durable state (SQLite + git-rendered checkpoints) survives machine wipes and enables team coordination. This repo's own 223 PRs across 880 commits were delivered by Aesop's own `/buildsystem` wave loop—a supervised loop under a human operator who sets goals and owns outward gates (npm publish, releases, history rewrites). The stack is portable: swappable backends (Claude Code reference, OpenAI-compatible Ollama/OpenRouter, Codex bridge), with auto-tuned verification safety calibrated per backend.

## Feature Demo

**One-turn wave** — Run a complete build cycle (tests, build, docs, review, merge, audit) end-to-end:
```bash
python driver/wave_loop.py --manifest wave.json --one-turn
```
Ranks backlog, dispatches parallel Haiku workers, runs tests, audits the output. Produces a JSON report of all agent runs and their verdicts.

**Multi-model drivers** — Choose your backend (Claude Code, Ollama, OpenRouter) with one config line:
```json
{ "backend": "openai-compatible", "model": "mistral-small", "base_url": "http://localhost:1234/v1" }
```
Verification tiers auto-adapt to backend capability—weaker models get stronger safety checking without code changes.

**Wave templates** — Bootstrap a new fleet with a preset architecture:
```bash
python tools/wave_templates.py saas --project-name my-api --base-dir /workspace
```
Generates a manifest for typical 3-tier (API, frontend, ops) or data pipelines.

**Live dashboard** — Real-time view of fleet health, security alerts, work-item kanban, cost analytics:
```bash
npx @matt82198/aesop dash
```
Opens http://localhost:8770. Four views: Overview (agents, events), Work (kanban), Activity (reasoning tail), Cost (spend/tokens).

**Health score** — Readiness assessment: env, git, Python, Node, ports, config, hooks:
```bash
python tools/health_score.py
```
Outputs a scorecard of system readiness; --json for parsing.

**Self-healing daemon** — Runs every 150s: backs up work, scans secrets, detects drift:
```bash
npx @matt82198/aesop watch
```
Pre-push hook blocks leaks. Heartbeat signals liveness; monitor auto-detects stalls and restarts the fleet.

**Hardened gate stack** — Fail-closed secret-scan, adversarial review (default-on):
```bash
python tools/secret_scan.py --staged   # Blocks push if leak detected
```
Exits with failure on file-read errors (not silently passing). CI validates every merge.

## Proof Numbers

Aesop builds itself. These numbers are live from git, verified by anyone who clones.

## Get Started

```bash
npx @matt82198/aesop my-fleet --name "api" --repos "/path/to/repo"
```
→ See [docs/INSTALL.md](./docs/INSTALL.md) for setup and first `/power` → `/buildsystem` cycle.
→ See [docs/DEMO.md](./docs/DEMO.md) for a complete walkthrough of one wave.


<!-- STATS:START -->

## Aesop builds itself

Aesop is built entirely by its own `/buildsystem` wave cycle—running parallel Haiku fleets across ranked backlog items, verifying merges, auditing orchestration health. These stats are the receipts: all numbers computed LIVE from git, verified by anyone who clones.

| Metric | Value |
| --- | --- |
| Merged PRs | 223 <!-- metrics-verified: self_stats.py (git log) --> |
| Total Commits | 880 <!-- metrics-verified: self_stats.py (git log) --> |
| Project Age | 10 days <!-- metrics-verified: self_stats.py (git log) --> |
| Waves | 30 <!-- metrics-verified: self_stats.py (git log) --> |
| Insertions + Deletions | 161,064 <!-- metrics-verified: self_stats.py (git log) --> |
| Files Tracked | 500 <!-- metrics-verified: self_stats.py (git log) --> |
| Distinct Co-authors | 9 <!-- metrics-verified: self_stats.py (git log) --> |

<!-- STATS:END -->








## Why Haiku-First Works

The benchmark proves it: across 39 judgment tasks (code review, severity calibration, root-cause analysis, refactor equivalence, security spots), Haiku scored **39/39** vs Opus **38/39** at ~1/3 the per-token cost. See [`bench/results/2026-07-17-judgment-v3-haiku-sonnet-opus.md`](./bench/results/2026-07-17-judgment-v3-haiku-sonnet-opus.md). Honest caveat: curated set (N=39), not real-transcript sampled; the benchmark found no task where Opus beats Haiku, proving sufficiency for this workload, not parity at the reasoning frontier.

## Learn More

- **[docs/INSTALL.md](./docs/INSTALL.md)** — Setup and first wave  
- **[docs/HOW-THE-LOOP-WORKS.md](./docs/HOW-THE-LOOP-WORKS.md)** — Concrete walkthrough of a wave cycle  
- **[docs/DISPATCH-MODEL.md](./docs/DISPATCH-MODEL.md)** — Cost analysis and scaling  
- **[docs/CARDINAL-RULES.md](./docs/CARDINAL-RULES.md)** — 10 foundational principles  
- **[docs/autonomous-swe.md](./docs/autonomous-swe.md)** — What "autonomous" means (and doesn't), evidence for all claims, honest limits  
- **[RELEASE-NOTES.md](./RELEASE-NOTES.md)** — Version 0.2.0: multi-model drivers, team coordination, transcript sampling

## Contributing

Aesop is **source-available** under the PolyForm Strict License 1.0.0, which does not permit modification or redistribution — so outside code patches can't be accepted as merged contributions. That said, **feedback is genuinely welcome**:

- **Issues and bug reports** — tell us what's broken or confusing.
- **Discussion and ideas** — feature requests, design critiques, use-case questions.

The repo develops itself via its own `/buildsystem` loop; code changes are made by the maintainer at their discretion, or by prior arrangement. See [CONTRIBUTING.md](./CONTRIBUTING.md) for details.

## License

**Source-available** under the [PolyForm Strict License 1.0.0](./LICENSE). You may read, run, and use the software for any permitted purpose, but **modification and redistribution are not permitted**. See [`LICENSE`](./LICENSE) for the full terms and the definition of permitted (noncommercial and personal) purposes.

Copyright 2026 Matt Culliton.

## References

- [Anthropic Claude API docs](https://docs.anthropic.com)
- [Claude Code CLI](https://github.com/anthropics/claude-code)
- [Git docs](https://git-scm.com/doc)

---

**Aesop**: Autonomous developer for any repository, built by Aesop itself. May your orchestrator be wise and your subagents swift.
