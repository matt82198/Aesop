#!/usr/bin/env python3
"""
Scaffold durable checkpointing directories for project orchestration.

Usage: ensure_state.py --state-dir DIR

Creates STATE.md and BUILDLOG.md templates in the state directory
if they do not already exist. Never overwrites existing files.
"""
# secretscan: allow-pattern-docs

import sys
import os
import argparse
import datetime
from pathlib import Path


STATE_TEMPLATE = """# STATE — authoritative project checkpoint

## Intent
One-line summary of the project's current phase and goal.

## Stack & locked decisions
- Key technology choices and constraints.
- Data model contracts and API signatures.

## Current status
- Phase summary and completion %.
- Major blockers or decisions pending.

## Gotchas
- Known issues, workarounds, environment quirks.

## NEXT STEPS
- Explicit ordered list of what comes next.
- Assigned owners if coordinating multiple agents.
"""

BUILDLOG_HEADER = "# BUILDLOG — append-only progress log"


def ensure_state_files(state_dir):
    """
    Create state directory with STATE.md and BUILDLOG.md if missing.
    Returns list of (filename, status) tuples: ('STATE.md', 'CREATED'), etc.
    """
    state_path = Path(state_dir)
    state_path.mkdir(parents=True, exist_ok=True)

    results = []

    # STATE.md
    state_file = state_path / 'STATE.md'
    if state_file.exists():
        results.append(('STATE.md', 'EXISTS'))
    else:
        with open(state_file, 'w', encoding='utf-8') as f:
            f.write(STATE_TEMPLATE)
        results.append(('STATE.md', 'CREATED'))

    # BUILDLOG.md
    buildlog_file = state_path / 'BUILDLOG.md'
    if buildlog_file.exists():
        results.append(('BUILDLOG.md', 'EXISTS'))
    else:
        timestamp = datetime.datetime.now().isoformat()
        with open(buildlog_file, 'w', encoding='utf-8') as f:
            f.write(f'{BUILDLOG_HEADER}\n')
            f.write(f'created {timestamp}\n')
        results.append(('BUILDLOG.md', 'CREATED'))

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Scaffold durable checkpointing directories.'
    )
    parser.add_argument('--state-dir', required=True,
                        help='State directory')

    args = parser.parse_args()

    state_dir = args.state_dir

    results = ensure_state_files(state_dir)

    for filename, status in results:
        print(f'{status} {filename}')


if __name__ == '__main__':
    main()
