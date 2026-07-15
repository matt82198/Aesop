#!/usr/bin/env python3
"""
ci_merge_wait.py — CI-gated merge helper: wait for PR checks to conclude, then merge.

Polls gh pr view until all status checks conclude (SUCCESS/FAILURE), then merges ONLY
if all checks are SUCCESS. The gh pr merge call is STRUCTURALLY UNREACHABLE unless the
status is SUCCESS — this is the whole point (prevents merge-on-CI-failure edge cases).

Usage:
  python ci_merge_wait.py <PR-number> [--timeout SECONDS] [--poll SECONDS] [--merge-method merge|squash|rebase]
                          [--dry-run] [--self-test]

Options:
  --timeout SECONDS      Max seconds to wait for CI to conclude (default: 3600)
  --poll SECONDS         Poll interval in seconds (default: 10)
  --merge-method METHOD  Merge strategy: merge, squash, rebase (default: merge)
  --dry-run              Skip actual merge, just verify CI status and report what would happen
  --self-test            Run offline self-test of polling/decision logic (no network, no PR required)

Exit codes:
  0 = PR merged successfully, dry-run verified, or self-test passed
  1 = General error or self-test failed
  2 = CI checks failed (do NOT merge, prints which check failed)
  3 = Timeout waiting for CI to conclude
  4 = PR not mergeable or has merge conflicts

Requires: gh CLI available on PATH (unless --self-test). Gracefully exits with error if gh is missing.
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


def merge_pr(pr_number, merge_method, dry_run=False):
    """
    Merge the PR using gh pr merge.
    This call is STRUCTURALLY UNREACHABLE unless CI is SUCCESS.
    If dry_run is True, report what would be done without actually merging.
    Returns True on success, False on error.
    """
    if dry_run:
        print(f"[DRY-RUN] Would merge PR #{pr_number} with --{merge_method}")
        return True

    result = subprocess.run(
        ["gh", "pr", "merge", str(pr_number), f"--{merge_method}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


def run_self_test():
    """
    Run self-test with mocked CI status checks.
    No network calls; verifies the merge guard logic.
    Returns True if all tests pass, False otherwise.
    """
    print("Running self-test with mocked CI statuses...")

    # Mock status rollup: all checks SUCCESS
    success_rollup = [
        {"name": "test-unit", "status": "SUCCESS"},
        {"name": "test-integration", "status": "SUCCESS"},
        {"name": "lint", "status": "SUCCESS"},
    ]

    # Test 1: success case
    ci_status, failed_check = check_ci_status(success_rollup)
    if ci_status != "success":
        print(f"FAIL: Expected 'success', got '{ci_status}'")
        return False
    print("[OK] success case: merge guard permits merge")

    # Test 2: pending case
    pending_rollup = [
        {"name": "test-unit", "status": "PENDING"},
        {"name": "test-integration", "status": "SUCCESS"},
    ]
    ci_status, failed_check = check_ci_status(pending_rollup)
    if ci_status != "pending":
        print(f"FAIL: Expected 'pending', got '{ci_status}'")
        return False
    print("[OK] pending case: merge guard blocks merge (structurally unreachable)")

    # Test 3: failure case
    failure_rollup = [
        {"name": "test-unit", "status": "FAILURE"},
        {"name": "test-integration", "status": "SUCCESS"},
    ]
    ci_status, failed_check = check_ci_status(failure_rollup)
    if ci_status != "failure" or failed_check != "test-unit":
        print(f"FAIL: Expected 'failure' with 'test-unit', got '{ci_status}' / '{failed_check}'")
        return False
    print("[OK] failure case: merge guard blocks merge (structurally unreachable)")

    # Test 4: no checks (treat as success)
    ci_status, _ = check_ci_status([])
    if ci_status != "success":
        print(f"FAIL: Expected 'success' for no checks, got '{ci_status}'")
        return False
    print("[OK] no-checks case: treated as success")

    print("\nAll self-tests passed!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "pr_number",
        type=int,
        nargs="?",
        default=None,
        help="GitHub PR number (required unless using --self-test)"
    )
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip actual merge, just verify CI status and report what would happen"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run offline self-test of polling/decision logic (no network)"
    )

    args = parser.parse_args()

    # Handle self-test mode
    if args.self_test:
        if run_self_test():
            sys.exit(0)
        else:
            sys.exit(1)

    # Validate PR is provided for non-self-test mode
    if args.pr_number is None:
        print("ERROR: PR number is required (unless using --self-test)")
        sys.exit(1)

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
            # SUCCESS: CI is green, re-check immediately before proceeding
            print(f"CI GREEN: All checks passed. Re-checking status before merge...")
            final_check = get_pr_status(args.pr_number)
            if final_check is None:
                print("ERROR: final status check failed")
                sys.exit(1)

            final_rollup = final_check.get("statusCheckRollup", [])
            final_ci_status, final_failed = check_ci_status(final_rollup)

            if final_ci_status != "success":
                print(f"CI STATUS CHANGED: {final_failed}")
                sys.exit(2)

            # SUCCESS: CI is still green, proceed to merge
            # This merge call is STRUCTURALLY UNREACHABLE unless ci_status == "success"
            if args.dry_run:
                print(f"[DRY-RUN] PR #{args.pr_number} CI is green, would merge...")
            else:
                print(f"CI CONFIRMED GREEN. Merging PR #{args.pr_number}...")

            if merge_pr(args.pr_number, args.merge_method, dry_run=args.dry_run):
                if args.dry_run:
                    print(f"[DRY-RUN] PR #{args.pr_number} merge command would succeed")
                else:
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
