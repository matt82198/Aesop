"""Regression test: extract_agent_dispatch_prompt() must redact credentials.

get_agent_detail() redacts the dispatch prompt via _redact_secrets() before
returning it, but the older extract_agent_dispatch_prompt() — exposed via a
public endpoint (ui/handler.py GET /agent?id=<id>) — returned the raw,
unredacted dispatch prompt. Dispatch prompts routinely embed API keys/bearer
tokens/credentials (e.g. pasted into a task description), so this was a
credential-leak surface reachable from the dashboard.

Run: python -m unittest tests.test_agent_dispatch_redaction
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

UI_DIR = Path(__file__).parent.parent / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

import config
import agents

ENV_KEYS = ("AESOP_ROOT", "AESOP_STATE_ROOT", "AESOP_TRANSCRIPTS_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")

# Assembled at runtime (not a literal) so the secret-scan pre-push gate
# doesn't flag this fixture as a real leaked credential.
_FAKE_TOKEN = "sk-" + "aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"


class AgentDispatchPromptRedactionTest(unittest.TestCase):
    """extract_agent_dispatch_prompt() must mask credentials in the prompt,
    matching the contract already enforced by get_agent_detail()."""

    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-redact-test-"))
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

    def _write_transcript(self, full_id, content):
        transcripts_subdir = self.transcripts_root / "subagents"
        transcripts_subdir.mkdir(exist_ok=True)
        transcript_file = transcripts_subdir / f"agent-{full_id}.jsonl"
        lines = [
            json.dumps({
                "type": "user",
                "parentUuid": None,
                "message": {"content": content},
            }),
            json.dumps({
                "type": "assistant",
                "model": "claude-haiku-4-5",
                "message": {"content": "ok"},
            }),
        ]
        transcript_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return transcript_file

    def test_string_dispatch_prompt_credential_is_redacted(self):
        """A plain-string dispatch prompt containing a credential must come
        back masked, not verbatim."""
        full_id = "a7815f98a4a97c1d"
        prompt = f"Deploy using API key: {_FAKE_TOKEN} then report status."
        self._write_transcript(full_id, prompt)

        result = agents.extract_agent_dispatch_prompt(full_id[:13])

        self.assertNotIn("error", result, result.get("error", ""))
        self.assertIn("dispatch_prompt", result)
        self.assertNotIn(_FAKE_TOKEN, result["dispatch_prompt"],
                          "raw credential leaked through extract_agent_dispatch_prompt()")
        self.assertIn("REDACTED", result["dispatch_prompt"])

    def test_content_block_list_dispatch_prompt_credential_is_redacted(self):
        """A dispatch prompt shaped as a content-block list (as real Claude
        Code transcripts sometimes emit) must be normalised to text AND
        redacted, matching get_agent_detail()'s handling."""
        full_id = "b8926fa9b5b087c2"
        content_blocks = [
            {"type": "text", "text": f"Bearer {_FAKE_TOKEN} authorizes this task."},
        ]
        self._write_transcript(full_id, content_blocks)

        result = agents.extract_agent_dispatch_prompt(full_id[:13])

        self.assertNotIn("error", result, result.get("error", ""))
        self.assertIsInstance(result["dispatch_prompt"], str)
        self.assertNotIn(_FAKE_TOKEN, result["dispatch_prompt"],
                          "raw credential leaked through content-block dispatch prompt")
        self.assertIn("REDACTED", result["dispatch_prompt"])

    def test_prompt_without_credential_is_unaffected(self):
        """Sanity check: redaction must not mangle ordinary prompt text."""
        full_id = "c9037fb0c6c198d3"
        prompt = "Investigate the failing test in tests/test_agents.py and fix it."
        self._write_transcript(full_id, prompt)

        result = agents.extract_agent_dispatch_prompt(full_id[:13])

        self.assertNotIn("error", result, result.get("error", ""))
        self.assertEqual(result["dispatch_prompt"], prompt)


if __name__ == "__main__":
    unittest.main()
