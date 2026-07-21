# AgentDriver — multi-model portability for aesop

> Run aesop's wave loop on backends other than Claude Code — Codex, and
> eventually open models — through one narrow interface.

This directory is **Phase 1** of the multi-model portability effort described in
the design spike (`conductor3/plans/spike-multitool-portability.md`). It defines
the abstraction seam and ships a reference adapter plus an honest Codex stub. No
wave-loop code is rewired yet; that is the next step (see roadmap below).

---

## The problem

Aesop's orchestration core — the wave / flat-dispatch cycle — is written against
Claude Code's Workflow harness. It calls `agent()`, `parallel()`, the
Read/Write/Bash tools, and `budget.spent()` directly. Those calls only exist
inside Claude Code, so the wave loop cannot run anywhere else.

The spike's finding: ~80% of aesop (daemons, tools, state_store, MCP, UI) is
already portable. The coupling is concentrated in **how the wave loop talks to
its execution backend**. Extract that into one interface and the loop becomes
backend-agnostic.

## The abstraction

`AgentDriver` (in `agent_driver.py`) is that interface — an abstract base class
with **five** operations, which are everything the wave loop needs from any
backend:

| # | Operation                         | What it gives the wave loop                                  |
|---|-----------------------------------|--------------------------------------------------------------|
| 1 | `probe_capabilities()`            | Honest self-report → drives the whole verification strategy. |
| 2 | `dispatch_worker(request)`        | Spawn one isolated worker (read/write files, run shell, return structured result). |
| 3 | `worker_status(worker_id)`        | Liveness / stall detection for the watchdog.                 |
| 4 | `run_command(cmd, cwd, shell)`    | Orchestrator-side execution: tests, git, verification.       |
| 5 | `resolve_model(role)`             | Abstract role (`worker`/`setup`/`verify`) → concrete model.  |

Plus one optional op: `get_tokens_spent()`.

The wave loop calls **only** these methods. A new backend is a new subclass — no
changes to the orchestration algorithm. That is the entire point of the seam.

### What maps where (Claude Code reference)

In Claude Code the actual dispatch runs inside the harness, not in this Python
process. So the reference adapter (`claude_code_driver.py`) is deliberately thin:

| Operation            | Claude Code mechanism        | Concrete here? |
|----------------------|------------------------------|:--------------:|
| `probe_capabilities` | static known-good facts      | yes            |
| `resolve_model`      | Anthropic model-name map     | yes            |
| `run_command`        | Bash tool (subprocess out of harness) | yes   |
| `dispatch_worker`    | Workflow `agent()`/Task tool | harness-serviced |
| `worker_status`      | harness + heartbeat files    | harness-serviced |

The two harness-serviced ops raise a clear, explained error out of harness
rather than fake a Claude agent from plain Python. When the wave-flat-dispatch
template is refactored onto the driver (Phase 1, below), these become the
documented handoff points to the harness.

---

## Per-backend capability matrix

Encoded honestly in each driver's `probe_capabilities()` — the numbers are the
spike's findings as data, so the orchestrator can plan **before** any CLI wiring
exists:

| Capability             | **claude-code** | **codex** (stub)          | open-model (future)        |
|------------------------|:---------------:|:-------------------------:|:--------------------------:|
| parallel_dispatch      | native          | no — external event loop  | no — external event loop   |
| worker filesystem I/O  | yes (tools)     | no — orchestrator injects | no — orchestrator injects  |
| worker shell           | yes (Bash tool) | no — orchestrator runs    | no — orchestrator runs     |
| structured output      | yes (~perfect)  | yes (function-calling)    | partial — regex recovery   |
| worktree isolation     | git-worktree    | no — temp-dir             | no — temp-dir              |
| native cost tracking   | `budget.spent()`| usage metadata (opaque)   | manual (len/4 estimate)    |
| tool-use accuracy      | ~0.99           | ~0.90–0.95                | ~0.70–0.85                 |
| **verification tier**  | **1**           | **2**                     | **4**                      |

Read the trend down the last row — it is the design's thesis, not an accident.

---

## The key insight — verification is load-bearing

> **Cheaper / weaker workers RAISE the need for the verification layer aesop
> already built. They do not lower the orchestrator's burden — they shift cost
> from inference to orchestration.**

Aesop's original bet was "Haiku suffices as a subagent because its tool-use
accuracy is ~99%, so the orchestrator only spot-checks lightly." A weaker
backend breaks that assumption:

- **Codex (gpt-3.5/4-turbo, ~90–95%)** returns 5–10% malformed JSON. The
  orchestrator must validate every output and budget ≥2 repair rounds → **Tier 2**.
- **Open models (~70–85%)** return 15–30% malformed JSON. Every Build result
  needs validation + strong spot-check (Sonnet-verified), with high triage
  escalation → **Tier 4**.

So the money saved on cheap inference is partly re-spent on orchestrator
verification (the spike models DeepSeek at ~6.7× cheaper than Haiku, not the
headline 10×, once recovery is counted). This is exactly why aesop's existing
adversarial-review / mutation / verification tooling is **load-bearing** for
portability: it is the thing that makes weak-but-cheap backends viable at all.
`recommended_verification_tier` on every `DriverCapabilities` encodes this
inverse relationship — lower accuracy, higher tier — and the test suite asserts
it as an invariant (`TestVerificationThesisEncoded`).

The Haiku baseline is **unchanged**: it stays Tier 1. Portability *extends* the
system; it does not replace the original principle (autonomous fleet work needs
high-confidence subagents **plus** strong orchestration).

---

## Phased roadmap

| Phase | Scope                                      | Status                     |
|-------|--------------------------------------------|----------------------------|
| **1** | Driver interface + Claude Code parity      | **this directory**         |
|       | Reference adapter, honest Codex stub, tests| shipped                    |
|       | Refactor wave-flat-dispatch onto the driver| next (harness handoff pts) |
| **2** | Codex reference adapter                     | stub only today            |
|       | Wire `codex` CLI / OpenAI API, JSON-schema validation, external Node/Python harness (parallel, file I/O, run_command), message-shape adapter | TODO in `codex_driver.py` |
| **3** | Open-model runner library                   | future                     |
|       | Ollama/OpenRouter/Together adapters, per-model prompt tuning, error-recovery protocol, Tier-4 enforcement, `bench/` accuracy benchmark | future |

**Deployment posture** (from the spike): Claude Code is production. Codex and
open models stay **experimental / opt-in** until their tiers are proven —
recommend Haiku for production fleets.

---

## Usage

```python
import sys
sys.path.insert(0, "driver")           # bare imports within the domain

from claude_code_driver import ClaudeCodeDriver
from codex_driver import CodexDriver

for driver in (ClaudeCodeDriver(), CodexDriver()):
    caps = driver.probe_capabilities()
    print(caps.summary())              # ASCII one-liner for logs/dashboards
    print("worker model ->", driver.resolve_model("worker"))
```

Run the contract tests:

```
python -m unittest tests.test_agent_driver
```

## Design constraints

- **stdlib-only** at this layer (`abc`, `dataclasses`, `typing`, `subprocess`).
  Provider SDKs (`openai`, `ollama`, …) belong to the concrete adapters, added
  in Phases 2–3 — the interface stays importable everywhere.
- **ASCII-only**, **Windows + Linux safe**.
- **Honest probes.** `DriverCapabilities` defaults are conservative (no native
  abilities, accuracy 0.0, tier 4). A backend must *opt in* to each capability.
