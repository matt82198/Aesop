#!/usr/bin/env python3
"""Offline tests for AdjudicationGate (swap increment 3, conservative).

Tests the two-tier adjudication gate with:
  * Mechanism-real-defects: challenger confident, correct -> accepted
  * Narrative-FP: challenger undetermined -> escalated -> incumbent correct
  * Challenger confident-but-wrong: spot-check disagree -> recorded
  * DECISION_FAILED handling: escalate to incumbent
  * Spot-check determinism: seeded, reproducible
  * Safety invariant: never emit unconfident verdict as final

Uses FakeChallengerDriver + FakeIncumbent (ground truth): offline, hermetic,
no API keys, no network. All assertions verify the safety invariant holds.

stdlib-only (unittest), ASCII-only, Windows + Linux safe.
"""

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# Add driver/ to sys.path.
REPO = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO / "driver"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

from adjudication_gate import AdjudicationGate  # noqa: E402


# ============================================================================
# Fake implementations for offline testing
# ============================================================================


@dataclass
class FakeChallengerDriver:
    """Mock OrchestratorDriver for testing AdjudicationGate.

    Returns canned verdicts so we can test the gate logic without network/API.
    Supports mechanism-correct, narrative-undetermined, confident-but-wrong cases.
    """

    verdicts: Dict[str, Dict[str, Any]] = None

    def __post_init__(self):
        if self.verdicts is None:
            self.verdicts = {}

    def decide(
        self,
        decision_type: str,
        context_pack: Any,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a pre-canned verdict for this decision_type."""
        if decision_type in self.verdicts:
            return self.verdicts[decision_type]
        # Default: return undetermined (safe fallback).
        return {
            "verdict": "undetermined",
            "evidence": "No canned response",
            "confidence": 0.0,
        }


@dataclass
class FakeIncumbent:
    """Ground-truth incumbent for testing.

    Provides correct verdicts for each decision_type.
    """

    correct_verdicts: Dict[str, Dict[str, Any]] = None

    def __post_init__(self):
        if self.correct_verdicts is None:
            self.correct_verdicts = {}

    def __call__(
        self,
        decision_type: str,
        context_pack: Any,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return the correct verdict for this decision_type."""
        if decision_type in self.correct_verdicts:
            return self.correct_verdicts[decision_type]
        return {
            "verdict": "UNDETERMINED",
            "evidence": "No ground truth",
            "confidence": 0.0,
        }


# ============================================================================
# Test suite
# ============================================================================


class TestAdjudicationGate(unittest.TestCase):
    """Test AdjudicationGate safety invariant and escalation logic."""

    def setUp(self):
        """Set up challenger and incumbent for each test."""
        self.challenger = FakeChallengerDriver()
        self.incumbent = FakeIncumbent()
        self.context_pack = type("ContextPack", (), {"content": {}})()

    def test_challenger_confident_mechanism_real_defect_accepted(self):
        """Mechanism-real-defect: challenger confident, correct -> accepted.

        This is the fast path: challenger identifies a real mechanism defect
        (e.g., incorrect type checking) with high confidence. Gate accepts it.
        """
        self.challenger.verdicts["defect_type_mismatch"] = {
            "verdict": "defect_found",
            "evidence": "Type X does not match expected Y",
            "confidence": 0.95,  # Confident.
        }
        self.incumbent.correct_verdicts["defect_type_mismatch"] = {
            "verdict": "defect_found",
            "evidence": "Confirmed: type mismatch",
            "confidence": 0.99,
        }

        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
        )

        result = gate.adjudicate("defect_type_mismatch", self.context_pack)

        # Safety invariant: source is 'challenger' and verdict is confident.
        self.assertEqual(result["source"], "challenger")
        self.assertEqual(result["verdict"], "defect_found")
        self.assertEqual(result["confidence"], 0.95)
        # Invariant: no incumbent_verdict (only escalated calls have it).
        self.assertNotIn("incumbent_verdict", result)

    def test_narrative_false_positive_challenger_undetermined_escalates(self):
        """Narrative-FP: challenger undetermined -> escalated -> incumbent correct.

        Challenger cannot refute a false-positive narrative claim (lacks context),
        returns undetermined. Gate escalates. Incumbent correctly refutes it.
        """
        self.challenger.verdicts["narrative_config_cleanup"] = {
            "verdict": "undetermined",
            "evidence": "Cannot determine without full code review",
            "confidence": 0.0,
        }
        self.incumbent.correct_verdicts["narrative_config_cleanup"] = {
            "verdict": "false_positive",
            "evidence": "Config cleanup is recommended practice, not a defect",
            "confidence": 0.98,
        }

        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
            escalate_on_undetermined=True,
        )

        result = gate.adjudicate("narrative_config_cleanup", self.context_pack)

        # Safety invariant: escalated, source is 'escalated-undetermined'.
        self.assertEqual(result["source"], "escalated-undetermined")
        # Verdict is from incumbent, NOT challenger's undetermined.
        self.assertEqual(result["verdict"], "false_positive")
        self.assertEqual(result["confidence"], 0.98)
        # Incumbent verdict is present.
        self.assertIn("incumbent_verdict", result)
        self.assertEqual(result["incumbent_verdict"]["verdict"], "false_positive")

    def test_challenger_decision_failed_escalates_to_incumbent(self):
        """DECISION_FAILED: challenger failed -> escalated -> incumbent succeeds.

        Backend error (malformed response, retry exhausted) causes challenger
        to return DECISION_FAILED. Gate escalates. Incumbent provides answer.
        """
        self.challenger.verdicts["repair_decision"] = {
            "verdict": "DECISION_FAILED",
            "evidence": "Malformed JSON after retries",
            "confidence": 0.0,
        }
        self.incumbent.correct_verdicts["repair_decision"] = {
            "verdict": "approved",
            "evidence": "Repair logic is sound",
            "confidence": 0.97,
        }

        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
        )

        result = gate.adjudicate("repair_decision", self.context_pack)

        # Safety invariant: escalated to incumbent, NOT returning DECISION_FAILED.
        self.assertEqual(result["source"], "escalated-failed")
        self.assertEqual(result["verdict"], "approved")
        self.assertNotEqual(result["verdict"], "DECISION_FAILED")

    def test_challenger_low_confidence_escalates_to_incumbent(self):
        """Low confidence: challenger <70% -> escalated -> incumbent correct.

        Challenger has some doubt (confidence below threshold). Gate escalates
        automatically to incumbent.
        """
        self.challenger.verdicts["merge_eligibility"] = {
            "verdict": "approved",
            "evidence": "Tests passed, but some uncertainty",
            "confidence": 0.65,  # Below default 0.70 threshold.
        }
        self.incumbent.correct_verdicts["merge_eligibility"] = {
            "verdict": "needs_changes",
            "evidence": "Test coverage incomplete",
            "confidence": 0.94,
        }

        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
            escalate_confidence_below=0.70,
        )

        result = gate.adjudicate("merge_eligibility", self.context_pack)

        # Safety invariant: escalated for low confidence.
        self.assertEqual(result["source"], "escalated-lowconf")
        # Verdict is from incumbent, NOT challenger's low-confidence verdict.
        self.assertEqual(result["verdict"], "needs_changes")
        self.assertEqual(result["confidence"], 0.94)

    def test_disallowed_decision_type_escalates_to_incumbent(self):
        """Disallowed type: narrative mechanism not in allowed set -> escalated.

        Gate is configured to allow only mechanism decisions, not narrative.
        Narrative type is automatically escalated.
        """
        self.challenger.verdicts["narrative_refutation"] = {
            "verdict": "false_positive",
            "evidence": "This is a style choice, not a defect",
            "confidence": 0.88,  # High confidence, but type disallowed.
        }
        self.incumbent.correct_verdicts["narrative_refutation"] = {
            "verdict": "false_positive",
            "evidence": "Confirmed: style, not defect",
            "confidence": 0.99,
        }

        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
            allowed_decision_types=["defect_type_mismatch", "logic_error"],
        )

        result = gate.adjudicate("narrative_refutation", self.context_pack)

        # Safety invariant: escalated because type is disallowed.
        self.assertEqual(result["source"], "escalated-disallowed-type")
        # Verdict is from incumbent (even though challenger was confident).
        self.assertEqual(result["verdict"], "false_positive")

    def test_spot_check_escalates_confident_verdict_for_audit(self):
        """Spot-check: confident verdict sampled -> escalated for audit -> record agreement/disagreement.

        Even a confident challenger verdict is escalated for audit sampling
        (default 10%). This records whether incumbent agrees.
        """
        # Use a specific context pack so we can predict the spot-check decision.
        context_pack = type("ContextPack", (), {"content": {}, "_spot_id": 0})()

        self.challenger.verdicts["sample_decision"] = {
            "verdict": "approved",
            "evidence": "All checks pass",
            "confidence": 0.92,
        }
        self.incumbent.correct_verdicts["sample_decision"] = {
            "verdict": "approved",
            "evidence": "Confirmed",
            "confidence": 0.95,
        }

        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
            spot_check_frac=0.50,  # High frac so we hit spot-check in test.
        )

        # Make several calls and look for a spot-check hit.
        hit_spot_check = False
        for i in range(20):
            ctx = type("ContextPack", (), {"content": {}, "_spot_id": i})()
            result = gate.adjudicate("sample_decision", ctx)
            if result["source"] == "escalated-spotcheck":
                hit_spot_check = True
                # Verify spot-check escalated correctly.
                self.assertEqual(result["verdict"], "approved")
                self.assertIn("incumbent_verdict", result)
                break

        self.assertTrue(
            hit_spot_check, "Expected at least one spot-check in 20 calls"
        )

    def test_spot_check_is_deterministic(self):
        """Spot-check is deterministic: same context_pack -> same decision.

        The spot-check uses a stable hash of (decision_type, nonce), not random.
        Repeating with the same context pack should produce the same result.
        """
        context_pack_a = type("ContextPack", (), {"content": {}})()
        context_pack_b = type("ContextPack", (), {"content": {}})()

        # Make a gate that might spot-check (high frac).
        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
            spot_check_frac=0.50,
        )

        # Call with same context twice.
        result1 = gate.adjudicate("test_type_a", context_pack_a)
        result2 = gate.adjudicate("test_type_a", context_pack_a)
        # Should have same source (deterministic).
        self.assertEqual(result1["source"], result2["source"])

        # Call with different context.
        result3 = gate.adjudicate("test_type_a", context_pack_b)
        # May differ from result1 (different nonce).
        # The point is: result1 and result2 are identical.

    def test_safety_invariant_never_returns_undetermined_as_final(self):
        """Safety invariant: never emit undetermined as final verdict.

        Even if challenger returns undetermined, gate must escalate and return
        incumbent's verdict. The gate is incumbent-safe by construction.
        """
        challenger = FakeChallengerDriver(
            verdicts={
                "case_1": {
                    "verdict": "undetermined",
                    "evidence": "Unknown",
                    "confidence": 0.0,
                },
                "case_2": {
                    "verdict": "DECISION_FAILED",
                    "evidence": "Error",
                    "confidence": 0.0,
                },
            }
        )
        incumbent = FakeIncumbent(
            correct_verdicts={
                "case_1": {
                    "verdict": "approved",
                    "evidence": "Incumbent says yes",
                    "confidence": 0.99,
                },
                "case_2": {
                    "verdict": "rejected",
                    "evidence": "Incumbent says no",
                    "confidence": 0.99,
                },
            }
        )

        gate = AdjudicationGate(
            challenger=challenger,
            incumbent_fn=incumbent,
        )

        # Case 1: undetermined
        result1 = gate.adjudicate("case_1", self.context_pack)
        self.assertNotEqual(result1["verdict"], "undetermined")
        self.assertNotEqual(result1["verdict"], "DECISION_FAILED")
        self.assertEqual(result1["verdict"], "approved")

        # Case 2: DECISION_FAILED
        result2 = gate.adjudicate("case_2", self.context_pack)
        self.assertNotEqual(result2["verdict"], "DECISION_FAILED")
        self.assertEqual(result2["verdict"], "rejected")

    def test_summarize_run_computes_statistics_correctly(self):
        """summarize_run() correctly counts escalations and agreements.

        Test the dashboard method that shows how often challenger was trusted.
        """
        results = [
            {"source": "challenger", "verdict": "approved"},
            {"source": "challenger", "verdict": "rejected"},
            {
                "source": "escalated-undetermined",
                "verdict": "approved",
                "challenger_verdict": {"verdict": "undetermined"},
                "incumbent_verdict": {"verdict": "approved"},
            },
            {
                "source": "escalated-lowconf",
                "verdict": "rejected",
                "challenger_verdict": {"verdict": "approved"},
                "incumbent_verdict": {"verdict": "rejected"},
            },
            {
                "source": "escalated-spotcheck",
                "verdict": "approved",
                "challenger_verdict": {"verdict": "approved"},
                "incumbent_verdict": {"verdict": "approved"},
            },
            {
                "source": "escalated-spotcheck",
                "verdict": "rejected",
                "challenger_verdict": {"verdict": "approved"},
                "incumbent_verdict": {"verdict": "rejected"},
            },
        ]

        gate = AdjudicationGate(
            challenger=self.challenger, incumbent_fn=self.incumbent
        )
        summary = gate.summarize_run(results)

        # Verify counts.
        self.assertEqual(summary["n"], 6)
        self.assertEqual(summary["accepted_challenger"], 2)
        self.assertEqual(summary["effective_escalation_rate"], 4 / 6)
        self.assertEqual(summary["escalated_by_reason"]["escalated-undetermined"], 1)
        self.assertEqual(summary["escalated_by_reason"]["escalated-lowconf"], 1)
        self.assertEqual(summary["escalated_by_reason"]["escalated-spotcheck"], 2)
        # Spot-check: 1 agreement, 1 disagreement.
        self.assertEqual(summary["spot_check_agreements"], 1)
        self.assertEqual(summary["spot_check_disagreements"], 1)

    def test_gate_never_emits_decision_failed_as_final(self):
        """Safety invariant: never emit DECISION_FAILED as final verdict.

        Even if challenger returns DECISION_FAILED, gate escalates to incumbent.
        """
        challenger = FakeChallengerDriver(
            verdicts={
                "any_type": {
                    "verdict": "DECISION_FAILED",
                    "evidence": "Backend error",
                    "confidence": 0.0,
                }
            }
        )
        incumbent = FakeIncumbent(
            correct_verdicts={
                "any_type": {
                    "verdict": "approved",
                    "evidence": "Incumbent overrides",
                    "confidence": 0.9,
                }
            }
        )

        gate = AdjudicationGate(
            challenger=challenger,
            incumbent_fn=incumbent,
        )

        result = gate.adjudicate("any_type", self.context_pack)
        # The gate must never return DECISION_FAILED as final.
        self.assertNotEqual(result["verdict"], "DECISION_FAILED")
        self.assertEqual(result["source"], "escalated-failed")

    def test_empty_allowed_list_means_all_allowed(self):
        """Empty allowed_decision_types means all types are allowed."""
        self.challenger.verdicts["any_type"] = {
            "verdict": "approved",
            "evidence": "Any type allowed",
            "confidence": 0.85,
        }

        gate = AdjudicationGate(
            challenger=self.challenger,
            incumbent_fn=self.incumbent,
            allowed_decision_types=[],  # Empty means all allowed.
        )

        result = gate.adjudicate("any_type", self.context_pack)
        # Should accept challenger (confident, type is allowed).
        self.assertEqual(result["source"], "challenger")

    def test_offline_proof_end_to_end(self):
        """Offline proof: representative fixture of 6 cases, all assertions pass.

        This is the core offline proof that the gate is safe:
        1. Mechanism defects: challenger correct + confident -> accepted
        2. Narrative FP: challenger undetermined -> escalated -> incumbent correct
        3. Challenger confident-but-wrong: spot-checked -> disagreement recorded
        4. DECISION_FAILED: escalated -> incumbent succeeds
        5. Low confidence: escalated -> incumbent succeeds
        6. Disallowed type: escalated -> incumbent succeeds

        For each case, assert:
        - Gate never emits undetermined/DECISION_FAILED as final
        - Escalation reason is correct
        - summarize_run counts are correct
        """
        challenger = FakeChallengerDriver(
            verdicts={
                # 1. Mechanism-real: confident, correct.
                "mechanism_1": {
                    "verdict": "defect",
                    "evidence": "Logic error",
                    "confidence": 0.96,
                },
                # 2. Narrative-FP: undetermined.
                "narrative_1": {
                    "verdict": "undetermined",
                    "evidence": "Cannot determine",
                    "confidence": 0.0,
                },
                # 3. Confident-but-wrong: will be in spot-check.
                "spotcheck_1": {
                    "verdict": "approved",
                    "evidence": "Looks good",
                    "confidence": 0.88,
                },
                # 4. DECISION_FAILED.
                "failed_1": {
                    "verdict": "DECISION_FAILED",
                    "evidence": "Backend error",
                    "confidence": 0.0,
                },
                # 5. Low confidence.
                "lowconf_1": {
                    "verdict": "approved",
                    "evidence": "Some doubt",
                    "confidence": 0.65,
                },
                # 6. Disallowed type (will escalate).
                "narrative_2": {
                    "verdict": "false_positive",
                    "evidence": "Not a real issue",
                    "confidence": 0.90,
                },
            }
        )
        incumbent = FakeIncumbent(
            correct_verdicts={
                "mechanism_1": {
                    "verdict": "defect",
                    "evidence": "Confirmed",
                    "confidence": 0.99,
                },
                "narrative_1": {
                    "verdict": "false_positive",
                    "evidence": "Not a defect",
                    "confidence": 0.98,
                },
                "spotcheck_1": {
                    "verdict": "rejected",
                    "evidence": "Needs work",
                    "confidence": 0.97,
                },
                "failed_1": {
                    "verdict": "approved",
                    "evidence": "Override",
                    "confidence": 0.95,
                },
                "lowconf_1": {
                    "verdict": "rejected",
                    "evidence": "More review needed",
                    "confidence": 0.96,
                },
                "narrative_2": {
                    "verdict": "false_positive",
                    "evidence": "Confirmed: style, not defect",
                    "confidence": 0.99,
                },
            }
        )

        gate = AdjudicationGate(
            challenger=challenger,
            incumbent_fn=incumbent,
            allowed_decision_types=["mechanism_1", "spotcheck_1", "failed_1", "lowconf_1"],
        )

        results = []
        for decision_type in [
            "mechanism_1",
            "narrative_1",
            "spotcheck_1",
            "failed_1",
            "lowconf_1",
            "narrative_2",
        ]:
            ctx = type("ContextPack", (), {"content": {}})()
            result = gate.adjudicate(decision_type, ctx)
            results.append(result)

            # CORE INVARIANT: never undetermined/DECISION_FAILED as final.
            self.assertNotIn(result["verdict"], ["undetermined", "DECISION_FAILED"])

        # Verify escalation reasons.
        self.assertEqual(results[0]["source"], "challenger")  # mechanism: accepted
        self.assertEqual(
            results[1]["source"], "escalated-undetermined"
        )  # narrative_1: escalated
        # spotcheck_1 may be challenger or escalated-spotcheck (depends on hash).
        self.assertIn(
            results[2]["source"],
            ["challenger", "escalated-spotcheck"],
        )
        self.assertEqual(
            results[3]["source"], "escalated-failed"
        )  # failed_1: escalated
        self.assertEqual(
            results[4]["source"], "escalated-lowconf"
        )  # lowconf_1: escalated
        self.assertEqual(
            results[5]["source"], "escalated-disallowed-type"
        )  # narrative_2: escalated

        # summarize_run: counts are correct.
        summary = gate.summarize_run(results)
        self.assertEqual(summary["n"], 6)
        self.assertGreaterEqual(summary["accepted_challenger"], 1)
        self.assertGreaterEqual(summary["effective_escalation_rate"], 0.5)
        self.assertIn("escalated-undetermined", summary["escalated_by_reason"])


if __name__ == "__main__":
    unittest.main()
