#!/usr/bin/env python3
"""Aesop UI — agent transcript reading + path-traversal-safe id handling (wave-9 split)."""
import json
import re
import subprocess
import sys
from pathlib import Path

import config


def _path_is_contained(child, root):
    """Check if child path is contained within root path (no traversal).

    Returns True if child is under root, False if it escapes (e.g., via ..).
    Uses Path.is_relative_to (Python 3.9+) with a fallback for older runtimes.

    Args:
        child: Path object (typically resolved)
        root: Path object (typically resolved)

    Returns:
        bool: True if child is contained within root, False otherwise
    """
    try:
        return child.is_relative_to(root.resolve())
    except AttributeError:
        # Path.is_relative_to requires Python 3.9+; fall back for older runtimes.
        try:
            child.relative_to(root.resolve())
            return True
        except ValueError:
            return False


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
        dash_extra_path = config.AESOP_ROOT / "dash" / "dash-extra.mjs"
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

_AGENT_ID_FORBIDDEN = re.compile(r'\.\.|[/\\*?\[\]]')

def extract_agent_dispatch_prompt(agent_id):
    """
    Extract dispatch prompt and metadata from agent jsonl transcript.
    Returns dict with prompt, dispatcher, model, activity times, and message count.
    Robust: missing/invalid file -> {error: "..."}
    Security: rejects agent_id containing path-traversal or glob-metacharacter
    sequences before building any glob pattern, and refuses to return a match
    that resolves outside config.TRANSCRIPTS_ROOT (defense in depth). Error results
    carry "invalid": True when the input itself was rejected, so callers can
    map that to an HTTP 400 rather than a plain 404.

    CRITICAL: Use prefix-matching via glob, not exact match. The dashboard (dash-extra.mjs)
    scans for agent-*.jsonl files and emits a 13-char truncated ID; files on disk carry
    full IDs (e.g., agent-a77b995bcdb953e9c1234567.jsonl). This function must search for
    the same file format that the dashboard actually finds.
    """
    try:
        if not agent_id or _AGENT_ID_FORBIDDEN.search(agent_id):
            return {"error": "invalid agent id", "invalid": True}

        # Prefix-match: search in config.TRANSCRIPTS_ROOT for files matching agent-agent_id*.jsonl
        # The dashboard (dash-extra.mjs) scans for agent-*.jsonl files and emits
        # a 13-char truncated ID; we must match against the same .jsonl files.
        if not config.TRANSCRIPTS_ROOT.exists():
            return {"error": f"transcripts root not found at {config.TRANSCRIPTS_ROOT}"}

        # Glob for matching files (prefix-match handles truncated IDs)
        matches = sorted(
            config.TRANSCRIPTS_ROOT.glob(f"**/agent-{agent_id}*.jsonl"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not matches:
            return {"error": f"transcript not found for {agent_id}"}
        output_file = matches[0]

        # Containment check: the resolved match must stay inside config.TRANSCRIPTS_ROOT.
        # Belt-and-suspenders alongside the input rejection above.
        if not _path_is_contained(output_file.resolve(), config.TRANSCRIPTS_ROOT):
            return {"error": "resolved path outside transcripts root", "invalid": True}

        dispatch_prompt = None
        message_count = 0
        model = None
        parent_uuid = None
        first_seen = None
        last_activity = None

        # Parse NDJSON (one JSON per line)
        with open(output_file, 'r', encoding='utf-8', errors='replace') as f:
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
        print(f"[extract_agent_dispatch_prompt] Uncaught exception: {e}", file=sys.stderr)
        return {"error": "Failed to extract dispatch prompt"}

def _transcripts_fingerprint():
    """Cheap fs-stat-only fingerprint of the transcripts tree.

    Used to decide whether it's worth re-invoking `node dash-extra.mjs` (which is
    comparatively expensive: process spawn + re-parsing every agent transcript).
    Only file count + max mtime — no file content is read.
    """
    try:
        if not config.TRANSCRIPTS_ROOT.exists():
            return (0, 0.0)
        count = 0
        latest = 0.0
        for p in config.TRANSCRIPTS_ROOT.glob("**/agent-*.jsonl"):
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
