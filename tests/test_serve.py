"""Unit tests for ui/serve.py alert path resolution.

Contract: security alerts live in state/SECURITY-ALERTS.log (canonical location used by
daemons and monitor) — NOT scan/. The bug was serve.py reading from scan/ instead of state/.

Run: python -m unittest tests.test_serve
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path


class TestServeAlertPath(unittest.TestCase):
    """Test cases for ui/serve.py alert path resolution."""

    def setUp(self):
        """Create temporary fixture directory structure."""
        self.fixture_root = tempfile.mkdtemp(prefix="aesop-serve-test-")
        self.state_dir = os.path.join(self.fixture_root, "state")
        self.scan_dir = os.path.join(self.fixture_root, "scan")
        os.makedirs(self.state_dir, exist_ok=True)
        os.makedirs(self.scan_dir, exist_ok=True)

        # Save original env
        self.orig_aesop_root = os.environ.get("AESOP_ROOT")

    def tearDown(self):
        """Clean up temporary fixture."""
        # Restore original env
        if self.orig_aesop_root is not None:
            os.environ["AESOP_ROOT"] = self.orig_aesop_root
        elif "AESOP_ROOT" in os.environ:
            del os.environ["AESOP_ROOT"]

        # Clean up temp dir
        import shutil
        if os.path.exists(self.fixture_root):
            shutil.rmtree(self.fixture_root)

    def _load_serve_module(self):
        """Dynamically import serve.py with fixture AESOP_ROOT."""
        # Set fixture AESOP_ROOT before importing
        os.environ["AESOP_ROOT"] = self.fixture_root

        # Remove cached serve module if it exists
        if "ui.serve" in sys.modules:
            del sys.modules["ui.serve"]
        if "ui" in sys.modules:
            del sys.modules["ui"]

        # Import serve module
        serve_path = Path(__file__).parent.parent / "ui" / "serve.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("serve", serve_path)
        serve = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(serve)
        return serve

    def test_alerts_in_state_directory_are_read(self):
        """Alert lines in state/SECURITY-ALERTS.log must be counted (canonical path)."""
        # Write HIGH alert to state/ (canonical location)
        alert_file = os.path.join(self.state_dir, "SECURITY-ALERTS.log")
        with open(alert_file, "w") as f:
            f.write("2026-07-12T00:00:00Z HIGH test alert for fixture\n")

        # Load serve module with fixture
        serve = self._load_serve_module()

        # Get alerts
        alerts = serve.get_alerts()

        # Verify alert was read from state/
        self.assertGreater(
            alerts["count"],
            0,
            "Alert written to state/SECURITY-ALERTS.log must be counted "
            "(this is the canonical location used by daemons)"
        )
        self.assertEqual(len(alerts["lines"]), 1)
        self.assertIn("HIGH", alerts["lines"][0])

    def test_alerts_in_scan_directory_are_not_read(self):
        """Alert lines in scan/ directory must NOT be read (non-canonical path)."""
        # Write decoy alert to scan/ (non-canonical, old/wrong location)
        scan_alert_file = os.path.join(self.scan_dir, "SECURITY-ALERTS.log")
        with open(scan_alert_file, "w") as f:
            f.write("2026-07-12T00:00:00Z CRITICAL decoy alert in scan/\n")

        # Load serve module with fixture
        serve = self._load_serve_module()

        # Get alerts
        alerts = serve.get_alerts()

        # Verify alert in scan/ was NOT read
        self.assertEqual(
            alerts["count"],
            0,
            "Alerts in scan/SECURITY-ALERTS.log must not be read — "
            "scan/ is not the canonical location (use state/ instead)"
        )

    def test_degrades_gracefully_when_no_alerts_exist(self):
        """Must not crash when SECURITY-ALERTS.log doesn't exist."""
        # Don't create any alert file

        # Load serve module with fixture
        serve = self._load_serve_module()

        # Get alerts - should not crash
        alerts = serve.get_alerts()

        # Verify graceful degradation
        self.assertEqual(alerts["count"], 0)
        self.assertEqual(alerts["lines"], [])


if __name__ == "__main__":
    unittest.main()
