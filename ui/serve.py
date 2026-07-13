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
# (TRACKER_FILE is imported from config)


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
