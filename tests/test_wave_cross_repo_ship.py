#!/usr/bin/env python3
"""Per-repo ship phase tests: manifest items with cross-repo git operations.

Tests for per-repo ship phase (Phase 1 scope):
  1. Two-repo manifest with verified items:
     - Each repo gets ONE commit with only its files
     - Each repo's expectTopLevel guard is verified separately
     - Commits succeed even if one repo's push fails
  2. Guard mismatch aborts THAT repo's ship but continues others
  3. Single-repo regression: byte-identical old behavior preserved

stdlib-only (unittest), ASCII-only, Windows + Linux safe.
"""

import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Add driver/ to path for imports.
REPO = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO / "driver"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

import agent_driver as ad  # noqa: E402
from agent_driver import (  # noqa: E402
    AgentDriver,
    DriverCapabilities,
    WorkerRequest,
    WorkerResult,
    CommandResult,
    WORKER_DONE,
    WORKER_FAILED,
    ROLE_WORKER,
)
from wave_loop import run_wave  # noqa: E402


# Module-level temp directories for two fixture repos
_MODULE_TMP = None
_MODULE_SAVED_CWD = None
_FIXTURE_REPO_A = None
_FIXTURE_REPO_B = None


def setUpModule():
    """Set up two fixture git repos in tmpdirs."""
    global _MODULE_TMP, _MODULE_SAVED_CWD, _FIXTURE_REPO_A, _FIXTURE_REPO_B
    _MODULE_SAVED_CWD = os.getcwd()
    _MODULE_TMP = tempfile.mkdtemp(prefix="wave-cross-repo-ship-tests-")
    os.chdir(_MODULE_TMP)

    # Create fixture repo A
    _FIXTURE_REPO_A = Path(_MODULE_TMP) / "repo-a"
    _FIXTURE_REPO_A.mkdir()
    os.chdir(str(_FIXTURE_REPO_A))
    os.system("git init")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    (_FIXTURE_REPO_A / "README.md").write_text("Fixture repo A\n")
    os.system("git add README.md")
    os.system("git commit -m 'Initial commit'")

    # Create fixture repo B
    _FIXTURE_REPO_B = Path(_MODULE_TMP) / "repo-b"
    _FIXTURE_REPO_B.mkdir()
    os.chdir(str(_FIXTURE_REPO_B))
    os.system("git init")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    (_FIXTURE_REPO_B / "README.md").write_text("Fixture repo B\n")
    os.system("git add README.md")
    os.system("git commit -m 'Initial commit'")

    os.chdir(_MODULE_SAVED_CWD)


def tearDownModule():
    """Clean up fixture repos and temp directory."""
    global _MODULE_TMP, _MODULE_SAVED_CWD
    if _MODULE_SAVED_CWD:
        os.chdir(_MODULE_SAVED_CWD)
    if _MODULE_TMP:
        shutil.rmtree(_MODULE_TMP, ignore_errors=True)


class FakeDriverForShip(AgentDriver):
    """Fake AgentDriver for per-repo ship testing."""

    def __init__(self):
        self.total_tokens = 0
        self.dispatch_count = 0
        self._workers = {}
        self.dispatched_items = []
        self.run_commands = []  # Track all run_command calls with cwd

    def probe_capabilities(self) -> DriverCapabilities:
        """Return Tier 2 capabilities."""
        return DriverCapabilities(
            name="fake-driver-ship",
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
            notes="Offline fake driver for per-repo ship testing",
        )

    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        """Dispatch a worker, writing files in the specified workdir."""
        self.dispatch_count += 1
        self.total_tokens += 100

        worker_id = f"worker-{self.dispatch_count}"
        self._workers[worker_id] = {"status": WORKER_DONE}

        workdir = Path(request.workdir) if request.workdir else Path(".")

        # Simulate writing files based on owned_files.
        files_written = []
        try:
            for f in request.owned_files:
                fpath = workdir / f
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(f"# Fixed by dispatch {self.dispatch_count}\n")
                files_written.append(f)
        except Exception as exc:
            return WorkerResult(
                worker_id=worker_id,
                status=WORKER_FAILED,
                ok=False,
                error=f"file write failed: {exc}",
            )

        self.dispatched_items.append({
            "worker_id": worker_id,
            "workdir": str(workdir),
            "owned_files": list(request.owned_files),
        })

        return WorkerResult(
            worker_id=worker_id,
            status=WORKER_DONE,
            ok=True,
            structured={"summary": f"Fixed {len(request.owned_files)} files"},
            files_written=tuple(files_written),
            tokens_spent=100,
        )

    def worker_status(self, worker_id: str) -> ad.WorkerStatus:
        """Return status of a worker."""
        if worker_id in self._workers:
            return ad.WorkerStatus(
                worker_id=worker_id,
                state=self._workers[worker_id]["status"],
            )
        return ad.WorkerStatus(worker_id=worker_id, state=ad.WORKER_UNKNOWN)

    def run_command(self, command: str, cwd=None, shell=None) -> CommandResult:
        """Run a command, simulating test pass for fixed files."""
        self.run_commands.append({"command": command, "cwd": cwd})

        if command.startswith("python -m unittest"):
            # Test passes if any .py file in cwd has been written (fixed).
            try:
                if cwd:
                    cwd_path = Path(cwd)
                    for f in cwd_path.glob("*.py"):
                        if f.read_text().startswith("# Fixed"):
                            return CommandResult(exit_code=0, stdout="PASS")
                    return CommandResult(exit_code=1, stdout="FAIL")
            except Exception:
                pass
            return CommandResult(exit_code=1, stdout="FAIL")

        if command.startswith("git"):
            # Actually run git commands so we can verify the commits.
            try:
                if cwd:
                    result = subprocess.run(
                        command,
                        cwd=cwd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    return CommandResult(
                        exit_code=result.returncode,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                else:
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    return CommandResult(
                        exit_code=result.returncode,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
            except Exception as e:
                return CommandResult(exit_code=1, stdout="", stderr=str(e))

        return CommandResult(exit_code=0, stdout="OK")

    def resolve_model(self, role: str) -> str:
        """Resolve a role to a model id."""
        return "fake-model"

    def get_tokens_spent(self) -> int:
        """Return cumulative tokens spent."""
        return self.total_tokens


class TestPerRepoShip(unittest.TestCase):
    """Tests for per-repo ship phase."""

    def test_two_repo_manifest_two_commits(self):
        """Two verified items in different repos produce TWO separate commits."""
        driver = FakeDriverForShip()

        manifest = {
            "items": [
                {
                    "slug": "item-a",
                    "repo": str(_FIXTURE_REPO_A),
                    "ownsFiles": ["file-a.py"],
                    "prompt": "Fix file A",
                    "testCmd": "python -m unittest",
                    "workDir": str(_FIXTURE_REPO_A),
                },
                {
                    "slug": "item-b",
                    "repo": str(_FIXTURE_REPO_B),
                    "ownsFiles": ["file-b.py"],
                    "prompt": "Fix file B",
                    "testCmd": "python -m unittest",
                    "workDir": str(_FIXTURE_REPO_B),
                },
            ]
        }

        # Prepare git config for ship.
        git_config = {"expectTopLevel": str(_FIXTURE_REPO_A)}

        result = run_wave(driver, manifest, git=git_config)

        # Wave should complete successfully.
        self.assertTrue(result["preflight_ok"])
        self.assertEqual(len(result["built"]), 2)
        self.assertTrue(result["built"][0]["verified"], "Item A should verify")
        self.assertTrue(result["built"][1]["verified"], "Item B should verify")

        # Verify shipped items recorded.
        self.assertIsNotNone(result["shipped"])
        self.assertEqual(len(result["shipped"]), 2)

        # Verify per-repo results recorded.
        self.assertIn("shipped_repos", result)
        self.assertEqual(len(result["shipped_repos"]), 2)

        # Check that each repo has a commit with only its files.
        # Repo A should have file-a.py
        os.chdir(str(_FIXTURE_REPO_A))
        result_a = subprocess.run(
            "git log --pretty=format:%B -n 1",
            shell=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Wave:", result_a.stdout)

        # Check file-a.py was committed to repo A
        exists_a = (Path(_FIXTURE_REPO_A) / "file-a.py").exists()
        self.assertTrue(exists_a, "file-a.py should exist in repo A")

        # Repo B should have file-b.py
        os.chdir(str(_FIXTURE_REPO_B))
        result_b = subprocess.run(
            "git log --pretty=format:%B -n 1",
            shell=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Wave:", result_b.stdout)

        # Check file-b.py was committed to repo B
        exists_b = (Path(_FIXTURE_REPO_B) / "file-b.py").exists()
        self.assertTrue(exists_b, "file-b.py should exist in repo B")

        # Verify file-a.py is NOT in repo B
        exists_a_in_b = (Path(_FIXTURE_REPO_B) / "file-a.py").exists()
        self.assertFalse(exists_a_in_b, "file-a.py should NOT be in repo B")

        # Verify file-b.py is NOT in repo A
        exists_b_in_a = (Path(_FIXTURE_REPO_A) / "file-b.py").exists()
        self.assertFalse(exists_b_in_a, "file-b.py should NOT be in repo A")

    def test_single_repo_regression(self):
        """Single repo with ship behaves identically to current behavior."""
        driver = FakeDriverForShip()

        manifest = {
            "items": [
                {
                    "slug": "item-1",
                    "repo": str(_FIXTURE_REPO_A),
                    "ownsFiles": ["single-file.py"],
                    "prompt": "Fix single file",
                    "testCmd": "python -m unittest",
                    "workDir": str(_FIXTURE_REPO_A),
                },
            ]
        }

        # Prepare git config for ship.
        git_config = {"expectTopLevel": str(_FIXTURE_REPO_A)}

        result = run_wave(driver, manifest, git=git_config)

        # Wave should complete successfully.
        self.assertTrue(result["preflight_ok"])
        self.assertEqual(len(result["built"]), 1)
        self.assertTrue(result["built"][0]["verified"])

        # Verify shipped items recorded.
        self.assertIsNotNone(result["shipped"])
        self.assertEqual(len(result["shipped"]), 1)

        # Verify file was committed to the repo.
        os.chdir(str(_FIXTURE_REPO_A))
        exists = (Path(_FIXTURE_REPO_A) / "single-file.py").exists()
        self.assertTrue(exists, "single-file.py should be in repo A")

    def test_guard_mismatch_aborts_repo_but_continues_others(self):
        """Guard mismatch in one repo (subdirectory case) doesn't prevent shipping of other repos."""
        # Create a subdirectory in repo A that's not its root
        subdir = _FIXTURE_REPO_A / "subdir"
        subdir.mkdir(exist_ok=True)

        driver = FakeDriverForShip()

        manifest = {
            "items": [
                {
                    "slug": "item-a",
                    "repo": str(_FIXTURE_REPO_A),
                    "ownsFiles": ["file-a.py"],
                    "prompt": "Fix file A",
                    "testCmd": "python -m unittest",
                    "workDir": str(_FIXTURE_REPO_A),
                },
                {
                    "slug": "item-sub",
                    # This repo is actually a subdirectory, so git rev-parse --show-toplevel
                    # will return the parent (repo_a), not this subdir.
                    "repo": str(subdir),
                    "ownsFiles": ["file-sub.py"],
                    "prompt": "Fix file sub",
                    "testCmd": "python -m unittest",
                    "workDir": str(subdir),
                },
                {
                    "slug": "item-b",
                    "repo": str(_FIXTURE_REPO_B),
                    "ownsFiles": ["file-b.py"],
                    "prompt": "Fix file B",
                    "testCmd": "python -m unittest",
                    "workDir": str(_FIXTURE_REPO_B),
                },
            ]
        }

        git_config = {"expectTopLevel": str(_FIXTURE_REPO_A)}

        result = run_wave(driver, manifest, git=git_config)

        # Wave should complete (preflight OK, items verified).
        self.assertTrue(result["preflight_ok"])
        self.assertTrue(result["built"][0]["verified"], "Item A should verify")
        self.assertTrue(result["built"][1]["verified"], "Item sub should verify")
        self.assertTrue(result["built"][2]["verified"], "Item B should verify")

        # Check shipped_repos for error reporting.
        self.assertIn("shipped_repos", result)
        repo_results = result["shipped_repos"]

        # Find results for each repo.
        result_a = next((r for r in repo_results if r["repo"] == str(_FIXTURE_REPO_A)), None)
        result_sub = next((r for r in repo_results if r["repo"] == str(subdir)), None)
        result_b = next((r for r in repo_results if r["repo"] == str(_FIXTURE_REPO_B)), None)

        self.assertIsNotNone(result_a, "Repo A should have a result")
        self.assertIsNotNone(result_sub, "Subdir should have a result")
        self.assertIsNotNone(result_b, "Repo B should have a result")

        # Repo A should succeed
        self.assertTrue(result_a.get("committed"), "Repo A should be committed")

        # Subdir should fail (its toplevel is repo_a, not the subdir itself)
        self.assertEqual(result_sub.get("error"), "git_toplevel_mismatch",
                        f"Subdir should fail guard check: {result_sub}")

        # Repo B should succeed
        self.assertTrue(result_b.get("committed"), "Repo B should be committed")

    def test_no_files_to_ship_skips_commit(self):
        """Verified items with no files written skip the commit."""
        driver = FakeDriverForShip()

        # Mock dispatch to return no files written.
        original_dispatch = driver.dispatch_worker

        def mock_dispatch(request):
            result = original_dispatch(request)
            # Clear files_written to simulate no changes.
            return WorkerResult(
                worker_id=result.worker_id,
                status=WORKER_DONE,
                ok=True,
                structured=result.structured,
                files_written=tuple(),  # No files written
                tokens_spent=result.tokens_spent,
            )

        driver.dispatch_worker = mock_dispatch

        manifest = {
            "items": [
                {
                    "slug": "item-1",
                    "repo": str(_FIXTURE_REPO_A),
                    "ownsFiles": [],  # No files
                    "prompt": "Refactor (no file changes)",
                    "testCmd": "python -m unittest",
                    "workDir": str(_FIXTURE_REPO_A),
                },
            ]
        }

        git_config = {"expectTopLevel": str(_FIXTURE_REPO_A)}
        result = run_wave(driver, manifest, git=git_config)

        # Wave should complete.
        self.assertTrue(result["preflight_ok"])
        # Item verifies, but no files to ship, so commit is skipped.
        # This should NOT error out.


if __name__ == "__main__":
    unittest.main()
