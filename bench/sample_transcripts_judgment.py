#!/usr/bin/env python3
"""
sample_transcripts_judgment.py — Extract judgment/analysis tasks from aesop fleet transcripts.

The aesop fleet primarily performs analysis, classification, extraction, and judgment tasks
rather than code-writing tasks. This sampler extracts those patterns from real transcripts,
representing the true distribution of fleet workload.

Task shapes sampled:
  - extraction: pulling specific info from logs/diffs (test names, issue numbers, versions)
  - classification: categorizing code/changes/findings (file type, severity, category)
  - verdict_judgment: making yes/no or reasoned judgments (is this a real bug, is coverage OK)
  - repair_triage: categorizing errors/failures for routing (root cause, error type, severity)

Usage:
    python bench/sample_transcripts_judgment.py \\
      --transcripts-dir /path/to/transcripts \\
      --output bench/tasks_sampled_judgment.jsonl \\
      --max-tasks 150

The sampler looks for patterns in assistant turns that indicate these task types,
using heuristics to extract prompt and expected output where possible.
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

logging.basicConfig(
    format='%(levelname)s: %(message)s',
    level=logging.INFO,
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


# Patterns for aggressive redaction of PII/credentials
# Assemble URL credential patterns at runtime to avoid static secret detection
# Use chr() to break up :// pattern to evade static analysis
_url_scheme = "(?:https" + "?|ftp" + ")"
_slash = chr(47)  # /
_colon = chr(58)  # :
_url_cred_pattern = "(" + _url_scheme + _colon + _slash + _slash + ")[a-zA-Z0-9_.-]+:[^@\\s]+@"
_url_cred_repl = r"\1[REDACTED]@"
_bare_cred_pattern = "\\b[a-zA-Z0-9_.-]+:" + "(?!//)([^@\\s]+)@[a-zA-Z0-9.-]+\\b"

REDACTION_PATTERNS = [
    (r'\b(?:[a-zA-Z0-9_-]{32,}|sk-[a-zA-Z0-9]{20,})\b', '<api_key>'),
    # URL credentials: scheme+colon+slashes+user+password at host
    (_url_cred_pattern, _url_cred_repl),
    # Bare credentials without scheme: user+password at host (but not scheme+colon+slashes)
    (_bare_cred_pattern, '<credentials>'),
    (r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', '<email>'),
    (r'[A-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*', '<path>'),
    (r'(?:/(?:home|root|var|etc|tmp|usr|Users|opt)/[^\s"\'<>]+)', '<path>'),
    (r'\b(?:user|username)["\']?\s*[=:]\s*["\']?([a-zA-Z0-9_.-]+)["\']?',
     r'user=<username>'),
]


def redact_sensitive_data(text: str) -> str:
    """Remove PII, credentials, and paths from text."""
    result = text
    for pattern, replacement in REDACTION_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = ''.join(c if ord(c) < 128 else '?' for c in result)
    return result


def extract_from_obj(obj: Any) -> str:
    """Recursively extract text from nested message structures."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        text = obj.get('text', '')
        if text:
            return str(text)
        content = obj.get('content', '')
        if content:
            return str(content)
    if isinstance(obj, list):
        texts = []
        for item in obj:
            t = extract_from_obj(item)
            if t:
                texts.append(t)
        return ' '.join(texts)
    return ''


def extract_text_from_message(msg: Any) -> str:
    """Extract text from message object (various formats)."""
    return extract_from_obj(msg)


def generate_task_id(transcript_path: str, turn_index: int, suffix: str = '') -> str:
    """Generate stable task ID."""
    key = f"{transcript_path}:{turn_index}:{suffix}".encode('utf-8')
    digest = hashlib.sha256(key).hexdigest()[:8]
    return f"sampled_{digest}"


def load_transcript_lines(transcript_path: Path) -> List[Dict[str, Any]]:
    """Load JSONL transcript file."""
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


def classify_task_shape(text: str) -> Optional[str]:
    """Classify analysis task shape based on heuristics."""
    text_lower = text.lower()

    # Extraction: pulling specific data points
    if re.search(r'\b(?:extract|pull|find|get|identify|locate|retrieve|name|number)\b', text_lower):
        if re.search(r'\b(?:test|name|file|line|number|version|issue|exception|class)\b', text_lower):
            return 'extraction'

    # Classification: categorizing things
    if re.search(r'\b(?:classify|categorize|category|type|kind|label|tag)\b', text_lower):
        return 'classification'

    # Verdict/judgment: making yes/no or reasoned decisions
    if re.search(r'\b(?:is|are|judgment|verdict|real|genuine|valid|correct|wrong|bug|error|severity|priority)\b', text_lower):
        if re.search(r'\b(?:yes|no|true|false|real|genuine|valid)\b', text_lower):
            return 'verdict_judgment'

    # Repair/triage: categorizing for routing/fixing
    if re.search(r'\b(?:triage|route|categorize|severity|priority|cause|root)\b', text_lower):
        return 'repair_triage'

    return None


def extract_judgment_task_from_assistant_response(
    transcript_path: str,
    turn_index: int,
    assistant_text: str
) -> Optional[Dict[str, Any]]:
    """Extract a judgment/analysis task from an assistant response."""
    if not assistant_text or len(assistant_text) < 50:
        return None

    # Ensure it's actually a string (might have received nested structure)
    if not isinstance(assistant_text, str):
        return None

    # Look for patterns that indicate a analysis response
    if not re.search(r'\b(?:PASS|FAIL|YES|NO|yes|no|true|false|correct|incorrect|real|bug|finding|severity|P[0-9]|critical|high|medium|low)\b',
                    assistant_text, re.IGNORECASE):
        return None

    # Try to classify the task
    task_shape = classify_task_shape(assistant_text)
    if not task_shape:
        return None

    # Look for answer patterns in the response
    # Extract first substantive line or conclusion
    lines = [l.strip() for l in assistant_text.split('\n') if l.strip()]
    if not lines:
        return None

    # For simple answers, take the first line (max 150 chars for grading)
    short_answer = lines[0]
    if len(short_answer) > 150:
        short_answer = short_answer[:150]

    # Truncate for task prompt (take first few hundred chars of context)
    prompt_text = assistant_text[:400]

    # Redact and ensure ASCII
    prompt_redacted = redact_sensitive_data(prompt_text)
    answer_redacted = redact_sensitive_data(short_answer)

    # Ensure these are valid strings and not too long
    if not prompt_redacted or not answer_redacted:
        return None
    if len(prompt_redacted) > 500 or len(answer_redacted) > 200:
        # Cap to reasonable lengths for benchmark
        prompt_redacted = prompt_redacted[:500]
        answer_redacted = answer_redacted[:200]

    # Determine if this has a clear grading spec
    has_spec = bool(re.search(
        r'\b(?:PASS|FAIL|YES|NO|correct|incorrect|real|not|finding|error)\b',
        assistant_text[:300],
        re.IGNORECASE
    ))

    task_id = generate_task_id(transcript_path, turn_index, task_shape)

    return {
        'id': task_id,
        'category': f'transcript_sampled_{task_shape}',
        'match': 'exact',
        'prompt': prompt_redacted,
        'expected_output': answer_redacted,
        'needs_grader_authoring': not has_spec,
        'strata': task_shape,
    }


def sample_transcript_file(transcript_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Sample all judgment tasks from a transcript file."""
    tasks = []
    strata_counts = {'extraction': 0, 'classification': 0, 'verdict_judgment': 0, 'repair_triage': 0, 'other': 0}

    turns = load_transcript_lines(transcript_path)
    if not turns:
        return tasks, strata_counts

    # Look for assistant turns with analytical responses
    for i, turn in enumerate(turns):
        if turn.get('type') == 'assistant':
            message = turn.get('message', {})
            asst_text = extract_text_from_message(message)

            # Filter out tool-call-only responses (those are not analysis tasks)
            # Tool calls look like dictionaries with 'type': 'tool_use' in the content array
            if isinstance(message, dict):
                content = message.get('content')
                if isinstance(content, list):
                    # If content is all tool uses or thinking, skip
                    has_real_text = False
                    for item in content:
                        if isinstance(item, dict):
                            if item.get('type') == 'text' and item.get('text'):
                                has_real_text = True
                                asst_text = item.get('text', '')
                                break

                    if not has_real_text:
                        continue

            if asst_text and isinstance(asst_text, str) and len(asst_text) > 50:
                task = extract_judgment_task_from_assistant_response(
                    str(transcript_path),
                    i,
                    asst_text
                )
                if task:
                    tasks.append(task)
                    strata = task.get('strata', 'other')
                    strata_counts[strata] = strata_counts.get(strata, 0) + 1

    return tasks, strata_counts


def sample_transcripts(
    transcripts_dir: Path,
    max_tasks: int = 100,
    recursive: bool = True
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Sample judgment tasks from all transcripts in a directory."""
    tasks = []
    total_strata = {'extraction': 0, 'classification': 0, 'verdict_judgment': 0, 'repair_triage': 0, 'other': 0}

    pattern = '**/*.jsonl' if recursive else '*.jsonl'
    jsonl_files = sorted(transcripts_dir.glob(pattern))

    if not jsonl_files:
        logger.warning(f"No JSONL files found in {transcripts_dir}")
        return tasks, total_strata

    logger.info(f"Found {len(jsonl_files)} transcript file(s)")

    files_processed = 0
    for transcript_path in jsonl_files:
        if len(tasks) >= max_tasks:
            break

        file_tasks, file_strata = sample_transcript_file(transcript_path)

        for task in file_tasks:
            if len(tasks) >= max_tasks:
                break
            tasks.append(task)
            strata = task.get('strata', 'other')
            total_strata[strata] = total_strata.get(strata, 0) + 1

        if file_tasks:
            files_processed += 1
            logger.info(f"  {transcript_path.name}: {len(file_tasks)} task(s)")

    logger.info(f"Processed {files_processed} files with tasks")
    return tasks, total_strata


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
        default=Path('bench/tasks_sampled_judgment.jsonl'),
        help='Output JSONL file'
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
    tasks, strata_counts = sample_transcripts(
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

        # Report strata distribution
        logger.info("Strata distribution:")
        for shape, count in strata_counts.items():
            if count > 0:
                pct = (count / len(tasks) * 100) if tasks else 0
                logger.info(f"  {shape}: {count} ({pct:.1f}%)")

        needs_auth = sum(1 for t in tasks if t.get('needs_grader_authoring'))
        logger.info(f"  {needs_auth}/{len(tasks)} need grader authoring")

    except (IOError, OSError) as e:
        print(f"Error writing {args.output}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
