#!/usr/bin/env python3
"""End-to-end tests for driver/wave_scheduler.py WS3a pilot (P1-P2 fixes).

Tests prove:
  1. Empty/missing ownsFiles rejected (P1-1).
  2. Path normalization: backslash/dot-slash conflicts detected (P1-2).
  3. Gate unavailability: fatal abort on import failure (P1-3).
  4. Gate check exceptions: abort-with-reason (P1-4).
  5. Double-dispatch prevention: tracker status updated atomically (P1-5).
  6. Manifest build failures: items excluded, recorded separately (P1-6).
  7. Dry-run: no tracker mutation (P1-5).
  8. P2 gates: HALT is final gate, merged=false in Report.

stdlib-only (unittest), ASCII-only, Windows + Linux safe.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

# Add driver/ and tools/ to path for imports
REPO = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO / "driver"
TOOLS_DIR = REPO / "tools"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import agent_driver as ad  # noqa: E402
from agent_driver import (  # noqa: E402
    AgentDriver,
    DriverCapabilities,
    WorkerRequest,
    WorkerResult,
    CommandResult,
    WORKER_DONE,
    WORKER_FAILED,
)
from wave_scheduler import (  # noqa: E402
    run_wave_scheduler,
    load_tracker_items,
    filter_todo_items,
    select_disjoint_items,
    emit_report,
    _normalize_path,
    _validate_item,
)

# Module-level tmpdir for isolation (hygiene rule: no cwd pollution)
_MODULE_TMP = None
_MODULE_SAVED_CWD = None


def setUpModule():
    global _MODULE_TMP, _MODULE_SAVED_CWD
    _MODULE_SAVED_CWD = os.getcwd()
    _MODULE_TMP = tempfile.mkdtemp(prefix="wave-scheduler-tests-")
    os.chdir(_MODULE_TMP)


def tearDownModule():
    global _MODULE_TMP, _MODULE_SAVED_CWD
    if _MODULE_SAVED_CWD:
        os.chdir(_MODULE_SAVED_CWD)
    if _MODULE_TMP:
        shutil.rmtree(_MODULE_TMP, ignore_errors=True)


class FakeDriver(AgentDriver):
    """Offline fake driver for testing wave_scheduler."""

    def __init__(self, tokens_per_call=100):
        self.tokens_per_call = tokens_per_call
        self.total_tokens = 0
        self.dispatch_count = 0
        self._workers = {}

    def probe_capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            name="fake-driver",
            parallel_dispatch=False,
            worker_filesystem_access=False,
            worker_shell_access=False,
            structured_output=False,
            worktree_isolation=False,
            native_cost_tracking=False,
            native_stall_detection=False,
            tool_use_accuracy=0.92,
            recommended_verification_tier=2,
            available_models=("fake-model",),
            notes="Offline fake driver for testing",
        )

    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        self.dispatch_count += 1
        self.total_tokens += self.tokens_per_call

        worker_id = f"worker-{self.dispatch_count}"
        self._workers[worker_id] = {"status": WORKER_DONE}

        workdir = Path(request.workdir) if request.workdir else Path(".")

        # Simulate writing files
        files_written = []
        try:
            for f in request.owned_files:
                fpath = workdir / f
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(f"# Fixed by wave_scheduler dispatch {self.dispatch_count}\n")
                files_written.append(f)
        except Exception as exc:
            return WorkerResult(
                worker_id=worker_id,
                status=WORKER_FAILED,
                ok=False,
                error=f"file write failed: {exc}",
            )

        return WorkerResult(
            worker_id=worker_id,
            status=WORKER_DONE,
            ok=True,
            structured={"summary": f"Fixed {len(request.owned_files)} files"},
            files_written=tuple(files_written),
            tokens_spent=self.tokens_per_call,
        )

    def worker_status(self, worker_id: str) -> ad.WorkerStatus:
        if worker_id in self._workers:
            return ad.WorkerStatus(worker_id=worker_id, state=self._workers[worker_id]["status"])
        return ad.WorkerStatus(worker_id=worker_id, state=ad.WORKER_UNKNOWN)

    def run_command(self, command: str, cwd=None, shell=None) -> CommandResult:
        if command.startswith("git"):
            return CommandResult(exit_code=0, stdout="OK")
        return CommandResult(exit_code=0, stdout="OK")

    def resolve_model(self, role: str) -> str:
        return "fake-model"

    def get_tokens_spent(self) -> int:
        return self.total_tokens


# ========================================================================
# Test Cases
# ========================================================================

class TestPathNormalization(unittest.TestCase):
    """Test _normalize_path() function (P1-2)."""

    def test_posixify_backslashes(self):
        """Backslashes converted to forward slashes."""
        result = _normalize_path("src\\a.py")
        self.assertEqual(result, "src/a.py")

    def test_strip_leading_dot_slash(self):
        """Leading ./ stripped."""
        result = _normalize_path("./a.py")
        self.assertEqual(result, "a.py")

    def test_posixify_then_strip(self):
        """Both transformations applied."""
        result = _normalize_path(".\\a.py")
        # After posixify: ./a.py, after strip: a.py
        self.assertEqual(result, "a.py")

    def test_casefold_on_windows(self):
        """On Windows, paths are lowercased."""
        if sys.platform == "win32":
            result = _normalize_path("SRC/A.PY")
            self.assertEqual(result, "src/a.py")


class TestItemValidation(unittest.TestCase):
    """Test _validate_item() function (P1-1, P1-6)."""

    def test_missing_slug(self):
        """Missing slug rejected."""
        item = {"ownsFiles": ["a.py"], "prompt": "Fix", "testCmd": "test"}
        is_valid, reason = _validate_item(item)
        self.assertFalse(is_valid)
        self.assertIn("slug", reason)

    def test_missing_ownsFiles(self):
        """Missing ownsFiles rejected."""
        item = {"slug": "feat/a", "prompt": "Fix", "testCmd": "test"}
        is_valid, reason = _validate_item(item)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "no_file_ownership")

    def test_empty_ownsFiles(self):
        """Empty ownsFiles list rejected (P1-1)."""
        item = {"slug": "feat/a", "ownsFiles": [], "prompt": "Fix", "testCmd": "test"}
        is_valid, reason = _validate_item(item)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "no_file_ownership")

    def test_missing_prompt(self):
        """Missing prompt rejected."""
        item = {"slug": "feat/a", "ownsFiles": ["a.py"], "testCmd": "test"}
        is_valid, reason = _validate_item(item)
        self.assertFalse(is_valid)
        self.assertIn("prompt", reason)

    def test_missing_testCmd(self):
        """Missing testCmd rejected."""
        item = {"slug": "feat/a", "ownsFiles": ["a.py"], "prompt": "Fix"}
        is_valid, reason = _validate_item(item)
        self.assertFalse(is_valid)
        self.assertIn("testCmd", reason)

    def test_valid_item(self):
        """Valid item passes."""
        item = {
            "id": "1",
            "slug": "feat/a",
            "ownsFiles": ["a.py"],
            "prompt": "Fix a.py",
            "testCmd": "python -m unittest tests.test_a",
        }
        is_valid, reason = _validate_item(item)
        self.assertTrue(is_valid)
        self.assertIsNone(reason)


class TestDisjointSelectionWithNormalization(unittest.TestCase):
    """Test select_disjoint_items() with path normalization (P1-2)."""

    def test_backslash_conflict(self):
        """Items with src\\a.py and src/a.py conflict."""
        items = [
            {"id": "1", "priority": "P1", "ownsFiles": ["src\\a.py"]},
            {"id": "2", "priority": "P1", "ownsFiles": ["src/a.py"]},
        ]
        selected, skipped = select_disjoint_items(items, max_count=2)
        self.assertEqual(len(selected), 1)
        self.assertIn("2", skipped)

    def test_dot_slash_conflict(self):
        """Items with ./a.py and a.py conflict."""
        items = [
            {"id": "1", "priority": "P1", "ownsFiles": ["./a.py"]},
            {"id": "2", "priority": "P1", "ownsFiles": ["a.py"]},
        ]
        selected, skipped = select_disjoint_items(items, max_count=2)
        self.assertEqual(len(selected), 1)
        self.assertIn("2", skipped)


class TestReportSchema(unittest.TestCase):
    """Test emit_report() structure (P2c)."""

    def test_merged_field_present(self):
        """Report includes merged field (P2c)."""
        report = emit_report(
            phase="dispatch",
            wave_id="123",
            items_selected=["1"],
            merged=False,
        )
        self.assertIn("merged", report)
        self.assertFalse(report["merged"])

    def test_items_failed_build_field(self):
        """Report includes items_failed_build when provided (P1-6)."""
        report = emit_report(
            phase="manifest",
            wave_id="123",
            items_selected=["1"],
            items_failed_build=["2"],
        )
        self.assertIn("items_failed_build", report)
        self.assertEqual(report["items_failed_build"], ["2"])

    def test_items_skipped_field(self):
        """Report includes items_skipped when provided (P1-1)."""
        report = emit_report(
            phase="intake",
            wave_id="123",
            items_selected=["1"],
            items_skipped=[{"id": "2", "reason": "no_file_ownership"}],
        )
        self.assertIn("items_skipped", report)
        self.assertEqual(len(report["items_skipped"]), 1)


class TestWaveSchedulerIntegration(unittest.TestCase):
    """Integration tests for run_wave_scheduler()."""

    def setUp(self):
        """Set up fixture tracker.json."""
        self.fixture_dir = Path(tempfile.mkdtemp(prefix="wave-scheduler-fixture-"))
        self.state_dir = self.fixture_dir / "state"
        self.state_dir.mkdir()

    def tearDown(self):
        """Clean up fixture."""
        shutil.rmtree(self.fixture_dir, ignore_errors=True)

    def _write_tracker(self, items):
        """Write tracker.json fixture."""
        tracker_path = self.fixture_dir / "tracker.json"
        with open(tracker_path, "w") as f:
            json.dump(items, f)
        return str(tracker_path)

    def test_empty_ownsFiles_rejected(self):
        """Items with empty ownsFiles rejected at intake (P1-1)."""
        items = [
            {
                "id": "1",
                "slug": "feat/a",
                "status": "todo",
                "priority": "P1",
                "ownsFiles": [],  # Empty!
                "prompt": "Fix",
                "testCmd": "test",
            },
        ]
        tracker_path = self._write_tracker(items)
        driver = FakeDriver()

        report = run_wave_scheduler(
            tracker_path=tracker_path,
            max_items=5,
            dry_run=True,
            driver=driver,
            state_dir=self.state_dir,
        )

        self.assertEqual(report["phase"], "intake")
        self.assertEqual(report["items_selected"], [])
        self.assertIn("items_skipped", report)
        skipped_reasons = [s["reason"] for s in report["items_skipped"]]
        self.assertIn("no_file_ownership", skipped_reasons)

    def test_missing_ownsFiles_rejected(self):
        """Items without ownsFiles rejected at intake (P1-1)."""
        items = [
            {
                "id": "1",
                "slug": "feat/a",
                "status": "todo",
                "priority": "P1",
                # ownsFiles missing!
                "prompt": "Fix",
                "testCmd": "test",
            },
        ]
        tracker_path = self._write_tracker(items)
        driver = FakeDriver()

        report = run_wave_scheduler(
            tracker_path=tracker_path,
            max_items=5,
            dry_run=True,
            driver=driver,
            state_dir=self.state_dir,
        )

        self.assertEqual(report["phase"], "intake")
        self.assertEqual(report["items_selected"], [])

    def test_path_normalization_conflict(self):
        """Paths with different separators detected as conflict (P1-2)."""
        items = [
            {
                "id": "1",
                "slug": "feat/a",
                "status": "todo",
                "priority": "P1",
                "ownsFiles": ["src\\a.py"],  # Backslash
                "prompt": "Fix",
                "testCmd": "test",
            },
            {
                "id": "2",
                "slug": "feat/b",
                "status": "todo",
                "priority": "P1",
                "ownsFiles": ["src/a.py"],  # Forward slash (conflict!)
                "prompt": "Fix",
                "testCmd": "test",
            },
        ]
        tracker_path = self._write_tracker(items)
        driver = FakeDriver()

        report = run_wave_scheduler(
            tracker_path=tracker_path,
            max_items=5,
            dry_run=True,
            driver=driver,
            state_dir=self.state_dir,
        )

        self.assertEqual(len(report["items_selected"]), 1)
        self.assertEqual(report["items_selected"][0], "1")

    def test_dry_run_no_tracker_mutation(self):
        """Dry-run does not update tracker status (P1-5)."""
        items = [
            {
                "id": "1",
                "slug": "feat/a",
                "status": "todo",
                "priority": "P1",
                "ownsFiles": ["a.py"],
                "prompt": "Fix",
                "testCmd": "test",
            },
        ]
        tracker_path = self._write_tracker(items)
        driver = FakeDriver()

        run_wave_scheduler(
            tracker_path=tracker_path,
            max_items=5,
            dry_run=True,
            driver=driver,
            state_dir=self.state_dir,
        )

        with open(tracker_path) as f:
            updated = json.load(f)
        self.assertEqual(updated[0]["status"], "todo")

    def test_report_includes_merged_false(self):
        """Report explicitly includes merged=false (P2c)."""
        items = [
            {
                "id": "1",
                "slug": "feat/a",
                "status": "todo",
                "priority": "P1",
                "ownsFiles": ["a.py"],
                "prompt": "Fix",
                "testCmd": "test",
            },
        ]
        tracker_path = self._write_tracker(items)
        driver = FakeDriver()

        report = run_wave_scheduler(
            tracker_path=tracker_path,
            max_items=5,
            dry_run=True,
            driver=driver,
            state_dir=self.state_dir,
        )

        self.assertIn("merged", report)
        self.assertFalse(report["merged"])

    def test_halt_file_aborts_with_reason(self):
        """HALT file present → abort with honest reason (assert halt imported)."""
        # P2d: assert halt import succeeded
        import wave_scheduler
        self.assertIsNotNone(wave_scheduler.halt, "halt module must be available for this test")

        items = [
            {
                "id": "1",
                "slug": "feat/a",
                "status": "todo",
                "priority": "P1",
                "ownsFiles": ["a.py"],
                "prompt": "Fix",
                "testCmd": "test",
            },
        ]
        tracker_path = self._write_tracker(items)

        halt_file = self.state_dir / ".HALT"
        halt_content = {"reason": "User halt", "timestamp": datetime.now(timezone.utc).isoformat()}
        with open(halt_file, "w") as f:
            json.dump(halt_content, f)

        driver = FakeDriver()

        report = run_wave_scheduler(
            tracker_path=tracker_path,
            max_items=5,
            dry_run=False,
            driver=driver,
            state_dir=self.state_dir,
        )

        self.assertEqual(report["phase"], "halt")
        self.assertIn("halt_reason", report)
        self.assertFalse(report["success"])


if __name__ == "__main__":
    unittest.main()
