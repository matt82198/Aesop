"""
Test suite for tools/stall_check.py — automated silent-hang detection.
"""

import os
import sys
import time
import json
import tempfile
import unittest
from pathlib import Path

# Add tools directory to path so we can import stall_check
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import stall_check


class TestStallCheck(unittest.TestCase):
    """Test suite for stall_check module."""

    def test_scan_transcripts_missing_root(self):
        """Test that missing root directory returns None gracefully."""
        nonexistent = Path("/nonexistent/path/to/transcripts")
        results = stall_check.scan_transcripts(nonexistent, 600)
        self.assertIsNone(results, "Missing root should return None")

    def test_scan_transcripts_empty_dir(self):
        """Test that empty directory returns empty list gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            results = stall_check.scan_transcripts(tmpdir_path, 600)
            self.assertEqual(results, [], "Empty directory should return empty list")

    def test_scan_transcripts_fresh_and_stalled(self):
        """Test that fresh and stalled transcripts are correctly classified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            now = time.time()
            threshold = 600

            # Create a fresh transcript (1 minute old)
            fresh_file = tmpdir_path / "agent-fresh123.jsonl"
            fresh_file.write_text("dummy")
            fresh_mtime = now - 60  # 60 seconds old
            os.utime(fresh_file, (fresh_mtime, fresh_mtime))

            # Create a stalled transcript (20 minutes old)
            stalled_file = tmpdir_path / "agent-stalled456.jsonl"
            stalled_file.write_text("dummy")
            stalled_mtime = now - 1200  # 1200 seconds old
            os.utime(stalled_file, (stalled_mtime, stalled_mtime))

            results = stall_check.scan_transcripts(tmpdir_path, threshold)

            self.assertEqual(len(results), 2, "Should find two transcripts")

            fresh_entry = next((r for r in results if r["agent_id"] == "fresh123"), None)
            stalled_entry = next((r for r in results if r["agent_id"] == "stalled456"), None)

            self.assertIsNotNone(fresh_entry, "Should find fresh transcript")
            self.assertIsNotNone(stalled_entry, "Should find stalled transcript")

            self.assertFalse(fresh_entry["stalled"], "Fresh transcript should not be stalled")
            self.assertTrue(stalled_entry["stalled"], "Stalled transcript should be stalled")

            # Verify age is approximately correct (allow 2-second variance)
            self.assertLessEqual(
                abs(fresh_entry["age_seconds"] - 60),
                2,
                f"Fresh age should be ~60s, got {fresh_entry['age_seconds']}"
            )
            self.assertLessEqual(
                abs(stalled_entry["age_seconds"] - 1200),
                2,
                f"Stalled age should be ~1200s, got {stalled_entry['age_seconds']}"
            )

    def test_scan_transcripts_nested_subdirs(self):
        """Test that nested subdirectories are scanned recursively."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create nested subdirectory
            nested_dir = tmpdir_path / "subdir" / "deep" / "nested"
            nested_dir.mkdir(parents=True, exist_ok=True)

            now = time.time()

            # Create a transcript in nested dir
            nested_file = nested_dir / "agent-nested999.jsonl"
            nested_file.write_text("dummy")
            os.utime(nested_file, (now - 100, now - 100))

            results = stall_check.scan_transcripts(tmpdir_path, 600)

            self.assertEqual(len(results), 1, "Should find nested transcript")
            self.assertEqual(results[0]["agent_id"], "nested999", "Should extract correct agent_id")

    def test_scan_transcripts_exclude_non_matching_files(self):
        """Test that non-agent-*.jsonl files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            now = time.time()

            # Create agent-*.jsonl file
            agent_file = tmpdir_path / "agent-valid.jsonl"
            agent_file.write_text("dummy")
            os.utime(agent_file, (now - 100, now - 100))

            # Create non-matching files
            (tmpdir_path / "other.jsonl").write_text("dummy")
            (tmpdir_path / "agent.txt").write_text("dummy")
            (tmpdir_path / "agent-").write_text("dummy")  # Invalid agent ID

            results = stall_check.scan_transcripts(tmpdir_path, 600)

            self.assertEqual(len(results), 1, "Should only find agent-*.jsonl files")
            self.assertEqual(results[0]["agent_id"], "valid", "Should extract correct agent_id")

    def test_scan_transcripts_json_output_format(self):
        """Test that JSON output contains all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            now = time.time()
            agent_file = tmpdir_path / "agent-test123.jsonl"
            agent_file.write_text("dummy")
            os.utime(agent_file, (now - 100, now - 100))

            results = stall_check.scan_transcripts(tmpdir_path, 600)

            self.assertEqual(len(results), 1)
            entry = results[0]

            # Verify all required fields are present
            self.assertIn("agent_id", entry)
            self.assertIn("age_seconds", entry)
            self.assertIn("stalled", entry)
            self.assertIn("last_mtime", entry)

            # Verify types
            self.assertIsInstance(entry["agent_id"], str)
            self.assertIsInstance(entry["age_seconds"], int)
            self.assertIsInstance(entry["stalled"], bool)
            self.assertIsInstance(entry["last_mtime"], str)

            # Verify ISO format (YYYY-MM-DDTHH:MM:SSZ)
            self.assertIn("T", entry["last_mtime"])
            self.assertIn("Z", entry["last_mtime"])

    def test_threshold_boundary(self):
        """Test that threshold boundary is correctly handled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            now = time.time()
            threshold = 600

            # Create file exactly at threshold
            boundary_file = tmpdir_path / "agent-boundary.jsonl"
            boundary_file.write_text("dummy")
            boundary_mtime = now - threshold
            os.utime(boundary_file, (boundary_mtime, boundary_mtime))

            results = stall_check.scan_transcripts(tmpdir_path, threshold)

            # At exactly threshold, should NOT be stalled (> not >=)
            entry = results[0]
            self.assertFalse(entry["stalled"], "File at exact threshold should not be stalled")

            # Create file just over threshold
            over_file = tmpdir_path / "agent-over.jsonl"
            over_file.write_text("dummy")
            over_mtime = now - threshold - 1
            os.utime(over_file, (over_mtime, over_mtime))

            results = stall_check.scan_transcripts(tmpdir_path, threshold)
            over_entry = next((r for r in results if r["agent_id"] == "over"), None)
            self.assertTrue(over_entry["stalled"], "File just over threshold should be stalled")


if __name__ == "__main__":
    unittest.main()
