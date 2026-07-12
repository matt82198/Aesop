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


class TestBacklogEndpoint(unittest.TestCase):
    """Test cases for /api/backlog endpoint."""

    def setUp(self):
        """Create temporary fixture directory structure."""
        self.fixture_root = tempfile.mkdtemp(prefix="aesop-backlog-endpoint-test-")
        self.state_dir = os.path.join(self.fixture_root, "state")
        os.makedirs(self.state_dir, exist_ok=True)

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
        os.environ["AESOP_ROOT"] = self.fixture_root

        if "ui.serve" in sys.modules:
            del sys.modules["ui.serve"]
        if "ui" in sys.modules:
            del sys.modules["ui"]

        serve_path = Path(__file__).parent.parent / "ui" / "serve.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("serve", serve_path)
        serve = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(serve)
        return serve

    def test_backlog_endpoint_returns_valid_json(self):
        """Verify /api/backlog endpoint returns valid JSON structure."""
        backlog_content = """# Audit backlog

## P0 — correctness / security (do first)

- ✅ **[sec] Item 1**
- 🔵 **[arch] Item 2**
"""
        backlog_path = os.path.join(self.fixture_root, "AUDIT-BACKLOG.md")
        with open(backlog_path, "w", encoding="utf-8") as f:
            f.write(backlog_content)

        serve = self._load_serve_module()
        data = serve.parse_audit_backlog()

        # Verify JSON structure
        self.assertIn("tiers", data)
        self.assertIsInstance(data["tiers"], list)
        if data["tiers"]:
            tier = data["tiers"][0]
            self.assertIn("tier", tier)
            self.assertIn("items", tier)
            self.assertIn("done", tier)
            self.assertIn("inflight", tier)
            self.assertIn("todo", tier)
            self.assertIn("total", tier)


class TestAuditBacklogParser(unittest.TestCase):
    """Test cases for parsing AUDIT-BACKLOG.md format."""

    def setUp(self):
        """Create temporary fixture directory structure."""
        self.fixture_root = tempfile.mkdtemp(prefix="aesop-backlog-test-")
        self.state_dir = os.path.join(self.fixture_root, "state")
        os.makedirs(self.state_dir, exist_ok=True)

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

    def test_parse_basic_backlog_structure(self):
        """Parse P0, P1, P2, and Needs a user decision sections with correct item counts."""
        backlog_content = """# Audit backlog — five-lens specialist review (2026-07-12)

## P0 — correctness / security (do first)

- ✅ **[sec] First P0 item**
  Some description here.
- 🔵 **[arch] Second P0 item**
- ⬜ **[bash] Third P0 item**

## P1 — hardening / robustness

- ⬜ **[js] First P1 item**
- ✅ **[sec] Second P1 item**

## P2 — honesty / polish / docs

- 🔵 **[arch] Only P2 item**

## Needs a user decision (⏸)

- ⏸ **[honest] User decision item**

## Landing log

This section is NOT parsed.
"""
        # Write fixture backlog
        backlog_path = os.path.join(self.fixture_root, "AUDIT-BACKLOG.md")
        with open(backlog_path, "w", encoding="utf-8") as f:
            f.write(backlog_content)

        # Load serve module
        serve = self._load_serve_module()

        # Parse backlog
        result = serve.parse_audit_backlog()

        # Verify structure
        self.assertIsNotNone(result)
        self.assertIn("tiers", result)

        # Check P0
        p0_tier = next((t for t in result["tiers"] if t["tier"] == "P0"), None)
        self.assertIsNotNone(p0_tier, "P0 tier should exist")
        self.assertEqual(len(p0_tier["items"]), 3, "P0 should have 3 items")

        # Check P1
        p1_tier = next((t for t in result["tiers"] if t["tier"] == "P1"), None)
        self.assertIsNotNone(p1_tier, "P1 tier should exist")
        self.assertEqual(len(p1_tier["items"]), 2, "P1 should have 2 items")

        # Check P2
        p2_tier = next((t for t in result["tiers"] if t["tier"] == "P2"), None)
        self.assertIsNotNone(p2_tier, "P2 tier should exist")
        self.assertEqual(len(p2_tier["items"]), 1, "P2 should have 1 item")

        # Check Needs decision (⏸)
        decision_tier = next((t for t in result["tiers"] if t["tier"] == "Needs decision"), None)
        self.assertIsNotNone(decision_tier, "Needs decision tier should exist")
        self.assertEqual(len(decision_tier["items"]), 1, "Needs decision should have 1 item")

    def test_parse_backlog_status_glyphs(self):
        """Verify status glyphs (✅, 🔵, ⬜, ⏸) are correctly classified."""
        backlog_content = """# Audit backlog

## P0 — correctness / security (do first)

- ✅ **[sec] Done item**
- 🔵 **[arch] In flight item**
- ⬜ **[bash] Unclaimed item**
- ⏸ **[js] User decision item**
"""
        backlog_path = os.path.join(self.fixture_root, "AUDIT-BACKLOG.md")
        with open(backlog_path, "w", encoding="utf-8") as f:
            f.write(backlog_content)

        serve = self._load_serve_module()
        result = serve.parse_audit_backlog()

        p0_tier = result["tiers"][0]
        items = p0_tier["items"]

        # Verify status glyphs
        self.assertEqual(items[0]["status"], "✅", "First item should have done status")
        self.assertEqual(items[1]["status"], "🔵", "Second item should have in-flight status")
        self.assertEqual(items[2]["status"], "⬜", "Third item should have unclaimed status")
        self.assertEqual(items[3]["status"], "⏸", "Fourth item should have decision status")

    def test_parse_backlog_extracts_tag_and_title(self):
        """Verify tag (e.g. [sec]) and title are correctly extracted."""
        backlog_content = """# Audit backlog

## P0 — correctness / security (do first)

- ✅ **[sec] This is the title**
- 🔵 **[arch] Another title with [brackets] in it**
"""
        backlog_path = os.path.join(self.fixture_root, "AUDIT-BACKLOG.md")
        with open(backlog_path, "w", encoding="utf-8") as f:
            f.write(backlog_content)

        serve = self._load_serve_module()
        result = serve.parse_audit_backlog()

        items = result["tiers"][0]["items"]

        # Verify tag and title extraction
        self.assertEqual(items[0]["tag"], "[sec]", "First item tag should be [sec]")
        self.assertEqual(items[0]["title"], "This is the title", "First item title should be extracted")

        self.assertEqual(items[1]["tag"], "[arch]", "Second item tag should be [arch]")
        self.assertEqual(items[1]["title"], "Another title with [brackets] in it", "Second item title should handle brackets")

    def test_parse_backlog_counts_status_per_tier(self):
        """Verify done/inflight/todo counts are correctly calculated per tier."""
        backlog_content = """# Audit backlog

## P0 — correctness / security (do first)

- ✅ **[sec] Done 1**
- ✅ **[sec] Done 2**
- 🔵 **[arch] In flight 1**
- 🔵 **[arch] In flight 2**
- ⬜ **[bash] Todo 1**
- ⬜ **[bash] Todo 2**
- ⬜ **[bash] Todo 3**
"""
        backlog_path = os.path.join(self.fixture_root, "AUDIT-BACKLOG.md")
        with open(backlog_path, "w", encoding="utf-8") as f:
            f.write(backlog_content)

        serve = self._load_serve_module()
        result = serve.parse_audit_backlog()

        p0_tier = result["tiers"][0]

        # Verify counts
        self.assertEqual(p0_tier["done"], 2, "P0 should have 2 done items")
        self.assertEqual(p0_tier["inflight"], 2, "P0 should have 2 in-flight items")
        self.assertEqual(p0_tier["todo"], 3, "P0 should have 3 todo items")
        self.assertEqual(p0_tier["total"], 7, "P0 should have 7 total items")

    def test_parse_backlog_missing_file_degrades_gracefully(self):
        """Must not crash when AUDIT-BACKLOG.md doesn't exist."""
        # Don't create backlog file

        serve = self._load_serve_module()
        result = serve.parse_audit_backlog()

        # Should return graceful empty structure
        self.assertIsNotNone(result)
        self.assertIn("tiers", result)
        self.assertEqual(len(result["tiers"]), 0, "Should return empty tiers on missing file")

    def test_parse_backlog_ignores_landing_log_and_dispatch_plan(self):
        """Must not parse items after 'Landing log' or 'Dispatch plan' sections."""
        backlog_content = """# Audit backlog

## P0 — correctness / security (do first)

- ✅ **[sec] Real P0 item**

## Landing log

This should NOT be parsed:
- ⬜ **[fake] Fake landing log item**

## Dispatch plan

- ⬜ **[fake] Fake dispatch plan item**
"""
        backlog_path = os.path.join(self.fixture_root, "AUDIT-BACKLOG.md")
        with open(backlog_path, "w", encoding="utf-8") as f:
            f.write(backlog_content)

        serve = self._load_serve_module()
        result = serve.parse_audit_backlog()

        p0_tier = result["tiers"][0]

        # Should only have 1 real item, not the fake ones
        self.assertEqual(len(p0_tier["items"]), 1, "Should ignore Landing log and Dispatch plan sections")
        self.assertEqual(p0_tier["items"][0]["title"], "Real P0 item")


if __name__ == "__main__":
    unittest.main()
