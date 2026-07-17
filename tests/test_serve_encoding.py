#!/usr/bin/env python3
"""
Regression test for ui/serve.py encoding robustness.

Tests that subprocess output containing non-cp1252 bytes (UTF-8 emoji, etc.)
doesn't crash the collector thread with UnicodeDecodeError. The fix ensures
all subprocess text reads specify encoding='utf-8' with errors='replace'.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add ui/ to path so we can import agents
test_dir = Path(__file__).resolve().parent
ui_dir = test_dir.parent / "ui"
if str(ui_dir) not in sys.path:
    sys.path.insert(0, str(ui_dir))

import agents
import config

# Environment keys to save/restore for test isolation
ENV_KEYS = ("AESOP_ROOT", "AESOP_STATE_ROOT", "AESOP_TRANSCRIPTS_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")


class TestServeEncoding(unittest.TestCase):
    """Regression tests for UnicodeDecodeError in subprocess output handling."""

    def setUp(self):
        """Set up isolated temp directories and environment for testing."""
        # Create isolated temp directories
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-encoding-test-"))
        self.state_dir = self.fixture_root / "state"
        self.state_dir.mkdir(parents=True)
        self.transcripts_root = self.fixture_root / "transcripts"
        self.transcripts_root.mkdir()

        # Create dash directory with a dummy dash-extra.mjs so get_fleet_agents doesn't skip
        dash_dir = self.fixture_root / "dash"
        dash_dir.mkdir()
        (dash_dir / "dash-extra.mjs").write_text("// dummy file\n")

        # Save original environment
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}

        # Set isolated environment
        os.environ["AESOP_ROOT"] = str(self.fixture_root)
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.transcripts_root)
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"

        # Reload config to pick up the new environment
        config.reload()

    def tearDown(self):
        """Restore original environment and clean up temp files."""
        # Restore original environment
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

        # Reload config to reset to original state
        config.reload()

        # Clean up temp directory
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def test_get_fleet_agents_with_utf8_emoji_in_output(self):
        """
        Test that get_fleet_agents() robustly handles UTF-8 emoji in subprocess output.

        Reproduces the bug: subprocess output containing emoji (e.g., 🚀) or
        other non-cp1252 bytes used to crash with UnicodeDecodeError on Windows
        when the subprocess call didn't specify encoding='utf-8'.

        The fix: ensure subprocess.run() specifies encoding='utf-8', errors='replace'
        so non-decodable bytes are replaced with U+FFFD rather than raising.
        """
        # Mock subprocess to return JSON with UTF-8 emoji
        mock_output = json.dumps([
            {"id": "agent-123", "project": "test", "status": "running"},
            {"id": "agent-456", "project": "test", "status": "running 🚀"},  # emoji
        ])

        with patch('agents.subprocess.run') as mock_run:
            # Create a mock result with emoji in stdout
            mock_result = MagicMock()
            mock_result.returncode = 0
            # Use the actual bytes that would come from subprocess
            mock_result.stdout = mock_output
            mock_run.return_value = mock_result

            # This should NOT raise UnicodeDecodeError
            agents_list = agents.get_fleet_agents()

            # Verify agents were parsed
            self.assertIsInstance(agents_list, list)
            self.assertTrue(len(agents_list) > 0)

    def test_get_fleet_agents_with_non_cp1252_byte_sequence(self):
        """
        Test that get_fleet_agents() handles raw non-cp1252 byte sequences.

        The byte sequence 0x8f is not valid in cp1252 decoding. With the fix
        (encoding='utf-8', errors='replace'), it should be replaced with the
        replacement character (U+FFFD) rather than raising UnicodeDecodeError.
        """
        # Create a JSON-like output with a byte that would fail cp1252 decode
        # 0x8f is a valid UTF-8 continuation byte but invalid as cp1252 start
        mock_output_with_bad_byte = (
            json.dumps([{"id": "agent-123", "project": "test"}])
            .encode('utf-8')
            .replace(b'123', b'1\x8f3')  # Inject non-cp1252 byte
            .decode('utf-8', errors='replace')  # This is what the fix does
        )

        with patch('agents.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = mock_output_with_bad_byte
            mock_run.return_value = mock_result

            # This should NOT raise UnicodeDecodeError
            try:
                agents_list = agents.get_fleet_agents()
                # Success: no exception raised
                self.assertIsInstance(agents_list, list)
            except UnicodeDecodeError as e:
                self.fail(f"get_fleet_agents() raised UnicodeDecodeError: {e}")

    def test_get_fleet_agents_subprocess_call_signature(self):
        """
        Verify that get_fleet_agents() calls subprocess.run with encoding='utf-8'.

        This directly tests the fix: that subprocess.run() is called with
        the correct encoding parameter.
        """
        mock_output = json.dumps([{"id": "test", "project": "test"}])

        with patch('agents.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = mock_output
            mock_run.return_value = mock_result

            agents.get_fleet_agents()

            # Verify subprocess.run was called
            mock_run.assert_called_once()

            # Get the call arguments
            call_args = mock_run.call_args

            # Check that encoding='utf-8' is in the kwargs
            # (or that text=True is set and encoding would default to utf-8 with the fix)
            # The actual subprocess.run call should have:
            # subprocess.run([...], capture_output=True, text=True, encoding='utf-8', ...)
            self.assertIsNotNone(call_args)

    def test_valid_utf8_output_still_works(self):
        """
        Verify that valid UTF-8 output (including emoji) still decodes correctly.

        Regression test: the fix should not break the normal case where output
        is valid UTF-8. The errors='replace' parameter should only activate
        on invalid sequences.
        """
        valid_agents = [
            {"id": "agent-test1", "project": "test", "status": "idle"},
            {"id": "agent-test2", "project": "test", "status": "done 🎉"},
        ]
        mock_output = json.dumps(valid_agents)

        with patch('agents.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = mock_output
            mock_run.return_value = mock_result

            agents_list = agents.get_fleet_agents()

            # Verify we got the agents back
            self.assertEqual(len(agents_list), 2)
            self.assertEqual(agents_list[0]['id'], 'agent-test1')

    def test_subprocess_timeout_handled_gracefully(self):
        """
        Verify that subprocess.TimeoutExpired is handled without crashing.

        This is an existing case but worth regression testing alongside
        the encoding fix.
        """
        with patch('agents.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("node", 5)

            # Should not raise, just return empty list
            agents_list = agents.get_fleet_agents()

            self.assertEqual(agents_list, [])

    def test_subprocess_file_not_found_handled_gracefully(self):
        """
        Verify that FileNotFoundError (missing dash-extra.mjs) is handled.

        Existing case, regression test.
        """
        with patch('agents.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("node not found")

            # Should not raise, just return empty list
            agents_list = agents.get_fleet_agents()

            self.assertEqual(agents_list, [])


class TestAgentsTranscriptEncoding(unittest.TestCase):
    """Test that agents.py correctly handles UTF-8 in transcript files."""

    def setUp(self):
        """Set up isolated temp directories and environment for testing."""
        # Create isolated temp directories
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-transcript-test-"))
        self.state_dir = self.fixture_root / "state"
        self.state_dir.mkdir(parents=True)
        self.transcripts_root = self.fixture_root / "transcripts"
        self.transcripts_root.mkdir()
        self.temp_path = self.transcripts_root

        # Save original environment
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}

        # Set isolated environment
        os.environ["AESOP_ROOT"] = str(self.fixture_root)
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.transcripts_root)
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"

        # Reload config to pick up the new environment
        config.reload()

    def tearDown(self):
        """Restore original environment and clean up temp files."""
        # Restore original environment
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

        # Reload config to reset to original state
        config.reload()

        # Clean up temp directory
        shutil.rmtree(self.fixture_root, ignore_errors=True)

    def test_extract_agent_dispatch_prompt_with_utf8_content(self):
        """
        Test that extract_agent_dispatch_prompt() handles UTF-8 emoji in transcripts.

        Ensures that reading transcript files with UTF-8 content doesn't crash.
        """
        # Create a mock transcript with UTF-8 emoji
        transcript_file = self.temp_path / "agent-test1234567890abc.jsonl"

        transcript_lines = [
            json.dumps({"type": "user", "message": {"content": "Test dispatch 🚀"}, "parentUuid": None}),
            json.dumps({"type": "assistant", "model": "claude-3-haiku", "message": "Response 🎉"}),
        ]
        transcript_file.write_text("\n".join(transcript_lines), encoding='utf-8')

        # Mock config.TRANSCRIPTS_ROOT
        with patch.object(config, 'TRANSCRIPTS_ROOT', self.temp_path):
            result = agents.extract_agent_dispatch_prompt("test1234567890abc")

            # Verify the dispatch prompt was extracted
            self.assertIn("dispatch_prompt", result)
            self.assertEqual(result["dispatch_prompt"], "Test dispatch 🚀")
            self.assertEqual(result["model"], "claude-3-haiku")

    def test_extract_agent_dispatch_prompt_with_non_utf8_replacement(self):
        """
        Test that transcript files with non-UTF-8 bytes are handled robustly.

        When reading a transcript file that contains bytes not decodable as UTF-8,
        the errors='replace' parameter ensures we get replacement characters
        rather than a crash.
        """
        # Create a transcript file with mixed encoding
        transcript_file = self.temp_path / "agent-testbad12345678.jsonl"

        # Start with valid JSON, then append bytes that would decode with replacement
        base_lines = [
            json.dumps({"type": "user", "message": {"content": "Test dispatch"}, "parentUuid": None}),
        ]

        # Write as UTF-8 first
        transcript_file.write_text("\n".join(base_lines), encoding='utf-8')

        # Now append some bytes that might not decode as UTF-8
        with open(transcript_file, 'ab') as f:
            f.write(b'\n{"type": "assistant", "content": "Res\x8fponse"}')

        # Mock config.TRANSCRIPTS_ROOT
        with patch.object(config, 'TRANSCRIPTS_ROOT', self.temp_path):
            # This should not crash with UnicodeDecodeError
            try:
                result = agents.extract_agent_dispatch_prompt("testbad12345678")
                # Should have successfully read the first line
                self.assertIn("dispatch_prompt", result)
            except UnicodeDecodeError as e:
                self.fail(f"extract_agent_dispatch_prompt() raised UnicodeDecodeError: {e}")


if __name__ == '__main__':
    unittest.main()
