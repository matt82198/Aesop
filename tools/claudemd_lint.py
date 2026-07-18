#!/usr/bin/env python3
"""CLAUDE.md linter — dogfoods the scope-min invariant.

For each */CLAUDE.md in a repo:
1. DOC-POINTER check — every referenced path ending .md/.py/.sh/.mjs that looks like a
   REPO file (relative, not a runtime artifact) must exist. Distinguishes real repo-doc
   pointers from legitimate references to runtime artifacts (state/**, *heartbeat*,
   BRIEF.md, PROPOSALS.md, BUILDLOG.md, MEMORY.md, STATE.md, OUTCOMES-LEDGER.md, tracker.json).
2. TEST-CMD check — any `npm run <script>` cited must exist in package.json scripts.
   Flags `pytest` if the repo uses unittest (grep package.json test:py).
3. Optional — flags files over --max-lines (default 150).

Exit: 0=clean, 1=findings. Supports --json flag.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Runtime artifact allowlist — these are correctly absent from the tree
RUNTIME_ARTIFACTS = {
    # State/control files
    "state",  # state/ directory
    "BRIEF.md",
    "PROPOSALS.md",
    "BUILDLOG.md",
    "MEMORY.md",
    "STATE.md",
    "OUTCOMES-LEDGER.md",
    "tracker.json",
    "ACTIONS.log",
    ".monitor-heartbeat",
    ".signal-state.json",
    ".HALT",
    ".git",
    "node_modules",
}

# Patterns that indicate a runtime artifact
RUNTIME_PATTERNS = [
    r"^\.\.?/state/",  # state/ directory
    r"heartbeat",  # *heartbeat*, .monitor-heartbeat, etc.
    r"^BRIEF\.md$",
    r"^PROPOSALS\.md$",
    r"^BUILDLOG\.md$",
    r"^MEMORY\.md$",
    r"^STATE\.md$",
    r"^OUTCOMES-LEDGER\.md$",
    r"^tracker\.json$",
    r"^ACTIONS\.log$",
    r"^\./state/",
    r"^state/",
]


def is_runtime_artifact(ref: str) -> bool:
    """Check if a reference is a legitimate runtime artifact."""
    for pattern in RUNTIME_PATTERNS:
        if re.search(pattern, ref, re.IGNORECASE):
            return True
    return False


def extract_path_references(text: str) -> List[str]:
    """Extract all references to paths ending in .md/.py/.sh/.mjs.

    Filters out:
    - Example paths starting with /path/to/
    - Environment variable references (VAR_NAME/...)
    - Absolute paths starting with /
    - Home directory references (~/.../...)
    - Non-relative paths
    - Glob patterns (*.something)
    - File type descriptions like ".py/.mjs"
    - Hidden directory references like .claude/ (not repo structure)
    """
    # Match paths: relative or starting with ./, alphanumeric, /, -, _
    # Also match inline code references like `path/file.md`
    # Note: intentionally NOT matching patterns like "*.test.mjs" (glob)
    pattern = r"(?:[`'\"])?([a-zA-Z0-9_.][a-zA-Z0-9_./\-]*\.(?:md|py|sh|mjs))(?:[`'\"])?"
    matches = re.finditer(pattern, text)
    refs = set()
    for match in matches:
        ref = match.group(1)

        # Filter out false positives
        if len(ref) <= 2:
            continue

        # Skip glob patterns (starting with *)
        if ref.startswith("*"):
            continue

        # Skip absolute paths
        if ref.startswith("/"):
            continue

        # Skip home directory references (~/...)
        if "~/" in ref:
            continue

        # Skip hidden directories that don't look like repo structure (./.something/...)
        # These are typically home dir refs like .claude/, .config/, etc.
        if ref.startswith(".") and "/" in ref:
            # Allow only ./ for current dir refs
            if not ref.startswith("./"):
                continue

        # Skip example paths
        if "/path/to/" in ref or ref.startswith("path/to/"):
            continue

        # Skip env var references (ALLCAPS_NAME/...)
        if re.match(r"^[A-Z_]+/", ref):
            continue

        # Skip file type descriptions like ".py/.mjs" (multiple dots in non-path context)
        if ref.count(".") > 2:
            continue

        # Skip references that don't have / (not a path)
        if "/" not in ref:
            continue

        refs.add(ref)

    return sorted(refs)


def extract_npm_scripts(text: str) -> List[str]:
    """Extract all `npm run <script>` references."""
    pattern = r"npm\s+run\s+([a-zA-Z0-9:_\-]+)"
    matches = re.finditer(pattern, text)
    scripts = set()
    for match in matches:
        scripts.add(match.group(1))
    return sorted(scripts)


def get_package_scripts(repo_root: Path) -> Dict[str, str]:
    """Load scripts from package.json."""
    pkg_path = repo_root / "package.json"
    if not pkg_path.exists():
        return {}
    try:
        with open(pkg_path) as f:
            pkg = json.load(f)
        return pkg.get("scripts", {})
    except (json.JSONDecodeError, IOError):
        return {}


def check_test_cmd_match(repo_root: Path) -> Tuple[bool, str]:
    """Check if repo uses unittest (test:py in package.json uses 'unittest').

    Returns: (is_using_unittest, test_cmd_value)
    """
    scripts = get_package_scripts(repo_root)
    test_py = scripts.get("test:py", "")
    is_unittest = "unittest" in test_py
    return is_unittest, test_py


def lint_claudemd(
    claudemd_path: Path,
    repo_root: Path,
    max_lines: int = 150,
) -> List[Dict[str, str]]:
    """Lint a single CLAUDE.md file.

    Returns list of findings, each a dict with 'type', 'line', 'message'.
    """
    findings = []

    try:
        content = claudemd_path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError) as e:
        return [{
            "type": "file-read-error",
            "line": "0",
            "message": f"Failed to read {claudemd_path.relative_to(repo_root)}: {e}",
        }]

    lines = content.split("\n")

    # Check line count
    if len(lines) > max_lines:
        findings.append({
            "type": "line-count",
            "line": str(len(lines)),
            "message": f"{claudemd_path.relative_to(repo_root)}: "
                       f"{len(lines)} lines exceeds max {max_lines}",
        })

    # Check if content mentions pytest but repo uses unittest
    is_unittest, _ = check_test_cmd_match(repo_root)
    if is_unittest and "pytest" in content.lower():
        findings.append({
            "type": "pytest-vs-unittest",
            "line": "?",
            "message": f"{claudemd_path.relative_to(repo_root)}: "
                       f"mentions 'pytest' but repo uses unittest (test:py)",
        })

    # DOC-POINTER check: find file references
    path_refs = extract_path_references(content)

    for ref in path_refs:
        # Skip runtime artifacts
        if is_runtime_artifact(ref):
            continue

        # Check if path exists (relative to repo root)
        target = repo_root / ref
        if not target.exists():
            findings.append({
                "type": "phantom-path",
                "line": "?",
                "message": f"{claudemd_path.relative_to(repo_root)}: "
                           f"references non-existent '{ref}'",
            })

    # TEST-CMD check: npm run scripts
    npm_scripts = extract_npm_scripts(content)
    available_scripts = get_package_scripts(repo_root)

    for script in npm_scripts:
        if script not in available_scripts:
            findings.append({
                "type": "missing-npm-script",
                "line": "?",
                "message": f"{claudemd_path.relative_to(repo_root)}: "
                           f"npm run '{script}' not in package.json scripts",
            })

    return findings


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Lint CLAUDE.md files for integrity"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd)",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=150,
        help="Maximum lines per CLAUDE.md (default: 150)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()
    repo_root = args.root.resolve()

    if not repo_root.exists():
        print(f"Error: repo root {repo_root} does not exist", file=sys.stderr)
        sys.exit(1)

    # Find all CLAUDE.md files
    claudemd_files = sorted(repo_root.glob("*/CLAUDE.md"))
    claudemd_files.extend(repo_root.glob("CLAUDE.md"))
    claudemd_files = sorted(set(claudemd_files))

    all_findings = []
    for claudemd_path in claudemd_files:
        findings = lint_claudemd(claudemd_path, repo_root, args.max_lines)
        all_findings.extend(findings)

    if args.json:
        output = {
            "findings": all_findings,
            "count": len(all_findings),
            "repo_root": str(repo_root),
        }
        print(json.dumps(output, indent=2))
    else:
        if all_findings:
            for i, finding in enumerate(all_findings, 1):
                print(
                    f"{i}. [{finding['type']}] {finding['message']} "
                    f"(line {finding['line']})"
                )
        else:
            print("✓ No issues found")

    sys.exit(1 if all_findings else 0)


if __name__ == "__main__":
    main()
