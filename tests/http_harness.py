"""Shared HTTP test harness for ThreadingHTTPServer-based tests.

This module provides a base test case class that handles common setup and teardown
patterns for tests that spin up a ThreadingHTTPServer running the dashboard handler.
It ensures proper server lifecycle management and connection cleanup to minimize
socket-level noise during test teardown.
"""
import http.client
import importlib.util
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVE_PATH = Path(__file__).parent.parent / "ui" / "serve.py"
UI_PATH = Path(__file__).parent.parent / "ui"

ENV_KEYS = ("AESOP_ROOT", "AESOP_TRANSCRIPTS_ROOT", "AESOP_STATE_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")


def load_serve(fixture_root, extra_env=None):
    """Import a fresh serve module instance bound to a fixture AESOP_ROOT.

    Each fixture gets its own isolated serve module to ensure proper env isolation
    and to allow reloading across test runs without cross-contamination.
    """
    os.environ["AESOP_ROOT"] = str(fixture_root)
    for k, v in (extra_env or {}).items():
        os.environ[k] = str(v)
    spec = importlib.util.spec_from_file_location(
        f"serve_http_harness_{id(fixture_root)}", SERVE_PATH)
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    return serve


class HTTPServerTestCase(unittest.TestCase):
    """Base class for tests that use ThreadingHTTPServer + DashboardHandler.

    Handles:
      - Fixture directory setup (AESOP_ROOT, state, transcripts)
      - serve.py module loading with isolated environment
      - ThreadingHTTPServer creation and lifecycle
      - Proper server shutdown and connection cleanup
      - Environment restoration on teardown

    Subclasses should call super().setUp() and super().tearDown() to ensure
    proper lifecycle management. Do not override these methods without
    calling the parent implementation.
    """

    def setUp(self):
        """Set up isolated test fixture and HTTP server."""
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-http-test-"))
        (self.fixture_root / "state").mkdir()
        (self.fixture_root / "transcripts").mkdir()

        # Save original environment
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}

        # Set isolated environment
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.fixture_root / "transcripts")
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"

        # Load serve module with isolated fixture
        self.serve = load_serve(self.fixture_root)
        self.token = self.serve.SESSION_TOKEN
        self.assertTrue(self.token, "fixture must produce a session token")

        # Load handler module to get QuietThreadingHTTPServer
        if str(UI_PATH) not in sys.path:
            sys.path.insert(0, str(UI_PATH))
        import handler

        # Create and start server using the custom QuietThreadingHTTPServer
        # (which suppresses expected socket disconnect exceptions on shutdown)
        self.httpd = handler.QuietThreadingHTTPServer(("127.0.0.1", 0), self.serve.DashboardHandler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        """Shut down server and restore environment."""
        try:
            # Stop the SSE collector
            self.serve._collector_stop_event.set()

            # Shut down the server (blocks until current requests complete)
            self.httpd.shutdown()

            # Close the server socket
            self.httpd.server_close()

            # Wait for the server thread to exit
            self.server_thread.join(timeout=3)
        finally:
            # Restore original environment
            for k, v in self._saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

            # Clean up fixture files
            shutil.rmtree(self.fixture_root, ignore_errors=True)

    def make_connection(self):
        """Create a new HTTP connection to the test server.

        Returns an http.client.HTTPConnection bound to the test server's
        port with a reasonable timeout.
        """
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def request(self, method, path, body=None, headers=None, max_retries=3):
        """Execute an HTTP request with transient error retry.

        Retries up to max_retries times on ConnectionAbortedError, ConnectionResetError,
        or RemoteDisconnected — normal on Windows when many ThreadingHTTPServer instances
        churn in one test process.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
            body: Request body (bytes or None)
            headers: Request headers (dict or None)
            max_retries: Number of attempts before raising

        Returns:
            (status_code, response_body_bytes)

        Raises:
            ConnectionAbortedError, ConnectionResetError, or RemoteDisconnected
            if all retries fail.
        """
        last_error = None
        for attempt in range(max_retries):
            conn = self.make_connection()
            try:
                conn.request(method, path, body=body, headers=headers or {})
                resp = conn.getresponse()
                data = resp.read()
                return resp.status, data
            except (ConnectionAbortedError, ConnectionResetError,
                    http.client.RemoteDisconnected) as e:
                last_error = e
                continue
            finally:
                conn.close()

        # All retries exhausted
        raise last_error

    def get(self, path):
        """Execute a GET request and return (status, body_bytes)."""
        return self.request("GET", path)

    def post(self, path, body, headers=None):
        """Execute a POST request and return (status, body_bytes)."""
        return self.request("POST", path, body=body, headers=headers)
