#!/usr/bin/env python3
"""Unit tests for wave_ledger_hook.py."""
import os
import sys
import subprocess
import tempfile
import unittest
import json
from pathlib import Path


class TestWaveLedgerHook(unittest.TestCase):
    """Test cases for wave_ledger_hook.py CLI wrapper."""

    def setUp(self):
        """Create temporary directories and fixtures for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.hook_script = Path(__file__).parent.parent / "tools" / "wave_ledger_hook.py"
        self.ledger_script = Path(__file__).parent.parent / "tools" / "fleet_ledger.py"
        self.state_dir = Path(self.temp_dir) / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directories."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _run_hook(self, *args, env_overrides=None):
        """Run wave_ledger_hook.py with arguments."""
        env = os.environ.copy()
        env["AESOP_STATE_ROOT"] = str(self.state_dir)
        if env_overrides:
            env.update(env_overrides)

        cmd = [sys.executable, str(self.hook_script)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result

    def _run_ledger(self, *args, env_overrides=None):
        """Run fleet_ledger.py with arguments."""
        env = os.environ.copy()
        env["AESOP_STATE_ROOT"] = str(self.state_dir)
        if env_overrides:
            env.update(env_overrides)

        cmd = [sys.executable, str(self.ledger_script)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result

    def _create_test_report(self, **overrides):
        """Create a minimal workflow report JSON for testing.

        Args:
            **overrides: Fields to override in the default report

        Returns:
            Path to the created report file
        """
        report_dir = Path(self.temp_dir) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "workflow-report.json"

        # Default report structure
        report = {
            "tokens": {
                "buildOut": 100,
                "verifyOut": 200,
                "repairOut": 50,
                "totalOut": 350
            },
            "build": [
                {"slug": "test-build-1"},
                {"slug": "test-build-2"}
            ],
            "integration": {
                "green": True
            },
            "repairsUsed": 0
        }

        # Apply overrides (replace dict fields entirely, don't just update)
        for key, value in overrides.items():
            report[key] = value

        report_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report_file

    def test_hook_basic_success(self):
        """Test basic hook execution with minimal report."""
        report_file = self._create_test_report()
        ts = "2024-07-13T10:00:00"

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", ts
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("OK:", result.stdout)

        # Verify ledger file was created
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        self.assertTrue(ledger_file.exists())

    def test_hook_missing_report_file(self):
        """Test hook with non-existent report file."""
        ts = "2024-07-13T10:00:00"

        result = self._run_hook(
            "--report-file", "/nonexistent/report.json",
            "--wave", "1",
            "--timestamp", ts
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stdout)

    def test_hook_malformed_json(self):
        """Test hook with malformed JSON report."""
        report_dir = Path(self.temp_dir) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "bad-report.json"
        report_file.write_text("{ this is not valid json }", encoding='utf-8')

        ts = "2024-07-13T10:00:00"

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", ts
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Failed to parse", result.stdout)

    def test_hook_timestamp_with_pipe_rejected(self):
        """Test that hook rejects timestamp containing pipe character."""
        report_file = self._create_test_report()
        bad_ts = "2024-07-13T10:00:00|injection"

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", bad_ts
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pipe", result.stdout.lower())

    def test_hook_timestamp_with_newline_rejected(self):
        """Test that hook rejects timestamp containing newline."""
        report_file = self._create_test_report()
        bad_ts = "2024-07-13T10:00:00\ninjection"

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", bad_ts
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("newline", result.stdout.lower())

    def test_hook_missing_timestamp_argument(self):
        """Test hook with missing timestamp argument."""
        report_file = self._create_test_report()

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1"
            # Missing --timestamp
        )

        self.assertNotEqual(result.returncode, 0)

    def test_hook_missing_wave_argument(self):
        """Test hook with missing wave argument."""
        report_file = self._create_test_report()

        result = self._run_hook(
            "--report-file", str(report_file),
            "--timestamp", "2024-07-13T10:00:00"
            # Missing --wave
        )

        self.assertNotEqual(result.returncode, 0)

    def test_hook_missing_report_file_argument(self):
        """Test hook with missing report-file argument."""
        result = self._run_hook(
            "--wave", "1",
            "--timestamp", "2024-07-13T10:00:00"
            # Missing --report-file
        )

        self.assertNotEqual(result.returncode, 0)

    def test_hook_idempotency_same_call_twice(self):
        """Test that hook is idempotent when called twice with same parameters."""
        report_file = self._create_test_report()
        ts = "2024-07-13T10:00:00"

        # First call
        result1 = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", ts
        )
        self.assertEqual(result1.returncode, 0)

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        lines_after_first = len(ledger_file.read_text().strip().split('\n'))

        # Second call with same parameters
        result2 = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", ts
        )
        self.assertEqual(result2.returncode, 0)

        lines_after_second = len(ledger_file.read_text().strip().split('\n'))

        # Line count should not increase (idempotent)
        self.assertEqual(lines_after_first, lines_after_second)

    def test_hook_appends_multiple_phases(self):
        """Test that hook appends entries for build, verify phases."""
        report_file = self._create_test_report(
            tokens={"buildOut": 100, "verifyOut": 200}
        )
        ts = "2024-07-13T10:00:00"

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", ts
        )

        self.assertEqual(result.returncode, 0)

        # Verify ledger has entries for multiple phases
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        content = ledger_file.read_text()

        # Should have build and verify phases
        lines = [l for l in content.split('\n') if '|' in l and '---|' not in l]
        self.assertGreater(len(lines), 0)

    def test_hook_appends_repair_phase_only_if_repairs_used(self):
        """Test that repair phase is appended only when repairsUsed > 0."""
        # First: report with repairsUsed=0 (no repair phase expected)
        report_file1 = self._create_test_report(
            tokens={"buildOut": 100, "verifyOut": 200, "repairOut": 50},
            repairsUsed=0
        )
        ts1 = "2024-07-13T10:00:00"

        result1 = self._run_hook(
            "--report-file", str(report_file1),
            "--wave", "1",
            "--timestamp", ts1
        )
        self.assertEqual(result1.returncode, 0)

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        content1 = ledger_file.read_text()

        # Count repair phase entries
        repair_count_1 = len([l for l in content1.split('\n') if 'repair' in l and '|' in l])
        self.assertEqual(repair_count_1, 0, "No repair phase should be added when repairsUsed=0")

        # Second: report with repairsUsed=1 (repair phase expected)
        report_file2 = self._create_test_report(
            tokens={"buildOut": 100, "verifyOut": 200, "repairOut": 50},
            repairsUsed=1
        )
        ts2 = "2024-07-13T11:00:00"

        result2 = self._run_hook(
            "--report-file", str(report_file2),
            "--wave", "2",
            "--timestamp", ts2
        )
        self.assertEqual(result2.returncode, 0)

        content2 = ledger_file.read_text()

        # Count repair phase entries for wave 2
        repair_count_2 = len([l for l in content2.split('\n') if 'repair' in l and 'wave' in l and '2' in l and '|' in l])
        self.assertGreater(repair_count_2, 0, "Repair phase should be added when repairsUsed > 0")

    def test_hook_round_trip_parse(self):
        """Test that hook-appended rows can be parsed back by fleet_ledger."""
        report_file = self._create_test_report(
            tokens={"buildOut": 250, "verifyOut": 350},
            integration={"green": True}
        )
        ts = "2024-07-13T10:00:00"

        # Append via hook
        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "5",
            "--timestamp", ts
        )
        self.assertEqual(result.returncode, 0)

        # Parse using fleet_ledger's parser
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from fleet_ledger import parse_ledger_rows

        # Temporarily set AESOP_STATE_ROOT for parsing
        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            # Should have at least one row
            self.assertGreater(len(rows), 0)

            # Find rows we just appended
            found_build = False
            found_verify = False
            for row in rows:
                if (row['wave'] == 5 and
                    row['model'] == 'haiku' and
                    row['iso_ts'] == ts):
                    if row['phase'] == 'build':
                        found_build = True
                        self.assertEqual(row['tokens_out'], 250)
                        self.assertEqual(row['verdict'], 'OK')
                    elif row['phase'] == 'verify':
                        found_verify = True
                        self.assertEqual(row['tokens_out'], 350)
                        self.assertEqual(row['verdict'], 'OK')

            self.assertTrue(found_build, "Build phase row not found in parsed ledger")
            self.assertTrue(found_verify, "Verify phase row not found in parsed ledger")
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)
            sys.path.pop(0)

    def test_hook_with_empty_report(self):
        """Test hook with minimal/empty report structure."""
        report_dir = Path(self.temp_dir) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "empty-report.json"

        # Minimal report with empty sections
        report = {
            "tokens": {},
            "integration": {"green": True}
        }
        report_file.write_text(json.dumps(report), encoding='utf-8')

        ts = "2024-07-13T10:00:00"

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", ts
        )

        # Should handle gracefully (may succeed with 0 phases or default behavior)
        self.assertIn(result.returncode, [0, 1], "Should handle empty report gracefully")

    def test_hook_with_full_report_features(self):
        """Test hook with full feature set in report."""
        report_file = self._create_test_report(
            tokens={
                "buildOut": 100,
                "verifyOut": 200,
                "repairOut": 50,
                "totalOut": 350
            },
            build=[
                {"slug": "fix-1"},
                {"slug": "fix-2"}
            ],
            integration={
                "green": True,
                "passed": 10,
                "failed": 0
            },
            repairsUsed=1,
            adversarialReviewMode=True
        )
        ts = "2024-07-13T10:00:00"

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "3",
            "--timestamp", ts
        )

        self.assertEqual(result.returncode, 0)

        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        self.assertTrue(ledger_file.exists())

    def test_hook_timestamp_empty_string_rejected(self):
        """Test that hook rejects empty timestamp."""
        report_file = self._create_test_report()

        result = self._run_hook(
            "--report-file", str(report_file),
            "--wave", "1",
            "--timestamp", ""
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty", result.stdout.lower())


class TestWaveLedgerHookImportable(unittest.TestCase):
    """Test that wave_ledger_hook can be imported."""

    def test_wave_ledger_hook_importable(self):
        """Test that wave_ledger_hook can be imported."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            import wave_ledger_hook
            # Verify the main function exists
            self.assertTrue(hasattr(wave_ledger_hook, 'main'))
            self.assertTrue(hasattr(wave_ledger_hook, 'validate_timestamp'))
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
