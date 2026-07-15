# Tiered Cognition/Execution — Wave-11 Spike Design

> **STATUS: SPIKE — NOTHING HERE IS ACTIVATED.** No live hook, settings.json,
> or skill was modified. The prototype (`strip-tools-hook.mjs`) and shim agent
> (`aesop-cognition.example.md`) live only in this directory. Rollout is a
> wave-12 decision — see `FINDINGS.md` for the GO/NO-GO and steps.

Source plan: `conductor3/plans/aesop-wave11-tiered-cognition.md`.

## 1. Architecture recap

```
Fable 5  ⇄  Haiku  ⇄  Opus  ⇄  Haiku  ⇄  Sonnet 5  ⇄  Haiku  ⇄  (files / git / tools / tests)
(cognition)  courier  (cognition) courier  (cognition)  executor
```

| Tier | Models | May do | May NOT do |
|---|---|---|---|
| Cognition | Fable 5, Opus, Sonnet 5 | Reason, decide, emit WORK-ORDERs, dispatch/message Haiku | Read, Write, Edit, Bash, Glob, Grep, WebFetch — any direct I/O/exec |
| Substrate | Haiku | Everything real: read/write/exec/git/tests + carry messages between tiers | Improvise, silently "fix" a work-order, summarize away errors |

Two mechanisms realize this: **(A)** a PreToolUse hook that strips I/O/exec
tools from cognition-tier subagents, and **(B)** a structured courier/executor
hand-off (WORK-ORDER → EXEC-BRIEF) so cognition output is mechanically
applicable and results flow back as typed briefs.

## 2. Mechanism A — the tool-stripping PreToolUse hook

Prototype: [`strip-tools-hook.mjs`](strip-tools-hook.mjs) — standalone, pure
`decide()` core, `--self-test` builds fixtures and asserts 27 cases (all pass).

### 2.1 Harness facts that shape the design

1. **The Agent tool input has NO `tools` field.** Its schema is
   `{description, prompt, subagent_type, model, isolation, run_in_background}`
   with `additionalProperties: false`. A hook's `updatedInput` therefore
   *cannot* inject a per-dispatch tool list (it would be an
   InputValidationError). The only supported way to constrain a subagent's
   tools today is the agent definition's `tools:` frontmatter
   (`~/.claude/agents/*.md`) — so dispatch-time stripping is implemented as a
   **rewrite to a shim agent type** whose definition carries the allowlist.
2. **PreToolUse hooks fire for subagents' own tool calls too**, which enables a
   call-time backstop independent of how the agent was dispatched.
3. **The hook payload does not name the session's model**
   (`{session_id, transcript_path, cwd, tool_name, tool_input, ...}`), so
   call-time tier detection is inferred from the transcript (§2.3).
4. **Hook composition hazard:** the live `force-haiku-subagents.mjs` already
   emits `updatedInput` on the same `Agent|Task` matcher. Two hooks rewriting
   the same call have no defined merge; at rollout the tier policy must be
   **merged into the model-policy hook as one file** (model routing decides the
   tier; the same decision then strips or keeps tools — one decision point, no
   ordering hazard).

### 2.2 Layer 1 — dispatch guard (matcher `Agent|Task`)

**Tier detection**, in order:

1. Explicit `tool_input.model` — substring match: `haiku` → substrate;
   `sonnet` / `opus` / `fable` → cognition.
2. Blank model + `subagent_type` → the installed agent definition's `model:`
   frontmatter (same catalog walk the model-policy hook uses).
3. Neither → **haiku** (correct by construction: the model-policy hook lands
   every non-specialist, non-escaped dispatch on Haiku).

**Decision table:**

| Dispatch | Action |
|---|---|
| Tier = haiku (or `subagent_type: fork`) | pass untouched |
| Tier = cognition, prompt has escape token | allow untouched + **audit** (§2.4) |
| Tier = cognition, no escape | **strip** — rewrite `subagent_type` → `aesop-cognition`, prepend `[COGNITION CONTRACT v1]` header naming the originally requested type |
| Malformed payload / unreadable catalog | pass (fail-open) |

**Kept tools** (via the shim's `tools:` frontmatter, see
[`aesop-cognition.example.md`](aesop-cognition.example.md)):
`Agent, SendMessage, TaskStop, Monitor` — reason, message, dispatch Haiku,
stop/monitor what it dispatched. Nothing else.

**Stripped (denied) tools:**
`Read, Write, Edit, MultiEdit, NotebookEdit, Bash, PowerShell, BashOutput,
KillShell, Glob, Grep, WebFetch, WebSearch, Skill, Artifact, ToolSearch,
EnterWorktree, ExitWorktree`.

Note the mission's generalization: cognition tiers lose **Read/Grep/Glob too**
— facts arrive via Haiku courier briefs, never raw file ingestion. This is the
"orchestrator reads nothing" cardinal rule applied to every expensive tier.

**Cost of the shim rewrite:** the original specialist's system prompt (its
`.md` body) is lost; the role survives only as the contract header line. §5
lists the wave-12 fix (generated per-specialist cognition variants).

### 2.3 Layer 2 — call-time backstop (matcher `Read|Write|Edit|NotebookEdit|Bash|PowerShell|Glob|Grep|WebFetch|WebSearch|Skill|Artifact`)

Defense in depth for dispatches that bypass Layer 1 (pre-existing sessions,
SDK-defined agents, the main thread, drift after a harness update).

1. Parse `transcript_path` (JSONL). Tier = model of the **last** assistant
   entry (`message.model`) — robust to mid-session model switches.
2. Escape check: any user entry containing an escape token (a subagent's
   dispatch prompt is the first user message of its transcript, so an escaped
   dispatch is visible here).
3. Decision: haiku or escaped → allow; cognition → **deny**; transcript
   missing/unreadable/model-free → pass (fail-open, no opinion).

The deny is **self-correcting**: `permissionDecision: "deny"` returns the
reason to the model, and the reason is an instruction —

> "Do NOT retry {tool}. Instead emit a WORK-ORDER v1 … and dispatch a Haiku
> executor agent to apply it and report back an EXEC-BRIEF."

so a cognition agent that tries to touch a file is redirected into the courier
pattern mid-flight instead of just failing.

**Main-thread consequence:** the backstop as specified also denies a Fable
main thread's direct writes — which *is* the cardinal rule ("orchestrator
never hand-writes files") — but today's orchestrator legitimately runs short
git one-liners. Rollout needs either a read-only Bash allowlist
(`git status|log|diff --stat` patterns) or a main-thread carve-out. Flagged in
FINDINGS; the spike prototype governs the listed tools uniformly.

### 2.4 Escape hatch — `[[ALLOW-TIER-TOOLS]]`

Same contract as the model policy's `[[ALLOW-NON-HAIKU]]`:

- Token in the dispatch prompt → the agent keeps its full toolset.
- **Never silent**: announced via `permissionDecisionReason` in the transcript
  AND appended as a JSON line to
  `${AESOP_ROOT:-~/aesop}/state/TIER-POLICY-ESCAPES.log`
  (`{ts, event: "tier_policy_escape", tool, session_id, cwd, description,
  requested_model, prompt_head}`).
- During migration, `[[ALLOW-NON-HAIKU]]` is grandfathered as implying tool
  retention (today's escalations are hands-on missions — this spike itself ran
  under it). Once cognition dispatch is the norm, escalate-model-but-stay-
  cognition becomes the default and `[[ALLOW-NON-HAIKU]]` stops implying tools.

## 3. Mechanism B — the courier/executor hand-off

### 3.1 WORK-ORDER v1 (cognition → executor)

A cognition agent's entire real-world intent for one coherent change-set,
batched into a single JSON document:

```json
{
  "kind": "work-order",
  "version": 1,
  "id": "wo-<slug>",
  "intent": "one-line goal (for logs and the brief)",
  "worktree": "C:/abs/path/to/isolated/worktree",
  "branch": "expected branch (executor verifies before acting)",
  "patch": "<unified diff as a single string, or null>",
  "commands": [
    { "run": "exact command line", "cwd": "abs path", "expect_exit": 0, "timeout_s": 120 }
  ],
  "verify": [
    { "run": "exact command line", "expect_exit": 0, "expect_stdout_re": "optional regex" }
  ],
  "report": { "format": "exec-brief/v1", "max_words": 200 }
}
```

Semantics:

- `patch` is applied with `git apply` (byte-exact context; a failed hunk is a
  FAILED brief, never hand-merged). `commands` run in listed order, stopping at
  the first unexpected exit. `verify` always runs after (even partially) —
  it is the evidence section of the brief.
- Ambiguity is an error: if the executor cannot apply the order *exactly as
  written*, it stops and reports; it never substitutes judgment.
- One work-order per coherent change-set (**batching amortizes the round-trip**
  — a whole patch + command plan, never line-by-line).

### 3.2 EXEC-BRIEF v1 (executor → cognition)

```json
{
  "kind": "exec-brief",
  "version": 1,
  "work_order_id": "wo-<slug>",
  "status": "APPLIED | FAILED | PARTIAL",
  "steps": [ { "step": "apply-patch | cmd:<n> | verify:<n>", "ok": true, "detail": "≤1 line" } ],
  "verify_results": [ { "run": "…", "exit": 0, "stdout_tail": "last ≤3 lines" } ],
  "verbatim_errors": [ "exact error text, untrimmed — empty array iff none" ],
  "files_touched": [ "relative paths" ],
  "commit": "sha or null"
}
```

### 3.3 Courier honesty rules

1. Apply **exactly** what the order says; no improvisation, no "small fixes".
2. Failures are reported **verbatim** in `verbatim_errors` — never summarized,
   never softened. The substrate must not editorialize.
3. A brief is **always** produced (inputs always produce outputs) — even a
   crash mid-order yields `status: FAILED` with whatever evidence exists.
4. Verification stays owner-owned: the executor *runs* the verify commands;
   the owning cognition tier *judges* the pass/fail brief
   (per `[[subagents-push-orchestrator-verifies]]`).

## 4. Worked example — a real round-trip (executed in this spike)

Task: one-line real doc change — link this spike directory from
`docs/README.md`. The cognition tier (Fable, this session) authored the
work-order below; a **real Haiku executor subagent** applied it.

### 4.1 The cognition-authored WORK-ORDER

```json
{
  "kind": "work-order",
  "version": 1,
  "id": "wo-w11-readme-spikes-link",
  "intent": "Add a Design Spikes section to docs/README.md linking the tiered-cognition spike",
  "worktree": "C:/Users/matt8/aesop-wt-wave11-mission-spike",
  "branch": "spike/wave11-tiered-cognition",
  "patch": "<the unified diff below, embedded verbatim>",
  "commands": [],
  "verify": [
    { "run": "git -C C:/Users/matt8/aesop-wt-wave11-mission-spike diff --numstat -- docs/README.md", "expect_exit": 0, "expect_stdout_re": "^4\\t0\\tdocs/README.md$" },
    { "run": "grep -n \"## Design Spikes\" docs/README.md", "expect_exit": 0, "expect_stdout_re": "^38:" },
    { "run": "grep -c \"spikes/tiered-cognition/\" docs/README.md", "expect_exit": 0, "expect_stdout_re": "^1$" }
  ],
  "report": { "format": "exec-brief/v1", "max_words": 200 }
}
```

```diff
--- a/docs/README.md
+++ b/docs/README.md
@@ -33,4 +33,8 @@
 ## Operational Guides
 
 - [PUBLISHING.md](PUBLISHING.md) — Release Aesop to npm using GitHub Actions with OIDC trusted publishing
 - [av-resilience.md](av-resilience.md) — Antivirus & behavioral-engine resilience patterns for reliable agent execution
+
+## Design Spikes
+
+- [spikes/tiered-cognition/](spikes/tiered-cognition/) — Wave-11 spike: tiered cognition/execution architecture (Haiku as sole I/O substrate; Sonnet/Opus/Fable cognition tiers emit structured work-orders)
```

### 4.2 The EXEC-BRIEF as received from the Haiku executor

Captured verbatim from a live general-purpose sub-dispatch (which the live
model policy landed on **Haiku**, as the architecture requires). Round-trip:
**33.9 s wall-clock, 33,932 subagent tokens, 6 tool uses**; the change was then
independently re-verified by the owner (`git diff --numstat` = `4 0
docs/README.md`, nothing else touched, em-dash bytes intact).

```json
{
  "kind": "exec-brief",
  "version": 1,
  "work_order_id": "wo-w11-readme-spikes-link",
  "status": "APPLIED",
  "steps": [
    { "step": "branch-check", "ok": true, "detail": "On spike/wave11-tiered-cognition" },
    { "step": "write-patch",  "ok": true, "detail": "Patch file written to scratchpad" },
    { "step": "apply-patch",  "ok": true, "detail": "git apply succeeded with exit 0" },
    { "step": "verify:1",     "ok": true, "detail": "diff --numstat: 4 additions, 0 deletions" },
    { "step": "verify:2",     "ok": true, "detail": "## Design Spikes found at line 38" },
    { "step": "verify:3",     "ok": true, "detail": "tiered-cognition reference count: 1" }
  ],
  "verify_results": [
    { "run": "git diff --numstat -- docs/README.md", "exit": 0, "stdout_tail": "4\t0\tdocs/README.md" },
    { "run": "grep -n '## Design Spikes' docs/README.md", "exit": 0, "stdout_tail": "38:## Design Spikes" },
    { "run": "grep -c 'spikes/tiered-cognition/' docs/README.md", "exit": 0, "stdout_tail": "1" }
  ],
  "verbatim_errors": [],
  "files_touched": ["docs/README.md"],
  "commit": null
}
```

## 5. Rollout sketch (wave 12 — only if GO)

1. Merge the tier policy into `force-haiku-subagents.mjs` (one decision point:
   route model → strip or keep tools) — eliminates the dual-`updatedInput`
   hazard of §2.1(4).
2. Install `aesop-cognition.md`; generate per-specialist cognition variants
   (`aesop-cognition-<specialist>.md`: specialist body + cognition tool
   allowlist) so the specialist system prompt survives stripping.
3. Add the Layer-2 backstop matcher to settings.json; decide the main-thread
   carve-out (read-only git allowlist vs. exempting the top-level session).
4. Teach `/buildsystem` dispatch prompts the WORK-ORDER/EXEC-BRIEF contract;
   add an `aesop-executor` Haiku agent definition embedding §3.3.
5. Verify transcript-sniff fidelity on real sidechain transcripts (the one
   mechanism this spike could not fully validate in-harness — see FINDINGS).
