#!/usr/bin/env python3
"""Unit tests for fleet_ledger.py harvest() function with JSONL malformed line handling."""
import os
import sys
import subprocess
import tempfile
import unittest
import json
from pathlib import Path


class TestFleetLedgerHarvest(unittest.TestCase):
    """Test cases for fleet_ledger.py harvest command with type guards."""

    def setUp(self):
        """Create temporary directories and fixtures for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.ledger_script = Path(__file__).parent.parent / "tools" / "fleet_ledger.py"
        self.state_dir = Path(self.temp_dir) / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directories."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _run_ledger(self, *args, env_overrides=None):
        """Run fleet_ledger.py with arguments."""
        env = os.environ.copy()
        env["AESOP_STATE_ROOT"] = str(self.state_dir)
        if env_overrides:
            env.update(env_overrides)

        cmd = [sys.executable, str(self.ledger_script)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result

    def _create_task_output_file(self, jsonl_lines):
        """Create a task output file with JSONL content.

        Args:
            jsonl_lines: List of lines to write (already JSON-encoded strings)

        Returns:
            Path to the created output file
        """
        tasks_dir = Path(self.temp_dir) / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        output_file = tasks_dir / "agent.output"

        content = '\n'.join(jsonl_lines)
        output_file.write_text(content, encoding='utf-8')
        return output_file

    def _create_valid_agent_event(self, agent_id, model='haiku', timestamp='2024-07-13T10:00:00'):
        """Create a valid agent completion event JSON object.

        Args:
            agent_id: Agent UUID
            model: Model name
            timestamp: ISO timestamp

        Returns:
            JSON string of the object
        """
        event = {
            "agentId": agent_id,
            "timestamp": timestamp,
            "message": {
                "type": "message",
                "role": "assistant",
                "model": model,
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 100
                },
                "stop_reason": "end_turn"
            }
        }
        return json.dumps(event)

    def test_harvest_valid_jsonl_dict_lines(self):
        """Test harvest() with valid dict JSONL lines."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1", model="haiku"),
            self._create_valid_agent_event("agent-2", model="sonnet"),
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested", result.stdout)

    def test_harvest_scalar_int_line(self):
        """Test harvest() gracefully skips scalar int JSONL lines."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            "42",  # bare int - should be skipped
            self._create_valid_agent_event("agent-2"),
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested", result.stdout)
        self.assertIn("Skipped 1 malformed JSONL lines", result.stdout)

    def test_harvest_scalar_string_line(self):
        """Test harvest() gracefully skips scalar string JSONL lines."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            '"just a string"',  # bare string - should be skipped
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested", result.stdout)
        self.assertIn("Skipped 1 malformed JSONL lines", result.stdout)

    def test_harvest_mixed_valid_and_scalar_lines(self):
        """Test harvest() with mixed valid dict rows and scalar lines."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            "123",  # scalar int
            self._create_valid_agent_event("agent-2"),
            '"error message"',  # scalar string
            self._create_valid_agent_event("agent-3"),
            "3.14",  # scalar float
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested", result.stdout)
        # Should skip 3 scalar lines (int, string, float)
        self.assertIn("Skipped 3 malformed JSONL lines", result.stdout)

    def test_harvest_only_scalar_lines_no_crash(self):
        """Test harvest() doesn't crash when file contains only scalar lines."""
        jsonl_lines = [
            "42",
            '"error"',
            "3.14",
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        # Should not crash, should report 0 harvested and 3 skipped
        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested 0", result.stdout)
        self.assertIn("Skipped 3", result.stdout)

    def test_harvest_scalar_bool_line(self):
        """Test harvest() gracefully skips scalar boolean JSONL lines."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            "true",  # JSON boolean - should be skipped
            self._create_valid_agent_event("agent-2"),
            "false",  # JSON boolean - should be skipped
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested", result.stdout)
        self.assertIn("Skipped 2 malformed JSONL lines", result.stdout)

    def test_harvest_scalar_null_line(self):
        """Test harvest() gracefully skips null JSONL lines."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            "null",  # JSON null - should be skipped
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested", result.stdout)
        self.assertIn("Skipped 1 malformed JSONL lines", result.stdout)

    def test_harvest_doesnt_report_skip_when_none(self):
        """Test harvest() doesn't report skip message when no lines are skipped."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            self._create_valid_agent_event("agent-2"),
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Harvested", result.stdout)
        # Should NOT mention skipped if none were skipped
        self.assertNotIn("Skipped", result.stdout)

    def test_harvest_round_trip_with_scalars_mixed_in(self):
        """Test that valid dict lines are properly harvested when scalars are present."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import parse_ledger_rows
        finally:
            sys.path.pop(0)

        jsonl_lines = [
            self._create_valid_agent_event("agent-1", timestamp="2024-07-13T10:00:00"),
            "42",  # should be skipped
            self._create_valid_agent_event("agent-2", timestamp="2024-07-13T10:01:00"),
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)

        # Now parse the ledger to verify both valid events were captured
        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            # Should have harvested 2 rows (the 2 dict lines)
            self.assertEqual(len(rows), 2)

            # Verify the agents are present
            agent_ids = [row.get('iso_ts') for row in rows]
            self.assertIn("2024-07-13T10:00:00", agent_ids)
            self.assertIn("2024-07-13T10:01:00", agent_ids)
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)

    def test_harvest_preserves_existing_append_wave_behavior(self):
        """Test that harvest() doesn't break existing append-wave append behavior."""
        # First, use append-wave to add some rows
        report_dir = Path(self.temp_dir) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "workflow-report.json"

        report = {
            "tokens": {"buildOut": 100},
            "integration": {"green": True}
        }
        report_file.write_text(json.dumps(report), encoding='utf-8')

        result = self._run_ledger(
            "append-wave",
            "--report-file", str(report_file),
            "--wave", "1",
            "--phase", "build",
            "--timestamp", "2024-07-13T09:00:00"
        )
        self.assertEqual(result.returncode, 0)

        # Now run harvest with a mixed JSONL file (scalars + valid)
        jsonl_lines = [
            self._create_valid_agent_event("harvest-agent-1"),
            "42",  # should be skipped
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)

        # Verify both the append-wave and harvest rows exist
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import parse_ledger_rows
        finally:
            sys.path.pop(0)

        old_state_root = os.environ.get("AESOP_STATE_ROOT")
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)

        try:
            rows = parse_ledger_rows()
            # Should have at least 2 rows: 1 from append-wave, 1 from harvest
            self.assertGreaterEqual(len(rows), 2)

            # Verify append-wave row is still there
            append_wave_rows = [r for r in rows if r.get('wave') == 1]
            self.assertGreater(len(append_wave_rows), 0)
        finally:
            if old_state_root:
                os.environ["AESOP_STATE_ROOT"] = old_state_root
            else:
                os.environ.pop("AESOP_STATE_ROOT", None)

    def test_harvest_empty_lines_ignored(self):
        """Test that empty lines in JSONL are ignored (existing behavior)."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            "",  # empty line - should be silently ignored
            "",
            self._create_valid_agent_event("agent-2"),
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        # Empty lines don't count as skipped (they're filtered before JSON parsing)
        self.assertNotIn("Skipped", result.stdout)

    def test_harvest_json_decode_errors_ignored(self):
        """Test that invalid JSON (non-scalar) is ignored (existing behavior)."""
        jsonl_lines = [
            self._create_valid_agent_event("agent-1"),
            "{ invalid json }",  # malformed JSON - should be ignored silently
            self._create_valid_agent_event("agent-2"),
        ]
        self._create_task_output_file(jsonl_lines)

        env_overrides = {"AESOP_TEMP_ROOT": str(self.temp_dir)}
        result = self._run_ledger("harvest", env_overrides=env_overrides)

        self.assertEqual(result.returncode, 0)
        # JSON decode errors don't count as skipped (they're filtered before type check)
        self.assertNotIn("Skipped", result.stdout)


class TestFleetLedgerHarvestImportable(unittest.TestCase):
    """Test that harvest and common tools are importable."""

    def test_fleet_ledger_harvest_importable(self):
        """Test that fleet_ledger.harvest can be imported."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        try:
            from fleet_ledger import harvest, parse_ledger_rows
            self.assertTrue(callable(harvest))
            self.assertTrue(callable(parse_ledger_rows))
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
