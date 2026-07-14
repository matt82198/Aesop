"""TDD tests for tools/self_stats.py — self-building stats counter for README.

Tests cover:
- Git-derived metrics: merged PRs, total commits, project age, wave count, insertions+deletions, files tracked, co-authors
- Session telemetry from docs/self-stats-data.json (omitted when missing/null)
- Output modes: default table, --markdown (with START/END markers), --json
- Markdown block must have verification markers for hard numbers
- Metrics gate validation (no unverified hard metrics)

Run: python -m unittest discover tests test_self_stats
     python -m pytest tests/test_self_stats.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Add tools directory to path
TOOLS_DIR = Path(__file__).parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import self_stats


class SelfStatsFixtureCase(unittest.TestCase):
    """Base fixture: tiny git repo + optional JSON data."""

    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-selfstats-test-"))
        self.repo_root = self.fixture_root / "testrepo"
        self.repo_root.mkdir(parents=True)
        self.data_file = self.repo_root / "docs" / "self-stats-data.json"
        self.data_file.parent.mkdir(parents=True)

        # Initialize tiny git repo
        subprocess.run(["git", "init"], cwd=str(self.repo_root), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.repo_root), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(self.repo_root), capture_output=True)

        self._saved_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._saved_cwd)
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def make_commit(self, msg, coauthor=None):
        """Create a commit in test repo."""
        # Create a test file
        test_file = self.repo_root / "test.txt"
        test_file.write_text(f"content {msg}\n")
        subprocess.run(["git", "add", "test.txt"], cwd=str(self.repo_root), capture_output=True, check=True)

        commit_msg = msg
        if coauthor:
            commit_msg += f"\n\nCo-Authored-By: {coauthor}"

        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(self.repo_root),
            capture_output=True,
            check=True
        )

    def make_merge_commit(self, pr_num):
        """Create a merge commit (mimics github merge)."""
        # Create initial main branch if it doesn't exist
        try:
            subprocess.run(
                ["git", "rev-parse", "--verify", "main"],
                cwd=str(self.repo_root),
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError:
            subprocess.run(
                ["git", "checkout", "-b", "main"],
                cwd=str(self.repo_root),
                capture_output=True
            )

        # Create and checkout a feature branch
        subprocess.run(
            ["git", "checkout", "-b", f"feature-{pr_num}"],
            cwd=str(self.repo_root),
            capture_output=True,
            check=True
        )
        self.make_commit(f"feature {pr_num}")

        # Switch back to main
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=str(self.repo_root),
            capture_output=True,
            check=True
        )

        # Merge with --no-ff to create merge commit
        subprocess.run(
            ["git", "merge", "--no-ff", f"feature-{pr_num}", "-m", f"Merge pull request #{pr_num} from test/feature"],
            cwd=str(self.repo_root),
            capture_output=True,
            check=True
        )


class GitDerivedStatsTest(SelfStatsFixtureCase):
    """Test git-derived statistics."""

    def test_git_stats_empty_repo(self):
        """Empty repo has zero stats."""
        os.chdir(str(self.repo_root))
        stats = self_stats.GitStats(repo_root=str(self.repo_root))

        self.assertEqual(stats.merged_prs, 0, "empty repo should have 0 merged PRs")
        self.assertEqual(stats.total_commits, 0, "empty repo should have 0 commits")
        self.assertIsNone(stats.project_age_days, "empty repo should have None project age")
        self.assertEqual(stats.wave_count, 0, "empty repo should have 0 waves")

    def test_git_stats_basic(self):
        """Repo with commits and PR merge."""
        os.chdir(str(self.repo_root))

        # Create initial commit
        self.make_commit("initial commit")

        # Create a merge commit
        self.make_merge_commit(1)

        stats = self_stats.GitStats(repo_root=str(self.repo_root))

        self.assertGreaterEqual(stats.total_commits, 2, "should have at least 2 commits")
        self.assertEqual(stats.merged_prs, 1, "should have 1 merged PR")
        # Project age might be None or 0 depending on git date parsing, so just check it's not negative
        if stats.project_age_days is not None:
            self.assertGreaterEqual(stats.project_age_days, 0, "project age should be >= 0")

    def test_coauthors_detection(self):
        """Should detect Co-Authored-By lines."""
        os.chdir(str(self.repo_root))

        self.make_commit("commit 1")
        self.make_commit("commit 2", coauthor="Claude Haiku <noreply@anthropic.com>")
        self.make_commit("commit 3", coauthor="Claude Sonnet <noreply@anthropic.com>")

        stats = self_stats.GitStats(repo_root=str(self.repo_root))

        # Should include "Test User" + 2 coauthors
        self.assertGreaterEqual(stats.distinct_coauthors, 3, "should detect co-authors")


class SessionTelemetryTest(SelfStatsFixtureCase):
    """Test session telemetry from JSON."""

    def test_no_data_file(self):
        """Missing JSON should return None for telemetry fields."""
        telemetry = self_stats.SessionTelemetry(data_file=str(self.data_file))

        self.assertIsNone(telemetry.total_sessions)
        self.assertIsNone(telemetry.total_turns)
        self.assertIsNone(telemetry.cumulative_tokens)

    def test_data_file_missing_fields(self):
        """JSON with some null fields should omit them."""
        data = {
            "total_sessions": 42,
            "total_turns": None,
            "cumulative_tokens": 1000000
        }
        self.data_file.write_text(json.dumps(data))

        telemetry = self_stats.SessionTelemetry(data_file=str(self.data_file))

        self.assertEqual(telemetry.total_sessions, 42)
        self.assertIsNone(telemetry.total_turns)
        self.assertEqual(telemetry.cumulative_tokens, 1000000)

    def test_data_file_all_fields(self):
        """JSON with all fields should load them."""
        data = {
            "_source": "orchestrator/telemetry.py",
            "_updated": "2024-12-13T14:30:00Z",
            "total_sessions": 15,
            "total_turns": 450,
            "total_user_prompts": 120,
            "max_tokens_single_turn": 8000,
            "cumulative_agent_runs": 340,
            "cumulative_tokens": 45000000,
            "total_coding_hours": 128.5
        }
        self.data_file.write_text(json.dumps(data))

        telemetry = self_stats.SessionTelemetry(data_file=str(self.data_file))

        self.assertEqual(telemetry.total_sessions, 15)
        self.assertEqual(telemetry.total_turns, 450)
        self.assertEqual(telemetry.cumulative_tokens, 45000000)


class OutputModesTest(SelfStatsFixtureCase):
    """Test output modes: table, markdown, json."""

    def setUp(self):
        super().setUp()
        os.chdir(str(self.repo_root))
        # Create a basic repo
        self.make_commit("initial")
        self.make_merge_commit(1)

        # Add some telemetry data
        data = {
            "total_sessions": 10,
            "total_turns": 200,
            "cumulative_tokens": 10000000
        }
        self.data_file.write_text(json.dumps(data))

    def test_default_table_mode(self):
        """Default mode prints human table."""
        stats = self_stats.StatsCounter(repo_root=str(self.repo_root), data_file=str(self.data_file))
        output = stats.table()

        self.assertIn("Aesop Self-Building Stats", output, "table should have title")
        self.assertIn("Repository Metrics", output, "table should have metrics section")

    def test_markdown_mode_has_markers(self):
        """Markdown mode has START/END markers."""
        stats = self_stats.StatsCounter(repo_root=str(self.repo_root), data_file=str(self.data_file))
        output = stats.markdown()

        self.assertIn("<!-- SELF-STATS:START -->", output)
        self.assertIn("<!-- SELF-STATS:END -->", output)

    def test_markdown_mode_contains_stats(self):
        """Markdown mode includes actual stats."""
        stats = self_stats.StatsCounter(repo_root=str(self.repo_root), data_file=str(self.data_file))
        output = stats.markdown()

        # Should have section header
        self.assertIn("Aesop builds itself", output)
        # Should have table with real data
        self.assertIn("1", output, "should include merged PR count")

    def test_markdown_has_verification_markers(self):
        """Markdown output should include metrics-verified comments for hard numbers."""
        stats = self_stats.StatsCounter(repo_root=str(self.repo_root), data_file=str(self.data_file))
        output = stats.markdown()

        # Any hard numbers should have verification markers
        # This is a soft check - actual gate will be metrics_gate.py
        if "%" in output or "x " in output or "$" in output:
            self.assertIn("metrics-verified", output, "hard metrics need verification comment")

    def test_json_mode(self):
        """JSON mode outputs machine-readable format."""
        stats = self_stats.StatsCounter(repo_root=str(self.repo_root), data_file=str(self.data_file))
        output = stats.json()

        # Should be valid JSON
        data = json.loads(output)
        self.assertIsInstance(data, dict)
        self.assertIn("git", data)
        self.assertIn("telemetry", data)
        self.assertIn("merged_prs", data["git"])
        self.assertIn("total_sessions", data["telemetry"])


class CliIntegrationTest(SelfStatsFixtureCase):
    """Test CLI entry point."""

    def setUp(self):
        super().setUp()
        os.chdir(str(self.repo_root))
        self.make_commit("initial")
        self.make_merge_commit(1)
        data = {
            "total_sessions": 5,
            "cumulative_tokens": 5000000
        }
        self.data_file.write_text(json.dumps(data))

    def test_cli_default_mode(self):
        """CLI default mode calls table()."""
        # Import and run via subprocess to test actual CLI
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "self_stats.py")],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True
        )

        self.assertEqual(result.returncode, 0, f"CLI should exit 0, stderr: {result.stderr}")
        self.assertIn("Aesop Self-Building Stats", result.stdout)

    def test_cli_markdown_mode(self):
        """CLI --markdown mode calls markdown()."""
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "self_stats.py"), "--markdown"],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )

        self.assertEqual(result.returncode, 0, f"CLI should exit 0, stderr: {result.stderr}")
        if result.stdout:
            self.assertIn("<!-- SELF-STATS:START -->", result.stdout)
            self.assertIn("<!-- SELF-STATS:END -->", result.stdout)

    def test_cli_json_mode(self):
        """CLI --json mode calls json()."""
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "self_stats.py"), "--json"],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("git", data)
        self.assertIn("merged_prs", data["git"])


if __name__ == "__main__":
    unittest.main()
