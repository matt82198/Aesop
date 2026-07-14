# ACTIVATION runbook — force-model-policy.merged.mjs

Swap the staged merged hook in for the live model-policy hook. **Do not run
this casually** — the live hook governs every subagent dispatch in every
session. Perform the swap between waves, not mid-fleet.

Paths used below:

- LIVE hook: `C:\Users\matt8\.claude\hooks\force-haiku-subagents.mjs`
- STAGED file: `<aesop>\docs\spikes\tiered-cognition\force-model-policy.merged.mjs`
- Shim agent def: `<aesop>\docs\spikes\tiered-cognition\aesop-cognition.example.md`

## Phase A activation (recommended first step)

Default behavior after the swap: model policy identical to today, plus
opus/fable-frontmatter dispatches rewritten to the message-only
`aesop-cognition` shim. Sonnet specialists untouched (no prompt loss —
FINDINGS.md condition 3 deferred). Layer 2 stays dormant.

1. **Install the shim agent definition** (the merged hook rewrites cognition
   dispatches to `subagent_type: aesop-cognition`; without the definition
   those dispatches would fail):

   ```powershell
   Copy-Item <aesop>\docs\spikes\tiered-cognition\aesop-cognition.example.md `
             C:\Users\matt8\.claude\agents\aesop-cognition.md
   ```

   Then edit the copied file's `description:` to remove the "NOT INSTALLED"
   sentence. Keep `tools: Agent, SendMessage, TaskStop, Monitor` and do NOT
   add a `model:` line (the hook passes the effective model explicitly).

2. **Back up the live hook** (timestamped, same directory):

   ```powershell
   Copy-Item C:\Users\matt8\.claude\hooks\force-haiku-subagents.mjs `
             C:\Users\matt8\.claude\hooks\force-haiku-subagents.mjs.bak-$(Get-Date -Format yyyyMMdd-HHmmss)
   ```

3. **Verify the staged file before copying** (must print `SELF-TEST: ALL PASS`,
   exit 0):

   ```powershell
   node --check <aesop>\docs\spikes\tiered-cognition\force-model-policy.merged.mjs
   node <aesop>\docs\spikes\tiered-cognition\force-model-policy.merged.mjs --self-test
   ```

4. **Copy over the live hook, keeping the live FILENAME** so settings.json
   needs no edit:

   ```powershell
   Copy-Item <aesop>\docs\spikes\tiered-cognition\force-model-policy.merged.mjs `
             C:\Users\matt8\.claude\hooks\force-haiku-subagents.mjs -Force
   ```

5. **Verify the settings matcher is unchanged and correct.** In
   `C:\Users\matt8\.claude\settings.json` the `hooks.PreToolUse` entry with
   matcher `Agent|Task` must point at
   `~/.claude/hooks/force-haiku-subagents.mjs` (node command). Do NOT add any
   other hook on that matcher — this file must remain the ONLY `updatedInput`
   owner for `Agent|Task`; wiring a second rewriting hook there reintroduces
   the exact collision this merge exists to fix.

6. **Re-run the self-test on the installed copy** (proves the copy is intact):

   ```powershell
   node C:\Users\matt8\.claude\hooks\force-haiku-subagents.mjs --self-test
   ```

7. **Restart.** Claude Code snapshots hook config at session start — running
   sessions keep the old hook until restarted. Restart the orchestrator
   session and any long-lived fleet sessions/daemons that dispatch subagents.

8. **Smoke-check in a fresh session:** dispatch a generic Haiku agent (expect
   pass/route-to-haiku, no shim), a `bash-pro` (expect claude-sonnet-5, no
   shim), and — if any opus/fable-frontmatter agent def is installed — one of
   those (expect the `⛓ … tools stripped via 'aesop-cognition' shim` system
   message). Confirm escape uses append to
   `state/MODEL-POLICY-ESCAPES.log` / `state/TIER-POLICY-ESCAPES.log`.

## Phase B (later, deliberate)

Set `TIER_STRIP_SCOPE=all` in the environment Claude Code launches from to
extend the shim to sonnet specialists — ONLY after per-specialist cognition
variants exist (FINDINGS.md condition 3), otherwise specialist system prompts
are lost to the generic shim. `TIER_STRIP_SCOPE=off` reduces the hook to pure
live-hook model-policy behavior (useful as a soft rollback).

## Phase C — arming Layer 2 (call-time backstop; later, deliberate)

Dormant until BOTH of these are true:

1. `TIER_ENFORCE=1` in the environment.
2. settings.json gains a second `PreToolUse` entry running this same hook file
   with a matcher covering the denied tools, e.g.
   `Read|Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell|Glob|Grep|WebFetch|WebSearch|Skill|Artifact`.
   (That entry never emits `updatedInput` — deny/allow only — so the
   single-owner rule is preserved.)

Before arming: validate transcript sniffing on real sidechain transcripts and
decide the main-thread carve-out (FINDINGS.md condition 2 / risk 4).

## Rollback

1. Restore the newest backup:

   ```powershell
   Copy-Item C:\Users\matt8\.claude\hooks\force-haiku-subagents.mjs.bak-<TS> `
             C:\Users\matt8\.claude\hooks\force-haiku-subagents.mjs -Force
   ```

2. Optionally remove `C:\Users\matt8\.claude\agents\aesop-cognition.md`
   (harmless to leave installed; nothing routes to it without the merged hook).
3. Unset `TIER_ENFORCE` / `TIER_STRIP_SCOPE` if set; remove any Layer-2
   matcher added in Phase C.
4. Restart running sessions (same snapshot rule as step 7 above).

## Env knobs (merged hook)

| Var | Default | Effect |
|---|---|---|
| `FORCE_ALL_HAIKU=1` | off | Every dispatch → haiku (bash-pro excepted) — unchanged from live hook |
| `TIER_STRIP_SCOPE` | `opus-fable` | `opus-fable` (Phase A) / `all` (Phase B) / `off` (model policy only) |
| `TIER_ENFORCE=1` | off | Arms the Layer-2 call-time backstop (needs the Phase C matcher too) |
| `AESOP_ROOT` | `~/aesop` | Root for `state/*-ESCAPES.log` audit logs |
