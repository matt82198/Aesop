#!/usr/bin/env python3
"""Unit tests for eod_sweep.py end-of-day repository health checks."""
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestEodSweep(unittest.TestCase):
    """Test cases for eod_sweep.py repository health verification."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.eod_script = Path(__file__).parent.parent / "tools" / "eod_sweep.py"

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
        """Initialize a git repository for testing."""
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

        # Create initial commit so branch can exist
        (repo_path / "README.md").write_text("# Test\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=str(repo_path),
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(repo_path),
            capture_output=True
        )

    def _run_eod_sweep(self, repos=None, readonly_repos=None, fix_push=False):
        """Run eod_sweep.py with specified repos."""
        cmd = [sys.executable, str(self.eod_script)]

        if repos:
            repos_str = ":".join(str(r) for r in repos)
            cmd.extend(["--repos", repos_str])

        if readonly_repos:
            readonly_str = ":".join(str(r) for r in readonly_repos)
            cmd.extend(["--readonly-repos", readonly_str])

        if fix_push:
            cmd.append("--fix-push")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result

    def test_no_repos_provided(self):
        """Test graceful degradation when no repos provided."""
        result = self._run_eod_sweep()
        self.assertEqual(result.returncode, 0)
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)

    def test_nonexistent_repo(self):
        """Test graceful degradation when repo doesn't exist."""
        nonexistent = Path(self.temp_dir) / "nonexistent"

        result = self._run_eod_sweep([nonexistent])
        # Should report SAFE (non-existent repos are skipped)
        self.assertEqual(result.returncode, 0)
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)

    def test_clean_repo(self):
        """Test clean repository reports SAFE."""
        test_repo = Path(self.temp_dir) / "clean_repo"
        self._init_git_repo(test_repo)

        result = self._run_eod_sweep([test_repo])
        self.assertEqual(result.returncode, 0)
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)

    def test_dirty_working_tree(self):
        """Test repo with uncommitted changes reports AT-RISK."""
        test_repo = Path(self.temp_dir) / "dirty_repo"
        self._init_git_repo(test_repo)

        # Create uncommitted change
        (test_repo / "README.md").write_text("# Modified\n")

        result = self._run_eod_sweep([test_repo])
        self.assertEqual(result.returncode, 1)
        self.assertIn("EOD-SWEEP: AT-RISK", result.stdout)
        self.assertIn("dirty working tree", result.stdout)

    def test_untracked_files_not_in_gitignore(self):
        """Test repo with untracked files (not in .gitignore) reports AT-RISK."""
        test_repo = Path(self.temp_dir) / "untracked_repo"
        self._init_git_repo(test_repo)

        # Create untracked file not in gitignore
        (test_repo / "untracked.txt").write_text("content\n")

        result = self._run_eod_sweep([test_repo])
        self.assertEqual(result.returncode, 1)
        self.assertIn("EOD-SWEEP: AT-RISK", result.stdout)
        self.assertIn("untracked files", result.stdout)

    def test_untracked_files_in_gitignore_ignored(self):
        """Test that untracked files in .gitignore are not flagged."""
        test_repo = Path(self.temp_dir) / "gitignored_repo"
        self._init_git_repo(test_repo)

        # Create .gitignore
        (test_repo / ".gitignore").write_text("*.tmp\n")
        subprocess.run(
            ["git", "add", ".gitignore"],
            cwd=str(test_repo),
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add gitignore"],
            cwd=str(test_repo),
            capture_output=True
        )

        # Create file in gitignore
        (test_repo / "test.tmp").write_text("content\n")

        result = self._run_eod_sweep([test_repo])
        self.assertEqual(result.returncode, 0)
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)

    def test_multiple_repos_all_clean(self):
        """Test multiple repos all clean."""
        repo1 = Path(self.temp_dir) / "repo1"
        repo2 = Path(self.temp_dir) / "repo2"

        self._init_git_repo(repo1)
        self._init_git_repo(repo2)

        result = self._run_eod_sweep([repo1, repo2])
        self.assertEqual(result.returncode, 0)
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)

    def test_multiple_repos_one_dirty(self):
        """Test multiple repos with one dirty."""
        repo1 = Path(self.temp_dir) / "repo1"
        repo2 = Path(self.temp_dir) / "repo2"

        self._init_git_repo(repo1)
        self._init_git_repo(repo2)

        # Make repo2 dirty
        (repo2 / "README.md").write_text("# Modified\n")

        result = self._run_eod_sweep([repo1, repo2])
        self.assertEqual(result.returncode, 1)
        self.assertIn("EOD-SWEEP: AT-RISK", result.stdout)

    def test_output_format_safe(self):
        """Test SAFE output format."""
        test_repo = Path(self.temp_dir) / "test_repo"
        self._init_git_repo(test_repo)

        result = self._run_eod_sweep([test_repo])
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)

    def test_output_format_at_risk_with_count(self):
        """Test AT-RISK output includes finding count."""
        test_repo = Path(self.temp_dir) / "risky_repo"
        self._init_git_repo(test_repo)

        # Create multiple issues
        (test_repo / "README.md").write_text("# Modified\n")  # dirty tree
        (test_repo / "untracked.txt").write_text("content\n")  # untracked

        result = self._run_eod_sweep([test_repo])
        self.assertEqual(result.returncode, 1)
        self.assertIn("AT-RISK", result.stdout)
        # Should mention findings count
        self.assertIn("findings", result.stdout)

    def test_exit_code_zero_on_safe(self):
        """Test exit code is 0 when all repos are safe."""
        test_repo = Path(self.temp_dir) / "test_repo"
        self._init_git_repo(test_repo)

        result = self._run_eod_sweep([test_repo])
        self.assertEqual(result.returncode, 0)

    def test_exit_code_nonzero_on_at_risk(self):
        """Test exit code is 1 when any repo is at-risk."""
        test_repo = Path(self.temp_dir) / "risky_repo"
        self._init_git_repo(test_repo)

        # Make dirty
        (test_repo / "README.md").write_text("# Modified\n")

        result = self._run_eod_sweep([test_repo])
        self.assertEqual(result.returncode, 1)

    def test_readonly_repos_not_modified(self):
        """Test that readonly-repos flag prevents modifications."""
        test_repo = Path(self.temp_dir) / "readonly_repo"
        self._init_git_repo(test_repo)

        result = self._run_eod_sweep(
            repos=[test_repo],
            readonly_repos=[test_repo],
            fix_push=True
        )
        # Should still work, just not auto-push readonly repos
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)

    def test_non_git_directory_skipped(self):
        """Test that non-git directories are gracefully skipped."""
        plain_dir = Path(self.temp_dir) / "plain_dir"
        plain_dir.mkdir()

        result = self._run_eod_sweep([plain_dir])
        # Should report SAFE (non-git repos are skipped)
        self.assertEqual(result.returncode, 0)
        self.assertIn("EOD-SWEEP: SAFE", result.stdout)


if __name__ == "__main__":
    unittest.main()
