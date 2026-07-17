"""Tests for the Agent Inspector backend: agents.get_agent_detail() +
GET /api/agent?id=<id> (wave-31 Agent Inspector drawer).

Two layers:
  * Unit — import agents directly, no server. Covers the happy path (dispatch
    prompt + bounded transcript tail), the shared path-traversal/glob-injection
    rejection (reused from extract_agent_dispatch_prompt), the 404-vs-400
    distinction, tail bounding on a large transcript, and best-effort credential
    redaction of the tail.
  * HTTP — the real GET /api/agent route through QuietThreadingHTTPServer:
    200 on a valid id, 404 for an unknown id, 400 for a rejected id, and the
    confirmed traversal PoC never leaking an out-of-root secret.

Dummy secrets are fragment-assembled at runtime so the push-gate secret scanner
never sees a contiguous credential in this file (repo invariant).

Run: python -m unittest tests.test_agent_inspector
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

UI_DIR = Path(__file__).parent.parent / "ui"
SERVE_PATH = UI_DIR / "serve.py"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

import config  # noqa: E402
import agents  # noqa: E402

ENV_KEYS = ("AESOP_ROOT", "AESOP_STATE_ROOT", "AESOP_TRANSCRIPTS_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")

SECRET_MARKER = "TOP_SECRET_CONTENT_DO_NOT_LEAK"

# AWS-format access key assembled from fragments so the literal never appears
# contiguously in source (secret-scan self-scan invariant): AKIA + 16 [0-9A-Z].
FAKE_AWS_KEY = "AK" + "IA" + "ABCDEFGHIJ012345"


class InspectorFixtureCase(unittest.TestCase):
    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-inspector-test-"))
        self.state_dir = self.fixture_root / "state"
        self.state_dir.mkdir(parents=True)
        self.transcripts_root = self.fixture_root / "transcripts"
        self.transcripts_root.mkdir()
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["AESOP_ROOT"] = str(self.fixture_root)
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.transcripts_root)
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"
        config.reload()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def _write_transcript(self, full_id, lines):
        path = self.transcripts_root / f"agent-{full_id}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


class TestGetAgentDetailHappyPath(InspectorFixtureCase):
    def test_returns_prompt_metadata_and_transcript_tail(self):
        full_id = "inspecthappy001abc"
        lines = [
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": "INSPECT DISPATCH PROMPT: build the drawer"}}),
            json.dumps({"type": "assistant", "model": "claude-haiku-4-5",
                        "message": {"content": [{"type": "text", "text": "on it"}]}}),
            json.dumps({"type": "assistant",
                        "message": {"content": [{"type": "tool_use", "name": "Write"}]}}),
        ]
        self._write_transcript(full_id, lines)

        result = agents.get_agent_detail(full_id[:13])

        self.assertNotIn("error", result, result.get("error", ""))
        self.assertIn("INSPECT DISPATCH PROMPT", result["dispatch_prompt"])
        self.assertEqual(result["dispatcher"], "main thread")
        self.assertEqual(result["model"], "claude-haiku-4-5")
        self.assertEqual(result["message_count"], 3)
        self.assertIsInstance(result["transcript_tail"], list)
        self.assertEqual(len(result["transcript_tail"]), 3)
        # Each entry is a {type, text} plain-string record.
        for entry in result["transcript_tail"]:
            self.assertIn("type", entry)
            self.assertIsInstance(entry["text"], str)
        # tool_use is summarised readably, not dropped.
        self.assertTrue(any("[tool_use: Write]" in e["text"] for e in result["transcript_tail"]))
        self.assertIn("tail_truncated", result)

    def test_xss_payload_is_returned_as_plain_string(self):
        # The backend returns plain strings (the client escapes on render). It
        # must NOT wrap/execute anything; the payload round-trips verbatim.
        full_id = "inspectxss002abc"
        payload = '<img src=x onerror=alert(1)><script>alert(1)</script>'
        lines = [
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": "prompt"}}),
            json.dumps({"type": "assistant", "message": {"content": payload}}),
        ]
        self._write_transcript(full_id, lines)

        result = agents.get_agent_detail(full_id[:13])
        joined = " ".join(e["text"] for e in result["transcript_tail"])
        self.assertIn(payload, joined)  # verbatim string, no HTML entities added


class TestGetAgentDetailBounding(InspectorFixtureCase):
    def test_tail_is_bounded_to_last_n_lines(self):
        full_id = "inspectbig003abc"
        # 500 lines; the tail must cap at TRANSCRIPT_TAIL_LINES (40) and mark
        # the payload truncated.
        lines = [json.dumps({"type": "user", "parentUuid": None,
                             "message": {"content": "prompt"}})]
        for i in range(500):
            lines.append(json.dumps({"type": "assistant",
                                     "message": {"content": f"line number {i}"}}))
        self._write_transcript(full_id, lines)

        result = agents.get_agent_detail(full_id[:13])
        self.assertNotIn("error", result)
        self.assertLessEqual(len(result["transcript_tail"]), agents.TRANSCRIPT_TAIL_LINES)
        self.assertTrue(result["tail_truncated"])
        # The LAST line must be present; an early line must have been dropped.
        joined = " ".join(e["text"] for e in result["transcript_tail"])
        self.assertIn("line number 499", joined)
        self.assertNotIn("line number 0 ", joined + " ")


class TestGetAgentDetailRedaction(InspectorFixtureCase):
    def test_credential_in_tail_is_masked(self):
        full_id = "inspectsec004abc"
        lines = [
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": "prompt"}}),
            json.dumps({"type": "assistant",
                        "message": {"content": f"here is the key {FAKE_AWS_KEY} do not leak"}}),
        ]
        self._write_transcript(full_id, lines)

        result = agents.get_agent_detail(full_id[:13])
        joined = " ".join(e["text"] for e in result["transcript_tail"])
        self.assertNotIn(FAKE_AWS_KEY, joined)
        self.assertIn("REDACTED", joined)

    def test_redact_secrets_masks_key_value_assignment(self):
        # Assemble the key name and value from fragments so no contiguous
        # `key = "value"` credential shape appears in this source file (the
        # push-gate scanner scans it).
        key_name = "api" + "_key"
        secret_value = "sk-" + "abcdefghij0123456789XYZ"
        raw = key_name + "=" + secret_value
        masked = agents._redact_secrets(raw)
        self.assertNotIn(secret_value, masked)
        self.assertIn("REDACTED", masked)


class TestGetAgentDetailErrors(InspectorFixtureCase):
    def test_forbidden_id_is_rejected_invalid(self):
        for bad in ("../outside/leaked", "*", "a\\b", "[abc]", ""):
            with self.subTest(agent_id=bad):
                result = agents.get_agent_detail(bad)
                self.assertTrue(result.get("invalid"), result)
                self.assertIn("error", result)
                self.assertNotIn("transcript_tail", result)

    def test_missing_transcript_is_404_shaped_not_invalid(self):
        result = agents.get_agent_detail("nonexistent999")
        self.assertIn("error", result)
        self.assertNotIn("invalid", result)
        self.assertNotIn("transcript_tail", result)


# ------------------------------------------------------------------------------
# HTTP-level: the real GET /api/agent route
# ------------------------------------------------------------------------------

def load_serve(fixture_root):
    os.environ["AESOP_ROOT"] = str(fixture_root)
    spec = importlib.util.spec_from_file_location(
        f"serve_inspector_{id(fixture_root)}", SERVE_PATH)
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    return serve


class TestServeApiAgentHTTP(InspectorFixtureCase):
    def setUp(self):
        super().setUp()
        # An out-of-root "secret" file — the traversal PoC must never read it.
        self.outside_dir = self.fixture_root / "outside_secret"
        self.outside_dir.mkdir()
        (self.outside_dir / "leaked.jsonl").write_text(
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": SECRET_MARKER}}) + "\n",
            encoding="utf-8",
        )
        self.serve = load_serve(self.fixture_root)

        import handler
        self.httpd = handler.QuietThreadingHTTPServer(
            ("127.0.0.1", 0), self.serve.DashboardHandler)
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

    def test_valid_id_returns_200_with_tail(self):
        full_id = "httphappy005abc"
        transcript = self.transcripts_root / f"agent-{full_id}.jsonl"
        transcript.write_text("\n".join([
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": "HTTP INSPECT PROMPT"}}),
            json.dumps({"type": "assistant", "message": {"content": "hello from tail"}}),
        ]) + "\n", encoding="utf-8")

        status, body = self._get(f"/api/agent?id={full_id[:10]}")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertIn("HTTP INSPECT PROMPT", payload["dispatch_prompt"])
        self.assertTrue(any("hello from tail" in e["text"] for e in payload["transcript_tail"]))

    def test_missing_id_param_is_400(self):
        status, _ = self._get("/api/agent?foo=bar")
        self.assertEqual(status, 400)

    def test_unknown_id_is_404(self):
        status, body = self._get("/api/agent?id=doesnotexist42")
        self.assertEqual(status, 404)
        self.assertNotIn(b"Traceback", body)

    def test_traversal_poc_never_leaks_secret(self):
        status, body = self._get("/api/agent?id=..%2Foutside_secret%2Fleaked")
        self.assertNotEqual(status, 200)
        self.assertNotIn(SECRET_MARKER.encode(), body)

    def test_wildcard_id_never_enumerates(self):
        status, body = self._get("/api/agent?id=*")
        self.assertNotEqual(status, 200)
        self.assertNotIn(SECRET_MARKER.encode(), body)


if __name__ == "__main__":
    unittest.main()
