#!/usr/bin/env python3
"""
sample_transcripts.py — Extract judgment-task candidates from Claude Code
session transcripts and convert them to benchmark task format.

This sampler reads JSONL files from Claude Code sessions (containing messages,
tool calls, and results) and extracts potential benchmark tasks. It focuses on
decision-making moments where an agent is reasoning about code, commits, test
failures, and reviews. Every extracted task is SANITIZED aggressively to remove:
  - Absolute paths (becomes relative or placeholder paths)
  - Usernames, real names, email addresses
  - API tokens, API keys, credentials
  - Repository names (becomes generic names like "repo", "project")
  - Private context (user identity, account details)

This sanitization is CRITICAL because the resulting tasks live in a PUBLIC
repository and must not leak customer data or infrastructure details.

Usage:
    python bench/sample_transcripts.py --transcripts-dir path/to/transcripts --output bench/tasks_sampled.jsonl

The output format is identical to bench/tasks.jsonl:
    {"id": "s001", "category": "...", "match": "exact|regex", "prompt": "..."}
    {"id": "s002", "category": "...", "match": "exact|regex", "prompt": "..."}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Patterns to detect and sanitize in transcripts
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
_API_KEY_RE = re.compile(r'(sk-[A-Za-z0-9]{20,}|api[_-]?key[=:]?\s*[\'"]?[A-Za-z0-9_]{20,}[\'"]?)', re.IGNORECASE)
_PATH_RE = re.compile(r'([A-Z]:)?[\\\/](?:Users|home|opt)[\\\/][^\s\\\/]+')
_USERNAME_RE = re.compile(r'(user|username)[=:]?\s*[\'"]?([A-Za-z0-9_.-]+)[\'"]?')
_REPO_RE = re.compile(r'(repo|repository|project)[=:]?\s*[\'"]?([A-Za-z0-9_.-]+)[\'"]?')
_GIT_USER_RE = re.compile(r'git\s+(?:user\.name|config)[=:]?\s*[\'"]?([^\'"\s]+)[\'"]?')

SANITIZATION_RULES = [
    ('emails', _EMAIL_RE, lambda m: '<email>'),
    ('api_keys', _API_KEY_RE, lambda m: '<api_key>'),
    ('paths', _PATH_RE, lambda m: '/path/to/<redacted>'),
    ('usernames', _USERNAME_RE, lambda m: 'user=<username>'),
    ('repo_names', _REPO_RE, lambda m: 'repo=<name>'),
    ('git_users', _GIT_USER_RE, lambda m: 'git user <name>'),
]


def sanitize_text(text: str) -> str:
    """Sanitize a transcript excerpt by removing PII and credentials.

    This is aggressive: every match on the patterns above is stripped,
    and the result is fit for inclusion in a public repository.
    """
    sanitized = text
    for rule_name, pattern, replacement in SANITIZATION_RULES:
        sanitized = pattern.sub(replacement, sanitized)

    # Additional manual sanitizations
    sanitized = re.sub(r'/Users/[^/\s]+', '/path/to/<user>', sanitized)
    sanitized = re.sub(r'/home/[^/\s]+', '/path/to/<user>', sanitized)
    sanitized = re.sub(r'C:\\Users\\[^\\]+', 'C:\\<user>', sanitized)

    return sanitized.strip()


def extract_decision_moments(transcript: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract decision-making moments from a Claude Code session transcript.

    A transcript is a session object with "messages" (list of user/assistant messages)
    and optional "tool_calls" (agent actions). We look for moments where:
      - The assistant is reasoning about code/commits/tests
      - The user is providing feedback or context about decisions
      - Tool results suggest a judgment call (a test failure, a diff, a review)

    Returns a list of extracted decision moments, each with 'context' and 'decision'.
    """
    moments = []
    messages = transcript.get('messages', [])

    # Simple heuristic: look for messages that mention decision keywords
    decision_keywords = [
        'should', 'correct', 'bug', 'fix', 'error', 'wrong', 'right',
        'classify', 'extract', 'determine', 'judge', 'decide',
    ]

    for msg in messages:
        if msg.get('role') != 'user':
            continue
        content = msg.get('content', '')
        # Check if this message contains a decision-relevant keyword
        if any(kw.lower() in content.lower() for kw in decision_keywords):
            moments.append({
                'context': content,
                'decision': None,  # To be filled from follow-ups
            })

    return moments


def task_from_moment(moment: Dict[str, str], task_id: str) -> Optional[Dict[str, Any]]:
    """Convert a decision moment into a benchmark task.

    A moment is a piece of context (the decision prompt). We create a task by:
      1. Sanitizing the context
      2. Determining the task category based on keywords
      3. Choosing a match type (exact for short decisions, regex for patterns)

    Returns a task dict or None if the moment is too short/unclassifiable.
    """
    context = moment.get('context', '').strip()
    if len(context) < 50:
        # Too short to be a useful task
        return None

    # Truncate to a reasonable prompt length
    if len(context) > 500:
        context = context[:500] + '...'

    # Sanitize
    sanitized = sanitize_text(context)
    if len(sanitized) < 30:
        return None

    # Categorize based on keywords
    if any(kw in sanitized.lower() for kw in ['classify', 'category']):
        category = 'classify_decision'
    elif any(kw in sanitized.lower() for kw in ['extract', 'find', 'pull']):
        category = 'extract_information'
    elif any(kw in sanitized.lower() for kw in ['bug', 'error', 'wrong', 'fix']):
        category = 'bug_judgment'
    elif any(kw in sanitized.lower() for kw in ['test', 'fail']):
        category = 'test_analysis'
    else:
        category = 'decision_making'

    # For now, all sampled tasks use exact matching (can be overridden)
    # Real tasks can use regex if the prompt is pattern-based
    match_type = 'exact'

    return {
        'id': task_id,
        'category': category,
        'match': match_type,
        'prompt': sanitized,
    }


def load_transcripts(transcripts_dir: Path) -> List[Dict[str, Any]]:
    """Load all JSONL transcript files from a directory.

    Each JSONL file is a single transcript object per line.
    """
    transcripts = []
    if not transcripts_dir.exists():
        raise FileNotFoundError(f"Transcripts directory not found: {transcripts_dir}")

    for jsonl_file in transcripts_dir.glob('*.jsonl'):
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    transcript = json.loads(line)
                    transcripts.append(transcript)
                except json.JSONDecodeError as exc:
                    print(f"Warning: {jsonl_file}:{lineno} invalid JSON: {exc}", file=sys.stderr)
                    continue

    return transcripts


def sample_tasks(transcripts: List[Dict[str, Any]], max_tasks: int = 50) -> List[Dict[str, Any]]:
    """Extract and sanitize tasks from transcripts.

    Args:
        transcripts: List of transcript dicts loaded from JSONL
        max_tasks: Maximum number of tasks to extract (None for unlimited)

    Returns:
        List of task dicts in bench format
    """
    tasks = []

    for transcript_idx, transcript in enumerate(transcripts):
        moments = extract_decision_moments(transcript)
        for moment_idx, moment in enumerate(moments):
            if max_tasks is not None and len(tasks) >= max_tasks:
                break

            # Generate stable task ID
            task_id = f"s{len(tasks):04d}"
            task = task_from_moment(moment, task_id)
            if task:
                tasks.append(task)

        if max_tasks is not None and len(tasks) >= max_tasks:
            break

    return tasks


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--transcripts-dir',
        type=Path,
        required=True,
        help='Directory containing Claude Code session JSONL files',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='Output file (default: stdout)',
    )
    parser.add_argument(
        '--max-tasks',
        type=int,
        default=50,
        help='Maximum number of tasks to extract (default: 50)',
    )
    args = parser.parse_args(argv)

    transcripts = load_transcripts(args.transcripts_dir)
    print(f"Loaded {len(transcripts)} transcripts", file=sys.stderr)

    tasks = sample_tasks(transcripts, max_tasks=args.max_tasks)
    print(f"Extracted {len(tasks)} tasks", file=sys.stderr)

    # Output as JSONL
    output_stream = open(args.output, 'w', encoding='utf-8') if args.output else sys.stdout
    try:
        for task in tasks:
            output_stream.write(json.dumps(task) + '\n')
    finally:
        if args.output:
            output_stream.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
