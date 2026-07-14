# state_store/ — event-sourced state layer (DB source of truth, git as export)

**Purpose**: the durable substrate to move aesop's coordination/state off git —
which cannot scale to a team (single-writer control files, hot-file merge
conflicts, no transactions/concurrency/real-time). State becomes an append-only
event log with per-stream versioning; current state is a projection; git is
demoted to a rendered, diffable **export**.

**Status (2026-07-14)**: additive prototype. The live `ui/` tracker path
(`collectors.py` → `state/tracker.json`) is UNCHANGED. This package ships the
store + tracker projection + backfill + export, ready for a later dual-read
cutover. Design: `conductor3 plans/aesop-scaling-rearchitecture.md`.

## Files (stdlib only — sqlite3/json/threading/time)
- **store.py** — `EventStore(db_path)`: append-only SQLite (WAL) log.
  Concurrency-safe across threads and processes via `busy_timeout` +
  `BEGIN IMMEDIATE` (atomic read-max-version-then-insert). `append/read/read_all`.
- **projections.py** — `project_tracker(events)`: folds `item_created` /
  `item_updated` / `item_archived` into the full `tracker.json` shape,
  preserving first-seen order.
- **api.py** — `StateAPI(db_path)`: the swap seam (`append`/`get`/`project`).
  Backend swaps SQLite→Postgres here without touching callers.
- **export.py** — `export_tracker(api, out_path)`: render the projection back to
  a git-tracked JSON snapshot (indent=2, ascii-escaped to match the live file).
- **ingest.py** — `ingest_tracker_json(api, path)`: backfill one `item_created`
  per existing item (the migration/backfill path).

## Invariants
- **Append-only**: never mutate/delete events; state changes are new events.
- **Per-stream version is 1-based and gapless** (enforced atomically).
- **git as export, not source**: nothing here reads git for state.
- **Round-trip fidelity**: ingest → project → export reproduces the same items
  (tested against the real `state/tracker.json`).

## Next (cutover, follow-up — NOT this increment)
Point tracker CRUD at `StateAPI` (create→`item_created`, update→`item_updated`,
move→lane update, delete→`item_archived`); add a `subscribe()` real-time path to
replace the SSE file-watch; run the `export_tracker` job to keep `tracker.json`
rendered during dual-read; then flip readers to the API.
