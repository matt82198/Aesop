#!/usr/bin/env python3
"""CodexDriver -- honest STUB AgentDriver for the OpenAI `codex` CLI backend.

This is a Phase 2 stub (per the spike). Its job today is to prove the
AgentDriver seam is real for a NON-Claude backend: the class satisfies the
interface, and -- critically -- its capability probe is filled in HONESTLY with
what the codex/OpenAI backend can and cannot do natively. The three operations
that require the actual CLI/API integration raise NotImplementedError with a
clear TODO pointing at where the work goes.

WHY THE PROBE IS THE LOAD-BEARING PART
--------------------------------------
The spike's central finding: Codex/OpenAI agents cannot touch the filesystem,
cannot run shell commands, and have no native parallelism -- the ORCHESTRATOR
must supply an external event loop and do file I/O + command execution on the
worker's behalf. And tool-use accuracy (~0.90-0.95) is below Claude's ~0.99, so
the orchestrator owes this backend Tier-2 verification (validate every JSON
output; ~50% spot-check; repair cap 2). Encoding those facts truthfully here is
what lets the orchestrator adapt BEFORE any CLI code exists.

CODEX CLI SHAPE (from the spike's findings)
-------------------------------------------
* Dispatch is a subprocess call to the `codex` CLI (or the OpenAI API directly)
  with function-calling + a JSON schema for structured output.
* No native parallel(): the orchestrator runs `codex` invocations concurrently
  from its own event loop / process pool.
* Agents have no filesystem or shell access: the orchestrator injects file
  contents into the prompt and writes results back; it runs tests/git itself.
* Token spend comes from usage metadata on each response (real, but the vendor
  meter is otherwise opaque -- no in-repo audit trail).
* No git worktree per worker: fall back to temp-dir isolation.

stdlib-only, ASCII-only, Windows + Linux safe. No `openai` import here -- the
real adapter owns that dependency; this stub stays importable everywhere.
"""

from typing import Optional

from agent_driver import (
    AgentDriver,
    CommandResult,
    DriverCapabilities,
    ROLE_SETUP,
    ROLE_VERIFY,
    ROLE_WORKER,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
    WORKER_UNKNOWN,
)


# Abstract-role -> OpenAI model mapping (spike Section 9). Workers map to the
# cheap model, setup/verify to the stronger one. resolve_model() is concrete
# even in the stub -- model selection needs no CLI, just a table.
_DEFAULT_MODEL_MAP = {
    ROLE_WORKER: "gpt-3.5-turbo",
    ROLE_SETUP: "gpt-4-turbo",
    ROLE_VERIFY: "gpt-4-turbo",
}

# Shared TODO text for the ops that need the real CLI/API integration.
_TODO = (
    "CodexDriver.{op} is not implemented yet (Phase 2 stub). TODO: {detail} "
    "See driver/README.md 'Phased roadmap' and the design spike "
    "(spike-multitool-portability.md, Section 3.2 + Section 6 Phase 2)."
)


class CodexDriver(AgentDriver):
    """Honest stub adapter for the `codex` / OpenAI backend."""

    name = "codex"

    def __init__(self, model_map: Optional[dict] = None):
        self._model_map = dict(_DEFAULT_MODEL_MAP)
        if model_map:
            self._model_map.update(model_map)

    # -- Operation 1: capability probe (FILLED IN HONESTLY) ----------------
    def probe_capabilities(self) -> DriverCapabilities:
        """Truthful capability matrix for the codex/OpenAI backend.

        These values are the spike's findings encoded as data. They are correct
        NOW even though dispatch is unimplemented -- which is the point: the
        orchestrator can plan its verification strategy before the CLI wiring
        exists.
        """
        return DriverCapabilities(
            name=self.name,
            parallel_dispatch=False,          # no native async; orchestrator loops
            worker_filesystem_access=False,   # agents cannot read/write files
            worker_shell_access=False,        # agents cannot run shell commands
            structured_output=True,           # function-calling + JSON schema
            worktree_isolation=False,         # temp-dir fallback; no git for agents
            native_cost_tracking=True,        # usage.total_tokens per response
            native_stall_detection=False,     # orchestrator times out / polls
            tool_use_accuracy=0.92,           # ~0.90-0.95, below Claude's ~0.99
            recommended_verification_tier=2,  # validate all JSON; ~50% spot-check
            available_models=("gpt-3.5-turbo", "gpt-4-turbo"),
            notes=(
                "STUB (Phase 2). Requires an EXTERNAL orchestration harness: the "
                "orchestrator supplies parallelism, file I/O, and command "
                "execution on the worker's behalf. OpenAI meter is opaque (no "
                "in-repo cost audit trail). Wave/cycle concept is absent in "
                "codex -- it is task-level, not cycle-driven."
            ),
        )

    # -- Operation 2: dispatch (NOT YET IMPLEMENTED) -----------------------
    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        """TODO: shell out to `codex` (or OpenAI API) with function-calling.

        The real implementation must, per the spike:
          * inject request.owned_files contents into the prompt (agents have no
            filesystem access);
          * call the CLI/API with the resolved model + request.result_schema for
            structured output;
          * parse + VALIDATE the returned JSON (Tier-2: every output validated),
            with in-turn retry on malformed JSON;
          * write any produced file contents back to disk itself and populate
            WorkerResult.files_written;
          * read usage.total_tokens into WorkerResult.tokens_spent.
        """
        raise NotImplementedError(
            _TODO.format(
                op="dispatch_worker",
                detail=(
                    "shell out to the codex CLI / OpenAI API with "
                    "function-calling + JSON schema, inject owned-file contents "
                    "into the prompt, validate the returned JSON, and write "
                    "results back (agents have no filesystem access)"
                ),
            )
        )

    # -- Operation 3: stall detection (NOT YET IMPLEMENTED) ----------------
    def worker_status(self, worker_id: str) -> WorkerStatus:
        """TODO: track subprocess/request liveness in the external harness.

        codex has no native worker-status API, so the orchestrator must record
        dispatch start time and last output, and time out wedged calls. Until
        that harness exists we report UNKNOWN rather than guess.
        """
        return WorkerStatus(
            worker_id=worker_id,
            state=WORKER_UNKNOWN,
            stalled=False,
            age_s=0.0,
            detail=_TODO.format(
                op="worker_status",
                detail=(
                    "track dispatch start/last-output time in the external "
                    "harness and time out wedged codex calls"
                ),
            ),
        )

    # -- Operation 4: orchestrator-side command (NOT YET IMPLEMENTED) ------
    def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        shell: Optional[str] = None,
    ) -> CommandResult:
        """TODO: run on the orchestrator host via the external harness.

        Conceptually identical to a plain subprocess call (this is the main
        thread running tests/git, not an agent), but it belongs to the Codex
        external harness so cost/verification accounting is consistent. Stubbed
        deliberately so the Phase-2 harness owns one command path.
        """
        raise NotImplementedError(
            _TODO.format(
                op="run_command",
                detail=(
                    "execute on the orchestrator host from the external Node/"
                    "Python harness (child_process/subprocess), keeping command "
                    "execution accounted alongside dispatch"
                ),
            )
        )

    # -- Operation 5: model selection (concrete even in the stub) ----------
    def resolve_model(self, role: str) -> str:
        """Map an abstract role to an OpenAI model id (spike Section 9).

        Unknown roles fall back to the worker model so a mis-typed role never
        silently escalates to the pricier gpt-4-turbo.
        """
        return self._model_map.get(role, self._model_map[ROLE_WORKER])

    # -- Optional: cost tracking -------------------------------------------
    def get_tokens_spent(self) -> Optional[int]:
        """Real spend comes from usage metadata once dispatch is wired.

        Until dispatch_worker aggregates usage.total_tokens there is nothing to
        report, so return None (estimate-only) rather than a fake zero.
        """
        return None
