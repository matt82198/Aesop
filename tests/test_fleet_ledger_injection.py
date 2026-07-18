#!/usr/bin/env python3
"""Unit tests for fleet_ledger.py injection/idempotency vulnerabilities."""
import os
import sys
import subprocess
import tempfile
import unittest
import json
from pathlib import Path


class TestFleetLedgerInjectionTimestamp(unittest.TestCase):
    """Test cases for iso_ts injection vulnerability fix."""

    def setUp(self):
        """Create temporary directories and fixtures for testing."""
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

    def _create_test_report(self, **overrides):
        """Create a minimal workflow report JSON for testing."""
        report_dir = Path(self.temp_dir) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "workflow-report.json"

        report = {
            "tokens": {"buildOut": 100},
            "integration": {"green": True}
        }
        for key, value in overrides.items():
            report[key] = value

        report_file.write_text(json.dumps(report), encoding='utf-8')
        return report_file

    def test_timestamp_pipe_neutralized(self):
        """Test that pipe in timestamp does not inject extra columns."""
        report_file = self._create_test_report()
        malicious_ts = "2024-07-13T10:00:00 | injected_column"

        result = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "1",
            "--phase", "build",
            "--timestamp", malicious_ts
        )

        self.assertEqual(result.returncode, 0)

        # Parse ledger to verify pipe was removed and no extra columns created
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import parse_ledger_rows
        finally:
            sys.path.pop(0)

        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            self.assertGreater(len(rows), 0)

            # Find the row we just appended
            found = False
            for row in rows:
                if row['phase'] == 'build' and row['wave'] == 1:
                    found = True
                    # Verify timestamp has pipe removed (sanitized) - this is the security check
                    self.assertNotIn('|', row['iso_ts'])
                    # Verify the timestamp doesn't match the original malicious input
                    self.assertNotEqual(row['iso_ts'], malicious_ts)
                    break

            self.assertTrue(found, "Appended row not found in parsed ledger")
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)

    def test_timestamp_newline_neutralized(self):
        """Test that newline in timestamp does not inject extra rows."""
        report_file = self._create_test_report()
        malicious_ts = "2024-07-13T10:00:00\n| fake_row | fake_model | 0 | 0 | 0 | FAKE | phase | 99 |"

        result = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "1",
            "--phase", "build",
            "--timestamp", malicious_ts
        )

        self.assertEqual(result.returncode, 0)

        # Parse ledger to verify newline was removed and no extra rows were created
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import parse_ledger_rows
        finally:
            sys.path.pop(0)

        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            # Should have exactly 1 row (no injected fake_row)
            self.assertEqual(len(rows), 1)

            # Verify no "fake_model" was injected
            for row in rows:
                self.assertNotEqual(row['model'], 'fake_model')
                self.assertNotIn('\n', row['iso_ts'])
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)

    def test_timestamp_carriage_return_neutralized(self):
        """Test that carriage return in timestamp is sanitized."""
        report_file = self._create_test_report()
        malicious_ts = "2024-07-13T10:00:00\r\ninjected"

        result = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "1",
            "--phase", "build",
            "--timestamp", malicious_ts
        )

        self.assertEqual(result.returncode, 0)

        # Verify the timestamp has no line-ending characters
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import parse_ledger_rows
        finally:
            sys.path.pop(0)

        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            self.assertEqual(len(rows), 1)
            self.assertNotIn('\r', rows[0]['iso_ts'])
            self.assertNotIn('\n', rows[0]['iso_ts'])
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)


class TestFleetLedgerInjectionIdempotency(unittest.TestCase):
    """Test cases for idempotency bypass vulnerability fix."""

    def setUp(self):
        """Create temporary directories and fixtures for testing."""
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

    def _create_test_report(self, **overrides):
        """Create a minimal workflow report JSON for testing."""
        report_dir = Path(self.temp_dir) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "workflow-report.json"

        report = {
            "tokens": {"buildOut": 100},
            "integration": {"green": True}
        }
        for key, value in overrides.items():
            report[key] = value

        report_file.write_text(json.dumps(report), encoding='utf-8')
        return report_file

    def test_long_phase_no_duplicate_on_retry(self):
        """Test that a phase >15 chars does not create duplicate rows on retry."""
        report_file = self._create_test_report()
        # Phase longer than 15 chars (limit in append_ledger_line)
        long_phase = "verification_step_extended_name"
        ts = "2024-07-13T10:00:00"

        # First append
        result1 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "1",
            "--phase", long_phase,
            "--timestamp", ts
        )
        self.assertEqual(result1.returncode, 0)

        # Get ledger after first append
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        lines_after_first = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # Second append with same parameters (should be idempotent)
        result2 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "1",
            "--phase", long_phase,
            "--timestamp", ts
        )
        self.assertEqual(result2.returncode, 0)
        self.assertIn("already exists", result2.stdout)

        # Get ledger after second append
        lines_after_second = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # No new row should be created (idempotent)
        self.assertEqual(lines_after_first, lines_after_second)

    def test_phase_with_pipe_no_duplicate_on_retry(self):
        """Test that a phase with pipe does not create duplicate rows on retry."""
        report_file = self._create_test_report()
        # Phase with pipe character
        phase_with_pipe = "build|malicious"
        ts = "2024-07-13T10:00:00"

        # First append
        result1 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "2",
            "--phase", phase_with_pipe,
            "--timestamp", ts
        )
        self.assertEqual(result1.returncode, 0)

        # Get ledger after first append
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        lines_after_first = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # Second append with same parameters (should be idempotent)
        result2 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "2",
            "--phase", phase_with_pipe,
            "--timestamp", ts
        )
        self.assertEqual(result2.returncode, 0)
        self.assertIn("already exists", result2.stdout)

        # Get ledger after second append
        lines_after_second = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # No new row should be created (idempotent)
        self.assertEqual(lines_after_first, lines_after_second)

    def test_timestamp_with_pipe_no_duplicate_on_retry(self):
        """Test that a timestamp with pipe does not create duplicate rows on retry."""
        report_file = self._create_test_report()
        # Timestamp with pipe character
        ts_with_pipe = "2024-07-13T10:00:00 | extra_column"

        # First append
        result1 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "3",
            "--phase", "build",
            "--timestamp", ts_with_pipe
        )
        self.assertEqual(result1.returncode, 0)

        # Get ledger after first append
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        lines_after_first = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # Second append with same parameters (should be idempotent)
        result2 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "3",
            "--phase", "build",
            "--timestamp", ts_with_pipe
        )
        self.assertEqual(result2.returncode, 0)
        self.assertIn("already exists", result2.stdout)

        # Get ledger after second append
        lines_after_second = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # No new row should be created (idempotent)
        self.assertEqual(lines_after_first, lines_after_second)

    def test_long_phase_with_pipe_no_duplicate(self):
        """Test that a long phase with pipe does not create duplicates."""
        report_file = self._create_test_report()
        # Both long and contains pipe
        complex_phase = "verification_step_extended_name|malicious"
        ts = "2024-07-13T10:00:00"

        # First append
        result1 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "4",
            "--phase", complex_phase,
            "--timestamp", ts
        )
        self.assertEqual(result1.returncode, 0)

        # Get ledger after first append
        ledger_file = self.state_dir / "ledger" / "OUTCOMES-LEDGER.md"
        lines_after_first = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # Second append with same parameters (should be idempotent)
        result2 = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "4",
            "--phase", complex_phase,
            "--timestamp", ts
        )
        self.assertEqual(result2.returncode, 0)
        self.assertIn("already exists", result2.stdout)

        # Get ledger after second append
        lines_after_second = len([l for l in ledger_file.read_text().split('\n') if l.strip() and '|' in l and '---|' not in l])

        # No new row should be created (idempotent)
        self.assertEqual(lines_after_first, lines_after_second)


class TestFleetLedgerInjectionRoundTrip(unittest.TestCase):
    """Test that injection fixes don't break normal round-trip behavior."""

    def setUp(self):
        """Create temporary directories and fixtures for testing."""
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

    def _create_test_report(self, **overrides):
        """Create a minimal workflow report JSON for testing."""
        report_dir = Path(self.temp_dir) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "workflow-report.json"

        report = {
            "tokens": {"buildOut": 100},
            "integration": {"green": True}
        }
        for key, value in overrides.items():
            report[key] = value

        report_file.write_text(json.dumps(report), encoding='utf-8')
        return report_file

    def test_normal_timestamp_still_works(self):
        """Test that normal clean timestamps still append and round-trip correctly."""
        report_file = self._create_test_report()
        ts = "2024-07-13T10:00:00"

        result = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "5",
            "--phase", "build",
            "--timestamp", ts
        )

        self.assertEqual(result.returncode, 0)

        # Parse and verify round-trip
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import parse_ledger_rows
        finally:
            sys.path.pop(0)

        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            found = False
            for row in rows:
                if row['iso_ts'] == ts and row['wave'] == 5 and row['phase'] == 'build':
                    found = True
                    self.assertEqual(row['tokens_out'], 100)
                    break

            self.assertTrue(found)
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)

    def test_normal_phase_still_works(self):
        """Test that normal phases still append and round-trip correctly."""
        report_file = self._create_test_report(
            tokens={"buildOut": 100, "verifyOut": 200}
        )
        ts = "2024-07-13T10:00:00"
        phase = "verify"

        result = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "6",
            "--phase", phase,
            "--timestamp", ts
        )

        self.assertEqual(result.returncode, 0)

        # Parse and verify round-trip
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import parse_ledger_rows
        finally:
            sys.path.pop(0)

        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            found = False
            for row in rows:
                if row['iso_ts'] == ts and row['wave'] == 6 and row['phase'] == phase:
                    found = True
                    self.assertEqual(row['tokens_out'], 200)
                    break

            self.assertTrue(found)
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)


if __name__ == "__main__":
    unittest.main()
