#!/usr/bin/env python3
"""
Common utilities shared across tools.

Functions:
  get_state_dir() -> Path
    Resolve state directory from AESOP_STATE_ROOT env var or default to ./state

  check_heartbeat_staleness(hb_file, threshold_s) -> (is_stale, age_s, info)
    Check if a heartbeat file is stale and return staleness, age, and descriptive info
"""

import os
import time
from pathlib import Path


def get_state_dir():
    """Resolve state directory from env var or current working directory.

    Returns:
        Path: Directory path for state files. Either from AESOP_STATE_ROOT env var
              or defaults to ./state relative to cwd.
    """
    if os.environ.get("AESOP_STATE_ROOT"):
        return Path(os.environ["AESOP_STATE_ROOT"])
    # Default to ./state (relative to cwd)
    return Path.cwd() / "state"


def check_heartbeat_staleness(hb_file, threshold_s):
    """Check if a heartbeat file is stale.

    Args:
        hb_file: Path to heartbeat file (contains epoch timestamp as first line)
        threshold_s: Staleness threshold in seconds; age >= threshold is stale

    Returns:
        Tuple of (is_stale, age_s, info):
          is_stale (bool): True if file missing, unreadable, or age >= threshold_s
          age_s (int): Age in seconds (0 if file missing/unreadable)
          info (str or None): Descriptive message if stale/missing, None if fresh
    """
    if not hb_file.exists():
        return True, 0, "Heartbeat file missing"

    try:
        content = hb_file.read_text(encoding="utf-8").strip()
        if not content:
            return True, 0, "Heartbeat file empty"

        timestamp = int(content)
    except (ValueError, IOError):
        return True, 0, "Heartbeat file unreadable"

    age_seconds = int(time.time()) - timestamp

    # Check for future-dated timestamp (clock skew beyond tolerance)
    # More than 120s in the future is treated as stale, not clamped-to-fresh
    if age_seconds < -120:
        return True, 0, "Heartbeat timestamp in future (clock skew)"

    # Clamp small negative ages to 0 (normal clock skew recovery)
    age_seconds = max(0, age_seconds)

    if age_seconds >= threshold_s:
        return True, age_seconds, f"Heartbeat stale ({age_seconds}s >= {threshold_s}s)"

    return False, age_seconds, None
