# Durable Checkpointing & State Management

For any long-running or multi-agent effort, maintain authoritative handoff files that survive context loss, wipes, and session interruptions. This guide covers the STATE.md / BUILDLOG.md lifecycle and recovery patterns.

## STATE.md: Authoritative intent & decisions

**Purpose**: Single source of truth for current intent, locked decisions, data model/contracts, key file paths, current phase, and explicit NEXT STEPS.

**Structure**:
- What we're trying to build (intent, not mechanism)
- Locked decisions (technology choices, data models, architecture trade-offs)
- Current phase (e.g., "Phase 2: API integration")
- Explicit NEXT STEPS (enumerated, actionable, owner assigned)
- Key paths (file locations, service boundaries, data contracts)

**Discipline**: Hand-update STATE.md at phase boundaries. Never leave it stale; always update BEFORE moving to the next phase. An out-of-date STATE.md is worse than no STATE.md (it's actively misleading).

**Recovery use case**: If context is lost or a session is interrupted, STATE.md is the first file to read. It answers "where were we?" and "what's next?" without re-reading logs or transcripts.

## BUILDLOG.md: Append-only progress snapshots

**Purpose**: Timestamped, immutable record of progress. Never overwrite or edit earlier entries (append-only discipline).

**Pattern**: Each entry contains:
- Timestamp (ISO 8601 or human-readable)
- Work completed (features, bugs, integrations, tests)
- Status (green / yellow / blocked / pending decision)
- Next step or blocker (for orchestrator reference)

**Example**:
```
[2026-07-11 13:00] Phase 1 complete: scaffolding + unit tests passing
[2026-07-11 14:30] API integration: 2 endpoints done, 1 blocked on schema review
[2026-07-11 15:45] BLOCKED: waiting for design review on request body format
[2026-07-11 16:20] Design approved; resume API endpoint 3 implementation
```

**Append-only rule**: Agents and loops append one line per work unit. The orchestrator never edits earlier entries. This prevents accidental data loss and keeps the log auditable.

## Recovery workflow: On context loss or resume

When you resume work (context wipe, new session, task restart), follow this protocol:

1. **Read STATE.md**: Understand intent, locked decisions, and current phase
2. **Skim BUILDLOG.md**: Review recent progress and current blockers
3. **Run git log**: Verify actual file state and recent commits vs. STATE.md
4. **Sync**: If STATE.md is stale, update it before proceeding; if reality diverged from STATE.md, note the delta and surface it

**Never invent state.** Verify everything from disk (git log, file timestamps, handoff files) before trusting in-memory recollection. Disk is the source of truth.

## Dated archive strategy: Log rotation

When BUILDLOG.md grows beyond **~200 lines or ~20 KB**:

1. Identify the cut point (e.g., last entry from yesterday or the last "green" state marker)
2. Move older entries to `BUILDLOG-YYYY-MM.md` (dated archive)
3. Keep only recent entries in the live `BUILDLOG.md`
4. Commit both files
5. Update any orchestrator references to point to the live file

**Why rotation?** The orchestrator reads the live BUILDLOG.md frequently; a 50-line log is faster and cheaper than 500 lines. Full history remains available in archives for auditing and debugging.

**Example**:
- Live file: `BUILDLOG.md` (entries from 2026-07-08 onward)
- Archive: `BUILDLOG-2026-07.md` (entries through 2026-07-07)

## Handoff metadata across team boundaries

When handing off work to another team member or agent:

- Include the git commit hash (anchors history)
- Snapshot key file paths and their state
- Document any external dependencies or waiting states
- List any environment assumptions (database schema versions, external service versions, etc.)

Example:
```
[2026-07-12 09:00] Handing off to feature-team: commit abc1234
  - Database schema: v3.2 (see db/migrations/)
  - API contracts frozen in openapi.yaml
  - Waiting for design review on component layout
  - Next: implement sign-up form based on design feedback
```

## Multi-session coordination

For work spanning multiple people or sessions:

1. **Orchestrator updates STATE.md** after each major decision or phase change
2. **Subagents append to BUILDLOG.md** after each work unit
3. **On session resume**, orchestrator syncs from disk and briefs the incoming worker
4. **Hand-updates to STATE.md** happen only at phase boundaries (not every commit)

This keeps overhead low (one STATE.md update per phase, one BUILDLOG line per work unit) while preserving a clear audit trail.

---

**Why STATE.md + BUILDLOG.md?** They ensure work survives context loss, enables rapid resume without re-reading history, and provides an audit trail for debugging. Together with git history and the heartbeat protocol, they form the **checkpointing core** that makes orchestration systems reliable and recoverable.
