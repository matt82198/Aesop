#!/usr/bin/env python3
"""
Portability gate: scan shipped surface for hardcoded personal/environment paths.

Detects absolute Windows user paths (C:\\Users\\<name> / C:/Users/<name>),
POSIX home paths (/home/<name>, /Users/<name>), and private-machine tokens
('conductor3', 'matt8'). Allows clearly-marked examples/defaults (lines containing
'example', 'default', or 'e.g.').

Exit 0 clean, 1 with numbered file:line findings.
Supports --json output and --root for base directory.
"""

import sys
import os
import json
import re
import glob
import argparse
from pathlib import Path


def read_package_json(root):
    """Read package.json and extract 'files' array."""
    pkg_path = os.path.join(root, 'package.json')
    try:
        with open(pkg_path, 'r') as f:
            content = json.load(f)
        return content.get('files', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def expand_globs(root, patterns):
    """Expand glob patterns from package.json 'files' array."""
    files = set()
    for pattern in patterns:
        # Normalize pattern to use forward slashes for glob
        pattern = pattern.replace('\\', '/')
        full_pattern = os.path.join(root, pattern).replace('\\', '/')

        matches = glob.glob(full_pattern, recursive=True)
        for match in matches:
            # Use Path to normalize, convert back to string
            normalized = str(Path(match))
            files.add(normalized)

    return sorted(files)


def is_text_file(filepath):
    """Check if file is likely text (not binary)."""
    binary_extensions = {
        '.bin', '.exe', '.dll', '.so', '.dylib',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp',
        '.pdf', '.zip', '.tar', '.gz', '.rar',
        '.woff', '.woff2', '.ttf', '.eot',
        '.mp3', '.mp4', '.wav', '.mov'
    }
    _, ext = os.path.splitext(filepath.lower())
    return ext not in binary_extensions


def read_file_lines(filepath):
    """Read file lines, handling encoding issues gracefully."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.readlines()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                return f.readlines()
        except Exception:
            return []
    except Exception:
        return []


def is_exception_line(line):
    """Check if line is marked as example/default."""
    line_lower = line.lower()
    return any(marker in line_lower for marker in ['example', 'default', 'e.g.'])


def scan_line_for_paths(line):
    """Scan a line for problematic paths and tokens."""
    findings = []

    # Windows absolute paths: C:\Users\<name> or C:/Users/<name>
    windows_user_patterns = [
        r'C:\\Users\\[a-zA-Z0-9_\-\.]+',
        r'C:/Users/[a-zA-Z0-9_\-\.]+'
    ]
    for pattern in windows_user_patterns:
        matches = re.finditer(pattern, line)
        for match in matches:
            findings.append({
                'type': 'windows_user_path',
                'path': match.group(0)
            })

    # POSIX home paths: /home/<name> or /Users/<name>
    posix_patterns = [
        r'/home/[a-zA-Z0-9_\-\.]+',
        r'/Users/[a-zA-Z0-9_\-\.]+'
    ]
    for pattern in posix_patterns:
        matches = re.finditer(pattern, line)
        for match in matches:
            findings.append({
                'type': 'posix_home_path',
                'path': match.group(0)
            })

    # Private machine tokens: 'conductor3' and 'matt8'
    # These are simple word boundary matches (whole word)
    for token in ['conductor3', 'matt8']:
        # Use word boundaries to avoid false positives in longer identifiers
        pattern = r'\b' + re.escape(token) + r'\b'
        matches = re.finditer(pattern, line)
        for match in matches:
            findings.append({
                'type': 'private_token',
                'token': token
            })

    return findings


def scan_shipped_surface(root, json_output=False):
    """Scan shipped surface for portability issues."""
    patterns = read_package_json(root)
    if not patterns:
        print("Warning: Could not read package.json 'files' array", file=sys.stderr)
        return []

    files = expand_globs(root, patterns)
    all_findings = []

    for filepath in files:
        if not os.path.isfile(filepath) or not is_text_file(filepath):
            continue

        lines = read_file_lines(filepath)
        for line_num, line in enumerate(lines, 1):
            # Skip exception lines (marked as example/default)
            if is_exception_line(line):
                continue

            # Scan for issues
            issues = scan_line_for_paths(line)
            for issue in issues:
                relative_path = os.path.relpath(filepath, root)
                finding = {
                    'file': relative_path,
                    'line': line_num,
                    'content': line.rstrip()[:100],  # First 100 chars
                    **issue
                }
                all_findings.append(finding)

    return all_findings


def main():
    parser = argparse.ArgumentParser(
        description='Portability gate: scan for hardcoded personal paths'
    )
    parser.add_argument(
        '--root',
        default='.',
        help='Root directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output findings as JSON'
    )

    args = parser.parse_args()
    root = os.path.abspath(args.root)

    findings = scan_shipped_surface(root, json_output=args.json)

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        if findings:
            print(f"Found {len(findings)} portability issue(s):", file=sys.stderr)
            for i, finding in enumerate(findings, 1):
                print(
                    f"{i}. {finding['file']}:{finding['line']}: "
                    f"{finding.get('type', 'unknown')}",
                    file=sys.stderr
                )
                if finding.get('path'):
                    print(f"   Path: {finding['path']}", file=sys.stderr)
                if finding.get('token'):
                    print(f"   Token: {finding['token']}", file=sys.stderr)
                print(f"   {finding['content']}", file=sys.stderr)

    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
