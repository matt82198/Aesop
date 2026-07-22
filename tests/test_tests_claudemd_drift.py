#!/usr/bin/env python3
"""
Test suite: Validate tests/CLAUDE.md suite counts match git ls-files reality.

This drift test ensures the documented counts of test suites in CLAUDE.md
stay synchronized with the actual files in the repo. If this test fails,
it means CLAUDE.md is stale and needs updating.

Gap-centric: Catches drift that would otherwise rot silently.
"""

import re
import subprocess
import tempfile
import os
import unittest


class TestClaudeMdDrift(unittest.TestCase):
    """Validate tests/CLAUDE.md counts vs actual test files."""

    @classmethod
    def setUpClass(cls):
        """Count actual test files once per class."""
        # Use subprocess to count via git ls-files (repo-aware).
        cls.actual_node_count = cls._count_git_files("tests/*.test.mjs")
        cls.actual_shell_count = cls._count_git_files(
            "tests/*.test.sh", "tests/test_*.sh"
        )
        cls.actual_python_count = cls._count_git_files("tests/test_*.py")

    @staticmethod
    def _count_git_files(*patterns):
        """Count files matching patterns using git ls-files (omits untracked)."""
        count = 0
        for pattern in patterns:
            try:
                result = subprocess.run(
                    ["git", "ls-files", pattern],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                count += len([line for line in result.stdout.strip().split("\n") if line])
            except subprocess.CalledProcessError:
                pass
        return count

    def test_claudemd_node_count_matches(self):
        """Node suite count in CLAUDE.md must match actual test files."""
        claudemd_path = os.path.join(
            os.path.dirname(__file__), "CLAUDE.md"
        )
        with open(claudemd_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Match "**Node (N suites)**:" pattern.
        match = re.search(r"\*\*Node \((\d+) suites?\)\*\*:", content)
        self.assertIsNotNone(match, "Could not find '**Node (N suites):**' in CLAUDE.md")

        documented_count = int(match.group(1))
        self.assertEqual(
            documented_count,
            self.actual_node_count,
            f"Node suite count mismatch: CLAUDE.md says {documented_count}, "
            f"but found {self.actual_node_count} actual files. "
            f"Update line 15 in tests/CLAUDE.md.",
        )

    def test_claudemd_shell_count_matches(self):
        """Shell suite count in CLAUDE.md must match actual test files."""
        claudemd_path = os.path.join(
            os.path.dirname(__file__), "CLAUDE.md"
        )
        with open(claudemd_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Match "**Shell (N suites)**:" pattern.
        match = re.search(r"\*\*Shell \((\d+) suites?\)\*\*:", content)
        self.assertIsNotNone(
            match, "Could not find '**Shell (N suites):**' in CLAUDE.md"
        )

        documented_count = int(match.group(1))
        self.assertEqual(
            documented_count,
            self.actual_shell_count,
            f"Shell suite count mismatch: CLAUDE.md says {documented_count}, "
            f"but found {self.actual_shell_count} actual files. "
            f"Update line 11 in tests/CLAUDE.md.",
        )

    def test_claudemd_python_count_matches(self):
        """Python suite count in CLAUDE.md must match actual test files."""
        claudemd_path = os.path.join(
            os.path.dirname(__file__), "CLAUDE.md"
        )
        with open(claudemd_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Match "**Python (N suites)**:" pattern.
        match = re.search(r"\*\*Python \((\d+) suites?\)\*\*:", content)
        self.assertIsNotNone(
            match, "Could not find '**Python (N suites):**' in CLAUDE.md"
        )

        documented_count = int(match.group(1))
        self.assertEqual(
            documented_count,
            self.actual_python_count,
            f"Python suite count mismatch: CLAUDE.md says {documented_count}, "
            f"but found {self.actual_python_count} actual files. "
            f"Update line 19 in tests/CLAUDE.md.",
        )


if __name__ == "__main__":
    unittest.main()
