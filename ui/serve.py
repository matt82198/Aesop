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
# Configuration & Paths
# ==============================================================================

PORT = int(os.getenv("PORT", "8770"))

# Determine AESOP_ROOT: env > default
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

# Derive paths with precedence: env var > config file > built-in default
# STATE_DIR: env AESOP_STATE_ROOT > config state_root > AESOP_ROOT/state
STATE_DIR = Path(
    os.getenv(
        "AESOP_STATE_ROOT",
        config.get("state_root", str(AESOP_ROOT / "state"))
    )
)

# TRANSCRIPTS_ROOT: env AESOP_TRANSCRIPTS_ROOT > config transcripts_root > ~/.claude/projects
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
ALERTS_LOG = STATE_DIR / "SECURITY-ALERTS.log"
INBOX_FILE = STATE_DIR / "ui-inbox.md"
AUDIT_BACKLOG_FILE = AESOP_ROOT / "AUDIT-BACKLOG.md"
UI_SESSION_TOKEN_FILE = STATE_DIR / ".ui-session-token"


# ==============================================================================
# CSRF Token Generation & Validation
# ==============================================================================

def generate_session_token():
    """Generate or load the per-session CSRF token.

    Token is generated once at startup and persisted to state/.ui-session-token (mode 0600).
    Subsequent imports of this module return the same token (in-memory).

    SECURITY: File is created atomically with restricted permissions using os.open(O_CREAT|O_EXCL)
    to avoid TOCTOU window where file exists with world-readable permissions.

    Returns:
        str: 43-character base64-like random token (256 bits / 3 bytes per char = ~43 chars)
    """
    # Check if token file exists and is readable
    if UI_SESSION_TOKEN_FILE.exists():
        try:
            token = UI_SESSION_TOKEN_FILE.read_text().strip()
            if token and len(token) >= 32:
                return token
        except:
            pass

    # Generate new token: 32 random bytes → 43-char base64-like string
    token = secrets.token_urlsafe(32)

    # Persist to file with restricted permissions (0600) using atomic creation
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        # Atomically create file with 0600 permissions using os.open with O_CREAT|O_EXCL.
        # This ensures the file is never world-readable (no TOCTOU window).
        # On Windows, mode bits are largely ignored, which is fine.
        try:
            fd = os.open(
                str(UI_SESSION_TOKEN_FILE),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600
            )
            # Write token via the file descriptor (no separate chmod needed)
            with os.fdopen(fd, 'w') as f:
                f.write(token)
        except FileExistsError:
            # File already exists (race condition or previous run).
            # Try to read it and use that token instead.
            try:
                token = UI_SESSION_TOKEN_FILE.read_text().strip()
                if token and len(token) >= 32:
                    return token
            except:
                pass
            # If we can't read the existing file, fall back to in-memory token
    except Exception:
        pass  # Fail-open: token exists in memory even if file write fails

    return token


# Generate and cache session token at module load time
SESSION_TOKEN = generate_session_token()


def validate_csrf_request(headers):
    """Validate CSRF protections on /submit POST request.

    Performs two checks:
    1. Origin/Referer validation: if Origin or Referer header is present, must be local
       (http://127.0.0.1:<port>, http://localhost:<port>)
    2. X-Aesop-Token validation: must match SESSION_TOKEN

    Args:
        headers: dict-like object with HTTP headers (case-insensitive)

    Returns:
        tuple: (is_valid: bool, reason: str or None)
        - (True, None) if CSRF checks pass
        - (False, reason) if either check fails
    """
    # Check 1: Origin/Referer header validation
    origin = headers.get("Origin", "").strip()
    referer = headers.get("Referer", "").strip()

    # If Origin or Referer is present, validate it's local
    if origin or referer:
        check_value = origin or referer
        # Check if it's a local origin: http://127.0.0.1:<PORT> or http://localhost:<PORT>
        is_local = (
            check_value.startswith("http://127.0.0.1:") or
            check_value.startswith("http://localhost:") or
            check_value.startswith("http://[::1]:")  # IPv6 localhost
        )
        if not is_local:
            return (False, "Foreign Origin/Referer rejected")

    # Check 2: X-Aesop-Token validation
    token = headers.get("X-Aesop-Token", "").strip()
    if not token:
        return (False, "Missing X-Aesop-Token header")

    if token != SESSION_TOKEN:
        return (False, "Invalid X-Aesop-Token")

    return (True, None)


# ==============================================================================
# Data Collection Functions
# ==============================================================================

def parse_audit_backlog():
    """
    Parse AUDIT-BACKLOG.md and return structured tier data.

    Returns:
        dict with 'tiers' list, each tier containing:
        {
            "tier": "P0" | "P1" | "P2" | "Needs decision",
            "items": [
                {"status": "✅"|"🔵"|"⬜"|"⏸", "tag": "[sec]", "title": "..."},
                ...
            ],
            "done": int,
            "inflight": int,
            "todo": int,
            "total": int
        }
    """
    result = {"tiers": []}

    try:
        if not AUDIT_BACKLOG_FILE.exists():
            return result

        content = AUDIT_BACKLOG_FILE.read_text(encoding='utf-8')
    except:
        return result

    # Split into lines
    lines = content.split('\n')

    # Parse sections and items.
    #
    # NOTE: tier headers are matched by REGEX PREFIX (e.g. "## P0\b"), not by exact/startswith
    # comparison against a fixed full title string. The backlog file's section titles evolve
    # over time (suffixes like "(do first)" become "(wave 5, from five-lens re-audit)"), and a
    # hardcoded full-string tier_map silently stops matching anything when that happens — the
    # panel then renders "no backlog found" forever even though the file is full of live items.
    # Regex-on-prefix survives any suffix/rename of the tier header.
    current_tier = None
    tier_patterns = [
        (re.compile(r'^##\s*P0\b'), "P0"),
        (re.compile(r'^##\s*P1\b'), "P1"),
        (re.compile(r'^##\s*P2\b'), "P2"),
        (re.compile(r'^##\s*Needs a user decision\b', re.IGNORECASE), "Needs decision"),
    ]

    # Stop parsing at these sections
    stop_sections = ["## Landing log", "## Dispatch plan"]

    tiers_data = {}  # tier_name -> list of items

    for line in lines:
        line_stripped = line.strip()

        # Check if we hit a stop section
        if any(line_stripped.startswith(stop) for stop in stop_sections):
            break

        # Any level-2 header re-evaluates current_tier. This is deliberate: a header that
        # doesn't match a known tier (e.g. "## Features (user-requested)") resets current_tier
        # to None, so its items are NOT silently attributed to whatever tier came before it
        # (bleed-through bug from sticky state).
        if line_stripped.startswith("## "):
            matched_tier = None
            for pattern, tier_name in tier_patterns:
                if pattern.match(line_stripped):
                    matched_tier = tier_name
                    break
            current_tier = matched_tier
            if current_tier and current_tier not in tiers_data:
                tiers_data[current_tier] = []
            continue

        # Parse item line (starts with "- " and a status glyph)
        if current_tier and line_stripped.startswith("- "):
            # Status glyphs: ✅ 🔵 ⬜ ⏸
            status = None
            rest = line_stripped[2:].strip()  # Remove "- "

            if rest.startswith("✅"):
                status = "✅"
                rest = rest[1:].strip()
            elif rest.startswith("🔵"):
                status = "🔵"
                rest = rest[1:].strip()
            elif rest.startswith("⬜"):
                status = "⬜"
                rest = rest[1:].strip()
            elif rest.startswith("⏸"):
                status = "⏸"
                rest = rest[1:].strip()

            if status:
                # Extract tag and title from "**[tag] Title...**"
                # Pattern: **[something] rest**
                if rest.startswith("**"):
                    # Find the closing **
                    match = re.match(r'\*\*\[([^\]]+)\]\s+(.+?)\*\*', rest)
                    if match:
                        tag = f"[{match.group(1)}]"
                        title = match.group(2)

                        tiers_data[current_tier].append({
                            "status": status,
                            "tag": tag,
                            "title": title
                        })

    # Convert to result format with counts
    tier_order = ["P0", "P1", "P2", "Needs decision"]
    for tier_name in tier_order:
        if tier_name in tiers_data:
            items = tiers_data[tier_name]
            done = sum(1 for item in items if item["status"] == "✅")
            inflight = sum(1 for item in items if item["status"] == "🔵")
            todo = sum(1 for item in items if item["status"] == "⬜")

            result["tiers"].append({
                "tier": tier_name,
                "items": items,
                "done": done,
                "inflight": inflight,
                "todo": todo,
                "total": len(items)
            })

    return result

def get_heartbeat_status():
    """Read daemon heartbeat age and status.

    Buckets age to prevent every-tick hash change: age is reported in 3-second buckets
    (e.g., 0-2s → 0, 3-5s → 3, 6-8s → 6, ...) so the heartbeat snapshot only changes
    every ~3 seconds, not every 1 second. This preserves the change-hash gate effectiveness.
    """
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
        # Bucket age to 3-second intervals to prevent hash churn
        age_bucketed = (age_seconds // 3) * 3
        alive = "ALIVE" if age_seconds < 300 else "STALE"
        return {"alive": alive, "age": age_bucketed, "threshold": 300}
    except:
        return {"alive": "unknown", "age": -1, "threshold": 300}


def get_monitor_heartbeat_status():
    """Read orchestration monitor heartbeat age and status.

    Buckets age to prevent every-tick hash change: age is reported in 3-second buckets
    (e.g., 0-2s → 0, 3-5s → 3, 6-8s → 6, ...) so the monitor snapshot only changes
    every ~3 seconds, not every 1 second. This preserves the change-hash gate effectiveness.
    """
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
        # Bucket age to 3-second intervals to prevent hash churn
        age_bucketed = (age_seconds // 3) * 3
        alive = "ALIVE" if age_seconds < 3600 else "STALE"
        return {"alive": alive, "age": age_bucketed, "threshold": 3600}
    except:
        return {"alive": "unknown", "age": -1, "threshold": 3600}


def get_fleet_agents():
    """Detect running subagents by calling dash-extra.mjs --json.

    dash-extra.mjs truncates agent ids to 13 characters for display. With enough
    concurrently-active agents, two distinct agents can share the same 13-char
    prefix and collide onto the same id. The dashboard keys DOM rows (and the
    click-to-expand lookup) by this id, so a collision silently merges two
    different agents into one row and can show mismatched detail on click. Since
    dash-extra.mjs is out of scope here, disambiguate post-hoc: keep the original
    (display-friendly) id as a prefix, but suffix it to guarantee uniqueness.
    """
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

    seen = {}
    for a in agents:
        if not isinstance(a, dict):
            continue
        aid = a.get("id", "")
        if aid in seen:
            seen[aid] += 1
            a["id"] = f"{aid}-{seen[aid]}"
        else:
            seen[aid] = 1
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
# Tracker Data Layer (state/tracker.json) — wave-8 CRUD API
# ==============================================================================

TRACKER_FILE = STATE_DIR / "tracker.json"


def load_tracker():
    """Load tracker.json, return empty tracker if missing or corrupt."""
    if not TRACKER_FILE.exists():
        return {"version": 1, "items": []}

    try:
        data = json.loads(TRACKER_FILE.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or "version" not in data:
            raise ValueError("Invalid tracker schema")
        return data
    except Exception as e:
        print(f"[tracker] Corrupt tracker.json: {e}", file=sys.stderr)
        corrupt_path = TRACKER_FILE.with_suffix('.json.corrupt')
        try:
            if TRACKER_FILE.exists():
                TRACKER_FILE.rename(corrupt_path)
        except:
            pass
        return {"version": 1, "items": []}


def save_tracker(tracker):
    """Save tracker atomically using temp file + os.replace."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TRACKER_FILE.with_suffix('.json.tmp')
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(tracker, f, indent=2)
        os.replace(str(temp_file), str(TRACKER_FILE))
    except Exception as e:
        print(f"[tracker] Error saving tracker: {e}", file=sys.stderr)
        try:
            temp_file.unlink()
        except:
            pass
        raise


def migrate_tracker_from_backlog():
    """One-time idempotent migration: AUDIT-BACKLOG.md -> tracker.json."""
    if TRACKER_FILE.exists():
        return load_tracker()

    backlog_data = parse_audit_backlog()
    if not backlog_data.get("tiers"):
        return {"version": 1, "items": []}

    items = []
    for tier_data in backlog_data["tiers"]:
        priority = tier_data["tier"]

        for backlog_item in tier_data.get("items", []):
            status_glyph = backlog_item["status"]

            if status_glyph == "✅":
                status, lane = "done", "done"
                tags = []
            elif status_glyph == "🔵":
                status, lane = "in-progress", "in-progress"
                tags = []
            elif status_glyph == "⏸":
                status, lane = "todo", "proposed"
                tags = ["needs-decision"]
            else:
                status, lane = "todo", "ranked"
                tags = []

            title = backlog_item.get("title", "")
            tag_prefix = backlog_item.get("tag", "")
            if tag_prefix:
                tag_value = tag_prefix.strip("[]")
                if tag_value and tag_value not in tags:
                    tags.insert(0, tag_value)

            item = {
                "id": secrets.token_hex(6),
                "title": title,
                "priority": priority,
                "status": status,
                "lane": lane,
                "source": "audit-backlog-migration",
                "tags": tags,
                "notes": None,
                "pr_link": None,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "completed_at": None
            }
            items.append(item)

    tracker = {"version": 1, "items": items}
    save_tracker(tracker)
    return tracker


def get_tracker_items(status=None, priority=None):
    """Retrieve tracker items with optional filters."""
    tracker = load_tracker()
    items = tracker.get("items", [])

    if status:
        items = [i for i in items if i.get("status") == status]
    if priority:
        items = [i for i in items if i.get("priority") == priority]

    return items


def create_tracker_item(data):
    """Create a new tracker item."""
    tracker = load_tracker()

    item = {
        "id": secrets.token_hex(6),
        "title": data.get("title", ""),
        "priority": data.get("priority", "P1"),
        "status": data.get("status", "todo"),
        "lane": data.get("lane", "proposed"),
        "source": data.get("source", "manual"),
        "tags": data.get("tags", []) if isinstance(data.get("tags"), list) else [],
        "notes": data.get("notes"),
        "pr_link": data.get("pr_link"),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "completed_at": None
    }

    tracker["items"].append(item)
    save_tracker(tracker)
    return item


def update_tracker_item(item_id, update_data):
    """Update a tracker item by id."""
    tracker = load_tracker()

    item = next((i for i in tracker["items"] if i["id"] == item_id), None)
    if not item:
        raise Exception(f"404 Item not found: {item_id}")

    for key in ["status", "lane", "priority", "notes", "pr_link", "tags"]:
        if key in update_data:
            item[key] = update_data[key]

    if update_data.get("status") == "done" and not item.get("completed_at"):
        item["completed_at"] = datetime.utcnow().isoformat() + "Z"

    save_tracker(tracker)
    return item


def delete_tracker_item(item_id):
    """Soft-delete a tracker item (mark as archived)."""
    tracker = load_tracker()

    item = next((i for i in tracker["items"] if i["id"] == item_id), None)
    if not item:
        raise Exception(f"404 Item not found: {item_id}")

    item["status"] = "archived"
    save_tracker(tracker)
    return item


# agent_id is attacker-controlled (GET /agent?id=...) and is spliced into a glob
# pattern below. Reject path-traversal segments and glob metacharacters before
# the pattern is ever built — a bare "/", "\", "..", "*", "?", "[" or "]" has no
# legitimate use in an agent id (ids are opaque hex-ish tokens).
_AGENT_ID_FORBIDDEN = re.compile(r'\.\.|[/\\*?\[\]]')


def extract_agent_dispatch_prompt(agent_id):
    """
    Extract dispatch prompt and metadata from agent output file.
    Returns dict with prompt, dispatcher, model, activity times, and message count.
    Robust: missing/invalid file -> {error: "..."}
    Security: rejects agent_id containing path-traversal or glob-metacharacter
    sequences before building any glob pattern, and refuses to return a match
    that resolves outside TRANSCRIPTS_ROOT (defense in depth). Error results
    carry "invalid": True when the input itself was rejected, so callers can
    map that to an HTTP 400 rather than a plain 404.

    CRITICAL: Use prefix-matching via glob, not exact match. The dashboard supplies
    truncated agent IDs; files on disk carry full IDs (e.g., a77b995bcdb953e9c.output).
    """
    try:
        if not agent_id or _AGENT_ID_FORBIDDEN.search(agent_id):
            return {"error": "invalid agent id", "invalid": True}

        # Prefix-match: search in TRANSCRIPTS_ROOT for files matching agent_id*.output
        if not TRANSCRIPTS_ROOT.exists():
            return {"error": f"transcripts root not found at {TRANSCRIPTS_ROOT}"}

        # Glob for matching files (prefix-match handles truncated IDs)
        matches = sorted(
            TRANSCRIPTS_ROOT.glob(f"**/{agent_id}*.output"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not matches:
            return {"error": f"transcript not found for {agent_id}"}
        output_file = matches[0]

        # Containment check: the resolved match must stay inside TRANSCRIPTS_ROOT.
        # Belt-and-suspenders alongside the input rejection above.
        try:
            is_contained = output_file.resolve().is_relative_to(TRANSCRIPTS_ROOT.resolve())
        except AttributeError:
            # Path.is_relative_to requires Python 3.9+; fall back for older runtimes.
            try:
                output_file.resolve().relative_to(TRANSCRIPTS_ROOT.resolve())
                is_contained = True
            except ValueError:
                is_contained = False
        if not is_contained:
            return {"error": "resolved path outside transcripts root", "invalid": True}

        dispatch_prompt = None
        message_count = 0
        model = None
        parent_uuid = None
        first_seen = None
        last_activity = None

        # Parse NDJSON (one JSON per line)
        with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            message_count = len(lines)

            # Get file mtime for activity time
            stat = output_file.stat()
            first_seen = int(stat.st_mtime)
            last_activity = int(stat.st_mtime)

            # First line should be type="user" with the dispatch prompt
            if lines:
                try:
                    first_line = json.loads(lines[0])
                    if first_line.get('type') == 'user':
                        msg = first_line.get('message', {})
                        dispatch_prompt = msg.get('content', '')
                        parent_uuid = first_line.get('parentUuid')
                except (json.JSONDecodeError, KeyError):
                    pass

            # Scan for model info in assistant messages
            for line in lines[1:20]:  # Check first ~20 lines
                try:
                    obj = json.loads(line)
                    if obj.get('type') == 'assistant' and not model:
                        if 'model' in obj:
                            model = obj.get('model')
                except (json.JSONDecodeError, KeyError):
                    pass

        if not dispatch_prompt:
            return {"error": f"no dispatch prompt found"}

        # Infer dispatcher: if parentUuid is null, it's main thread; otherwise parent agent
        dispatcher = "main thread" if parent_uuid is None else "parent agent"

        return {
            "id": agent_id,
            "dispatch_prompt": dispatch_prompt,
            "dispatcher": dispatcher,
            "model": model or "unknown",
            "message_count": message_count,
            "first_seen": first_seen,
            "last_activity": last_activity,
        }
    except Exception as e:
        return {"error": str(e)}


# ==============================================================================
# Realtime collector (SSE) — background thread, change-hash gated broadcast
# ==============================================================================

# How often the collector wakes up to check for changes. Cheap sources (heartbeat
# files, log tails) are re-read every tick; expensive sources (backlog parse, the
# `node dash-extra.mjs` subprocess for agents) are gated behind a mtime/fingerprint
# check so they're only re-derived when their underlying input actually changed.
COLLECTOR_INTERVAL = float(os.getenv("AESOP_UI_COLLECT_INTERVAL", "1.0"))
SSE_KEEPALIVE_SECONDS = 15
SSE_MAX_CLIENTS = 100  # Resource cap: reject new connections past this
SSE_QUEUE_MAXSIZE = 50  # Per-client bounded queue (drops oldest on overflow)
SSE_WRITE_TIMEOUT = 5.0  # Write timeout in seconds to prevent stalled clients

_sse_lock = threading.Lock()
_sse_clients = []  # list[queue.Queue]
_sse_client_count = 0  # Track concurrent connections for cap enforcement

_latest_lock = threading.Lock()
_latest_snapshots = {"data": None, "backlog": None, "agents": None, "tracker": None, "status": None}  # name -> json str

_collector_lock = threading.Lock()
_collector_started = False
_collector_stop_event = threading.Event()


def _snapshot_data():
    """Everything the 'data' SSE section covers (header, repos, events, alerts, messages)."""
    return {
        "watchdog": get_heartbeat_status(),
        "monitor": get_monitor_heartbeat_status(),
        "repos": get_repos_status(),
        "events": get_recent_events(),
        "alerts": get_alerts(),
        "messages": get_main_thread_messages(),
    }


def _transcripts_fingerprint():
    """Cheap fs-stat-only fingerprint of the transcripts tree.

    Used to decide whether it's worth re-invoking `node dash-extra.mjs` (which is
    comparatively expensive: process spawn + re-parsing every agent transcript).
    Only file count + max mtime — no file content is read.
    """
    try:
        if not TRANSCRIPTS_ROOT.exists():
            return (0, 0.0)
        count = 0
        latest = 0.0
        for p in TRANSCRIPTS_ROOT.glob("**/agent-*.jsonl"):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            count += 1
            if mtime > latest:
                latest = mtime
        return (count, latest)
    except Exception:
        return (0, 0.0)



# New functions for tracker SSE integration (to be inserted into serve.py)

def _snapshot_tracker():
    """Read tracker.json, return {items: [...]}."""
    tracker_file = STATE_DIR / "tracker.json"
    if not tracker_file.exists():
        return {"items": []}
    try:
        data = json.loads(tracker_file.read_text(encoding='utf-8'))
        if isinstance(data, dict) and "items" in data:
            return {"items": data.get("items", [])}
        return {"items": []}
    except Exception as e:
        print(f"[tracker] Snapshot error: {e}", file=sys.stderr)
        return {"items": []}


def _snapshot_orchestrator_status():
    """Read and normalize orchestrator-status.json."""
    status_file = STATE_DIR / "orchestrator-status.json"
    if not status_file.exists():
        return {"orchestrators": []}
    try:
        data = json.loads(status_file.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {"orchestrators": []}
        # Already normalized list shape
        if "orchestrators" in data and isinstance(data["orchestrators"], list):
            return data
        # Wrap bare object as single entry
        if "id" in data or "role" in data:
            age_seconds = 0
            stale = False
            try:
                updated_at_str = data.get("updated_at", "")
                if updated_at_str:
                    updated_at_str = updated_at_str.rstrip('Z')
                    updated_at = datetime.fromisoformat(updated_at_str)
                    age_seconds = int((datetime.utcnow() - updated_at).total_seconds())
                    stale = age_seconds > 1800
            except:
                pass
            entry = dict(data)
            entry["age_seconds"] = age_seconds
            entry["stale"] = stale
            return {"orchestrators": [entry]}
        return {"orchestrators": []}
    except Exception as e:
        print(f"[status] Snapshot error: {e}", file=sys.stderr)
        return {"orchestrators": []}


def drain_tracker_inbox():
    """Drain .tracker-inbox.jsonl, create items idempotently."""
    inbox_file = STATE_DIR / ".tracker-inbox.jsonl"
    if not inbox_file.exists():
        return []
    
    created = []
    try:
        content = inbox_file.read_text(encoding='utf-8')
        if not content.strip():
            inbox_file.unlink()
            return []
        
        lines = content.strip().splitlines()
        tracker = load_tracker()
        existing_hashes = set()
        for item in tracker.get("items", []):
            source = item.get("source", "")
            title = item.get("title", "")
            h = hashlib.sha256((source + ":" + title).encode()).hexdigest()
            existing_hashes.add(h)
        
        rejects = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    rejects.append(line)
                    continue
                
                source = entry.get("source", "")
                title = entry.get("title", "")
                h = hashlib.sha256((source + ":" + title).encode()).hexdigest()
                
                if h not in existing_hashes:
                    item = create_tracker_item(entry)
                    created.append(item)
                    existing_hashes.add(h)
            except json.JSONDecodeError:
                rejects.append(line)
            except Exception as e:
                rejects.append(line + " # " + str(e))
        
        if rejects:
            rejects_file = inbox_file.with_name(".tracker-inbox.rejects")
            rejects_file.write_text("\n".join(rejects) + "\n", encoding='utf-8')
        
        inbox_file.unlink()
    except Exception as e:
        print(f"[inbox] Drain error: {e}", file=sys.stderr)
    
    return created


def register_sse_client():
    """Register a new SSE client queue. Returns the queue to read events from, or None if cap exceeded."""
    with _sse_lock:
        if len(_sse_clients) >= SSE_MAX_CLIENTS:
            return None  # Caller will return HTTP 503
        q = queue.Queue(maxsize=SSE_QUEUE_MAXSIZE)
        _sse_clients.append(q)
    return q


def unregister_sse_client(q):
    """Remove a disconnected SSE client's queue."""
    with _sse_lock:
        if q in _sse_clients:
            _sse_clients.remove(q)


def broadcast_sse(event_name, payload):
    """Push (event_name, payload) onto every currently-registered client queue.

    If a client queue is full, drop the oldest event to make room (bounded backpressure).
    This prevents one slow client from blocking the broadcast.
    """
    with _sse_lock:
        clients = list(_sse_clients)
    for q in clients:
        try:
            q.put_nowait((event_name, payload))
        except queue.Full:
            # Queue is full: drop the oldest event and retry
            try:
                q.get_nowait()  # Remove oldest
                q.put_nowait((event_name, payload))  # Add new
            except Exception:
                import sys
                print(f"[collector_loop] Exception: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        except Exception:
            pass


def _maybe_emit(name, snapshot, last_hashes):
    """Hash-gate: only store + broadcast a section if its content actually changed."""
    payload = json.dumps(snapshot, default=str, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if last_hashes.get(name) == digest:
        return
    last_hashes[name] = digest
    with _latest_lock:
        _latest_snapshots[name] = payload
    broadcast_sse(name, payload)


def collector_loop(stop_event):
    """Background loop: poll cheap sources, gate expensive ones, broadcast on change."""
    last_hashes = {}
    last_backlog_mtime = object()  # sentinel guaranteed != any real mtime/None
    last_agents_fingerprint = None
    cached_backlog_snapshot = {"tiers": []}
    cached_agents_snapshot = []
    last_tracker_mtime = object()
    last_status_mtime = object()
    cached_tracker_snapshot = {'items': []}
    cached_status_snapshot = {'orchestrators': []}

    while not stop_event.is_set():
        try:
            _maybe_emit("data", _snapshot_data(), last_hashes)

            try:
                backlog_mtime = AUDIT_BACKLOG_FILE.stat().st_mtime if AUDIT_BACKLOG_FILE.exists() else None
            except OSError:
                backlog_mtime = None
            if backlog_mtime != last_backlog_mtime:
                last_backlog_mtime = backlog_mtime
                cached_backlog_snapshot = parse_audit_backlog()
            _maybe_emit("backlog", cached_backlog_snapshot, last_hashes)

            fingerprint = _transcripts_fingerprint()
            if fingerprint != last_agents_fingerprint:
                last_agents_fingerprint = fingerprint
                cached_agents_snapshot = get_fleet_agents()
            _maybe_emit("agents", cached_agents_snapshot, last_hashes)

            # Emit tracker section (mtime-gated)
            try:
                tracker_mtime = (STATE_DIR / "tracker.json").stat().st_mtime if (STATE_DIR / "tracker.json").exists() else None
            except OSError:
                tracker_mtime = None
            if tracker_mtime != last_tracker_mtime:
                last_tracker_mtime = tracker_mtime
                cached_tracker_snapshot = _snapshot_tracker()
            _maybe_emit("tracker", cached_tracker_snapshot, last_hashes)

            # Emit status section (mtime-gated)
            try:
                status_mtime = (STATE_DIR / "orchestrator-status.json").stat().st_mtime if (STATE_DIR / "orchestrator-status.json").exists() else None
            except OSError:
                status_mtime = None
            if status_mtime != last_status_mtime:
                last_status_mtime = status_mtime
                cached_status_snapshot = _snapshot_orchestrator_status()
            _maybe_emit("status", cached_status_snapshot, last_hashes)

            # Drain inbox
            try:
                drain_tracker_inbox()
            except Exception as e:
                print(f"[collector] Inbox drain error: {e}", file=sys.stderr, flush=True)
        except Exception as e:
            import sys
            print(f"[collector_loop] Exception: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        stop_event.wait(COLLECTOR_INTERVAL)


def start_collector_thread():
    """Idempotently start the background collector daemon thread (safe to call from
    multiple request handlers / run_server — only the first call actually starts it)."""
    global _collector_started
    with _collector_lock:
        if _collector_started:
            return
        _collector_started = True
        t = threading.Thread(target=collector_loop, args=(_collector_stop_event,), daemon=True)
        t.start()


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
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Aesop Fleet Dashboard</title>
    <script>
        // CSRF token injected by server (same-origin JS can read this)
        window.__AESOP_CSRF_TOKEN__ = """ + json.dumps(SESSION_TOKEN) + """;
    </script>
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

        .header { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; padding: 12px; background: #1a1a1a; border-radius: 4px; }
        .header-item { flex: 1 1 140px; min-width: 120px; }
        .header-label { font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 4px; }
        .header-value { font-size: 14px; color: #fff; font-weight: bold; }
        .status-alive { color: #0a0; }
        .status-stale { color: #f44; }
        .status-unknown { color: #999; }

        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
        @media (max-width: 1200px) { .grid { grid-template-columns: 1fr; } }
        /* Responsive header: items pack 2-per-row on narrow viewports instead of overflowing */
        @media (max-width: 900px) { .header { gap: 12px; } .header-item { flex-basis: calc(50% - 12px); } }

        .panel { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; }
        .panel-title { font-size: 12px; color: #8ac; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
        .panel-title-emoji { font-size: 14px; }

        /* Agent row expand/collapse */
        .agent-row { cursor: pointer; padding: 8px; margin-bottom: 4px; background: #0f0f0f; border: 1px solid #2a2a2a; border-radius: 3px; transition: all 0.2s ease; display: flex; align-items: center; gap: 8px; }
        .agent-row:hover { background: #151515; border-color: #444; }
        .agent-row.expanded { background: #1a1a1a; border-color: #8ac; }
        .agent-status-icon { font-size: 12px; width: 14px; }
        .agent-row-header { flex: 1; font-size: 12px; display: flex; gap: 12px; align-items: center; }
        .agent-id-badge { color: #8ac; font-weight: bold; }
        .agent-age { color: #666; font-size: 11px; }
        .agent-preview { color: #999; font-size: 11px; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .agent-expand-toggle { color: #8ac; font-size: 14px; font-weight: bold; transition: transform 0.2s ease, color 0.2s ease; }
        .agent-row:hover .agent-expand-toggle { color: #fff; }
        .agent-row.expanded .agent-expand-toggle { transform: rotate(90deg); }

        .agent-details { display: none; margin-top: 8px; padding: 12px; background: #0f0f0f; border-left: 3px solid #8ac; border-radius: 2px; max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
        .agent-row.expanded .agent-details { display: block; max-height: 600px; }
        .detail-row { margin-bottom: 8px; font-size: 11px; }
        .detail-label { color: #8ac; font-weight: bold; display: inline-block; width: 100px; }
        .detail-value { color: #ccc; word-break: break-all; }
        .dispatch-prompt { background: #0a0a0a; border: 1px solid #333; border-radius: 2px; padding: 8px; margin-top: 6px; max-height: 300px; overflow-y: auto; font-size: 11px; color: #ccc; font-family: 'Monaco', 'Menlo', monospace; white-space: pre-wrap; word-wrap: break-word; }

        .item { padding: 8px 0; font-size: 12px; border-bottom: 1px solid #2a2a2a; }
        .item:last-child { border-bottom: none; }
        .item-id { color: #8ac; font-weight: bold; }
        .item-age { color: #999; margin: 0 8px; }
        .item-status { padding: 2px 6px; border-radius: 2px; font-size: 10px; font-weight: bold; }
        .status-running { background: #88f; color: #000; }
        .status-done { background: #0a0; color: #000; }

        .inbox-box { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; margin-bottom: 20px; }
        .inbox-label { font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 8px; }
        .inbox-input { width: 100%; padding: 8px; background: #0a0a0a; border: 1px solid #333; color: #e0e0e0; border-radius: 2px; font-size: 12px; font-family: inherit; }
        .inbox-input:focus { outline: none; border-color: #8ac; }
        .inbox-button { background: #8ac; color: #000; border: none; padding: 8px 16px; border-radius: 2px; margin-top: 8px; cursor: pointer; font-weight: bold; font-size: 12px; }
        .inbox-button:hover { background: #9bd; }
        .inbox-button:disabled { background: #555; cursor: not-allowed; }
        .inbox-status { font-size: 11px; color: #0a0; margin-top: 4px; display: none; }

        /* Alert box styling: distinct alarm treatment when alerts exist */
        .alerts-box { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; }
        .alerts-box.has-alerts { border-color: #f44; border-width: 2px; background: #1a0a0a; }
        .alerts-box.has-high-alerts { border-color: #f44; border-width: 2px; background: #1a0808; }
        .alerts-box.has-med-alerts { border-color: #f80; border-width: 2px; background: #1a1008; }
        .alert-line { font-size: 11px; padding: 4px 0; color: #f44; font-family: monospace; }
        .alert-line.severity-high { color: #f44; font-weight: bold; }
        .alert-line.severity-med { color: #f80; font-weight: bold; }
        .alert-none { color: #666; }

        /* Alert count in header: scales with severity */
        #alert-count { color: #999; }
        #alert-count.alarm-high { color: #f44; font-weight: bold; }
        #alert-count.alarm-med { color: #f80; font-weight: bold; }

        .messages-box { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; max-height: 400px; overflow-y: auto; }
        .message { padding: 8px 0; border-bottom: 1px solid #2a2a2a; font-size: 11px; }
        .message:last-child { border-bottom: none; }
        .message-role { color: #8ac; font-weight: bold; }
        .message-time { color: #666; font-size: 10px; margin-left: 8px; }
        .message-text { color: #ccc; margin-top: 4px; }

        .backlog-tier { margin-bottom: 16px; padding: 12px; background: #0f0f0f; border: 1px solid #2a2a2a; border-radius: 3px; }
        .backlog-tier-header { font-size: 12px; font-weight: bold; color: #8ac; margin-bottom: 8px; display: flex; align-items: center; gap: 12px; }
        .backlog-tier-name { font-size: 13px; }
        .backlog-progress-container { width: 100%; background: #0a0a0a; border: 1px solid #333; border-radius: 2px; height: 20px; overflow: hidden; margin-bottom: 6px; }
        .backlog-progress-bar { height: 100%; display: flex; background: #0a0a0a; }
        .backlog-progress-done { background: #0a0; }
        .backlog-progress-inflight { background: #88f; }
        .backlog-progress-empty { background: #333; flex: 1; }
        .backlog-stats { font-size: 11px; color: #999; }
        .backlog-items { font-size: 11px; margin-top: 8px; max-height: 200px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #555 #0a0a0a; }
        /* Truncation cue: a scrollable (overflowing) tier gets a visible scrollbar + bottom fade so "more below" is obvious */
        .backlog-items::-webkit-scrollbar { width: 8px; }
        .backlog-items::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
        .backlog-items::-webkit-scrollbar-track { background: #0a0a0a; }
        .backlog-items.has-overflow { -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 18px), transparent); mask-image: linear-gradient(to bottom, #000 calc(100% - 18px), transparent); }
        .backlog-item { padding: 4px 0; color: #ccc; display: flex; gap: 8px; align-items: flex-start; }
        .backlog-item-glyph { min-width: 14px; font-size: 12px; }
        .backlog-item-tag { color: #8ac; font-weight: bold; min-width: 60px; }
        .backlog-item-title { color: #bbbbbb; flex: 1; word-break: break-word; }
        .backlog-item.done { padding: 2px 0; opacity: 0.55; }
        .backlog-item.done .backlog-item-title { opacity: 0.55; font-size: 10px; }

        .loading { color: #666; font-style: italic; }
        .error { color: #f44; }
        .fade-in { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0.5; } to { opacity: 1; } }

        /* Orchestrator status banner */
        #orchestrator-banner { margin-bottom: 16px; padding: 12px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px; }
        .status-none { color: #999; }
        .status-activity { color: #8ac; font-weight: bold; }
        .status-age { color: #666; font-size: 11px; margin-left: 8px; }
        .status-stale-warn { color: #f80; font-weight: bold; }
        .audit-banner { background: #1a1408; border: 1px solid #f80; border-radius: 4px; padding: 12px; margin: 12px 0; }
        .audit-banner-title { color: #f80; font-weight: bold; font-size: 12px; margin-bottom: 6px; }
        .audit-ascii { font-family: 'Monaco', 'Menlo', monospace; font-size: 11px; color: #8ac; line-height: 1.3; white-space: pre; margin: 6px 0; }
        .audit-marquee { animation: marqueeAnim 2s linear infinite; }
        @keyframes marqueeAnim { 0% { content: '░▒▓'; } 33% { content: '▒▓░'; } 66% { content: '▓░▒'; } }

        /* Tracker lanes */
        .tracker-lanes { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-bottom: 20px; }
        .tracker-lane { background: #0f0f0f; border: 1px solid #2a2a2a; border-radius: 4px; padding: 12px; }
        .lane-header { font-size: 12px; font-weight: bold; color: #8ac; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
        .lane-count { font-size: 11px; color: #666; }
        .lane-items { display: flex; flex-direction: column; gap: 8px; }
        .tracker-item { background: #1a1a1a; border: 1px solid #333; border-radius: 3px; padding: 10px; cursor: pointer; transition: all 0.2s ease; }
        .tracker-item:hover { border-color: #8ac; background: #151515; }
        .tracker-item-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
        .tracker-item-title { flex: 1; font-size: 12px; font-weight: bold; color: #e0e0e0; word-break: break-word; }
        .priority-chip { display: inline-block; padding: 2px 6px; border-radius: 2px; font-size: 10px; font-weight: bold; text-transform: uppercase; }
        .priority-p0 { background: #f44; color: #fff; }
        .priority-p1 { background: #f80; color: #000; }
        .priority-p2 { background: #88f; color: #000; }
        .priority-p3 { background: #666; color: #bbb; }
        .tracker-item-tags { font-size: 10px; color: #8ac; margin-bottom: 6px; }
        .tag { display: inline-block; margin-right: 4px; padding: 1px 3px; background: #0a0a0a; border: 1px solid #8ac; border-radius: 2px; }
        .tracker-item-details { display: none; margin-top: 8px; padding-top: 8px; border-top: 1px solid #2a2a2a; font-size: 11px; color: #ccc; }
        .tracker-item.expanded .tracker-item-details { display: block; }
        .detail-row { margin-bottom: 4px; }
        .detail-label { color: #8ac; font-weight: bold; }
        .detail-value { color: #999; }
        .tracker-item-actions { display: flex; gap: 4px; margin-top: 8px; }
        .tracker-action-btn { flex: 1; padding: 4px 8px; background: #2a2a2a; border: 1px solid #444; color: #8ac; border-radius: 2px; cursor: pointer; font-size: 10px; font-weight: bold; transition: all 0.2s ease; }
        .tracker-action-btn:hover { background: #333; border-color: #8ac; }
        .tracker-action-btn.primary { background: #8ac; color: #000; border-color: #8ac; }
        .tracker-action-btn.primary:hover { background: #9bd; }
        .tracker-action-btn.danger { background: #f44; color: #fff; border-color: #f44; }
        .tracker-action-btn.danger:hover { background: #f55; }

        /* Tracker add-item form */
        .tracker-form { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 12px; margin-bottom: 20px; }
        .form-group { margin-bottom: 8px; }
        .form-label { font-size: 11px; color: #8ac; font-weight: bold; text-transform: uppercase; margin-bottom: 4px; display: block; }
        .form-input { width: 100%; padding: 6px; background: #0a0a0a; border: 1px solid #333; color: #e0e0e0; border-radius: 2px; font-size: 12px; font-family: inherit; box-sizing: border-box; }
        .form-input:focus { outline: none; border-color: #8ac; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .form-submit { padding: 8px 16px; background: #8ac; color: #000; border: none; border-radius: 2px; font-weight: bold; font-size: 11px; cursor: pointer; transition: all 0.2s ease; }
        .form-submit:hover { background: #9bd; }
        .form-submit:disabled { background: #555; cursor: not-allowed; }
        .tracker-archived-summary { font-size: 11px; color: #666; padding: 8px; background: #0f0f0f; border: 1px solid #2a2a2a; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Aesop Fleet Dashboard</h1>

        <div id="orchestrator-banner" style="display: none;">
            <div class="header-label">Orchestrator Status</div>
            <div id="orchestrator-status" class="status-none">—</div>
        </div>
        <div id="audit-banner" class="audit-banner" style="display: none;" aria-hidden="true">
            <div class="audit-banner-title">AUDIT CYCLE RUNNING</div>
            <pre class="audit-ascii">   .-.--.        ___
  ( o___ )----- (o,o)
   `-.__.'       \_/   <span class="audit-marquee">░▒▓</span> scanning...</pre>
        </div>

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
            <div class="header-item" style="flex: 0 0 auto; text-align: right;">
                <div class="header-label">Live</div>
                <div class="header-value">
                    <span id="conn-live" style="color: #0a0;">● live</span>
                    <span id="conn-reconnecting" style="color: #f80; display: none;">◌ reconnecting…</span>
                    <span id="connection-degraded" style="color: #f44; display: none; margin-left: 8px;">⚠ frame error</span>
                </div>
            </div>
        </div>

        <div class="grid">
            <div class="panel">
                <div class="panel-title">
                    <span class="panel-title-emoji">⚡</span>
                    <span>Fleet Agents (<span id="running-agents-count">0</span> active)</span>
                </div>
                <div id="agents-list" class="loading">—</div>
            </div>

            <div class="alerts-box">
                <div class="panel-title">Security Alerts (Unreviewed)</div>
                <div id="alerts-list" class="alert-none">—</div>
            </div>
        </div>

        <div class="inbox-box">
            <div class="inbox-label">Queue Work (Read by Orchestrator Each Turn)</div>
            <input type="text" class="inbox-input" id="inbox-input" placeholder="Type your task here...">
            <button class="inbox-button" id="inbox-button">Send to Inbox</button>
            <div class="inbox-status" id="inbox-status">Queued ✓</div>
        </div>

        <div class="tracker-form">
            <div class="form-label">Add Work Item</div>
            <div class="form-group">
                <input type="text" class="form-input" id="tracker-title" placeholder="Title" maxlength="200">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <select class="form-input" id="tracker-priority" style="appearance: none; padding-right: 24px;">
                        <option value="P0">P0 — Critical</option>
                        <option value="P1">P1 — High</option>
                        <option value="P2" selected>P2 — Medium</option>
                        <option value="P3">P3 — Low</option>
                    </select>
                </div>
                <div class="form-group">
                    <button class="form-submit" id="tracker-add-btn">+ Add Item</button>
                </div>
            </div>
            <div class="form-group">
                <input type="text" class="form-input" id="tracker-notes" placeholder="Notes (optional)" maxlength="500">
            </div>
        </div>

        <div id="tracker-container" class="loading" style="margin-bottom: 20px;">
            <div class="tracker-lanes" id="tracker-lanes">—</div>
        </div>

        <div class="panel" style="margin-bottom: 20px;">
            <div class="panel-title">
                <span class="panel-title-emoji">📋</span>
                <span>Audit Backlog — Clearing Progress</span>
            </div>
            <div id="backlog-tiers" class="loading">—</div>
        </div>

        <div class="grid">
            <div class="panel">
                <div class="panel-title">Recent Events (Last 8)</div>
                <div id="events-list" class="loading">—</div>
            </div>

            <div class="panel">
                <div class="panel-title">Repos Status</div>
                <div id="repos-list" class="loading">—</div>
            </div>
        </div>

        <div class="panel">
            <div class="panel-title">Main-Thread Prompts (Last ~12 Messages)</div>
            <div class="messages-box" id="messages-list" class="loading">—</div>
        </div>

        <div style="text-align: center; margin-top: 30px; color: #666; font-size: 11px;">
            Realtime via SSE (push on change) · Click agent rows to inspect dispatches ·
            <button id="manual-refresh-button" style="background: none; border: 1px solid #444; color: #999; border-radius: 2px; padding: 2px 8px; cursor: pointer; font-size: 11px;">⟳ Refresh now</button>
        </div>
    </div>

    <script>
        // ------------------------------------------------------------------
        // Realtime model: one EventSource('/events'), keyed in-place DOM
        // patching per section. No interval polling, no full-page rebuild —
        // clicks, expansion state, scroll position, and text selection all
        // survive indefinitely because existing DOM nodes are mutated in
        // place rather than replaced.
        // ------------------------------------------------------------------

        // Client-side cache of the last snapshot per section, used by the
        // click handler (synchronous lookup — no network round-trip on click)
        // and by the manual refresh fallback.
        let latestAgents = [];
        let latestBacklog = { tiers: [] };
        let latestData = {};

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

        // CSS.escape wrapper (with a conservative fallback) so item/tier keys
        // containing brackets, quotes, etc. can't break attribute selectors.
        function cssEscape(s) {
            if (window.CSS && typeof CSS.escape === 'function') return CSS.escape(String(s));
            return String(s).replace(/[^a-zA-Z0-9_-]/g, (c) => '\\\\' + c);
        }

        // Test hook: expose cache size for verify_dash.py
        window.__getPromptCacheSize = function() { return promptCache.size; };

        function setConnectionStatus(connected) {
            document.getElementById('conn-live').style.display = connected ? '' : 'none';
            document.getElementById('conn-reconnecting').style.display = connected ? 'none' : '';
        }

        function setConnectionDegraded(degraded) {
            document.getElementById('connection-degraded').style.display = degraded ? '' : 'none';
        }

        // ---- header (watchdog / monitor / alert count) --------------------
        function getAlertSeverity(alerts) {
            // Scan alert lines for severity keywords (HIGH takes precedence over MED)
            if (!alerts || !alerts.lines || alerts.lines.length === 0) return 'none';
            const text = alerts.lines.join(' ').toUpperCase();
            if (text.includes('HIGH')) return 'high';
            if (text.includes('MED') || text.includes('MEDIUM')) return 'med';
            return 'low';
        }

        function patchHeader(data) {
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

            // Alert count: color scales with severity
            const alertCount = document.getElementById('alert-count');
            const count = (data.alerts && data.alerts.count) || 0;
            alertCount.textContent = count;
            alertCount.className = ''; // Reset classes
            if (count > 0) {
                const severity = getAlertSeverity(data.alerts);
                alertCount.classList.add('alarm-' + severity);
            }
        }

        function patchHeaderRunningCount(agents) {
            const running = (agents || []).filter(a => a.status === 'running').length;
            document.getElementById('running-count').textContent = running;
            document.getElementById('running-agents-count').textContent = (agents || []).length;
        }

        // ---- agents panel: keyed rows, click-to-expand survives updates --
        function renderAgentDetails(row, agent) {
            const detailsDiv = row.querySelector('.agent-details');
            const now = Date.now();
            const startTime = agent.startedAt ? new Date(agent.startedAt).getTime() : now;
            const runtime = Math.floor((now - startTime) / 1000);
            const runtimeStr = runtime < 60 ? runtime + 's' : Math.floor(runtime / 60) + 'm';

            // BUGFIX: Field-level patching — only update nodes whose content changed.
            // Do NOT clear detailsDiv.textContent; instead update existing fields or
            // append new ones. This preserves scroll position and text selection in the
            // prompt box.
            const fields = [
                ['Task:', agent.taskLabel || 'N/A'],
                ['Status:', agent.status || 'unknown'],
                ['Runtime:', runtimeStr],
                ['Tokens:', String(agent.tokensUsed || 0)],
            ];
            
            // Ensure all detail rows exist and update values atomically
            fields.forEach(([label, value]) => {
                let rowEl = detailsDiv.querySelector(`[data-detail-label="${label}"]`);
                if (!rowEl) {
                    rowEl = document.createElement('div');
                    rowEl.className = 'detail-row';
                    rowEl.dataset.detailLabel = label;
                    const labelEl = document.createElement('span');
                    labelEl.className = 'detail-label';
                    labelEl.textContent = label;
                    const valueEl = document.createElement('span');
                    valueEl.className = 'detail-value';
                    valueEl.textContent = value;
                    rowEl.appendChild(labelEl);
                    rowEl.appendChild(document.createTextNode(' '));
                    rowEl.appendChild(valueEl);
                    detailsDiv.appendChild(rowEl);
                } else {
                    // Update value only if it changed
                    const valueEl = rowEl.querySelector('.detail-value');
                    if (valueEl && valueEl.textContent !== value) {
                        valueEl.textContent = value;
                    }
                }
            });

            // Ensure prompt label row exists
            let promptLabelRow = detailsDiv.querySelector('[data-detail-label="Prompt:"]');
            if (!promptLabelRow) {
                promptLabelRow = document.createElement('div');
                promptLabelRow.className = 'detail-row';
                promptLabelRow.dataset.detailLabel = 'Prompt:';
                const promptLabel = document.createElement('span');
                promptLabel.className = 'detail-label';
                promptLabel.textContent = 'Prompt:';
                promptLabelRow.appendChild(promptLabel);
                detailsDiv.appendChild(promptLabelRow);
            }

            // Ensure prompt box exists and update only if content changed
            let promptBox = detailsDiv.querySelector('.dispatch-prompt');
            if (!promptBox) {
                promptBox = document.createElement('div');
                promptBox.className = 'dispatch-prompt';
                detailsDiv.appendChild(promptBox);
            }
            
            // The list payload (dash-extra) has no prompt; the full dispatch prompt
            // comes from GET /agent?id=. Fetch once per agent and cache — push
            // updates re-render expanded rows, and must neither clobber a loaded
            // prompt nor refetch on every SSE event.
            const cached = promptCache.get(agent.id);
            const promptText = (typeof cached === 'string') ? cached : 'Loading…';
            if (promptBox.textContent !== promptText) {
                promptBox.textContent = promptText;
            }
            
            if (!promptCache.has(agent.id)) fetchDispatchPrompt(agent.id);
        }

        const promptCache = new Map();  // agent id -> prompt string (null while in flight)
        function fetchDispatchPrompt(agentId) {
            promptCache.set(agentId, null);
            fetch('/agent?id=' + encodeURIComponent(agentId))
                .then(r => r.json())
                .then(d => {
                    const text = d.dispatch_prompt || ('(' + (d.error || 'no prompt found') + ')');
                    promptCache.set(agentId, text);
                    const row = document.querySelector(`[data-agent-id="${cssEscape(agentId)}"]`);
                    if (row) {
                        const box = row.querySelector('.dispatch-prompt');
                        if (box) box.textContent = text;  // textContent: XSS-safe
                    }
                })
                .catch(() => { promptCache.delete(agentId); });
        }

        function buildAgentRow(a) {
            const row = document.createElement('div');
            row.className = 'agent-row';
            row.dataset.agentId = a.id;
            row.innerHTML = `
                <span class="agent-status-icon"></span>
                <div class="agent-row-header">
                    <span class="agent-id-badge"></span>
                    <span class="agent-age"></span>
                    <span class="agent-preview"></span>
                </div>
                <span class="agent-expand-toggle">▶</span>
                <div class="agent-details"></div>
            `;
            return row;
        }

        function patchAgents(agents) {
            latestAgents = agents || [];
            const container = document.getElementById('agents-list');
            container.classList.remove('loading');

            if (latestAgents.length === 0) {
                if (!container.querySelector('.empty-state')) {
                    container.innerHTML = '<div class="empty-state" style="color: #aaaaaa; font-size: 12px;">💤 No active agents — fleet is idle</div>';
                }
                return;
            }
            const emptyState = container.querySelector('.empty-state');
            if (emptyState) emptyState.remove();

            const newIds = new Set(latestAgents.map(a => a.id));
            container.querySelectorAll('[data-agent-id]').forEach(row => {
                if (!newIds.has(row.dataset.agentId)) {
                    // BUGFIX: Evict promptCache entries for agents no longer present
                    promptCache.delete(row.dataset.agentId);
                    row.remove();
                }
            });

            latestAgents.forEach(a => {
                const statusEmoji = a.status === 'running' ? '🟢' : (a.status === 'idle' ? '⚪' : '⚠️');
                const preview = (a.hint || '').substring(0, 60);

                let row = container.querySelector(`[data-agent-id="${cssEscape(a.id)}"]`);
                if (!row) {
                    row = buildAgentRow(a);
                    container.appendChild(row);
                }
                row.querySelector('.agent-status-icon').textContent = statusEmoji;
                row.querySelector('.agent-id-badge').textContent = a.id;
                row.querySelector('.agent-age').textContent = a.age_s + 's';
                row.querySelector('.agent-preview').textContent = preview;

                // If this row is currently expanded, keep its live fields (runtime,
                // tokens, age) fresh in place — the click-to-expand state itself is
                // never touched here, so it survives every push update.
                if (row.classList.contains('expanded')) {
                    renderAgentDetails(row, a);
                }
            });
        }

        // Event delegation on the stable container: attached once, works for
        // every row (past, present, and future) without re-binding per row.
        document.getElementById('agents-list').addEventListener('click', function (e) {
            const row = e.target.closest('.agent-row');
            if (!row || !this.contains(row)) return;
            row.classList.toggle('expanded');
            if (row.classList.contains('expanded')) {
                const agent = latestAgents.find(a => a.id === row.dataset.agentId);
                if (agent) {
                    renderAgentDetails(row, agent);
                } else {
                    row.querySelector('.agent-details').textContent = 'Agent details not found';
                }
            }
        });

        // ---- repos / events / alerts / messages: presentational lists,
        // no click/expand state to preserve, so a hash-gated (not interval-
        // gated) full swap per section is safe. ----------------------------
        function patchRepos(repos) {
            const reposList = document.getElementById('repos-list');
            reposList.classList.remove('loading');
            if (repos && repos.length > 0) {
                reposList.innerHTML = repos.map(r => {
                    const repo = r.repo || Object.keys(r)[0] || 'unknown';
                    const state = r.state || r[repo] || 'unknown';
                    return `<div class="item"><span class="item-id">${sanitize(repo.substring(0, 30))}</span> <span style="color: #999;">${sanitize(state)}</span></div>`;
                }).join('');
            } else {
                reposList.textContent = '(no repos)';
                reposList.style.color = '#666';
            }
        }

        function patchEvents(events) {
            const eventsList = document.getElementById('events-list');
            eventsList.classList.remove('loading');
            if (events && events.length > 0) {
                eventsList.innerHTML = events.map(e =>
                    `<div class="item"><span style="color: #999; font-size: 10px;">${sanitize(e.substring(0, 80))}</span></div>`
                ).join('');
            } else {
                eventsList.textContent = '(no recent events)';
                eventsList.style.color = '#aaaaaa';
            }
        }

        function patchAlerts(alerts) {
            const alertsList = document.getElementById('alerts-list');
            const alertsBox = document.querySelector('.alerts-box');

            // Defensive: ensure alerts-box exists before styling it
            if (alertsBox) {
                // Reset alerts-box styling
                alertsBox.className = 'alerts-box';

                if (alerts && alerts.lines && alerts.lines.length > 0) {
                    // Determine highest severity to style the container
                    const text = alerts.lines.join(' ').toUpperCase();
                    if (text.includes('HIGH')) {
                        alertsBox.classList.add('has-high-alerts');
                    } else if (text.includes('MED') || text.includes('MEDIUM')) {
                        alertsBox.classList.add('has-med-alerts');
                    } else {
                        alertsBox.classList.add('has-alerts');
                    }
                }
            }

            if (alerts && alerts.lines && alerts.lines.length > 0) {
                alertsList.innerHTML = alerts.lines.map(line => {
                    const upperLine = line.toUpperCase();
                    let severity = '';
                    if (upperLine.includes('HIGH')) {
                        severity = 'severity-high';
                    } else if (upperLine.includes('MED') || upperLine.includes('MEDIUM')) {
                        severity = 'severity-med';
                    }
                    return `<div class="alert-line ${severity}">${sanitize(line.substring(0, 120))}</div>`;
                }).join('');
            } else {
                alertsList.innerHTML = '<div class="alert-none">(no alerts)</div>';
            }
        }

        function patchMessages(messages) {
            const messagesList = document.getElementById('messages-list');
            messagesList.classList.remove('loading');
            if (messages && messages.length > 0) {
                messagesList.innerHTML = messages.map(m =>
                    `<div class="message"><span class="message-role">${sanitize(m.role)}</span><span class="message-time">${formatTimestamp(m.timestamp)}</span><div class="message-text">${sanitize(m.text)}</div></div>`
                ).join('');
            } else {
                messagesList.textContent = '(no messages)';
                messagesList.style.color = '#aaaaaa';
            }
        }

        function patchDataSection(data) {
            latestData = data || {};
            patchHeader(latestData);
            patchRepos(latestData.repos || []);
            patchEvents(latestData.events || []);
            patchAlerts(latestData.alerts || { count: 0, lines: [] });
            patchMessages(latestData.messages || []);
        }

        // ---- audit backlog panel: tiers + items keyed, so live status
        // changes (⬜ → 🔵 → ✅) update in place without losing scroll or
        // flashing the whole panel on every unrelated tick. -----------------
        function backlogItemKey(item) {
            return (item.tag || '') + '||' + (item.title || '');
        }

        function buildBacklogTier(tier) {
            const tierEl = document.createElement('div');
            tierEl.className = 'backlog-tier';
            tierEl.dataset.tier = tier.tier;
            tierEl.innerHTML = `
                <div class="backlog-tier-header"><span class="backlog-tier-name"></span></div>
                <div class="backlog-progress-container">
                    <div class="backlog-progress-bar">
                        <div class="backlog-progress-done"></div>
                        <div class="backlog-progress-inflight"></div>
                        <div class="backlog-progress-empty"></div>
                    </div>
                </div>
                <div class="backlog-stats"></div>
                <div class="backlog-items"></div>
            `;
            return tierEl;
        }

        function buildBacklogItem(key) {
            const itemEl = document.createElement('div');
            itemEl.className = 'backlog-item';
            itemEl.dataset.itemKey = key;
            itemEl.innerHTML = `
                <span class="backlog-item-glyph"></span>
                <span class="backlog-item-tag"></span>
                <span class="backlog-item-title"></span>
            `;
            return itemEl;
        }

        function patchBacklog(backlogData) {
            latestBacklog = backlogData || { tiers: [] };
            const container = document.getElementById('backlog-tiers');
            container.classList.remove('loading');
            const tiers = latestBacklog.tiers || [];

            if (tiers.length === 0) {
                if (!container.querySelector('.empty-state')) {
                    container.innerHTML = '<div class="empty-state" style="color: #aaaaaa; font-size: 12px;">📋 No audit backlog found</div>';
                }
                return;
            }
            const emptyState = container.querySelector('.empty-state');
            if (emptyState) emptyState.remove();

            const newTierNames = new Set(tiers.map(t => t.tier));
            container.querySelectorAll('[data-tier]').forEach(el => {
                if (!newTierNames.has(el.dataset.tier)) el.remove();
            });

            tiers.forEach(tier => {
                let tierEl = container.querySelector(`[data-tier="${cssEscape(tier.tier)}"]`);
                if (!tierEl) {
                    tierEl = buildBacklogTier(tier);
                    container.appendChild(tierEl);
                }
                tierEl.querySelector('.backlog-tier-name').textContent = tier.tier;

                const total = tier.total || 0;
                const done = tier.done || 0;
                const inflight = tier.inflight || 0;
                const donePercent = total > 0 ? (done / total) * 100 : 0;
                const inflightPercent = total > 0 ? (inflight / total) * 100 : 0;
                tierEl.querySelector('.backlog-progress-done').style.width = donePercent + '%';
                tierEl.querySelector('.backlog-progress-inflight').style.width = inflightPercent + '%';
                tierEl.querySelector('.backlog-progress-empty').style.width = (100 - donePercent - inflightPercent) + '%';
                tierEl.querySelector('.backlog-stats').textContent = `${done}/${total} cleared · ${inflight} in flight`;

                const itemsContainer = tierEl.querySelector('.backlog-items');
                const items = tier.items || [];
                const newKeys = new Set(items.map(backlogItemKey));
                itemsContainer.querySelectorAll('[data-item-key]').forEach(el => {
                    if (!newKeys.has(el.dataset.itemKey)) el.remove();
                });

                items.forEach(item => {
                    const key = backlogItemKey(item);
                    let itemEl = itemsContainer.querySelector(`[data-item-key="${cssEscape(key)}"]`);
                    if (!itemEl) {
                        itemEl = buildBacklogItem(key);
                        itemsContainer.appendChild(itemEl);
                    }
                    itemEl.classList.toggle('done', item.status === '✅');
                    itemEl.querySelector('.backlog-item-glyph').textContent = item.status;
                    itemEl.querySelector('.backlog-item-tag').textContent = item.tag;
                    itemEl.querySelector('.backlog-item-title').textContent = item.title;
                });

                // Truncation cue: fade the bottom when this tier's items overflow the 200px box (more below)
                itemsContainer.classList.toggle('has-overflow', itemsContainer.scrollHeight > itemsContainer.clientHeight + 2);
            });
        }

        // ---- tracker panel: lanes + keyed items ----------
        let latestTracker = { items: [] };

        function getItemLane(item) {
            return item.lane || item.status || 'proposed';
        }

        function buildTrackerItem(item) {
            const priorityClass = `priority-${item.priority || 'P3'}`.toLowerCase();
            const tagsHtml = (item.tags || []).map(t => `<span class="tag">${sanitize(t)}</span>`).join('');
            const itemEl = document.createElement('div');
            itemEl.className = 'tracker-item';
            itemEl.dataset.itemId = item.id;
            itemEl.innerHTML = `
                <div class="tracker-item-header">
                    <div class="tracker-item-title"></div>
                    <span class="priority-chip ${priorityClass}"></span>
                </div>
                <div class="tracker-item-tags">${tagsHtml}</div>
                <div class="tracker-item-details" style="display: none;">
                    ${item.notes ? `<div class="detail-row"><span class="detail-label">Notes:</span> <span class="detail-value">${sanitize(item.notes)}</span></div>` : ''}
                    ${item.pr_link ? `<div class="detail-row"><span class="detail-label">PR:</span> <a href="${sanitize(item.pr_link)}" target="_blank" style="color: #8ac;">${sanitize(item.pr_link.substring(0, 50))}</a></div>` : ''}
                    ${item.created_at ? `<div class="detail-row"><span class="detail-label">Created:</span> <span class="detail-value">${sanitize(item.created_at)}</span></div>` : ''}
                    ${item.completed_at ? `<div class="detail-row"><span class="detail-label">Completed:</span> <span class="detail-value">${sanitize(item.completed_at)}</span></div>` : ''}
                </div>
                <div class="tracker-item-actions">
                    <button class="tracker-action-btn claim-btn" data-id="${sanitize(item.id)}">Claim</button>
                    <button class="tracker-action-btn done-btn" data-id="${sanitize(item.id)}">Done</button>
                    <button class="tracker-action-btn danger archive-btn" data-id="${sanitize(item.id)}">Archive</button>
                </div>
            `;
            itemEl.querySelector('.tracker-item-title').textContent = item.title || '(untitled)';
            itemEl.querySelector('.priority-chip').textContent = item.priority || 'P3';
            return itemEl;
        }

        function patchTracker(trackerData) {
            if (Array.isArray(trackerData)) trackerData = { items: trackerData };
            latestTracker = trackerData || { items: [] };
            if (!Array.isArray(latestTracker.items)) latestTracker.items = [];
            const container = document.getElementById('tracker-lanes');
            container.innerHTML = '';

            const lanes = { proposed: [], ranked: [], 'in-progress': [], done: [], archived: [] };
            latestTracker.items.forEach(item => {
                const lane = getItemLane(item);
                if (lane === 'archived') lanes.archived.push(item);
                else if (lanes[lane]) lanes[lane].push(item);
                else lanes.proposed.push(item);
            });

            const laneOrder = ['proposed', 'ranked', 'in-progress', 'done'];
            laneOrder.forEach(laneName => {
                const items = lanes[laneName] || [];
                const laneEl = document.createElement('div');
                laneEl.className = 'tracker-lane';
                laneEl.innerHTML = `
                    <div class="lane-header">
                        <span>${laneName.charAt(0).toUpperCase() + laneName.slice(1).replace('-', ' ')}</span>
                        <span class="lane-count">${items.length}</span>
                    </div>
                    <div class="lane-items" data-lane="${laneName}"></div>
                `;
                container.appendChild(laneEl);

                const itemsContainer = laneEl.querySelector('.lane-items');
                items.forEach(item => {
                    const itemEl = buildTrackerItem(item);
                    itemsContainer.appendChild(itemEl);
                });
            });

            if (latestTracker.items.length === 0) {
                const emptyHint = document.createElement('div');
                emptyHint.className = 'loading';
                emptyHint.style.cssText = 'grid-column: 1/-1; text-align: center; color: #aaa;';
                emptyHint.textContent = 'No work items yet — add one above';
                container.appendChild(emptyHint);
            }

            if (lanes.archived.length > 0) {
                const archivedSummary = document.createElement('div');
                archivedSummary.className = 'tracker-archived-summary';
                archivedSummary.textContent = `${lanes.archived.length} archived item${lanes.archived.length !== 1 ? 's' : ''}`;
                container.appendChild(archivedSummary);
            }

            document.getElementById('tracker-container').classList.remove('loading');
            setupTrackerEventHandlers();
        }

        function setupTrackerEventHandlers() {
            document.querySelectorAll('.tracker-item').forEach(row => {
                row.addEventListener('click', function(e) {
                    if (e.target.closest('.tracker-action-btn')) return;
                    this.classList.toggle('expanded');
                    const details = this.querySelector('.tracker-item-details');
                    if (details) details.style.display = this.classList.contains('expanded') ? 'block' : 'none';
                });
            });

            document.querySelectorAll('.claim-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;
                    submitTrackerUpdate(id, { status: 'in-progress', lane: 'in-progress' });
                });
            });

            document.querySelectorAll('.done-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;
                    submitTrackerUpdate(id, { status: 'done', lane: 'done' });
                });
            });

            document.querySelectorAll('.archive-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;
                    submitTrackerDelete(id);
                });
            });
        }

        function submitTrackerUpdate(id, update) {
            const csrfToken = window.__AESOP_CSRF_TOKEN__ || '';
            fetch(`/api/tracker/${encodeURIComponent(id)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Aesop-Token': csrfToken
                },
                body: JSON.stringify(update)
            })
            .then(r => r.json())
            .catch(() => console.error('Tracker update failed'));
        }

        function submitTrackerDelete(id) {
            const csrfToken = window.__AESOP_CSRF_TOKEN__ || '';
            fetch(`/api/tracker/${encodeURIComponent(id)}?action=delete`, {
                method: 'POST',
                headers: { 'X-Aesop-Token': csrfToken }
            })
            .then(r => r.json())
            .catch(() => console.error('Tracker delete failed'));
        }

        // ---- orchestrator status panel --------
        function patchOrchestratorStatus(statusData) {
            const banner = document.getElementById('orchestrator-banner');
            const auditBanner = document.getElementById('audit-banner');
            const statusDiv = document.getElementById('orchestrator-status');

            if (!statusData.orchestrators || statusData.orchestrators.length === 0) {
                banner.style.display = 'none';
                auditBanner.style.display = 'none';
                return;
            }

            const orch = statusData.orchestrators[0];
            banner.style.display = 'block';

            let statusText = orch.activity || 'no active session';
            if (orch.age_seconds !== undefined) {
                const mins = Math.floor(orch.age_seconds / 60);
                const secs = orch.age_seconds % 60;
                const ageStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                statusText += ` · updated ${ageStr} ago`;
                if (orch.stale) statusDiv.className = 'status-stale-warn';
                else statusDiv.className = 'status-activity';
            }
            statusDiv.textContent = statusText;

            // Show ASCII banner for audit phase
            if (orch.phase === 'audit') {
                auditBanner.style.display = 'block';
            } else {
                auditBanner.style.display = 'none';
            }
        }

        // ---- SSE wiring ----------------------------------------------------
        const evtSource = new EventSource('/events');

        evtSource.addEventListener('data', (e) => {
            try {
                patchDataSection(JSON.parse(e.data));
                setConnectionStatus(true);
                setConnectionDegraded(false);
            } catch (err) {
                console.error('Failed to parse data frame:', err);
                setConnectionDegraded(true);
            }
        });
        evtSource.addEventListener('backlog', (e) => {
            try {
                patchBacklog(JSON.parse(e.data));
                setConnectionStatus(true);
                setConnectionDegraded(false);
            } catch (err) {
                console.error('Failed to parse backlog frame:', err);
                setConnectionDegraded(true);
            }
        });
        evtSource.addEventListener('agents', (e) => {
            try {
                patchAgents(JSON.parse(e.data));
                patchHeaderRunningCount(latestAgents);
                setConnectionStatus(true);
                setConnectionDegraded(false);
            } catch (err) {
                console.error('Failed to parse agents frame:', err);
                setConnectionDegraded(true);
            }
        });
        evtSource.addEventListener('tracker', (e) => {
            try {
                patchTracker(JSON.parse(e.data));
                setConnectionStatus(true);
                setConnectionDegraded(false);
            } catch (err) {
                console.error('Failed to parse tracker frame:', err);
                setConnectionDegraded(true);
            }
        });
        evtSource.addEventListener('status', (e) => {
            try {
                patchOrchestratorStatus(JSON.parse(e.data));
                setConnectionStatus(true);
                setConnectionDegraded(false);
            } catch (err) {
                console.error('Failed to parse status frame:', err);
                setConnectionDegraded(true);
            }
        });
        evtSource.addEventListener('open', () => {
            setConnectionStatus(true);
            setConnectionDegraded(false);
        });
        evtSource.addEventListener('error', () => setConnectionStatus(false));

        // Manual refresh fallback (one-shot fetch, reuses the exact same patch
        // functions as the push path so there's a single rendering code path).
        async function manualRefresh() {
            try {
                const [dataResp, backlogResp, agentsResp, trackerResp] = await Promise.all([
                    fetch('/data'), fetch('/api/backlog'), fetch('/api/agents'), fetch('/api/tracker')
                ]);
                if (dataResp.ok) patchDataSection(await dataResp.json());
                if (backlogResp.ok) patchBacklog(await backlogResp.json());
                if (agentsResp.ok) {
                    patchAgents(await agentsResp.json());
                    patchHeaderRunningCount(latestAgents);
                }
                if (trackerResp.ok) patchTracker(await trackerResp.json());
            } catch (e) {
                console.error('Manual refresh error:', e);
            }
        }
        document.getElementById('manual-refresh-button').addEventListener('click', manualRefresh);

        async function handleInboxSubmit() {
            const input = document.getElementById('inbox-input');
            const button = document.getElementById('inbox-button');
            const status = document.getElementById('inbox-status');

            const text = input.value.trim();
            if (!text) return;

            button.disabled = true;
            try {
                // Get CSRF token from window (injected by server)
                const csrfToken = window.__AESOP_CSRF_TOKEN__ || '';
                const response = await fetch('/submit', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Aesop-Token': csrfToken
                    },
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

        async function handleTrackerAddItem() {
            const titleInput = document.getElementById('tracker-title');
            const priorityInput = document.getElementById('tracker-priority');
            const notesInput = document.getElementById('tracker-notes');
            const button = document.getElementById('tracker-add-btn');

            const title = titleInput.value.trim();
            if (!title) return;

            const itemData = {
                title: title,
                priority: priorityInput.value || 'P2',
                notes: notesInput.value.trim() || null,
                source: 'dashboard',
                tags: [],
                status: 'todo',
                lane: 'proposed'
            };

            button.disabled = true;
            try {
                const response = await fetch('/api/tracker', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Aesop-Token': window.__AESOP_CSRF_TOKEN__ || ''
                    },
                    body: JSON.stringify(itemData)
                });
                if (response.ok) {
                    titleInput.value = '';
                    notesInput.value = '';
                    priorityInput.value = 'P2';
                }
            } catch (e) {
                console.error('Tracker add error:', e);
            } finally {
                button.disabled = false;
            }
        }

        document.getElementById('tracker-add-btn').addEventListener('click', handleTrackerAddItem);
        document.getElementById('tracker-title').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleTrackerAddItem();
        });

        // Initial fetch for tracker and status data
        Promise.all([fetch('/api/tracker')]).then(([trackerResp]) => {
            if (trackerResp.ok) trackerResp.json().then(data => patchTracker({ items: data }));
        }).catch(e => console.error('Initial tracker fetch error:', e));
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
