#!/usr/bin/env python3
"""
bench_runner.py — Held-out benchmark scorer for fleet subagent capability claims.

Wave-26 context: an external critique observed that the claim "Haiku is sufficient
for fleet subagent work" was unmeasured and, where it *was* measured at all, was
self-graded by the fleet (agents grading agents) with results parked in a private
MEMORY.md. That is not evidence. This module is the MEASUREMENT APPARATUS, not a
verdict: it loads a fixed set of held-out tasks (bench/tasks.jsonl), scores a
model runner's outputs against externally-fixed ground truth (bench/ground_truth.jsonl)
by exact string match or regex match, and prints a per-model accuracy table.

It ships with a MOCK runner (`mock_runner`) so the SCORING LOGIC can be tested and
demonstrated completely offline, without calling any model or spending any tokens.
The mock runner is a small deterministic heuristic (regex/string-parsing stand-in).
Its accuracy says NOTHING about how Haiku, Sonnet, or Opus would actually score —
see bench/README.md for how to wire a real model runner.

Usage:
    python tools/bench_runner.py                  # run the mock runner, print table
    python tools/bench_runner.py --runner mock
    python tools/bench_runner.py --tasks path/to/tasks.jsonl --ground-truth path/to/gt.jsonl

Exit codes: 0 always on a completed run (this is a measurement tool, not a gate).
Programmatic API: load_tasks(), load_ground_truth(), score_output(), run_bench().
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

BENCH_DIR = Path(__file__).resolve().parent.parent / "bench"
DEFAULT_TASKS_PATH = BENCH_DIR / "tasks.jsonl"
DEFAULT_GROUND_TRUTH_PATH = BENCH_DIR / "ground_truth.jsonl"

REQUIRED_TASK_FIELDS = ("id", "category", "match", "prompt")
VALID_MATCH_TYPES = ("exact", "regex")

# A model runner is any callable that takes a prompt string and returns the
# model's raw text response. Real runners (Haiku/Sonnet/Opus/etc.) are wired
# by the caller; this module never imports a model SDK itself.
ModelRunner = Callable[[str], str]


def load_jsonl(path: Path) -> List[dict]:
    """Load a JSON-Lines file into a list of dicts. Blank lines are skipped."""
    items: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return items


def load_tasks(tasks_path: Optional[Path] = None) -> List[dict]:
    """Load the task list and validate required fields are present."""
    path = Path(tasks_path) if tasks_path else DEFAULT_TASKS_PATH
    tasks = load_jsonl(path)
    for task in tasks:
        missing = [f for f in REQUIRED_TASK_FIELDS if f not in task]
        if missing:
            raise ValueError(f"task {task.get('id', '<unknown>')} missing fields: {missing}")
        if task["match"] not in VALID_MATCH_TYPES:
            raise ValueError(
                f"task {task['id']} has invalid match type {task['match']!r}; "
                f"expected one of {VALID_MATCH_TYPES}"
            )
    return tasks


def load_ground_truth(ground_truth_path: Optional[Path] = None) -> Dict[str, dict]:
    """Load ground truth entries keyed by task id."""
    path = Path(ground_truth_path) if ground_truth_path else DEFAULT_GROUND_TRUTH_PATH
    entries = load_jsonl(path)
    by_id: Dict[str, dict] = {}
    for entry in entries:
        if "id" not in entry:
            raise ValueError(f"ground truth entry missing 'id': {entry}")
        by_id[entry["id"]] = entry
    return by_id


def score_output(output: Optional[str], ground_truth_entry: dict, match_type: str) -> bool:
    """Score a single model output against its ground truth entry.

    exact: case-insensitive, whitespace-trimmed string equality against
           ground_truth_entry["expected"].
    regex: re.search of ground_truth_entry["expected_regex"] against the
           trimmed output (search, not fullmatch — callers anchor with ^/$
           in the pattern when they need a full-string match).
    """
    if output is None:
        return False
    trimmed = output.strip()
    if match_type == "regex":
        pattern = ground_truth_entry.get("expected_regex")
        if pattern is None:
            raise ValueError("ground truth entry for a regex task is missing 'expected_regex'")
        return re.search(pattern, trimmed) is not None
    if match_type == "exact":
        expected = ground_truth_entry.get("expected")
        if expected is None:
            raise ValueError("ground truth entry for an exact task is missing 'expected'")
        return trimmed.lower() == str(expected).strip().lower()
    raise ValueError(f"unknown match type: {match_type!r}")


def run_bench(
    tasks: List[dict],
    ground_truth: Dict[str, dict],
    runner: ModelRunner,
) -> Tuple[List[dict], float]:
    """Run every task through `runner`, score against `ground_truth`.

    Returns (per_task_results, accuracy) where accuracy is correct/total
    (0.0 for an empty task list, never a division error).
    """
    results: List[dict] = []
    correct = 0
    for task in tasks:
        tid = task["id"]
        if tid not in ground_truth:
            raise KeyError(f"no ground truth entry for task id {tid!r}")
        gt_entry = ground_truth[tid]
        output = runner(task["prompt"])
        ok = score_output(output, gt_entry, task["match"])
        if ok:
            correct += 1
        results.append(
            {
                "id": tid,
                "category": task.get("category", ""),
                "output": output,
                "correct": ok,
            }
        )
    accuracy = correct / len(tasks) if tasks else 0.0
    return results, accuracy


# ---------------------------------------------------------------------------
# Mock runner — zero-cost, deterministic, offline. Exists ONLY to prove the
# scoring pipeline works end to end without a network call or an API key.
# Do not read its accuracy as evidence about any real model's capability.
# ---------------------------------------------------------------------------

_FILE_RE = re.compile(r"File:\s*(\S+)")
_FAILED_TEST_RE = re.compile(r"FAILED\s+\S+::(\w+)")
_ISSUE_NUM_RE = re.compile(r"#(\d+)")
_PR_TITLE_RE = re.compile(r"Title:\s*(\w+):")
_EXC_TYPE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):")
_VERSION_RE = re.compile(r"\[(\d+\.\d+\.\d+)\]")
_IDENTIFIER_RE = re.compile(r"Identifier:\s*(\S+)")
_FILE_LINE_RE = re.compile(r"([A-Za-z0-9_\-./]+\.py:\d+)")


def _classify_file_path(path: str) -> str:
    filename = path.rsplit("/", 1)[-1]
    if path.startswith("tests/") or "/tests/" in path or filename.startswith("test_"):
        return "test"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"md", "rst", "txt"}:
        return "docs"
    if ext in {"json", "yaml", "yml", "toml", "ini", "cfg"}:
        return "config"
    return "code"


def _snake_to_camel(identifier: str) -> str:
    parts = identifier.split("_")
    if not parts:
        return identifier
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def mock_runner(prompt: str) -> str:
    """Deterministic offline stand-in for a real model runner.

    Handles extraction/classification/transform tasks with plain regex and
    string logic (no judgment required). Deliberately does NOT attempt the
    semantic "is this a real bug" judgment task and always answers "no" for
    it — a cheap default that is sometimes wrong, so the scorer has at least
    one guaranteed miss to prove it distinguishes correct from incorrect
    (a mock that always scored 100% would not exercise the failure path).
    """
    m = _FILE_RE.search(prompt)
    if m and "Classify this changed file path" in prompt:
        return _classify_file_path(m.group(1))

    m = _FAILED_TEST_RE.search(prompt)
    if m and "failing test function" in prompt:
        return m.group(1)

    if "issue/PR number" in prompt:
        m = _ISSUE_NUM_RE.search(prompt)
        if m:
            return m.group(1)

    m = _PR_TITLE_RE.search(prompt)
    if m and "PR title" in prompt:
        return m.group(1)

    if "exception class name" in prompt:
        matches = _EXC_TYPE_RE.findall(prompt)
        if matches:
            return matches[-1]

    if "is the finding a real bug" in prompt:
        return "no"

    m = _VERSION_RE.search(prompt)
    if m and "semantic version" in prompt:
        return m.group(1)

    m = _IDENTIFIER_RE.search(prompt)
    if m and "camelCase" in prompt:
        return _snake_to_camel(m.group(1))

    m = _FILE_LINE_RE.search(prompt)
    if m and "path:line" in prompt:
        return m.group(1)

    return ""


RUNNERS: Dict[str, ModelRunner] = {
    "mock": mock_runner,
}


def print_table(model_name: str, results: List[dict], accuracy: float, stream=None) -> None:
    stream = stream or sys.stdout
    print(f"\nBenchmark results -- runner: {model_name}", file=stream)
    print("-" * 60, file=stream)
    print(f"{'id':<6}{'category':<28}{'result':<8}", file=stream)
    for r in results:
        mark = "PASS" if r["correct"] else "FAIL"
        print(f"{r['id']:<6}{r['category']:<28}{mark:<8}", file=stream)
    print("-" * 60, file=stream)
    n = len(results)
    n_correct = sum(1 for r in results if r["correct"])
    print(f"Accuracy: {n_correct}/{n} = {accuracy:.1%}", file=stream)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner",
        default="mock",
        choices=sorted(RUNNERS.keys()),
        help="Which registered model runner to score (default: mock, offline/zero-cost).",
    )
    parser.add_argument("--tasks", default=None, help="Override path to tasks.jsonl")
    parser.add_argument("--ground-truth", default=None, help="Override path to ground_truth.jsonl")
    args = parser.parse_args(argv)

    tasks = load_tasks(args.tasks)
    ground_truth = load_ground_truth(args.ground_truth)
    runner = RUNNERS[args.runner]

    results, accuracy = run_bench(tasks, ground_truth, runner)
    print_table(args.runner, results, accuracy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
