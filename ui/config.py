#!/usr/bin/env python3
"""
Aesop UI Configuration — Path and environment resolution.

This module centralizes all path configuration, environment variable resolution,
and config file loading for the UI dashboard. It provides a reload() function to
recompute all paths when environment changes (e.g., between test fixtures).

Config precedence: env vars > aesop.config.json > built-in defaults.
"""
import json
import os
import sys
from pathlib import Path


# ==============================================================================
# Path Resolution Functions
# ==============================================================================

def reload():
    """Recompute all configuration from current environment.

    Called at module load and whenever environment changes (test fixtures).
    Mutates module-level globals in place so that importers see the current state.
    """
    global PORT, AESOP_ROOT, CONFIG_FILE, STATE_DIR, TRANSCRIPTS_ROOT
    global WATCHDOG_HEARTBEAT, MONITOR_HEARTBEAT, REPOS_JSON, BACKUP_LOG
    global ALERTS_LOG, INBOX_FILE, AUDIT_BACKLOG_FILE
    global UI_SESSION_TOKEN_FILE, TRACKER_FILE, ORCH_STATUS_FILE
    global COLLECTOR_INTERVAL, SSE_KEEPALIVE_SECONDS, SSE_MAX_CLIENTS, SSE_QUEUE_MAXSIZE, SSE_WRITE_TIMEOUT

    # PORT: env PORT > default 8770
    PORT = int(os.getenv("PORT", "8770"))

    # Determine AESOP_ROOT: env AESOP_ROOT > default $HOME/aesop
    AESOP_ROOT = Path(os.getenv("AESOP_ROOT", Path.home() / "aesop"))

    # Try to load config file for additional settings
    CONFIG_FILE = AESOP_ROOT / "aesop.config.json"
    config_data = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"[config] Failed to load {CONFIG_FILE}: {e}", file=sys.stderr)

    # Derive paths with precedence: env var > config file > built-in default
    # STATE_DIR: env AESOP_STATE_ROOT > config state_root > AESOP_ROOT/state
    STATE_DIR = Path(
        os.getenv(
            "AESOP_STATE_ROOT",
            config_data.get("state_root", str(AESOP_ROOT / "state"))
        )
    )

    # TRANSCRIPTS_ROOT: env AESOP_TRANSCRIPTS_ROOT > config transcripts_root > ~/.claude/projects
    TRANSCRIPTS_ROOT = Path(
        os.getenv(
            "AESOP_TRANSCRIPTS_ROOT",
            config_data.get("transcripts_root", "~/.claude/projects")
        )
    ).expanduser()

    # Data file paths (all derived from STATE_DIR and AESOP_ROOT)
    WATCHDOG_HEARTBEAT = STATE_DIR / ".watchdog-heartbeat"
    MONITOR_HEARTBEAT = STATE_DIR / ".monitor-heartbeat"
    REPOS_JSON = STATE_DIR / ".watchdog-repos.json"
    BACKUP_LOG = STATE_DIR / "FLEET-BACKUP.log"
    ALERTS_LOG = STATE_DIR / "SECURITY-ALERTS.log"
    INBOX_FILE = STATE_DIR / "ui-inbox.md"
    AUDIT_BACKLOG_FILE = AESOP_ROOT / "AUDIT-BACKLOG.md"
    UI_SESSION_TOKEN_FILE = STATE_DIR / ".ui-session-token"
    TRACKER_FILE = STATE_DIR / "tracker.json"
    ORCH_STATUS_FILE = STATE_DIR / "orchestrator-status.json"

    # Collector and SSE configuration
    COLLECTOR_INTERVAL = float(os.getenv("AESOP_UI_COLLECT_INTERVAL", "1.0"))
    SSE_KEEPALIVE_SECONDS = 15
    SSE_MAX_CLIENTS = 100  # Resource cap: reject new connections past this
    SSE_QUEUE_MAXSIZE = 50  # Per-client bounded queue (drops oldest on overflow)
    SSE_WRITE_TIMEOUT = 5.0  # Write timeout in seconds to prevent stalled clients


# ==============================================================================
# Module-level initialization
# ==============================================================================

# Initialize configuration at module load time
# These globals are recomputed by reload() and accessed by other modules
PORT = 8770
AESOP_ROOT = Path.home() / "aesop"
CONFIG_FILE = AESOP_ROOT / "aesop.config.json"
STATE_DIR = AESOP_ROOT / "state"
TRANSCRIPTS_ROOT = Path("~/.claude/projects").expanduser()
WATCHDOG_HEARTBEAT = STATE_DIR / ".watchdog-heartbeat"
MONITOR_HEARTBEAT = STATE_DIR / ".monitor-heartbeat"
REPOS_JSON = STATE_DIR / ".watchdog-repos.json"
BACKUP_LOG = STATE_DIR / "FLEET-BACKUP.log"
ALERTS_LOG = STATE_DIR / "SECURITY-ALERTS.log"
INBOX_FILE = STATE_DIR / "ui-inbox.md"
AUDIT_BACKLOG_FILE = AESOP_ROOT / "AUDIT-BACKLOG.md"
UI_SESSION_TOKEN_FILE = STATE_DIR / ".ui-session-token"
TRACKER_FILE = STATE_DIR / "tracker.json"
ORCH_STATUS_FILE = STATE_DIR / "orchestrator-status.json"
COLLECTOR_INTERVAL = 1.0
SSE_KEEPALIVE_SECONDS = 15
SSE_MAX_CLIENTS = 100
SSE_QUEUE_MAXSIZE = 50
SSE_WRITE_TIMEOUT = 5.0

# Perform initial load from environment
reload()
