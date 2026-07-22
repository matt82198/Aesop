#!/usr/bin/env python3
"""ClaudeCodeDriver -- reference AgentDriver for the Claude Code backend.

This is the PARITY reference: it maps the five AgentDriver operations onto what
Claude Code's Workflow harness already provides. It is intentionally a thin,
well-documented adapter, because in Claude Code the actual dispatch does NOT run
inside this Python process -- it runs inside the harness's Workflow context
(the `agent()`, `parallel()`, Read/Write/Bash tools, `budget.spent()`).

WHAT MAPS WHERE
---------------
  Operation            Claude Code mechanism            Lives where
  -------------------  -------------------------------  ------------------------
  probe_capabilities   static, known-good facts         this file (concrete)
  dispatch_worker      Workflow agent()/Task tool       HARNESS (conceptual)
  worker_status        heartbeat + harness liveness     HARNESS + state files
  run_command          Bash tool                        HARNESS
  resolve_model        Anthropic model-name passthrough this file (concrete)

So two of the five ops (probe_capabilities, resolve_model) are fully concrete
Python here -- they are pure data/mapping and need no harness. The other three
(dispatch_worker, worker_status, run_command) are documented adapters: in a live
Claude Code wave they are serviced by the harness's own tools, not by this
process. This class exists so the SEAM is real and testable -- the wave loop can
be written against AgentDriver and this reference proves the Claude Code backend
satisfies the contract. When the wave-flat-dispatch template is refactored onto
the driver (spike Phase 1), these three methods become the documented handoff
points to the harness.

For out-of-harness use (tests, tooling, local scripts) run_command is given a
real subprocess implementation so it is not a dead stub; dispatch_worker and
worker_status raise a clear, explained error rather than pretending to spawn a
Claude agent from plain Python.

stdlib-only, ASCII-only, Windows + Linux safe.
"""

import subprocess
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


# Default abstract-role -> Anthropic model mapping. Workers are Haiku by policy
# (aesop cardinal rule: subagents are always Haiku); setup/verify may lift to
# Sonnet. resolve_model() reads this and is overridable via the constructor.
_DEFAULT_MODEL_MAP = {
    ROLE_WORKER: "haiku",
    ROLE_SETUP: "sonnet",
    ROLE_VERIFY: "haiku",
}

# Marker error text shared with tests: the ops that only a live harness can do.
_HARNESS_ONLY = (
    "ClaudeCodeDriver.{op} is serviced by the Claude Code Workflow harness "
    "(agent()/Task tool), not by this Python process. In a live wave the "
    "orchestrator dispatches through the harness; this reference adapter marks "
    "the seam. See driver/README.md 'What maps where'."
)


class ClaudeCodeDriver(AgentDriver):
    """Reference adapter mapping AgentDriver onto Claude Code."""

    name = "claude-code"

    def __init__(self, model_map: Optional[dict] = None):
        # Copy so callers cannot mutate our defaults; fall back per-role.
        self._model_map = dict(_DEFAULT_MODEL_MAP)
        if model_map:
            self._model_map.update(model_map)

    # -- Operation 1: capability probe (concrete) --------------------------
    def probe_capabilities(self) -> DriverCapabilities:
        """Claude Code is the self-contained, high-accuracy reference backend.

        Every capability is native and instant; tool-use accuracy is ~0.99, so
        the recommended verification tier is 1 (light spot-check). These facts
        are static and known-good -- no probing round-trip required.
        """
        return DriverCapabilities(
            name=self.name,
            parallel_dispatch=True,          # native parallel() in the harness
            worker_filesystem_access=True,   # workers use Read/Write tools
            worker_shell_access=True,        # workers use the Bash tool
            structured_output=True,          # agent(schema=...) is near-perfect
            worktree_isolation=True,         # orchestrator manages git worktrees
            native_cost_tracking=True,       # budget.spent() real-time API
            native_stall_detection=True,     # harness + heartbeat liveness
            tool_use_accuracy=0.99,
            recommended_verification_tier=1,
            available_models=("haiku", "sonnet", "opus"),
            notes=(
                "Reference backend. Self-contained: no external harness. "
                "dispatch_worker/worker_status/run_command are serviced by the "
                "Claude Code Workflow harness in a live wave."
            ),
        )

    # -- Operation 2: dispatch (harness-serviced) --------------------------
    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        """Documented seam: real dispatch happens in the harness.

        In a live Claude Code wave the orchestrator spawns the worker via the
        harness's agent()/Task tool with the resolved model, the owned-files
        contract, and (optionally) request.result_schema. From plain Python
        there is no Claude agent to spawn, so we raise a clear, explained error
        rather than fake a result.
        """
        raise NotImplementedError(_HARNESS_ONLY.format(op="dispatch_worker"))

    # -- Operation 3: stall detection (harness-serviced) -------------------
    def worker_status(self, worker_id: str) -> WorkerStatus:
        """Documented seam: liveness comes from the harness + heartbeat files.

        A live wave reads worker liveness from the harness and the fleet's
        heartbeat/state files. Out of harness there is nothing to observe, so
        we report UNKNOWN honestly.
        """
        return WorkerStatus(
            worker_id=worker_id,
            state=WORKER_UNKNOWN,
            stalled=False,
            age_s=0.0,
            detail=_HARNESS_ONLY.format(op="worker_status"),
        )

    # -- Operation 4: orchestrator-side command (real) ---------------------
    def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        shell: Optional[str] = None,
    ) -> CommandResult:
        """Run a command on the orchestrator host.

        In a live wave this is the Bash tool; out of harness we back it with a
        real subprocess so tooling/tests get genuine behavior. `shell` is
        advisory -- we always execute through the platform shell so the same
        call works on Windows and Linux.
        """
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
            )
            return CommandResult(
                exit_code=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
            )
        except OSError as exc:
            return CommandResult(exit_code=127, stdout="", stderr=str(exc))

    # -- Operation 5: model selection (concrete) ---------------------------
    def resolve_model(self, role: str) -> str:
        """Map an abstract role to an Anthropic model name.

        Unknown roles fall back to the worker (Haiku) mapping so a mis-typed
        role can never silently escalate cost.
        """
        return self._model_map.get(role, self._model_map[ROLE_WORKER])

    # -- Optional: cost tracking -------------------------------------------
    def get_tokens_spent(self) -> Optional[int]:
        """Read fleet ledger (OUTCOMES-LEDGER.md) and return sum of tokens_in+tokens_out.

        Returns None only when the ledger file is truly absent (first run, no sessions yet).
        Returns 0 when the ledger exists but has no data rows (edge case, but consistent).
        Returns the summed token spend when ledger data exists.

        This implementation reuses fleet_ledger.py's shared parser for consistency
        with cost_ceiling.py and other spend-tracking tools.
        """
        try:
            # Import fleet_ledger from tools/ to reuse its parser (single source of truth)
            try:
                import sys
                from pathlib import Path
                REPO = Path(__file__).resolve().parent.parent
                TOOLS_DIR = REPO / "tools"
                if str(TOOLS_DIR) not in sys.path:
                    sys.path.insert(0, str(TOOLS_DIR))
                import fleet_ledger
            except ImportError:
                # fleet_ledger not available; return None
                return None

            # Check if ledger exists BEFORE calling parse_ledger_rows()
            # (because parse_ledger_rows calls ensure_ledger_header which creates it)
            try:
                ledger_file, _, _ = fleet_ledger.get_ledger_paths()
                if not ledger_file.exists():
                    # Ledger file doesn't exist: truly no session data yet
                    return None
            except Exception:
                # If even checking existence fails, return None (safe default)
                return None

            # Parse the ledger rows
            rows = fleet_ledger.parse_ledger_rows()

            # If rows list is empty, ledger exists but has no data yet
            if not rows:
                return 0

            # Sum tokens_in + tokens_out across all rows
            total = 0
            for row in rows:
                try:
                    total += row.get("tokens_in", 0) + row.get("tokens_out", 0)
                except (TypeError, ValueError):
                    # Skip malformed rows; continue with others
                    continue

            return total

        except Exception:
            # On any exception (permission, parse, etc.), return None (fail-open)
            # This preserves fleet availability; cost_ceiling has its own fallback
            return None
