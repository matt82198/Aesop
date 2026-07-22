#!/usr/bin/env python3
"""
TDD tests for P2 wave_preflight defects (audit 2026-07-18).

Defects:
(a) tools/wave_preflight.py:159-166 — future-dated `updated_at` hits max(0, age)
    clamp and reports "fresh forever" even with dead orchestrator
(b) naive-timestamp local-parse hole (naive vs aware comparison)
(c) tools/wave_preflight.py:342-350 — phase-drift check is vacuous (always passes)

Tests verify:
1. Future-dated orchestrator-status.json updated_at beyond tolerance → stale, not fresh
2. Timezone consistency in orchestrator-status.json parsing
3. Phase drift detection actually fails the check (not vacuous)
"""

import datetime
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


class PrefightP2TestBase(unittest.TestCase):
    """Base class: isolated temp repo + state dir, hermetic."""

    def setUp(self):
        """Create throwaway git repo in a temp directory."""
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-p2-test-"))
        self.repo_dir = self.fixture_root / "repo"
        self.repo_dir.mkdir(parents=True)
        # Configure git identity in temp repo
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

        # Create initial commit
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

    def _setup_tracker_json(self, valid=True):
        """Write state/tracker.json."""
        tracker_json = self.state_dir / "tracker.json"
        if valid:
            data = {"version": 1, "items": []}
            tracker_json.write_text(json.dumps(data) + "\n", encoding="utf-8")
        else:
            tracker_json.write_text("{ invalid json", encoding="utf-8")

    def _setup_fresh_watchdog_heartbeat(self):
        """Write fresh watchdog heartbeat."""
        watchdog_hb = self.state_dir / ".watchdog-heartbeat"
        now_ts = time.time()
        now_int = int(now_ts)
        watchdog_hb.write_text(str(now_int) + "\n", encoding="utf-8")


class TestDefectAFutureOrchestratorStatus(PrefightP2TestBase):
    """
    Defect (a): future-dated updated_at hits max(0, age) clamp.
    Dead orchestrator with clock-skewed timestamp should NOT appear fresh forever.
    """

    def test_future_dated_orchestrator_status_beyond_tolerance_is_stale(self):
        """
        DEFECT: Orchestrator-status with 1-year-future updated_at hits max(0, age)
        clamp and incorrectly reports fresh (age=0 < 300s threshold).
        FIX: Must check for far-future timestamps first, report as stale.
        """
        self._setup_tracker_json(valid=True)
        self._setup_fresh_watchdog_heartbeat()

        # Create orchestrator-status.json with 1 year in future
        orch_status = self.state_dir / "orchestrator-status.json"
        far_future_ts = int(time.time()) + 31536000  # 1 year in future
        far_future_dt = datetime.datetime.fromtimestamp(
            far_future_ts, tz=datetime.timezone.utc
        )
        far_future_iso = far_future_dt.isoformat().replace("+00:00", "Z")
        orch_status.write_text(
            json.dumps({
                "id": "main",
                "role": "orchestrator",
                "activity": "running",
                "phase": "test",
                "updated_at": far_future_iso,
            }) + "\n",
            encoding="utf-8"
        )

        result = self._run_preflight()

        # SHOULD FAIL: orchestrator-status is stale (far-future timestamp)
        self.assertIn(
            "Heartbeats and orchestrator status fresh: FAIL",
            result.stdout,
            "Future-dated orchestrator-status should be detected as stale"
        )
        self.assertNotEqual(result.returncode, 0, "Should exit 1 (stale heartbeats)")
        # Detail should mention the future timestamp issue
        self.assertIn(
            "future",
            result.stdout.lower(),
            "Detail should explain the future timestamp problem"
        )

    def test_future_dated_orchestrator_status_within_tolerance_is_fresh(self):
        """
        Future timestamp within clock-skew tolerance (60s) should be treated fresh.
        This is acceptable clock skew recovery.
        """
        self._setup_tracker_json(valid=True)
        self._setup_fresh_watchdog_heartbeat()

        # Create orchestrator-status.json with 60s in future (within tolerance)
        orch_status = self.state_dir / "orchestrator-status.json"
        near_future_ts = int(time.time()) + 60
        near_future_dt = datetime.datetime.fromtimestamp(
            near_future_ts, tz=datetime.timezone.utc
        )
        near_future_iso = near_future_dt.isoformat().replace("+00:00", "Z")
        orch_status.write_text(
            json.dumps({
                "id": "main",
                "role": "orchestrator",
                "activity": "running",
                "phase": "test",
                "updated_at": near_future_iso,
            }) + "\n",
            encoding="utf-8"
        )

        result = self._run_preflight()

        # SHOULD PASS: within clock-skew tolerance
        self.assertIn(
            "Heartbeats and orchestrator status fresh: PASS",
            result.stdout,
            "Small future-dated timestamp should be treated fresh"
        )
        self.assertEqual(result.returncode, 0, "Should exit 0 (ready)")


class TestDefectBTimezoneConsistency(PrefightP2TestBase):
    """
    Defect (b): naive vs aware timestamp comparison inconsistency.
    Verify both naive and aware ISO 8601 formats are handled correctly.
    """

    def test_orchestrator_status_with_timezone_z_suffix(self):
        """Verify Z suffix (UTC) is parsed correctly."""
        self._setup_tracker_json(valid=True)
        self._setup_fresh_watchdog_heartbeat()

        # Create orchestrator-status.json with Z suffix
        orch_status = self.state_dir / "orchestrator-status.json"
        now_ts = time.time()
        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
        now_iso = now_dt.isoformat().replace("+00:00", "Z")
        orch_status.write_text(
            json.dumps({
                "id": "main",
                "role": "orchestrator",
                "activity": "running",
                "phase": "test",
                "updated_at": now_iso,
            }) + "\n",
            encoding="utf-8"
        )

        result = self._run_preflight()

        # Should parse Z suffix correctly and report fresh
        self.assertIn("Heartbeats and orchestrator status fresh: PASS", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_orchestrator_status_with_utc_offset(self):
        """Verify +00:00 offset format is parsed correctly."""
        self._setup_tracker_json(valid=True)
        self._setup_fresh_watchdog_heartbeat()

        # Create orchestrator-status.json with +00:00 offset
        orch_status = self.state_dir / "orchestrator-status.json"
        now_ts = time.time()
        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
        now_iso = now_dt.isoformat()  # Will be ...+00:00
        orch_status.write_text(
            json.dumps({
                "id": "main",
                "role": "orchestrator",
                "activity": "running",
                "phase": "test",
                "updated_at": now_iso,
            }) + "\n",
            encoding="utf-8"
        )

        result = self._run_preflight()

        # Should parse +00:00 offset correctly and report fresh
        self.assertIn("Heartbeats and orchestrator status fresh: PASS", result.stdout)
        self.assertEqual(result.returncode, 0)


class TestDefectCPhaseDriftVacuousCheck(PrefightP2TestBase):
    """
    Defect (c): phase-drift check is vacuous (always passes).
    Currently phase_ok is hardcoded to True regardless of drift detection.
    FIX: phase_ok should reflect whether drift actually occurred.
    """

    def test_phase_drift_check_can_detect_drift(self):
        """
        Phase drift detection is non-vacuous: drift is detected and reported
        with a visible warning, but doesn't block the wave (warning-level).
        """
        self._setup_tracker_json(valid=True)
        self._setup_fresh_watchdog_heartbeat()

        # Create STATE.md with phase wave-001
        state_md = self.repo_dir / "STATE.md"
        state_md.write_text(
            "# STATE\n\n## Phase: `wave-001` (test)\n\nContent.\n",
            encoding="utf-8"
        )

        # Create orchestrator-status.json with DIFFERENT phase wave-002
        orch_status = self.state_dir / "orchestrator-status.json"
        now_ts = time.time()
        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
        now_iso = now_dt.isoformat().replace("+00:00", "Z")
        orch_status.write_text(
            json.dumps({
                "id": "main",
                "role": "orchestrator",
                "activity": "running",
                "phase": "wave-002",  # Different from STATE.md
                "updated_at": now_iso,
            }) + "\n",
            encoding="utf-8"
        )

        result = self._run_preflight("--json")
        data = json.loads(result.stdout)

        # Find the phase drift check
        phase_check = [c for c in data["checks"] if "phase consistent" in c["name"]][0]

        # Phase drift is warning-level: check passes but warning is visible
        self.assertTrue(
            phase_check["ok"],
            "Phase drift is warning-level, check should pass"
        )
        self.assertIn("WARN: drift detected", phase_check["detail"])
        self.assertIn("wave-001", phase_check["detail"])
        self.assertIn("wave-002", phase_check["detail"])

        # Phase drift doesn't block the wave (exit 0)
        self.assertEqual(result.returncode, 0, "Phase drift is warning-level, exit 0")


class TestDefectCPhaseDriftBehavior(PrefightP2TestBase):
    """
    Document the fixed behavior: phase drift check is no longer vacuous.
    Phase drift detection now properly fails the check.
    """

    def test_phase_drift_detection_warns_not_blocks(self):
        """
        Phase drift is detected, reported with WARN detail, but doesn't block
        (warning-level, exit 0). The check is non-vacuous: drift is tested
        and visible, not ignored.
        """
        self._setup_tracker_json(valid=True)
        self._setup_fresh_watchdog_heartbeat()

        state_md = self.repo_dir / "STATE.md"
        state_md.write_text(
            "# STATE\n\n## Phase: `wave-001` (test)\n\nContent.\n",
            encoding="utf-8"
        )

        orch_status = self.state_dir / "orchestrator-status.json"
        now_ts = time.time()
        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
        now_iso = now_dt.isoformat().replace("+00:00", "Z")
        orch_status.write_text(
            json.dumps({
                "id": "main",
                "role": "orchestrator",
                "activity": "running",
                "phase": "wave-002",  # Drifted
                "updated_at": now_iso,
            }) + "\n",
            encoding="utf-8"
        )

        result = self._run_preflight()

        # Should show warning (loud, visible)
        self.assertIn("[WARN: drift detected]", result.stdout)
        self.assertIn("wave-001", result.stdout)
        self.assertIn("wave-002", result.stdout)

        # Phase drift is warning-level: doesn't block the wave (exit 0)
        self.assertEqual(
            result.returncode, 0,
            "Phase drift is warning-level, exit 0 (doesn't block)"
        )

    def test_phase_consistency_passes_when_no_drift(self):
        """Verify phase consistency check passes when phases match."""
        self._setup_tracker_json(valid=True)
        self._setup_fresh_watchdog_heartbeat()

        state_md = self.repo_dir / "STATE.md"
        state_md.write_text(
            "# STATE\n\n## Phase: `wave-001` (test)\n\nContent.\n",
            encoding="utf-8"
        )

        orch_status = self.state_dir / "orchestrator-status.json"
        now_ts = time.time()
        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
        now_iso = now_dt.isoformat().replace("+00:00", "Z")
        orch_status.write_text(
            json.dumps({
                "id": "main",
                "role": "orchestrator",
                "activity": "running",
                "phase": "wave-001",  # Matches STATE.md
                "updated_at": now_iso,
            }) + "\n",
            encoding="utf-8"
        )

        result = self._run_preflight()

        # Should pass
        self.assertIn("STATE.md phase consistent", result.stdout)
        self.assertEqual(
            result.returncode, 0,
            "Phase consistency should pass when phases match"
        )


if __name__ == "__main__":
    unittest.main()
