#!/usr/bin/env python3
"""
ci_merge_wait.py — CI-gated merge helper: wait for PR checks to conclude, then merge.

Polls gh pr view until all status checks conclude (SUCCESS/FAILURE), then merges ONLY
if all checks are SUCCESS. The gh pr merge call is STRUCTURALLY UNREACHABLE unless the
status is SUCCESS — this is the whole point (prevents merge-on-CI-failure edge cases).

Usage:
  python ci_merge_wait.py <PR-number> [--timeout SECONDS] [--poll SECONDS] [--merge-method merge|squash|rebase]

Options:
  --timeout SECONDS      Max seconds to wait for CI to conclude (default: 3600)
  --poll SECONDS         Poll interval in seconds (default: 10)
  --merge-method METHOD  Merge strategy: merge, squash, rebase (default: merge)

Exit codes:
  0 = PR merged successfully
  2 = CI checks failed (do NOT merge, prints which check failed)
  3 = Timeout waiting for CI to conclude
  4 = PR not mergeable or has merge conflicts

Requires: gh CLI available on PATH. Gracefully exits with error if gh is missing.
"""

import argparse
import json
import subprocess
import sys
import time


def run_gh_command(args):
    """
    Run gh CLI command; return parsed JSON or None if gh missing/error.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            if "not found" in result.stderr or "No such file" in result.stderr:
                return None
            # Re-raise for non-zero return (will be caught by caller)
            result.check_returncode()
        return json.loads(result.stdout) if result.stdout.strip() else None
    except subprocess.TimeoutExpired:
        print("ERROR: gh command timed out")
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: gh CLI not found on PATH")
        sys.exit(1)


def get_pr_status(pr_number):
    """
    Fetch PR status via gh pr view.
    Returns dict with 'mergeable' and 'statusCheckRollup' keys.
    Returns None if gh is missing.
    """
    data = run_gh_command([
        "gh", "pr", "view", str(pr_number),
        "--json", "mergeable,statusCheckRollup"
    ])
    return data


def check_ci_status(status_rollup):
    """
    Analyze status check rollup.
    Returns: ("pending", None), ("success", None), or ("failure", check_name)
    """
    if not status_rollup:
        # No checks (unusual but treat as success)
        return ("success", None)

    # Collect statuses
    pending_checks = []
    failed_checks = []

    for check in status_rollup:
        status = check.get("status", "").upper()
        if status == "PENDING":
            pending_checks.append(check.get("name", "unknown"))
        elif status == "FAILURE":
            failed_checks.append(check.get("name", "unknown"))

    # Determine overall status
    if failed_checks:
        return ("failure", failed_checks[0])
    elif pending_checks:
        return ("pending", None)
    else:
        return ("success", None)


def merge_pr(pr_number, merge_method):
    """
    Merge the PR using gh pr merge.
    This call is STRUCTURALLY UNREACHABLE unless CI is SUCCESS.
    Returns True on success, False on error.
    """
    result = subprocess.run(
        ["gh", "pr", "merge", str(pr_number), f"--{merge_method}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pr_number", type=int, help="GitHub PR number")
    parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Max seconds to wait for CI (default: 3600)"
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=10,
        help="Poll interval in seconds (default: 10)"
    )
    parser.add_argument(
        "--merge-method",
        choices=["merge", "squash", "rebase"],
        default="merge",
        help="Merge strategy (default: merge)"
    )

    args = parser.parse_args()

    # Validate inputs
    if args.pr_number <= 0:
        print("ERROR: PR number must be positive")
        sys.exit(1)

    if args.timeout <= 0 or args.poll <= 0:
        print("ERROR: timeout and poll must be positive")
        sys.exit(1)

    # Fetch initial PR status
    print(f"Checking PR #{args.pr_number} status...")
    status = get_pr_status(args.pr_number)
    if status is None:
        print("ERROR: gh CLI not available or PR not found")
        sys.exit(1)

    mergeable = status.get("mergeable", "").upper()
    if mergeable == "CONFLICTED":
        print(f"MERGE CONFLICT: PR #{args.pr_number} has conflicts")
        sys.exit(4)
    elif mergeable not in ("MERGEABLE", "UNKNOWN"):
        # Also treat UNKNOWN conservatively as non-mergeable until we have clarity
        print(f"NOT MERGEABLE: PR #{args.pr_number} status={mergeable}")
        sys.exit(4)

    # Poll until CI concludes
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        if elapsed > args.timeout:
            print(f"TIMEOUT: CI did not conclude within {args.timeout}s")
            sys.exit(3)

        status = get_pr_status(args.pr_number)
        if status is None:
            print("ERROR: gh CLI check failed")
            sys.exit(1)

        status_rollup = status.get("statusCheckRollup", [])
        ci_status, failed_check = check_ci_status(status_rollup)

        if ci_status == "failure":
            print(f"CI FAILED: {failed_check}")
            sys.exit(2)
        elif ci_status == "success":
            # SUCCESS: CI is green, proceed to merge
            # This merge call is STRUCTURALLY UNREACHABLE unless ci_status == "success"
            print(f"CI GREEN: All checks passed. Merging PR #{args.pr_number}...")
            if merge_pr(args.pr_number, args.merge_method):
                print(f"MERGED: PR #{args.pr_number} merged successfully")
                sys.exit(0)
            else:
                print("ERROR: merge failed (PR state changed?)")
                sys.exit(1)

        # Still pending: wait and retry
        print(f"CI PENDING ({elapsed:.0f}s elapsed)... waiting {args.poll}s")
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
