#!/usr/bin/env python3
"""
Cost ceiling guard — trips tools/halt.py's kill switch when fleet spend
(tokens) meets or exceeds a configured ceiling.

Why: wave-26 critique — autonomy expanded to self-merging portfolio PRs on
green with no ceiling/cap/limit/abort anywhere in the harness. This is the cap.

Configuration (aesop.config.json):
  "limits": {
    "max_wave_tokens": null,   # null = disabled (opt-in)
    "max_daily_tokens": null
  }

Spend source: an explicit --spent/spent= figure always wins. Otherwise spend
is read from the cost ledger (tools/fleet_ledger.py's OUTCOMES-LEDGER.md under
the resolved state dir): sum of tokens_in + tokens_out across all ledger rows.
Missing/unreadable ledger -> spend of 0 (never trips on a ledger that doesn't
exist yet).

API:
  check(spent=None, period="wave", config=None, state_dir=None, trip=True) -> dict
    Returns {"period", "ceiling", "spent", "exceeded", "tripped"}.
    When exceeded and trip=True, calls tools/halt.py's halt() with a reason
    describing the breach, and "tripped" is True. When ceiling is None
    (unconfigured), exceeded is always False and nothing is ever tripped.

CLI:
  python tools/cost_ceiling.py --check --spent N [--period wave|daily]
    Exit 0 if not exceeded (or ceiling unconfigured), exit 1 if exceeded
    (and thus tripped, unless already halted).
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    import halt
    import fleet_ledger
except ImportError:
    from tools import halt
    from tools import fleet_ledger


def load_config():
    """Load aesop.config.json from current directory, return dict (or {} if absent/bad)."""
    config_file = Path("aesop.config.json")
    if not config_file.exists():
        return {}
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[cost_ceiling] Failed to load config: {e}", file=sys.stderr)
        return {}


def get_ceiling(config, period):
    """Extract the configured ceiling for `period` ('wave' or 'daily'), or None."""
    limits = config.get("limits", {}) if isinstance(config, dict) else {}
    if not isinstance(limits, dict):
        return None
    key = f"max_{period}_tokens"
    value = limits.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_ledger_total_tokens(state_dir, period="wave"):
    """Sum tokens_in + tokens_out from OUTCOMES-LEDGER.md.

    Args:
        state_dir: path to state directory
        period: "wave" (all rows) or "daily" (today's rows only, filtered by UTC date)

    Returns 0 if the ledger doesn't exist or is unreadable/empty.
    Uses fleet_ledger.py's shared parser (single source of truth).
    """
    # Set the state root temporarily so fleet_ledger can find the ledger
    import os
    old_state_root = os.environ.get("AESOP_STATE_ROOT")
    try:
        os.environ["AESOP_STATE_ROOT"] = str(state_dir)
        rows = fleet_ledger.parse_ledger_rows()
    finally:
        if old_state_root is not None:
            os.environ["AESOP_STATE_ROOT"] = old_state_root
        else:
            os.environ.pop("AESOP_STATE_ROOT", None)

    if not rows:
        return 0

    total = 0

    if period == "daily":
        # Filter to today's UTC date only
        today_utc = datetime.now(timezone.utc).date()
        for row in rows:
            # Extract date from ISO timestamp (format: YYYY-MM-DDTHH:MM:SSZ or similar)
            try:
                iso_ts = row['iso_ts']
                # Parse the date part (first 10 characters: YYYY-MM-DD)
                row_date = datetime.fromisoformat(iso_ts.replace('Z', '+00:00')).date()
                if row_date == today_utc:
                    total += row['tokens_in'] + row['tokens_out']
            except (ValueError, IndexError, KeyError):
                # Skip malformed timestamps
                continue
    else:
        # period == "wave": sum all rows
        for row in rows:
            total += row['tokens_in'] + row['tokens_out']

    return total


def check(spent=None, period="wave", config=None, state_dir=None, trip=True):
    """Check spend against the configured ceiling for `period`.

    Returns a dict: {"period", "ceiling", "spent", "exceeded", "tripped", "reason"}.

    Distinctions:
    - Genuine ceiling breach (ceiling is configured, spent >= ceiling): when trip=True,
      writes persistent .HALT sentinel via halt.halt() and sets tripped=True.
    - Exception during spend computation (ledger read/create failure, etc.): signals
      abort of current wave (exceeded=True) but does NOT write persistent sentinel
      (tripped=False). This preserves fleet availability across transient I/O errors
      (e.g., momentary file lock, disk full) while still aborting the current wave.
    """
    try:
        if config is None:
            config = load_config()
        if state_dir is None:
            state_dir = halt.resolve_state_dir(config=config)
        state_dir = Path(state_dir)

        ceiling = get_ceiling(config, period)

        if spent is None:
            spent = read_ledger_total_tokens(state_dir, period=period)
        spent = int(spent)

        exceeded = ceiling is not None and spent >= ceiling
        tripped = False

        if exceeded and trip:
            reason = (
                f"cost ceiling exceeded: {period} spend {spent} tokens >= "
                f"ceiling {ceiling} tokens"
            )
            halt.halt(reason, state_dir=state_dir)
            tripped = True

        return {
            "period": period,
            "ceiling": ceiling,
            "spent": spent,
            "exceeded": exceeded,
            "tripped": tripped,
            "reason": None,
        }
    except Exception as e:
        # Exception during spend computation (e.g., ledger read/create failure,
        # file lock, transient I/O error). This is fail-SAFE: abort the current
        # wave (exceeded=True) to prevent runaway work, but do NOT write the
        # persistent .HALT sentinel (tripped=False). The distinction ensures a
        # transient I/O hiccup does not permanently wedge the fleet.
        reason_text = f"cost_check_error: {type(e).__name__}: {str(e)[:100]}"
        return {
            "period": period,
            "ceiling": None,
            "spent": None,
            "exceeded": True,
            "tripped": False,
            "error": str(e),
            "reason": reason_text,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cost ceiling guard for the fleet kill switch.")
    parser.add_argument("--check", action="store_true", help="Run the ceiling check (required).")
    parser.add_argument("--spent", type=int, default=None, help="Explicit spend figure in tokens; defaults to ledger total.")
    parser.add_argument("--period", choices=("wave", "daily"), default="wave", help="Which ceiling to check against (default: wave).")
    args = parser.parse_args(argv)

    if not args.check:
        parser.print_usage(sys.stderr)
        return 2

    result = check(spent=args.spent, period=args.period)

    # Check for errors FIRST (fail-closed): exception during check() means abort the wave
    if "error" in result:
        reason = result.get("reason", result["error"])
        print(f"[cost_ceiling] FATAL: {reason}", file=sys.stderr)
        return 1

    if result["ceiling"] is None:
        print(f"[cost_ceiling] no {args.period} ceiling configured — skipping (spent={result['spent']})")
        return 0

    if result["exceeded"]:
        print(
            f"[cost_ceiling] EXCEEDED: {args.period} spend {result['spent']} >= "
            f"ceiling {result['ceiling']} — HALT tripped"
        )
        return 1

    print(f"[cost_ceiling] ok: {args.period} spend {result['spent']} < ceiling {result['ceiling']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
