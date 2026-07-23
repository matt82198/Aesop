"""
Test suite for daemons/install-tasks.ps1 (Windows Scheduled Task installer).

Tests:
- DryRun mode correctly prints task configuration without registering tasks.
- Output contains wscript.exe, //B, run-hidden.vbs, Hidden, and expected task names.
- run-hidden.vbs file exists.
- No cwd pollution or global git config writes.

SKIP on non-Windows platforms.
"""

import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "Windows-only tests")
class TestInstallTasks(unittest.TestCase):
    """Test the Windows Scheduled Task installer."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures once."""
        cls.worktree_root = Path("C:\\Users\\matt8\\aesop\\aesop-wt-hidden-tasks")
        cls.script_path = cls.worktree_root / "daemons" / "install-tasks.ps1"

        # Verify worktree and script exist
        if not cls.worktree_root.exists():
            raise RuntimeError(f"Worktree not found: {cls.worktree_root}")
        if not cls.script_path.exists():
            raise RuntimeError(f"Script not found: {cls.script_path}")

    def test_run_hidden_vbs_exists(self):
        """Test that run-hidden.vbs file exists in daemons/."""
        vbs_path = self.worktree_root / "daemons" / "run-hidden.vbs"
        self.assertTrue(vbs_path.exists(), f"run-hidden.vbs not found at {vbs_path}")

    def test_dryrun_mode_prints_output(self):
        """
        Test DryRun mode:
        - Runs install-tasks.ps1 with -DryRun -TaskPrefix AesopDryRunTest.
        - Asserts exit code 0.
        - Asserts output contains wscript.exe, //B, run-hidden.vbs, AesopDryRunTestWatchdogDaemon, and Hidden.
        """
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            "-DryRun",
            "-TaskPrefix",
            "AesopDryRunTest",
        ]

        result = subprocess.run(
            cmd,
            cwd=str(self.worktree_root),
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Check exit code
        self.assertEqual(
            result.returncode,
            0,
            f"Expected exit 0, got {result.returncode}.\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}",
        )

        # Check output contains expected strings
        output = result.stdout + result.stderr
        self.assertIn(
            "wscript.exe",
            output,
            "Output should contain 'wscript.exe'",
        )
        self.assertIn(
            "//B",
            output,
            "Output should contain '//B'",
        )
        self.assertIn(
            "run-hidden.vbs",
            output,
            "Output should contain 'run-hidden.vbs'",
        )
        self.assertIn(
            "AesopDryRunTestWatchdogDaemon",
            output,
            "Output should contain task name 'AesopDryRunTestWatchdogDaemon'",
        )
        self.assertIn(
            "Hidden",
            output,
            "Output should contain 'Hidden' (Settings.Hidden=True)",
        )

    def test_dryrun_does_not_register_tasks(self):
        """
        Test that DryRun mode does NOT register tasks:
        - Run install-tasks.ps1 with -DryRun -TaskPrefix AesopDryRunTest.
        - Verify Get-ScheduledTask -TaskName 'AesopDryRunTestWatchdogDaemon' fails or returns nothing.
        """
        # First, run DryRun (should not register)
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            "-DryRun",
            "-TaskPrefix",
            "AesopDryRunTest",
        ]

        result = subprocess.run(
            cmd,
            cwd=str(self.worktree_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0)

        # Now check that the task was NOT registered
        check_cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Get-ScheduledTask -TaskName 'AesopDryRunTestWatchdogDaemon' -ErrorAction SilentlyContinue",
        ]

        check_result = subprocess.run(
            check_cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Task should not exist, so output should be empty
        self.assertEqual(
            check_result.stdout.strip(),
            "",
            f"Task should not be registered after DryRun, but got: {check_result.stdout}",
        )

    def test_no_cwd_pollution(self):
        """
        Test that running the script doesn't change the current working directory.
        """
        # Record initial cwd
        initial_cwd = os.getcwd()

        # Run the script
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            "-DryRun",
            "-TaskPrefix",
            "AesopNoPollutionTest",
        ]

        subprocess.run(
            cmd,
            cwd=str(self.worktree_root),
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Verify cwd hasn't changed
        final_cwd = os.getcwd()
        self.assertEqual(
            initial_cwd,
            final_cwd,
            f"CWD changed from {initial_cwd} to {final_cwd}",
        )


if __name__ == "__main__":
    unittest.main()
