# Aesop 0.1.0-rc.1

**First release candidate.** Aesop is an open-source, self-building orchestration harness for
Claude Code: a plain-file "brain", git as the only durable state layer, cheap Haiku-first
subagent fleets, and guardrails enforced in code. This RC is the first build where the core
claims are backed by measurement rather than illustration.

## What's in this release

- **Verified audit, no hallucinations.** A full release audit was run with adversarial
  verification of every finding — 0 hallucinated issues, closing out the prior risk of
  all-Haiku audits inflating severity.
- **Kill-switch, wired and proven.** Fleet-wide halt is now wired into the live dispatch path
  and exercised end-to-end: one signal stops every agent.
- **Cost-ceiling guardrail.** Dispatch halts when a per-wave spend budget is exceeded.
- **Held-out benchmark, measured.** A real offline scorer (`tools/bench_runner.py`) over a
  held-out set of **39 judgment tasks** shows Haiku scoring on par with Opus at roughly
  **1/3 the cost** — the numbers are receipts, not marketing.
- **State-reconcile primitive.** Wave startup reconciles tracker state against shipped work so
  finished items are never re-dispatched.
- **Reproduce-from-clean-clone CI.** CI builds and validates the package from a fresh clone,
  proving the tarball is self-contained and reproducible.
- **CI docs-only deadlock fixed.** A docs-gate deadlock that could mask HEAD failures is gone.
- **Wave PR Board + Agent Inspector.** Two new browser-proven dashboard views: per-wave merge
  status at a glance, and per-agent transcript/cost/lifecycle drill-down.
- **Slimmer npm package (~400 kB).** Only built artifacts, Python, tools, and docs ship — UI
  source and `node_modules` are excluded.

## Install

```bash
npx @matt82198/aesop@rc my-fleet --name "my-api" --repos "/path/to/repo"
```

## Honest limits

- **Small-N benchmark.** The Haiku≈Opus result is measured over 39 judgment tasks — a real,
  held-out set, but small. Treat it as directional evidence for this workload, not a universal
  law. Your task mix may differ.
- **Out-of-repo dispatch core.** The orchestration loop is driven by Claude Code and your own
  operator workflow; this package ships the harness, guardrails, dashboard, and tooling, not a
  turnkey autonomous agent runtime.
- **Release candidate, not final.** APIs, config, and dashboard contracts may still shift
  before 0.1.0. Pin the exact version if you need stability.
- **Local-first.** State lives in git and local files; there is no hosted control plane. Team
  scale beyond a single machine is on the roadmap, not shipped here.

See [CHANGELOG.md](./CHANGELOG.md) for the full entry.
