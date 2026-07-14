# Reliability & Core Obligations

**TL;DR**: Three rules for shipping production work: (1) orchestrator never idles (spawn next task while agents run), (2) every action produces observable output (silence = failure), (3) pride bar — verify end-to-end before marking done. Together: reliable, visible, trustworthy automation.

---

## NEVER WAIT: Keep the orchestrator busy

The orchestrator must never go idle while background work is in flight. Every moment waiting on agents or builds is spent producing forward progress:

- Dispatch the next unblocked work unit
- Extend planning documentation (roadmaps, next phases)
- Stage ideas and observations to memory
- Queue important facts via the inbox pattern
- Always offer the user an actionable idea for what to do next

**Key principle**: "Waiting on X" is never a complete status — it must come with "meanwhile, doing/proposing Y." Never burn cycles re-reading state that scoped agents will report anyway.

## Inputs ALWAYS produce outputs

Every dispatched agent, loop cycle, tool run, and workflow MUST emit an observable output:
- A brief summary
- A log line
- A heartbeat signal
- Or an explicit `FAILED` or `EMPTY` marker

**Silence is never acceptable.** No output = failure, and the watchdog treats it as a hang. Never swallow a result; never let a task end without reporting something.

## The pride bar: never ship until you would be proud to deliver it

"An agent returned a brief" and "tests pass" are checkpoints, not completion.

**Done means:**
- Verified end-to-end (not just isolated tests)
- Briefs cross-checked against reality
- Test artifacts cleaned up
- Loose ends closed or explicitly logged as pending decisions
- Nothing known-broken shipped silently

If you would hesitate to hand it over under your own name, it is not done — keep going. Shipping something you're not proud of erodes team trust and creates technical debt that costs more to fix later.

## Why these matter

**Cache persistence.** Consistent outputs and reliable checkpoints mean the prompt cache stays warm and effective. Broken shortcuts kill cache hit rates and waste tokens.

**Team trust.** Silence erodes confidence in agent-driven work. Observable outputs, explicit failures, and the pride bar rebuild and maintain trust.

**Cost containment.** Retries, debug loops, and rollbacks all cost tokens. Getting it right the first time (through upfront verification and deliberate finishing) is cheaper than fixing broken work later.

## Implementation checklist

- Daemons emit heartbeats every cycle (even on error)
- Logs are append-only; every action logged with timestamp
- If a subagent stalls >200s, watchdog respawns it
- Orchestrator briefs the user with findings while delegating to subagents (never idle)
- Before marking work done, verify end-to-end and cross-check briefs against reality
- On task completion, ask: "Would I be proud to deliver this under my name?"

---

These three principles together form the **reliability core**: keep working (never wait), always report (inputs → outputs), and never compromise on quality (pride bar). They enable scaling from 1 orchestrator to dozens of parallel subagents without losing control, visibility, or production readiness.
