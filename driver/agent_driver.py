#!/usr/bin/env python3
"""AgentDriver -- the backend-portability seam for aesop's wave loop.

Aesop's orchestration core (the wave/flat-dispatch cycle) is written against
Claude Code's Workflow harness. To run the same wave algorithm on Codex or an
open-model runner, the orchestration loop must talk to its execution backend
through ONE narrow interface instead of calling Claude-Code-specific functions
directly. That interface is `AgentDriver`.

Grounded in the design spike (conductor3/plans/spike-multitool-portability.md),
which distils everything the wave loop needs from a backend down to a handful of
operations. This module encodes those as an abstract base class (ABC) with five
abstract methods plus honest capability metadata.

THE FIVE OPERATIONS (what the wave loop needs from ANY backend)
---------------------------------------------------------------
1. probe_capabilities() -> DriverCapabilities
      Honest self-report: does this backend do parallel dispatch, native
      tool-use, structured output, worktree isolation, cost tracking? What is
      its realistic tool-use accuracy, and therefore which verification tier
      does the orchestrator owe it? Everything else keys off this.

2. dispatch_worker(request) -> WorkerResult
      Spawn ONE isolated worker against a prompt, a set of owned files, and a
      working directory. The worker is the unit that (per the spike) may read
      files, write files, run a shell command, and return a STRUCTURED result.
      Whether the worker does those itself or the orchestrator does them on the
      worker's behalf is a per-backend fact reported by probe_capabilities()
      (worker_filesystem_access / worker_shell_access / structured_output).

3. worker_status(worker_id) -> WorkerStatus
      Liveness / stall detection. The watchdog needs to tell "still working"
      from "wedged" so it can relaunch. Backends without native status must
      approximate (heartbeat age, last-output age).

4. run_command(command, cwd, shell) -> CommandResult
      ORCHESTRATOR-side command execution: tests, git, verification. This is
      distinct from a worker running a shell command -- it is the main thread
      checking the fleet's work, and every backend must support it (the
      orchestrator always runs on a real host).

5. resolve_model(role) -> str
      Map an abstract role ("worker" / "setup" / "verify") to a concrete model
      id for this backend. Claude Code returns "haiku"/"sonnet"; Codex maps to
      "gpt-3.5-turbo"/"gpt-4-turbo"; open-model maps to "mistral:latest", etc.

INVARIANTS
----------
* The wave loop calls ONLY AgentDriver methods -- never `agent()`, `parallel()`,
  Bash/Read/Write tools, or `budget.spent()` directly. That is the whole point
  of the seam.
* probe_capabilities() must be HONEST. A backend that cannot do native parallel
  dispatch reports parallel_dispatch=False so the orchestrator supplies its own
  event loop. Lying here corrupts every downstream verification decision.
* Weaker workers (lower tool_use_accuracy) => higher recommended verification
  tier. Cheaper/weaker backends RAISE, not lower, the orchestrator's burden.
* stdlib-only, ASCII-only, Windows + Linux safe. No provider SDKs imported at
  this layer; concrete adapters own their own dependencies.

This file defines the CONTRACT only. Concrete adapters live alongside it:
  claude_code_driver.py  -- reference implementation (Claude Code parity)
  codex_driver.py        -- honest stub for the `codex` CLI backend
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# --------------------------------------------------------------------------
# Status / role vocabularies (plain string constants -- no enum ceremony,
# stays trivially JSON- and log-friendly across backends).
# --------------------------------------------------------------------------

# Worker lifecycle states reported by worker_status().
WORKER_RUNNING = "running"
WORKER_DONE = "done"
WORKER_STALLED = "stalled"
WORKER_FAILED = "failed"
WORKER_UNKNOWN = "unknown"

WORKER_STATES = (
    WORKER_RUNNING,
    WORKER_DONE,
    WORKER_STALLED,
    WORKER_FAILED,
    WORKER_UNKNOWN,
)

# Abstract model roles the wave loop asks for; resolve_model() maps these to
# concrete backend model ids.
ROLE_WORKER = "worker"
ROLE_SETUP = "setup"
ROLE_VERIFY = "verify"

MODEL_ROLES = (ROLE_WORKER, ROLE_SETUP, ROLE_VERIFY)

# Effort hints a dispatch may carry (advisory; backends map to their own knobs).
EFFORT_QUICK = "quick"
EFFORT_NORMAL = "normal"
EFFORT_THOROUGH = "thorough"

EFFORT_LEVELS = (EFFORT_QUICK, EFFORT_NORMAL, EFFORT_THOROUGH)


# --------------------------------------------------------------------------
# Capability probe payload.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DriverCapabilities:
    """Honest self-description of a backend, returned by probe_capabilities().

    The orchestrator reads this ONCE up front and adapts its strategy: whether
    to supply its own parallel event loop, whether to validate every worker's
    JSON, how aggressively to spot-check, and how many repair rounds to budget.

    Fields are deliberately booleans + a single accuracy float + a recommended
    tier, so the orchestrator's branching stays simple and auditable.
    """

    # Human/log-facing backend name, e.g. "claude-code", "codex", "open-model".
    name: str

    # Can the backend run multiple workers concurrently by itself? If False,
    # the orchestrator must drive parallelism from its own event loop.
    parallel_dispatch: bool = False

    # Can a dispatched WORKER read/write files on its own (vs. the orchestrator
    # injecting file contents into the prompt and writing results back)?
    worker_filesystem_access: bool = False

    # Can a dispatched WORKER run shell commands on its own?
    worker_shell_access: bool = False

    # Does the backend natively return schema-valid structured output, or must
    # the orchestrator parse/repair free text into JSON?
    structured_output: bool = False

    # Does the backend give each worker an isolated git worktree, or must the
    # orchestrator fall back to temp-dir isolation?
    worktree_isolation: bool = False

    # Does the backend report real token spend per call (vs. estimate-only)?
    native_cost_tracking: bool = False

    # Can the backend report worker liveness natively, or must stall detection
    # be approximated from heartbeat/output age?
    native_stall_detection: bool = False

    # Honest realistic tool-use / structured-output success rate in [0.0, 1.0].
    # This is the load-bearing number: it drives the verification tier.
    tool_use_accuracy: float = 0.0

    # Recommended orchestrator verification tier (1 = light spot-check ...
    # 4 = validate everything + heavy spot-check). Derived from accuracy but
    # stated explicitly so config/audit can read it without recomputing.
    recommended_verification_tier: int = 4

    # Concrete model ids this backend can dispatch, best-effort.
    available_models: Tuple[str, ...] = field(default_factory=tuple)

    # Free-form honesty notes: known limitations, required external harness,
    # opaque cost meters, etc. Surfaced in logs and config docs.
    notes: str = ""

    def summary(self) -> str:
        """One-line ASCII summary for logs/dashboards."""
        return (
            "{name}: parallel={p} wfs={f} wsh={s} structured={o} "
            "worktree={w} cost={c} stall={d} acc={a:.2f} tier={t}".format(
                name=self.name,
                p=int(self.parallel_dispatch),
                f=int(self.worker_filesystem_access),
                s=int(self.worker_shell_access),
                o=int(self.structured_output),
                w=int(self.worktree_isolation),
                c=int(self.native_cost_tracking),
                d=int(self.native_stall_detection),
                a=self.tool_use_accuracy,
                t=self.recommended_verification_tier,
            )
        )


# --------------------------------------------------------------------------
# Dispatch request / result payloads.
# --------------------------------------------------------------------------


@dataclass
class WorkerRequest:
    """One unit of work handed to dispatch_worker().

    Bundles the prompt with the isolation contract (owned_files + workdir) that
    aesop's single-writer discipline depends on: a worker touches ONLY the files
    it owns, inside its own workdir. `result_schema`, when given, is the JSON
    schema the worker's structured result should satisfy.
    """

    prompt: str
    owned_files: Tuple[str, ...] = field(default_factory=tuple)
    workdir: str = "."
    model: Optional[str] = None          # concrete id, or None to resolve by role
    role: str = ROLE_WORKER              # abstract role for resolve_model()
    label: Optional[str] = None          # short name for logging
    phase: Optional[str] = None          # orchestration phase (Build, Ship, ...)
    result_schema: Optional[Dict] = None  # structured-output schema, if any
    effort: str = EFFORT_NORMAL


@dataclass
class WorkerResult:
    """Structured outcome of a dispatch_worker() call.

    `structured` is the parsed/validated result object (may be None if the
    backend produced only free text). `files_written` records what the worker
    (or the orchestrator on its behalf) changed, for verification. `ok` is the
    single boolean the wave loop branches on.
    """

    worker_id: str
    status: str = WORKER_UNKNOWN         # one of WORKER_STATES
    ok: bool = False
    structured: Optional[Dict] = None
    text: str = ""
    files_written: Tuple[str, ...] = field(default_factory=tuple)
    tokens_spent: Optional[int] = None   # None => backend does not report spend
    error: Optional[str] = None


@dataclass
class WorkerStatus:
    """Liveness snapshot for a worker, returned by worker_status()."""

    worker_id: str
    state: str = WORKER_UNKNOWN          # one of WORKER_STATES
    stalled: bool = False
    age_s: float = 0.0                   # seconds since last observed progress
    detail: str = ""


@dataclass
class CommandResult:
    """Result of an orchestrator-side run_command()."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


# --------------------------------------------------------------------------
# The interface.
# --------------------------------------------------------------------------


class AgentDriver(ABC):
    """Abstract backend the wave loop dispatches through.

    Subclass and implement the five abstract methods to add a backend. The
    orchestration algorithm is written against THIS type and nothing else, so a
    new backend is a new subclass -- no changes to the wave loop.
    """

    #: Stable backend identifier; subclasses should override.
    name: str = "abstract"

    # -- Operation 1: capability probe -------------------------------------
    @abstractmethod
    def probe_capabilities(self) -> DriverCapabilities:
        """Report -- honestly -- what this backend can and cannot do.

        Called once up front. The orchestrator keys its parallelism, output
        validation, spot-check rate, and repair budget off the returned
        DriverCapabilities. Must not lie: an over-optimistic probe corrupts
        every downstream verification decision.
        """
        raise NotImplementedError

    # -- Operation 2: dispatch an isolated worker --------------------------
    @abstractmethod
    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        """Spawn ONE isolated worker for `request` and return its result.

        The worker operates on request.owned_files within request.workdir. It
        may read files, write files, run a shell command, and return a
        structured result -- the extent to which it does these itself vs. the
        orchestrator doing them on its behalf is reported by
        probe_capabilities() (worker_filesystem_access / worker_shell_access /
        structured_output). Implementations resolve request.model (falling back
        to resolve_model(request.role) when None).
        """
        raise NotImplementedError

    # -- Operation 3: stall detection / status -----------------------------
    @abstractmethod
    def worker_status(self, worker_id: str) -> WorkerStatus:
        """Return liveness for a previously dispatched worker.

        Backends with native status report it directly; others approximate from
        heartbeat/output age. Powers the watchdog's stall-and-relaunch loop.
        """
        raise NotImplementedError

    # -- Operation 4: orchestrator-side command execution ------------------
    @abstractmethod
    def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        shell: Optional[str] = None,
    ) -> CommandResult:
        """Run `command` on the ORCHESTRATOR's host (tests, git, verification).

        Distinct from a worker running a shell command: this is the main thread
        checking the fleet's output. Every backend must support it. `shell` is
        an advisory hint ("bash" | "powershell" | "sh"); implementations pick a
        sane default per platform.
        """
        raise NotImplementedError

    # -- Operation 5: model selection --------------------------------------
    @abstractmethod
    def resolve_model(self, role: str) -> str:
        """Map an abstract role to a concrete backend model id.

        `role` is one of MODEL_ROLES. Claude Code returns Anthropic names;
        Codex maps to OpenAI models; open-model maps to Ollama/OpenRouter ids.
        """
        raise NotImplementedError

    # -- Optional convenience (non-abstract) -------------------------------
    def get_tokens_spent(self) -> Optional[int]:
        """Cumulative tokens spent, or None if the backend cannot report it.

        Optional: the default returns None (estimate-only backend). Override
        when the backend exposes real spend (Claude Code budget API, OpenAI
        usage metadata).
        """
        return None

    def describe(self) -> str:
        """ASCII one-liner combining name + capability summary (for logs)."""
        return self.probe_capabilities().summary()
