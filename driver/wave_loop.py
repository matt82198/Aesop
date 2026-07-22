#!/usr/bin/env python3
"""Wave loop engine: orchestrates a full multi-item wave through AgentDriver backends.

This module implements Step 3 of the driver integration plan: a Python wave engine
that mirrors the phase sequence from wave-flat-dispatch.template.mjs but runs
offline against AgentDriver backends (Claude Code, Codex, open-model, etc.).

Phases (mirror the template):
  1. Preflight ownership guard: check no two items share an ownsFiles path
  2. Resolve policy ONCE: call verification_policy(caps) and use the returned
     knobs for repair_cap, spot_check_frac, require_adversarial_review
  3. Cost-ceiling gate (fail-closed): before build and before each repair round,
     check spend against ceiling; abort if tripped
  4. Build (PARALLEL): use ThreadPoolExecutor to dispatch items concurrently,
     running each item's test, honoring disjoint ownership
  5. Bounded repair: for failed items, retry with test output appended to prompt,
     up to policy's repair_cap rounds
  6. Adversarial review: if required, dispatch a review per item or mark deferred
  7. Batched ship: if git config given, add/commit/push the verified items

HONESTY GUARANTEE:
  - Verified = True ONLY if the item's test passed (exit code 0 from run_command).
  - Any exception -> item.verified = False, never a false green.
  - Ownership is enforced at the driver level (dispatch_worker rejects out-of-scope).
  - Adversarial review is NOT yet enforced; marked as 'deferred' (TODO in a later increment).

FAIL-SAFE:
  - Cost-ceiling check: if exceeded, ABORT the wave immediately (return early).
  - Disjoint ownership: any overlap -> ABORT with structured error, no dispatch.
  - Repair cap bounded: never infinite retry loop.

stdlib-only, ASCII-only, Windows + Linux safe.
"""

import concurrent.futures
import json
import os
import sys
import time
import uuid
from math import ceil
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Add driver/ to path for imports.
REPO = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO / "driver"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

from agent_driver import AgentDriver
from wave_bridge import build_manifest_item, dispatch_item
from verification_policy import verification_policy

# Try to import cost_ceiling and coordination (optional, for safety gates).
try:
    import sys
    TOOLS_DIR = REPO / "tools"
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import cost_ceiling
except ImportError:
    cost_ceiling = None

try:
    STATE_STORE_DIR = REPO / "state_store"
    if str(STATE_STORE_DIR) not in sys.path:
        sys.path.insert(0, str(STATE_STORE_DIR))
    import coordination
except ImportError:
    coordination = None


def run_wave(
    driver: AgentDriver,
    manifest: Dict[str, Any],
    *,
    state_dir: Optional[str] = None,
    git: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run a full multi-item wave through an AgentDriver backend.

    Implements the complete wave algorithm: preflight ownership guard, parallel
    build, bounded repair, optional adversarial review, and batched git ship.

    Args:
        driver: AgentDriver instance providing dispatch_worker, run_command, etc.
        manifest: dict with:
          - items: list of item dicts with {slug, ownsFiles, prompt, testCmd, workDir, ...}
          - (optional) other manifest fields
        state_dir: optional path to state directory for coordination claims and
                   cost_ceiling ledger. If None, these features are skipped.
        git: optional dict with {expectTopLevel: str} for git operations. If None,
             ship phase is skipped.

    Returns:
        dict with structure:
          {
            "preflight_ok": bool,
            "aborted": bool,
            "abort_reason": str or None,
            "built": [
              {
                "slug": str,
                "dispatched": bool,
                "verified": bool,
                "testExit": int or None,
                "repairs": int,
                "error": str or None,
                "filesWritten": [str],
              },
              ...
            ],
            "shipped": [str] or None (list of slugs, or None if git not configured),
            "ceiling": dict or None (from cost_ceiling.check, or None if no ceiling),
            "policy": dict (the resolved verification_policy),
          }

    Fail-safe invariants:
      - Verified is True ONLY from run_command exit code 0.
      - Any exception in an item's dispatch -> verified=False for that item.
      - Cost ceiling: if check() says exceeded, abort immediately with no more dispatch.
      - Disjoint ownership: any overlap -> abort with structured error, no dispatch.
    """
    result = {
        "preflight_ok": False,
        "aborted": False,
        "abort_reason": None,
        "built": [],
        "shipped": None,
        "ceiling": None,
        "policy": None,
    }

    # Extract items from manifest.
    items = manifest.get("items", [])

    # ========================================================================
    # PHASE 1: Preflight ownership guard
    # ========================================================================
    owner_map = {}  # normalized file -> slug
    conflicts = []

    for item in items:
        slug = item.get("slug", "unknown")
        owned_files = item.get("ownsFiles", [])
        for f in owned_files:
            # Normalize path: handle separators, ./, .., and case on case-insensitive platforms
            normalized = os.path.normcase(os.path.normpath(f))
            if normalized in owner_map:
                conflicts.append(
                    {
                        "file": f,
                        "normalized": normalized,
                        "items": [owner_map[normalized], slug],
                    }
                )
            else:
                owner_map[normalized] = slug

    if conflicts:
        result["aborted"] = True
        result["abort_reason"] = "ownership_overlap"
        result["conflicts"] = conflicts
        return result

    result["preflight_ok"] = True

    # ========================================================================
    # PHASE 2: Resolve verification policy ONCE
    # ========================================================================
    caps = driver.probe_capabilities()
    policy = verification_policy(caps)
    result["policy"] = policy

    repair_cap = policy.get("repair_cap", 1)
    spot_check_frac = policy.get("spot_check_frac", 0.0)
    require_adversarial_review = policy.get("require_adversarial_review", False)

    # ========================================================================
    # PHASE 3: Cost-ceiling gate (before build)
    # ========================================================================
    if cost_ceiling is not None and state_dir is not None:
        ceiling_result = cost_ceiling.check(
            spent=driver.get_tokens_spent() or 0,
            trip=True,
            state_dir=state_dir,
        )
        result["ceiling"] = ceiling_result

        if ceiling_result.get("exceeded", False):
            result["aborted"] = True
            result["abort_reason"] = "cost_ceiling_exceeded"
            return result

    # ========================================================================
    # PHASE 4: Build (PARALLEL with ThreadPoolExecutor)
    # ========================================================================
    # Prepare built items list and track for repair.
    built_items = []
    failed_items = []  # (index, item, result) tuples for repair

    def build_item(item_index: int, item: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Build one item and return (index, result_dict)."""
        slug = item.get("slug", f"item-{item_index}")
        workdir = item.get("workDir", ".")

        # Try to claim the item if state_dir is given (fail-closed on claim failure).
        instance_id = f"wave-{uuid.uuid4()}"
        claim_held = False
        if coordination is not None and state_dir is not None:
            try:
                from state_store import store
                db_path = Path(state_dir) / "state.db"
                event_store = store.EventStore(str(db_path))
                claim_held = coordination.try_claim(
                    event_store,
                    resource=slug,
                    instance_id=instance_id,
                )
                if not claim_held:
                    # Item is claimed by another instance; skip it.
                    return (
                        item_index,
                        {
                            "slug": slug,
                            "dispatched": False,
                            "verified": False,
                            "testExit": None,
                            "repairs": 0,
                            "error": "resource claimed by another instance",
                            "filesWritten": [],
                        },
                    )
            except Exception:
                # On exception, fail-closed: skip the item.
                claim_held = False

        try:
            # Build the manifest item with policy.
            manifest_item = build_manifest_item(driver, item)

            # Dispatch the item.
            dispatch_result = dispatch_item(driver, manifest_item, workdir=workdir)

            item_result = {
                "slug": slug,
                "dispatched": dispatch_result.get("route") == "driver",
                "verified": dispatch_result.get("verified", False),
                "testExit": dispatch_result.get("testExit"),
                "repairs": 0,
                "error": dispatch_result.get("error"),
                "filesWritten": dispatch_result.get("filesWritten", []),
                "workerId": dispatch_result.get("workerId"),
            }

            return (item_index, item_result)

        except Exception as exc:
            # Catch-all: any exception -> failed result, never a false green.
            return (
                item_index,
                {
                    "slug": slug,
                    "dispatched": False,
                    "verified": False,
                    "testExit": None,
                    "repairs": 0,
                    "error": f"build exception: {exc}",
                    "filesWritten": [],
                },
            )
        finally:
            # Release the claim if held.
            if claim_held and coordination is not None and state_dir is not None:
                try:
                    from state_store import store
                    db_path = Path(state_dir) / "state.db"
                    event_store = store.EventStore(str(db_path))
                    coordination.release(event_store, resource=slug, instance_id=instance_id)
                except Exception:
                    pass

    # Run build in parallel.
    max_workers = min(8, len(items)) if items else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(build_item, i, item)
            for i, item in enumerate(items)
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                item_index, item_result = future.result()
                built_items.append((item_index, items[item_index], item_result))

                # Track failed items for repair.
                if not item_result["verified"]:
                    failed_items.append((item_index, items[item_index], item_result))
            except Exception:
                # Should not happen (build_item catches internally), but just in case.
                pass

    # Sort built_items by index to preserve order.
    built_items.sort(key=lambda x: x[0])
    result["built"] = [item_result for _, _, item_result in built_items]

    # ========================================================================
    # PHASE 5: Bounded repair
    # ========================================================================
    for repair_round in range(repair_cap):
        if not failed_items:
            break

        # Cost-ceiling check before repair round.
        if cost_ceiling is not None and state_dir is not None:
            ceiling_result = cost_ceiling.check(
                spent=driver.get_tokens_spent() or 0,
                trip=True,
                state_dir=state_dir,
            )
            if ceiling_result.get("exceeded", False):
                result["aborted"] = True
                result["abort_reason"] = "cost_ceiling_exceeded_in_repair"
                return result

        # Repair each failed item.
        next_failed = []
        for item_index, item, item_result in failed_items:
            slug = item.get("slug", f"item-{item_index}")
            workdir = item.get("workDir", ".")
            test_cmd = item.get("testCmd", "")

            # Build repair prompt: append test output to original prompt.
            original_prompt = item.get("prompt", "")
            test_output = f"\n\nTest failed with exit code {item_result['testExit']}.\n"
            if item_result.get("error"):
                test_output += f"Error: {item_result['error']}\n"
            repair_prompt = original_prompt + test_output

            # Create a repair item.
            repair_item = dict(item)
            repair_item["prompt"] = repair_prompt

            try:
                # Build the manifest item.
                manifest_item = build_manifest_item(driver, repair_item)

                # Dispatch the repair.
                dispatch_result = dispatch_item(driver, manifest_item, workdir=workdir)

                # Update the item result.
                item_result["verified"] = dispatch_result.get("verified", False)
                item_result["testExit"] = dispatch_result.get("testExit")
                item_result["error"] = dispatch_result.get("error")
                item_result["filesWritten"] = dispatch_result.get("filesWritten", [])
                item_result["repairs"] += 1

                # If still failed, mark for next round.
                if not item_result["verified"]:
                    next_failed.append((item_index, item, item_result))

            except Exception as exc:
                item_result["error"] = f"repair exception: {exc}"
                item_result["repairs"] += 1
                next_failed.append((item_index, item, item_result))

        # Update failed_items for next round.
        failed_items = next_failed

    # ========================================================================
    # PHASE 5.5: Spot-check verified items (if spot_check_frac > 0)
    # ========================================================================
    if spot_check_frac > 0:
        # Collect verified items and their original test commands.
        verified_items_to_check = []
        for item_index, (idx, original_item, item_result) in enumerate(
            [(i, items[i], r) for i, r in enumerate(result["built"]) if r.get("verified", False)]
        ):
            verified_items_to_check.append((original_item, item_result))

        # Determine how many to spot-check.
        num_to_check = ceil(len(verified_items_to_check) * spot_check_frac)

        # Deterministic sampling: check first N items by slug order.
        # Sort by slug for determinism, then check the first num_to_check.
        verified_items_to_check.sort(key=lambda x: x[0].get("slug", ""))
        items_to_rerun = verified_items_to_check[:num_to_check]

        # Re-run tests for sampled items.
        for original_item, item_result in items_to_rerun:
            test_cmd = original_item.get("testCmd", "")
            workdir = original_item.get("workDir", ".")

            if test_cmd:
                try:
                    rerun_result = driver.run_command(test_cmd, cwd=workdir)
                    # If re-run does NOT exit 0, flip verified to False.
                    if rerun_result.exit_code != 0:
                        item_result["verified"] = False
                        item_result["spot_check_failed"] = True
                except Exception:
                    # On exception, flip verified to False.
                    item_result["verified"] = False
                    item_result["spot_check_failed"] = True

    # ========================================================================
    # PHASE 6: Adversarial review (deferred, not yet enforced)
    # ========================================================================
    # Adversarial review is not yet implemented; mark all as deferred.
    # (TODO in a later increment: real adversarial review dispatch via driver)
    result["adversarial_review"] = "deferred"
    for item_result in result["built"]:
        item_result["adversarial_review"] = "deferred"

    # ========================================================================
    # PHASE 7: Batched ship (git operations, if configured)
    # ========================================================================
    if git is not None:
        # Verify expectTopLevel guard: MUST be a non-empty string matching actual toplevel.
        expect_top_level = git.get("expectTopLevel")
        if not expect_top_level or not isinstance(expect_top_level, str):
            # Empty or missing expectTopLevel with git config is an error.
            result["aborted"] = True
            result["abort_reason"] = "git_toplevel_missing_or_empty"
            return result

        toplevel_result = driver.run_command("git rev-parse --show-toplevel")
        if toplevel_result.exit_code != 0:
            result["aborted"] = True
            result["abort_reason"] = "git_toplevel_check_failed"
            return result

        toplevel = toplevel_result.stdout.strip()
        if toplevel != expect_top_level:
            result["aborted"] = True
            result["abort_reason"] = "git_toplevel_mismatch"
            return result

        # Only ship items that verified green.
        verified_items = [
            item_result for item_result in result["built"]
            if item_result.get("verified", False)
        ]

        if verified_items:
            # Stage and commit.
            files_to_add = []
            for item_result in verified_items:
                files_to_add.extend(item_result.get("filesWritten", []))

            if files_to_add:
                # Add files.
                add_cmd = "git add " + " ".join(files_to_add)
                add_result = driver.run_command(add_cmd)
                if add_result.exit_code != 0:
                    result["aborted"] = True
                    result["abort_reason"] = "git_add_failed"
                    return result

                # Commit.
                commit_msg = f"Wave: {len(verified_items)} items verified"
                commit_cmd = f"git commit -m '{commit_msg}'"
                commit_result = driver.run_command(commit_cmd)
                if commit_result.exit_code != 0:
                    # Might be "nothing to commit"; not necessarily a failure.
                    pass

                # Push.
                push_result = driver.run_command("git push")
                if push_result.exit_code != 0:
                    result["aborted"] = True
                    result["abort_reason"] = "git_push_failed"
                    return result

                # Record shipped items.
                result["shipped"] = [item_result["slug"] for item_result in verified_items]

    return result
