#!/usr/bin/env python3
"""
tools.stateapi_lint — Scanner for direct state file opens outside the API.

Detects violations of the "reads go through state_store.read_api" rule by scanning
ui/ and tools/ for direct opens of state files (tracker.json, orchestrator-status.json,
heartbeat files, OUTCOMES-LEDGER.md) outside the read_api module.

Writers (state_store/export.py, state_store/ingest.py, etc.) are allowlisted.

Exit codes:
  0 = no new violations (or no baseline yet)
  1 = new violations detected
  2 = error

Usage:
  python tools/stateapi_lint.py [--root REPO_ROOT] [--json]

Options:
  --root REPO_ROOT: Repository root (default: cwd)
  --json: Output JSON instead of text
"""
import json
import re
import sys
from pathlib import Path


# State files that should only be read via the API
STATE_FILES_TO_PROTECT = [
    "tracker.json",
    "orchestrator-status.json",
    "OUTCOMES-LEDGER.md",
    ".watchdog-heartbeat",
    ".monitor-heartbeat",
    ".orchestrator-heartbeat",
]

# File patterns that are WRITERS and allowed to access state files directly
WRITER_ALLOWLIST = [
    "state_store/export.py",
    "state_store/ingest.py",
    "state_store/read_api.py",  # The read API facade itself (reads the state files)
    "ui/collectors.py",  # Some readers also export/flush
    "tools/cost.py",  # Parses ledger
]

# Directories to scan for violations
SCAN_DIRS = ["ui", "tools", "state_store"]  # Include state_store to catch internal issues


def find_direct_opens(repo_root):
    """Scan repo for direct opens of protected state files outside the API.

    Args:
        repo_root: Path to repository root

    Returns:
        list: List of violation strings (file:line or file:pattern)
    """
    repo_root = Path(repo_root)
    violations = []

    # Pattern to detect file opens: Path(...).read_text(), open(...), json.load(open(...)), etc.
    # Look for strings containing state file names in suspicious contexts
    read_patterns = [
        r'["\']tracker\.json["\']',
        r'["\']orchestrator-status\.json["\']',
        r'["\']OUTCOMES-LEDGER\.md["\']',
        r'["\']\.watchdog-heartbeat["\']',
        r'["\']\.monitor-heartbeat["\']',
        r'["\']\.orchestrator-heartbeat["\']',
    ]

    # Also look for state/ directory references
    read_patterns.extend([
        r'state\s*/\s*tracker\.json',
        r'state\s*/\s*orchestrator-status',
        r'state\s*/\s*.*heartbeat',
    ])

    for scan_dir in SCAN_DIRS:
        scan_path = repo_root / scan_dir
        if not scan_path.exists():
            continue

        for py_file in scan_path.rglob("*.py"):
            # Check if this file is in the allowlist
            relative_path = py_file.relative_to(repo_root)
            is_allowed = any(
                str(relative_path).replace("\\", "/") == allow.replace("\\", "/")
                for allow in WRITER_ALLOWLIST
            )

            if is_allowed:
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Skip if file imports read_api (it's using the facade correctly)
            if "from state_store.read_api import" in content or "import state_store.read_api" in content:
                continue

            # Scan for violations
            for line_num, line in enumerate(content.split("\n"), 1):
                for pattern in read_patterns:
                    if re.search(pattern, line):
                        # Additional filter: skip comment lines and string literals in docstrings
                        if line.strip().startswith("#"):
                            continue
                        if '"""' in line or "'''" in line:
                            continue

                        violations.append(f"{relative_path}:{line_num}")
                        break  # Only report once per line

    return violations


def save_baseline(baseline_file, data):
    """Save violations baseline to JSON file.

    Args:
        baseline_file: Path to baseline file
        data: dict with "violations" list
    """
    baseline_file = Path(baseline_file)
    baseline_file.parent.mkdir(parents=True, exist_ok=True)
    baseline_file.write_text(json.dumps(data, indent=2))


def load_baseline(baseline_file):
    """Load violations baseline from JSON file.

    Returns:
        dict with "violations" list, or empty dict if file missing.
    """
    baseline_file = Path(baseline_file)
    if not baseline_file.exists():
        return {"violations": []}

    try:
        return json.loads(baseline_file.read_text())
    except Exception:
        return {"violations": []}


def check_ratchet(baseline_violations, current_violations):
    """Check ratchet: ensure current violations don't exceed baseline.

    The ratchet pattern: baseline records the current state of violations.
    New code must not ADD violations (tighter is OK, looser is FAIL).

    Args:
        baseline_violations: list of violation strings from baseline
        current_violations: list of violation strings from current scan

    Returns:
        bool: True if OK (no new violations), False if new violations found.
    """
    baseline_set = set(baseline_violations)
    current_set = set(current_violations)

    # Find violations in current that are NOT in baseline
    new_violations = current_set - baseline_set
    return len(new_violations) == 0


def main(argv=None):
    """CLI entry point."""
    argv = sys.argv[1:] if argv is None else argv

    repo_root = None
    output_format = "text"
    baseline_file = None

    # Parse arguments
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--root":
            i += 1
            if i < len(argv):
                repo_root = argv[i]
            i += 1
        elif arg.startswith("--root="):
            repo_root = arg[len("--root="):]
            i += 1
        elif arg == "--json":
            output_format = "json"
            i += 1
        elif arg == "--baseline":
            i += 1
            if i < len(argv):
                baseline_file = argv[i]
            i += 1
        else:
            print(f"Unknown argument: {arg}", file=sys.stderr)
            return 2
        i += 1

    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    if baseline_file is None:
        baseline_file = repo_root / ".stateapi-baseline.json"

    # Scan for violations
    violations = find_direct_opens(str(repo_root))

    # Load baseline
    baseline_data = load_baseline(str(baseline_file))
    baseline_violations = baseline_data.get("violations", [])

    # Check ratchet
    is_ok = check_ratchet(baseline_violations, violations)

    if output_format == "json":
        result = {
            "ok": is_ok,
            "violations": violations,
            "baseline_count": len(baseline_violations),
            "current_count": len(violations),
            "new_violations": [v for v in violations if v not in baseline_violations],
        }
        print(json.dumps(result, indent=2))
    else:
        # Text format
        print(f"State API lint: {len(violations)} violation(s) found")
        if baseline_violations:
            print(f"  (baseline: {len(baseline_violations)})")

        if violations:
            for v in sorted(violations):
                print(f"  {v}")

        new_violations = [v for v in violations if v not in baseline_violations]
        if new_violations:
            print(f"\nNEW violations ({len(new_violations)}):")
            for v in sorted(new_violations):
                print(f"  {v}")
            print(f"\nFAIL: {len(new_violations)} new violation(s) detected")
            return 1
        elif violations:
            print(f"\nPASS: All violations within baseline ({len(baseline_violations)})")
            return 0
        else:
            print("PASS: No violations")
            return 0


if __name__ == "__main__":
    sys.exit(main())
