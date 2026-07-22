#!/usr/bin/env python3
"""End-to-end tests for CodexDriver Phase 2 implementation.

Comprehensive offline tests proving:
  1. Happy path: FakeTransport supplies valid JSON -> files written, ok=True
  2. Retry: malformed-then-valid JSON triggers retry mechanism
  3. Fail-safe: always-malformed JSON -> clean failure, no files written
  4. Ownership: out-of-scope paths rejected wholesale
  5. Oversized files: pre-dispatch guard fails safe (transport never called)
  6. True e2e: RED stub + FakeTransport fix + run_command -> GREEN (offline proof)
  7. run_command: real subprocess execution
  8. worker_status: registry tracking
  9. verification_policy: tier->policy mapping
  10. probe unchanged: existing interface still passes

Tests use FakeTransport to avoid network/secrets. ONE live test (gated by
AESOP_CODEX_LIVE env var) exercises the real OpenAI transport; skipped in CI.

stdlib-only (unittest), ASCII-only, Windows + Linux safe.
No dependencies: no openai, no jsonschema, no pytest.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add driver/ to path for imports.
REPO = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO / "driver"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

import agent_driver as ad  # noqa: E402
from agent_driver import (  # noqa: E402
    DriverCapabilities,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
    ROLE_SETUP,
    ROLE_VERIFY,
    ROLE_WORKER,
    WORKER_DONE,
    WORKER_FAILED,
    WORKER_RUNNING,
    WORKER_UNKNOWN,
)
from codex_driver import CodexDriver, WORKER_PATCH_SCHEMA  # noqa: E402
from verification_policy import verification_policy  # noqa: E402


class FakeTransport:
    """Fake transport returning canned OpenAI-shaped responses.

    Preset response or scripted queue for testing retry logic.
    """

    def __init__(self, response=None, responses=None):
        """Initialize with a single response or a queue of responses.

        Args:
            response: single dict response (used for all calls).
            responses: list of dicts for each call (used in order; repeats last).
        """
        if response is not None:
            self.responses = [response]
            self._idx = 0
        elif responses is not None:
            self.responses = responses
            self._idx = 0
        else:
            self.responses = []
            self._idx = 0

    def __call__(self, payload):
        """Return the next response from the queue."""
        if not self.responses:
            raise RuntimeError("FakeTransport: no responses configured")
        response = self.responses[min(self._idx, len(self.responses) - 1)]
        self._idx += 1
        return response


def make_response(patch_dict, total_tokens=42):
    """Helper: build an OpenAI-shaped response containing JSON patch."""
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(patch_dict),
                },
            },
        ],
        "usage": {"total_tokens": total_tokens},
    }


class TestCodexDriverHappyPath(unittest.TestCase):
    def test_dispatch_with_single_file_replacement(self):
        """Valid schema JSON -> file written, ok=True, tokens tracked."""
        patch = {
            "files": [{"path": "test.py", "contents": "print(42)\n"}],
            "summary": "Fixed test.py",
            "done": True,
        }
        fake_transport = FakeTransport(response=make_response(patch, total_tokens=50))
        driver = CodexDriver(transport=fake_transport)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create initial file.
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print(0)\n")

            # Dispatch.
            request = WorkerRequest(
                prompt="Fix the test",
                owned_files=("test.py",),
                workdir=tmpdir,
                label="fix-test",
            )
            result = driver.dispatch_worker(request)

            # Assert success.
            self.assertTrue(result.ok)
            self.assertEqual(result.status, WORKER_DONE)
            self.assertEqual(result.tokens_spent, 50)
            self.assertEqual(result.files_written, ("test.py",))

            # Assert file was written.
            self.assertEqual(test_file.read_text(), "print(42)\n")
            self.assertEqual(result.structured["summary"], "Fixed test.py")


class TestCodexDriverRetry(unittest.TestCase):
    def test_malformed_then_valid_json_retries_once(self):
        """Malformed JSON on first attempt -> retry -> valid JSON -> success."""
        # First response: junk JSON.
        # Second response: valid patch.
        valid_patch = {
            "files": [{"path": "fix.py", "contents": "fixed"}],
            "summary": "Fixed",
            "done": True,
        }
        fake_transport = FakeTransport(
            responses=[
                {"choices": [{"message": {"content": "{ invalid json"}}], "usage": {"total_tokens": 10}},
                make_response(valid_patch, total_tokens=30),
            ]
        )
        driver = CodexDriver(transport=fake_transport, max_retries=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("fix.py").write_text("broken")

            request = WorkerRequest(
                prompt="Fix it",
                owned_files=("fix.py",),
                workdir=tmpdir,
            )
            result = driver.dispatch_worker(request)

            # Should succeed on second attempt.
            self.assertTrue(result.ok)
            self.assertEqual(result.status, WORKER_DONE)


class TestCodexDriverFailSafe(unittest.TestCase):
    def test_always_malformed_json_fails_clean(self):
        """Malformed JSON all attempts -> WORKER_FAILED, no files written."""
        junk = {"choices": [{"message": {"content": "not json"}}], "usage": {"total_tokens": 0}}
        fake_transport = FakeTransport(
            responses=[junk] * 3  # 3 failures (0 retries + 1 initial)
        )
        driver = CodexDriver(transport=fake_transport, max_retries=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            original = "original"
            test_file.write_text(original)

            request = WorkerRequest(
                prompt="Fix it",
                owned_files=("test.py",),
                workdir=tmpdir,
            )
            result = driver.dispatch_worker(request)

            # Should fail cleanly.
            self.assertFalse(result.ok)
            self.assertEqual(result.status, WORKER_FAILED)
            self.assertIn("validation failed", result.error)
            # File untouched.
            self.assertEqual(test_file.read_text(), original)


class TestCodexDriverOwnershipEnforcement(unittest.TestCase):
    def test_out_of_scope_path_rejected_wholesale(self):
        """Worker returns path NOT in owned_files -> WORKER_FAILED, no writes."""
        patch = {
            "files": [
                {"path": "owned.py", "contents": "ok"},
                {"path": "stolen.py", "contents": "hacked!"},  # NOT in owned_files
            ],
            "summary": "Sneaky",
            "done": False,
        }
        fake_transport = FakeTransport(response=make_response(patch))
        driver = CodexDriver(transport=fake_transport)

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("owned.py").write_text("original")

            request = WorkerRequest(
                prompt="Fix it",
                owned_files=("owned.py",),  # ONLY owned.py
                workdir=tmpdir,
            )
            result = driver.dispatch_worker(request)

            # Should reject the whole dispatch.
            self.assertFalse(result.ok)
            self.assertEqual(result.status, WORKER_FAILED)
            self.assertIn("out-of-scope", result.error)
            # Neither file written (all-or-nothing).
            self.assertEqual(Path(tmpdir).joinpath("owned.py").read_text(), "original")


class TestCodexDriverOversizedFiles(unittest.TestCase):
    def test_oversized_owned_files_fail_pre_dispatch(self):
        """Files exceed max_owned_bytes -> fail BEFORE transport call."""
        fake_transport = FakeTransport(response=make_response({"files": [], "summary": "", "done": False}))
        driver = CodexDriver(transport=fake_transport, max_owned_bytes=10)  # Tiny limit.

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("big.py").write_text("x" * 100)

            request = WorkerRequest(
                prompt="Fix it",
                owned_files=("big.py",),
                workdir=tmpdir,
            )
            result = driver.dispatch_worker(request)

            # Should fail pre-dispatch (context guard).
            self.assertFalse(result.ok)
            self.assertEqual(result.status, WORKER_FAILED)
            self.assertIn("exceed context budget", result.error)


class TestCodexDriverE2E(unittest.TestCase):
    """The core Phase-2 thesis: RED stub + model fix + orchestrator verification."""

    def test_red_to_green_via_model_fix(self):
        """Full e2e: broken unit test -> FakeTransport supplies fix -> run_command GREEN."""
        # RED: a module that fails its own test.
        broken_module = '''
def add(a, b):
    return a * b  # WRONG: should be +

'''

        broken_test = '''
import sys
import unittest
from pathlib import Path

# Add parent to path.
sys.path.insert(0, str(Path(__file__).parent))

from broken_module import add

class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

if __name__ == "__main__":
    unittest.main()
'''

        # FIX: correct module contents.
        fixed_module = '''
def add(a, b):
    return a + b  # FIXED

'''

        # Model's response: full-file replacement for the module.
        patch = {
            "files": [{"path": "broken_module.py", "contents": fixed_module}],
            "summary": "Fixed add() to use + instead of *",
            "done": True,
        }
        fake_transport = FakeTransport(response=make_response(patch))
        driver = CodexDriver(transport=fake_transport)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tmpdir_path.joinpath("broken_module.py").write_text(broken_module)
            tmpdir_path.joinpath("test_broken_module.py").write_text(broken_test)

            # 1. Verify test is RED before fix.
            result_before = driver.run_command(
                sys.executable + " -m unittest test_broken_module.TestAdd.test_add",
                cwd=tmpdir,
            )
            self.assertNotEqual(result_before.exit_code, 0, "Test should fail before fix")

            # 2. Dispatch worker to fix the module.
            request = WorkerRequest(
                prompt="Fix the add() function",
                owned_files=("broken_module.py",),
                workdir=tmpdir,
                label="fix-add-function",
            )
            fix_result = driver.dispatch_worker(request)
            self.assertTrue(fix_result.ok, f"Dispatch failed: {fix_result.error}")

            # 3. Verify test is GREEN after fix.
            result_after = driver.run_command(
                sys.executable + " -m unittest test_broken_module.TestAdd.test_add",
                cwd=tmpdir,
            )
            self.assertEqual(result_after.exit_code, 0, "Test should pass after fix")


class TestCodexDriverRunCommand(unittest.TestCase):
    def test_run_command_real_subprocess(self):
        """run_command executes real subprocess (not a mock)."""
        driver = CodexDriver(transport=lambda p: {})

        # Portable cross-platform test.
        result = driver.run_command(sys.executable + ' -c "print(42)"')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("42", result.stdout)

    def test_run_command_with_cwd(self):
        """run_command respects cwd argument."""
        driver = CodexDriver(transport=lambda p: {})

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a marker file in the temp dir.
            Path(tmpdir).joinpath("marker.txt").write_text("found")

            # Run a command that checks for the marker.
            if sys.platform == "win32":
                cmd = f'if exist marker.txt (exit /b 0) else (exit /b 1)'
            else:
                cmd = "[ -f marker.txt ] && exit 0 || exit 1"

            result = driver.run_command(cmd, cwd=tmpdir)
            self.assertEqual(result.exit_code, 0)


class TestCodexDriverWorkerStatus(unittest.TestCase):
    def test_worker_status_unknown_initially(self):
        """Unregistered worker -> UNKNOWN."""
        driver = CodexDriver(transport=lambda p: {})
        status = driver.worker_status("nonexistent")
        self.assertEqual(status.state, WORKER_UNKNOWN)

    def test_worker_status_done_after_dispatch(self):
        """After successful dispatch, worker_status reports DONE."""
        patch = {
            "files": [{"path": "x.py", "contents": "ok"}],
            "summary": "done",
            "done": True,
        }
        fake_transport = FakeTransport(response=make_response(patch))
        driver = CodexDriver(transport=fake_transport)

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("x.py").write_text("old")
            request = WorkerRequest(
                prompt="Fix",
                owned_files=("x.py",),
                workdir=tmpdir,
            )
            result = driver.dispatch_worker(request)
            worker_id = result.worker_id

            # Now check status.
            status = driver.worker_status(worker_id)
            self.assertEqual(status.state, WORKER_DONE)


class TestVerificationPolicy(unittest.TestCase):
    def test_tier_1_policy(self):
        """Tier 1 (Claude reference): light spot-check, no adversarial."""
        caps = DriverCapabilities(
            name="test",
            recommended_verification_tier=1,
            tool_use_accuracy=0.99,
        )
        policy = verification_policy(caps)
        self.assertFalse(policy["validate_all_json"])
        self.assertEqual(policy["spot_check_frac"], 0.10)
        self.assertEqual(policy["repair_cap"], 1)
        self.assertFalse(policy["require_adversarial_review"])

    def test_tier_2_policy(self):
        """Tier 2 (Codex): validate all, ~50% spot-check, mandatory adversarial."""
        caps = DriverCapabilities(
            name="test",
            recommended_verification_tier=2,
            tool_use_accuracy=0.92,
        )
        policy = verification_policy(caps)
        self.assertTrue(policy["validate_all_json"])
        self.assertEqual(policy["spot_check_frac"], 0.50)
        self.assertEqual(policy["repair_cap"], 2)
        self.assertTrue(policy["require_adversarial_review"])

    def test_tier_3_policy(self):
        """Tier 3: validate all, 100% spot-check."""
        caps = DriverCapabilities(
            name="test",
            recommended_verification_tier=3,
        )
        policy = verification_policy(caps)
        self.assertTrue(policy["validate_all_json"])
        self.assertEqual(policy["spot_check_frac"], 1.00)

    def test_tier_4_policy(self):
        """Tier 4: maximum scrutiny."""
        caps = DriverCapabilities(
            name="test",
            recommended_verification_tier=4,
        )
        policy = verification_policy(caps)
        self.assertTrue(policy["validate_all_json"])
        self.assertEqual(policy["spot_check_frac"], 1.00)
        self.assertEqual(policy["repair_cap"], 3)

    def test_codex_probe_yields_tier_2_policy(self):
        """CodexDriver probe -> Tier 2 policy."""
        driver = CodexDriver(transport=lambda p: {})
        caps = driver.probe_capabilities()
        policy = verification_policy(caps)

        # Assert Tier-2 values.
        self.assertTrue(policy["validate_all_json"])
        self.assertTrue(policy["require_adversarial_review"])
        self.assertEqual(policy["repair_cap"], 2)


class TestCodexProbeUnchanged(unittest.TestCase):
    """Verify probe_capabilities() still meets the existing spec."""

    def test_probe_returns_tier_2(self):
        driver = CodexDriver(transport=lambda p: {})
        caps = driver.probe_capabilities()
        self.assertEqual(caps.recommended_verification_tier, 2)

    def test_probe_no_filesystem_access(self):
        driver = CodexDriver(transport=lambda p: {})
        caps = driver.probe_capabilities()
        self.assertFalse(caps.worker_filesystem_access)

    def test_probe_no_shell_access(self):
        driver = CodexDriver(transport=lambda p: {})
        caps = driver.probe_capabilities()
        self.assertFalse(caps.worker_shell_access)

    def test_probe_accuracy_below_claude(self):
        from claude_code_driver import ClaudeCodeDriver  # noqa: E402
        codex = CodexDriver(transport=lambda p: {})
        claude = ClaudeCodeDriver()
        self.assertLess(codex.probe_capabilities().tool_use_accuracy,
                        claude.probe_capabilities().tool_use_accuracy)


@unittest.skipUnless(
    os.environ.get("AESOP_CODEX_LIVE") == "1" and os.environ.get("OPENAI_API_KEY"),
    "live OpenAI test; set AESOP_CODEX_LIVE=1 + OPENAI_API_KEY to run"
)
class TestCodexDriverLive(unittest.TestCase):
    """Live test against the real OpenAI API (skipped in CI by default)."""

    def test_live_e2e_with_real_api(self):
        """End-to-end test with real OpenAI API (gated by env var)."""
        # Use the real default_openai_transport.
        driver = CodexDriver()  # Will use default_openai_transport

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple broken module and test.
            Path(tmpdir).joinpath("math_helper.py").write_text(
                "def multiply(a, b):\n    return a + b  # WRONG\n"
            )
            Path(tmpdir).joinpath("test_math.py").write_text(
                "import unittest\n"
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).parent))\n"
                "from math_helper import multiply\n"
                "class Test(unittest.TestCase):\n"
                "    def test_multiply(self):\n"
                "        self.assertEqual(multiply(3, 4), 12)\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            )

            # Verify test fails before fix.
            before = driver.run_command(
                sys.executable + " -m unittest test_math.Test.test_multiply",
                cwd=tmpdir,
            )
            self.assertNotEqual(before.exit_code, 0)

            # Dispatch to fix.
            request = WorkerRequest(
                prompt=(
                    "Fix the multiply function to return a * b instead of a + b"
                ),
                owned_files=("math_helper.py",),
                workdir=tmpdir,
            )
            result = driver.dispatch_worker(request)
            self.assertTrue(result.ok, f"Live dispatch failed: {result.error}")

            # Verify test passes after fix.
            after = driver.run_command(
                sys.executable + " -m unittest test_math.Test.test_multiply",
                cwd=tmpdir,
            )
            self.assertEqual(after.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
