#!/usr/bin/env python3
"""Unit tests for buildlog.py BUILDLOG entry appender."""
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestBuildlog(unittest.TestCase):
    """Test cases for buildlog.py append command."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.buildlog_script = Path(__file__).parent.parent / "tools" / "buildlog.py"
        self.state_dir = Path(self.temp_dir) / "state"
        self.repo_dir = Path(self.temp_dir) / "repo"

    def tearDown(self):
        """Clean up temporary directories."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _run_buildlog(self, *args, env_overrides=None):
        """Run buildlog.py with arguments."""
        env = os.environ.copy()
        env["AESOP_STATE_ROOT"] = str(self.state_dir)
        if env_overrides:
            env.update(env_overrides)

        cmd = [sys.executable, str(self.buildlog_script)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.temp_dir,
            env=env
        )
        return result

    def test_append_simple_message(self):
        """Test appending simple message without git HEAD."""
        result = self._run_buildlog("test message")
        self.assertEqual(result.returncode, 0)
        self.assertIn("test message", result.stderr)

        # Verify BUILDLOG.md was created
        buildlog_file = self.state_dir / "BUILDLOG.md"
        self.assertTrue(buildlog_file.exists())

    def test_buildlog_format(self):
        """Test BUILDLOG entry format with timestamp."""
        result = self._run_buildlog("test message")
        self.assertEqual(result.returncode, 0)

        buildlog_file = self.state_dir / "BUILDLOG.md"
        content = buildlog_file.read_text()

        # Should contain header
        self.assertIn("Build Log", content)
        # Should contain formatted entry
        self.assertIn("test message", content)
        self.assertIn("[", content)  # Timestamp brackets

    def test_append_with_git_head_no_repo(self):
        """Test --head flag when repo doesn't exist (graceful degradation)."""
        result = self._run_buildlog("test message", "--head")
        self.assertEqual(result.returncode, 0)
        self.assertIn("test message", result.stderr)
        self.assertIn("(no-repo)", result.stderr)

    def test_idempotent_re_run(self):
        """Test that running twice appends both entries."""
        result1 = self._run_buildlog("message 1")
        self.assertEqual(result1.returncode, 0)

        result2 = self._run_buildlog("message 2")
        self.assertEqual(result2.returncode, 0)

        buildlog_file = self.state_dir / "BUILDLOG.md"
        content = buildlog_file.read_text()

        # Should contain both messages
        self.assertIn("message 1", content)
        self.assertIn("message 2", content)

    def test_append_creates_state_dir(self):
        """Test that append creates state directory if missing."""
        # Don't create state_dir first
        self.assertFalse(self.state_dir.exists())

        result = self._run_buildlog("test message")
        self.assertEqual(result.returncode, 0)

        # State dir should now exist
        self.assertTrue(self.state_dir.exists())
        self.assertTrue((self.state_dir / "BUILDLOG.md").exists())

    def test_custom_state_dir(self):
        """Test --state-dir parameter."""
        custom_state = Path(self.temp_dir) / "custom_state"

        result = self._run_buildlog(
            "test message",
            "--state-dir", str(custom_state)
        )
        self.assertEqual(result.returncode, 0)

        buildlog_file = custom_state / "BUILDLOG.md"
        self.assertTrue(buildlog_file.exists())

    def test_multiline_message(self):
        """Test message with special characters."""
        msg = "Build step: running tests (main branch)"
        result = self._run_buildlog(msg)
        self.assertEqual(result.returncode, 0)

        buildlog_file = self.state_dir / "BUILDLOG.md"
        content = buildlog_file.read_text()
        self.assertIn(msg, content)

    def test_buildlog_header_once(self):
        """Test that BUILDLOG header is not duplicated on multiple appends."""
        self._run_buildlog("message 1")
        self._run_buildlog("message 2")
        self._run_buildlog("message 3")

        buildlog_file = self.state_dir / "BUILDLOG.md"
        content = buildlog_file.read_text()

        # Count headers (should be exactly 1)
        header_count = content.count("Build Log")
        self.assertEqual(header_count, 1)

    def test_entry_timestamp_format(self):
        """Test that entry timestamps match expected format."""
        result = self._run_buildlog("test message")
        self.assertEqual(result.returncode, 0)

        buildlog_file = self.state_dir / "BUILDLOG.md"
        content = buildlog_file.read_text()

        # Check for timestamp format [YYYY-MM-DD HH:MM]
        import re
        pattern = r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]'
        matches = re.findall(pattern, content)
        self.assertGreater(len(matches), 0)


if __name__ == "__main__":
    unittest.main()
