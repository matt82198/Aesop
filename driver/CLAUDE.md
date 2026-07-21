# driver/ — AgentDriver backend-portability seam

**What**: The one-file domain contract that lets aesop's wave loop run on
backends other than Claude Code (Codex, open models). The wave loop dispatches
through the `AgentDriver` interface and nothing else; each backend is a subclass.

Grounded in a multi-model portability design spike.
**Phase 1 (interface + reference adapter, shipped)** + **Phase 2 (Codex OpenAI Chat Completions, shipped)** + **Phase 3 (wave-manifest bridge, shipped)**.

## Files

- **agent_driver.py** — the `AgentDriver` ABC + capability/request/result
  dataclasses. The contract. stdlib-only, no provider SDKs.
- **claude_code_driver.py** — reference adapter (Claude Code parity). Thin +
  documented: two ops are concrete Python, three are serviced by the harness.
- **codex_driver.py** — Phase 2 IMPLEMENTATION: OpenAI Chat Completions HTTP
  backend. Fully wired: dispatch_worker (file injection, JSON validation with
  retry, full-file replacement), run_command (subprocess), worker_status
  (in-memory registry), get_tokens_spent (aggregate usage). Transport injectable
  for offline testing.
- **openai_transport.py** — stdlib urllib transport for OpenAI Chat Completions
  endpoint. Injectable seam so tests feed canned responses (FakeTransport) with
  no API key or network.
- **verification_policy.py** — pure function mapping recommended_verification_tier
  -> orchestrator tuning (validate_all_json, spot_check_frac, repair_cap,
  require_adversarial_review).
- **wave_bridge.py** — Phase 3 IMPLEMENTATION: bridges AgentDriver backends to
  wave-flat-dispatch manifest items. Two core functions: build_manifest_item()
  produces manifest item with verificationTier + model from driver probe;
  dispatch_item() routes execution by capabilities (harness for tier-1, orchestrator
  for tier-2+) and decides green ONLY from test exit code (never model's say-so).
- **README.md** — the abstraction, the phased roadmap, the verification thesis.
- **../tests/test_agent_driver.py** — the contract's test suite.
- **../tests/test_codex_driver_e2e.py** — Phase 2 end-to-end offline tests
  (FakeTransport, red-to-green verification, retry logic, ownership enforcement)
  + gated live test (AESOP_CODEX_LIVE env var).
- **../tests/test_wave_bridge.py** — Phase 3 end-to-end offline tests proving
  non-Claude backend drives a real RED stub to verified-GREEN offline (no API key,
  no network). Tests: manifest building, routing, fail-safe, ownership enforcement,
  headline test (red stub + FakeTransport fix + test pass -> ok=True).

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

| Capability            | claude-code  | codex (Phase 2)       |
|-----------------------|:------------:|:---------------------:|
| parallel_dispatch     | yes          | no (ext loop)         |
| worker filesystem     | yes          | no (orch injects)      |
| worker shell          | yes          | no (orch runs)         |
| structured_output     | yes (~perfect)| yes (JSON schema)      |
| worktree_isolation    | yes          | no (temp-dir)         |
| native_cost_tracking  | yes          | yes (usage metadata)   |
| tool_use_accuracy     | ~0.99        | ~0.92                 |
| verification_tier     | 1            | 2                     |

## Phase 2 Codex Implementation Details

The Codex driver proves a non-Claude backend can take a real coding task
end-to-end through the AgentDriver and produce orchestrator-verified results,
entirely offline (no API key, no network in CI).

**dispatch_worker**: Orchestrator-managed worker (Tier 2):
- Injects owned-file contents into the prompt (worker has no filesystem access).
- Calls OpenAI Chat Completions API via injectable transport (default=urllib).
- Requests strict JSON schema output (full-file replacements).
- Validates ALL JSON with bounded in-turn retry (<=2 attempts).
- Enforces ownership: rejects out-of-scope paths wholesale.
- Pre-dispatch max_owned_bytes guard: fails safe on oversized files (no
  truncation).
- Writes full-file replacements to disk; never applies diffs.
- Records usage.total_tokens for cost tracking.
- CRITICAL: Green is NOT decided by the model's done:true; it is decided by
  the orchestrator running run_command and getting exit 0 (center verification).

**Transport seam**: The injectable transport callable keeps CI offline. Tests
pass FakeTransport with canned responses; production code reads OPENAI_API_KEY
from environment and uses default_openai_transport (stdlib urllib, hard timeout).

**Verification policy**: verification_policy(caps) maps tier 2 -> {
validate_all_json: True, spot_check_frac: 0.50, repair_cap: 2,
require_adversarial_review: True }. Feeds the wave's integration verifier.

## Phase 3 Bridge Implementation Details

The wave bridge connects AgentDriver backends to wave-flat-dispatch manifest
items, making verification tier driven by backend capability, not config.

**build_manifest_item(driver, item) -> dict**:
- Takes a backlog item {slug, ownsFiles, prompt, testCmd, workDir, ...} + driver.
- Returns manifest-item dict enriched with: model (from driver.resolve_model('worker'))
  and verificationTier (from driver.probe_capabilities().recommended_verification_tier).
- Preserves all input fields; adds only model + tier.

**dispatch_item(driver, item) -> dict**:
- Routes execution by driver.probe_capabilities().worker_filesystem_access:
  - True (Claude tier-1): returns {route:'harness', ...} (harness will dispatch).
  - False (Codex tier-2+): orchestrator-managed: calls driver.dispatch_worker(),
    then driver.run_command() for the test. Returns {route:'driver', ok, testExit, filesWritten, ...}.
- CRITICAL: Green ONLY if test exit code == 0. Never from model's done:true.
- Fail-safe: any exception -> ok=False, never a false green.
- Ownership enforced at driver level (dispatch_worker rejects out-of-scope paths).

**Tests**: prove a non-Claude backend (Codex + FakeTransport) takes a RED unittest
stub, applies a fix, runs the test, and returns ok=True ONLY because the test passed
(exit 0). All offline, no API key, no network.

## Status

- **Phase 1**: shipped. Interface + Claude reference adapter + contract tests.
- **Phase 2**: shipped. Codex OpenAI Chat Completions implementation wired
  end-to-end. All offline tests GREEN (no API key, no network). One live test
  gated by AESOP_CODEX_LIVE + OPENAI_API_KEY (skipped in CI).
- **Phase 3**: shipped. Wave bridge wiring driver -> manifest + orchestrator-side
  dispatch. Proves non-Claude backends can drive items end-to-end with verified-honest
  decisions (green only from test exit 0). All offline tests GREEN.
- **Next**: Refactor wave-flat-dispatch onto the driver (Phase 1 handoff).
- **Future**: Open-model adapter (Tier-4 backend).
