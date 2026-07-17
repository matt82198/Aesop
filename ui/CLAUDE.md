# ui/ — Web dashboard

**Purpose**: Stdlib-only local observability dashboard. Serves a dark-theme HTML dashboard on a configurable port (realtime via Server-Sent Events), enabling real-time fleet monitoring without external dependencies.

## Files (wave-14 U9 cutover: new React+Vite app structure)

**Backend (Python, unchanged from wave-9 split)**:
- **serve.py** — Thin (~65-line) entry point + composition layer. Wires the sibling modules, calls `config.reload()` / `csrf.init()` / `sse.reset_state()`, and re-exports their symbols so `serve.X` keeps resolving for the test suite (which loads serve.py by path) and for `python ui/serve.py`.
- **config.py** — Path / env / `aesop.config.json` resolution. `reload()` recomputes all path globals from the current environment. **Load-bearing rule: every other module reads `config.X` at call time (`import config`), never `from config import <path>` — a frozen import would go stale after reload() (breaks test-fixture isolation).** Added in wave-14: `WEB_DIST` path pointing to `ui/web/dist/`.
- **csrf.py** — Session-token generation (atomic O_EXCL 0600) + `validate_csrf_request()`; `init()` sets `SESSION_TOKEN`.
- **collectors.py** — Read-only data collectors (heartbeats, repos, events, alerts, messages, backlog parse), tracker CRUD, and SSE section snapshots (incl. `read`-style tracker/orchestrator-status snapshots + inbox drain).
- **agents.py** — Agent transcript reading (`get_fleet_agents`, `extract_agent_dispatch_prompt`) and path-traversal-safe agent-id handling (`_AGENT_ID_FORBIDDEN`).
- **sse.py** — SSE client registry, bounded broadcast, hash-gated `_maybe_emit`, and the background `collector_loop`. `reset_state()` restores per-import collector isolation (the `sse` module is cached across test re-imports). Extended in wave-14: emits "cost" as a 6th SSE section.
- **render.py** — Renders `ui/web/dist/index.html` (wave-14 U9 cutover: no fallback), substituting the CSRF token via a unique sentinel (the sentinel persists through Vite's build). Requires `template_path` parameter; legacy fallback removed.
- **handler.py** — `DashboardHandler` (HTTP routing + all GET/POST endpoints incl. /api/tracker) and `run_server()`. Wave-14 additions: static serving (`GET /assets/*` from `ui/web/dist/assets/`), `/api/state` consolidated snapshot, `/api/session` for Vite dev server, `/api/cost` scorecard. Reads `config.X` / `csrf.SESSION_TOKEN` at call time.
- **cost.py** — Parser for `state/ledger/OUTCOMES-LEDGER.md` (markdown table); returns per-model and per-day aggregates, verdict scorecards, and optional dollar estimates (only if `aesop.config.json` supplies `pricing` map).
- **wave_prs.py** — Wave PR board collector: `get_wave_prs()` gathers open PRs (`gh pr list`) + PR-less `feat/*` branches (`git for-each-ref`), rolls check runs into passing/failing/pending/none, derives the top blocker, caches ~5s. Read-only; subprocess reads use `encoding='utf-8', errors='replace'`; degrades to `{available:false, error}` when gh is missing/un-authed. `AESOP_GH_BIN` overrides the gh binary.

## State Store Integration (Wave-15)

The tracker uses a **dual-path mutation model** backed by an event-sourced SQLite WAL store:

- **Write path**: Mutations append events to `tracker_events.db` (WAL mode) via the StateAPI layer (`state_store/api.py`). Each mutation (create/update/delete) produces an immutable event in the event log.
- **Read path**: `tracker.json` is re-rendered as an export (projection) from the event log on every read. This export is committed to git for checkpoint durability.
- **Location**: `state/tracker_events.db` (SQLite WAL, never committed). `tracker.json` (rendered export, committed).
- **Render-failure recovery**: If projection rendering fails, the UI falls back to the last-known good `tracker.json`; no data loss. Stale renders are repaired on the next successful mutation (idempotent re-render).

This design provides:
- **Durable event audit trail** (append-only events in WAL)
- **Git-friendly checkpoints** (rendered tracker.json snapshots)
- **Atomic mutations** (events append, projection re-renders)
- **Graceful degradation** (fallback to last-known-good on render failure)

**Frontend (React 18 + Vite + TypeScript, wave-14 U1–U8)**:
- **ui/web/** — Complete React application (TypeScript, Vite, TypeScript strict mode).
  - **src/main.tsx** — Vite entry point; renders `<App />` to `#root`.
  - **src/App.tsx** — App shell: header + hash-routed view slots (/#/, /#/work, /#/activity, /#/cost).
  - **src/styles/tokens.css** + **src/styles/global.css** — Design tokens (light/dark color palettes, spacing, typography) + base resets.
  - **src/views/** — Page-level components (Overview, Work, Activity, Cost) with SSE bindings.
  - **src/components/** — Reusable UI components (HealthHeader, AgentsPanel, TrackerBoard, Timeline, CostChart, etc.).
  - **src/lib/api.ts** — Typed fetch helpers + CSRF header injection + `/api/session` fallback for dev server.
  - **src/lib/useSSE.ts** — EventSource hook with reconnect logic, per-section state, connection status.
  - **src/lib/types.ts** — TypeScript types for all API payloads (contract with backend).
  - **src/lib/sanitizeUrl.ts** — XSS-safe URL parsing (PR links inert on bad schemes).
  - **vite.config.ts** — Vite config with API proxy for `/data`, `/api`, `/events`, `/agent`, `/submit` to :8770.
  - **dist/** — Built static files (committed to git; served by Python handler). Filenames are content-hashed by Vite.
- **README.md** — User guide and configuration reference (updated for wave-14).

## Configuration & Path Precedence

Configuration is resolved in this order (first match wins):

1. **Environment variables** (highest priority):
   - `PORT` — HTTP server port (default: 8770)
   - `AESOP_ROOT` — aesop installation root (default: `$HOME/aesop`)
   - `AESOP_STATE_ROOT` — state directory (overrides config state_root)
   - `AESOP_TRANSCRIPTS_ROOT` — Claude transcript directory (overrides config transcripts_root)
   - `AESOP_UI_COLLECT_INTERVAL` — collector thread poll cadence in seconds (default: 1.0)

2. **Config file** (`aesop.config.json`):
   - `state_root` — path to state/ directory
   - `transcripts_root` — path to Claude transcript directory

3. **Built-in defaults** (lowest priority):
   - `AESOP_ROOT/state` for state directory
   - `~/.claude/projects` for transcripts

## CSRF & Session Protection

**Token model**:
- Per-session CSRF token generated at startup, persisted to `state/.ui-session-token` (mode 0600, readable only by owner)
- Token is 43-character URL-safe base64 string (256 bits)
- Persistent across server restarts (read from file if exists, generate fresh if not)
- Used to validate mutations via /submit endpoint

**Validation on /submit POST**:
1. **Origin/Referer check**: if present, must be local (http://127.0.0.1:<port>, http://localhost:<port>, or http://[::1]:<port>)
2. **X-Aesop-Token header check**: must match SESSION_TOKEN exactly
- Both checks fail-closed (missing header = rejection)
- GET /events (SSE, read-only) requires no token

**Local CLI access**:
- CLI tools read token from `state/.ui-session-token` (0600) to submit to /submit endpoint
- Legitimate browser clients: token injected into HTML template, sent by JavaScript

## API Endpoints (wave-14 wave additions)

**Read-only (no CSRF required)**:
- `GET /` — Renders `ui/web/dist/index.html` with CSRF token substituted (hard 500 if dist missing).
- `GET /assets/*` — Static files from `ui/web/dist/assets/` (content-hashed, immutable cache headers, path-traversal-safe).
- `GET /api/state` — Consolidated first-paint snapshot: `{data, backlog, agents, tracker, status, cost}` in one round trip (reuses latest snapshots).
- `GET /api/session` — Returns `{token}` for Vite dev server; Origin-checked fail-closed (only local origins).
- `GET /api/cost` — Cost/scorecard summary from `state/ledger/OUTCOMES-LEDGER.md` (per-model, per-day, verdicts, optional pricing estimates).
- `GET /api/wave/prs` — Wave PR board: open PRs (`gh pr list`) + PR-less `feat/*` branches (`git for-each-ref`), each with CI rollup / mergeable / age / top blocker. Cached ~5s; degrades to `{available:false, error}` when gh is missing/un-authenticated (never a 500). `wave_prs.py` collector; polled by the frontend (not an SSE section — `gh` is too slow for the collector tick). Set `AESOP_GH_BIN` to override the gh binary path.
- `GET /events` — Server-Sent Events stream (read-only, no CSRF).

**Mutations (CSRF-gated)**:
- `POST /submit` — Append to inbox.
- `POST /api/tracker`, `POST /api/tracker/<id>` — Tracker CRUD.

## Server-Sent Events (SSE) Model

**Realtime streaming via GET /events**:
- ThreadingHTTPServer required (SSE holds one connection per client)
- Streams JSON frames: `event: <section>` / `data: <json>`
- Keepalive comment-line (`: keepalive`) sent every ~15s to prevent timeout
- Read-only stream; no mutations

**Sections emitted** (only on content change, in order):
1. **data** — heartbeat status, daemon state, log tail
2. **backlog** — AUDIT-BACKLOG.md parsed into tier buckets (P0/P1/P2/Needs decision)
3. **agents** — fleet agent activity (from Claude transcripts directory)
4. **tracker** — tracker items (CRUD mutations reflected in realtime)
5. **status** — orchestrator phase + activity
6. **cost** — cost/scorecard summary (wave-14 addition)

## Background Collector Thread

Daemon thread polling heartbeats/logs via mtime/fingerprint gates; re-derives SSE sections only on input change, broadcasts only when content-hash differs (avoids expensive operations on every tick). Started idempotently on first HTTP request via `start_collector_thread()`, runs with single-instance guard `_collector_lock`, wakes every `COLLECTOR_INTERVAL` (default 1.0s, `AESOP_UI_COLLECT_INTERVAL`).

## Invariants & Gotchas

- **Stdlib only**: No external dependencies (requests, flask, etc.). Uses only `http.server`, `json`, `subprocess`, `threading`.
- **ThreadingHTTPServer required**: SSE model requires one thread per client connection. Standard HTTPServer (processes) cannot hold SSE connections open.
- **Collector fail-open**: If collector thread crashes, server continues serving; realtime updates stop but dashboard remains accessible.
- **Token file permissions**: On Unix-like systems, token file is chmod 0600 (user-only). Windows ignores mode bits but respects file permissions via ACLs.
- **Paths git-ignored**: `state/.ui-session-token` is ephemeral (regenerated if missing), never committed.
