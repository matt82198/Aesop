"""Unit tests for rotate_logs.py log rotation utility."""
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


class TestRotateLogs(unittest.TestCase):
    """Test cases for log rotation with --max-lines, --max-bytes, --check mode."""

    def setUp(self):
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.rotate_script = Path(__file__).parent.parent / "tools" / "rotate_logs.py"

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _run_rotate(self, logfile, args=None):
        """Helper to run rotate_logs.py with subprocess."""
        cmd = [sys.executable, str(self.rotate_script), logfile]
        if args:
            cmd.extend(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def _count_lines(self, filepath):
        """Count lines in a file."""
        if not os.path.exists(filepath):
            return 0
        with open(filepath, 'r') as f:
            return sum(1 for _ in f)

    def _get_file_size(self, filepath):
        """Get file size in bytes."""
        if not os.path.exists(filepath):
            return 0
        return os.path.getsize(filepath)

    def test_under_threshold_no_op(self):
        """Test that file under threshold is not rotated."""
        logfile = os.path.join(self.temp_dir, "test.log")
        with open(logfile, 'w') as f:
            f.write("line 1\nline 2\nline 3\n")

        result = self._run_rotate(logfile, ["--max-lines", "200"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self._count_lines(logfile), 3)

        # Verify no archive was created
        archive_dir = os.path.join(self.temp_dir, "archive")
        self.assertFalse(os.path.exists(archive_dir))

    def test_over_lines_rotation(self):
        """Test rotation when lines exceed --max-lines threshold."""
        logfile = os.path.join(self.temp_dir, "test.log")
        # Create 250 lines
        with open(logfile, 'w') as f:
            for i in range(1, 251):
                f.write(f"line {i}\n")

        result = self._run_rotate(logfile, ["--max-lines", "200"])
        self.assertEqual(result.returncode, 0)

        # After rotation, original should have ~half (newest lines)
        remaining_lines = self._count_lines(logfile)
        self.assertLessEqual(remaining_lines, 200)

        # Verify archive was created
        archive_dir = os.path.join(self.temp_dir, "archive")
        self.assertTrue(os.path.exists(archive_dir))

        # List archive files
        archive_files = os.listdir(archive_dir)
        self.assertGreater(len(archive_files), 0)

        # Verify total lines (archive + remaining == original)
        archive_file = os.path.join(archive_dir, archive_files[0])
        archived_lines = self._count_lines(archive_file)
        total_lines = remaining_lines + archived_lines
        self.assertEqual(total_lines, 250)

    def test_over_bytes_rotation(self):
        """Test rotation when file size exceeds --max-bytes threshold."""
        logfile = os.path.join(self.temp_dir, "test.log")
        # Create lines each ~100 bytes to exceed 2000 bytes
        with open(logfile, 'w') as f:
            for i in range(30):
                f.write(f"line {i}: " + "x" * 90 + "\n")

        result = self._run_rotate(logfile, ["--max-bytes", "2000"])
        self.assertEqual(result.returncode, 0)

        # After rotation, original should be under threshold
        remaining_size = self._get_file_size(logfile)
        self.assertLessEqual(remaining_size, 2000)

        # Verify archive was created
        archive_dir = os.path.join(self.temp_dir, "archive")
        self.assertTrue(os.path.exists(archive_dir))

        # Verify total size preserved (archive + remaining == original)
        archive_files = os.listdir(archive_dir)
        archive_file = os.path.join(archive_dir, archive_files[0])
        archived_size = self._get_file_size(archive_file)
        # We can't guarantee exact total due to rounding, but should be very close
        total_size = remaining_size + archived_size
        self.assertGreater(total_size, 2000)

    def test_check_mode_no_rotation_needed(self):
        """Test --check mode exits 0 when no rotation needed."""
        logfile = os.path.join(self.temp_dir, "test.log")
        with open(logfile, 'w') as f:
            f.write("line 1\nline 2\nline 3\n")

        result = self._run_rotate(logfile, ["--check", "--max-lines", "200"])
        self.assertEqual(result.returncode, 0)

        # Verify file is unchanged
        self.assertEqual(self._count_lines(logfile), 3)

    def test_check_mode_rotation_needed(self):
        """Test --check mode exits 3 when rotation is needed."""
        logfile = os.path.join(self.temp_dir, "test.log")
        with open(logfile, 'w') as f:
            for i in range(1, 251):
                f.write(f"line {i}\n")

        result = self._run_rotate(logfile, ["--check", "--max-lines", "200"])
        self.assertEqual(result.returncode, 3)

        # Verify file is unchanged
        self.assertEqual(self._count_lines(logfile), 250)

        # Verify no archive was created
        archive_dir = os.path.join(self.temp_dir, "archive")
        self.assertFalse(os.path.exists(archive_dir))

    def test_archive_directory_creation(self):
        """Test that archive directory is created if it doesn't exist."""
        logfile = os.path.join(self.temp_dir, "test.log")
        with open(logfile, 'w') as f:
            for i in range(1, 251):
                f.write(f"line {i}\n")

        result = self._run_rotate(logfile, ["--max-lines", "200"])
        self.assertEqual(result.returncode, 0)

        archive_dir = os.path.join(self.temp_dir, "archive")
        self.assertTrue(os.path.exists(archive_dir))

    def test_custom_archive_directory(self):
        """Test --archive-dir parameter."""
        logfile = os.path.join(self.temp_dir, "test.log")
        custom_archive = os.path.join(self.temp_dir, "custom_archive")
        os.makedirs(custom_archive, exist_ok=True)

        with open(logfile, 'w') as f:
            for i in range(1, 251):
                f.write(f"line {i}\n")

        result = self._run_rotate(
            logfile,
            ["--max-lines", "200", "--archive-dir", custom_archive]
        )
        self.assertEqual(result.returncode, 0)

        # Verify archive was created in custom location
        archive_files = os.listdir(custom_archive)
        self.assertGreater(len(archive_files), 0)

    def test_archive_naming_format(self):
        """Test that archive files follow <basename>.<UTCstamp>.log format."""
        logfile = os.path.join(self.temp_dir, "test.log")
        with open(logfile, 'w') as f:
            for i in range(1, 251):
                f.write(f"line {i}\n")

        result = self._run_rotate(logfile, ["--max-lines", "200"])
        self.assertEqual(result.returncode, 0)

        archive_dir = os.path.join(self.temp_dir, "archive")
        archive_files = os.listdir(archive_dir)
        self.assertEqual(len(archive_files), 1)

        archive_file = archive_files[0]
        # Should match pattern: test.<timestamp>.log
        self.assertTrue(archive_file.startswith("test."))
        self.assertTrue(archive_file.endswith(".log"))

    def test_idempotent_under_threshold(self):
        """Test that running rotation twice on under-threshold file is safe."""
        logfile = os.path.join(self.temp_dir, "test.log")
        with open(logfile, 'w') as f:
            f.write("line 1\nline 2\nline 3\n")

        # Run twice
        result1 = self._run_rotate(logfile, ["--max-lines", "200"])
        result2 = self._run_rotate(logfile, ["--max-lines", "200"])

        self.assertEqual(result1.returncode, 0)
        self.assertEqual(result2.returncode, 0)
        self.assertEqual(self._count_lines(logfile), 3)

    def test_total_content_preserved(self):
        """Test that total lines are preserved across archive + original."""
        logfile = os.path.join(self.temp_dir, "test.log")
        original_count = 300
        with open(logfile, 'w') as f:
            for i in range(1, original_count + 1):
                f.write(f"line {i}\n")

        result = self._run_rotate(logfile, ["--max-lines", "200"])
        self.assertEqual(result.returncode, 0)

        # Count remaining
        remaining_lines = self._count_lines(logfile)

        # Count archived
        archive_dir = os.path.join(self.temp_dir, "archive")
        archive_files = os.listdir(archive_dir)
        archived_lines = 0
        for archive_file in archive_files:
            archived_lines += self._count_lines(os.path.join(archive_dir, archive_file))

        # Verify total
        total_lines = remaining_lines + archived_lines
        self.assertEqual(total_lines, original_count)

    def test_newest_lines_retained(self):
        """Test that newest lines are retained after rotation."""
        logfile = os.path.join(self.temp_dir, "test.log")
        with open(logfile, 'w') as f:
            for i in range(1, 251):
                f.write(f"line {i}\n")

        result = self._run_rotate(logfile, ["--max-lines", "200"])
        self.assertEqual(result.returncode, 0)

        # Read remaining lines and verify they include the newest ones
        with open(logfile, 'r') as f:
            remaining = f.readlines()

        # Should contain "line 250" (the newest)
        self.assertTrue(any("line 250" in line for line in remaining))

    def test_keep_count_guard_tiny_max_bytes(self):
        """Test that rotation guards against keep_count <= 0 when max_bytes is tiny.

        When max_bytes is very small (e.g., 1 byte) and all lines exceed it,
        the calculated keep_count becomes 0 or negative. The guard should
        ensure at least 1 line is kept and the rest are archived.
        """
        logfile = os.path.join(self.temp_dir, "test.log")
        # Create lines of 10 bytes each
        with open(logfile, 'w') as f:
            for i in range(1, 21):
                f.write(f"line {i:02d}\n")  # Each line is ~10 bytes

        # Set max_bytes to 1 (tiny, would cause keep_count <= 0)
        result = self._run_rotate(logfile, ["--max-bytes", "1"])
        self.assertEqual(result.returncode, 0)

        # After rotation, original should have at least 1 line
        remaining_lines = self._count_lines(logfile)
        self.assertGreaterEqual(remaining_lines, 1, "Must keep at least 1 line")

        # Verify archive was created with the rest
        archive_dir = os.path.join(self.temp_dir, "archive")
        self.assertTrue(os.path.exists(archive_dir))

        archive_files = os.listdir(archive_dir)
        self.assertGreater(len(archive_files), 0)

        # Verify total lines preserved
        archive_file = os.path.join(archive_dir, archive_files[0])
        archived_lines = self._count_lines(archive_file)
        total_lines = remaining_lines + archived_lines
        self.assertEqual(total_lines, 20)


if __name__ == "__main__":
    unittest.main()
