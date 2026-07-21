# driver/ — AgentDriver backend-portability seam

**What**: The one-file domain contract that lets aesop's wave loop run on
backends other than Claude Code (Codex, open models). The wave loop dispatches
through the `AgentDriver` interface and nothing else; each backend is a subclass.

Grounded in `conductor3/plans/spike-multitool-portability.md` (the design spike).
This is **Phase 1**: the interface + reference adapter + honest Codex stub.

## Files

- **agent_driver.py** — the `AgentDriver` ABC + capability/request/result
  dataclasses. The contract. stdlib-only, no provider SDKs.
- **claude_code_driver.py** — reference adapter (Claude Code parity). Thin +
  documented: two ops are concrete Python, three are serviced by the harness.
- **codex_driver.py** — honest STUB for the `codex`/OpenAI backend. Capability
  probe is filled in truthfully; un-wired ops raise `NotImplementedError`.
- **README.md** — the abstraction, the phased roadmap, the verification thesis.
- **../tests/test_agent_driver.py** — the contract's test suite.

## The five operations (what the wave loop needs from ANY backend)

1. `probe_capabilities() -> DriverCapabilities` — honest self-report (parallel?
   filesystem? shell? structured output? worktree? cost tracking? accuracy? →
   recommended verification tier). Read once; everything keys off it.
2. `dispatch_worker(request) -> WorkerResult` — spawn ONE isolated worker over a
   prompt + owned_files + workdir; the worker may read/write files, run a shell
   command, and return a **structured** result (extent reported by the probe).
3. `worker_status(worker_id) -> WorkerStatus` — liveness / stall detection for
   the watchdog.
4. `run_command(command, cwd, shell) -> CommandResult` — ORCHESTRATOR-side
   command execution (tests, git, verification). Distinct from a worker shell.
5. `resolve_model(role) -> str` — map an abstract role (`worker`/`setup`/
   `verify`) to a concrete backend model id.

Optional (non-abstract): `get_tokens_spent()`.

## Invariants

- The wave loop calls **only** `AgentDriver` methods — never `agent()`,
  `parallel()`, Read/Write/Bash tools, or `budget.spent()` directly. That is
  the seam.
- `probe_capabilities()` must be **honest**. Defaults are conservative (no
  native abilities, accuracy 0.0, tier 4) — optimism is opt-in, never default.
- **Weaker workers → higher verification tier.** Lower `tool_use_accuracy`
  raises `recommended_verification_tier`. Cheaper/weaker backends RAISE the
  orchestrator's burden; they do not lower it.
- Unknown roles in `resolve_model()` fall back to the worker model — a mis-typed
  role can never silently escalate cost.
- stdlib-only (`abc`, `dataclasses`, `typing`, `subprocess`), ASCII-only,
  Windows + Linux safe. Concrete adapters own any provider SDK, not this layer.

## Per-backend capability matrix (as encoded)

| Capability            | claude-code | codex (stub) |
|-----------------------|:-----------:|:------------:|
| parallel_dispatch     | yes         | no (ext loop)|
| worker filesystem     | yes         | no           |
| worker shell          | yes         | no           |
| structured_output     | yes         | yes          |
| worktree_isolation    | yes         | no (temp-dir)|
| native_cost_tracking  | yes         | yes (opaque) |
| tool_use_accuracy     | ~0.99       | ~0.92        |
| verification_tier     | 1           | 2            |

## Status

Phase 1 seam only. `codex_driver` dispatch/`run_command` raise
`NotImplementedError` with TODOs. Claude Code dispatch/status are harness-
serviced (documented handoff points for the Phase-1 wave-loop refactor).
