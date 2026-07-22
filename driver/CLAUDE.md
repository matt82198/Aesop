# driver/ — AgentDriver backend-portability seam

**What**: the domain contract letting aesop's wave loop run on non-Claude backends
(Codex, open models); the loop dispatches only through the `AgentDriver` interface.
**Phases 1-3 shipped** (interface + reference adapter; Codex Chat Completions; wave bridge).

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
- **openai_compatible_driver.py** — OpenAI-compatible backend (Ollama, OpenRouter, etc.).
- **verification_policy.py** — Maps verification tier -> orchestrator tuning (validate_all_json,
  spot_check_frac, repair_cap, require_adversarial_review).
- **wave_loop.py** — the wave ENGINE: preflight ownership guard, parallel build,
  bounded repair, adversarial review, per-repo batched git ship, recovery journal.
- **wave_bridge.py** — Phase 3: bridges AgentDriver backends to wave manifest items.
  build_manifest_item() enriches with verificationTier + model; dispatch_item() routes
  by capability and decides green ONLY from test exit code (not model's say-so).
- **backend_config.py** — Per-deployment model resolution (role → model id, API key/base URL).
- **README.md** — the abstraction, the phased roadmap, the verification thesis.
- **../tests/test_agent_driver.py** — the contract's test suite.
- **../tests/test_codex_driver_e2e.py** — Phase 2 end-to-end offline tests
  (FakeTransport, red-to-green verification, retry logic, ownership enforcement)
  + gated live test (AESOP_CODEX_LIVE env var).
- **../tests/test_wave_bridge.py** — Phase 3 offline e2e (honest green: exit 0 only).
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
entirely offline (no API key, no network in CI). The probe's `tool_use_accuracy` 0.92 assertion is evidence-backed as conservative by the 2026-07-22 live run (gpt-4o-mini 32/32 composite, `bench/results/accuracy-live-2026-07-22.json`); single-run, N=32 curated — not a transfer claim.

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

**Transport seam**: injectable transport callable keeps CI offline (FakeTransport
in tests; production reads OPENAI_API_KEY, default_openai_transport, hard timeout).

**Verification policy**: verification_policy(caps) maps tier 2 -> {
validate_all_json: True, spot_check_frac: 0.50, repair_cap: 2,
require_adversarial_review: True }. Feeds the wave's integration verifier.

## Phase 3 Bridge Implementation Details

Connects AgentDriver backends to wave-flat-dispatch manifest items; verification
tier is driven by backend capability, not config.

**build_manifest_item(driver, item) -> dict**: enriches a backlog item with model
(driver.resolve_model), verificationTier (probe), and the four policy knobs from
verification_policy(caps) — RESOLVED ONCE, carried as literal manifest fields so the
template cannot recompute/drift; tier-1/Claude path stays byte-identical (repairCap=1,
requireAdversarialReview=false, spotCheckFrac=0.10, validateAllJson=false).

**dispatch_item(driver, item) -> dict**:
- Routes by worker_filesystem_access: True→{route:'harness'}; False→orchestrator-managed
  (dispatch_worker + run_command test). Returns {route, ok, testExit, filesWritten, verified, ...}.
- HONESTY: Green (ok=True) ONLY on test exit 0; never from model's done:true. No testCmd
  → unverified (ok=False, verified=False, reason='no_test_command'): "no test" ≠ "verified."
- Fail-safe: exception → ok=False, verified=False. Ownership at driver level.

**Tests**: prove a non-Claude backend (Codex + FakeTransport) takes a RED unittest
stub, applies a fix, runs the test, and returns ok=True ONLY because the test passed
(exit 0). All offline, no API key, no network.

## Wave Scheduler (WS3a Pilot)

**wave_scheduler.py** — single-cycle backlog orchestration: intake up to N file-disjoint todo items from tracker.json (empty/missing ownsFiles REJECTED; paths normalized posix+casefold-on-Windows before overlap checks; required fields pre-validated) -> manifest via build_manifest_item (model + verificationTier from driver.probe) -> HALT + cost-ceiling gates (fail-CLOSED: module import failure or check exception = abort with honest Report, phase=gate_unavailable) -> run_wave (recovery journal + git ship) -> STOP before merge; Report JSON {phase, wave_id, items_selected, items_skipped, items_failed_build, items_shipped, branch, sha, merged:false, halt_reason?, ceiling_reason?, success}. After ship, selected items atomically marked in_progress in tracker (temp+os.replace; dry-run never mutates) so a second run cannot double-dispatch.

**CLI**: `python driver/wave_scheduler.py --tracker <path> --max-items N --dry-run|--execute`

**Tests** (tests/test_wave_scheduler.py, 24): disjoint/normalization/rejection cases, gate fail-closed incl. exception paths, dry-run purity, tracker idempotence, Report honesty, empty-tracker EMPTY report; module-tmpdir hygiene; all TestCase.

**Invariants**: stdlib-only, ASCII, Windows+Linux safe (list-form subprocess); manifest items carry resolved policy knobs from verification_policy (no recompute drift); merge stays manual in the pilot.

## Status

- **Phase 1**: shipped. Interface + Claude reference adapter + contract tests.
- **Phase 2**: shipped. Codex OpenAI Chat Completions implementation. Offline tests GREEN.
- **Phase 3**: shipped. Wave bridge: driver → manifest, orchestrator-side dispatch.
  Proves non-Claude backends drive items end-to-end with honest green (test exit 0 only).
- **Wave Scheduler (WS3a)**: shipped. Single-cycle orchestration: intake → manifest → dispatch → report (manual merge). Pilot gate: disjoint filter, HALT/ceiling, run_wave integration.
- **Next**: Refactor wave-flat-dispatch onto the driver (Phase 1 handoff).
- **Future**: Open-model adapter (Tier-4 backend).
