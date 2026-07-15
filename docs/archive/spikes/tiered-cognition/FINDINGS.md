# Tiered Cognition/Execution — Wave-11 Spike Findings

**Verdict: GO (conditional)** — mechanism is buildable with today's harness
primitives, the courier round-trip works with full fidelity on a real task,
and the prototype hook passes its self-test. Three conditions must be closed
in wave 12 before activation (below).

## What was proven

1. **Hook prototype works.** `strip-tools-hook.mjs --self-test`:
   **27/27 PASS** (Node v24.16.0). Covers: sonnet/opus/fable dispatches
   stripped via the `aesop-cognition` shim rewrite; haiku and
   haiku-frontmatter dispatches untouched; blank-model specialist resolution
   via agent-catalog frontmatter; escape token honored + audited to
   `state/TIER-POLICY-ESCAPES.log`; legacy `[[ALLOW-NON-HAIKU]]`
   grandfathered; fork pass-through; call-time deny of Write/Bash under a
   sonnet transcript with a redirect-to-work-order reason; allow under haiku;
   fail-open on malformed payloads and missing transcripts.
2. **Courier round-trip works end-to-end on a real change.** A cognition-
   authored WORK-ORDER (unified diff + 3 verify steps, DESIGN.md §4) was
   applied by a **live Haiku executor sub-dispatch** (the existing model
   policy routed it to Haiku with no special handling — the two policies
   compose). Result: `status: APPLIED`, all verifies green, byte-exact
   application (UTF-8 em-dashes and LF endings survived the
   prompt → Write → git-apply path), zero collateral edits, honest typed
   brief returned.
3. **`git apply` is a sufficient fidelity gate.** Because the executor applies
   the diff mechanically and the diff carries byte-exact context, any drift
   the courier introduces fails the apply loudly instead of corrupting the
   file. The verify list then provides positive evidence, not just absence of
   error.

## Round-trip overhead observed

| Metric | Value |
|---|---|
| Wall-clock, dispatch → EXEC-BRIEF | **33.9 s** |
| Executor tokens (Haiku) | 33,932 |
| Executor tool uses | 6 (branch check, patch write, apply, 3 verifies) |
| Cognition-side cost | authoring the work-order (one message) + reading a ~200-word brief |

Interpretation: ~30–60 s and a few-cent Haiku bill per coherent change-set is
acceptable **iff work-orders stay batched** (whole patch + command plan per
round trip). At line-by-line granularity the architecture would be unusable —
batching is a hard rule, not an optimization.

## Fidelity risks / what breaks (honest list)

1. **Hook composition (must fix before activation).** The live
   `force-haiku-subagents.mjs` and this hook both emit `updatedInput` on the
   same `Agent|Task` matcher; merge order is undefined. **Condition 1: merge
   tier policy into the model-policy hook as one file.** Not fixable by
   ordering config alone — one decision point is the correct design anyway.
2. **Layer-2 tier detection is transcript-sniffed and unverified in-harness.**
   The hook payload doesn't name the session model; the prototype infers it
   from `transcript_path` JSONL (`message.model` of the last assistant
   entry). This works on fixture transcripts, but sidechain/subagent
   transcript layout in the current harness build was NOT exercised live
   (this spike's session is escape-token-exempt, so a live negative test
   wasn't possible without wiring the hook in — out of spike scope).
   **Condition 2: validate the sniffer against real subagent transcripts
   before trusting Layer 2; treat Layer 1 as the primary control.**
3. **Specialist prompt loss under the shim rewrite.** Rewriting
   `subagent_type` → `aesop-cognition` drops the specialist's system prompt;
   the role survives only as a contract-header line. Cognition quality for
   typed specialists will degrade until per-specialist cognition variants are
   generated (DESIGN §5.2). **Condition 3 for full fleet rollout; not a
   blocker for a Fable/Opus-orchestrator-only first phase.**
4. **Main-thread carve-out undecided.** Uniform Layer-2 denial would break the
   orchestrator's legitimate short git one-liners. Needs a read-only Bash
   allowlist or a top-session exemption (DESIGN §2.3). Decide at rollout.
5. **Fail-open stance.** Every failure path passes (consistent with the model
   policy hook). A malformed transcript therefore silently disables Layer 2 —
   same shape as the known `proposals-lock fail-open` issue. Acceptable for a
   guardrail whose primary layer is dispatch-time, but worth a revisit when
   Layer 2 is trusted.
6. **Executor honesty is prompt-enforced, not mechanical.** The brief schema
   and "verbatim errors" rule live in the dispatch prompt. A lazy executor
   could still fabricate a green brief; mitigation is the existing
   owner-verifies rule (the owning tier re-runs/reads the cheap verify
   evidence, as done in this spike) plus `git apply`'s mechanical honesty.
7. **Escape-token smuggling** applies to `[[ALLOW-TIER-TOOLS]]` exactly as to
   the model policy's token: prompts are untrusted text. Same mitigation
   inherited: never silent, always audited to state log.

## GO / NO-GO

**GO** for wave-12 rollout, phased:

1. **Phase A (cheap, high value):** merge tier policy into
   `force-haiku-subagents.mjs` (Condition 1); install `aesop-cognition.md` +
   an `aesop-executor` Haiku agent def embedding the courier honesty rules;
   teach `/buildsystem` dispatch prompts the WORK-ORDER/EXEC-BRIEF schema.
   Apply stripping to **opus/fable dispatches only** first (no specialist
   prompt loss — Condition 3 deferred safely).
2. **Phase B:** generate per-specialist cognition variants; extend stripping
   to sonnet specialists; measure fix-item throughput vs. the current
   Sonnet-hands-on baseline for one wave before making it default.
3. **Phase C:** wire Layer-2 backstop after validating transcript sniffing on
   real sidechains (Condition 2) and deciding the main-thread carve-out.

Top risk if rolled out as-is without the conditions: **the dual-hook
`updatedInput` collision (risk 1)** — it could silently drop the model
rewrite or the tool strip depending on harness ordering, i.e. a policy hole
that looks green.

## Spike inventory (all inert)

- `docs/spikes/tiered-cognition/DESIGN.md` — mechanism + schemas + executed worked example
- `docs/spikes/tiered-cognition/strip-tools-hook.mjs` — prototype hook, self-test 27/27 PASS
- `docs/spikes/tiered-cognition/aesop-cognition.example.md` — shim agent def (NOT installed)
- `docs/README.md` — one real change, applied by the Haiku executor round-trip
- Nothing wired into `~/.claude/settings.json`, live hooks, or `/buildsystem`.
