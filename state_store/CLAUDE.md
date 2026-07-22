# state_store/ — event-sourced state layer (SQLite WAL, projections, git-as-export)

## Universal rules (every domain)
- Feature branch only, never main; every push gated by `python tools/secret_scan.py --staged` exit 0.
- Tests never pollute cwd or global git config; temp dirs only; dummy secrets are runtime-concatenated, never literal.
- In worktrees use ABSOLUTE paths under the worktree for every write.
- Domain docs stay minimal-but-complete; update this file in the same PR as code it describes.

## Purpose & Status
Durable substrate moving aesop's coordination/state off git (which cannot scale to a team due to single-writer control files, hot-file merge conflicts, no transactions/concurrency). State becomes an append-only event log with per-stream versioning; current state is a projection; git is demoted to a rendered, diffable **export**. Status (2026-07-14): additive prototype. The live `ui/` tracker path is UNCHANGED. Full architecture & migration design: `docs/TEAM-STATE.md`.

## API Surface (state_store.api.StateAPI)
**Facade over EventStore + projections; swap backend (SQLite→Postgres) here without touching callers.**
- `append(stream, event_type, payload, actor="system", expected_version=None) → int`: Append one event; return its new per-stream version. **OCC support (Phase 2)**: if `expected_version` is provided, the append succeeds ONLY if the stream's current max version equals `expected_version`; otherwise raises `ConcurrencyConflict` WITHOUT writing (fail-closed, atomic). Enables writers to serialize reads: "I read version N; I will append only if it's still N when I try."
- `get(stream) → list`: Return all events in ``stream`` ascending by version.
- `project(view) → dict`: Fold the same-named stream through its projector into current state. Registered views: "tracker" (via `project_tracker`).
- **Exceptions:** `ConcurrencyConflict(expected_version, actual_version)` — raised by `append()` when OCC check fails; carries both versions so caller can rebase and retry.

## Concurrency Model & Measured Safety
**Multi-writer safe via SQLite WAL + atomicity:**
- `PRAGMA journal_mode=WAL` — many readers; serialized writers via write lock.
- `PRAGMA busy_timeout=5000` — retry for 5s on contention before erroring.
- `BEGIN IMMEDIATE` in `append()` — atomic read-max-version-then-insert; two writers never collide or duplicate a version.
- **Measured safety (2026-07-18 spike):** 4 concurrent writers, 800 events each (800/800), 0 lock errors, ~704 events/sec throughput.

**Optimistic Concurrency Control (Phase 2, 2026-07-21):**
- `append(..., expected_version=N)` — writer asserts "stream is at version N"; append succeeds only if true.
- **Atomicity:** The version check and append both happen under `BEGIN IMMEDIATE`, so no TOCTOU window.
- **Failure mode:** On version mismatch, raises `ConcurrencyConflict(expected, actual)` WITHOUT writing any event (fail-closed).
- **Retry protocol:** Caller re-reads the stream, extracts the new version from `ConcurrencyConflict.actual_version` or re-count events, and retries `append(..., expected_version=new_version)`.
- **Backward compatible:** `expected_version=None` (default) disables OCC; old code remains unchanged and unaffected.
- **Use case:** Multiple orchestrators coordinating on multi-instance state (e.g., distributed tracing, multi-writer audit log) can use OCC to prevent lost updates when racing to extend the same stream.

## Module Layout
- **read_api.py** — `ReadAPI` facade over state surfaces; read-only. Delegates to existing parsers: tracker snapshot, orchestrator status, heartbeat freshness via `tools/common`, ledger rows via `tools/fleet_ledger`. Never forks logic.
- **write_api.py** — `WriteAPI(state_dir)` facade for tracker mutations (WS4b: state consolidation write path). Exposes three operations: `tracker_update_status(item_id, new_status, note)`, `tracker_append_item(item_dict)`, and `rebuild_projection(force=False)`. 
  - **tracker_* methods**: Both append events atomically AND update tracker.json projection (tempfile + os.replace). Fail-closed: event append failure blocks projection write.
  - **OCC (Optimistic Concurrency Control)**: Each instance tracks the last hash it wrote. Before atomic write, detects concurrent modification: if on-disk hash differs from BOTH start-of-operation hash AND computed projection hash, raises `WriteConflict` (fail-closed). Corrupt JSON on disk also raises `WriteConflict` (fail-closed, not fail-open). Baseline hash captured at operation START (before event append) so the check window covers the entire operation.
  - **ID collision detection**: `tracker_append_item` with explicit id rejects duplicates (raises `ValueError` before appending) to prevent duplicate events for the same logical item.
  - **Self-healing recovery**: `rebuild_projection(force=True)` force-renders from the event store, bypassing OCC, to recover orphaned events (event in store, missing from projection). Recovery contract: projection is derived from event store, so rebuilding naturally recovers prior events.
- **store.py** — `EventStore(db_path)`: append-only SQLite log. `append(stream, type, payload, actor, expected_version=None)` returns new version or raises `ConcurrencyConflict` on OCC mismatch; `read(stream)` / `read_all()` return event rows. Corrupt JSON payloads are skipped with stderr log; snapshot read/write for tail-replay optimization.
- **__init__.py** — Public exports: `EventStore`, `StateAPI`, `ConcurrencyConflict`, `project_tracker`, `export_tracker`, `ingest_tracker_json`.
- **projections.py** — `project_tracker(events)`: folds `item_created` / `item_updated` / `item_archived` into the full `tracker.json` shape, preserving first-seen order.
- **api.py** — `StateAPI(db_path)`: the swap seam. Callers use this only; backend implementation hidden. Passes through OCC support transparently.
- **export.py** — `export_tracker(api, out_path)`: render the projection back to a git-tracked JSON snapshot (indent=2, ascii-escaped to match the live file).
- **ingest.py** — `ingest_tracker_json(api, path)`: backfill one `item_created` per existing item; validates event structure at boundary.
- **identity.py** — Multi-instance identity: `InstanceID(hostname, pid, nonce)` uniquely tags each Aesop process. Enables distributed leasing and fault detection.
- **coordination.py** — Lease-by-append claims for multi-writer coordination: `claim_lease(stream, actor)` / `release_lease(stream, actor)` via fail-closed event appends. Prevents concurrent orchestrators from colliding.

## Invariants
- **Append-only**: never mutate/delete events; state changes are new events.
- **Per-stream version is 1-based and gapless** (enforced atomically).
- **git as export, not source**: nothing here reads git for state.
- **Round-trip fidelity**: ingest → project → export reproduces the same items (tested against the real `state/tracker.json`).

## CI Isolation & Concurrency Gotcha
**SQLite tests deadlock under parallel CI shards** (false positive; no code defect). When running the unittest suite under parallel CI shards, multiple test files may contend on filesystem-level WAL locks. **Solution:** Use `_retry_on_db_lock(func, max_retries=3, delay=0.1)` wrapper for DB initialization and appends; apply exponential backoff. Real fix = per-shard DB isolation (future work). On CI re-run, the shard passes.

## Test Commands
Run from repo root:
- `python -m unittest tests.test_state_store` — Core API, concurrency, round-trip tests.
- `python -m unittest tests.test_state_store_occ` — OCC multi-process tests (Phase 2): exactly-one-succeeds, no-write-on-conflict, retry-convergence, backward-compat.
- `python -m unittest tests.test_state_store_concurrency` — Phase 1 multi-process coordination tests (claims, leases).
- `python -m unittest tests.test_state_store_hardening` — Corrupt event handling, input validation.
- `python -m unittest tests.test_state_store_snapshots` — Snapshot read/write and tail-replay.
- `npm run test:py` — All Python test suites (includes state_store).

## Agent Lifecycle Events (Wave-29)

**New event types** (additive, appended by UI collectors on agent phase changes):
- `agent_dispatched` — payload `{agent_id, timestamp}` — marks agent dispatch start
- `agent_working` — payload `{agent_id, timestamp}` — marks work in progress (thinking/tool-use)
- `agent_done` — payload `{agent_id, timestamp}` — marks completion
- `agent_stalled` — payload `{agent_id, timestamp}` — marks stall/error detected

**Projection**: `project_agent_lifecycle(events)` folds these into per-agent lifecycle state with transition history (state + timestamp). Enables Activity view to show agents entering/leaving states over time.

## Next (cutover, follow-up — NOT this increment)
**Phase 1 (early)**: Add `orchestrator_status` stream (orchestrator_status → `append("orchestrator_status", "phase_changed", ...)`, read from `project("orchestrator_status")` on recovery).
**Phase 2 (middle)**: Tracker dual-read (StateAPI for CRUD, export job keeps `tracker.json` rendered).
**Phase 3 (cutover complete)**: Flip all readers to API; remove git fallback.
**Phase 4 (optional, team scale)**: Postgres backend swap (no change to call sites).

Map of all domains: /CLAUDE.md
