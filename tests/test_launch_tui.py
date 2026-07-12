#!/usr/bin/env python3
"""
Tests for launch_tui.py — portable git-bash resolver.
"""

import unittest
from unittest import mock
from pathlib import Path
import sys
import os

# Add parent directory to path so we can import launch_tui
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from launch_tui import resolve_git_bash_path


class TestResolveGitBashPath(unittest.TestCase):
    """Test portable git-bash resolver with priority order."""

    def test_env_var_wins(self):
        """env var AESOP_GIT_BASH should be returned first."""
        env_path = r"C:\Custom\git-bash.exe"
        with mock.patch.dict(os.environ, {"AESOP_GIT_BASH": env_path}):
            with mock.patch("os.path.exists", return_value=True):
                result = resolve_git_bash_path()
                self.assertEqual(result, env_path)

    def test_which_git_bash_second(self):
        """shutil.which('git-bash') should be tried second."""
        which_path = r"C:\SomeLocation\git-bash.exe"
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("shutil.which") as mock_which:
                with mock.patch("os.path.exists", return_value=True):
                    # which('git-bash') succeeds
                    mock_which.side_effect = lambda x: (
                        which_path if x == "git-bash" else None
                    )
                    result = resolve_git_bash_path()
                    self.assertEqual(result, which_path)

    def test_git_derived_third(self):
        """Derive from which('git') -> ../git-bash.exe on Windows."""
        git_path = r"C:\Program Files\Git\cmd\git.exe"
        expected_bash = r"C:\Program Files\Git\git-bash.exe"
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("shutil.which") as mock_which:
                with mock.patch("os.path.exists", return_value=True):
                    # which('git-bash') fails, which('git') succeeds
                    mock_which.side_effect = lambda x: (
                        git_path if x == "git" else None
                    )
                    result = resolve_git_bash_path()
                    # The derived path should be from git_path's parent + git-bash.exe
                    # git_path: C:\Program Files\Git\cmd\git.exe
                    # parent: C:\Program Files\Git\cmd
                    # parent.parent: C:\Program Files\Git
                    # git-bash.exe: C:\Program Files\Git\git-bash.exe
                    self.assertEqual(result, expected_bash)

    def test_default_fallback(self):
        """Default hardcoded path as last resort."""
        default_path = r"C:\Program Files\Git\git-bash.exe"
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch("os.path.exists", return_value=True):
                    result = resolve_git_bash_path()
                    self.assertEqual(result, default_path)

    def test_none_found_error(self):
        """Clear error message when nothing is found."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch("os.path.exists", return_value=False):
                    with self.assertRaises(FileNotFoundError) as cm:
                        resolve_git_bash_path()
                    error_msg = str(cm.exception)
                    # Check that error message is informative
                    self.assertIn("git-bash.exe not found", error_msg)
                    self.assertIn("Tried (in order)", error_msg)
                    # Should include the default fallback path
                    self.assertIn("C:\\Program Files\\Git", error_msg)


if __name__ == "__main__":
    unittest.main()
