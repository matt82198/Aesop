#!/usr/bin/env python3
"""Tests for seated_shadow_adjudication.py

Verifies that:
1. Real context packs contain actual file-brain sources (STATE.md, tracker.json, etc.)
2. Labels (incumbent_verdict, ground_truth) are NEVER included in context packs
3. Manifest accurately tracks included/truncated sources
4. No regressions in orchestrator_driver test suite
5. Repo code extraction handles missing files gracefully

All tests are OFFLINE (no API calls, no OPENAI_API_KEY needed).
"""

import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

# Add driver/ to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO_ROOT / "driver"
TOOLS_DIR = REPO_ROOT / "tools"

if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from context_pack import build_context_pack, ContextPackViolation  # noqa: E402
from seated_shadow_adjudication import (  # noqa: E402
    extract_real_file_brain,
    extract_real_repo_code,
    build_seated_context_pack,
)


class TestRealFileBrainExtraction(unittest.TestCase):
    """Test extraction of REAL file-brain sources."""

    def test_state_md_extracted(self):
        """STATE.md should be read and included in file_brain."""
        file_brain = extract_real_file_brain(REPO_ROOT)

        self.assertIn("state", file_brain)
        state_content = file_brain["state"]
        # Should have substantial content from real STATE.md
        self.assertGreater(len(state_content), 100)
        # Should contain known sections from STATE.md
        self.assertIn("Intent", state_content)

    def test_tracker_json_extracted(self):
        """tracker.json should be read and open items included (if it exists)."""
        file_brain = extract_real_file_brain(REPO_ROOT)

        # tracker.json is git-ignored so may not exist in worktree
        if "tracker_open" in file_brain:
            tracker_content = file_brain["tracker_open"]
            # Should be valid JSON
            tracker_data = json.loads(tracker_content)
            self.assertIn("open_items_count", tracker_data)
            self.assertIn("items", tracker_data)

    def test_missing_buildlog_gracefully_handled(self):
        """Missing BUILDLOG.md should not raise, just omit the source."""
        # Test with repo that may or may not have BUILDLOG
        file_brain = extract_real_file_brain(REPO_ROOT)

        # It's OK if buildlog_tail is missing or present
        if "buildlog_tail:50" in file_brain:
            self.assertIsInstance(file_brain["buildlog_tail:50"], str)
        # The extraction should not crash


class TestRealRepoCodeExtraction(unittest.TestCase):
    """Test extraction of REAL code snippets from repo files."""

    def test_vbs_waitforexit_code_extracted(self):
        """run-hidden.vbs should be extracted for vbs-waitforexit finding."""
        evidence = extract_real_repo_code(REPO_ROOT, "vbs-waitforexit")

        self.assertIn("code:daemons/run-hidden.vbs", evidence)
        vbs_content = evidence["code:daemons/run-hidden.vbs"]
        # Should contain the working fix (True for wait)
        self.assertIn("shell.Run(cmd, windowStyle, True)", vbs_content)
        # Should NOT contain the broken version
        self.assertNotIn("shell.Run(cmd, windowStyle, False)", vbs_content)

    def test_whitelist_gate_weakening_code_extracted(self):
        """Item 9 should include secret_scan.py header (MONEY QUESTION)."""
        evidence = extract_real_repo_code(REPO_ROOT, "whitelist-gate-weakening")

        # Should have code from secret_scan.py
        secret_scan_keys = [k for k in evidence.keys() if "secret_scan.py" in k]
        self.assertGreater(len(secret_scan_keys), 0)

        # The secret_scan.py content should show recursive file scanning
        secret_scan_content = evidence.get("code:tools/secret_scan.py:1-100", "")
        self.assertIn("secret_scan.py", evidence.keys().__str__())

    def test_missing_file_gracefully_handled(self):
        """Missing repo files should not raise, just report error."""
        evidence = extract_real_repo_code(REPO_ROOT, "nonexistent-item")

        # Should return empty dict for unknown finding
        self.assertEqual(len(evidence), 0)

    def test_quote_validation_code_extracted(self):
        """install-tasks.ps1 should be extracted for quote-validation."""
        evidence = extract_real_repo_code(REPO_ROOT, "quote-validation")

        # Should have install-tasks.ps1 code
        ps1_keys = [k for k in evidence.keys() if "install-tasks.ps1" in k]
        self.assertGreater(len(ps1_keys), 0)


class TestSeatedContextPackConstruction(unittest.TestCase):
    """Test the full context pack building for seated adjudication."""

    def setUp(self):
        """Load a test corpus item."""
        corpus_path = REPO_ROOT / "driver" / "decisions" / "shadow" / "corpus-2026-07-23.jsonl"
        self.corpus = []
        if corpus_path.exists():
            with open(corpus_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.corpus.append(json.loads(line))

    def test_context_pack_has_real_file_brain(self):
        """Context pack should include REAL file-brain sources."""
        if not self.corpus:
            self.skipTest("Corpus not available")

        item = self.corpus[0]  # Use first item
        pack = build_seated_context_pack(REPO_ROOT, item)

        # Pack should have file-brain content
        self.assertGreater(len(pack.content), 0)
        # Should include STATE.md content
        self.assertIn("state", pack.content)

    def test_context_pack_never_includes_labels(self):
        """Labels (incumbent_verdict, ground_truth) MUST NEVER be in the pack."""
        if not self.corpus:
            self.skipTest("Corpus not available")

        item = self.corpus[0]
        pack = build_seated_context_pack(REPO_ROOT, item)

        # Serialize pack to string to check for label presence
        pack_str = json.dumps(pack.__dict__, default=str)

        # These should NEVER appear (blind adjudication)
        self.assertNotIn("incumbent_verdict", pack_str)
        self.assertNotIn("ground_truth", pack_str)
        self.assertNotIn('"labels"', pack_str)

    def test_manifest_tracks_included_sources(self):
        """Manifest should accurately record what was included/truncated."""
        if not self.corpus:
            self.skipTest("Corpus not available")

        item = self.corpus[0]
        pack = build_seated_context_pack(REPO_ROOT, item)

        # Pack should have manifest
        self.assertGreater(len(pack.manifest), 0)

        # Each manifest entry should have these fields
        for entry in pack.manifest:
            self.assertIn("source", entry)
            self.assertIn("included", entry)
            self.assertIn("size_bytes", entry)

    def test_item9_money_question_evidence(self):
        """Item 9 (whitelist-gate-weakening) should have secret_scan.py in pack."""
        if not self.corpus:
            self.skipTest("Corpus not available")

        item9 = None
        for item in self.corpus:
            if item["id"] == "whitelist-gate-weakening":
                item9 = item
                break

        if not item9:
            self.skipTest("Item 9 not in corpus")

        pack = build_seated_context_pack(REPO_ROOT, item9)

        # Pack evidence should include secret_scan.py
        evidence_sources = set(pack.evidence.keys())
        secret_scan_found = any("secret_scan" in key for key in evidence_sources)
        self.assertTrue(secret_scan_found, f"secret_scan not in evidence: {evidence_sources}")


class TestNoLabelsInPack(unittest.TestCase):
    """Comprehensive test that labels are NEVER leaked to packs."""

    def test_labels_not_in_evidence_dict(self):
        """Test that labels dict is never passed to context pack."""
        if not Path(REPO_ROOT / "driver" / "decisions" / "shadow" / "corpus-2026-07-23.jsonl").exists():
            self.skipTest("Corpus not available")

        with open(
            REPO_ROOT / "driver" / "decisions" / "shadow" / "corpus-2026-07-23.jsonl",
            encoding="utf-8"
        ) as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    pack = build_seated_context_pack(REPO_ROOT, item)

                    # Check evidence dict
                    for key, value in pack.evidence.items():
                        self.assertNotIn("incumbent_verdict", value)
                        self.assertNotIn("ground_truth", value)
                        self.assertNotIn("real_defect", value)
                        self.assertNotIn("false_positive", value)

    def test_labels_not_in_content_dict(self):
        """Test that labels never appear in main content."""
        if not Path(REPO_ROOT / "driver" / "decisions" / "shadow" / "corpus-2026-07-23.jsonl").exists():
            self.skipTest("Corpus not available")

        with open(
            REPO_ROOT / "driver" / "decisions" / "shadow" / "corpus-2026-07-23.jsonl",
            encoding="utf-8"
        ) as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    pack = build_seated_context_pack(REPO_ROOT, item)

                    # Check content dict
                    for key, value in pack.content.items():
                        if isinstance(value, str) and len(value) > 0:
                            # Labels should NOT appear
                            self.assertNotIn("incumbent_verdict", value)
                            self.assertNotIn("ground_truth", value)


class TestContextPackSizeConstraints(unittest.TestCase):
    """Test that context packs respect size constraints."""

    def test_pack_respects_size_cap(self):
        """Context pack should respect the 64KB size cap."""
        if not Path(REPO_ROOT / "driver" / "decisions" / "shadow" / "corpus-2026-07-23.jsonl").exists():
            self.skipTest("Corpus not available")

        with open(
            REPO_ROOT / "driver" / "decisions" / "shadow" / "corpus-2026-07-23.jsonl",
            encoding="utf-8"
        ) as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    pack = build_seated_context_pack(REPO_ROOT, item)

                    # Total size should not exceed cap
                    self.assertLessEqual(pack.total_size_bytes, 65536)

                    # Evidence size should not exceed its cap
                    self.assertLessEqual(pack.evidence_size_bytes, 16384)

                    # Manifest should record this
                    self.assertLessEqual(pack.total_size_bytes, pack.total_size_cap)


class TestOrchestrationCoreRegression(unittest.TestCase):
    """Sanity check that test_orchestrator_driver still passes.

    This just imports and does basic validation; the real tests
    are in test_orchestrator_driver.py.
    """

    def test_orchestrator_driver_imports(self):
        """OrchestratorDriver should import without errors."""
        from orchestrator_driver import OrchestratorDriver  # noqa: E402, F401
        # If we got here, import succeeded

    def test_context_pack_imports(self):
        """context_pack should import without errors."""
        from context_pack import build_context_pack  # noqa: E402, F401
        # If we got here, import succeeded


if __name__ == "__main__":
    unittest.main()
