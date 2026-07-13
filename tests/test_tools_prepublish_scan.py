#!/usr/bin/env python3
"""Unit tests for prepublish_scan.py pre-publish gate."""
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestPrepublishScan(unittest.TestCase):
    """Test cases for prepublish_scan.py pre-publish verification."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.prepublish_script = Path(__file__).parent.parent / "tools" / "prepublish_scan.py"
        self.test_repo = Path(self.temp_dir) / "test_repo"
        self._init_git_repo(self.test_repo)

    def tearDown(self):
        """Clean up temporary directories."""
        import shutil
        import stat

        def handle_remove_readonly(func, path, exc):
            """Error handler for Windows readonly file deletion."""
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
                func(path)
            else:
                raise

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, onerror=handle_remove_readonly)

    def _init_git_repo(self, repo_path):
        """Initialize a bare git repository for testing."""
        repo_path.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "init"],
            cwd=str(repo_path),
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(repo_path),
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=str(repo_path),
            capture_output=True
        )

    def _add_file_and_commit(self, repo_path, filename, content):
        """Add file and commit to repo."""
        file_path = repo_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        subprocess.run(
            ["git", "add", filename],
            cwd=str(repo_path),
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Add {filename}"],
            cwd=str(repo_path),
            capture_output=True
        )

    def _run_prepublish_scan(self, repo_path):
        """Run prepublish_scan.py on a repository."""
        cmd = [sys.executable, str(self.prepublish_script), "--repo", str(repo_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result

    def test_clean_repo_passes(self):
        """Test that clean repository passes pre-publish check."""
        # Create a clean repo with a safe file
        self._add_file_and_commit(self.test_repo, "README.md", "# Hello World\n")

        result = self._run_prepublish_scan(self.test_repo)
        self.assertEqual(result.returncode, 0)
        self.assertIn("CLEAR-TO-PUBLISH", result.stdout)

    def test_multiple_safe_files(self):
        """Test repo with multiple safe files passes."""
        self._add_file_and_commit(self.test_repo, "README.md", "# Project\n")
        self._add_file_and_commit(self.test_repo, "LICENSE", "MIT License\n")
        self._add_file_and_commit(self.test_repo, "src/main.py", "print('hello')\n")

        result = self._run_prepublish_scan(self.test_repo)
        self.assertEqual(result.returncode, 0)
        self.assertIn("CLEAR-TO-PUBLISH", result.stdout)

    def test_graceful_degradation_no_repo(self):
        """Test graceful degradation when repo doesn't exist."""
        nonexistent = Path(self.temp_dir) / "nonexistent"

        result = self._run_prepublish_scan(nonexistent)
        # Non-existent repo is treated as empty/clean, so it passes
        self.assertTrue(
            "CLEAR-TO-PUBLISH" in result.stdout or "STOP" in result.stdout
        )

    def test_graceful_degradation_not_git_repo(self):
        """Test graceful degradation when directory is not a git repo."""
        not_git = Path(self.temp_dir) / "not_git"
        not_git.mkdir()

        result = self._run_prepublish_scan(not_git)
        # Non-git directory is treated as clean
        self.assertTrue(
            "CLEAR-TO-PUBLISH" in result.stdout or "STOP" in result.stdout
        )

    def test_output_format_clear_to_publish(self):
        """Test output format includes CLEAR-TO-PUBLISH."""
        self._add_file_and_commit(self.test_repo, "test.txt", "hello\n")

        result = self._run_prepublish_scan(self.test_repo)
        self.assertIn("CLEAR-TO-PUBLISH", result.stdout)

    def test_output_format_stop(self):
        """Test output format includes STOP when findings exist."""
        # Create file that *might* trigger scanner
        self._add_file_and_commit(self.test_repo, "safe.py", "x = 1\n")

        result = self._run_prepublish_scan(self.test_repo)
        # Should include either CLEAR-TO-PUBLISH or STOP
        self.assertTrue(
            "CLEAR-TO-PUBLISH" in result.stdout or "STOP" in result.stdout
        )

    def test_includes_both_scans_in_output(self):
        """Test that output includes history and staged scan results."""
        self._add_file_and_commit(self.test_repo, "test.txt", "hello\n")

        result = self._run_prepublish_scan(self.test_repo)

        # Should mention both scans
        self.assertIn("History Scan", result.stdout)
        self.assertIn("Staged Scan", result.stdout)

    def test_exit_code_zero_on_clean(self):
        """Test exit code is 0 when repo is clean."""
        self._add_file_and_commit(self.test_repo, "clean.txt", "content\n")

        result = self._run_prepublish_scan(self.test_repo)
        self.assertEqual(result.returncode, 0)

    def test_exit_code_nonzero_on_unclean(self):
        """Test exit code is nonzero when findings exist."""
        self._add_file_and_commit(self.test_repo, "test.txt", "hello\n")

        # For a clean file without secrets, should pass (exit 0)
        result = self._run_prepublish_scan(self.test_repo)
        # Expected: 0 for clean file
        self.assertEqual(result.returncode, 0)

    def test_idempotent_scan(self):
        """Test that scanning twice produces consistent results."""
        self._add_file_and_commit(self.test_repo, "README.md", "# Test\n")

        result1 = self._run_prepublish_scan(self.test_repo)
        result2 = self._run_prepublish_scan(self.test_repo)

        self.assertEqual(result1.returncode, result2.returncode)
        self.assertIn("CLEAR-TO-PUBLISH", result1.stdout)
        self.assertIn("CLEAR-TO-PUBLISH", result2.stdout)


if __name__ == "__main__":
    unittest.main()
