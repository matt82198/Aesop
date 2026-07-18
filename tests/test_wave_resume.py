"""
Tests for tools/wave_resume.py — mid-wave recovery classification.

Test strategy (TDD):
1. load_journal() parses valid .jsonl, skips malformed lines, handles missing files
2. verify_files_exist() checks all files exist under workdir (empty list = true)
3. classify_items() correctly splits completed vs remaining based on journal + file presence
4. CLI: --json flag, human-readable output, exit 0 on success
5. Edge cases: empty journal, missing workdir, duplicate slugs in journal, empty files list

HERMETIC: all tests use tempfile.mkdtemp() fixtures. No test writes to repo root or
state dir. Dummy secrets (if needed) are fragment-assembled at runtime.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO / "tools"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# Import the tool module under test
import wave_resume

WAVE_RESUME_PY = TOOLS_DIR / "wave_resume.py"


class TestWaveResumeLoadJournal(unittest.TestCase):
    """Tests for load_journal() function."""

    def setUp(self):
        """Create temporary directory for fixtures."""
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-wave-resume-test-"))

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def test_load_journal_nonexistent_file(self):
        """load_journal() returns empty list for missing file."""
        result = wave_resume.load_journal(
            str(self.fixture_root / "nonexistent.jsonl")
        )
        self.assertEqual(result, [])

    def test_load_journal_empty_file(self):
        """load_journal() returns empty list for empty file."""
        journal_path = self.fixture_root / "empty.jsonl"
        journal_path.write_text("")

        result = wave_resume.load_journal(str(journal_path))
        self.assertEqual(result, [])

    def test_load_journal_valid_records(self):
        """load_journal() parses valid JSON records."""
        journal_path = self.fixture_root / "journal.jsonl"
        records = [
            {"slug": "item1", "status": "completed", "files": ["out1.txt"]},
            {"slug": "item2", "status": "pending", "files": []},
        ]
        with open(journal_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        result = wave_resume.load_journal(str(journal_path))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["slug"], "item1")
        self.assertEqual(result[1]["slug"], "item2")

    def test_load_journal_skips_malformed_lines(self):
        """load_journal() skips malformed JSON lines."""
        journal_path = self.fixture_root / "journal.jsonl"
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"slug": "item1"}) + "\n")
            f.write("{ not valid json }\n")
            f.write("{ [ }\n")
            f.write(json.dumps({"slug": "item2"}) + "\n")

        result = wave_resume.load_journal(str(journal_path))
        self.assertEqual(len(result), 2)  # Only 2 valid records
        self.assertEqual(result[0]["slug"], "item1")
        self.assertEqual(result[1]["slug"], "item2")

    def test_load_journal_handles_blank_lines(self):
        """load_journal() ignores blank/whitespace-only lines."""
        journal_path = self.fixture_root / "journal.jsonl"
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"slug": "item1"}) + "\n")
            f.write("\n")
            f.write("  \n")
            f.write(json.dumps({"slug": "item2"}) + "\n")

        result = wave_resume.load_journal(str(journal_path))
        self.assertEqual(len(result), 2)

    def test_load_journal_utf8_encoding(self):
        """load_journal() correctly decodes UTF-8."""
        journal_path = self.fixture_root / "journal.jsonl"
        records = [{"slug": "item-café", "status": "completed", "files": []}]
        with open(journal_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        result = wave_resume.load_journal(str(journal_path))
        self.assertEqual(result[0]["slug"], "item-café")


class TestWaveResumeVerifyFilesExist(unittest.TestCase):
    """Tests for verify_files_exist() function."""

    def setUp(self):
        """Create temporary workdir."""
        self.workdir = Path(tempfile.mkdtemp(prefix="aesop-wave-resume-files-"))

    def tearDown(self):
        """Clean up temp workdir."""
        shutil.rmtree(self.workdir, ignore_errors=True)

    def _create_file(self, relative_path: str) -> None:
        """Create a file at relative_path under workdir."""
        file_path = self.workdir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test content")

    def test_verify_files_empty_list(self):
        """verify_files_exist() returns True for empty list."""
        result = wave_resume.verify_files_exist(str(self.workdir), [])
        self.assertTrue(result)

    def test_verify_files_all_exist(self):
        """verify_files_exist() returns True if all files exist."""
        self._create_file("file1.txt")
        self._create_file("subdir/file2.txt")

        result = wave_resume.verify_files_exist(
            str(self.workdir), ["file1.txt", "subdir/file2.txt"]
        )
        self.assertTrue(result)

    def test_verify_files_one_missing(self):
        """verify_files_exist() returns False if any file missing."""
        self._create_file("file1.txt")

        result = wave_resume.verify_files_exist(
            str(self.workdir), ["file1.txt", "missing.txt"]
        )
        self.assertFalse(result)

    def test_verify_files_all_missing(self):
        """verify_files_exist() returns False if all files missing."""
        result = wave_resume.verify_files_exist(
            str(self.workdir), ["missing1.txt", "missing2.txt"]
        )
        self.assertFalse(result)

    def test_verify_files_nested_directories(self):
        """verify_files_exist() handles nested directory paths."""
        self._create_file("a/b/c/deep.txt")

        result = wave_resume.verify_files_exist(str(self.workdir), ["a/b/c/deep.txt"])
        self.assertTrue(result)

    def test_verify_files_nonexistent_workdir(self):
        """verify_files_exist() returns False if workdir doesn't exist."""
        nonexistent = str(self.workdir / "nonexistent")

        result = wave_resume.verify_files_exist(nonexistent, ["file.txt"])
        self.assertFalse(result)


class TestWaveResumeClassifyItems(unittest.TestCase):
    """Tests for classify_items() function."""

    def setUp(self):
        """Create temporary fixtures."""
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-wave-resume-classify-"))
        self.workdir = self.fixture_root / "workdir"
        self.workdir.mkdir(parents=True)

    def tearDown(self):
        """Clean up temp fixtures."""
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def _create_file(self, relative_path: str) -> None:
        """Create a file at relative_path under workdir."""
        file_path = self.workdir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test content")

    def _make_journal(self, records: list) -> list:
        """Return journal records as-is (helper for clarity)."""
        return records

    def test_classify_all_completed_with_files(self):
        """classify_items() marks items completed when files exist."""
        self._create_file("out1.txt")
        self._create_file("out2.txt")

        journal = self._make_journal(
            [
                {"slug": "item1", "status": "completed", "files": ["out1.txt"]},
                {"slug": "item2", "status": "completed", "files": ["out2.txt"]},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertEqual(result["completed"], ["item1", "item2"])
        self.assertEqual(result["remaining"], [])
        self.assertEqual(result["resume_hint"], "All items completed")

    def test_classify_mixed_completed_and_remaining(self):
        """classify_items() correctly splits completed vs remaining."""
        self._create_file("out1.txt")

        journal = self._make_journal(
            [
                {"slug": "item1", "status": "completed", "files": ["out1.txt"]},
                {"slug": "item2", "status": "pending", "files": []},
                {"slug": "item3", "status": "failed", "files": []},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertEqual(result["completed"], ["item1"])
        self.assertIn("item2", result["remaining"])
        self.assertIn("item3", result["remaining"])

    def test_classify_completed_missing_files(self):
        """classify_items() marks as remaining if completed but files missing."""
        journal = self._make_journal(
            [
                {"slug": "item1", "status": "completed", "files": ["missing.txt"]},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertEqual(result["completed"], [])
        self.assertEqual(result["remaining"], ["item1"])

    def test_classify_completed_empty_files_list(self):
        """classify_items() treats completed with empty files as remaining."""
        journal = self._make_journal(
            [
                {"slug": "item1", "status": "completed", "files": []},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertEqual(result["completed"], [])
        self.assertEqual(result["remaining"], ["item1"])

    def test_classify_completed_no_files_field(self):
        """classify_items() treats missing 'files' field as remaining."""
        journal = self._make_journal(
            [
                {"slug": "item1", "status": "completed"},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertEqual(result["completed"], [])
        self.assertEqual(result["remaining"], ["item1"])

    def test_classify_resume_hint_first_remaining(self):
        """classify_items() resume_hint points to first remaining item."""
        journal = self._make_journal(
            [
                {"slug": "item1", "status": "pending"},
                {"slug": "item2", "status": "pending"},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertIn("item1", result["resume_hint"])

    def test_classify_duplicate_slugs_last_wins(self):
        """classify_items() processes each slug once (first occurrence)."""
        self._create_file("out1.txt")

        journal = self._make_journal(
            [
                {"slug": "item1", "status": "completed", "files": ["out1.txt"]},
                # This duplicate is skipped
                {"slug": "item1", "status": "pending", "files": []},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        # First occurrence wins
        self.assertEqual(result["completed"], ["item1"])
        self.assertNotIn("item1", result["remaining"])

    def test_classify_empty_journal(self):
        """classify_items() handles empty journal."""
        result = wave_resume.classify_items([], str(self.workdir))

        self.assertEqual(result["completed"], [])
        self.assertEqual(result["remaining"], [])
        self.assertEqual(result["resume_hint"], "All items completed")

    def test_classify_no_status_field(self):
        """classify_items() treats missing status as non-completed."""
        journal = self._make_journal(
            [
                {"slug": "item1", "files": []},
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertEqual(result["remaining"], ["item1"])

    def test_classify_multiple_files_partial_missing(self):
        """classify_items() marks incomplete if any file is missing."""
        self._create_file("out1.txt")

        journal = self._make_journal(
            [
                {
                    "slug": "item1",
                    "status": "completed",
                    "files": ["out1.txt", "out2.txt"],
                },
            ]
        )

        result = wave_resume.classify_items(journal, str(self.workdir))

        self.assertEqual(result["remaining"], ["item1"])


class TestWaveResumeCLI(unittest.TestCase):
    """Tests for CLI integration."""

    def setUp(self):
        """Create temporary fixtures."""
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-wave-resume-cli-"))
        self.workdir = self.fixture_root / "workdir"
        self.workdir.mkdir(parents=True)

    def tearDown(self):
        """Clean up temp fixtures."""
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def _run_cli(self, *args) -> subprocess.CompletedProcess:
        """Run wave_resume.py via subprocess."""
        env = os.environ.copy()
        return subprocess.run(
            [sys.executable, str(WAVE_RESUME_PY), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def _create_journal(self, records: list) -> str:
        """Create a temporary journal file."""
        journal_path = self.fixture_root / "journal.jsonl"
        with open(journal_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        return str(journal_path)

    def _create_file(self, relative_path: str) -> None:
        """Create a file in workdir."""
        file_path = self.workdir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test")

    def test_cli_requires_journal_and_workdir(self):
        """CLI exits non-zero if --journal or --workdir missing."""
        result = self._run_cli()
        self.assertNotEqual(result.returncode, 0)

        result = self._run_cli("--journal", "j.jsonl")
        self.assertNotEqual(result.returncode, 0)

    def test_cli_human_readable_output(self):
        """CLI defaults to human-readable output."""
        journal_path = self._create_journal(
            [
                {"slug": "item1", "status": "completed", "files": []},
            ]
        )

        result = self._run_cli("--journal", journal_path, "--workdir", str(self.workdir))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Completed:", result.stdout)
        self.assertIn("Remaining:", result.stdout)

    def test_cli_json_output(self):
        """CLI --json outputs valid JSON."""
        self._create_file("out1.txt")
        journal_path = self._create_journal(
            [
                {"slug": "item1", "status": "completed", "files": ["out1.txt"]},
            ]
        )

        result = self._run_cli(
            "--journal", journal_path, "--workdir", str(self.workdir), "--json"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("completed", output)
        self.assertIn("remaining", output)
        self.assertIn("resume_hint", output)
        self.assertEqual(output["completed"], ["item1"])

    def test_cli_nonexistent_journal(self):
        """CLI handles nonexistent journal file gracefully."""
        result = self._run_cli(
            "--journal",
            str(self.fixture_root / "nonexistent.jsonl"),
            "--workdir",
            str(self.workdir),
        )

        # Should still succeed with empty journal
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
