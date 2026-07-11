#!/usr/bin/env python3
"""
Aesop Web Dashboard — stdlib-only local observability.
Serves a dark-theme HTML dashboard on a configurable port (default 8770).
No external dependencies. Auto-refresh every 3s via fetch('/data') → JSON.

Configuration:
  - AESOP_ROOT: env var pointing to aesop installation (default: $HOME/aesop)
  - aesop.config.json: optional config file with paths and settings
  - PORT env var: override dashboard port (default: 8770)
  - AESOP_TRANSCRIPTS_ROOT: env var for Claude transcript directory
"""
import http.server
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from time import time


# ==============================================================================
# Configuration & Paths
# ==============================================================================

PORT = int(os.getenv("PORT", "8770"))

# Determine AESOP_ROOT
AESOP_ROOT = Path(os.getenv("AESOP_ROOT", Path.home() / "aesop"))

# Try to load config file for additional settings
CONFIG_FILE = AESOP_ROOT / "aesop.config.json"
config = {}
if CONFIG_FILE.exists():
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    except:
        pass

# Derive paths from config or defaults
STATE_DIR = Path(config.get("state_root", str(AESOP_ROOT / "state")))
SCAN_DIR = Path(config.get("scan_root", str(AESOP_ROOT / "scan")))

# Transcript path: configurable via env var or config
# Default placeholder: $BRAIN_ROOT/projects/<project-name> (user fills in)
TRANSCRIPTS_ROOT = Path(
    os.getenv(
        "AESOP_TRANSCRIPTS_ROOT",
        config.get("transcripts_root", "~/.claude/projects")
    )
).expanduser()

WATCHDOG_HEARTBEAT = STATE_DIR / ".watchdog-heartbeat"
MONITOR_HEARTBEAT = STATE_DIR / ".monitor-heartbeat"
REPOS_JSON = STATE_DIR / ".watchdog-repos.json"
BACKUP_LOG = STATE_DIR / "FLEET-BACKUP.log"
ALERTS_LOG = SCAN_DIR / "SECURITY-ALERTS.log"
INBOX_FILE = STATE_DIR / "ui-inbox.md"


# ==============================================================================
# Data Collection Functions
# ==============================================================================

def get_heartbeat_status():
    """Read daemon heartbeat age and status."""
    try:
        if not WATCHDOG_HEARTBEAT.exists():
            return {"alive": "UNKNOWN", "age": -1, "threshold": 300}
        content = WATCHDOG_HEARTBEAT.read_text().strip()
        if not content:
            return {"alive": "UNKNOWN", "age": -1, "threshold": 300}
        # Parse epoch value robustly; assume seconds (standard epoch format)
        try:
            timestamp = int(content)
        except ValueError:
            # Retry once in case of race during daemon write
            try:
                content = WATCHDOG_HEARTBEAT.read_text().strip()
                timestamp = int(content)
            except:
                return {"alive": "unknown", "age": -1, "threshold": 300}
        # Age in seconds: now_seconds - heartbeat_seconds
        age_seconds = int(time()) - timestamp
        alive = "ALIVE" if age_seconds < 300 else "STALE"
        return {"alive": alive, "age": age_seconds, "threshold": 300}
    except:
        return {"alive": "unknown", "age": -1, "threshold": 300}


def get_monitor_heartbeat_status():
    """Read orchestration monitor heartbeat age and status."""
    try:
        # Check both possible paths: state/.monitor-heartbeat and monitor/.monitor-heartbeat
        monitor_hb = MONITOR_HEARTBEAT
        if not monitor_hb.exists():
            # Try alternate path
            alt_path = AESOP_ROOT / "monitor" / ".monitor-heartbeat"
            if not alt_path.exists():
                return {"alive": "not running", "age": -1, "threshold": 3600}
            monitor_hb = alt_path

        content = monitor_hb.read_text().strip()
        if not content:
            return {"alive": "not running", "age": -1, "threshold": 3600}
        # Parse epoch value robustly; assume seconds (standard epoch format)
        try:
            timestamp = int(content)
        except ValueError:
            # Retry once in case of race during monitor write
            try:
                content = monitor_hb.read_text().strip()
                timestamp = int(content)
            except:
                return {"alive": "unknown", "age": -1, "threshold": 3600}
        # Age in seconds: now_seconds - heartbeat_seconds
        age_seconds = int(time()) - timestamp
        alive = "ALIVE" if age_seconds < 3600 else "STALE"
        return {"alive": alive, "age": age_seconds, "threshold": 3600}
    except:
        return {"alive": "unknown", "age": -1, "threshold": 3600}


def get_fleet_agents():
    """Detect running subagents by calling dash-extra.mjs --json."""
    agents = []
    try:
        # Call the working detector (dash-extra.mjs) with --json flag
        dash_extra_path = AESOP_ROOT / "dash" / "dash-extra.mjs"
        if not dash_extra_path.exists():
            return agents
        result = subprocess.run(
            ["node", str(dash_extra_path), "--json"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout:
            agents = json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    except Exception:
        pass
    return agents


def get_main_thread_messages():
    """Read last ~12 messages from newest session JSONL."""
    messages = []
    try:
        if not TRANSCRIPTS_ROOT.exists():
            return messages
        # Find newest .jsonl
        jsonl_files = sorted(
            TRANSCRIPTS_ROOT.glob("**/*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not jsonl_files:
            return messages

        newest = jsonl_files[0]
        with open(newest, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            # Get last 30 lines to extract ~12 message turns
            for line in lines[-30:]:
                try:
                    obj = json.loads(line)
                    role = obj.get("role", "unknown")
                    if role in ("user", "assistant"):
                        # Extract text content
                        content = obj.get("content", [])
                        text = ""
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and "text" in block:
                                    text = block["text"]
                                    break
                        elif isinstance(content, str):
                            text = content

                        if text:
                            # Truncate to 200 chars and sanitize
                            preview = text[:200].replace("\n", " ").strip()
                            timestamp = obj.get("timestamp", "")
                            messages.append({
                                "role": role,
                                "text": preview,
                                "timestamp": timestamp
                            })
                except (json.JSONDecodeError, KeyError):
                    pass
            # Keep only last 12
            messages = messages[-12:]
    except:
        pass
    return messages


def get_repos_status():
    """Read repos from .watchdog-repos.json."""
    repos = []
    try:
        if not REPOS_JSON.exists():
            return repos
        data = json.loads(REPOS_JSON.read_text())
        if isinstance(data, list):
            repos = data[:10]  # Limit to 10
        elif isinstance(data, dict):
            repos = [{"repo": k, "state": v} for k, v in data.items()][:10]
    except:
        pass
    return repos


def get_recent_events():
    """Read last 8 lines from FLEET-BACKUP.log."""
    events = []
    try:
        if not BACKUP_LOG.exists():
            return events
        lines = BACKUP_LOG.read_text().strip().split('\n')
        events = [line.strip() for line in lines[-8:] if line.strip()]
    except:
        pass
    return events


def get_alerts():
    """Read SECURITY-ALERTS.log, skip NOTE:/RESOLVED-FP, count by severity."""
    alerts = {"count": 0, "lines": []}
    try:
        if not ALERTS_LOG.exists():
            return alerts
        lines = ALERTS_LOG.read_text().strip().split('\n')
        unreviewed = [
            line.strip() for line in lines
            if line.strip()
            and "NOTE:" not in line
            and "RESOLVED-FP" not in line
        ]
        alerts["count"] = len(unreviewed)
        alerts["lines"] = unreviewed[-5:]  # Show last 5
    except:
        pass
    return alerts


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
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests."""
        if self.path == "/submit":
            self.handle_submit()
        else:
            self.send_error(404)

    def serve_html(self):
        """Serve the dashboard HTML."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Aesop Fleet Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html { color-scheme: dark; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Monospace;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 16px;
            line-height: 1.5;
        }
        .container { max-width: 1600px; margin: 0 auto; }
        h1 { font-size: 20px; margin-bottom: 20px; color: #fff; }
        h2 { font-size: 14px; margin-top: 20px; margin-bottom: 10px; color: #8ac; font-weight: bold; }

        .header { display: flex; gap: 20px; margin-bottom: 20px; padding: 12px; background: #1a1a1a; border-radius: 4px; }
        .header-item { flex: 1; }
        .header-label { font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 4px; }
        .header-value { font-size: 14px; color: #fff; font-weight: bold; }
        .status-alive { color: #0a0; }
        .status-stale { color: #f44; }
        .status-unknown { color: #999; }

        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
        @media (max-width: 1200px) { .grid { grid-template-columns: 1fr; } }

        .panel { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; }
        .panel-title { font-size: 12px; color: #8ac; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; }

        .item { padding: 8px 0; font-size: 12px; border-bottom: 1px solid #2a2a2a; }
        .item:last-child { border-bottom: none; }
        .item-id { color: #8ac; font-weight: bold; }
        .item-age { color: #999; margin: 0 8px; }
        .item-status { padding: 2px 6px; border-radius: 2px; font-size: 10px; font-weight: bold; }
        .status-running { background: #0a0; color: #000; }
        .status-done { background: #666; color: #fff; }

        .inbox-box { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; margin-bottom: 20px; }
        .inbox-label { font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 8px; }
        .inbox-input { width: 100%; padding: 8px; background: #0a0a0a; border: 1px solid #333; color: #e0e0e0; border-radius: 2px; font-size: 12px; font-family: inherit; }
        .inbox-input:focus { outline: none; border-color: #8ac; }
        .inbox-button { background: #8ac; color: #000; border: none; padding: 8px 16px; border-radius: 2px; margin-top: 8px; cursor: pointer; font-weight: bold; font-size: 12px; }
        .inbox-button:hover { background: #9bd; }
        .inbox-button:disabled { background: #555; cursor: not-allowed; }
        .inbox-status { font-size: 11px; color: #0a0; margin-top: 4px; display: none; }

        .alerts-box { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; }
        .alert-line { font-size: 11px; padding: 4px 0; color: #f44; font-family: monospace; }
        .alert-none { color: #666; }

        .messages-box { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; max-height: 400px; overflow-y: auto; }
        .message { padding: 8px 0; border-bottom: 1px solid #2a2a2a; font-size: 11px; }
        .message:last-child { border-bottom: none; }
        .message-role { color: #8ac; font-weight: bold; }
        .message-time { color: #666; font-size: 10px; margin-left: 8px; }
        .message-text { color: #ccc; margin-top: 4px; }

        .loading { color: #666; font-style: italic; }
        .error { color: #f44; }
        .fade-in { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0.5; } to { opacity: 1; } }
    </style>
</head>
<body>
    <div class="container">
        <h1>Aesop Fleet Dashboard</h1>

        <div class="header" id="header">
            <div class="header-item">
                <div class="header-label">Watchdog Status</div>
                <div class="header-value" id="watchdog-status">
                    <span id="watchdog-alive" class="status-unknown">—</span>
                    <span id="watchdog-age" style="color: #999; margin-left: 8px;">—</span>
                </div>
            </div>
            <div class="header-item">
                <div class="header-label">Monitor Status</div>
                <div class="header-value" id="monitor-status">
                    <span id="monitor-alive" class="status-unknown">—</span>
                    <span id="monitor-age" style="color: #999; margin-left: 8px;">—</span>
                </div>
            </div>
            <div class="header-item">
                <div class="header-label">Security Alerts</div>
                <div class="header-value" id="alert-count" style="color: #999;">—</div>
            </div>
            <div class="header-item">
                <div class="header-label">Running Agents</div>
                <div class="header-value" id="running-count" style="color: #999;">—</div>
            </div>
        </div>

        <div class="inbox-box">
            <div class="inbox-label">Queue Work (Read by Orchestrator Each Turn)</div>
            <input type="text" class="inbox-input" id="inbox-input" placeholder="Type your task here...">
            <button class="inbox-button" id="inbox-button">Send to Inbox</button>
            <div class="inbox-status" id="inbox-status">Queued ✓</div>
        </div>

        <div class="grid">
            <div class="panel">
                <div class="panel-title">Fleet Agents (Last 2 Min)</div>
                <div id="agents-list" class="loading">—</div>
            </div>

            <div class="panel">
                <div class="panel-title">Repos Status</div>
                <div id="repos-list" class="loading">—</div>
            </div>
        </div>

        <div class="grid">
            <div class="panel">
                <div class="panel-title">Recent Events (Last 8)</div>
                <div id="events-list" class="loading">—</div>
            </div>

            <div class="alerts-box">
                <div class="panel-title">Security Alerts (Unreviewed)</div>
                <div id="alerts-list" class="alert-none">—</div>
            </div>
        </div>

        <div class="panel">
            <div class="panel-title">Main-Thread Prompts (Last ~12 Messages)</div>
            <div class="messages-box" id="messages-list" class="loading">—</div>
        </div>

        <div style="text-align: center; margin-top: 30px; color: #666; font-size: 11px;">
            Auto-refresh every 3s · Dashboard
        </div>
    </div>

    <script>
        let lastRefresh = 0;

        function formatTimestamp(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        }

        function sanitize(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function refresh() {
            try {
                const response = await fetch('/data');
                if (!response.ok) return;
                const data = await response.json();

                // Update header
                const watchdog = data.watchdog || {};
                const watchdogAlive = document.getElementById('watchdog-alive');
                watchdogAlive.textContent = watchdog.alive || '—';
                watchdogAlive.className = 'status-' + (watchdog.alive || 'unknown').toLowerCase();
                document.getElementById('watchdog-age').textContent = watchdog.age >= 0 ? watchdog.age + 's' : '—';

                const monitor = data.monitor || {};
                const monitorAlive = document.getElementById('monitor-alive');
                monitorAlive.textContent = monitor.alive || '—';
                monitorAlive.className = 'status-' + (monitor.alive || 'unknown').toLowerCase();
                document.getElementById('monitor-age').textContent = monitor.age >= 0 ? monitor.age + 's' : '—';

                document.getElementById('alert-count').textContent = data.alerts?.count || 0;
                const runningAgents = (data.agents || []).filter(a => a.status === 'running').length;
                document.getElementById('running-count').textContent = runningAgents;

                // Agents
                const agentsList = document.getElementById('agents-list');
                if (data.agents && data.agents.length > 0) {
                    agentsList.innerHTML = data.agents.map(a =>
                        `<div class="item fade-in"><span class="item-id">${sanitize(a.id)}</span><span class="item-age">${a.age_s}s</span><span class="item-status status-${a.status}">${a.status}</span><br><span style="color: #999;">${sanitize((a.hint || '').substring(0, 60))}</span></div>`
                    ).join('');
                } else {
                    agentsList.textContent = '(no active agents)';
                    agentsList.style.color = '#666';
                }

                // Repos
                const reposList = document.getElementById('repos-list');
                if (data.repos && data.repos.length > 0) {
                    reposList.innerHTML = data.repos.map(r => {
                        const repo = r.repo || Object.keys(r)[0] || 'unknown';
                        const state = r.state || r[repo] || 'unknown';
                        return `<div class="item"><span class="item-id">${sanitize(repo.substring(0, 30))}</span> <span style="color: #999;">${sanitize(state)}</span></div>`;
                    }).join('');
                } else {
                    reposList.textContent = '(no repos)';
                    reposList.style.color = '#666';
                }

                // Events
                const eventsList = document.getElementById('events-list');
                if (data.events && data.events.length > 0) {
                    eventsList.innerHTML = data.events.map(e =>
                        `<div class="item"><span style="color: #999; font-size: 10px;">${sanitize(e.substring(0, 80))}</span></div>`
                    ).join('');
                } else {
                    eventsList.textContent = '(no recent events)';
                    eventsList.style.color = '#666';
                }

                // Alerts
                const alertsList = document.getElementById('alerts-list');
                if (data.alerts && data.alerts.lines && data.alerts.lines.length > 0) {
                    alertsList.innerHTML = data.alerts.lines.map(line =>
                        `<div class="alert-line">${sanitize(line.substring(0, 120))}</div>`
                    ).join('');
                } else {
                    alertsList.innerHTML = '<div class="alert-none">(no alerts)</div>';
                }

                // Messages
                const messagesList = document.getElementById('messages-list');
                if (data.messages && data.messages.length > 0) {
                    messagesList.innerHTML = data.messages.map(m =>
                        `<div class="message fade-in"><span class="message-role">${sanitize(m.role)}</span><span class="message-time">${formatTimestamp(m.timestamp)}</span><div class="message-text">${sanitize(m.text)}</div></div>`
                    ).join('');
                } else {
                    messagesList.textContent = '(no messages)';
                    messagesList.style.color = '#666';
                }

                lastRefresh = Date.now();
            } catch (e) {
                console.error('Refresh error:', e);
            }
        }

        async function handleInboxSubmit() {
            const input = document.getElementById('inbox-input');
            const button = document.getElementById('inbox-button');
            const status = document.getElementById('inbox-status');

            const text = input.value.trim();
            if (!text) return;

            button.disabled = true;
            try {
                const response = await fetch('/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                if (response.ok) {
                    input.value = '';
                    status.style.display = 'block';
                    setTimeout(() => { status.style.display = 'none'; }, 3000);
                }
            } catch (e) {
                console.error('Submit error:', e);
            } finally {
                button.disabled = false;
            }
        }

        document.getElementById('inbox-button').addEventListener('click', handleInboxSubmit);
        document.getElementById('inbox-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleInboxSubmit();
        });

        refresh();
        setInterval(refresh, 3000);
    </script>
</body>
</html>"""
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

    def handle_submit(self):
        """Handle /submit POST."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 10000:  # 10KB limit
                self.send_error(413)
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
            if not INBOX_FILE.exists():
                INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
                INBOX_FILE.write_text("# UI Inbox — orchestrator reads each turn / on /power\n\n")

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
    """Start the HTTP server."""
    addr = ("127.0.0.1", PORT)
    httpd = http.server.HTTPServer(addr, DashboardHandler)
    print(f"Dashboard: http://localhost:{PORT}")
    print(f"AESOP_ROOT: {AESOP_ROOT}")
    print(f"Transcripts: {TRANSCRIPTS_ROOT}")
    print(f"Press Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown complete.")
        sys.exit(0)


if __name__ == "__main__":
    run_server()
