#!/usr/bin/env python3
"""Wave scheduler: single-cycle orchestration of backlog intake, manifest build, and wave dispatch.

WS3a pilot: deterministic one-cycle loop that:
  1. Intakes up to N file-disjoint todo items from tracker.json (respects ownsFiles)
  2. Builds a run_wave manifest via wave_templates conventions
  3. Invokes driver.wave_loop.run_wave with recovery journal + git ship config
  4. STOPS before merge: emits Report JSON for human/orchestrator review
  5. Bounded by: HALT file check (before each phase) + cost ceiling check

CLI: python driver/wave_scheduler.py --tracker <path> --max-items N --dry-run|--execute

Manifest item schema (tracker):
  {
    "id": "item-uuid",
    "slug": "feat/foo",
    "status": "todo|blocked|pending-ci",
    "priority": "P1|P2|P3",
    "ownsFiles": ["path/a.py", "path/b.py"],
    "prompt": "user prompt text",
    "testCmd": "python -m unittest tests.test_foo",
    "workDir": "."  (optional, defaults to ".")
  }

Report schema:
  {
    "phase": "intake|manifest|dispatch|halt|ceiling",
    "wave_id": "uuid",
    "items_selected": [item_ids],
    "items_shipped": [item_ids],  (if executed)
    "branch": "feat/w28-...",
    "sha": "abc123...",
    "halt_reason": "...",  (if halted)
    "ceiling_reason": "...",  (if ceiling exceeded)
    "error": "...",  (if unhandled error)
    "success": true|false
  }

stdlib-only, ASCII-only, Windows + Linux safe.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

# Add driver/ and tools/ to path
REPO = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO / "driver"
TOOLS_DIR = REPO / "tools"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# Import core modules
from wave_loop import run_wave
from agent_driver import AgentDriver
from verification_policy import verification_policy

# Import safety gates (optional)
try:
    import halt
    import cost_ceiling
except ImportError:
    halt = None
    cost_ceiling = None

try:
    from common import get_state_dir
except ImportError:
    from tools.common import get_state_dir


# ========================================================================
# Tracker & Manifest Loading
# ========================================================================

def load_tracker_items(tracker_path: str) -> List[Dict[str, Any]]:
    """Load tracker.json items.

    Args:
        tracker_path: absolute path to tracker.json

    Returns:
        list of item dicts, or [] if file missing/invalid
    """
    p = Path(tracker_path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Handle both {"items": [...]} and [...]
        if isinstance(data, dict):
            return data.get("items", [])
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def filter_todo_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter items to only status=todo, sorted by priority then creation date.

    Priority order: P1 > P2 > P3
    Within same priority: oldest first
    """
    todo = [item for item in items if item.get("status") == "todo"]

    # Sort by priority (P1=0, P2=1, P3=2), then by createdAt
    def priority_rank(item):
        prio = item.get("priority", "P3")
        rank = {"P1": 0, "P2": 1, "P3": 2}.get(prio, 2)
        created = item.get("createdAt", "2999-01-01")
        return (rank, created)

    return sorted(todo, key=priority_rank)


def select_disjoint_items(
    items: List[Dict[str, Any]], max_count: int
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Greedily select up to max_count items with no file overlap.

    Greedy algorithm: sort by (file_count, priority), pick items that don't
    overlap ownsFiles with already-selected items.

    Args:
        items: list of tracker items (should be todo-filtered and sorted)
        max_count: maximum items to select

    Returns:
        (selected_items, skipped_item_ids) — skipped due to overlap
    """
    selected = []
    used_files: Set[str] = set()
    skipped = []

    # Sort by file count (ascending) to pack smaller items first
    def item_sort_key(item):
        files = item.get("ownsFiles", [])
        prio = item.get("priority", "P3")
        rank = {"P1": 0, "P2": 1, "P3": 2}.get(prio, 2)
        return (len(files), rank)

    items_to_process = sorted(items, key=item_sort_key)

    for item in items_to_process:
        if len(selected) >= max_count:
            break

        owns = set(item.get("ownsFiles", []))

        # Check for overlap
        if owns & used_files:
            skipped.append(item.get("id", "unknown"))
            continue

        # No overlap, select it
        selected.append(item)
        used_files.update(owns)

    return selected, skipped


def _check_halt_file(state_dir: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
    """Check if .HALT file exists and return its reason.

    Returns:
        (is_halted: bool, reason: str|None)
    """
    if halt is None:
        return False, None

    try:
        if halt.is_halted(state_dir):
            info = halt.get_halt_info(state_dir)
            reason = info.get("reason", "Unknown halt") if info else "Unknown halt"
            return True, reason
    except Exception:
        pass
    return False, None


def _check_cost_ceiling(state_dir: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
    """Check cost ceiling and return if exceeded + reason.

    Returns:
        (ceiling_exceeded: bool, reason: str|None)
    """
    if cost_ceiling is None:
        return False, None

    try:
        result = cost_ceiling.check(spent=None, period="wave", state_dir=state_dir, trip=False)
        if result.get("exceeded"):
            return True, f"Cost ceiling exceeded: {result.get('spent', 0)}/{result.get('ceiling', 0)} tokens"
    except Exception:
        pass
    return False, None


# ========================================================================
# Manifest Building
# ========================================================================

def build_wave_manifest(
    selected_items: List[Dict[str, Any]], driver: AgentDriver
) -> Dict[str, Any]:
    """Build a wave manifest from selected tracker items.

    For each item, calls wave_bridge.build_manifest_item() to enrich with
    model + verificationTier. Combines into a wave manifest dict.

    Args:
        selected_items: list of tracker items
        driver: AgentDriver instance

    Returns:
        wave manifest dict ready for run_wave()
    """
    try:
        from wave_bridge import build_manifest_item
    except ImportError:
        from driver.wave_bridge import build_manifest_item

    manifest_items = []
    for item in selected_items:
        try:
            m_item = build_manifest_item(driver, item)
            manifest_items.append(m_item)
        except Exception as e:
            # If build fails, skip this item (fail-safe)
            print(f"[wave_scheduler] Failed to build manifest for {item.get('id')}: {e}", file=sys.stderr)
            continue

    wave_id = str(uuid.uuid4())
    return {
        "wave_id": wave_id,
        "items": manifest_items,
        "wave_description": f"WS3a pilot wave {wave_id[:8]}",
    }


# ========================================================================
# Reporting
# ========================================================================

def emit_report(
    phase: str,
    wave_id: str,
    items_selected: List[str],
    items_shipped: Optional[List[str]] = None,
    branch: Optional[str] = None,
    sha: Optional[str] = None,
    halt_reason: Optional[str] = None,
    ceiling_reason: Optional[str] = None,
    error: Optional[str] = None,
    success: bool = False,
) -> Dict[str, Any]:
    """Emit a Report JSON structure.

    Returns:
        report dict (ready to serialize)
    """
    report = {
        "phase": phase,
        "wave_id": wave_id,
        "items_selected": items_selected,
        "items_shipped": items_shipped or [],
        "branch": branch,
        "sha": sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": success,
    }

    if halt_reason:
        report["halt_reason"] = halt_reason
    if ceiling_reason:
        report["ceiling_reason"] = ceiling_reason
    if error:
        report["error"] = error

    return report


# ========================================================================
# Main Orchestrator
# ========================================================================

def run_wave_scheduler(
    tracker_path: str,
    max_items: int = 5,
    dry_run: bool = False,
    driver: Optional[AgentDriver] = None,
    state_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run one complete wave cycle (intake -> manifest -> dispatch -> report).

    Args:
        tracker_path: path to tracker.json
        max_items: max items to select
        dry_run: if True, print manifest without dispatch
        driver: AgentDriver instance (defaults to FakeDriver for testing)
        state_dir: state directory (defaults to ./state)

    Returns:
        Report dict (phase, wave_id, items_selected, items_shipped, etc.)
    """
    if state_dir is None:
        try:
            state_dir = get_state_dir()
        except Exception:
            state_dir = Path("./state")

    state_dir = Path(state_dir)
    wave_id = str(uuid.uuid4())

    # ====== PHASE 1: HALT CHECK ======
    is_halted, halt_reason = _check_halt_file(state_dir)
    if is_halted:
        return emit_report(
            phase="halt",
            wave_id=wave_id,
            items_selected=[],
            halt_reason=halt_reason,
            success=False,
        )

    # ====== PHASE 2: INTAKE ======
    all_items = load_tracker_items(tracker_path)
    todo_items = filter_todo_items(all_items)

    if not todo_items:
        return emit_report(
            phase="intake",
            wave_id=wave_id,
            items_selected=[],
            success=True,  # Empty intake is clean, not an error
        )

    # ====== PHASE 3: DISJOINT SELECTION ======
    selected_items, skipped_ids = select_disjoint_items(todo_items, max_items)

    if not selected_items:
        return emit_report(
            phase="intake",
            wave_id=wave_id,
            items_selected=[],
            success=True,  # No eligible items is clean
        )

    selected_ids = [item.get("id", "unknown") for item in selected_items]

    # ====== PHASE 4: MANIFEST BUILD ======
    # Use default FakeDriver if none provided (for testing)
    if driver is None:
        from tests.test_wave_loop import FakeDriver
        driver = FakeDriver()

    try:
        manifest = build_wave_manifest(selected_items, driver)
    except Exception as e:
        return emit_report(
            phase="manifest",
            wave_id=wave_id,
            items_selected=selected_ids,
            error=str(e),
            success=False,
        )

    # ====== PHASE 5: DRY-RUN CHECK ======
    if dry_run:
        return emit_report(
            phase="manifest",
            wave_id=wave_id,
            items_selected=selected_ids,
            success=True,
        )

    # ====== PHASE 6: HALT CHECK (BEFORE DISPATCH) ======
    is_halted, halt_reason = _check_halt_file(state_dir)
    if is_halted:
        return emit_report(
            phase="halt",
            wave_id=wave_id,
            items_selected=selected_ids,
            halt_reason=halt_reason,
            success=False,
        )

    # ====== PHASE 7: COST CEILING CHECK ======
    ceiling_exceeded, ceiling_reason = _check_cost_ceiling(state_dir)
    if ceiling_exceeded:
        return emit_report(
            phase="ceiling",
            wave_id=wave_id,
            items_selected=selected_ids,
            ceiling_reason=ceiling_reason,
            success=False,
        )

    # ====== PHASE 8: RUN WAVE ======
    try:
        # Prepare state_dir
        state_dir.mkdir(parents=True, exist_ok=True)

        # Call run_wave with recovery journal + git config
        wave_result = run_wave(
            driver=driver,
            manifest=manifest,
            state_dir=state_dir,
            git={"expectTopLevel": str(REPO)},
            resume_journal=True,
        )

        # Extract shipped items from result
        items_shipped = [
            item.get("id", "unknown")
            for item in wave_result.get("shipped", [])
        ]

        # Get branch and sha if available
        branch = wave_result.get("branch")
        sha = wave_result.get("sha")

        return emit_report(
            phase="dispatch",
            wave_id=wave_id,
            items_selected=selected_ids,
            items_shipped=items_shipped,
            branch=branch,
            sha=sha,
            success=wave_result.get("success", False),
        )

    except Exception as e:
        return emit_report(
            phase="dispatch",
            wave_id=wave_id,
            items_selected=selected_ids,
            error=str(e),
            success=False,
        )


# ========================================================================
# CLI
# ========================================================================

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Wave scheduler: intake -> manifest -> dispatch -> report"
    )
    parser.add_argument(
        "--tracker",
        required=True,
        help="Path to tracker.json",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Maximum items to select (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print manifest without dispatch",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the wave (default: dry-run)",
    )
    parser.add_argument(
        "--state-dir",
        help="State directory (default: ./state)",
    )

    args = parser.parse_args()

    dry_run = not args.execute

    # Run scheduler
    report = run_wave_scheduler(
        tracker_path=args.tracker,
        max_items=args.max_items,
        dry_run=dry_run,
        state_dir=Path(args.state_dir) if args.state_dir else None,
    )

    # Output report as JSON
    print(json.dumps(report, indent=2))

    # Exit with success/failure
    sys.exit(0 if report.get("success") else 1)


if __name__ == "__main__":
    main()
