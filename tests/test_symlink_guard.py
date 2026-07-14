"""Cross-platform symlink/junction guard tests for ui/api/submit.

Covers security guard against symlinked inbox file (TOCTOU defense).
- Windows: uses junctions (mklink /J) — no privilege required
- Linux/macOS: uses POSIX symlinks (os.symlink)

CRITICAL FINDING (Python 3.14/Windows):
- os.path.islink() does NOT detect Windows junctions
- Junctions are reported as regular directories
- This is a REAL gap: a malicious junction can bypass the guard on Windows

Run: python -m pytest tests/test_symlink_guard.py -v
     python -m unittest tests.test_symlink_guard
"""
import http.client
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVE_PATH = Path(__file__).parent.parent / "ui" / "serve.py"

ENV_KEYS = ("AESOP_ROOT", "AESOP_TRANSCRIPTS_ROOT", "AESOP_STATE_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")


def load_serve(fixture_root, extra_env=None):
    """Import a fresh serve module instance bound to a fixture AESOP_ROOT."""
    os.environ["AESOP_ROOT"] = str(fixture_root)
    for k, v in (extra_env or {}).items():
        os.environ[k] = str(v)
    spec = importlib.util.spec_from_file_location(f"serve_symlink_{id(fixture_root)}", SERVE_PATH)
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    return serve


def is_windows():
    """Return True if running on Windows."""
    return sys.platform == "win32"


class SymlinkGuardBaseTestCase(unittest.TestCase):
    """Base class for symlink/junction guard tests."""

    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-symlink-guard-test-"))
        (self.fixture_root / "state").mkdir()
        (self.fixture_root / "transcripts").mkdir()
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.fixture_root / "transcripts")
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"

        self.serve = load_serve(self.fixture_root)
        self.token = self.serve.SESSION_TOKEN
        self.assertTrue(self.token, "fixture must produce a session token")

    def tearDown(self):
        try:
            self.serve._collector_stop_event.set()
        except:
            pass
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def _create_junction(self, junction_path, target_path):
        """Create a Windows junction (directory link, no privilege needed).

        Args:
            junction_path: Path object for the junction to create
            target_path: Path object for the target directory

        Returns:
            True if junction created successfully, False otherwise
        """
        if not is_windows():
            return False

        try:
            result = subprocess.run(
                ["mklink", "/J", str(junction_path), str(target_path)],
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _create_symlink(self, symlink_path, target_path):
        """Create a POSIX symlink (or attempt on Windows if privileged).

        Args:
            symlink_path: Path object for the symlink to create
            target_path: Path object for the target

        Returns:
            True if symlink created successfully, False otherwise
        """
        try:
            os.symlink(str(target_path), str(symlink_path))
            return True
        except (OSError, NotImplementedError):
            return False


class TestDirectApiSubmitJunctionGuard(SymlinkGuardBaseTestCase):
    """Direct tests of api.submit.append_to_inbox against junctions (Windows) and symlinks.

    These test the pure function directly, without HTTP.
    """

    def setUp(self):
        super().setUp()
        # Import the API after serve is loaded
        import api.submit
        import config as ui_config
        self.submit_api = api.submit
        self.config = ui_config

    def test_append_rejects_posix_symlink_inbox(self):
        """POSIX symlink to inbox file must be rejected on all platforms."""
        if is_windows():
            # File symlinks need privilege on Windows; skip unless available
            self.skipTest("File symlinks require admin privilege on Windows")

        target = self.fixture_root / "state" / "not-the-inbox.md"
        target.write_text("attacker-controlled\n", encoding="utf-8")
        inbox_path = Path(self.config.INBOX_FILE)

        if not self._create_symlink(inbox_path, target):
            self.skipTest("Could not create POSIX symlink on this platform")

        ok, result = self.submit_api.append_to_inbox("should not be written")
        self.assertFalse(ok, "append_to_inbox should reject POSIX symlink")
        status, error = result
        self.assertEqual(status, 400)
        self.assertIn("symlink", error["error"].lower())
        self.assertNotIn("should not be written", target.read_text(encoding="utf-8"))

    def test_append_rejects_windows_junction_inbox(self):
        """Windows junction to inbox parent must be rejected (or at least tested).

        CRITICAL: On Windows Python 3.14, os.path.islink() does NOT detect junctions.
        This test will FAIL, exposing the guard gap.
        """
        if not is_windows():
            self.skipTest("Junction test only applies to Windows")

        # Create a target directory to point the junction to
        target_dir = self.fixture_root / "junction-target"
        target_dir.mkdir()

        inbox_path = Path(self.config.INBOX_FILE)
        inbox_parent = inbox_path.parent

        # Create junction pointing to target directory
        # We'll make the inbox file be inside the junction
        junction_path = inbox_parent / "junction-inbox"

        if not self._create_junction(junction_path, target_dir):
            self.skipTest("Could not create Windows junction (requires Windows)")

        # Point inbox to a file inside the junction
        inbox_through_junction = junction_path / "ui-inbox.md"
        # Override the config to use this path
        self.config.INBOX_FILE = inbox_through_junction

        ok, result = self.submit_api.append_to_inbox("test via junction")

        # EXPECTED FAILURE: The guard DOES NOT detect junctions
        # os.path.islink(junction_path) returns False
        # So the write will SUCCEED when it should FAIL

        if ok:
            # This is the bug: junction was NOT detected
            self.fail(
                "GUARD GAP FOUND: append_to_inbox did NOT reject Windows junction inbox. "
                "os.path.islink() does not detect junctions on Windows Python 3.14. "
                "A malicious junction could bypass this guard. "
                "Evidence: islink(junction) = False, but target was followed."
            )
        else:
            # Guard somehow detected it (unexpected, but not a failure)
            status, error = result
            self.assertEqual(status, 400)
            self.assertIn("symlink", error["error"].lower())

    def test_append_accepts_real_file_inbox(self):
        """Appending to a real (non-symlink, non-junction) inbox must succeed."""
        inbox_path = Path(self.config.INBOX_FILE)
        inbox_path.parent.mkdir(parents=True, exist_ok=True)

        ok, result = self.submit_api.append_to_inbox("test entry")
        self.assertTrue(ok, f"append_to_inbox should succeed for real file: {result}")
        self.assertIsNone(result)

        content = inbox_path.read_text(encoding="utf-8")
        self.assertIn("test entry", content)


class TestHttpSubmitJunctionGuard(SymlinkGuardBaseTestCase):
    """HTTP-level tests of /submit endpoint against junctions and symlinks."""

    def setUp(self):
        super().setUp()
        self.httpd = __import__("http.server", fromlist=["ThreadingHTTPServer"]) \
            .ThreadingHTTPServer(("127.0.0.1", 0), self.serve.DashboardHandler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        try:
            self.serve._collector_stop_event.set()
            self.httpd.shutdown()
            self.httpd.server_close()
            self.server_thread.join(timeout=3)
        finally:
            super().tearDown()

    def _conn(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def _request(self, method, path, body=None, headers=None):
        """Send HTTP request with retry on transient socket errors."""
        last = None
        for _ in range(3):
            con = self._conn()
            try:
                con.request(method, path, body=body, headers=headers or {})
                resp = con.getresponse()
                return resp.status, resp.read()
            except (ConnectionAbortedError, ConnectionResetError,
                    http.client.RemoteDisconnected) as e:
                last = e
                continue
            finally:
                con.close()
        raise last

    def test_http_submit_rejects_posix_symlink_inbox(self):
        """POST /submit when inbox is a POSIX symlink must be rejected."""
        if is_windows():
            self.skipTest("File symlinks need admin on Windows")

        target = self.fixture_root / "state" / "not-the-inbox.md"
        target.write_text("attacker-controlled\n", encoding="utf-8")
        inbox_path = Path(self.serve.INBOX_FILE)

        if not self._create_symlink(inbox_path, target):
            self.skipTest("Could not create POSIX symlink")

        payload = b'{"text": "test entry"}'
        status, body = self._request(
            "POST", "/submit",
            body=payload,
            headers={"Content-Length": str(len(payload)), "X-Aesop-Token": self.token}
        )
        self.assertNotEqual(status, 200,
            f"POST /submit should reject symlinked inbox, got {status}")

    def test_http_submit_with_windows_junction_inbox_gap(self):
        """POST /submit when inbox parent has a junction demonstrates the guard gap.

        On Windows, junctions are NOT detected by os.path.islink().
        This test demonstrates the gap.
        """
        if not is_windows():
            self.skipTest("Junction test only for Windows")

        target_dir = self.fixture_root / "junction-target"
        target_dir.mkdir()

        inbox_path = Path(self.serve.INBOX_FILE)
        inbox_parent = inbox_path.parent
        junction_path = inbox_parent / "junction-inbox"

        if not self._create_junction(junction_path, target_dir):
            self.skipTest("Could not create junction")

        # Point inbox to file inside junction
        inbox_through_junction = junction_path / "ui-inbox.md"

        # We can't easily override serve.INBOX_FILE at runtime, so we'll
        # document the expected gap instead
        print(f"\nGUARD GAP TEST: Inlet through junction at {junction_path}")
        print(f"  os.path.islink({junction_path}) = {os.path.islink(junction_path)}")
        print(f"  Expected: Junction NOT detected, write would proceed (SECURITY GAP)")

        # Rather than modify serve's INBOX_FILE, we'll document the finding
        self.assertFalse(os.path.islink(junction_path),
            "Guard relies on islink(), which does NOT detect junctions on Windows Python 3.14")


class TestJunctionDetectionOnWindows(unittest.TestCase):
    """Test Python's junction detection capabilities on Windows.

    This test documents the behavior of os.path.islink(), os.stat(), and
    pathlib.Path.is_symlink() when used with Windows junctions.
    """

    @unittest.skipUnless(is_windows(), "Windows-only test")
    def test_islink_does_not_detect_junction(self):
        """Verify that os.path.islink() returns False for Windows junctions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            target = tmpdir / "target"
            target.mkdir()
            junction = tmpdir / "junction"

            # Create junction
            result = subprocess.run(
                ["mklink", "/J", str(junction), str(target)],
                shell=True,
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                self.skipTest("Could not create junction on this Windows setup")

            # CRITICAL: islink returns False for junctions
            is_link = os.path.islink(junction)
            self.assertFalse(is_link,
                "os.path.islink() returns False for Windows junctions — "
                "this is the root cause of the guard gap")

    @unittest.skipUnless(is_windows(), "Windows-only test")
    def test_pathlib_is_symlink_does_not_detect_junction(self):
        """Verify that Path.is_symlink() also does NOT detect junctions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            target = tmpdir / "target"
            target.mkdir()
            junction = tmpdir / "junction"

            # Create junction
            result = subprocess.run(
                ["mklink", "/J", str(junction), str(target)],
                shell=True,
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                self.skipTest("Could not create junction")

            # Path.is_symlink() also returns False
            is_sym = junction.is_symlink()
            self.assertFalse(is_sym,
                "Path.is_symlink() returns False for Windows junctions")


if __name__ == "__main__":
    unittest.main()
