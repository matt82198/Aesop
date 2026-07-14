"""Regression tests for the GET /agent path-traversal / arbitrary-file-read fix.

Vulnerability (reproduced pre-fix): extract_agent_dispatch_prompt() in ui/serve.py
spliced the unescaped `id` query param into a glob pattern
(`TRANSCRIPTS_ROOT.glob(f"**/{agent_id}*.output")`) with no rejection of `..`
segments or glob metacharacters (`* ? [ ]`), and never verified the matched file
stayed inside TRANSCRIPTS_ROOT. That allowed:

  - GET /agent?id=..%2Foutside_secret%2Fleaked  -> read a file OUTSIDE the
    transcripts root (path traversal / arbitrary file read).
  - GET /agent?id=*                              -> enumerate/exfiltrate every
    .output file anywhere under the transcripts tree (wildcard injection).

Fix under test:
  1. extract_agent_dispatch_prompt() rejects agent_id containing any of
     `/ \\ .. * ? [ ]` BEFORE building the glob pattern.
  2. After resolving the best match, it verifies the resolved path is still
     `.is_relative_to(TRANSCRIPTS_ROOT.resolve())`, refusing otherwise.
  3. The legitimate contract (prefix-matching a truncated dashboard id against a
     full-id `*.output` transcript, per TestDispatchPromptExtraction in
     tests/test_serve_sse.py) keeps working.

Run: python -m unittest tests.test_serve_agent_security
"""
import http.client
import importlib.util
import json
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

SECRET_MARKER = "TOP_SECRET_CONTENT_DO_NOT_LEAK"


def load_serve(fixture_root, extra_env=None):
    """Import a fresh serve module instance bound to a fixture AESOP_ROOT."""
    os.environ["AESOP_ROOT"] = str(fixture_root)
    for k, v in (extra_env or {}).items():
        os.environ[k] = str(v)
    spec = importlib.util.spec_from_file_location(f"serve_agentsec_{id(fixture_root)}", SERVE_PATH)
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    return serve


class EnvFixtureCase(unittest.TestCase):
    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-agentsec-test-"))
        (self.fixture_root / "state").mkdir()
        (self.fixture_root / "transcripts").mkdir()
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.fixture_root / "transcripts")
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.fixture_root, ignore_errors=True)


# ------------------------------------------------------------------------------
# Unit-level: extract_agent_dispatch_prompt() must reject before touching disk
# ------------------------------------------------------------------------------

class TestExtractAgentDispatchPromptRejectsTraversal(EnvFixtureCase):
    def setUp(self):
        super().setUp()
        # Sibling directory OUTSIDE the transcripts root, holding a "secret" file.
        # This mirrors the confirmed PoC: outside_secret/leaked.output is a
        # sibling of TRANSCRIPTS_ROOT, not a descendant of it.
        self.outside_dir = self.fixture_root / "outside_secret"
        self.outside_dir.mkdir()
        self.leaked_file = self.outside_dir / "leaked.output"
        self.leaked_file.write_text(
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": SECRET_MARKER}}) + "\n",
            encoding="utf-8",
        )
        self.serve = load_serve(self.fixture_root)

    def test_rejects_dotdot_slash_traversal(self):
        data = self.serve.extract_agent_dispatch_prompt("../outside_secret/leaked")
        self.assertIn("error", data)
        self.assertNotIn("dispatch_prompt", data)

    def test_rejects_dotdot_backslash_traversal(self):
        data = self.serve.extract_agent_dispatch_prompt("..\\outside_secret\\leaked")
        self.assertIn("error", data)
        self.assertNotIn("dispatch_prompt", data)

    def test_rejects_bare_wildcard(self):
        data = self.serve.extract_agent_dispatch_prompt("*")
        self.assertIn("error", data)
        self.assertNotIn("dispatch_prompt", data)

    def test_rejects_wildcard_suffix(self):
        data = self.serve.extract_agent_dispatch_prompt("../../secret*")
        self.assertIn("error", data)
        self.assertNotIn("dispatch_prompt", data)

    def test_rejects_bracket_glob_metachar(self):
        data = self.serve.extract_agent_dispatch_prompt("[a-z]*")
        self.assertIn("error", data)
        self.assertNotIn("dispatch_prompt", data)

    def test_rejects_question_mark_glob_metachar(self):
        data = self.serve.extract_agent_dispatch_prompt("le?ked")
        self.assertIn("error", data)
        self.assertNotIn("dispatch_prompt", data)


class TestExtractAgentDispatchPromptHappyPath(EnvFixtureCase):
    """The legitimate contract must keep working: truncated id prefix-matches a
    full-id *.output transcript inside TRANSCRIPTS_ROOT."""

    def test_valid_prefix_id_still_resolves(self):
        full_id = "abc123def456fedcba9876"
        transcript = self.fixture_root / "transcripts" / f"agent-{full_id}.jsonl"
        lines = [
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": "FIXTURE DISPATCH PROMPT: fix the widget"}}),
            json.dumps({"type": "assistant", "model": "claude-haiku-4-5",
                        "message": {"content": "ok"}}),
        ]
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

        serve = load_serve(self.fixture_root)
        data = serve.extract_agent_dispatch_prompt(full_id[:13])
        self.assertNotIn("error", data, data.get("error", ""))
        self.assertIn("FIXTURE DISPATCH PROMPT", data["dispatch_prompt"])
        self.assertEqual(data["dispatcher"], "main thread")
        self.assertEqual(data["message_count"], 2)

    def test_missing_transcript_is_still_graceful(self):
        serve = load_serve(self.fixture_root)
        data = serve.extract_agent_dispatch_prompt("nonexistent000")
        self.assertIn("error", data)


# ------------------------------------------------------------------------------
# HTTP-level: the exact confirmed PoC against the real GET /agent route
# ------------------------------------------------------------------------------

class TestServeAgentHTTPEndToEnd(EnvFixtureCase):
    def setUp(self):
        super().setUp()
        self.outside_dir = self.fixture_root / "outside_secret"
        self.outside_dir.mkdir()
        (self.outside_dir / "leaked.output").write_text(
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": SECRET_MARKER}}) + "\n",
            encoding="utf-8",
        )

        self.serve = load_serve(self.fixture_root)

        # Load handler module to get QuietThreadingHTTPServer
        if str(UI_PATH) not in sys.path:
            sys.path.insert(0, str(UI_PATH))
        import handler

        # Use QuietThreadingHTTPServer to suppress socket disconnect exceptions
        self.httpd = handler.QuietThreadingHTTPServer(("127.0.0.1", 0), self.serve.DashboardHandler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.server_thread.join(timeout=3)
        finally:
            super().tearDown()

    def _get(self, path):
        # Retry transient Windows socket aborts (WSAECONNABORTED / reset).
        last = None
        for _ in range(3):
            con = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
            try:
                con.request("GET", path)
                resp = con.getresponse()
                return resp.status, resp.read()
            except (ConnectionAbortedError, ConnectionResetError,
                    http.client.RemoteDisconnected) as e:
                last = e
                continue
            finally:
                con.close()
        raise last

    def test_dotdot_slash_traversal_poc_never_leaks_secret(self):
        status, body = self._get("/agent?id=..%2Foutside_secret%2Fleaked")
        self.assertNotEqual(status, 200)
        self.assertNotIn(SECRET_MARKER.encode(), body)

    def test_dotdot_encoded_slash_traversal_never_leaks_secret(self):
        status, body = self._get("/agent?id=..%2F..%2Fx")
        self.assertNotEqual(status, 200)
        self.assertNotIn(SECRET_MARKER.encode(), body)

    def test_wildcard_id_never_enumerates_files(self):
        status, body = self._get("/agent?id=*")
        self.assertNotEqual(status, 200)
        self.assertNotIn(SECRET_MARKER.encode(), body)

    def test_valid_id_happy_path_still_returns_200(self):
        full_id = "validhappyid001"
        transcript = self.fixture_root / "transcripts" / f"agent-{full_id}.jsonl"
        lines = [
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": "HAPPY PATH PROMPT"}}),
        ]
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

        status, body = self._get(f"/agent?id={full_id[:10]}")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertNotIn("error", payload, payload.get("error", ""))
        self.assertIn("HAPPY PATH PROMPT", payload["dispatch_prompt"])


if __name__ == "__main__":
    unittest.main()
