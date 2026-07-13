#!/usr/bin/env python3
"""Unit tests for ensure_state.py checkpoint scaffolding."""
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestEnsureState(unittest.TestCase):
    """Test cases for ensure_state.py checkpoint scaffolding."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.ensure_state_script = Path(__file__).parent.parent / "tools" / "ensure_state.py"
        self.state_dir = Path(self.temp_dir) / "state"

    def tearDown(self):
        """Clean up temporary directories."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _run_ensure_state(self, state_dir_arg):
        """Run ensure_state.py with --state-dir argument."""
        cmd = [
            sys.executable,
            str(self.ensure_state_script),
            "--state-dir", str(state_dir_arg)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def test_creates_state_directory(self):
        """Test that state directory is created."""
        self.assertFalse(self.state_dir.exists())

        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        self.assertTrue(self.state_dir.exists())

    def test_creates_state_md(self):
        """Test that STATE.md is created."""
        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        state_file = self.state_dir / "STATE.md"
        self.assertTrue(state_file.exists())
        self.assertIn("CREATED STATE.md", result.stdout)

    def test_creates_buildlog_md(self):
        """Test that BUILDLOG.md is created."""
        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        buildlog_file = self.state_dir / "BUILDLOG.md"
        self.assertTrue(buildlog_file.exists())
        self.assertIn("CREATED BUILDLOG.md", result.stdout)

    def test_state_md_content(self):
        """Test STATE.md template content."""
        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        state_file = self.state_dir / "STATE.md"
        content = state_file.read_text()

        # Check for required sections
        self.assertIn("STATE", content)
        self.assertIn("Intent", content)
        self.assertIn("Stack", content)
        self.assertIn("Current status", content)
        self.assertIn("NEXT STEPS", content)

    def test_buildlog_md_content(self):
        """Test BUILDLOG.md has header."""
        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        buildlog_file = self.state_dir / "BUILDLOG.md"
        content = buildlog_file.read_text()

        # Should have header
        self.assertIn("BUILDLOG", content)
        self.assertIn("append-only", content)

    def test_idempotent_rerun(self):
        """Test that running twice doesn't overwrite existing files."""
        # First run
        result1 = self._run_ensure_state(self.state_dir)
        self.assertEqual(result1.returncode, 0)
        self.assertIn("CREATED STATE.md", result1.stdout)

        # Read first version
        state_file = self.state_dir / "STATE.md"
        first_content = state_file.read_text()

        # Wait a moment then run again
        import time
        time.sleep(0.1)

        # Second run
        result2 = self._run_ensure_state(self.state_dir)
        self.assertEqual(result2.returncode, 0)
        self.assertIn("EXISTS STATE.md", result2.stdout)

        # Content should be identical (not overwritten)
        second_content = state_file.read_text()
        self.assertEqual(first_content, second_content)

    def test_partial_existing_files(self):
        """Test when only one file already exists."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Create only STATE.md
        state_file = self.state_dir / "STATE.md"
        state_file.write_text("existing content")

        # Run ensure_state
        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        # STATE.md should still exist and be unchanged
        self.assertEqual(state_file.read_text(), "existing content")
        self.assertIn("EXISTS STATE.md", result.stdout)

        # BUILDLOG.md should be created
        buildlog_file = self.state_dir / "BUILDLOG.md"
        self.assertTrue(buildlog_file.exists())
        self.assertIn("CREATED BUILDLOG.md", result.stdout)

    def test_output_status_created(self):
        """Test output shows CREATED status."""
        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        self.assertIn("CREATED", result.stdout)
        self.assertIn("STATE.md", result.stdout)
        self.assertIn("BUILDLOG.md", result.stdout)

    def test_nested_state_directory(self):
        """Test creating state in nested directory."""
        nested_state = self.state_dir / "nested" / "deep" / "state"

        result = self._run_ensure_state(nested_state)
        self.assertEqual(result.returncode, 0)

        self.assertTrue((nested_state / "STATE.md").exists())
        self.assertTrue((nested_state / "BUILDLOG.md").exists())

    def test_buildlog_has_timestamp(self):
        """Test BUILDLOG.md includes creation timestamp."""
        result = self._run_ensure_state(self.state_dir)
        self.assertEqual(result.returncode, 0)

        buildlog_file = self.state_dir / "BUILDLOG.md"
        content = buildlog_file.read_text()

        # Should contain ISO timestamp line
        import re
        self.assertTrue(re.search(r'\d{4}-\d{2}-\d{2}T', content))


if __name__ == "__main__":
    unittest.main()
