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
- `append(stream, event_type, payload, actor="system") → int`: Append one event; return its new per-stream version.
- `get(stream) → list`: Return all events in ``stream`` ascending by version.
- `project(view) → dict`: Fold the same-named stream through its projector into current state. Registered views: "tracker" (via `project_tracker`).

## Concurrency Model & Measured Safety
**Multi-writer safe via SQLite WAL + atomicity:**
- `PRAGMA journal_mode=WAL` — many readers; serialized writers via write lock.
- `PRAGMA busy_timeout=5000` — retry for 5s on contention before erroring.
- `BEGIN IMMEDIATE` in `append()` — atomic read-max-version-then-insert; two writers never collide or duplicate a version.
- **Measured safety (2026-07-18 spike):** 4 concurrent writers, 800 events each (800/800), 0 lock errors, ~704 events/sec throughput.

## Module Layout
- **store.py** — `EventStore(db_path)`: append-only SQLite log. `append(stream, type, payload, actor)` returns new version; `read(stream)` / `read_all()` return event rows. Corrupt JSON payloads are skipped with stderr log; snapshot read/write for tail-replay optimization.
- **projections.py** — `project_tracker(events)`: folds `item_created` / `item_updated` / `item_archived` into the full `tracker.json` shape, preserving first-seen order.
- **api.py** — `StateAPI(db_path)`: the swap seam. Callers use this only; backend implementation hidden.
- **export.py** — `export_tracker(api, out_path)`: render the projection back to a git-tracked JSON snapshot (indent=2, ascii-escaped to match the live file).
- **ingest.py** — `ingest_tracker_json(api, path)`: backfill one `item_created` per existing item; validates event structure at boundary.

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
- `python -m unittest tests.test_state_store_hardening` — Corrupt event handling, input validation.
- `python -m unittest tests.test_state_store_snapshots` — Snapshot read/write and tail-replay.
- `npm run test:py` — All Python test suites (includes state_store).

## Next (cutover, follow-up — NOT this increment)
**Phase 1 (early)**: Add `orchestrator_status` stream (orchestrator_status → `append("orchestrator_status", "phase_changed", ...)`, read from `project("orchestrator_status")` on recovery).
**Phase 2 (middle)**: Tracker dual-read (StateAPI for CRUD, export job keeps `tracker.json` rendered).
**Phase 3 (cutover complete)**: Flip all readers to API; remove git fallback.
**Phase 4 (optional, team scale)**: Postgres backend swap (no change to call sites).

Map of all domains: /CLAUDE.md
