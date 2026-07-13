#!/usr/bin/env python3
"""
eod_sweep.py — End-of-day safety check for repository health.

Verifies git repositories are safe (no data loss risk):
- Working tree clean/dirty
- Branch pushed (ahead-count 0)
- Untracked files not in .gitignore

Output contract:
  Line 1: EOD-SWEEP: SAFE or EOD-SWEEP: AT-RISK — <n> findings
  Lines 2+: One finding per line (if any)
  Exit code 0 only when SAFE.

Usage: eod_sweep.py [--repos PATHS] [--readonly-repos PATHS] [--fix-push]

  --repos: Colon-separated paths to scan (default: empty; use env var or flag to specify)
  --readonly-repos: Colon-separated paths that should NOT be auto-pushed
  --fix-push: Auto-push unpushed commits in repos where safe
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import time


class Finding:
    """A single finding with repo + message."""
    def __init__(self, repo, msg):
        self.repo = repo
        self.msg = msg

    def __str__(self):
        return f"{self.repo.name}: {self.msg}"


def get_git_status(repo_path):
    """Return (is_clean, dirty_files_list) for a repo."""
    try:
        output = subprocess.run(
            ['git', '-C', str(repo_path), 'status', '--porcelain'],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        if not output:
            return (True, [])
        else:
            dirty = [line for line in output.split('\n') if line]
            return (False, dirty)
    except Exception as e:
        return (None, str(e))


def get_ahead_count(repo_path):
    """Return count of commits ahead of origin/HEAD (or None on error)."""
    try:
        # First check if there's a tracking branch
        try:
            output = subprocess.run(
                ['git', '-C', str(repo_path), 'rev-list', '--left-only', '--count', 'HEAD...@{u}'],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except:
            # Fallback to origin/HEAD if no upstream
            output = subprocess.run(
                ['git', '-C', str(repo_path), 'rev-list', '--left-only', '--count', 'HEAD...origin/HEAD'],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()

        try:
            return int(output) if output else 0
        except:
            return None
    except Exception:
        return None


def check_untracked_files(repo_path):
    """Return list of untracked files not in .gitignore."""
    try:
        output = subprocess.run(
            ['git', '-C', str(repo_path), 'ls-files', '--others', '--exclude-standard'],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        if output:
            return output.split('\n')
        return []
    except Exception:
        return None


def check_repo(repo_path):
    """Check a single repo; return list of Finding objects or None if repo doesn't exist."""
    if not repo_path.exists():
        return None

    if not (repo_path / '.git').exists():
        return None

    findings = []

    # Check 1: Working tree clean
    is_clean, dirty = get_git_status(repo_path)
    if is_clean is None:
        findings.append(Finding(repo_path, f"git status check failed: {dirty}"))
    elif not is_clean:
        findings.append(Finding(repo_path, f"dirty working tree: {len(dirty)} files"))

    # Check 2: Branch pushed
    ahead = get_ahead_count(repo_path)
    if ahead is None:
        findings.append(Finding(repo_path, "ahead-count check failed"))
    elif ahead > 0:
        findings.append(Finding(repo_path, f"ahead of origin: {ahead} commits unpushed"))

    # Check 3: Untracked files
    untracked = check_untracked_files(repo_path)
    if untracked is None:
        findings.append(Finding(repo_path, "untracked file check failed"))
    elif untracked:
        findings.append(Finding(repo_path, f"untracked files: {len(untracked)} items"))

    return findings


def push_repo(repo_path):
    """Push commits for a repo (return True if successful)."""
    try:
        result = subprocess.run(
            ['git', '-C', str(repo_path), 'push'],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def run_secret_scan(repo_path):
    """Run secret_scan.py on staged files (return True if no secrets found)."""
    try:
        script_path = Path(__file__).parent / 'secret_scan.py'
        result = subprocess.run(
            [sys.executable, str(script_path), '--staged'],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--repos',
        default='',
        help='Colon-separated paths to scan (default: empty)'
    )
    parser.add_argument(
        '--readonly-repos',
        default='',
        help='Colon-separated paths that should NOT be auto-pushed'
    )
    parser.add_argument(
        '--fix-push',
        action='store_true',
        help='Auto-push unpushed commits'
    )
    args = parser.parse_args()

    # Parse repos
    repos_to_check = []
    if args.repos:
        repos_to_check = [Path(p) for p in args.repos.split(':') if p]

    # Parse readonly repos
    readonly_repos = set()
    if args.readonly_repos:
        readonly_repos = {Path(p) for p in args.readonly_repos.split(':') if p}

    findings = []

    # Scan all repos
    for repo_path in repos_to_check:
        repo_findings = check_repo(repo_path)
        if repo_findings is not None:
            findings.extend(repo_findings)

    # Determine verdict
    if not findings:
        verdict = "SAFE"
        verdict_line = "EOD-SWEEP: SAFE"
        exit_code = 0
    else:
        verdict = f"AT-RISK — {len(findings)} findings"
        verdict_line = f"EOD-SWEEP: AT-RISK — {len(findings)} findings"
        exit_code = 1

    # Handle --fix-push if requested and conditions are met
    if args.fix_push and findings:
        # Filter for ahead-only findings that we can push
        ahead_findings = [f for f in findings if 'unpushed' in f.msg and f.repo not in readonly_repos]
        if ahead_findings:
            for finding in ahead_findings:
                repo_path = finding.repo
                if repo_path and repo_path not in readonly_repos:
                    # Run secret scan first
                    if run_secret_scan(repo_path):
                        if push_repo(repo_path):
                            print(f"Pushed: {repo_path.name}")
                            findings.remove(finding)
                        else:
                            print(f"Push failed: {repo_path.name}")
                    else:
                        print(f"Secret scan blocked: {repo_path.name}")

            # Re-evaluate verdict
            if not findings:
                verdict = "SAFE"
                verdict_line = "EOD-SWEEP: SAFE"
                exit_code = 0
            else:
                verdict_line = f"EOD-SWEEP: AT-RISK — {len(findings)} findings"

    # Print output
    print(verdict_line)
    for finding in findings:
        print(f"  {finding}")

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
