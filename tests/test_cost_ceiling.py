"""Tests for tools/cost_ceiling.py — the fleet cost ceiling / spend guard.

Test strategy (TDD):
1. Under/at/over ceiling classification (pure function, no side effects)
2. Over-ceiling trips tools/halt.py's .HALT sentinel (in a temp state dir)
3. Under-ceiling never touches the sentinel
4. No ceiling configured (null/absent) -> never trips, always "ok"
5. Spend read from the ledger file when --spent / spent= isn't supplied
6. CLI --check --spent N: exit codes and output

HERMETIC: every test points AESOP_STATE_ROOT at a throwaway tempfile.mkdtemp()
fixture. No test ever writes a real .HALT into the real project state dir.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

COST_CEILING_PY = TOOLS_DIR / "cost_ceiling.py"

ENV_KEYS = ("AESOP_STATE_ROOT", "AESOP_ROOT")


class CostCeilingTestCase(unittest.TestCase):
    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-cost-ceiling-test-"))
        self.state_dir = self.fixture_root / "state"
        self.state_dir.mkdir(parents=True)

        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)
        os.environ.pop("AESOP_ROOT", None)

        for mod in ("cost_ceiling", "halt", "common"):
            sys.modules.pop(mod, None)
        import cost_ceiling
        import halt
        self.cost_ceiling = cost_ceiling
        self.halt = halt

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("cost_ceiling", None)
        sys.modules.pop("halt", None)
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def _write_ledger(self, rows):
        """rows: list of (tokens_in, tokens_out) tuples."""
        ledger_dir = self.state_dir / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger_file = ledger_dir / "OUTCOMES-LEDGER.md"
        header = (
            "| ISO ts | agent_type | model | duration_sec | tokens_in | tokens_out | verdict | phase | wave |\n"
            "|--------|------------|-------|--------------|-----------|------------|--------|-------|------|\n"
        )
        lines = [header]
        for ti, to in rows:
            lines.append(
                f"| 2026-07-16T00:00:00Z | build | haiku | 10 | {ti} | {to} | OK | build | 26 |\n"
            )
        ledger_file.write_text("".join(lines), encoding="utf-8")
        return ledger_file


class TestCeilingClassification(CostCeilingTestCase):
    def test_under_ceiling_not_exceeded(self):
        result = self.cost_ceiling.check(spent=500, period="wave", config={"limits": {"max_wave_tokens": 1000}})
        self.assertFalse(result["exceeded"])
        self.assertFalse(result["tripped"])

    def test_at_ceiling_is_exceeded(self):
        result = self.cost_ceiling.check(spent=1000, period="wave", config={"limits": {"max_wave_tokens": 1000}})
        self.assertTrue(result["exceeded"])

    def test_over_ceiling_is_exceeded(self):
        result = self.cost_ceiling.check(spent=1500, period="wave", config={"limits": {"max_wave_tokens": 1000}})
        self.assertTrue(result["exceeded"])

    def test_no_ceiling_configured_never_exceeded(self):
        result = self.cost_ceiling.check(spent=10_000_000, period="wave", config={"limits": {"max_wave_tokens": None}})
        self.assertFalse(result["exceeded"])
        self.assertFalse(result["tripped"])

    def test_missing_limits_key_never_exceeded(self):
        result = self.cost_ceiling.check(spent=10_000_000, period="wave", config={})
        self.assertFalse(result["exceeded"])

    def test_daily_period_uses_max_daily_tokens(self):
        config = {"limits": {"max_wave_tokens": 100, "max_daily_tokens": 5000}}
        result = self.cost_ceiling.check(spent=200, period="daily", config=config)
        self.assertFalse(result["exceeded"])
        result2 = self.cost_ceiling.check(spent=6000, period="daily", config=config)
        self.assertTrue(result2["exceeded"])


class TestCeilingTripsHalt(CostCeilingTestCase):
    def test_over_ceiling_trips_halt(self):
        self.assertFalse(self.halt.is_halted())
        result = self.cost_ceiling.check(
            spent=2000, period="wave", config={"limits": {"max_wave_tokens": 1000}}
        )
        self.assertTrue(result["tripped"])
        self.assertTrue(self.halt.is_halted())
        info = self.halt.get_halt_info()
        self.assertIn("cost", info["reason"].lower())

    def test_under_ceiling_does_not_trip_halt(self):
        self.cost_ceiling.check(spent=100, period="wave", config={"limits": {"max_wave_tokens": 1000}})
        self.assertFalse(self.halt.is_halted())

    def test_trip_false_disables_side_effect(self):
        result = self.cost_ceiling.check(
            spent=2000, period="wave", config={"limits": {"max_wave_tokens": 1000}}, trip=False
        )
        self.assertTrue(result["exceeded"])
        self.assertFalse(result["tripped"])
        self.assertFalse(self.halt.is_halted())


class TestCeilingLedgerSpend(CostCeilingTestCase):
    def test_spend_read_from_ledger_when_not_supplied(self):
        self._write_ledger([(100, 200), (50, 150)])
        result = self.cost_ceiling.check(period="wave", config={"limits": {"max_wave_tokens": 1000}})
        self.assertEqual(result["spent"], 500)  # 100+200+50+150
        self.assertFalse(result["exceeded"])

    def test_ledger_spend_over_ceiling_trips(self):
        self._write_ledger([(600, 600)])
        result = self.cost_ceiling.check(period="wave", config={"limits": {"max_wave_tokens": 1000}})
        self.assertTrue(result["exceeded"])
        self.assertTrue(self.halt.is_halted())

    def test_missing_ledger_treated_as_zero_spend(self):
        result = self.cost_ceiling.check(period="wave", config={"limits": {"max_wave_tokens": 1000}})
        self.assertEqual(result["spent"], 0)
        self.assertFalse(result["exceeded"])


class TestCeilingCLI(CostCeilingTestCase):
    def _run_cli(self, *args):
        env = os.environ.copy()
        return subprocess.run(
            [sys.executable, str(COST_CEILING_PY), *args],
            capture_output=True, text=True, env=env,
        )

    def _write_config(self, config):
        config_path = self.fixture_root / "aesop.config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return config_path

    def test_cli_under_ceiling_exit_zero(self):
        self._write_config({"limits": {"max_wave_tokens": 1000}})
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, str(COST_CEILING_PY), "--check", "--spent", "100"],
            capture_output=True, text=True, env=env, cwd=str(self.fixture_root),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.halt.is_halted())

    def test_cli_over_ceiling_exit_nonzero_and_trips(self):
        self._write_config({"limits": {"max_wave_tokens": 1000}})
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, str(COST_CEILING_PY), "--check", "--spent", "5000"],
            capture_output=True, text=True, env=env, cwd=str(self.fixture_root),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.halt.is_halted())


if __name__ == "__main__":
    unittest.main()
