#!/usr/bin/env python3
"""
state_store.read_api — Typed read-only facade for state surfaces.

Consolidates read patterns for: tracker snapshot, orchestrator-status,
heartbeat freshness, and ledger rows. This facade allows the underlying
state representation to change (git → SQLite → Postgres) without altering
caller code.

Callers use:
  api = ReadAPI(state_dir)
  tracker = api.read_tracker_snapshot()
  status = api.read_orchestrator_status()
  is_fresh = api.is_orchestrator_status_fresh(threshold_s=300)
  is_fresh = api.check_heartbeat_fresh(".watchdog-heartbeat", 200)
  rows = api.read_ledger_rows()
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path


class ReadAPI:
    """Read-only facade over state surfaces (tracker, orchestrator-status, heartbeats, ledger).

    Designed to be swappable: backends can change (git → SQLite → Postgres) without
    altering call sites. Current implementation reads from filesystem; future may
    read from SQLite projections or API.
    """

    def __init__(self, state_dir):
        """Initialize the read API with a state directory.

        Args:
            state_dir: Path to the state directory (e.g., "state" or "/absolute/path/state")
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def read_tracker_snapshot(self):
        """Read the current tracker snapshot.

        Returns the tracker.json file, or an empty dict if missing/unreadable.
        In the future, this may read from the SQLite projection instead.

        Returns:
            dict: Tracker snapshot (items, metadata, etc.) or {} if unavailable.
        """
        tracker_file = self.state_dir / "tracker.json"
        if not tracker_file.exists():
            return {}

        try:
            content = tracker_file.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception:
            # Malformed JSON or read error: return empty dict (fail-open)
            return {}

    def read_orchestrator_status(self):
        """Read orchestrator-status.json if present.

        Returns:
            dict with "phase", "activity", "updated_at" fields if file is valid, or None.
        """
        status_file = self.state_dir / "orchestrator-status.json"
        if not status_file.exists():
            return None

        try:
            content = status_file.read_text(encoding="utf-8")
            data = json.loads(content)
            # Validate required fields for orchestrator status
            if "phase" not in data:
                return None
            return data
        except Exception:
            return None

    def is_orchestrator_status_fresh(self, threshold_s=300):
        """Check if orchestrator-status.json exists and is fresh.

        Reads updated_at timestamp and compares to current time.
        Returns False if file missing, unparseable, or stale.

        Args:
            threshold_s: Staleness threshold in seconds (default: 300s)

        Returns:
            bool: True if file is fresh, False if stale/missing/malformed.
        """
        status = self.read_orchestrator_status()
        if status is None:
            return False

        try:
            updated_at_str = status.get("updated_at")
            if not updated_at_str:
                return False

            # Parse ISO format timestamp (handle both "Z" and "+00:00")
            normalized = updated_at_str.replace("Z", "+00:00")
            updated_at = datetime.fromisoformat(normalized)

            now = datetime.now(timezone.utc)
            age = (now - updated_at).total_seconds()

            # Treat future-dated timestamps as stale (fail-closed)
            if age < -120:  # More than 2min in future = clock skew, treat as stale
                return False

            # Clamp small negative ages to 0
            age = max(0, age)

            return age < threshold_s
        except Exception:
            return False

    def check_heartbeat_fresh(self, heartbeat_filename, threshold_s=200):
        """Check if a heartbeat file is fresh.

        Reads the heartbeat file (expected to contain epoch timestamp as first line)
        and compares to current time.

        Args:
            heartbeat_filename: Filename in state_dir (e.g., ".watchdog-heartbeat")
            threshold_s: Staleness threshold in seconds (default: 200s)

        Returns:
            bool: True if file exists and is fresh, False otherwise.
        """
        hb_file = self.state_dir / heartbeat_filename
        if not hb_file.exists():
            return False

        try:
            content = hb_file.read_text(encoding="utf-8").strip()
            if not content:
                return False

            timestamp = int(content)
        except (ValueError, OSError):
            return False

        age_seconds = int(time.time()) - timestamp

        # Check for future-dated timestamp (clock skew beyond tolerance)
        if age_seconds < -120:  # More than 2min in future = clock skew
            return False

        # Clamp small negative ages to 0
        age_seconds = max(0, age_seconds)

        return age_seconds < threshold_s

    def read_ledger_rows(self):
        """Read OUTCOMES-LEDGER.md and parse rows.

        Reads the ledger markdown table and returns parsed rows.
        Returns empty list if file missing or unparseable.

        Returns:
            list: List of row dicts parsed from the ledger table, or [].
        """
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        if not ledger_file.exists():
            return []

        try:
            content = ledger_file.read_text(encoding="utf-8")
            rows = []

            # Simple markdown table parser: look for lines starting with |
            in_table = False
            for line in content.split("\n"):
                line = line.strip()

                # Skip header and separator lines
                if not line.startswith("|"):
                    in_table = False
                    continue

                if not in_table:
                    # Check if this looks like a header
                    if "Date" in line or "Phase" in line:
                        in_table = True
                        continue

                # Parse data row: | col1 | col2 | ... |
                parts = [p.strip() for p in line.split("|")[1:-1]]  # ignore leading/trailing empty
                if parts:
                    rows.append(parts)

            return rows
        except Exception:
            return []
