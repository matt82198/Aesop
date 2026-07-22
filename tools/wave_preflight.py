#!/usr/bin/env python3
"""
Wave preflight validator — check repo readiness before starting a wave.

Validates:
  1. Current repo is on a feature branch (never main/master)
  2. Working tree clean
  3. STATE.md phase heading consistent with state/orchestrator-status.json phase
     (warning-level: drift is reported but does not block the wave)
  4. No .HALT sentinel
  5. Heartbeats fresh (watchdog 200s) and orchestrator-status.json fresh (300s)
  6. state/tracker.json parses as JSON
  7. secret_scan importable

Exit codes:
  0 = ready (all checks pass, or only warnings like phase drift)
  1 = blocked (one or more critical checks failed)

Output:
  --text (default): numbered list of checks with status and detail
  --json: {ready: bool, checks: [{name, ok, detail}]}

Usage:
  python tools/wave_preflight.py [--root REPO_ROOT] [--state-root STATE_ROOT] [--json]

Arguments:
  --root REPO_ROOT: repository root directory (default: cwd)
  --state-root STATE_ROOT: state directory (default: REPO_ROOT/state or ./state)
  --json: output in JSON format (default: text)

Environment:
  AESOP_STATE_ROOT: state dir (takes precedence over --state-root argument)
  AESOP_ROOT: repo root (default: cwd or inferred from .git)
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from common import get_state_dir, check_heartbeat_staleness
except ImportError:
    from tools.common import get_state_dir, check_heartbeat_staleness

try:
    import halt
except ImportError:
    from tools import halt

try:
    from state_store.read_api import ReadAPI
except ImportError:
    # Fallback if state_store not accessible (shouldn't happen)
    ReadAPI = None


def load_config(root_dir=None):
    """Load aesop.config.json from root, return dict (or {} if absent/bad)."""
    if root_dir is None:
        root_dir = Path.cwd()
    else:
        root_dir = Path(root_dir)

    config_file = root_dir / "aesop.config.json"
    if not config_file.exists():
        return {}
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def resolve_state_dir(root_dir=None, config=None):
    """Resolve state dir: AESOP_STATE_ROOT env > config state_root > ./state."""
    if os.environ.get("AESOP_STATE_ROOT"):
        return Path(os.environ["AESOP_STATE_ROOT"])

    if root_dir is None:
        root_dir = Path.cwd()
    else:
        root_dir = Path(root_dir)

    if config is None:
        config = load_config(root_dir)

    state_root = config.get("state_root") if isinstance(config, dict) else None
    if state_root:
        p = Path(state_root).expanduser()
        if not p.is_absolute():
            p = root_dir / p
        return p

    return root_dir / "state"


def parse_state_md_phase(state_md_path):
    """Extract phase from STATE.md heading: ## Phase: `<phase>` ...

    Returns:
        str or None: the phase name, or None if not found/unparseable.
    """
    if not state_md_path.exists():
        return None

    try:
        content = state_md_path.read_text(encoding="utf-8")
        # Match: ## Phase: `<phase>` ...
        match = re.search(r'^##\s+Phase:\s+`([^`]+)`', content, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception:
        pass

    return None


def parse_orchestrator_status_phase(status_json_path):
    """Extract phase from orchestrator-status.json.

    Returns:
        str or None: the phase field, or None if not found/unparseable.
    """
    if not status_json_path.exists():
        return None

    try:
        data = json.loads(status_json_path.read_text(encoding="utf-8"))
        return data.get("phase")
    except Exception:
        pass

    return None


def check_orchestrator_status_freshness(status_json_path, threshold_s):
    """Check if orchestrator-status.json is fresh based on updated_at timestamp.

    Uses read_api if available; falls back to direct read if not.

    Args:
        status_json_path: Path to orchestrator-status.json (or state dir)
        threshold_s: Staleness threshold in seconds

    Returns:
        Tuple of (is_stale, age_s, info):
          is_stale (bool): True if file missing, unreadable, or age >= threshold_s
          age_s (int): Age in seconds (0 if file missing/unreadable)
          info (str or None): Descriptive message if stale/missing, None if fresh
    """
    # If ReadAPI is available, use it for the check
    if ReadAPI is not None:
        try:
            # Determine state_dir: if status_json_path is the status file, use its parent
            status_path = Path(status_json_path)
            if status_path.name == "orchestrator-status.json":
                state_dir = status_path.parent
            else:
                state_dir = status_path

            api = ReadAPI(str(state_dir))
            status = api.read_orchestrator_status()
            if status is None:
                return True, 0, "orchestrator-status.json file missing or unreadable"

            # Check freshness
            updated_at = status.get("updated_at")
            if not updated_at:
                return True, 0, "orchestrator-status.json missing updated_at field"

            # Parse ISO 8601 timestamp
            import datetime
            normalized_ts = updated_at.replace("Z", "+00:00")
            updated_dt = datetime.datetime.fromisoformat(normalized_ts)
            timestamp = updated_dt.timestamp()

            age_seconds = int(time.time()) - int(timestamp)

            # Check for far-future timestamp (clock skew beyond tolerance)
            if age_seconds < -120:
                return True, 0, "orchestrator-status timestamp in future (clock skew)"

            # Clamp small negative ages to 0
            age_seconds = max(0, age_seconds)

            if age_seconds >= threshold_s:
                return True, age_seconds, f"orchestrator-status stale ({age_seconds}s >= {threshold_s}s)"

            return False, age_seconds, None
        except Exception as e:
            return True, 0, f"orchestrator-status.json unreadable: {e}"

    # Fallback to direct file read if ReadAPI not available
    if not status_json_path.exists():
        return True, 0, "orchestrator-status.json file missing"

    try:
        data = json.loads(status_json_path.read_text(encoding="utf-8"))
        updated_at = data.get("updated_at")
        if not updated_at:
            return True, 0, "orchestrator-status.json missing updated_at field"

        # Parse ISO 8601 timestamp (handle both "Z" and "+00:00" timezone formats)
        import datetime
        # Normalize Z suffix to +00:00 for fromisoformat compatibility
        normalized_ts = updated_at.replace("Z", "+00:00")
        updated_dt = datetime.datetime.fromisoformat(normalized_ts)
        timestamp = updated_dt.timestamp()

        age_seconds = int(time.time()) - int(timestamp)

        # Check for far-future timestamp (clock skew beyond tolerance)
        # More than 120s in the future is treated as stale, not clamped-to-fresh
        if age_seconds < -120:
            return True, 0, "orchestrator-status timestamp in future (clock skew)"

        # Clamp small negative ages to 0 (normal clock skew recovery)
        age_seconds = max(0, age_seconds)

        if age_seconds >= threshold_s:
            return True, age_seconds, f"orchestrator-status stale ({age_seconds}s >= {threshold_s}s)"

        return False, age_seconds, None
    except Exception as e:
        return True, 0, f"orchestrator-status.json unreadable: {e}"


def is_git_repo(root_dir):
    """Check if root_dir is a git repository."""
    git_dir = Path(root_dir) / ".git"
    return git_dir.exists()


def get_current_branch(root_dir):
    """Get current git branch name.

    Returns:
        str or None: branch name, or None if unable to determine (e.g., not a repo, detached HEAD).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch == "HEAD":
                # Detached HEAD
                return None
            return branch
    except Exception:
        pass
    return None


def is_working_tree_clean(root_dir):
    """Check if git working tree is clean (ignores untracked files).

    Returns:
        (bool, str or None): (is_clean, detail_msg if not clean)
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if not output:
                return True, None
            # Filter out untracked files (lines starting with ??)
            # and only consider tracked file changes (M, A, D, etc.)
            dirty_lines = [
                line for line in output.split("\n")
                if line and not line.startswith("??")
            ]
            if not dirty_lines:
                return True, None
            # List first few dirty files
            lines = dirty_lines[:3]
            detail = "uncommitted changes: " + "; ".join(lines)
            if len(dirty_lines) > 3:
                detail += f" (+{len(dirty_lines) - 3} more)"
            return False, detail
    except Exception:
        pass
    return False, "unable to check git status"


def can_import_secret_scan():
    """Check if secret_scan can be imported.

    Returns:
        (bool, str or None): (importable, detail_msg if not)
    """
    try:
        import secret_scan
        return True, None
    except ImportError as e:
        return False, str(e)


def run_checks(root_dir=None, state_dir=None, config=None):
    """Run all preflight checks.

    Args:
        root_dir: repo root (inferred from cwd if None)
        state_dir: state dir (resolved if None)
        config: aesop.config.json dict (loaded if None)

    Returns:
        dict: {
            ready: bool (all checks pass/warn),
            checks: [
                {name: str, ok: bool, detail: str},
                ...
            ]
        }
    """
    if root_dir is None:
        root_dir = Path.cwd()
    else:
        root_dir = Path(root_dir)

    if config is None:
        config = load_config(root_dir)

    if state_dir is None:
        state_dir = resolve_state_dir(root_dir, config)
    else:
        state_dir = Path(state_dir)

    checks = []

    # Check 1: Git repo exists
    is_repo = is_git_repo(root_dir)
    checks.append({
        "name": "Git repository",
        "ok": is_repo,
        "detail": "repo found" if is_repo else "not a git repo",
    })

    if not is_repo:
        # Can't proceed without a repo
        return {"ready": False, "checks": checks}

    # Check 2: On a feature branch (not main/master)
    branch = get_current_branch(root_dir)
    if branch is None:
        on_feature_branch = False
        detail = "detached HEAD or unable to determine branch"
    else:
        on_feature_branch = branch not in ("main", "master")
        detail = f"branch={branch}"

    checks.append({
        "name": "Feature branch (not main/master)",
        "ok": on_feature_branch,
        "detail": detail,
    })

    # Check 3: Working tree clean
    clean, dirty_detail = is_working_tree_clean(root_dir)
    checks.append({
        "name": "Working tree clean",
        "ok": clean,
        "detail": dirty_detail or "no uncommitted changes",
    })

    # Check 4: No .HALT sentinel
    is_halted = halt.is_halted(state_dir)
    halt_detail = "not halted"
    if is_halted:
        halt_info = halt.get_halt_info(state_dir)
        halt_detail = halt_info.get("reason", "halted") if halt_info else "halted"

    checks.append({
        "name": "No .HALT sentinel",
        "ok": not is_halted,
        "detail": halt_detail,
    })

    # Check 5: STATE.md phase vs orchestrator-status.json phase (warn-level)
    # Genuine comparison: only warn if both phases exist and differ
    state_md_path = root_dir / "STATE.md"
    status_json_path = state_dir / "orchestrator-status.json"

    state_phase = parse_state_md_phase(state_md_path)
    status_phase = parse_orchestrator_status_phase(status_json_path)

    # Determine phase drift: only if both are defined and differ
    drift_detected = False
    if state_phase is not None and status_phase is not None:
        if state_phase != status_phase:
            # Drift detected: both phases exist but differ
            drift_detected = True
            phase_detail = f"STATE.md={state_phase}, status.json={status_phase} [WARN: drift detected]"
        else:
            # Phases match
            phase_detail = f"STATE.md={state_phase}, status.json={status_phase}"
    else:
        # One or both phases missing (not yet ready or not applicable)
        phase_detail = f"STATE.md={state_phase}, status.json={status_phase}"

    # Phase drift check: warning-level (drift is reported but does not block)
    # The check always passes (phase_ok = True), but drift detail is visible in output
    # This makes the check non-vacuous: drift is detected and reported, but doesn't block
    phase_ok = True

    checks.append({
        "name": "STATE.md phase consistent with orchestrator-status.json (warning-level)",
        "ok": phase_ok,
        "detail": phase_detail,
    })

    # Check 6: Heartbeats and status freshness
    # Check watchdog heartbeat (200s threshold) and orchestrator-status.json (300s)
    heartbeat_details = []
    all_heartbeats_ok = True

    watchdog_hb = state_dir / ".watchdog-heartbeat"
    is_stale, age, info = check_heartbeat_staleness(watchdog_hb, 200)
    hb_name = "watchdog"
    if is_stale:
        all_heartbeats_ok = False
        heartbeat_details.append(f"{hb_name}: {info} (age={age}s)")
    else:
        heartbeat_details.append(f"{hb_name}: fresh (age={age}s)")

    # Check orchestrator-status.json updated_at field (300s threshold)
    status_json_path = state_dir / "orchestrator-status.json"
    is_stale, age, info = check_orchestrator_status_freshness(status_json_path, 300)
    status_name = "orchestrator-status"
    if is_stale:
        all_heartbeats_ok = False
        heartbeat_details.append(f"{status_name}: {info} (age={age}s)")
    else:
        heartbeat_details.append(f"{status_name}: fresh (age={age}s)")

    checks.append({
        "name": "Heartbeats and orchestrator status fresh",
        "ok": all_heartbeats_ok,
        "detail": "; ".join(heartbeat_details),
    })

    # Check 7: state/tracker.json parses as JSON
    tracker_json_path = state_dir / "tracker.json"
    tracker_ok = False
    tracker_detail = "tracker.json not found"

    if tracker_json_path.exists():
        try:
            json.loads(tracker_json_path.read_text(encoding="utf-8"))
            tracker_ok = True
            tracker_detail = "valid JSON"
        except json.JSONDecodeError as e:
            tracker_detail = f"invalid JSON: {e}"
        except Exception as e:
            tracker_detail = f"unreadable: {e}"

    checks.append({
        "name": "state/tracker.json parses as JSON",
        "ok": tracker_ok,
        "detail": tracker_detail,
    })

    # Check 8: secret_scan importable
    can_import, import_detail = can_import_secret_scan()
    checks.append({
        "name": "secret_scan importable",
        "ok": can_import,
        "detail": import_detail or "importable",
    })

    # Determine overall readiness: pass if all checks ok (warnings don't fail)
    # For now, all checks must pass (warnings are just flags in detail)
    all_ok = all(c["ok"] for c in checks)

    return {
        "ready": all_ok,
        "checks": checks,
    }


def main(argv=None):
    """CLI entry point."""
    argv = sys.argv[1:] if argv is None else argv

    root_dir = None
    state_dir = None
    output_format = "text"

    # Parse arguments
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--root":
            i += 1
            if i < len(argv):
                root_dir = argv[i]
            i += 1
        elif arg.startswith("--root="):
            root_dir = arg[len("--root="):]
            i += 1
        elif arg == "--state-root":
            i += 1
            if i < len(argv):
                state_dir = argv[i]
            i += 1
        elif arg.startswith("--state-root="):
            state_dir = arg[len("--state-root="):]
            i += 1
        elif arg == "--json":
            output_format = "json"
            i += 1
        else:
            print(f"Unknown argument: {arg}", file=sys.stderr)
            return 2

    if root_dir is None:
        root_dir = Path.cwd()
    else:
        root_dir = Path(root_dir)

    config = load_config(root_dir)
    if state_dir is None:
        state_dir = resolve_state_dir(root_dir, config)
    else:
        state_dir = Path(state_dir)

    result = run_checks(root_dir, state_dir, config)

    if output_format == "json":
        print(json.dumps(result, indent=2))
    else:
        # Text format: numbered list
        print("Wave preflight checks:")
        for i, check in enumerate(result["checks"], 1):
            status = "PASS" if check["ok"] else "FAIL"
            print(f"{i}. {check['name']}: {status}")
            if check["detail"]:
                print(f"   {check['detail']}")

        if result["ready"]:
            print("\nPASS: Ready for wave")
        else:
            print("\nFAIL: Not ready for wave (see failures above)")

    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
