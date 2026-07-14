#!/usr/bin/env python3
"""Aesop UI — read-only data collectors + tracker CRUD + SSE section snapshots (wave-9 split)."""
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from time import time

import config


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
        if not config.AUDIT_BACKLOG_FILE.exists():
            return result

        content = config.AUDIT_BACKLOG_FILE.read_text(encoding='utf-8')
    except Exception as e:
        print(f"[collectors] Failed to read audit backlog: {e}", file=sys.stderr)
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
        if not config.WATCHDOG_HEARTBEAT.exists():
            return {"alive": "UNKNOWN", "age": -1, "threshold": 300}
        content = config.WATCHDOG_HEARTBEAT.read_text().strip()
        if not content:
            return {"alive": "UNKNOWN", "age": -1, "threshold": 300}
        # Parse epoch value robustly; assume seconds (standard epoch format)
        try:
            timestamp = int(content)
        except ValueError:
            # Retry once in case of race during daemon write
            try:
                content = config.WATCHDOG_HEARTBEAT.read_text().strip()
                timestamp = int(content)
            except Exception as e:
                print(f"[collectors] Failed to parse watchdog heartbeat: {e}", file=sys.stderr)
                return {"alive": "unknown", "age": -1, "threshold": 300}
        # Age in seconds: now_seconds - heartbeat_seconds
        age_seconds = int(time()) - timestamp
        # Bucket age to 3-second intervals to prevent hash churn
        age_bucketed = (age_seconds // 3) * 3
        alive = "ALIVE" if age_seconds < 300 else "STALE"
        return {"alive": alive, "age": age_bucketed, "threshold": 300}
    except Exception as e:
        print(f"[collectors] Failed to get watchdog heartbeat: {e}", file=sys.stderr)
        return {"alive": "unknown", "age": -1, "threshold": 300}

def get_monitor_heartbeat_status():
    """Read orchestration monitor heartbeat age and status.

    Buckets age to prevent every-tick hash change: age is reported in 3-second buckets
    (e.g., 0-2s → 0, 3-5s → 3, 6-8s → 6, ...) so the monitor snapshot only changes
    every ~3 seconds, not every 1 second. This preserves the change-hash gate effectiveness.
    """
    try:
        # Check both possible paths: state/.monitor-heartbeat and monitor/.monitor-heartbeat
        monitor_hb = config.MONITOR_HEARTBEAT
        if not monitor_hb.exists():
            # Try alternate path
            alt_path = config.AESOP_ROOT / "monitor" / ".monitor-heartbeat"
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
            except Exception as e:
                print(f"[collectors] Failed to parse monitor heartbeat: {e}", file=sys.stderr)
                return {"alive": "unknown", "age": -1, "threshold": 3600}
        # Age in seconds: now_seconds - heartbeat_seconds
        age_seconds = int(time()) - timestamp
        # Bucket age to 3-second intervals to prevent hash churn
        age_bucketed = (age_seconds // 3) * 3
        alive = "ALIVE" if age_seconds < 3600 else "STALE"
        return {"alive": alive, "age": age_bucketed, "threshold": 3600}
    except Exception as e:
        print(f"[collectors] Failed to get monitor heartbeat: {e}", file=sys.stderr)
        return {"alive": "unknown", "age": -1, "threshold": 3600}

def get_main_thread_messages():
    """Read last ~12 messages from newest session JSONL."""
    messages = []
    try:
        if not config.TRANSCRIPTS_ROOT.exists():
            return messages
        # Find newest .jsonl
        jsonl_files = sorted(
            config.TRANSCRIPTS_ROOT.glob("**/*.jsonl"),
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
    except Exception as e:
        print(f"[collectors] Failed to read main thread messages: {e}", file=sys.stderr)
    return messages

def get_repos_status():
    """Read repos from .watchdog-repos.json."""
    repos = []
    try:
        if not config.REPOS_JSON.exists():
            return repos
        data = json.loads(config.REPOS_JSON.read_text())
        if isinstance(data, list):
            repos = data[:10]  # Limit to 10
        elif isinstance(data, dict):
            repos = [{"repo": k, "state": v} for k, v in data.items()][:10]
    except Exception as e:
        print(f"[collectors] Failed to read repos status: {e}", file=sys.stderr)
    return repos

def get_recent_events():
    """Read last 8 lines from FLEET-BACKUP.log."""
    events = []
    try:
        if not config.BACKUP_LOG.exists():
            return events
        lines = config.BACKUP_LOG.read_text().strip().split('\n')
        events = [line.strip() for line in lines[-8:] if line.strip()]
    except Exception as e:
        print(f"[collectors] Failed to read recent events: {e}", file=sys.stderr)
    return events

def get_alerts():
    """Read SECURITY-ALERTS.log, skip NOTE:/RESOLVED-FP, count by severity."""
    alerts = {"count": 0, "lines": []}
    try:
        if not config.ALERTS_LOG.exists():
            return alerts
        lines = config.ALERTS_LOG.read_text().strip().split('\n')
        unreviewed = [
            line.strip() for line in lines
            if line.strip()
            and "NOTE:" not in line
            and "RESOLVED-FP" not in line
        ]
        alerts["count"] = len(unreviewed)
        alerts["lines"] = unreviewed[-5:]  # Show last 5
    except Exception as e:
        print(f"[collectors] Failed to read alerts: {e}", file=sys.stderr)
    return alerts

def load_tracker():
    """Load tracker.json, return empty tracker if missing or corrupt."""
    if not config.TRACKER_FILE.exists():
        return {"version": 1, "items": []}

    try:
        data = json.loads(config.TRACKER_FILE.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or "version" not in data:
            raise ValueError("Invalid tracker schema")
        return data
    except Exception as e:
        print(f"[tracker] Corrupt tracker.json: {e}", file=sys.stderr)
        corrupt_path = config.TRACKER_FILE.with_suffix('.json.corrupt')
        try:
            if config.TRACKER_FILE.exists():
                config.TRACKER_FILE.rename(corrupt_path)
        except Exception as e:
            print(f"[tracker] Failed to rename corrupt tracker: {e}", file=sys.stderr)
        return {"version": 1, "items": []}

def save_tracker(tracker):
    """Save tracker atomically using temp file + os.replace."""
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = config.TRACKER_FILE.with_suffix('.json.tmp')
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(tracker, f, indent=2)
        os.replace(str(temp_file), str(config.TRACKER_FILE))
    except Exception as e:
        print(f"[tracker] Error saving tracker: {e}", file=sys.stderr)
        try:
            temp_file.unlink()
        except Exception as ue:
            print(f"[tracker] Failed to unlink temp file: {ue}", file=sys.stderr)
        raise

def migrate_tracker_from_backlog():
    """One-time idempotent migration: AUDIT-BACKLOG.md -> tracker.json."""
    if config.TRACKER_FILE.exists():
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
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        item["completed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

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

def _snapshot_tracker():
    """Read tracker.json, return {items: [...]}."""
    tracker_file = config.STATE_DIR / "tracker.json"
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
    status_file = config.STATE_DIR / "orchestrator-status.json"
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
                    age_seconds = int((datetime.now(timezone.utc).replace(tzinfo=None) - updated_at).total_seconds())
                    stale = age_seconds > 1800
            except Exception as e:
                print(f"[collectors] Failed to parse orchestrator timestamp: {e}", file=sys.stderr)
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
    inbox_file = config.STATE_DIR / ".tracker-inbox.jsonl"
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
