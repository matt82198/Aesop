#!/usr/bin/env python3
"""Cost/scorecard collector — parse ledger and aggregate costs.

This module provides get_cost_summary() which parses the outcomes ledger
markdown table and returns per-model, per-day, and overall cost/token aggregations
with optional pricing estimates.

Ledger format (markdown table):
  | ISO timestamp | agent_type | model | duration | tokens_in | tokens_out | verdict |
  | 2026-07-11T22:08:17 | Agent | claude-haiku-4-5-20251001 | 0 | 8 | 186 | OK |

CostSummary JSON shape (returned by get_cost_summary()):
  {
    "models": {
      "model-id": {
        "runs": int,
        "tokens_in": int,
        "tokens_out": int,
        "verdicts": {"OK": int, "FAILED": int, "EMPTY": int, "HUNG": int}
      },
      ...
    },
    "daily_totals": {
      "YYYY-MM-DD": {"tokens_in": int, "tokens_out": int},
      ...
    },
    "overall_scorecard": {
      "total_runs": int,
      "ok_count": int,
      "failed_count": int,
      "empty_count": int,
      "hung_count": int,
      "ok_rate": float (0.0-1.0),
      "failed_rate": float,
      "empty_rate": float,
      "hung_rate": float
    },
    "skipped_lines": int,
    "has_pricing": bool,
    "estimates_by_model": {
      "model-id": {
        "input_cost": float (dollars),
        "output_cost": float (dollars),
        "total_cost": float (dollars)
      },
      ...
    }
  }

Key behavior:
  - Missing ledger file: returns empty summary with documented shape.
  - Malformed lines: skipped and counted in skipped_lines field.
  - Config read at CALL time (not import time) for test isolation.
  - UTF-8 explicit encoding for all file operations.
  - No external dependencies (pure stdlib).
  - Pricing estimates ONLY if aesop.config.json has a "pricing" map.
"""
import json
from pathlib import Path

# Note: import config at module level, but read config.X at CALL time
# (not at import time) to ensure test-fixture isolation works.
import config


def _validate_ledger_format(lines):
    """Validate that ledger has the expected column structure.

    Checks the first non-empty, non-separator, non-header line to ensure it looks like a data row
    (has ISO timestamp, agent type, model, numeric fields, verdict). Returns (is_valid, error_message).

    Expected format:
      | ISO timestamp | agent_type | model | duration | tokens_in | tokens_out | verdict |
      |---|---|---|---|---|---|---|
      | 2026-07-11T22:08:17 | Agent | claude-haiku-4-5-20251001 | 0 | 8 | 186 | OK |
    """
    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip separator lines (all dashes and pipes)
        if all(c in '|-' for c in line):
            continue

        # This is the first real line; validate it
        if not line.startswith('|') or not line.endswith('|'):
            return False, "First data line does not start/end with pipe"

        parts = [p.strip() for p in line.split('|')]

        # Should have 9 parts: [empty, col1, col2, col3, col4, col5, col6, col7, empty]
        if len(parts) != 9:
            return False, f"Expected 7 columns, got {len(parts) - 2}"

        # Extract columns and validate types
        try:
            timestamp = parts[1]
            agent_type = parts[2]
            model = parts[3]
            duration_str = parts[4]
            tokens_in_str = parts[5]
            tokens_out_str = parts[6]
            verdict = parts[7]

            # Skip header line if timestamp column contains "timestamp" or "ISO"
            if 'timestamp' in timestamp.lower() or 'iso' in timestamp.lower():
                continue

            # Check if timestamp looks like ISO format (contains 'T' and '-')
            if 'T' not in timestamp or '-' not in timestamp:
                return False, f"First data line does not have ISO timestamp in column 1: {timestamp}"

            # Check if tokens are numeric
            try:
                int(tokens_in_str)
                int(tokens_out_str)
            except ValueError:
                return False, f"Token columns must be numeric, got tokens_in={tokens_in_str}, tokens_out={tokens_out_str}"

            # Check if verdict is valid
            if verdict not in ("OK", "FAILED", "EMPTY", "HUNG"):
                return False, f"First data line has invalid verdict: {verdict}"

            return True, ""
        except IndexError:
            return False, "First data line has missing columns"

    # No data lines found
    return True, ""  # Empty ledger is ok


def get_cost_summary():
    """Parse the outcomes ledger and return cost/token/verdict aggregations.

    Reads from the ledger path exposed by config (config.STATE_DIR/ledger/OUTCOMES-LEDGER.md).
    Returns an empty summary with documented shape if ledger is missing or empty.
    Malformed lines are skipped and counted in skipped_lines.

    Validates ledger format on first data line. If format is invalid, returns
    a summary containing {"error": "ledger format invalid"} and logs to stderr.

    All config paths are read at call time (not import time) to ensure
    test-fixture isolation via config.reload().

    Returns:
        dict: CostSummary with models, daily_totals, overall_scorecard,
              skipped_lines, has_pricing, estimates_by_model (or error field if invalid).
    """
    import sys

    # Read ledger path at call time
    ledger_file = config.STATE_DIR / "ledger" / "OUTCOMES-LEDGER.md"

    # Initialize result structure
    result = {
        "models": {},
        "daily_totals": {},
        "overall_scorecard": {
            "total_runs": 0,
            "ok_count": 0,
            "failed_count": 0,
            "empty_count": 0,
            "hung_count": 0,
            "ok_rate": 0.0,
            "failed_rate": 0.0,
            "empty_rate": 0.0,
            "hung_rate": 0.0,
        },
        "skipped_lines": 0,
        "has_pricing": False,
        "estimates_by_model": {},
    }

    # If ledger file doesn't exist, return empty summary
    if not ledger_file.exists():
        return result

    # Read and parse ledger with explicit UTF-8 encoding
    try:
        content = ledger_file.read_text(encoding='utf-8')
    except Exception:
        # Graceful: if read fails, return empty summary
        return result

    lines = content.strip().split('\n')

    # Validate ledger format
    is_valid, error_msg = _validate_ledger_format(lines)
    if not is_valid:
        print(f"[cost] Ledger format invalid: {error_msg}", file=sys.stderr, flush=True)
        result["error"] = "ledger format invalid"
        return result

    # Parse each line
    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip header separator lines (all dashes and pipes) — silently, don't count as skipped
        if all(c in '|-' for c in line):
            continue

        # Parse pipe-delimited row
        if not line.startswith('|') or not line.endswith('|'):
            print(f"[cost] Skipping malformed line (no pipe delimiters): {line[:50]}", file=sys.stderr, flush=True)
            result["skipped_lines"] += 1
            continue

        # Split by pipe and strip whitespace
        parts = [p.strip() for p in line.split('|')]

        # Markdown tables have empty strings at start and end after split
        # Format: | col1 | col2 | col3 | col4 | col5 | col6 | col7 |
        # After split: ['', 'col1', 'col2', 'col3', 'col4', 'col5', 'col6', 'col7', '']
        if len(parts) < 9:  # Need at least 9 parts (empty + 7 columns + empty)
            print(f"[cost] Skipping line with too few columns ({len(parts) - 2}): {line[:50]}", file=sys.stderr, flush=True)
            result["skipped_lines"] += 1
            continue

        # Extract columns (skip leading/trailing empty)
        try:
            timestamp = parts[1]  # ISO timestamp
            agent_type = parts[2]  # "Agent"
            model = parts[3]
            duration_str = parts[4]
            tokens_in_str = parts[5]
            tokens_out_str = parts[6]
            verdict = parts[7]
        except IndexError:
            print(f"[cost] Skipping line with missing columns: {line[:50]}", file=sys.stderr, flush=True)
            result["skipped_lines"] += 1
            continue

        # Skip header line if timestamp column contains "timestamp" or "ISO" — silently, don't count as skipped
        if 'timestamp' in timestamp.lower() or 'iso' in timestamp.lower():
            continue

        # Parse numeric fields
        try:
            tokens_in = int(tokens_in_str)
            tokens_out = int(tokens_out_str)
        except ValueError:
            print(f"[cost] Skipping line with non-numeric tokens (in={tokens_in_str}, out={tokens_out_str}): {line[:50]}", file=sys.stderr, flush=True)
            result["skipped_lines"] += 1
            continue

        # Validate verdict
        if verdict not in ("OK", "FAILED", "EMPTY", "HUNG"):
            print(f"[cost] Skipping line with invalid verdict ({verdict}): {line[:50]}", file=sys.stderr, flush=True)
            result["skipped_lines"] += 1
            continue

        # Extract date from ISO timestamp (YYYY-MM-DD)
        try:
            date_str = timestamp.split('T')[0]
        except IndexError:
            print(f"[cost] Skipping line with invalid timestamp format: {line[:50]}", file=sys.stderr, flush=True)
            result["skipped_lines"] += 1
            continue

        # Aggregate by model
        if model not in result["models"]:
            result["models"][model] = {
                "runs": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "verdicts": {"OK": 0, "FAILED": 0, "EMPTY": 0, "HUNG": 0},
            }

        result["models"][model]["runs"] += 1
        result["models"][model]["tokens_in"] += tokens_in
        result["models"][model]["tokens_out"] += tokens_out
        result["models"][model]["verdicts"][verdict] += 1

        # Aggregate by date
        if date_str not in result["daily_totals"]:
            result["daily_totals"][date_str] = {"tokens_in": 0, "tokens_out": 0}

        result["daily_totals"][date_str]["tokens_in"] += tokens_in
        result["daily_totals"][date_str]["tokens_out"] += tokens_out

        # Count for overall scorecard
        result["overall_scorecard"]["total_runs"] += 1
        if verdict == "OK":
            result["overall_scorecard"]["ok_count"] += 1
        elif verdict == "FAILED":
            result["overall_scorecard"]["failed_count"] += 1
        elif verdict == "EMPTY":
            result["overall_scorecard"]["empty_count"] += 1
        elif verdict == "HUNG":
            result["overall_scorecard"]["hung_count"] += 1

    # Calculate rates
    total = result["overall_scorecard"]["total_runs"]
    if total > 0:
        result["overall_scorecard"]["ok_rate"] = result["overall_scorecard"]["ok_count"] / total
        result["overall_scorecard"]["failed_rate"] = result["overall_scorecard"]["failed_count"] / total
        result["overall_scorecard"]["empty_rate"] = result["overall_scorecard"]["empty_count"] / total
        result["overall_scorecard"]["hung_rate"] = result["overall_scorecard"]["hung_count"] / total

    # Load pricing config at call time and compute estimates
    pricing_map = _load_pricing_config()
    if pricing_map:
        result["has_pricing"] = True
        for model, stats in result["models"].items():
            if model in pricing_map:
                pricing = pricing_map[model]
                input_price = pricing.get("input_per_mtok", 0.0)
                output_price = pricing.get("output_per_mtok", 0.0)

                # Calculate costs: (tokens / 1_000_000) * price_per_mtok
                input_cost = (stats["tokens_in"] * input_price) / 1_000_000
                output_cost = (stats["tokens_out"] * output_price) / 1_000_000
                total_cost = input_cost + output_cost

                result["estimates_by_model"][model] = {
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "total_cost": total_cost,
                }

    return result


def _load_pricing_config():
    """Load pricing map from aesop.config.json at call time.

    Returns:
        dict or None: pricing map {model: {input_per_mtok: float, output_per_mtok: float}}
                      or None if no pricing config found.
    """
    # Read config file at call time (not import time)
    config_file = config.CONFIG_FILE

    if not config_file.exists():
        return None

    try:
        with open(config_file, encoding='utf-8') as f:
            config_data = json.load(f)
    except Exception:
        # Graceful: if config read fails, no pricing
        return None

    return config_data.get("pricing", None)
