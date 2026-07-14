# ui/ — Web dashboard

**Purpose**: Stdlib-only local observability dashboard. Serves a dark-theme HTML dashboard on a configurable port (realtime via Server-Sent Events), enabling real-time fleet monitoring without external dependencies.

## Files (wave-9 split: serve.py monolith decomposed into focused modules)

- **serve.py** — Thin (~65-line) entry point + composition layer. Wires the sibling modules, calls `config.reload()` / `csrf.init()` / `sse.reset_state()`, and re-exports their symbols so `serve.X` keeps resolving for the test suite (which loads serve.py by path) and for `python ui/serve.py`.
- **config.py** — Path / env / `aesop.config.json` resolution. `reload()` recomputes all path globals from the current environment. **Load-bearing rule: every other module reads `config.X` at call time (`import config`), never `from config import <path>` — a frozen import would go stale after reload() (breaks test-fixture isolation).**
- **csrf.py** — Session-token generation (atomic O_EXCL 0600) + `validate_csrf_request()`; `init()` sets `SESSION_TOKEN`.
- **collectors.py** — Read-only data collectors (heartbeats, repos, events, alerts, messages, backlog parse), tracker CRUD, and SSE section snapshots (incl. `read`-style tracker/orchestrator-status snapshots + inbox drain).
- **agents.py** — Agent transcript reading (`get_fleet_agents`, `extract_agent_dispatch_prompt`) and path-traversal-safe agent-id handling (`_AGENT_ID_FORBIDDEN`).
- **sse.py** — SSE client registry, bounded broadcast, hash-gated `_maybe_emit`, and the background `collector_loop`. `reset_state()` restores per-import collector isolation (the `sse` module is cached across test re-imports).
- **render.py** — Renders `templates/dashboard.html`, substituting the CSRF token via a unique sentinel (no `.format`/% — the CSS/JS is full of `{}`/`%`).
- **handler.py** — `DashboardHandler` (HTTP routing + all GET/POST endpoints incl. /api/tracker) and `run_server()`. Reads `config.X` / `csrf.SESSION_TOKEN` at call time.
- **templates/dashboard.html** — The dashboard HTML/CSS/JS (extracted from the serve.py string), incl. tracker panel + orchestrator-status panel + audit-cycle ASCII banner.
- **README.md** — User guide and configuration reference.

## API Package (ui/api/)

Shared mutation-request validation and domain-logic handlers (wave-10 split from handler.py). Every mutating endpoint (`/submit`, `POST /api/tracker`, `POST /api/tracker/<id>`) gates requests identically: CSRF token validation, Content-Length bounds-check, then JSON decode. This module centralizes those gates so they are directly unit-testable without HTTP coupling.

- **__init__.py** — Shared mutation gate (`validate_mutation()`). Performs CSRF validation + Content-Length bounds-check (10 KB cap) + JSON decode. Returns `(True, parsed_json)` on success or `(False, (status_code, error_dict))` on gate failure. **Load-bearing rule**: callers must bound the socket read using the same Content-Length header before invoking, to prevent DoS; MAX_BODY_BYTES is re-derived here for validation but socket read is caller's responsibility.
- **submit.py** — Inbox-append logic (`append_to_inbox(text)`). Appends one timestamped line to `config.INBOX_FILE`, rejects symlinks (TOCTOU defense), creates file with header if missing.
- **tracker.py** — Tracker CRUD handlers (`list_items()`, `create()`, `update()`, `delete()`). Calls `collectors` tracker functions; returns `(status_code, response_dict)` for direct HTTP response writing. **Load-bearing**: all tracker mutations pass through `validate_mutation()` in create; update/delete check CSRF via `csrf.validate_csrf_request()` performed by caller before path is parsed.

**Key invariant**: All three modules read `config.X` live via `import config` at call time, never `from config import X`. A frozen import goes stale after `config.reload()` (breaks test-fixture isolation). See ui/CLAUDE.md "load-bearing rule" note above.

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

## Server-Sent Events (SSE) Model

**Realtime streaming via GET /events**:
- ThreadingHTTPServer required (SSE holds one connection per client)
- Streams JSON frames: `event: data|backlog|agents` / `data: <json>`
- Keepalive comment-line (`: keepalive`) sent every ~15s to prevent timeout
- Read-only stream; no mutations

**Sections emitted** (only on content change):
1. **data** — heartbeat status, daemon state, log tail
2. **backlog** — AUDIT-BACKLOG.md parsed into tier buckets (P0/P1/P2/Needs decision)
3. **agents** — fleet agent activity (from Claude transcripts directory)

## Background Collector Thread

**Lifecycle**:
- Started idempotently on first HTTP request (via `start_collector_thread()`)
- Runs as daemon thread (terminates when main process exits)
- Single-instance guard via `_collector_lock` (prevents double-start)

**Polling strategy**:
- Wakes every `COLLECTOR_INTERVAL` seconds (default: 1.0, overridable via `AESOP_UI_COLLECT_INTERVAL`)
- Polls cheap sources: heartbeat file mtimes, log tails, file fingerprints
- Only re-derives sections when underlying input changed (mtime/fingerprint gate)
- Only emits to clients when section content-hash changed (avoids redundant broadcasts)

**Cached data**:
- Last computed hash per section (data/backlog/agents)
- Last mtime of AUDIT-BACKLOG.md
- Last fingerprint of transcripts directory (to detect agent activity changes)
- Cached parsed backlog and agent snapshot (reused until inputs change)

**Content-change detection**:
- Mtime-gated: backlog section re-derived only if AUDIT-BACKLOG.md mtime changed
- Fingerprint-gated: agents section re-derived only if transcripts directory content changed
- Hash-gated: broadcast only sent if content-hash differs from last broadcast
- This avoids expensive operations (subprocess for dash-extra.mjs, directory walk) on every tick

## Invariants & Gotchas

- **Stdlib only**: No external dependencies (requests, flask, etc.). Uses only `http.server`, `json`, `subprocess`, `threading`.
- **ThreadingHTTPServer required**: SSE model requires one thread per client connection. Standard HTTPServer (processes) cannot hold SSE connections open.
- **Collector fail-open**: If collector thread crashes, server continues serving; realtime updates stop but dashboard remains accessible.
- **Token file permissions**: On Unix-like systems, token file is chmod 0600 (user-only). Windows ignores mode bits but respects file permissions via ACLs.
- **Paths git-ignored**: `state/.ui-session-token` is ephemeral (regenerated if missing), never committed.
