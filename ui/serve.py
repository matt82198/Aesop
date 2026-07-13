#!/usr/bin/env python3
"""
Aesop Web Dashboard — stdlib-only local observability.
Serves a dark-theme HTML dashboard on a configurable port (default 8770).
No external dependencies. Realtime via GET /events (Server-Sent Events) —
a background collector thread emits a section (data/backlog/agents) only
when its content actually changed; the client patches the DOM in place
(no interval polling, no full-page rebuild).

Configuration:
  - AESOP_ROOT: env var pointing to aesop installation (default: $HOME/aesop)
  - aesop.config.json: optional config file with paths and settings
  - PORT env var: override dashboard port (default: 8770)
  - AESOP_TRANSCRIPTS_ROOT: env var for Claude transcript directory
  - AESOP_UI_COLLECT_INTERVAL: env var, seconds between collector polls (default: 1.0)

CSRF Protection:
  - Per-session token generated at startup and persisted to state/.ui-session-token (0600)
  - /submit endpoint validates Origin/Referer headers (must be local or absent)
  - /submit endpoint requires X-Aesop-Token header matching session token
  - Legitimate dashboard submits: token injected into HTML and sent by browser JS
  - Local CLI clients: read token from state/.ui-session-token (0600)
  - GET /events (SSE) requires no token: it is a read-only stream, not a mutation

Realtime (SSE) model:
  - Server: a daemon collector thread polls cheap sources (heartbeat files, log
    tails, AUDIT-BACKLOG.md mtime, a transcripts-dir fingerprint) on a short
    cadence. It only re-derives + re-emits a section when its underlying input
    actually changed (mtime/fingerprint gate), and only broadcasts to clients
    when the section's content-hash changed. This avoids spawning `node
    dash-extra.mjs` on every tick.
  - GET /events (ThreadingHTTPServer — required, since SSE holds one connection
    open per client) streams `event: data|backlog|agents` / `data: <json>`
    frames, plus a comment-line keepalive (`: keepalive`) every ~15s.
"""
import hashlib
import http.server
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path
from time import time

# ==============================================================================
# Sibling module imports (config, csrf)
# ==============================================================================

# Sys.path shim: add ui/ directory to path so sibling imports work
# (both when run as 'python ui/serve.py' and when imported via importlib)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and initialize config
import config
config.reload()

# Import and initialize CSRF protection
import csrf
csrf.init()

import render

# Re-export all config and csrf symbols for backward compatibility
# (tests and other code access these via serve.X)
from config import *
from csrf import *
from render import render_dashboard

# wave-9 split: data/agents/sse modules re-exported so serve.X keeps resolving
import collectors, agents, sse
sse.reset_state()  # fresh collector/snapshot state per serve import (test isolation)
from collectors import *
from agents import *
from sse import *
from collectors import (_snapshot_data, _snapshot_tracker,
                        _snapshot_orchestrator_status, drain_tracker_inbox)
from agents import _AGENT_ID_FORBIDDEN, _transcripts_fingerprint
from sse import (_sse_lock, _sse_clients, _latest_lock, _latest_snapshots,
                 _collector_lock, _collector_stop_event, _maybe_emit)


# ==============================================================================
# Data Collection Functions
# ==============================================================================


















# ==============================================================================
# Tracker Data Layer (state/tracker.json) — wave-8 CRUD API
# ==============================================================================
# (TRACKER_FILE is imported from config)
















# agent_id is attacker-controlled (GET /agent?id=...) and is spliced into a glob
# pattern below. Reject path-traversal segments and glob metacharacters before
# the pattern is ever built — a bare "/", "\", "..", "*", "?", "[" or "]" has no
# legitimate use in an agent id (ids are opaque hex-ish tokens).




# ==============================================================================
# Realtime collector (SSE) — background thread, change-hash gated broadcast
# ==============================================================================

# How often the collector wakes up to check for changes. Cheap sources (heartbeat
# files, log tails) are re-read every tick; expensive sources (backlog parse, the
# `node dash-extra.mjs` subprocess for agents) are gated behind a mtime/fingerprint
# check so they're only re-derived when their underlying input actually changed.










# New functions for tracker SSE integration (to be inserted into serve.py)



















# ==============================================================================
# HTTP Server
# ==============================================================================

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for dashboard."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/":
            self.serve_html()
        elif self.path == "/data":
            self.serve_data()
        elif self.path == "/api/backlog":
            self.serve_backlog()
        elif self.path == "/api/agents":
            self.serve_agents()
        elif self.path.startswith("/api/tracker"):
            self.serve_tracker()
        elif self.path.startswith("/agent?"):
            self.serve_agent()
        elif self.path == "/events":
            self.serve_events()
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests."""
        if self.path == "/submit":
            self.handle_submit()
        elif self.path == "/api/tracker":
            self.handle_tracker_create()
        elif self.path.startswith("/api/tracker/"):
            self.handle_tracker_mutate()
        else:
            self.send_error(404)

    def serve_html(self):
        """Serve the dashboard HTML."""
        html = render_dashboard(SESSION_TOKEN)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_data(self):
        """Serve dashboard data as JSON."""
        data = {
            "watchdog": get_heartbeat_status(),
            "monitor": get_monitor_heartbeat_status(),
            "agents": get_fleet_agents(),
            "repos": get_repos_status(),
            "events": get_recent_events(),
            "alerts": get_alerts(),
            "messages": get_main_thread_messages(),
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode('utf-8'))

    def serve_tracker(self):
        """Serve tracker items as JSON via GET /api/tracker."""
        try:
            # Parse query string for filters
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            status = params.get('status', [None])[0]
            priority = params.get('priority', [None])[0]

            items = get_tracker_items(status=status, priority=priority)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(items, default=str).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def handle_tracker_create(self):
        """Handle POST /api/tracker (create item)."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > 10000:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid Content-Length"}).encode('utf-8'))
                return

            body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
            data = json.loads(body)

            item = create_tracker_item(data)
            self.send_response(201)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(item, default=str).encode('utf-8'))
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def handle_tracker_mutate(self):
        """Handle POST /api/tracker/<id> (update or delete)."""
        try:
            is_valid, reason = validate_csrf_request(self.headers)
            if not is_valid:
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "CSRF protection: " + reason}).encode('utf-8'))
                return

            # Extract item_id from path
            path_parts = self.path.strip("/").split("/")
            if len(path_parts) < 3:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Not found"}).encode('utf-8'))
                return

            item_id = path_parts[2]

            # Parse query for action (update or delete)
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            action = params.get('action', ['update'])[0]

            if action == "delete":
                item = delete_tracker_item(item_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(item, default=str).encode('utf-8'))
            else:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length <= 0 or content_length > 10000:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Invalid Content-Length"}).encode('utf-8'))
                    return

                body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
                update_data = json.loads(body)

                item = update_tracker_item(item_id, update_data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(item, default=str).encode('utf-8'))
        except Exception as e:
            if "404" in str(e):
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))


    def serve_backlog(self):
        """Serve audit backlog data as JSON via GET /api/backlog."""
        try:
            data = parse_audit_backlog()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def serve_agents(self):
        """Serve rich agent list with metadata via GET /api/agents."""
        try:
            agents = get_fleet_agents()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(agents, default=str).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def serve_agent(self):
        """Serve agent dispatch prompt and metadata via GET /agent?id=<agent_id>"""
        try:
            # Parse query string
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            agent_id = params.get('id', [None])[0]

            if not agent_id:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "missing id parameter"}).encode('utf-8'))
                return

            # Extract dispatch prompt and metadata
            data = extract_agent_dispatch_prompt(agent_id)

            if "error" in data:
                # Rejected input (path traversal, glob metacharacters, or a match
                # that resolved outside TRANSCRIPTS_ROOT) -> 400. A well-formed id
                # with no matching transcript -> 404. Never 200 on error.
                status = 400 if data.get("invalid") else 404
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": data["error"]}).encode('utf-8'))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            print(f"[serve_agent] Uncaught exception: {e}", file=sys.stderr)
            self.wfile.write(json.dumps({"error": "Internal server error"}).encode('utf-8'))

    def _write_sse_event(self, event_name, payload):
        """Write one SSE frame with timeout. Caller handles disconnect exceptions."""
        msg = f"event: {event_name}\ndata: {payload}\n\n"
        # Set socket timeout to prevent stalled writes from blocking the server
        try:
            old_timeout = self.connection.gettimeout()
            self.connection.settimeout(SSE_WRITE_TIMEOUT)
        except (AttributeError, OSError):
            pass
        try:
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()
        finally:
            # Restore original timeout
            try:
                if 'old_timeout' in locals():
                    self.connection.settimeout(old_timeout)
            except (AttributeError, OSError):
                pass

    def serve_events(self):
        """GET /events — Server-Sent Events stream.

        No CSRF token required: this is a read-only stream, not a mutation (POST
        /submit keeps its token requirement unchanged). Holds the connection open
        for the life of the client; requires ThreadingHTTPServer (see run_server)
        so one SSE client can't block every other request.

        Returns HTTP 503 if concurrent connection cap (SSE_MAX_CLIENTS) is exceeded.
        """
        start_collector_thread()

        q = register_sse_client()
        if q is None:
            # Connection cap exceeded; return 503 Service Unavailable
            try:
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Retry-After", "30")
                self.end_headers()
                self.wfile.write(b"Service overloaded: too many concurrent clients\n")
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
                pass
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            unregister_sse_client(q)
            return
        try:
            # Send an immediate full snapshot so first paint isn't empty. If the
            # collector hasn't produced anything yet (first-ever request), compute
            # it inline once.
            with _latest_lock:
                initial = dict(_latest_snapshots)
            if all(v is None for v in initial.values()):
                initial["data"] = json.dumps(_snapshot_data(), default=str, sort_keys=True)
                initial["backlog"] = json.dumps(parse_audit_backlog(), default=str, sort_keys=True)
                initial["agents"] = json.dumps(get_fleet_agents(), default=str, sort_keys=True)
                initial["tracker"] = json.dumps(_snapshot_tracker(), default=str, sort_keys=True)
                initial["status"] = json.dumps(_snapshot_orchestrator_status(), default=str, sort_keys=True)
                with _latest_lock:
                    _latest_snapshots.update(initial)

            for name in ("data", "backlog", "agents", "tracker", "status"):
                payload = initial.get(name)
                if payload is not None:
                    self._write_sse_event(name, payload)

            while True:
                try:
                    event_name, payload = q.get(timeout=SSE_KEEPALIVE_SECONDS)
                    self._write_sse_event(event_name, payload)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            # Client disconnected (tab closed, network drop) — normal, not an error.
            pass
        except Exception:
            pass
        finally:
            unregister_sse_client(q)

    def handle_submit(self):
        """Handle /submit POST with CSRF protection."""
        try:
            # CSRF validation: Check Origin/Referer + X-Aesop-Token
            is_valid, reason = validate_csrf_request(self.headers)
            if not is_valid:
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "CSRF protection: " + reason
                }).encode('utf-8'))
                return

            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > 10000:  # 10KB limit, must be positive
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Invalid Content-Length (must be 1-10000 bytes)"
                }).encode('utf-8'))
                return

            body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
            data = json.loads(body)
            text = data.get("text", "").strip()

            if not text:
                self.send_response(400)
                self.end_headers()
                return

            # Append to inbox
            inbox_content = f"- [{datetime.now().isoformat()}] {text}\n"
            # Security: reject symlinks (TOCTOU defense)
            if INBOX_FILE.exists():
                if os.path.islink(str(INBOX_FILE)):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": "Inbox file is a symlink (rejected for security)"
                    }).encode('utf-8'))
                    return
            else:
                INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
                # Must match the encoding (utf-8) AND newline convention (LF) of the
                # append below — text-mode write_text() with no encoding= falls back
                # to the locale-preferred encoding (cp1252 on Windows), which mangles
                # non-ASCII bytes like the em-dash and leaves the file as a whole not
                # valid UTF-8 for anything that reads it with encoding="utf-8".
                with open(INBOX_FILE, 'w', encoding='utf-8', newline='\n') as f:
                    f.write("# UI Inbox — orchestrator reads each turn / on /power\n\n")

            with open(INBOX_FILE, 'a', encoding='utf-8') as f:
                f.write(inbox_content)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.end_headers()


def run_server():
    """Start the HTTP server.

    Must be ThreadingHTTPServer, not HTTPServer: GET /events (SSE) holds its
    connection open for the life of the client, so a single-threaded server would
    wedge every other request (including the initial page load and /submit)
    behind that one held connection.
    """
    addr = ("127.0.0.1", PORT)
    httpd = http.server.ThreadingHTTPServer(addr, DashboardHandler)
    httpd.daemon_threads = True
    start_collector_thread()
    print(f"Dashboard: http://localhost:{PORT}")
    print(f"AESOP_ROOT: {AESOP_ROOT}")
    print(f"Transcripts: {TRANSCRIPTS_ROOT}")
    print(f"Press Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _collector_stop_event.set()
        print("\nShutdown complete.")
        sys.exit(0)


if __name__ == "__main__":
    run_server()
