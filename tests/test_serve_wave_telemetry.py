"""Wave telemetry backend tests — GET /api/wave/telemetry.

Contract under test:
  - GET /api/wave/telemetry — current wave phase info, cost metrics, and top blocker,
                              read at call time (no caching).
  - Response shape: {"wave": str, "phase": str, "blocker": str, "tokens_used": int,
                     "top_model": str, "ok_rate": float}
  - Reads from STATE.md (phase), AUDIT-BACKLOG.md (top blocker), and the cost ledger
    (via cost.py) at call time.

Isolation: every test binds serve.py to a throwaway fixture AESOP_ROOT /
AESOP_STATE_ROOT so nothing touches the real repo state (pattern from
tests/test_api_state.py).

Run: python -m unittest tests.test_serve_wave_telemetry
"""
import http.client
import importlib.util
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVE_PATH = Path(__file__).parent.parent / "ui" / "serve.py"
UI_PATH = Path(__file__).parent.parent / "ui"

ENV_KEYS = ("AESOP_ROOT", "AESOP_TRANSCRIPTS_ROOT", "AESOP_STATE_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")

# Fixture STATE.md with wave and phase info
FIXTURE_STATE_MD = """# STATE — aesop refinement loop

## Phase: `wave-rc.2: build` (2026-07-17, current)
Current phase focuses on wave-rc.2 build work.

## NEXT STEPS
1. Complete wave-rc.2 implementation
2. Run full test suite
3. Merge to main
"""

# Fixture AUDIT-BACKLOG.md with P0 items
FIXTURE_BACKLOG_MD = """# AUDIT-BACKLOG — aesop audit findings

## P0

- 🔵 **[ui] Dashboard wave telemetry tile**
- ⬜ **[test] Complete wave telemetry tests**
- ✅ **[sec] Fix CSRF origin check**

## P1

- ⬜ **[perf] SSE keepalive tuning**
"""

# Fixture ledger for cost data
FIXTURE_LEDGER = """| timestamp | agent_type | model | duration | tokens_in | tokens_out | verdict |
|---|---|---|---|---|---|---|
| 2026-07-17T10:00:00 | Agent | claude-haiku-4-5 | 12 | 500 | 1200 | OK |
| 2026-07-17T10:05:00 | Agent | claude-haiku-4-5 | 8 | 300 | 800 | OK |
| 2026-07-17T10:10:00 | Agent | claude-sonnet-4-5 | 15 | 800 | 600 | FAILED |
"""

# Fixture orchestrator-status.json (fresh, <24h) — generated with fresh timestamp
def _get_fresh_orch_status():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    updated_at = (now - timedelta(hours=12)).isoformat()
    return f"""{{
  "id": "main",
  "role": "orchestrator",
  "parent_id": null,
  "activity": "dispatching wave-rc.3",
  "phase": "wave-rc.3: dispatch",
  "updated_at": "{updated_at}"
}}"""

# Fixture orchestrator-status.json (stale, >24h) — generated with stale timestamp
def _get_stale_orch_status():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    updated_at = (now - timedelta(hours=30)).isoformat()
    return f"""{{
  "id": "main",
  "role": "orchestrator",
  "parent_id": null,
  "activity": "old activity",
  "phase": "wave-rc.2",
  "updated_at": "{updated_at}"
}}"""


def load_serve(fixture_root, extra_env=None):
    """Import a fresh serve module instance bound to a fixture AESOP_ROOT."""
    os.environ["AESOP_ROOT"] = str(fixture_root)
    os.environ["AESOP_STATE_ROOT"] = str(fixture_root / "state")
    for k, v in (extra_env or {}).items():
        os.environ[k] = str(v)
    spec = importlib.util.spec_from_file_location(
        f"serve_wave_telemetry_{id(fixture_root)}", SERVE_PATH)
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    return serve


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class WaveTelemetryFixtureCase(unittest.TestCase):
    """Base: fixture root + live ThreadingHTTPServer bound to a fresh serve import."""

    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-wave-telemetry-test-"))
        (self.fixture_root / "state" / "ledger").mkdir(parents=True)
        (self.fixture_root / "transcripts").mkdir()
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.fixture_root / "transcripts")
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"

        # Write fixture files
        (self.fixture_root / "STATE.md").write_text(FIXTURE_STATE_MD, encoding="utf-8")
        (self.fixture_root / "AUDIT-BACKLOG.md").write_text(FIXTURE_BACKLOG_MD, encoding="utf-8")
        (self.fixture_root / "state" / "ledger" / "OUTCOMES-LEDGER.md").write_text(
            FIXTURE_LEDGER, encoding="utf-8")

        self.serve = load_serve(self.fixture_root)
        self.token = self.serve.SESSION_TOKEN
        self.assertTrue(self.token, "fixture must produce a session token")

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
            self.serve._collector_stop_event.set()
            self.httpd.shutdown()
            self.httpd.server_close()
            self.server_thread.join(timeout=3)
        finally:
            for k, v in self._saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(self.fixture_root, ignore_errors=True)

    def _request(self, method, path, body=None, headers=None):
        """One HTTP request; retries transient Windows socket aborts."""
        last = None
        for _ in range(3):
            con = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                con.request(method, path, body=body, headers=headers or {})
                resp = con.getresponse()
                return resp.status, dict(resp.getheaders()), resp.read()
            except (ConnectionAbortedError, ConnectionResetError,
                    http.client.RemoteDisconnected) as e:
                last = e
                continue
            finally:
                con.close()
        raise last

    def _get_json(self, path, headers=None):
        status, hdrs, body = self._request("GET", path, headers=headers)
        return status, hdrs, json.loads(body.decode("utf-8"))


class GetWaveTelemetry(WaveTelemetryFixtureCase):
    """GET /api/wave/telemetry — wave phase, blocker, and cost metrics."""

    def test_wave_telemetry_endpoint_exists(self):
        """GET /api/wave/telemetry returns 200 and valid JSON."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        self.assertIn("wave", body)
        self.assertIn("phase", body)
        self.assertIn("blocker", body)
        self.assertIn("tokens_used", body)
        self.assertIn("top_model", body)
        self.assertIn("ok_rate", body)

    def test_wave_telemetry_phase_from_state_md(self):
        """Wave telemetry extracts phase from STATE.md."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should extract "wave-rc.2: build" from the fixture
        self.assertTrue(
            "rc.2" in body["phase"].lower() or "wave" in body["phase"].lower(),
            f"Phase should contain 'rc.2' or 'wave': {body['phase']}"
        )

    def test_wave_telemetry_blocker_from_backlog(self):
        """Wave telemetry extracts top P0 blocker from AUDIT-BACKLOG.md."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should extract the 🔵 (inflight) item from P0
        blocker = body["blocker"]
        self.assertNotEqual(blocker, "unknown")
        # Should contain part of the title
        self.assertTrue(
            "telemetry" in blocker.lower() or "dashboard" in blocker.lower(),
            f"Blocker '{blocker}' should mention telemetry or dashboard"
        )

    def test_wave_telemetry_cost_metrics(self):
        """Wave telemetry computes cost metrics from ledger."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should have cost data from ledger
        self.assertGreater(body["tokens_used"], 0)
        self.assertGreater(body["ok_rate"], 0)
        # Top model should be one of the models in the ledger
        self.assertIn(
            body["top_model"].lower(),
            ["haiku", "sonnet", "opus", "unknown"]
        )

    def test_wave_telemetry_ok_rate_is_valid(self):
        """Wave telemetry OK rate is between 0 and 1."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        ok_rate = body["ok_rate"]
        self.assertGreaterEqual(ok_rate, 0.0)
        self.assertLessEqual(ok_rate, 1.0)

    def test_wave_telemetry_no_cache_header(self):
        """GET /api/wave/telemetry returns no-cache headers (read at call time)."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        cache_control = hdrs.get("Cache-Control", "")
        self.assertIn("no-cache", cache_control)

    def test_wave_telemetry_content_type_json(self):
        """GET /api/wave/telemetry returns application/json content type."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        content_type = hdrs.get("Content-Type", "")
        self.assertIn("application/json", content_type)


class MissingFiles(WaveTelemetryFixtureCase):
    """Wave telemetry graceful degradation when files are missing."""

    def test_wave_telemetry_missing_state_md(self):
        """Wave telemetry degrades gracefully when STATE.md is missing."""
        (self.fixture_root / "STATE.md").unlink()
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should return "unknown" phase, not error
        self.assertEqual(body["phase"], "unknown")

    def test_wave_telemetry_missing_backlog(self):
        """Wave telemetry degrades gracefully when AUDIT-BACKLOG.md is missing."""
        (self.fixture_root / "AUDIT-BACKLOG.md").unlink()
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should return "unknown" blocker, not error
        self.assertEqual(body["blocker"], "unknown")

    def test_wave_telemetry_missing_ledger(self):
        """Wave telemetry degrades gracefully when ledger is missing."""
        (self.fixture_root / "state" / "ledger" / "OUTCOMES-LEDGER.md").unlink()
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should have zero tokens, not error
        self.assertEqual(body["tokens_used"], 0)


class OrchestratorStatusSource(WaveTelemetryFixtureCase):
    """Wave telemetry source selection: orchestrator-status.json vs STATE.md."""

    def test_wave_telemetry_fresh_orchestrator_status_wins(self):
        """Fresh orchestrator-status.json (<24h) is preferred over STATE.md."""
        # Write fresh orchestrator status
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            _get_fresh_orch_status(), encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should extract phase from orchestrator-status.json
        self.assertIn("rc.3", body["phase"].lower())
        # Should indicate source
        self.assertEqual(body["source"], "orchestrator-status")

    def test_wave_telemetry_stale_orchestrator_status_falls_back(self):
        """Stale orchestrator-status.json (>24h) falls back to STATE.md."""
        # Write stale orchestrator status
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            _get_stale_orch_status(), encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should fall back to STATE.md phase
        self.assertTrue(
            "rc.2" in body["phase"].lower() or "wave" in body["phase"].lower(),
            f"Phase should contain 'rc.2' or 'wave': {body['phase']}"
        )
        # Should indicate fallback source
        self.assertEqual(body["source"], "state-md")

    def test_wave_telemetry_missing_orchestrator_status_falls_back(self):
        """Missing orchestrator-status.json falls back to STATE.md."""
        # Don't create orchestrator-status.json
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should fall back to STATE.md phase
        self.assertTrue(
            "rc.2" in body["phase"].lower() or "wave" in body["phase"].lower(),
            f"Phase should contain 'rc.2' or 'wave': {body['phase']}"
        )
        # Should indicate fallback source
        self.assertEqual(body["source"], "state-md")

    def test_wave_telemetry_malformed_orchestrator_status_degrades(self):
        """Malformed orchestrator-status.json degrades gracefully."""
        # Write malformed JSON
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            "{invalid json", encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should fall back to STATE.md
        self.assertTrue(
            "rc.2" in body["phase"].lower() or "wave" in body["phase"].lower(),
            f"Phase should contain 'rc.2' or 'wave': {body['phase']}"
        )
        self.assertEqual(body["source"], "state-md")

    def test_wave_telemetry_orchestrator_status_missing_updated_at(self):
        """Orchestrator status without updated_at field degrades gracefully."""
        # Write orchestrator status without updated_at
        bad_status = """{
  "id": "main",
  "role": "orchestrator",
  "activity": "test",
  "phase": "wave-test"
}"""
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            bad_status, encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should fall back to STATE.md
        self.assertEqual(body["source"], "state-md")

    def test_wave_telemetry_source_field_always_present(self):
        """Source field is always present in the response."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Source field should be present and valid
        self.assertIn("source", body)
        self.assertIn(body["source"], ["orchestrator-status", "state-md", "error"])

    def test_wave_telemetry_burn_rate_fields_present(self):
        """Wave telemetry includes burn-rate and projection fields."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should have burn-rate fields
        self.assertIn("tokens_burned_per_min", body)
        self.assertIn("projected_total_tokens", body)
        self.assertIn("cost_ceiling_exceeded", body)

    def test_wave_telemetry_burn_rate_types(self):
        """Wave telemetry burn-rate fields have correct types."""
        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Check types
        self.assertIsInstance(body["tokens_burned_per_min"], (int, float))
        self.assertGreaterEqual(body["tokens_burned_per_min"], 0.0)
        self.assertIsInstance(body["projected_total_tokens"], int)
        self.assertGreaterEqual(body["projected_total_tokens"], 0)
        self.assertIsInstance(body["cost_ceiling_exceeded"], bool)

    def test_wave_telemetry_future_dated_orchestrator_status_falls_back(self):
        """Future-dated orchestrator-status.json (P3 bug fix) falls back to STATE.md.

        If orchestrator-status.json has a future-dated timestamp (beyond ~60s clock skew),
        it's treated as corrupted and not fresh, so the tool falls back to STATE.md.
        """
        from datetime import datetime, timezone, timedelta
        # Create future-dated orchestrator status (100 seconds in the future)
        future_time = (datetime.now(timezone.utc) + timedelta(seconds=100)).isoformat()
        future_status = f"""{{
  "id": "main",
  "role": "orchestrator",
  "activity": "dispatching",
  "phase": "wave-999-future",
  "updated_at": "{future_time}"
}}"""
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            future_status, encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should fall back to STATE.md because future-dated status is not fresh
        self.assertTrue(
            "rc.2" in body["phase"].lower() or "wave" in body["phase"].lower(),
            f"Phase should fall back to STATE.md (rc.2 or wave): {body['phase']}"
        )
        self.assertEqual(body["source"], "state-md", "Should fall back to state-md for future-dated status")

    def test_wave_telemetry_wave_extraction_from_phase(self):
        """Wave extraction from orchestrator-status.json properly parses wave-N-phase format.

        If orchestrator-status.json has phase='wave-26-verify', the wave field should be
        'wave-26', not 'wave'.
        """
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        fresh_timestamp = (now - timedelta(hours=6)).isoformat()
        orch_status = f"""{{
  "id": "main",
  "role": "orchestrator",
  "activity": "verifying wave-26",
  "phase": "wave-26-verify",
  "updated_at": "{fresh_timestamp}"
}}"""
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            orch_status, encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should extract "wave-26" from "wave-26-verify", not just "wave"
        self.assertIn("26", body["wave"], f"Wave should contain '26', got: {body['wave']}")
        self.assertNotEqual(body["wave"], "wave", "Wave should not be just 'wave'")
        self.assertEqual(body["phase"], "wave-26-verify")

    def test_wave_telemetry_slight_future_date_rejected(self):
        """Even slightly future-dated timestamps (>0s) should be rejected (P2 bug fix).

        If orchestrator-status.json has a timestamp 30 seconds in the future,
        it should fall back to STATE.md (not treat it as fresh).
        """
        from datetime import datetime, timezone, timedelta
        # Create slightly future-dated orchestrator status (30 seconds in the future)
        future_time = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
        future_status = f"""{{
  "id": "main",
  "role": "orchestrator",
  "activity": "dispatching",
  "phase": "wave-999-future",
  "updated_at": "{future_time}"
}}"""
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            future_status, encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should reject even slightly future-dated status and fall back to STATE.md
        self.assertTrue(
            "rc.2" in body["phase"].lower() or "wave" in body["phase"].lower(),
            f"Phase should fall back to STATE.md (rc.2 or wave): {body['phase']}"
        )
        self.assertEqual(body["source"], "state-md", "Should fall back to state-md for ANY future-dated status")

    def test_wave_telemetry_wave_rc_format_extraction(self):
        """Wave extraction handles wave-rc.2 format correctly (P3 bug fix).

        If orchestrator-status.json has phase='wave-rc.2: build' (release candidate format),
        the orchestrator-status regex should extract 'wave-rc' (preferred), not fall back to 'rc.2'.
        """
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        fresh_timestamp = (now - timedelta(hours=6)).isoformat()
        orch_status = f"""{{
  "id": "main",
  "role": "orchestrator",
  "activity": "building wave-rc.2",
  "phase": "wave-rc.2: build",
  "updated_at": "{fresh_timestamp}"
}}"""
        (self.fixture_root / "state" / "orchestrator-status.json").write_text(
            orch_status, encoding="utf-8")

        status, hdrs, body = self._get_json("/api/wave/telemetry")
        self.assertEqual(status, 200)

        # Should extract "wave-rc" from "wave-rc.2: build", not just "rc.2"
        # The orchestrator-status source is preferred; it should extract the full wave identifier
        wave = body["wave"].lower()
        self.assertTrue(
            "wave-rc" in wave,
            f"Wave should include 'wave-rc' when source is orchestrator-status: got {wave}"
        )
        self.assertNotIn("wave-rc.2: build", body["wave"], "Wave should not include ': build' suffix")


if __name__ == "__main__":
    unittest.main()
