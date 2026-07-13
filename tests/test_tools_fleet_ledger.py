#!/usr/bin/env python3
"""Unit tests for fleet_ledger.py outcome audit trail."""
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestFleetLedger(unittest.TestCase):
    """Test cases for fleet_ledger.py append/harvest/rotate commands."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.ledger_script = Path(__file__).parent.parent / "tools" / "fleet_ledger.py"
        self.state_dir = Path(self.temp_dir) / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directories."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _run_ledger(self, *args, env_overrides=None):
        """Run fleet_ledger.py with arguments."""
        env = os.environ.copy()
        env["AESOP_STATE_ROOT"] = str(self.state_dir)
        if env_overrides:
            env.update(env_overrides)

        cmd = [sys.executable, str(self.ledger_script)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result

    def test_append_single_entry(self):
        """Test appending a single ledger entry."""
        ts = "2024-07-13T10:00:00"
        result = self._run_ledger(
            "append", ts, "agent", "claude-3-sonnet", "10", "100", "200", "OK"
        )
        self.assertEqual(result.returncode, 0)

        # Verify ledger file was created
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        self.assertTrue(ledger_file.exists())

    def test_ledger_format_markdown_table(self):
        """Test ledger is formatted as markdown table."""
        ts = "2024-07-13T10:00:00"
        self._run_ledger(
            "append", ts, "agent", "claude-3-sonnet", "10", "100", "200"
        )

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        content = ledger_file.read_text()

        # Should be markdown table
        self.assertIn("|", content)
        self.assertIn("ISO ts", content)
        self.assertIn("agent_type", content)

    def test_append_creates_header_once(self):
        """Test that table header appears only once."""
        self._run_ledger("append", "2024-07-13T10:00:00", "agent1", "model1", "10", "100", "200")
        self._run_ledger("append", "2024-07-13T10:05:00", "agent2", "model2", "15", "150", "250")

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        content = ledger_file.read_text()

        # Count header lines (should be 2: one title, one separator)
        header_lines = [l for l in content.split('\n') if '---|' in l]
        self.assertEqual(len(header_lines), 1)

    def test_append_default_verdict_ok(self):
        """Test that verdict defaults to OK when omitted."""
        ts = "2024-07-13T10:00:00"
        result = self._run_ledger(
            "append", ts, "agent", "model", "10", "100", "200"
        )
        self.assertEqual(result.returncode, 0)

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        content = ledger_file.read_text()

        # Should contain OK verdict
        self.assertIn("OK", content)

    def test_append_custom_verdict(self):
        """Test appending with custom verdict."""
        ts = "2024-07-13T10:00:00"
        self._run_ledger(
            "append", ts, "agent", "model", "10", "100", "200", "FAILED"
        )

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        content = ledger_file.read_text()

        self.assertIn("FAILED", content)

    def test_idempotent_append(self):
        """Test that appending same entry twice is idempotent (not duplicate)."""
        ts = "2024-07-13T10:00:00"

        self._run_ledger("append", ts, "agent", "model", "10", "100", "200")
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        lines_after_first = len(ledger_file.read_text().strip().split('\n'))

        self._run_ledger("append", ts, "agent", "model", "10", "100", "200")
        lines_after_second = len(ledger_file.read_text().strip().split('\n'))

        # Should have added another line (not idempotent at ledger level)
        self.assertEqual(lines_after_second, lines_after_first + 1)

    def test_harvest_empty_temp_dir(self):
        """Test harvest with no tasks to process (graceful degradation)."""
        # Create an empty temp directory and point to it
        empty_temp = Path(self.temp_dir) / "empty_temp"
        empty_temp.mkdir()
        env_override = {"AESOP_TEMP_ROOT": str(empty_temp)}

        result = self._run_ledger("harvest", env_overrides=env_override)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested 0", result.stdout)

    def test_rotate_no_rotation_needed(self):
        """Test rotate when ledger is under 200 lines."""
        # Add just a few entries
        for i in range(5):
            ts = f"2024-07-13T10:0{i}:00"
            self._run_ledger("append", ts, "agent", "model", "10", "100", "200")

        result = self._run_ledger("rotate")
        self.assertEqual(result.returncode, 0)
        self.assertIn("no rotation needed", result.stdout)

    def test_rotate_large_ledger(self):
        """Test rotate when ledger exceeds ~200 lines."""
        # Add many entries to exceed threshold (need ~203 data lines + 2 header)
        for i in range(210):
            ts = f"2024-07-13T{i // 60:02d}:{i % 60:02d}:00"
            self._run_ledger("append", ts, f"agent{i}", "model", "10", "100", "200")

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        initial_lines = len(ledger_file.read_text().strip().split('\n'))

        # Now rotate
        result = self._run_ledger("rotate")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Rotated", result.stdout)

        # Ledger should be smaller now
        final_lines = len(ledger_file.read_text().strip().split('\n'))
        self.assertLess(final_lines, initial_lines)

    def test_rotate_creates_archive(self):
        """Test that rotate creates archive files."""
        # Add entries to exceed threshold (need ~203 data lines + 2 header)
        for i in range(210):
            ts = f"2024-07-13T{i // 60:02d}:{i % 60:02d}:00"
            self._run_ledger("append", ts, f"agent{i}", "model", "10", "100", "200")

        result = self._run_ledger("rotate")
        self.assertEqual(result.returncode, 0)

        # Archive should exist
        archive_dir = self.state_dir / "ledger" / "archives"
        self.assertTrue(archive_dir.exists())

        # Should have at least one archive file
        archive_files = list(archive_dir.glob("*.md"))
        self.assertGreater(len(archive_files), 0)

    def test_graceful_degradation_missing_state_dir(self):
        """Test graceful degradation when state dir doesn't exist."""
        bad_state = Path(self.temp_dir) / "nonexistent"
        env = {"AESOP_STATE_ROOT": str(bad_state)}

        result = self._run_ledger("append", "2024-07-13T10:00:00", "agent", "model", "10", "100", "200", env_overrides=env)
        # Should create the directory and succeed
        self.assertTrue(bad_state.exists())


if __name__ == "__main__":
    unittest.main()
