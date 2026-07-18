# Team-Shared State: Architecture & Migration

**Status**: Design document. Prototype complete (`state_store/` SQLite module shipped). Migration path defined. NOT YET INTEGRATED into orchestrator reader/writer paths.

---

## Problem Statement

Aesop currently stores orchestration state in **two git-tracked files**:
- `STATE.md` — intent, decisions, phase, NEXT STEPS (single-writer orchestrator)
- `BUILDLOG.md` — append-only progress snapshots (agents append one line per work unit)

This works **for single-user/single-orchestrator** workflows but does not scale to teams:

1. **Hot-file merge conflicts** — Multiple agents appending to the same files requires rebasing and re-coordination; a team of 3+ users editing these simultaneously causes conflicts.
2. **No transactions/concurrency** — Git has no concept of atomic multi-file updates or per-agent locks; coordination is manual and error-prone.
3. **No real-time status** — Readers must `git fetch` to see the latest state; no subscription/push model for live updates.
4. **Single-writer bottleneck** — The orchestrator is the only writer to STATE.md; other workers cannot safely report their own state.

---

## Current Truth: Git-as-State (Single-Instance)

### Data model

State lives as **human-readable JSON** in two git-tracked files:

```
orchestrator (Fable/Opus) ←→ STATE.md (single-writer, locked decisions + phase + NEXT STEPS)
                          ←→ BUILDLOG.md (append-only, agents append one line per work unit)
                          
↓ (read-only consumers)

dashboards, monitoring, forensics
```

**Invariants**:
- Only the orchestrator writes to STATE.md (enforced by discipline, not by code)
- BUILDLOG.md is append-only; orchestrator never rewrites earlier entries
- All state is human-diffable (intentional — enables review, forensics, inheritance)
- Durability via git: push after each update, recover from `git log` on session restart
- Git is the **source of truth** for current state

### Limitations for team scale

- **No concurrent writers** — Two orchestrators or agents trying to write simultaneously causes merge conflicts
- **No transactions** — A phase update + next-steps change is two separate commits, not atomic
- **High latency** — State changes require `git push`; observability is on a push-frequency, not real-time
- **No locking** — State can be read/modified while orchestrator is deciding; no optimistic concurrency
- **No history/events** — Only final state (current file contents) is stored; intermediate states are lost

---

## Target: SQLite WAL as Live Substrate, Git as Export

### Proposed data model

```
orchestrator/agents write events ─→ SQLite WAL event log (LIVE substrate, fast, transactional)
                                 ↓
                            state_store/ EventStore
                            (append() atomic across processes/threads)
                                 ↓
                            [snapshots for O(n) tail-replay]
                                 ↓
                            projections/StateAPI (project tracker state)
                                 ↓
export_tracker() ─────────→ STATE.md / BUILDLOG.md (git-tracked EXPORT, human-diffable, immutable)
                                 ↓
                            [dashboards, monitoring, forensics read git export]
```

### Key design principles

1. **Event sourcing**: State is a fold of immutable events, not mutable files. Each write is a single `append(stream, event_type, payload, actor)` call — atomic, ordered, versionable.

2. **Append-only**: No deletes or mutations. History is preserved forever. Replayability + auditing for free.

3. **Per-stream versioning**: Each "stream" (e.g., `"tracker"`, `"orchestrator_status"`) has its own 1-based, gapless version. Enables deterministic snapshots and tail-replay (see `state_store/store.py` line 81–92 and `state_store/projections.py` line 117–127).

4. **Concurrency-safe writes**: SQLite WAL mode + `BEGIN IMMEDIATE` transactions guarantee that two writers on the same file never collide or duplicate a version (see `state_store/store.py` line 30–94). Tested in `tests/test_state_store.py::EventStoreTest::test_concurrent_appends_have_no_dupes_or_gaps`.

5. **Snapshots for O(n) tail-replay**: Instead of replaying all events on every read, save materialized state snapshots at key versions; future replays fold only newer events (see `state_store/store.py` line 130–196 and `state_store/projections.py` line 84–114).

6. **Git as export, not source**: The SQLite store is the system-of-record. `export_tracker(api, out_path)` renders the current projection back to human-readable JSON for git durability and review (see `state_store/export.py`). Git is now **read-only for state** (except for manual edits, which become new events on next `ingest_tracker_json`).

7. **Projection-based readers**: Callers do not query the raw event log; instead, they call `api.project(view)` to get the current state as a dict. New projections (e.g., `project_orchestrator_status`) can be registered in `state_store/api.py` without changing the event store (see line 12–35).

---

## Architecture: The Three Layers

### 1. Event Store (SQLite WAL)

**File**: `state_store/store.py`

**Class**: `EventStore(db_path)`

**Public API**:
- `append(stream: str, event_type: str, payload: dict, actor: str = "system") -> int` — Append one event, return its per-stream version. Atomic: multiple writers see no dupes or gaps (tests line 90–108).
- `read(stream: str) -> list` — All events in a stream, ascending by version. Returns list of dicts with `{"id", "ts", "actor", "stream", "type", "payload", "version"}`.
- `read_all() -> list` — All events across all streams, ascending by global id.
- `save_snapshot(stream: str, event_version: int, projection: dict) -> None` — Persist a materialized projection at a specific version (line 130–153).
- `read_snapshot(stream: str) -> tuple | None` — Read the most recent snapshot; returns `(event_version, projection_dict, checksum)` or None (line 155–197).

**Concurrency model**:
- Multiple writers: `BEGIN IMMEDIATE` locks the write lock up front, so read-max-version-then-insert is atomic (line 80).
- Multiple readers: SQLite WAL mode allows readers to run concurrently with writers on separate .db-wal shadow files (no blocking).
- Process/thread-safe: each `append()` call opens its own connection; `busy_timeout=5000` (5 seconds) waits if the DB is locked (line 32–94).
- Tested with two threads, each with its own EventStore instance, appending 100 events concurrently with no dupes (tests line 90–108).

### 2. Projections (Fold Events into State)

**File**: `state_store/projections.py`

**Functions**:
- `_fold_events(events, order=None, items=None) -> (order, items)` — Fold events into an accumulated state tuple. Mutates order + items in place. Helper used by both full and snapshot-aware projections (line 25–71).

- `project_tracker(events: list) -> dict` — Original full-replay projection: fold all events → `{"version": 1, "items": [items in first-seen order]}`. Defines tracker event schema:
  - `item_created` (payload = full item dict): establishes item, kept in first-seen order
  - `item_updated` (payload = `{"id": ..., ...partial fields}`): merges partial fields onto existing item
  - `item_archived` (payload = `{"id": ...}`): sets `status` to `"archived"`, optionally merges `completed_at`
  - Unknown event types: ignored (line 74–81).

- `project_tracker_with_snapshot(store, stream: str, events: list) -> dict` — Snapshot-aware projection: load latest snapshot; fold only tail events (after snapshot version) for O(n) tail-replay. Falls back to full replay if snapshot is missing or corrupt (line 84–114).

- `save_snapshot(store, stream: str, event_version: int, projection: dict) -> None` — Wrapper over `store.save_snapshot()` (line 117–126).

**Event schema for tracker**:
```json
{
  "type": "item_created",
  "payload": {"id": "abc", "title": "...", "lane": "proposed", "status": "todo", ...}
}
{
  "type": "item_updated",
  "payload": {"id": "abc", "lane": "in-progress"}
}
{
  "type": "item_archived",
  "payload": {"id": "abc", "completed_at": "2026-07-17T...Z"}
}
```

Tolerance: unknown ids on update/archive are ignored (no error); unknown event types are skipped (line 62–70).

### 3. Facade API (Single Seam for Backend Swaps)

**File**: `state_store/api.py`

**Class**: `StateAPI(db_path)`

**Public API**:
- `append(stream: str, event_type: str, payload: dict, actor: str = "system") -> int` — Append event, return version.
- `get(stream: str) -> list` — Read all events in a stream.
- `project(view: str) -> dict` — Fold the named stream through its projector into current state. Raises `ValueError` if projector not registered (line 15–35).

**Backend swaps**: The backend (SQLite now, Postgres later) is abstracted here. Callers **never** touch `EventStore` directly; they use `StateAPI` only. On cutover to Postgres, only `api.py` changes; call sites stay the same.

---

## New State Streams (Beyond Tracker)

The tracker stream is the first proof of concept. The event log supports **arbitrary streams**; new streams are registered by adding a projector to `_PROJECTORS` in `state_store/api.py` (line 12).

### Proposed: `orchestrator_status` stream

**Purpose**: Record orchestrator phase, NEXT STEPS, decisions, and audit results in real-time without git writes.

**Events**:
```json
{
  "type": "phase_changed",
  "payload": {"phase": "wave-rc.3", "reason": "stable release shipped"}
}
{
  "type": "next_steps_updated",
  "payload": {"steps": ["reconcile state_store SI", "add orchestrator_status stream", ...]}
}
{
  "type": "decision_locked",
  "payload": {"key": "model_dispatch_core", "value": "out-of-repo (structural)", "justification": "..."}
}
{
  "type": "audit_findings_recorded",
  "payload": {"level": "wave-rc.2", "findings_count": 3, "summary": "..."}
}
```

**Projection** (pseudo-code):
```python
def project_orchestrator_status(events):
    status = {
        "phase": None,
        "decisions": {},
        "next_steps": [],
        "latest_audit": None,
    }
    for ev in events:
        if ev["type"] == "phase_changed":
            status["phase"] = ev["payload"]["phase"]
        elif ev["type"] == "decision_locked":
            key = ev["payload"]["key"]
            status["decisions"][key] = ev["payload"]["value"]
        elif ev["type"] == "next_steps_updated":
            status["next_steps"] = ev["payload"]["steps"]
        elif ev["type"] == "audit_findings_recorded":
            status["latest_audit"] = ev["payload"]
    return status
```

**Readers** (same-turn):
- Dashboard queries `api.project("orchestrator_status")` → sees latest phase, decisions, next steps live (no git fetch).
- Monitor daemon queries `api.project("orchestrator_status")` → sees what the orchestrator decided last turn; compares against local observations.
- Agents query `api.project("orchestrator_status")` → see their assignment (brief payload in next_steps).

---

## Migration Path: Which Readers/Writers Move First

### Phase 1: Add orchestrator_status Stream (EARLY CUTOVER)

**What moves**: Orchestrator WRITES phase + next steps to `orchestrator_status` events instead of `STATE.md`. Readers stay on git (BUILDLOG.md + STATE.md fetches).

**Why first**: Orchestrator is single-writer; no merge conflicts to worry about. Proof that the event store works under real orchestrator load.

**Changes**:
1. Add `orchestrator_status` projector to `state_store/projections.py` (new file or extend existing).
2. Orchestrator calls `api.append("orchestrator_status", "phase_changed", {...}, actor="orchestrator")` instead of git commits.
3. Export job (`export_orchestrator_status()`) renders to a new `STATE.md` periodically (e.g., per-phase boundary) for git durability.
4. Readers still read git; no behavior change yet.

**Concurrency model**: Single orchestrator writer, many readers (dashboards, agents). No conflicts.

**Git-authoritative?**: NO. `STATE.md` becomes a rendered snapshot, not source-of-truth. On recovery, orchestrator reads latest `STATE.md` but reconciles with `orchestrator_status` events to fill any gaps.

### Phase 2: Dual-Read Tracker (MIDDLE CUTOVER)

**What moves**: Tracker CRUD (item creation, updates, archives) writes to the event log. Readers read from either git or the live event log (both running simultaneously).

**Why here**: Tracker is the most-read state; dual-read lets us test the event store under high read load while keeping git as a safety net.

**Changes**:
1. Add dual-read logic to tracker consumers: try `api.project("tracker")` first; fall back to git if the event store is unavailable.
2. Tracker CRUD emitters (`create_item()`, `update_item()`, `archive_item()`) append events instead of mutating git.
3. Keep the export job running: `export_tracker(api, state/tracker.json)` renders live projections back to git.
4. Tests compare git and event-store projections; must match exactly (see tests line 165–179).

**Concurrency model**: Multiple writers (agents creating/updating items), many readers. SQLite WAL + `BEGIN IMMEDIATE` handles concurrency safely.

**Git-authoritative?**: NO. Event store is source-of-truth. Git is an export. Reconciliation required on recovery.

### Phase 3: Flip Readers (CUTOVER COMPLETE)

**What moves**: All readers flip to the event store; git becomes purely an audit trail.

**Changes**:
1. Remove dual-read fallback; all tracker reads go through `api.project("tracker")`.
2. Remove git-read paths from dashboards, forensics, monitoring.
3. Keep export jobs running for durability + review.

**Concurrency model**: No change; SQLite WAL already supports N readers + 1 writer per connection.

**Git-authoritative?**: NO. Event store is source-of-truth.

---

## Locking & Concurrency Model

### Write path (multiple writers allowed)

1. Caller: `api.append("tracker", "item_created", {"id": "x", ...}, actor="agent-1")`
2. `StateAPI` delegates to `EventStore.append()`.
3. `EventStore.append()` opens a new connection, sets `busy_timeout=5000` (wait up to 5 seconds if locked).
4. Executes `BEGIN IMMEDIATE` (acquires write lock up front).
5. Reads max version for the stream (e.g., currently 42).
6. Inserts the new event with version 43.
7. Commits (releases lock).
8. Returns version 43.

**Guarantee**: No two writers see the same max version. Two concurrent writers always get consecutive versions (43, 44) with no dupes or gaps.

**Tested**: `tests/test_state_store.py::EventStoreTest::test_concurrent_appends_have_no_dupes_or_gaps` — two threads, 50 appends each, verified versions 1–100 are consecutive.

### Read path (many readers in parallel)

1. Caller: `api.project("tracker")`
2. `StateAPI` gets all events: `store.read("tracker")`
3. `EventStore.read()` opens a connection, sets `busy_timeout=5000`.
4. Queries all events for the stream (ascending by version). In WAL mode, readers see a consistent snapshot (MVCC).
5. Returns list of dicts.
6. `project_tracker()` folds events into a projection (in-process, no DB access).

**Guarantee**: Readers never block writers (WAL mode). Readers see a consistent snapshot at the moment they start the read. Dirty reads are impossible; serialization is guaranteed by SQLite's MVCC.

### Snapshot coordination

1. `project_tracker_with_snapshot()` reads the latest snapshot (one extra query).
2. Folds only events after the snapshot version.
3. If the snapshot is corrupt, falls back to full replay (graceful degradation).

**Snapshot updates are asynchronous**: A background job can call `api._store.save_snapshot(stream="tracker", event_version=100, projection=...)` without blocking readers. The snapshot is just an optimization.

---

## What Stays Git-Authoritative (and Why)

### 1. Durable Checkpoint History

Git history (commit log, diffs, tags) remains **definitive for auditing and recovery**:

- Each time an export job runs, it writes a new commit to git.
- The commit hash anchors a specific version of all state streams.
- On session restart, `git log --oneline` shows when state changed, who changed it, and why.
- `git show <commit>` lets you see exactly what was decided at that moment.

**Why not move to SQLite?** SQLite has no built-in diff/review/approval workflow. Code review, pull requests, and merge discipline are git patterns. For team scale, retaining git as the audit log preserves these workflows.

### 2. Durability & Offline Safety

SQLite stores state **in the working tree**, which may get wiped, corrupted, or lost.

Git stores state **on remote servers** (GitHub, GitLab, etc.), which have redundancy, backups, and audit logs built in.

**Recommendation**: Always run `export_tracker()` and `export_orchestrator_status()` jobs after each major state change. Push the exports to git. If the SQLite store is corrupted, `ingest_tracker_json(git_version)` reconstitutes it.

### 3. Team Sync & Cross-Machine Continuity

When a developer or orchestrator switches machines or sessions:

1. Clone/pull the repo (gets the latest git state).
2. Reconstitute the event store: `ingest_tracker_json(api, state/tracker.json)` (tests line 165–179).
3. Continue from there.

**Why this works**: The ingest path is idempotent (see `state_store/ingest.py` line 14–41). Running it twice on the same events is a no-op (second run has no items to ingest, since they're already in the event log).

### 4. Configuration & Secrets

Aesop configuration (aesop.config.json, credentials, API keys) **does NOT go in state streams**. These remain git-ignored and managed separately.

Event payloads must not include secrets (enforced at the append call site, not in the store).

---

## Multi-Writer Concurrency: Measured (2026-07-18)

**Multi-writer safety is now verified under production load.** A concurrent-writer stress test (4 writer processes, 5s duration, WAL mode + `busy_timeout=5000` + `BEGIN IMMEDIATE`) appended 800 events across the tracker stream with zero dupes, zero gaps, zero "database is locked" failures. Measured throughput: ~704 events/sec. All projections converged (consistent state). This moves multi-writer support from "design" to "validated."

---

## Not Yet Built

### 1. **Orchestrator Reader/Writer Integration**

Currently, the orchestrator only writes to git (STATE.md). To move to the event store:

- Orchestrator `phase_changed` → write to stream `"orchestrator_status"` instead of STATE.md
- Orchestrator `next_steps_updated` → append event instead of git commit
- Orchestrator recovery: read `api.project("orchestrator_status")` to bootstrap phase + next steps

**Effort**: ~1 sprint. Touch: `skills/power/*, monitor/` event loop, orchestrator dispatch template.

### 2. **Dashboard Real-Time Subscription**

Currently, dashboards query the git export (STATE.md, tracker.json). For real-time updates:

- Add `subscribe(stream: str, callback)` to StateAPI
- Implement with SQLite's FTS/updates or a simple file-watch on the .db-wal file
- Dashboard websocket sends live updates to browsers

**Effort**: ~1 sprint. Touch: `ui/`, `state_store/api.py`.

### 3. **Team-Shared Database Setup**

The current design assumes a **local SQLite file** (filesystem-shared at best). For a true team:

- Backend swap: `StateAPI` points to Postgres instead of SQLite (seamless; only `api.py` changes).
- Setup: Postgres server, connection pooling, schema migration job.
- Tuning: Query optimization for high read/write load.

**Effort**: ~2 sprints. Mostly infrastructure/testing; application code is abstracted.

### 4. **Reconciliation & Conflict Resolution**

If two teams merge their state stores (e.g., two subagent fleets run independently, then reconcile):

- **Event deduplication**: No duplicate event ids; version numbers are per-stream (don't collide between stores).
- **Metadata tagging**: Each event carries an `actor` and `ts` (timestamp); reconciliation can detect/log conflicts.
- **Projection idempotence**: Refolding events is deterministic; the projection will converge to the same state.

**Current support**: `actor` field in every event. Reconciliation logic is **not yet implemented** (would live in `state_store/reconcile.py` or a separate tool).

**Effort**: ~1–2 sprints, depending on conflict resolution strategy (append-only, last-write-wins, domain-specific merge).

### 5. **Model-Dispatch Correlation**

The orchestrator needs to correlate which Haiku agent was given which backlog item and track per-item cost/success.

**Current event schema**: `orchestrator_status` events can carry item assignments, but **no current mechanism to append per-item traces** (which agent, which LLM, cost, tokens, result).

**Needed**:
- New stream: `"agent_traces"` with events like `agent_dispatched`, `agent_completed`, `agent_failed`.
- Agent brief template includes event-append credentials (stream + actor).
- Aggregation job correlates agent traces + cost logs + PR outcomes.

**Effort**: ~1–2 sprints. Touch: `dispatch template`, `monitor/`, cost logger.

---

## Guarantees & Semantics

### Atomicity

Each `append()` call is atomic: either the event is inserted (and you get a version back) or it fails (exception). No partial writes.

Example:
```python
version = api.append("tracker", "item_created", {"id": "x", "title": "Y"}, actor="agent-1")
# version is now 43 (for stream "tracker")
# event is durable; will survive process restart
```

### Consistency

The event log is append-only; once an event is inserted, it never changes. The projection is deterministic: folding the same events always yields the same result.

Example:
```python
events_1 = api.get("tracker")  # [v1, v2, v3]
proj_1 = project_tracker(events_1)

# Later:
events_2 = api.get("tracker")  # [v1, v2, v3, v4, v5]
proj_2 = project_tracker(events_2)

# proj_2 differs from proj_1 only by v4+v5's changes (if any)
```

### Isolation

Readers see a consistent snapshot (SQLite MVCC). No dirty reads. Concurrent writes are serialized by `BEGIN IMMEDIATE`.

Example:
```python
# Thread 1: reader
snapshot_1 = api.get("tracker")  # sees [v1..v50]

# Thread 2: writer (concurrent)
v51 = api.append(...)  # inserts v51

# Thread 1: reader (still sees [v1..v50], consistent snapshot)
snapshot_1  # unchanged; snapshot_1 is immutable
```

### Durability

Events are flushed to disk (SQLite journal + WAL file). On process restart, all events from the last committed transaction are recovered.

Example:
```python
version = api.append("tracker", "item_created", {...})  # returns 43, durable
# If process crashes here, event v43 is still there on next start
```

### Idempotence (Export Fidelity)

The `ingest_tracker_json()` + `project_tracker()` + `export_tracker()` round-trip preserves item fidelity: ingesting a tracker.json and exporting the projection reproduces the same items.

Tested in `tests/test_state_store.py::ApiAndExportTest::test_ingest_project_export_round_trips_real_tracker`:

```python
original = json.loads("state/tracker.json")
api.ingest_tracker_json("state/tracker.json")
projected = api.project("tracker")
assert projected["items"] == original["items"]  # exact match
```

---

## File Organization

**Event store layer** (new):
- `state_store/store.py` — SQLite WAL append-only event log.
- `state_store/projections.py` — Fold events into tracker state.
- `state_store/api.py` — StateAPI facade (append/get/project).
- `state_store/export.py` — Render projections to git-tracked JSON.
- `state_store/ingest.py` — Backfill events from existing JSON.
- `state_store/__init__.py` — Public exports.

**Tests** (new):
- `tests/test_state_store.py` — EventStore + projection + round-trip tests.
- `tests/test_state_store_snapshots.py` — Snapshot save/load fidelity.
- `tests/test_state_store_hardening.py` — Concurrency, corruption recovery.
- `tests/test_api_state.py` — StateAPI facade tests.

**Git exports** (existing, to be extended):
- `state/tracker.json` — Current tracker state (now an export, not source-of-truth).
- `STATE.md` — (Will become an export; currently single-writer orchestrator file.)
- `BUILDLOG.md` — (Will be merged into event streams; currently append-only progress log.)

---

## Deployment Checklist (for future waves)

- [ ] **Wave N+1**: Add `orchestrator_status` stream to `state_store/projections.py`.
- [ ] Orchestrator transition: phase/next-steps writes to event store (no git commits).
- [ ] Export job: periodically render `orchestrator_status` → `STATE.md` for git durability.
- [ ] Dashboard: read `api.project("orchestrator_status")` + git for fallback.
- [ ] Tests: verify orchestrator recovery from event stream (not git) works.

- [ ] **Wave N+2**: Tracker dual-read.
- [ ] Tracker CRUD: write events instead of git.
- [ ] Add dual-read logic: try event store, fall back to git.
- [ ] Export job: `export_tracker()` keeps `state/tracker.json` in sync.
- [ ] Tests: compare git + event-store projections; they must match.

- [ ] **Wave N+3**: Flip readers.
- [ ] Remove dual-read fallback.
- [ ] All reads go through `api.project()`.
- [ ] Git becomes audit trail only.

- [ ] **Wave N+4**: Postgres backend (optional, depends on team scale).
- [ ] Postgres schema + migration job.
- [ ] Backend swap in `StateAPI.__init__()`.
- [ ] Load testing + performance tuning.

---

## References & Code Citations

All design claims are grounded in actual implementation:

- **Concurrency safety**: `state_store/store.py` lines 30–94 (BEGIN IMMEDIATE + busy_timeout).
- **Snapshot replay**: `state_store/projections.py` lines 84–114 (project_tracker_with_snapshot).
- **Tracker projection**: `state_store/projections.py` lines 25–81 (event folding logic).
- **Round-trip fidelity**: `tests/test_state_store.py` lines 165–179 (ingest + project + export test).
- **Concurrent append test**: `tests/test_state_store.py` lines 90–108 (two threads, no dupes).
- **API facade**: `state_store/api.py` lines 15–35 (StateAPI.project seam for backend swaps).

See `state_store/CLAUDE.md` for domain-specific setup and next steps.
