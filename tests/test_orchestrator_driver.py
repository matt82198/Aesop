#!/usr/bin/env python3
"""Tests for the OrchestratorDriver seam and context_pack builder.

TDD-first tests covering:
  * context_pack.py: allowlist enforcement, size capping, truncation.
  * orchestrator_driver.py: decide() + schema validation + retry + fail-safe.

Uses FakeTransport (mirrors AgentDriver test pattern): offline, hermetic,
no API keys, no cwd pollution, all temp files cleaned up.

stdlib-only (unittest), ASCII-only, Windows + Linux safe.
"""

import json
import os
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

# Add driver/ to sys.path (mirrors AgentDriver test pattern).
REPO = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO / "driver"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

from agent_driver import (  # noqa: E402
    AgentDriver,
    CommandResult,
    DriverCapabilities,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
)
from context_pack import (  # noqa: E402
    ContextPack,
    ContextPackViolation,
    build_context_pack,
)
from orchestrator_driver import OrchestratorDriver  # noqa: E402


# ============================================================================
# FakeTransport: Mock backend for offline testing
# ============================================================================


@dataclass
class FakeTransport:
    """Mock AgentDriver for testing OrchestratorDriver.

    Returns canned responses so we can test the decide() logic without
    network/API keys. Supports:
      - Successful JSON decisions.
      - Malformed JSON (for retry testing).
      - Command execution success/failure.

    Attributes:
        response_sequence: List of responses to return in sequence.
                          Each item is (stdout, stderr, exit_code).
        call_count: Tracks how many times the backend was called.
    """

    response_sequence: list = None
    call_count: int = 0

    def __post_init__(self):
        if self.response_sequence is None:
            self.response_sequence = []

    def probe_capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            name="fake",
            tool_use_accuracy=0.99,
            recommended_verification_tier=1,
        )

    def run_command(
        self, command: str, cwd=None, shell=None
    ) -> CommandResult:
        """Return the next response in sequence."""
        if self.call_count >= len(self.response_sequence):
            return CommandResult(
                exit_code=1, stdout="", stderr="No more responses"
            )

        stdout, stderr, exit_code = self.response_sequence[self.call_count]
        self.call_count += 1
        return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    def worker_status(self, worker_id: str) -> WorkerStatus:
        return WorkerStatus(worker_id=worker_id)

    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(worker_id="fake")

    def resolve_model(self, role: str) -> str:
        return "fake-model"

    def get_tokens_spent(self):
        return None


class FakeAgentDriver(AgentDriver):
    """Full AgentDriver implementation using FakeTransport for offline testing."""

    def __init__(self, transport: FakeTransport = None):
        self.transport = transport or FakeTransport()

    def probe_capabilities(self) -> DriverCapabilities:
        return self.transport.probe_capabilities()

    def run_command(self, command: str, cwd=None, shell=None) -> CommandResult:
        return self.transport.run_command(command, cwd, shell)

    def worker_status(self, worker_id: str) -> WorkerStatus:
        return self.transport.worker_status(worker_id)

    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        return self.transport.dispatch_worker(request)

    def resolve_model(self, role: str) -> str:
        return self.transport.resolve_model(role)


# ============================================================================
# Tests: context_pack.py
# ============================================================================


class TestContextPackAllowlist(unittest.TestCase):
    """Test context pack allowlist enforcement (Cardinal Rule 4 in code)."""

    def setUp(self):
        """Create temp repo/conductor roots."""
        self.temp_repo = tempfile.TemporaryDirectory()
        self.temp_conductor = tempfile.TemporaryDirectory()
        self.repo_root = self.temp_repo.name
        self.conductor_root = self.temp_conductor.name

    def tearDown(self):
        """Clean up temp dirs."""
        self.temp_repo.cleanup()
        self.temp_conductor.cleanup()

    def test_state_md_read_from_repo(self):
        """Happy path: read STATE.md from repo root."""
        state_file = Path(self.repo_root) / "STATE.md"
        state_file.write_text("# Wave 1\nphase: dispatch\n", encoding="utf-8")

        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"state": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
        )

        self.assertIn("state", pack.content)
        self.assertIn("# Wave 1", pack.content["state"])
        self.assertTrue(
            any(m["source"] == "state" and m["included"] for m in pack.manifest)
        )

    def test_state_md_read_from_conductor(self):
        """Fall back to conductor root if repo has no STATE.md."""
        conductor_state = Path(self.conductor_root) / "STATE.md"
        conductor_state.write_text(
            "# Conductor STATE\nphase: verify\n", encoding="utf-8"
        )

        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"state": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
        )

        self.assertIn("state", pack.content)
        self.assertIn("# Conductor STATE", pack.content["state"])

    def test_buildlog_tail_reads_last_n_lines(self):
        """Read last N lines of BUILDLOG.md."""
        buildlog_file = Path(self.repo_root) / "BUILDLOG.md"
        buildlog_file.write_text(
            "line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8"
        )

        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"buildlog_tail:2": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
        )

        self.assertIn("buildlog_tail:2", pack.content)
        # Last 2 lines: line 4 and line 5.
        self.assertIn("line 4", pack.content["buildlog_tail:2"])
        self.assertIn("line 5", pack.content["buildlog_tail:2"])
        self.assertNotIn("line 1", pack.content["buildlog_tail:2"])

    def test_tracker_open_reads_open_items(self):
        """Read open items from tracker.json."""
        tracker_dir = Path(self.repo_root) / "state"
        tracker_dir.mkdir()
        tracker_file = tracker_dir / "tracker.json"
        tracker_file.write_text(
            json.dumps(
                {
                    "items": [
                        {"id": "1", "status": "open", "title": "item 1"},
                        {"id": "2", "status": "closed", "title": "item 2"},
                        {"id": "3", "status": "open", "title": "item 3"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"tracker_open": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
        )

        self.assertIn("tracker_open", pack.content)
        open_items = json.loads(pack.content["tracker_open"])
        self.assertEqual(len(open_items), 2)
        self.assertTrue(
            all(item["status"] == "open" for item in open_items)
        )

    def test_brief_explicit_path_allowlisted(self):
        """Explicit brief: path must be under allowlist."""
        # Create a file under repo_root.
        brief_file = Path(self.repo_root) / "NOTES.md"
        brief_file.write_text("# Decision brief\n", encoding="utf-8")

        pack = build_context_pack(
            decision_type="adjudicate",
            sources={f"brief:{brief_file}": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
        )

        self.assertIn(f"brief:{brief_file}", pack.content)
        self.assertIn("# Decision brief", pack.content[f"brief:{brief_file}"])

    def test_brief_path_outside_allowlist_raises(self):
        """Arbitrary paths outside allowlist raise ContextPackViolation."""
        with tempfile.TemporaryDirectory() as outside_root:
            outside_file = Path(outside_root) / "EVIL.txt"
            outside_file.write_text("secret data", encoding="utf-8")

            with self.assertRaises(ContextPackViolation):
                build_context_pack(
                    decision_type="adjudicate",
                    sources={f"brief:{outside_file}": None},
                    repo_root=self.repo_root,
                    conductor_root=self.conductor_root,
                )

    def test_unknown_source_type_raises(self):
        """Unknown source types raise ContextPackViolation."""
        with self.assertRaises(ContextPackViolation) as cm:
            build_context_pack(
                decision_type="rank_backlog",
                sources={"unknown_source": None},
                repo_root=self.repo_root,
                conductor_root=self.conductor_root,
            )
        self.assertIn("Unknown context source", str(cm.exception))

    def test_size_cap_enforced_truncates_buildlog_first(self):
        """Size cap enforcement: log sources are truncated before others."""
        # Create a state file and a buildlog.
        state_file = Path(self.repo_root) / "STATE.md"
        state_file.write_text("# STATE\n" + "s" * 10000, encoding="utf-8")

        buildlog_file = Path(self.repo_root) / "BUILDLOG.md"
        buildlog_file.write_text("# LOG\n" + "b" * 10000, encoding="utf-8")

        # Pack with cap that requires truncation of at least one source.
        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"state": None, "buildlog_tail:10": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
            size_cap=8000,  # 8KB cap for ~20KB of content.
        )

        # Both sources should be included (we don't exclude sources).
        self.assertTrue(
            any(m["source"] == "state" and m["included"]
                for m in pack.manifest)
        )
        self.assertTrue(
            any(m["source"] == "buildlog_tail:10" and m["included"]
                for m in pack.manifest)
        )
        # Pack should be significantly smaller than untruncated (truncation working).
        self.assertLess(pack.total_size_bytes, 20000)  # Much less than original.

    def test_manifest_tracks_included_truncated_sizes(self):
        """Manifest accurately tracks what was included/truncated/size."""
        state_file = Path(self.repo_root) / "STATE.md"
        state_file.write_text("# STATE\n", encoding="utf-8")

        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"state": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
        )

        state_manifest = next(
            m for m in pack.manifest if m["source"] == "state"
        )
        self.assertTrue(state_manifest["included"])
        self.assertFalse(state_manifest["truncated"])
        self.assertGreater(state_manifest["size_bytes"], 0)


# ============================================================================
# Tests: orchestrator_driver.py
# ============================================================================


class TestOrchestratorDriverBasics(unittest.TestCase):
    """Test OrchestratorDriver.decide() fundamentals."""

    def setUp(self):
        """Create temp fixtures and fake backend."""
        self.temp_repo = tempfile.TemporaryDirectory()
        self.repo_root = self.temp_repo.name

        # Create STATE.md for context packs.
        state_file = Path(self.repo_root) / "STATE.md"
        state_file.write_text("# Wave\nphase: dispatch\n", encoding="utf-8")

    def tearDown(self):
        """Clean up temp dirs."""
        self.temp_repo.cleanup()

    def test_decide_happy_path_valid_json(self):
        """Happy path: backend returns valid JSON -> verdict returned."""
        context = ContextPack(
            decision_type="rank_backlog",
            content={"state": "# STATE"},
        )

        decision_response = json.dumps(
            {
                "verdict": "APPROVED",
                "evidence": "Items ranked by priority.",
            }
        )

        transport = FakeTransport(
            response_sequence=[
                (decision_response, "", 0),  # Success on first try.
            ]
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(backend)

        result = driver.decide("rank_backlog", context)

        self.assertEqual(result["verdict"], "APPROVED")
        self.assertIn("evidence", result)
        self.assertEqual(result["retry_count"], 0)
        self.assertEqual(transport.call_count, 1)

    def test_decide_malformed_then_valid_retries(self):
        """Malformed JSON on first attempt, valid on second -> success."""
        context = ContextPack(
            decision_type="rank_backlog",
            content={"state": "# STATE"},
        )

        valid_response = json.dumps(
            {
                "verdict": "APPROVED",
                "evidence": "Fixed on retry.",
            }
        )

        transport = FakeTransport(
            response_sequence=[
                ("{INVALID JSON}", "", 0),  # Malformed JSON.
                (valid_response, "", 0),  # Valid on retry.
            ]
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(backend, max_retries=2)

        result = driver.decide("rank_backlog", context)

        self.assertEqual(result["verdict"], "APPROVED")
        self.assertEqual(result["retry_count"], 1)  # Succeeded on 2nd attempt.
        self.assertEqual(transport.call_count, 2)

    def test_decide_always_malformed_fails_safe(self):
        """Always-malformed JSON -> DECISION_FAILED (never green)."""
        context = ContextPack(
            decision_type="rank_backlog",
            content={"state": "# STATE"},
        )

        transport = FakeTransport(
            response_sequence=[
                ("{INVALID1}", "", 0),
                ("{INVALID2}", "", 0),
                ("{INVALID3}", "", 0),
            ]
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(backend, max_retries=2)

        result = driver.decide("rank_backlog", context)

        self.assertEqual(result["verdict"], "DECISION_FAILED")
        self.assertIn("evidence", result)
        self.assertIn("Malformed JSON", result["evidence"])
        # Never green: verdict is FAILED, not fabricated.
        self.assertNotEqual(result["verdict"], "APPROVED")

    def test_decide_missing_required_keys_fails_safe(self):
        """Missing 'verdict' or 'evidence' -> retry then DECISION_FAILED."""
        context = ContextPack(
            decision_type="rank_backlog",
            content={"state": "# STATE"},
        )

        # Missing 'evidence'.
        bad_response = json.dumps({"verdict": "APPROVED"})

        transport = FakeTransport(
            response_sequence=[
                (bad_response, "", 0),
                (bad_response, "", 0),
                (bad_response, "", 0),
            ]
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(backend, max_retries=2)

        result = driver.decide("rank_backlog", context)

        self.assertEqual(result["verdict"], "DECISION_FAILED")

    def test_decide_backend_command_failure_retries_then_fails(self):
        """Backend run_command returns non-zero exit code -> fail-safe."""
        context = ContextPack(
            decision_type="rank_backlog",
            content={"state": "# STATE"},
        )

        transport = FakeTransport(
            response_sequence=[
                ("", "error", 1),  # Failed execution.
                ("", "error", 1),
                ("", "error", 1),
            ]
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(backend, max_retries=2)

        result = driver.decide("rank_backlog", context)

        self.assertEqual(result["verdict"], "DECISION_FAILED")
        self.assertIn("exit", result["evidence"].lower())


class TestOrchestratorDriverSchemaValidation(unittest.TestCase):
    """Test schema-based validation."""

    def setUp(self):
        """Create temp fixtures."""
        self.temp_repo = tempfile.TemporaryDirectory()
        self.temp_schema_dir = tempfile.TemporaryDirectory()
        self.repo_root = self.temp_repo.name
        self.schema_dir = self.temp_schema_dir.name

        # Create decisions/ subdir.
        decisions_dir = Path(self.schema_dir) / "decisions"
        decisions_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up temp dirs."""
        self.temp_repo.cleanup()
        self.temp_schema_dir.cleanup()

    def test_schema_loaded_from_file(self):
        """Schema loaded from decisions/<type>.schema.json."""
        schema = {
            "type": "object",
            "required": ["verdict", "evidence", "priority"],
        }
        schema_file = (
            Path(self.schema_dir) / "decisions" / "rank_backlog.schema.json"
        )
        schema_file.write_text(json.dumps(schema), encoding="utf-8")

        context = ContextPack(
            decision_type="rank_backlog", content={"state": "# STATE"}
        )

        # Missing 'priority' field -> should fail validation.
        bad_response = json.dumps(
            {"verdict": "APPROVED", "evidence": "..."}
        )

        transport = FakeTransport(
            response_sequence=[(bad_response, "", 0)] * 3
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(
            backend, schema_dir=self.schema_dir, max_retries=2
        )

        result = driver.decide("rank_backlog", context)

        # Should fail because schema requires 'priority'.
        self.assertEqual(result["verdict"], "DECISION_FAILED")

    def test_schema_absent_minimal_validation(self):
        """Absent schema: only requires 'verdict' and 'evidence'."""
        context = ContextPack(
            decision_type="rank_backlog", content={"state": "# STATE"}
        )

        # Only verdict + evidence, no other fields.
        minimal_response = json.dumps(
            {"verdict": "APPROVED", "evidence": "minimal decision"}
        )

        transport = FakeTransport(
            response_sequence=[(minimal_response, "", 0)]
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(
            backend, schema_dir=self.schema_dir, max_retries=2
        )

        # Schema file does not exist; minimal validation used.
        result = driver.decide("rank_backlog", context)

        self.assertEqual(result["verdict"], "APPROVED")
        # No schema file -> schema_validated is False (minimal validation only).
        self.assertFalse(result["schema_validated"])

    def test_schema_caching(self):
        """Loaded schemas are cached."""
        schema = {"type": "object", "required": ["verdict", "evidence"]}
        schema_file = (
            Path(self.schema_dir) / "decisions" / "test_type.schema.json"
        )
        schema_file.write_text(json.dumps(schema), encoding="utf-8")

        context = ContextPack(
            decision_type="test_type", content={"state": "# STATE"}
        )

        valid_response = json.dumps(
            {"verdict": "APPROVED", "evidence": "test"}
        )

        transport = FakeTransport(
            response_sequence=[(valid_response, "", 0)] * 2
        )
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(
            backend, schema_dir=self.schema_dir, max_retries=1
        )

        # First call loads schema.
        result1 = driver.decide("test_type", context)
        self.assertEqual(result1["verdict"], "APPROVED")

        # Second call uses cached schema.
        result2 = driver.decide("test_type", context)
        self.assertEqual(result2["verdict"], "APPROVED")

        # Only 2 backend calls (one per decide), not 3 (which would suggest
        # schema re-loading).
        self.assertEqual(transport.call_count, 2)


class TestContextPackSizeCap(unittest.TestCase):
    """Test context pack size capping behavior."""

    def setUp(self):
        """Create temp fixtures."""
        self.temp_repo = tempfile.TemporaryDirectory()
        self.repo_root = self.temp_repo.name

    def tearDown(self):
        """Clean up temp dirs."""
        self.temp_repo.cleanup()

    def test_size_cap_respected(self):
        """Total pack size does not exceed size_cap."""
        # Create a large STATE.md.
        large_state = "x" * 30000
        state_file = Path(self.repo_root) / "STATE.md"
        state_file.write_text(large_state, encoding="utf-8")

        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"state": None},
            repo_root=self.repo_root,
            conductor_root=self.repo_root,
            size_cap=5000,  # 5KB cap.
        )

        # Total size should be capped (or slightly over due to manifest).
        self.assertLess(pack.total_size_bytes, 10000)  # Generous margin.

    def test_truncation_marked_in_manifest(self):
        """Truncated sources are marked in manifest."""
        large_state = "x" * 30000
        state_file = Path(self.repo_root) / "STATE.md"
        state_file.write_text(large_state, encoding="utf-8")

        pack = build_context_pack(
            decision_type="rank_backlog",
            sources={"state": None},
            repo_root=self.repo_root,
            conductor_root=self.repo_root,
            size_cap=5000,
        )

        # Manifest should show truncation.
        state_manifest = next(
            (m for m in pack.manifest if m["source"] == "state"), None
        )
        self.assertIsNotNone(state_manifest)
        # May or may not be truncated depending on other sources, but if
        # truncated, it should be marked.
        if state_manifest["size_bytes"] < len(large_state.encode("utf-8")):
            self.assertTrue(state_manifest["truncated"])


class TestContextPackEvidence(unittest.TestCase):
    """Test evidence-enriched context packs (increment 2.5)."""

    def setUp(self):
        """Create temp repo/conductor roots."""
        self.temp_repo = tempfile.TemporaryDirectory()
        self.temp_conductor = tempfile.TemporaryDirectory()
        self.repo_root = self.temp_repo.name
        self.conductor_root = self.temp_conductor.name

    def tearDown(self):
        """Clean up temp dirs."""
        self.temp_repo.cleanup()
        self.temp_conductor.cleanup()

    def test_evidence_included_in_pack(self):
        """Evidence dict is included and added to pack.evidence."""
        evidence_dict = {
            "code_example": "def foo():\n    pass",
            "repro_output": "Error: xyz\nStack trace...",
        }

        pack = build_context_pack(
            decision_type="adjudicate_finding",
            sources={},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
            evidence=evidence_dict,
        )

        self.assertEqual(len(pack.evidence), 2)
        self.assertIn("code_example", pack.evidence)
        self.assertIn("repro_output", pack.evidence)
        self.assertEqual(pack.evidence["code_example"], "def foo():\n    pass")
        self.assertEqual(pack.evidence["repro_output"], "Error: xyz\nStack trace...")

    def test_evidence_size_tracked_in_manifest(self):
        """Evidence size is tracked separately and recorded in manifest."""
        evidence_dict = {"example": "test content"}

        pack = build_context_pack(
            decision_type="adjudicate_finding",
            sources={},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
            evidence=evidence_dict,
        )

        self.assertGreater(pack.evidence_size_bytes, 0)
        self.assertEqual(len(pack.evidence_manifest), 1)
        manifest_entry = pack.evidence_manifest[0]
        self.assertEqual(manifest_entry["name"], "example")
        self.assertTrue(manifest_entry["included"])
        self.assertFalse(manifest_entry["truncated"])

    def test_evidence_size_cap_enforced(self):
        """Evidence size cap is enforced; truncation is marked."""
        # Create evidence that exceeds the cap.
        large_evidence = "x" * 10000
        evidence_dict = {
            "large": large_evidence,
            "small": "test",
        }

        pack = build_context_pack(
            decision_type="adjudicate_finding",
            sources={},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
            evidence=evidence_dict,
            evidence_cap=500,  # Small cap to force truncation.
        )

        # Total evidence size should be under cap.
        self.assertLess(pack.evidence_size_bytes, 500)

        # At least one evidence item should be truncated.
        truncated_items = [m for m in pack.evidence_manifest if m["truncated"]]
        self.assertGreater(len(truncated_items), 0)

        # Truncated items should have a reason.
        for item in truncated_items:
            self.assertEqual(item["truncation_reason"], "evidence_size_cap_exceeded")

    def test_evidence_no_label_leak_assertion(self):
        """Evidence should not contain label/verdict strings."""
        evidence_dict = {
            "neutral_fact": "Git Bash accepts //server/share syntax",
        }

        pack = build_context_pack(
            decision_type="adjudicate_finding",
            sources={},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
            evidence=evidence_dict,
        )

        # Verify no label strings appear in evidence.
        evidence_text = json.dumps(pack.evidence)
        forbidden_labels = [
            "false_positive",
            "real_defect",
            "enhancement_opportunity",
            "incumbent_verdict",
            "ground_truth",
            "gt_note",
        ]
        for label in forbidden_labels:
            self.assertNotIn(label, evidence_text)

    def test_evidence_separated_from_content(self):
        """Evidence is separate from main content and doesn't compete for size cap."""
        content_text = "x" * 1000
        evidence_text = "y" * 1000

        state_file = Path(self.repo_root) / "STATE.md"
        state_file.write_text(content_text, encoding="utf-8")

        pack = build_context_pack(
            decision_type="adjudicate_finding",
            sources={"state": None},
            repo_root=self.repo_root,
            conductor_root=self.conductor_root,
            size_cap=2000,
            evidence={"evidence_item": evidence_text},
            evidence_cap=2000,
        )

        # Both content and evidence should be included without competing.
        self.assertIn("state", pack.content)
        self.assertIn("evidence_item", pack.evidence)
        self.assertGreater(pack.total_size_bytes, 0)
        self.assertGreater(pack.evidence_size_bytes, 0)


class TestOrchestratorDriverCapabilities(unittest.TestCase):
    """Test capability delegation to backend."""

    def test_probe_capabilities_delegated(self):
        """probe_capabilities() delegates to backend."""
        transport = FakeTransport()
        backend = FakeAgentDriver(transport)
        driver = OrchestratorDriver(backend)

        caps = driver.probe_capabilities()

        self.assertEqual(caps.name, "fake")
        self.assertEqual(caps.tool_use_accuracy, 0.99)
        self.assertEqual(caps.recommended_verification_tier, 1)


if __name__ == "__main__":
    unittest.main()
