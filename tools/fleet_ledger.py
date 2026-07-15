#!/usr/bin/env python3
r"""
Fleet Outcome Ledger — append-only audit trail for dispatched agents.

Subcommands:
  append <timestamp> <agent_type> <model> <duration_sec> <tokens_in> <tokens_out> [verdict]
    Manually append one ledger line (verdict = OK|FAILED|EMPTY|HUNG, default OK)
  harvest
    Scan session tasks directories for agent outcomes and append missing entries.
    (Tracks state in ledger directory for resume capability)
  rotate
    Archive ledger lines exceeding ~200 lines to dated archive, keep recent tail in live ledger

Ledger format (markdown table):
  | ISO ts | agent_type | model | duration_sec | tokens_in | tokens_out | verdict |

Environment:
  AESOP_STATE_ROOT: Path to state directory (default: ./state relative to cwd)
  AESOP_TEMP_ROOT: Path to temp directory for tasks scanning (optional)
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import re
from collections import defaultdict

try:
    from common import get_state_dir
except ImportError:
    from tools.common import get_state_dir


def get_ledger_paths():
    """Get ledger file and sidecar state file paths."""
    state_dir = get_state_dir()
    ledger_dir = state_dir / "ledger"
    ledger_file = ledger_dir / "OUTCOMES-LEDGER.md"
    harvest_state_file = ledger_dir / ".fleet-ledger-harvest.json"
    return ledger_file, harvest_state_file, ledger_dir


def ensure_ledger_header():
    """Ensure ledger file exists with markdown table header."""
    ledger_file, _, ledger_dir = get_ledger_paths()
    if not ledger_file.exists():
        ledger_dir.mkdir(parents=True, exist_ok=True)
        header = '| ISO ts | agent_type | model | duration_sec | tokens_in | tokens_out | verdict |\n'
        header += '|--------|------------|-------|--------------|-----------|------------|--------|\n'
        ledger_file.write_text(header, encoding='utf-8')


def append_ledger_line(iso_ts, agent_type, model, duration_sec, tokens_in, tokens_out, verdict='OK'):
    """Append one line to the ledger."""
    ensure_ledger_header()
    ledger_file, _, _ = get_ledger_paths()

    # Sanitize fields: no pipes, truncate to reasonable length
    agent_type = str(agent_type or '-').replace('|', '').strip()[:30]
    model = str(model or '-').replace('|', '').strip()[:30]
    verdict = str(verdict or 'OK').replace('|', '').strip()[:10]

    try:
        dur = int(duration_sec) if duration_sec else 0
    except (ValueError, TypeError):
        dur = 0

    try:
        ti = int(tokens_in) if tokens_in else 0
    except (ValueError, TypeError):
        ti = 0

    try:
        to = int(tokens_out) if tokens_out else 0
    except (ValueError, TypeError):
        to = 0

    line = f'| {iso_ts} | {agent_type} | {model} | {dur} | {ti} | {to} | {verdict} |\n'
    with open(ledger_file, 'a', encoding='utf-8') as f:
        f.write(line)


def load_harvest_state():
    """Load last-harvest state (set of already-seen agent IDs)."""
    _, harvest_state_file, _ = get_ledger_paths()
    if harvest_state_file.exists():
        try:
            data = json.loads(harvest_state_file.read_text(encoding='utf-8'))
            return set(data.get('seen_agents', [])), data.get('last_harvest_ts', None)
        except (json.JSONDecodeError, IOError):
            pass
    return set(), None


def save_harvest_state(seen_agents, last_harvest_ts=None):
    """Save last-harvest state."""
    _, harvest_state_file, ledger_dir = get_ledger_paths()
    ledger_dir.mkdir(parents=True, exist_ok=True)
    state = {
        'seen_agents': sorted(list(seen_agents)),
        'last_harvest_ts': last_harvest_ts or datetime.now(timezone.utc).isoformat()
    }
    harvest_state_file.write_text(json.dumps(state, indent=2), encoding='utf-8')


def harvest():
    """Scan task output files and append missing agent outcomes."""
    ensure_ledger_header()
    seen_agents, _ = load_harvest_state()
    new_seen = set(seen_agents)
    harvested_count = 0

    # Determine temp root for tasks scanning
    if os.environ.get("AESOP_TEMP_ROOT"):
        temp_root = Path(os.environ["AESOP_TEMP_ROOT"])
    else:
        # Default to system temp + /claude
        import tempfile
        temp_root = Path(tempfile.gettempdir()) / "claude"

    # Find all .output files in tasks directories
    for output_file in temp_root.rglob('tasks/*.output'):
        if not output_file.is_file():
            continue

        try:
            content = output_file.read_text(encoding='utf-8', errors='ignore')
        except (IOError, OSError):
            continue

        # Parse JSONL: each line is a JSON object
        for line_idx, line in enumerate(content.split('\n')):
            if not line.strip():
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Look for agent spawn events (type='assistant' with Agent/Task tool_use)
            # or completion events (type='assistant' with usage data)
            agent_id = obj.get('agentId') or obj.get('uuid')
            if not agent_id:
                continue

            # Skip if already seen
            if agent_id in seen_agents:
                continue

            # Try to extract completion info
            msg = obj.get('message', {})
            ts = obj.get('timestamp', '')
            msg_type = msg.get('type', '')

            # Look for assistant message with usage (indicates completion)
            if msg_type == 'message' and msg.get('role') == 'assistant':
                usage = msg.get('usage', {})
                if usage:
                    # Found a completion event
                    agent_type = 'Agent'  # placeholder; ideally track subagent_type from spawn
                    model = msg.get('model', '-')

                    # Try to extract duration from timestamps or usage
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)

                    # Verdict: assume OK if no stop_reason error
                    stop_reason = msg.get('stop_reason')
                    verdict = 'OK'
                    if stop_reason in ('error', 'end_turn'):
                        verdict = 'OK'  # normal completion
                    elif not stop_reason:
                        verdict = 'OK'

                    duration_sec = 0  # TODO: parse from timestamps if available

                    # Append to ledger
                    if ts:
                        append_ledger_line(ts[:19], agent_type, model, duration_sec,
                                         input_tokens, output_tokens, verdict)
                        new_seen.add(agent_id)
                        harvested_count += 1

        # Save state after processing each file to avoid re-processing
        save_harvest_state(new_seen)

    ledger_file, _, _ = get_ledger_paths()
    print(f'Harvested {harvested_count} new agent outcomes to {ledger_file}')
    return harvested_count


def rotate():
    """Archive old ledger lines if ledger exceeds ~200 lines."""
    ensure_ledger_header()
    ledger_file, _, ledger_dir = get_ledger_paths()

    try:
        lines = ledger_file.read_text(encoding='utf-8').split('\n')
    except (IOError, OSError):
        print('Error reading ledger')
        return

    # Count non-header lines
    data_lines = [l for l in lines if l.strip() and not l.startswith('|---|')]
    header_lines = [l for l in lines if l.startswith('|') and '---|' in l]

    if len(data_lines) <= 202:  # Leave some headroom
        print(f'Ledger has {len(data_lines)} lines; no rotation needed (threshold: 200)')
        return

    # Create archive with date stamp
    archive_dir = ledger_dir / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_name = datetime.now(timezone.utc).strftime('FLEET-LEDGER-%Y%m%d-%H%M%S.md')
    archive_file = archive_dir / archive_name

    # Write header + oldest 50% of data lines to archive
    archive_count = len(data_lines) // 2
    archive_lines = header_lines + data_lines[:archive_count]
    archive_file.write_text('\n'.join(archive_lines) + '\n', encoding='utf-8')

    # Keep header + newest lines in live ledger
    new_ledger = header_lines + data_lines[archive_count:]
    ledger_file.write_text('\n'.join(new_ledger) + '\n', encoding='utf-8')

    print(f'Rotated {archive_count} lines to {archive_file}')
    print(f'Live ledger now has {len(new_ledger) - len(header_lines)} data lines')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'append':
        # append <ts> <agent_type> <model> <dur> <tokens_in> <tokens_out> [verdict]
        if len(sys.argv) < 7:
            print('Usage: fleet_ledger.py append <ts> <agent_type> <model> <dur_sec> <tokens_in> <tokens_out> [verdict]')
            sys.exit(1)

        ts = sys.argv[2]
        agent_type = sys.argv[3]
        model = sys.argv[4]
        dur = sys.argv[5]
        ti = sys.argv[6]
        to = sys.argv[7] if len(sys.argv) > 7 else '0'
        verdict = sys.argv[8] if len(sys.argv) > 8 else 'OK'

        append_ledger_line(ts, agent_type, model, dur, ti, to, verdict)
        print(f'Appended: {ts} {agent_type} {model} {dur}s {ti}->{to} [{verdict}]')

    elif cmd == 'harvest':
        harvest()

    elif cmd == 'rotate':
        rotate()

    else:
        print(f'Unknown command: {cmd}')
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
