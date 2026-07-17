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

try:
    import halt
except ImportError:
    from tools import halt


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


def read_ledger_total_tokens(state_dir):
    """Sum tokens_in + tokens_out across every row of OUTCOMES-LEDGER.md.

    Returns 0 if the ledger doesn't exist or is unreadable/empty. Parses the
    same markdown-table format tools/fleet_ledger.py writes, independently
    (read-only) — no import of fleet_ledger.py, so this has no side effects
    on the ledger and no coupling to its internal state.
    """
    ledger_file = Path(state_dir) / "ledger" / "OUTCOMES-LEDGER.md"
    if not ledger_file.exists():
        return 0
    try:
        lines = ledger_file.read_text(encoding="utf-8").split("\n")
    except OSError:
        return 0

    total = 0
    for line in lines:
        if not line.strip() or "---|" in line or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 6:
            continue
        try:
            tokens_in = int(cells[4]) if cells[4] else 0
            tokens_out = int(cells[5]) if cells[5] else 0
        except ValueError:
            continue
        total += tokens_in + tokens_out
    return total


def check(spent=None, period="wave", config=None, state_dir=None, trip=True):
    """Check spend against the configured ceiling for `period`.

    Returns a dict: {"period", "ceiling", "spent", "exceeded", "tripped"}.
    """
    if config is None:
        config = load_config()
    if state_dir is None:
        state_dir = halt.resolve_state_dir(config=config)
    state_dir = Path(state_dir)

    ceiling = get_ceiling(config, period)

    if spent is None:
        spent = read_ledger_total_tokens(state_dir)
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
