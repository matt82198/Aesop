#!/usr/bin/env python3
"""
sample_transcripts.py — Extract completed coding tasks from Claude Code transcripts.

Samples CODING tasks from Claude Code session transcript JSONL files
(the output of agent runs), redacts sensitive information, and emits them as
bench task records matching the schema expected by coding_grader.py.

A sampled task is only gradeable if it includes:
  1. A clear task prompt (what the agent was asked to do)
  2. Code the agent produced
  3. Either:
     a. A checkable specification (test cases, assertions), OR
     b. A marker needs_grader_authoring=true (task has no spec yet)

Tasks without a checkable spec are marked needs_grader_authoring rather than
silently produced as "pass" — preserving the honest gap between code written
and code we can verify actually solves the task.

Sanitization: aggressive redaction of PII (paths, emails, tokens, usernames,
repo names) before emitting tasks to a public repository.

Usage:
    python bench/sample_transcripts.py \\
      --transcripts-dir /path/to/transcripts \\
      --output bench/tasks_sampled.jsonl \\
      --max-tasks 100

Deterministic (sys.executable for subprocess, no hardcoded timestamps, ASCII-only).
No network, no model calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logging (stderr only, stdout reserved for JSON)
logging.basicConfig(
    format='%(levelname)s: %(message)s',
    level=logging.INFO,
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


# Patterns for aggressive redaction of PII/credentials
REDACTION_PATTERNS = [
    # API keys and tokens (40+ hex chars, sk-prefixed, etc.)
    (r'\b(?:[a-zA-Z0-9_-]{32,}|sk-[a-zA-Z0-9]{20,})\b', '<api_key>'),
    # Email addresses
    (r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', '<email>'),
    # Absolute Windows paths
    (r'[A-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*', '<path>'),
    # Absolute Unix paths
    (r'(?:/(?:home|root|var|etc|tmp|usr|Users|opt)/[^\s"\'<>]+)', '<path>'),
    # Usernames in common patterns
    (r'(?:user|username)["\']?\s*[=:]\s*["\']?([a-zA-Z0-9_.-]+)["\']?', r'user=<username>'),
]


def redact_sensitive_data(text: str) -> str:
    """Remove PII, credentials, and paths from text.

    Applies aggressive redaction patterns, then strips non-ASCII to ensure
    safe transport in JSON. Output is always ASCII-safe.
    """
    result = text
    for pattern, replacement in REDACTION_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Strip any non-ASCII (they may leak in weird ways)
    result = ''.join(c if ord(c) < 128 else '?' for c in result)

    return result


def is_code_response(text: str) -> Tuple[bool, Optional[str]]:
    """Detect if a response contains code and infer the language.

    Returns (is_code: bool, language: str|None) where language is 'python',
    'javascript', 'bash', etc., or None if code is present but language
    is not clearly identifiable.
    """
    # Markdown code fences are most reliable
    fence_match = re.search(r'```(\w+)?', text)
    if fence_match:
        lang = fence_match.group(1) or None
        return True, lang

    # Heuristics for indented/undecorated code
    if re.search(r'^\s{4,}(?:def|class|if|for|while|import|from|async)', text, re.MULTILINE):
        return True, 'python'

    if re.search(r'^\s{4,}(?:function|const|let|var|async|class|import)', text, re.MULTILINE):
        return True, 'javascript'

    if re.search(r'^\s{4,}(?:#!/bin/bash|#!/bin/sh|set -)', text, re.MULTILINE):
        return True, 'bash'

    return False, None


def extract_code_from_text(text: str) -> Optional[str]:
    """Extract a code block from text that may contain prose/fences.

    Prefers markdown fences (```lang ... ```), falls back to indented blocks.
    Returns extracted code or None if none found.
    """
    lines = text.split('\n')

    # Try markdown fences first
    in_fence = False
    code_lines = []

    for line in lines:
        if re.match(r'^```', line):
            if not in_fence:
                in_fence = True
            else:
                in_fence = False
            continue

        if in_fence:
            code_lines.append(line)

    if code_lines:
        return '\n'.join(code_lines).strip()

    # Fallback: collect indented lines (4+ spaces or tabs)
    code_lines = []
    for line in lines:
        if line and line[0] in ' \t':
            code_lines.append(line)
        elif re.match(r'^(?:def|class|import|async|if|for|while)', line):
            code_lines.append(line)

    if code_lines:
        return '\n'.join(code_lines).strip()

    return None


def generate_task_id(transcript_path: str, turn_index: int) -> str:
    """Generate a stable, deterministic task ID (no timestamps).

    Uses SHA256(transcript_path:turn_index) for reproducibility.
    """
    key = f"{transcript_path}:{turn_index}".encode('utf-8')
    digest = hashlib.sha256(key).hexdigest()[:8]
    return f"sampled_{digest}"


def load_transcript_lines(transcript_path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL transcript file (one JSON object per line).

    Returns list of parsed turns (user, assistant, etc. events).
    Skips malformed lines with a warning.
    """
    lines = []
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    lines.append(obj)
                except json.JSONDecodeError:
                    logger.debug(f"{transcript_path}:{line_num} malformed JSON, skipped")
    except (IOError, OSError) as e:
        logger.warning(f"Could not read {transcript_path}: {e}")

    return lines


def extract_text_from_message(msg: Any) -> str:
    """Extract text content from a message object.

    Handles both dict (with 'content' key) and list (array of parts) formats.
    """
    if isinstance(msg, dict):
        content = msg.get('content', '')
        return content if isinstance(content, str) else ''

    if isinstance(msg, list):
        parts = []
        for part in msg:
            if isinstance(part, dict):
                parts.append(part.get('text', ''))
            elif isinstance(part, str):
                parts.append(part)
        return ' '.join(parts)

    if isinstance(msg, str):
        return msg

    return ''


def extract_coding_task_from_turns(
    transcript_path: str,
    turn_index: int,
    user_turn: Dict[str, Any],
    assistant_turn: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Extract a coding task from a user→assistant turn pair.

    Returns task dict with id, category, match, prompt, produced_code,
    needs_grader_authoring, or None if not a coding task.
    """
    # Extract user prompt text
    user_text = extract_text_from_message(user_turn.get('message'))

    # Extract assistant response text
    assistant_text = extract_text_from_message(assistant_turn.get('message'))

    # Must have both
    if not user_text or not assistant_text:
        return None

    # Check if assistant response contains code
    is_code, lang = is_code_response(assistant_text)
    if not is_code:
        return None

    # Extract the actual code
    code = extract_code_from_text(assistant_text)
    if not code:
        return None

    # Check if user prompted for code/implementation
    if not re.search(
        r'\b(?:write|code|implement|solve|function|script|program|class|module)\b',
        user_text,
        re.IGNORECASE
    ):
        return None

    # Redact both
    prompt_redacted = redact_sensitive_data(user_text[:500])  # Truncate long prompts
    code_redacted = redact_sensitive_data(code)

    # Heuristic: does prompt mention test cases, assertions, or examples?
    # If so, we have a checkable spec; otherwise, needs_grader_authoring.
    has_spec = bool(re.search(
        r'\b(?:test|assert|example|expected|should|verify|pass|input.*output)\b',
        user_text,
        re.IGNORECASE
    ))

    task_id = generate_task_id(transcript_path, turn_index)

    return {
        'id': task_id,
        'category': f'transcript_sampled_coding_{lang or "unknown"}',
        'match': 'exact',
        'prompt': prompt_redacted,
        'produced_code': code_redacted,
        'needs_grader_authoring': not has_spec,
    }


def sample_transcript_file(transcript_path: Path) -> Tuple[List[Dict[str, Any]], int]:
    """Sample all coding tasks from a single JSONL transcript file.

    Returns (tasks, needs_authoring_count).
    """
    tasks = []
    needs_authoring = 0

    turns = load_transcript_lines(transcript_path)
    if not turns:
        return tasks, needs_authoring

    # Pair user turns with following assistant turns
    i = 0
    while i < len(turns) - 1:
        user_turn = turns[i]

        # Find next assistant turn
        j = i + 1
        while j < len(turns) and turns[j].get('type') != 'assistant':
            j += 1

        if j >= len(turns):
            break

        if user_turn.get('type') == 'user':
            task = extract_coding_task_from_turns(
                str(transcript_path),
                i,
                user_turn,
                turns[j]
            )
            if task:
                tasks.append(task)
                if task.get('needs_grader_authoring'):
                    needs_authoring += 1

        i = j + 1

    return tasks, needs_authoring


def sample_transcripts(
    transcripts_dir: Path,
    max_tasks: int = 100,
    recursive: bool = True
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Sample coding tasks from all JSONL files in a directory.

    Returns (tasks, total_sampled, total_needs_authoring).
    """
    tasks = []
    total_sampled = 0
    total_needs_authoring = 0

    # Find all JSONL files
    pattern = '**/*.jsonl' if recursive else '*.jsonl'
    jsonl_files = sorted(transcripts_dir.glob(pattern))

    if not jsonl_files:
        logger.warning(f"No JSONL files found in {transcripts_dir}")
        return tasks, 0, 0

    logger.info(f"Found {len(jsonl_files)} transcript file(s)")

    for transcript_path in jsonl_files:
        if len(tasks) >= max_tasks:
            break

        file_tasks, needs_auth = sample_transcript_file(transcript_path)

        for task in file_tasks:
            if len(tasks) >= max_tasks:
                break
            tasks.append(task)
            total_sampled += 1
            total_needs_authoring += needs_auth

        if file_tasks:
            logger.info(f"  {transcript_path.name}: {len(file_tasks)} task(s)")

    return tasks, total_sampled, total_needs_authoring


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--transcripts-dir',
        type=Path,
        required=True,
        help='Directory containing transcript JSONL files'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('bench/tasks_sampled.jsonl'),
        help='Output JSONL file (default: bench/tasks_sampled.jsonl)'
    )
    parser.add_argument(
        '--max-tasks',
        type=int,
        default=100,
        help='Maximum tasks to sample (default: 100)'
    )
    parser.add_argument(
        '--recursive',
        action='store_true',
        default=True,
        help='Search recursively for JSONL files'
    )

    args = parser.parse_args(argv)

    if not args.transcripts_dir.exists():
        print(f"Error: {args.transcripts_dir} does not exist", file=sys.stderr)
        return 1

    logger.info(f"Sampling from {args.transcripts_dir}")
    tasks, num_sampled, num_needs_auth = sample_transcripts(
        args.transcripts_dir,
        max_tasks=args.max_tasks,
        recursive=args.recursive
    )

    # Write output JSONL
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            for task in tasks:
                f.write(json.dumps(task, ensure_ascii=True) + '\n')

        logger.info(f"Wrote {len(tasks)} task(s) to {args.output}")
        logger.info(f"  {num_needs_auth}/{num_sampled} need grader authoring")

    except (IOError, OSError) as e:
        print(f"Error writing {args.output}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
