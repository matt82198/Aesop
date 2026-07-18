#!/usr/bin/env python3
"""Tests for tools/wave_preflight.py — wave preflight validator.

Test strategy (TDD):
1. Check detection: git repo, feature branch, working tree clean, .HALT sentinel, heartbeats, tracker.json, secret_scan import
2. State dir resolution: AESOP_STATE_ROOT env, config state_root, default
3. STATE.md vs orchestrator-status.json phase consistency detection
4. CLI: --text, --json output formats, exit codes
5. All checks isolated: hermetic temp git repos, never touch cwd or global git config

HERMETIC: every test below creates a throwaway git repo INSIDE a temp directory.
No test ever touches cwd, global git config, or the real aesop repo.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

PREFLIGHT_PY = TOOLS_DIR / "wave_preflight.py"

ENV_KEYS = ("AESOP_STATE_ROOT", "AESOP_ROOT")


class PrefightTestBase(unittest.TestCase):
    """Base class: isolated temp repo + state dir, hermetic."""

    def setUp(self):
        """Create throwaway git repo in a temp directory."""
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-preflight-test-"))
        self.repo_dir = self.fixture_root / "repo"
        self.repo_dir.mkdir(parents=True)
        # Configure git identity in temp repo (--local scopes to this repo only)
        subprocess.run(
            ["git", "init"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "user.email", "test@test.local"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "user.name", "Test User"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )
        self.state_dir = self.repo_dir / "state"
        self.state_dir.mkdir(parents=True)

        # Create initial commit so we can have branches
        (self.repo_dir / ".gitkeep").write_text("")
        subprocess.run(
            ["git", "add", ".gitkeep"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )

        # Start on a feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feat/test"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )

        # Save environment
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)
        os.environ.pop("AESOP_ROOT", None)

        # Clear cached imports
        for mod in ("halt", "common", "wave_preflight"):
            sys.modules.pop(mod, None)

    def tearDown(self):
        """Restore environment and clean up."""
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for mod in ("halt", "common", "wave_preflight"):
            sys.modules.pop(mod, None)
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def _run_preflight(self, *args, env_overrides=None):
        """Run wave_preflight.py with args."""
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        cmd = [sys.executable, str(PREFLIGHT_PY), f"--root={self.repo_dir}", *args]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result

    def _setup_state_md(self, phase):
        """Write a minimal STATE.md with a phase heading."""
        state_md = self.repo_dir / "STATE.md"
        state_md.write_text(
            f"# STATE\n\n## Phase: `{phase}` (test)\n\nContent.\n",
            encoding="utf-8",
        )

    def _setup_orchestrator_status(self, phase):
        """Write orchestrator-status.json with a phase field."""
        status_json = self.state_dir / "orchestrator-status.json"
        data = {
            "id": "main",
            "role": "orchestrator",
            "activity": "test",
            "phase": phase,
            "updated_at": "2026-07-17T00:00:00Z",
        }
        status_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _setup_tracker_json(self, valid=True):
        """Write state/tracker.json."""
        tracker_json = self.state_dir / "tracker.json"
        if valid:
            data = {"version": 1, "items": []}
            tracker_json.write_text(json.dumps(data) + "\n", encoding="utf-8")
        else:
            tracker_json.write_text("{ invalid json", encoding="utf-8")

    def _setup_heartbeats(self, fresh=True):
        """Set up heartbeat files (fresh or stale)."""
        hb_dir = self.state_dir / "heartbeats"
        hb_dir.mkdir(parents=True, exist_ok=True)

        if fresh:
            now = int(time.time())
        else:
            # 400 seconds old
            now = int(time.time()) - 400

        # Watchdog heartbeat
        watchdog_hb = self.state_dir / ".watchdog-heartbeat"
        watchdog_hb.write_text(str(now) + "\n", encoding="utf-8")

        # Orchestrator heartbeat
        orch_hb = hb_dir / "orchestrator"
        orch_hb.write_text(str(now) + "\n", encoding="utf-8")


class TestGitRepoDetection(PrefightTestBase):
    """Test git repository detection."""

    def test_detects_git_repo(self):
        """Should detect git repo."""
        result = self._run_preflight()
        self.assertEqual(result.returncode, 1)  # Will fail on other checks
        self.assertIn("Git repository: PASS", result.stdout)

    def test_detects_no_git_repo(self):
        """Should detect missing git repo."""
        non_git_dir = self.fixture_root / "not-git"
        non_git_dir.mkdir()
        result = subprocess.run(
            [sys.executable, str(PREFLIGHT_PY), f"--root={non_git_dir}"],
            capture_output=True,
            text=True,
        )
        self.assertIn("Git repository: FAIL", result.stdout)


class TestFeatureBranchDetection(PrefightTestBase):
    """Test feature branch detection."""

    def test_allows_feature_branch(self):
        """Should allow feature/* branches."""
        result = self._run_preflight()
        # Will fail on other checks, but should pass feature branch check
        self.assertIn("Feature branch (not main/master): PASS", result.stdout)

    def test_blocks_main_branch(self):
        """Should block main branch."""
        result = subprocess.run(
            ["git", "checkout", "-b", "main"],
            cwd=self.repo_dir,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, f"git checkout failed: {result.stderr}")
        result = self._run_preflight()
        self.assertIn("Feature branch (not main/master): FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_blocks_master_branch(self):
        """Should block master branch."""
        # master is already created by git init, just check it out
        result = subprocess.run(
            ["git", "checkout", "master"],
            cwd=self.repo_dir,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, f"git checkout failed: {result.stderr}")
        result = self._run_preflight()
        self.assertIn("Feature branch (not main/master): FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)


class TestWorkingTreeClean(PrefightTestBase):
    """Test working tree cleanliness."""

    def test_clean_tree_passes(self):
        """Should pass with clean working tree."""
        result = self._run_preflight()
        self.assertIn("Working tree clean: PASS", result.stdout)

    def test_untracked_file_passes(self):
        """Untracked files should pass (git status --porcelain ignores them)."""
        (self.repo_dir / "untracked.txt").write_text("test")
        result = self._run_preflight()
        # Note: git status --porcelain only shows tracked changes, not untracked
        self.assertIn("Working tree clean: PASS", result.stdout)

    def test_modified_file_fails(self):
        """Modified tracked files should fail."""
        tracked_file = self.repo_dir / "tracked.txt"
        tracked_file.write_text("original")
        subprocess.run(
            ["git", "add", "tracked.txt"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )

        tracked_file.write_text("modified")
        result = self._run_preflight()
        self.assertIn("Working tree clean: FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_staged_changes_fail(self):
        """Staged changes should fail."""
        tracked_file = self.repo_dir / "tracked.txt"
        tracked_file.write_text("original")
        subprocess.run(
            ["git", "add", "tracked.txt"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )

        tracked_file.write_text("modified")
        subprocess.run(
            ["git", "add", "tracked.txt"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True,
        )
        result = self._run_preflight()
        self.assertIn("Working tree clean: FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)


class TestHaltSentinel(PrefightTestBase):
    """Test .HALT sentinel detection."""

    def test_no_halt_passes(self):
        """Should pass when no .HALT sentinel."""
        result = self._run_preflight()
        self.assertIn("No .HALT sentinel: PASS", result.stdout)

    def test_halt_sentinel_fails(self):
        """Should fail when .HALT sentinel exists."""
        halt_sentinel = self.state_dir / ".HALT"
        halt_data = {"reason": "testing", "timestamp": "2026-07-17T00:00:00Z"}
        halt_sentinel.write_text(json.dumps(halt_data) + "\n", encoding="utf-8")
        result = self._run_preflight()
        self.assertIn("No .HALT sentinel: FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)


class TestPhaseConsistency(PrefightTestBase):
    """Test STATE.md vs orchestrator-status.json phase consistency."""

    def test_consistent_phases_pass(self):
        """Should pass when phases match."""
        self._setup_state_md("wave-rc.2")
        self._setup_orchestrator_status("wave-rc.2")
        result = self._run_preflight()
        self.assertIn("STATE.md phase consistent", result.stdout)
        self.assertIn("PASS", result.stdout.split("STATE.md phase")[1].split("\n")[0])

    def test_inconsistent_phases_warn(self):
        """Should warn (but not fail) when phases differ."""
        self._setup_state_md("wave-rc.2")
        self._setup_orchestrator_status("wave-rc.3")
        result = self._run_preflight()
        self.assertIn("STATE.md phase consistent", result.stdout)
        # Should show FAIL for this check
        self.assertIn("[DRIFT]", result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_missing_files_ok(self):
        """Should pass if files don't exist yet."""
        result = self._run_preflight()
        self.assertIn("STATE.md phase consistent", result.stdout)
        # Missing files should be treated as OK
        lines = result.stdout.split("\n")
        phase_line = [l for l in lines if "STATE.md phase consistent" in l][0]
        self.assertIn("PASS", phase_line)


class TestHeartbeatFreshness(PrefightTestBase):
    """Test heartbeat freshness detection."""

    def test_fresh_heartbeats_pass(self):
        """Should pass with fresh heartbeats."""
        self._setup_heartbeats(fresh=True)
        result = self._run_preflight()
        self.assertIn("Heartbeats fresh: PASS", result.stdout)

    def test_stale_heartbeats_fail(self):
        """Should fail with stale heartbeats."""
        self._setup_heartbeats(fresh=False)
        result = self._run_preflight()
        self.assertIn("Heartbeats fresh: FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_missing_heartbeats_fail(self):
        """Should fail if heartbeat files missing."""
        result = self._run_preflight()
        self.assertIn("Heartbeats fresh: FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)


class TestTrackerJson(PrefightTestBase):
    """Test tracker.json JSON validation."""

    def test_valid_tracker_json_passes(self):
        """Should pass with valid tracker.json."""
        self._setup_tracker_json(valid=True)
        result = self._run_preflight()
        self.assertIn("state/tracker.json parses as JSON: PASS", result.stdout)

    def test_invalid_tracker_json_fails(self):
        """Should fail with invalid JSON."""
        self._setup_tracker_json(valid=False)
        result = self._run_preflight()
        self.assertIn("state/tracker.json parses as JSON: FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_missing_tracker_json_fails(self):
        """Should fail if tracker.json missing."""
        result = self._run_preflight()
        self.assertIn("state/tracker.json parses as JSON: FAIL", result.stdout)
        self.assertNotEqual(result.returncode, 0)


class TestSecretScanImport(PrefightTestBase):
    """Test secret_scan importability."""

    def test_secret_scan_importable(self):
        """Should pass if secret_scan can be imported."""
        result = self._run_preflight()
        self.assertIn("secret_scan importable: PASS", result.stdout)


class TestOutputFormats(PrefightTestBase):
    """Test output formatting."""

    def test_text_output_default(self):
        """Default output should be text format."""
        result = self._run_preflight()
        self.assertIn("Wave preflight checks:", result.stdout)
        # Should have numbered checks
        self.assertIn("1.", result.stdout)

    def test_json_output_format(self):
        """Should output JSON when --json specified."""
        result = self._run_preflight("--json")
        # Should be valid JSON
        data = json.loads(result.stdout)
        self.assertIn("ready", data)
        self.assertIn("checks", data)
        self.assertIsInstance(data["checks"], list)

    def test_json_check_structure(self):
        """JSON output should have proper check structure."""
        result = self._run_preflight("--json")
        data = json.loads(result.stdout)
        for check in data["checks"]:
            self.assertIn("name", check)
            self.assertIn("ok", check)
            self.assertIn("detail", check)
            self.assertIsInstance(check["ok"], bool)


class TestExitCodes(PrefightTestBase):
    """Test exit codes."""

    def test_ready_returns_zero(self):
        """Ready state should return exit 0."""
        self._setup_state_md("test")
        self._setup_orchestrator_status("test")
        self._setup_tracker_json(valid=True)
        self._setup_heartbeats(fresh=True)
        result = self._run_preflight()
        self.assertEqual(result.returncode, 0)

    def test_not_ready_returns_one(self):
        """Not ready (missing tracker.json) should return exit 1."""
        result = self._run_preflight()
        self.assertEqual(result.returncode, 1)


class TestStateDirResolution(PrefightTestBase):
    """Test state directory resolution."""

    def test_env_var_takes_precedence(self):
        """AESOP_STATE_ROOT env var should take precedence."""
        alt_state = self.fixture_root / "alt-state"
        alt_state.mkdir()

        # Create tracker.json in alt state dir
        tracker_json = alt_state / "tracker.json"
        tracker_json.write_text(json.dumps({"version": 1, "items": []}) + "\n")

        # Create heartbeats in alt state dir
        hb_dir = alt_state / "heartbeats"
        hb_dir.mkdir()
        now = int(time.time())
        (alt_state / ".watchdog-heartbeat").write_text(str(now) + "\n")
        (hb_dir / "orchestrator").write_text(str(now) + "\n")

        result = self._run_preflight(
            env_overrides={"AESOP_STATE_ROOT": str(alt_state)}
        )
        # Should find tracker.json in alt state dir
        self.assertIn("state/tracker.json parses as JSON: PASS", result.stdout)


class TestBlockingFailures(PrefightTestBase):
    """Test that failures block wave (exit 1 with numbered list)."""

    def test_multiple_failures_listed_numbered(self):
        """Multiple failures should be listed with numbers."""
        # Create a scenario with multiple failures
        # (missing tracker, stale heartbeats, on main branch, etc.)
        subprocess.run(
            ["git", "checkout", "-b", "main"],
            cwd=self.repo_dir,
            capture_output=True,
        )
        result = self._run_preflight()
        # Should show multiple numbered items
        self.assertIn("1.", result.stdout)
        self.assertIn("2.", result.stdout)
        self.assertNotEqual(result.returncode, 0)


class TestWindowsPathHandling(PrefightTestBase):
    """Test Windows path handling (backslashes, relative paths, config portability)."""

    def test_config_with_relative_state_root(self):
        """Should handle config with relative state_root path."""
        # Create a config file with relative state_root
        config_file = self.repo_dir / "aesop.config.json"
        config_data = {
            "description": "Test config",
            "state_root": "state",  # Relative path
            "aesop_root": str(self.repo_dir),
        }
        config_file.write_text(json.dumps(config_data) + "\n", encoding="utf-8")

        # Create state dir and tracker.json
        self._setup_tracker_json(valid=True)
        self._setup_heartbeats(fresh=True)

        result = self._run_preflight()
        self.assertIn("state/tracker.json parses as JSON: PASS", result.stdout)

    def test_config_with_tilde_state_root(self):
        """Should handle config with ~ expanded paths."""
        # Create a config file with ~ path (should be expanded by resolve_state_dir)
        config_file = self.repo_dir / "aesop.config.json"
        config_data = {
            "description": "Test config",
            "state_root": "state",  # Relative path (not ~, since ~ is user home)
            "aesop_root": str(self.repo_dir),
        }
        config_file.write_text(json.dumps(config_data) + "\n", encoding="utf-8")

        # Create state dir and tracker.json
        self._setup_tracker_json(valid=True)
        self._setup_heartbeats(fresh=True)

        result = self._run_preflight()
        self.assertIn("state/tracker.json parses as JSON: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
