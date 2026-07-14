"""Direct module-isolation unit tests for ui/agents.py (wave-10 P0 seam tests,
promised follow-up to the wave-9 collectors/agents/sse split).

These tests `import agents` directly — no HTTP server, no importlib-loading of
serve.py. Security focus: extract_agent_dispatch_prompt() must reject
path-traversal and glob-metacharacter sequences BEFORE touching disk (no
exception, no file access outside config.TRANSCRIPTS_ROOT). Also covers
get_fleet_agents() graceful degradation when dash-extra.mjs / node are absent,
and its 13-char-id collision de-dup suffixing.

Run: python -m pytest tests/test_agents.py -q
     python -m unittest tests.test_agents
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

UI_DIR = Path(__file__).parent.parent / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

import config  # noqa: E402
import agents  # noqa: E402

ENV_KEYS = ("AESOP_ROOT", "AESOP_STATE_ROOT", "AESOP_TRANSCRIPTS_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")

SECRET_MARKER = "TOP_SECRET_CONTENT_DO_NOT_LEAK"

# Ids that must be rejected before extract_agent_dispatch_prompt() ever builds
# a glob pattern or touches config.TRANSCRIPTS_ROOT: ".." traversal (either
# slash style), an absolute-looking path, bare/suffixed glob metacharacters,
# and a backslash.
FORBIDDEN_AGENT_IDS = [
    "../outside_secret/leaked",
    "..\\outside_secret\\leaked",
    "/etc/passwd",
    "*",
    "?",
    "[abc]",
    "a\\b",
    "../../secret*",
    "C:/Users/whoever/outside_secret/leaked",
]


class AgentsFixtureCase(unittest.TestCase):
    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-agents-test-"))
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


# ------------------------------------------------------------------------------
# extract_agent_dispatch_prompt: security — reject before touching disk
# ------------------------------------------------------------------------------

class TestExtractAgentDispatchPromptSecurity(AgentsFixtureCase):
    def setUp(self):
        super().setUp()
        # A "secret" file sitting OUTSIDE the transcripts root, sibling dir —
        # if any forbidden id ever reached the glob/open stage this would leak.
        self.outside_dir = self.fixture_root / "outside_secret"
        self.outside_dir.mkdir()
        (self.outside_dir / "leaked.output").write_text(
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": SECRET_MARKER}}) + "\n",
            encoding="utf-8",
        )

    def test_forbidden_ids_are_rejected_without_exception_or_leak(self):
        for bad_id in FORBIDDEN_AGENT_IDS:
            with self.subTest(agent_id=bad_id):
                result = agents.extract_agent_dispatch_prompt(bad_id)
                self.assertIsInstance(result, dict)
                self.assertTrue(result.get("invalid"), f"expected invalid=True for {bad_id!r}: {result}")
                self.assertIn("error", result)
                self.assertNotIn("dispatch_prompt", result)
                self.assertNotIn(SECRET_MARKER, json.dumps(result))

    def test_forbidden_ids_rejected_even_when_transcripts_root_does_not_exist(self):
        # Point TRANSCRIPTS_ROOT at a path that was never created. The forbidden
        # check must fire before any .exists()/.glob() call touches the
        # filesystem, so this must behave identically to the happy-path fixture.
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.fixture_root / "does-not-exist")
        config.reload()

        for bad_id in ("../x", "*", "a\\b"):
            with self.subTest(agent_id=bad_id):
                result = agents.extract_agent_dispatch_prompt(bad_id)
                self.assertTrue(result.get("invalid"))
                self.assertNotIn("dispatch_prompt", result)

    def test_empty_agent_id_is_rejected(self):
        result = agents.extract_agent_dispatch_prompt("")
        self.assertTrue(result.get("invalid"))
        self.assertIn("error", result)


class TestExtractAgentDispatchPromptHappyPath(AgentsFixtureCase):
    def test_valid_opaque_id_prefix_matches_full_transcript(self):
        full_id = "abc123def456fedcba9876"
        transcript = self.transcripts_root / f"agent-{full_id}.jsonl"
        lines = [
            json.dumps({"type": "user", "parentUuid": None,
                        "message": {"content": "FIXTURE DISPATCH PROMPT: fix the widget"}}),
            json.dumps({"type": "assistant", "model": "claude-haiku-4-5",
                        "message": {"content": "ok"}}),
        ]
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = agents.extract_agent_dispatch_prompt(full_id[:13])

        self.assertNotIn("error", result, result.get("error", ""))
        self.assertIn("FIXTURE DISPATCH PROMPT", result["dispatch_prompt"])
        self.assertEqual(result["dispatcher"], "main thread")
        self.assertEqual(result["model"], "claude-haiku-4-5")
        self.assertEqual(result["message_count"], 2)

    def test_no_matching_transcript_is_graceful_not_invalid(self):
        # A well-formed id with nothing on disk is a plain 404, not a rejected
        # (invalid=True) input — those are different failure modes.
        result = agents.extract_agent_dispatch_prompt("nonexistent000")
        self.assertIn("error", result)
        self.assertNotIn("invalid", result)


# ------------------------------------------------------------------------------
# get_fleet_agents: graceful degradation + id collision de-dup
# ------------------------------------------------------------------------------

class TestGetFleetAgents(AgentsFixtureCase):
    def test_missing_dash_extra_script_returns_empty_list(self):
        # No dash/ dir at all under fixture_root.
        self.assertFalse((self.fixture_root / "dash" / "dash-extra.mjs").exists())
        result = agents.get_fleet_agents()
        self.assertEqual(result, [])

    def test_node_missing_degrades_gracefully_no_throw(self):
        dash_dir = self.fixture_root / "dash"
        dash_dir.mkdir()
        (dash_dir / "dash-extra.mjs").write_text("// stub", encoding="utf-8")

        with mock.patch.object(agents.subprocess, "run", side_effect=FileNotFoundError("node not found")):
            result = agents.get_fleet_agents()

        self.assertEqual(result, [])

    def test_subprocess_timeout_degrades_gracefully_no_throw(self):
        import subprocess as subprocess_module

        dash_dir = self.fixture_root / "dash"
        dash_dir.mkdir()
        (dash_dir / "dash-extra.mjs").write_text("// stub", encoding="utf-8")

        with mock.patch.object(
            agents.subprocess, "run",
            side_effect=subprocess_module.TimeoutExpired(cmd="node", timeout=5),
        ):
            result = agents.get_fleet_agents()

        self.assertEqual(result, [])

    def test_malformed_json_stdout_degrades_gracefully_no_throw(self):
        dash_dir = self.fixture_root / "dash"
        dash_dir.mkdir()
        (dash_dir / "dash-extra.mjs").write_text("// stub", encoding="utf-8")

        fake_result = SimpleNamespace(returncode=0, stdout="{not valid json")
        with mock.patch.object(agents.subprocess, "run", return_value=fake_result):
            result = agents.get_fleet_agents()

        self.assertEqual(result, [])

    def test_13_char_id_collisions_are_deduped_with_numeric_suffix(self):
        dash_dir = self.fixture_root / "dash"
        dash_dir.mkdir()
        (dash_dir / "dash-extra.mjs").write_text("// stub", encoding="utf-8")

        raw_agents = [
            {"id": "abc1234567890", "name": "one"},
            {"id": "abc1234567890", "name": "two"},
            {"id": "abc1234567890", "name": "three"},
            {"id": "distinctid999", "name": "four"},
        ]
        fake_result = SimpleNamespace(returncode=0, stdout=json.dumps(raw_agents))
        with mock.patch.object(agents.subprocess, "run", return_value=fake_result):
            result = agents.get_fleet_agents()

        ids = [a["id"] for a in result]
        self.assertEqual(
            ids,
            ["abc1234567890", "abc1234567890-2", "abc1234567890-3", "distinctid999"],
        )
        # Original entries stay distinguishable by their other fields.
        self.assertEqual([a["name"] for a in result], ["one", "two", "three", "four"])


if __name__ == "__main__":
    unittest.main()
