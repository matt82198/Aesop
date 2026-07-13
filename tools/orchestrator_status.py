#!/usr/bin/env python3
"""Orchestrator status CLI tool — atomic status updates for the orchestration layer.

Usage:
  python orchestrator_status.py set --activity "dispatching wave-8" --phase audit [--id main --role orchestrator]
  python orchestrator_status.py clear

Writes state/orchestrator-status.json atomically (temp+replace) for wave-8/wave-9+ compatibility.
No external dependencies.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def get_state_dir():
    """Get state directory from env or fallback to AESOP_ROOT/state."""
    state_root = os.getenv("AESOP_STATE_ROOT")
    if state_root:
        return Path(state_root)
    
    aesop_root = os.getenv("AESOP_ROOT", str(Path.home() / "aesop"))
    return Path(aesop_root) / "state"


def set_status(activity, phase, id=None, role=None):
    """Atomically write orchestrator status."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    
    status_data = {
        "id": id or "main",
        "role": role or "orchestrator",
        "parent_id": None,
        "activity": activity,
        "phase": phase,
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }
    
    status_file = state_dir / "orchestrator-status.json"
    temp_file = status_file.with_suffix(".json.tmp")
    
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=2)
        os.replace(str(temp_file), str(status_file))
        print(f"[OK] Status updated: activity={activity}, phase={phase}")
    except Exception as e:
        print(f"[ERROR] Failed to write status: {e}", file=sys.stderr)
        try:
            temp_file.unlink()
        except:
            pass
        sys.exit(1)


def clear_status():
    """Atomically remove orchestrator status file."""
    state_dir = get_state_dir()
    status_file = state_dir / "orchestrator-status.json"
    
    try:
        if status_file.exists():
            status_file.unlink()
        print("[OK] Status cleared")
    except Exception as e:
        print(f"[ERROR] Failed to clear status: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Atomic orchestrator status updates"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # set command
    set_parser = subparsers.add_parser("set", help="Set orchestrator status")
    set_parser.add_argument("--activity", required=True, help="Activity description")
    set_parser.add_argument("--phase", required=True, help="Phase (plan, dispatch, audit, etc)")
    set_parser.add_argument("--id", default="main", help="Orchestrator ID (default: main)")
    set_parser.add_argument("--role", default="orchestrator", help="Orchestrator role (default: orchestrator)")
    
    # clear command
    subparsers.add_parser("clear", help="Clear orchestrator status")
    
    args = parser.parse_args()
    
    if args.command == "set":
        set_status(args.activity, args.phase, args.id, args.role)
    elif args.command == "clear":
        clear_status()


if __name__ == "__main__":
    main()
