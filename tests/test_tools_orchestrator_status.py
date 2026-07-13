"""Tests for tools/orchestrator_status.py — set/clear roundtrip and encoding regression."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "orchestrator_status.py"


def run_tool(args, state_root):
    env = dict(os.environ, AESOP_STATE_ROOT=str(state_root))
    return subprocess.run([sys.executable, str(TOOL)] + args,
                          capture_output=True, text=True, env=env)


class TestOrchestratorStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_is_valid_utf8(self):
        # Regression: shipped once with a cp1252 em-dash byte -> SyntaxError on every run
        TOOL.read_bytes().decode("utf-8")

    def test_set_writes_normalized_status(self):
        r = run_tool(["set", "--activity", "testing", "--phase", "audit"], self.state)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((self.state / "orchestrator-status.json").read_text(encoding="utf-8"))
        self.assertEqual(data["activity"], "testing")
        self.assertEqual(data["phase"], "audit")
        self.assertTrue(data["updated_at"].endswith("Z"))
        self.assertIn("role", data)

    def test_clear_removes_file(self):
        run_tool(["set", "--activity", "x", "--phase", "y"], self.state)
        r = run_tool(["clear"], self.state)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.state / "orchestrator-status.json").exists())

    def test_clear_when_absent_is_graceful(self):
        r = run_tool(["clear"], self.state)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
