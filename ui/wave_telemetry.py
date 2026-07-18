#!/usr/bin/env python3
"""
Wave telemetry collector — current wave phase, cost metrics, and blockers.

Reads state at CALL TIME (not import time) to ensure test isolation.
State sources:
  - state/orchestrator-status.json: current phase and activity (preferred, <24h)
  - STATE.md: current phase and wave info (fallback if status file missing/stale)
  - AUDIT-BACKLOG.md: top blocker via parse
  - state/ledger/OUTCOMES-LEDGER.md: cost data (re-uses cost.py logic)
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import config
import cost


def _read_orchestrator_status():
    """Read orchestrator-status.json if fresh (<24h old).

    Returns:
        tuple: (phase_str, activity_str, source_str) or (None, None, None) if missing/stale/malformed
    """
    try:
        status_file = config.ORCH_STATUS_FILE
        if not status_file.exists():
            return None, None, None

        content = status_file.read_text(encoding='utf-8')
        data = json.loads(content)

        # Extract updated_at and check freshness
        updated_at_str = data.get("updated_at")
        if not updated_at_str:
            return None, None, None

        # Parse ISO format timestamp (handle both "Z" and "+00:00" suffixes)
        updated_at_str_normalized = updated_at_str.replace("Z", "+00:00")
        try:
            updated_at = datetime.fromisoformat(updated_at_str_normalized)
        except ValueError:
            return None, None, None

        # Check if fresh (<24h) and not in the future (beyond ~60s clock skew tolerance)
        now = datetime.now(timezone.utc)
        age = now - updated_at
        # Treat future-dated timestamps (beyond 60s clock skew) as NOT fresh (fail-closed)
        if age > timedelta(hours=24) or age < -timedelta(seconds=60):
            return None, None, None

        # Extract phase and activity
        phase = data.get("phase", "").lower()
        activity = data.get("activity", "").lower()

        if not phase:
            return None, None, None

        return phase, activity, "orchestrator-status"
    except Exception as e:
        print(f"[wave_telemetry] Error reading orchestrator-status.json: {e}", file=sys.stderr)
        return None, None, None


def _parse_state_md_phase():
    """Extract current phase and wave from STATE.md.

    Looks for lines like:
      ## Phase: `rc-1-published-source-available` (2026-07-17, current)
    or
      ## Phase: `wave-rc.2` (2026-07-17, current)

    Returns:
        dict: {"wave": str, "phase": str} or {"wave": "unknown", "phase": "unknown"}
    """
    try:
        state_md = config.AESOP_ROOT / "STATE.md"
        if not state_md.exists():
            return {"wave": "unknown", "phase": "unknown"}

        content = state_md.read_text(encoding='utf-8')

        # Look for ## Phase: `...` (..., current)
        # Extract the phase name between backticks and the wave indicator
        match = re.search(r'## Phase:\s*`([^`]+)`', content)
        if not match:
            return {"wave": "unknown", "phase": "unknown"}

        phase = match.group(1)

        # Extract wave name from phase (e.g., "wave-rc.2" from "rc-1-published-source-available")
        # Try to find a pattern like "wave-" or "rc"
        wave_match = re.search(r'(wave|rc)[-.]?(\w+)', phase, re.IGNORECASE)
        if wave_match:
            wave_str = wave_match.group(0)  # e.g., "wave-rc.2" or "rc-1"
        else:
            wave_str = phase  # Fallback to phase itself

        return {
            "wave": wave_str.lower(),
            "phase": phase.lower()
        }
    except Exception as e:
        print(f"[wave_telemetry] Error parsing STATE.md: {e}", file=sys.stderr)
        return {"wave": "unknown", "phase": "unknown"}


def _parse_top_blocker():
    """Extract top blocker from AUDIT-BACKLOG.md.

    Looks for the first P0 item with status 🔵 (inflight) or ⬜ (todo).
    Returns the title if found, otherwise looks for orchestrator-status.

    Returns:
        str: blocker title or reason, e.g., "CI test flakes", "unknown"
    """
    try:
        backlog_file = config.AUDIT_BACKLOG_FILE
        if not backlog_file.exists():
            return "unknown"

        content = backlog_file.read_text(encoding='utf-8')
        lines = content.split('\n')

        in_p0 = False
        for line in lines:
            line_stripped = line.strip()

            # Check if we entered P0 section
            if re.match(r'^##\s*P0\b', line_stripped):
                in_p0 = True
                continue

            # If we entered a different tier, stop
            if line_stripped.startswith('## ') and not re.match(r'^##\s*P0\b', line_stripped):
                in_p0 = False
                continue

            if in_p0 and line_stripped.startswith('- '):
                # Check for inflight (🔵) or todo (⬜) status
                if '🔵' in line_stripped or '⬜' in line_stripped:
                    # Extract title after status
                    # Pattern: - 🔵 **[tag] Title**
                    match = re.search(r'(?:🔵|⬜)\s+\*\*\[([^\]]+)\]\s+(.+?)\*\*', line_stripped)
                    if match:
                        title = match.group(2)
                        return title

        return "unknown"
    except Exception as e:
        print(f"[wave_telemetry] Error parsing blocker: {e}", file=sys.stderr)
        return "unknown"


def _get_wave_cost_metrics():
    """Get cost metrics for the current wave.

    Uses cost.py to parse the ledger and return this-wave totals.
    For now, returns a simplified snapshot of per-model tokens and OK rate.

    Returns:
        dict: {
            "tokens_used": int,
            "top_model": str,
            "ok_rate": float (0.0-1.0)
        }
    """
    try:
        summary = cost.get_cost_summary()

        if "error" in summary:
            return {
                "tokens_used": 0,
                "top_model": "unknown",
                "ok_rate": 0.0
            }

        # Sum total tokens across all models
        total_tokens = 0
        top_model = "unknown"
        top_model_tokens = 0

        for model, stats in summary.get("models", {}).items():
            tokens = stats.get("tokens_in", 0) + stats.get("tokens_out", 0)
            total_tokens += tokens
            if tokens > top_model_tokens:
                # Extract model name (e.g., "haiku" from "claude-haiku-4-5" or "claude-haiku-4-5-20251001")
                model_lower = model.lower()
                if "haiku" in model_lower:
                    top_model = "haiku"
                elif "sonnet" in model_lower:
                    top_model = "sonnet"
                elif "opus" in model_lower:
                    top_model = "opus"
                else:
                    # Fallback to last part of model id
                    top_model = model.split("-")[-1]
                top_model_tokens = tokens

        scorecard = summary.get("overall_scorecard", {})
        ok_rate = scorecard.get("ok_rate", 0.0)

        return {
            "tokens_used": total_tokens,
            "top_model": top_model,
            "ok_rate": ok_rate
        }
    except Exception as e:
        print(f"[wave_telemetry] Error computing cost metrics: {e}", file=sys.stderr)
        return {
            "tokens_used": 0,
            "top_model": "unknown",
            "ok_rate": 0.0
        }


def get_wave_telemetry():
    """Get consolidated wave telemetry snapshot.

    Prefers state/orchestrator-status.json (if fresh <24h) over STATE.md regex parsing.
    Reads all state at call time (not import time) to ensure test isolation.

    Returns:
        dict: {
            "wave": str,
            "phase": str,
            "blocker": str,
            "tokens_used": int,
            "top_model": str,
            "ok_rate": float,
            "source": "orchestrator-status" | "state-md"
        }
    """
    try:
        # Try orchestrator-status.json first (fresh <24h)
        orch_phase, orch_activity, source = _read_orchestrator_status()

        if orch_phase:
            # Fresh orchestrator-status.json found; use it
            # Extract wave identifier from phase (e.g., "wave-26" from "wave-26-verify")
            wave_match = re.search(r'(wave|rc)[-.]?(\w+)', orch_phase, re.IGNORECASE)
            if wave_match:
                wave_str = wave_match.group(0)  # e.g., "wave-26" or "rc-1"
            else:
                wave_str = orch_phase  # Fallback to phase itself
            phase_info = {
                "wave": wave_str.lower(),
                "phase": orch_phase
            }
            source_field = source
        else:
            # Fall back to STATE.md
            phase_info = _parse_state_md_phase()
            source_field = "state-md"

        blocker = _parse_top_blocker()
        cost_metrics = _get_wave_cost_metrics()

        return {
            "wave": phase_info["wave"],
            "phase": phase_info["phase"],
            "blocker": blocker,
            "tokens_used": cost_metrics["tokens_used"],
            "top_model": cost_metrics["top_model"],
            "ok_rate": cost_metrics["ok_rate"],
            "source": source_field
        }
    except Exception as e:
        print(f"[wave_telemetry] Uncaught error: {e}", file=sys.stderr)
        return {
            "wave": "unknown",
            "phase": "unknown",
            "blocker": "error",
            "tokens_used": 0,
            "top_model": "unknown",
            "ok_rate": 0.0,
            "source": "error"
        }
