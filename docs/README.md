# Aesop Documentation Index

Aesop is a fable-fleet orchestration harness for Claude Code. It runs fast, cheap delivery waves: parallel Haiku agents, lower cost via Haiku-first dispatch and faster wall-clock via parallel agents.

**New to Aesop?** Start here: [HOW-THE-LOOP-WORKS.md](HOW-THE-LOOP-WORKS.md) — a walkthrough of one wave cycle and why it's productive.

For deeper governance + operational rules, see the reference docs below.

---

## Quick Start

- [HOW-THE-LOOP-WORKS.md](HOW-THE-LOOP-WORKS.md) — Concrete walkthrough of one `/buildsystem` wave (rank → fan out → verify → merge → close)

## Core Governance & Rules (Reference)

- [CARDINAL-RULES.md](CARDINAL-RULES.md) — Foundational operational principles (dispatch model, cost, subagent discipline, retry caps)
- [RELIABILITY.md](RELIABILITY.md) — Reliability core: never wait, inputs always produce outputs, pride bar for completion
- [CHECKPOINTING.md](CHECKPOINTING.md) — Durable STATE.md/BUILDLOG.md lifecycle, recovery on resume, log rotation patterns
- [SCRIPTS-POLICY.md](SCRIPTS-POLICY.md) — Local-only execution, shared script library, task-local vs. reusable heuristics
- [DISPATCH-MODEL.md](DISPATCH-MODEL.md) — Fable/Haiku orchestration patterns and cost calculations
- [GOVERNANCE.md](GOVERNANCE.md) — Single-instance loops, single-writer files, heartbeat protocol, security gates

## The Five Pillars

### 1. Onboarding Templates
- [MEMORY-TEMPLATE.md](MEMORY-TEMPLATE.md) — Canonical index format and structure for team memory & facts

### 2. Policy Hooks
- [HOOK-INSTALL.md](HOOK-INSTALL.md) — Install and customize `hooks/pre-push-policy.sh` (branch/secret enforcement at push time)

### 3. Behavioral PRs
- [BEHAVIORAL-PR-REVIEW.md](BEHAVIORAL-PR-REVIEW.md) — Checklist for reviewing PRs that modify rules, policies, or orchestration behavior

### 4. Forensics (Git-Bisectable Agent Debugging)
- [FORENSICS.md](FORENSICS.md) — Reconstruct agent failures using `tools/agent-forensics.sh`; make agent behavior git-debuggable

### 5. Restore (Cross-Machine Reconstitution)
- [RESTORE.md](RESTORE.md) — Reconstitute Aesop & fleet on a new machine from git + watchdog backups after a wipe

## Operational Guides

- [PUBLISHING.md](PUBLISHING.md) — Release Aesop to npm using GitHub Actions with OIDC trusted publishing
- [av-resilience.md](av-resilience.md) — Antivirus & behavioral-engine resilience patterns for reliable agent execution
