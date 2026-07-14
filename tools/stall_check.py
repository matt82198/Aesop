#!/usr/bin/env python3
"""
Automated silent-hang detection for agent transcripts.

Usage:
  stall_check.py [--transcripts-root DIR] [--threshold-seconds SEC] [--json] [--exit-nonzero-on-stall]

Options:
  --transcripts-root DIR       Root directory to scan for agent-*.jsonl transcripts.
                               Defaults to AESOP_TRANSCRIPTS_ROOT env var, or ~/.claude/projects if unset.
  --threshold-seconds SEC      Max age in seconds for a "fresh" transcript (default: 600).
                               Transcripts older than this are flagged as stalled.
  --json                       Output as JSON list of {agent_id, age_seconds, stalled, last_mtime}.
  --exit-nonzero-on-stall      Exit 1 if any agent is detected as stalled; default exit 0 always.

Behavior:
  - Walks transcripts-root for files matching agent-*.jsonl.
  - For each file, computes age = now - file mtime (seconds).
  - Reports agents as stalled if age > threshold-seconds.
  - Default output: human-readable table; add --json for structured output.
  - Gracefully reports "no transcripts found" if root is missing or empty.
  - Exit code: 0 always (unless --exit-nonzero-on-stall specified and stalls detected).
"""

import sys
import os
import time
import json
import argparse
from pathlib import Path


def get_transcripts_root():
    """Resolve transcripts root from env var or default to ~/.claude/projects."""
    if os.environ.get("AESOP_TRANSCRIPTS_ROOT"):
        return Path(os.environ["AESOP_TRANSCRIPTS_ROOT"])
    # Default to ~/.claude/projects
    return Path.home() / ".claude" / "projects"


def scan_transcripts(transcripts_root, threshold_seconds):
    """Scan transcripts root for agent-*.jsonl files and compute staleness.

    Returns: list of dicts {agent_id, age_seconds, stalled, last_mtime (ISO format)}
    """
    transcripts_root = Path(transcripts_root)

    if not transcripts_root.exists():
        return None  # Signal: root missing

    now = time.time()
    results = []

    # Walk all subdirectories for agent-*.jsonl files
    for jsonl_file in transcripts_root.rglob("agent-*.jsonl"):
        if not jsonl_file.is_file():
            continue

        mtime = jsonl_file.stat().st_mtime
        age_seconds = int(now - mtime)
        stalled = age_seconds > threshold_seconds

        # Extract agent_id from filename (e.g., agent-abc123.jsonl -> abc123)
        agent_id = jsonl_file.stem.replace("agent-", "")

        results.append({
            "agent_id": agent_id,
            "age_seconds": age_seconds,
            "stalled": stalled,
            "last_mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime)),
        })

    return results


def print_human_table(results):
    """Print results as a human-readable table."""
    if not results:
        print("no transcripts found")
        return

    # Sort by age_seconds (oldest first)
    sorted_results = sorted(results, key=lambda r: r["age_seconds"], reverse=True)

    # Header
    print(f"{'AGENT_ID':<30} {'AGE (s)':<10} {'STATUS':<10} {'LAST_MTIME':<25}")
    print("-" * 75)

    for entry in sorted_results:
        status = "STALLED" if entry["stalled"] else "ACTIVE"
        print(f"{entry['agent_id']:<30} {entry['age_seconds']:<10} {status:<10} {entry['last_mtime']:<25}")


def print_json_output(results):
    """Print results as JSON."""
    if results is None:
        print(json.dumps([]))
    else:
        print(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--transcripts-root",
        default=None,
        help="Root directory to scan for agent-*.jsonl files (default: AESOP_TRANSCRIPTS_ROOT or ~/.claude/projects)",
    )
    parser.add_argument(
        "--threshold-seconds",
        type=int,
        default=600,
        help="Max age in seconds for a 'fresh' transcript (default: 600)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable table",
    )
    parser.add_argument(
        "--exit-nonzero-on-stall",
        action="store_true",
        help="Exit 1 if any agent is stalled (default: always exit 0)",
    )

    args = parser.parse_args()

    # Resolve transcripts root
    transcripts_root = args.transcripts_root if args.transcripts_root else get_transcripts_root()

    # Scan transcripts
    results = scan_transcripts(transcripts_root, args.threshold_seconds)

    # Output
    if args.json:
        print_json_output(results)
    else:
        if results is None:
            print("no transcripts found")
        else:
            print_human_table(results)

    # Determine exit code
    exit_code = 0
    if args.exit_nonzero_on_stall and results:
        has_stalled = any(r["stalled"] for r in results)
        if has_stalled:
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
