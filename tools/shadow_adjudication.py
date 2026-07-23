#!/usr/bin/env python3
"""Shadow adjudication wave runner.

Replays a corpus of ground-truth-labeled adjudication decisions through
the OrchestratorDriver seam using a configurable challenger backend
(OpenAI-compatible; --model selects the ladder rung). Zero behavior change
to any live system. Scorecards record the API-reported served model id as
evidence of which brain actually answered.

Blind adjudication: labels are NEVER included in challenger context packs.

CLI: python tools/shadow_adjudication.py --corpus <path> [--offline | --live]
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add driver/ to sys.path.
REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO_ROOT / "driver"
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
from context_pack import build_context_pack, ContextPack  # noqa: E402
from orchestrator_driver import OrchestratorDriver  # noqa: E402
from openai_transport import default_openai_transport  # noqa: E402


# ============================================================================
# FakeTransport (offline testing)
# ============================================================================


@dataclass
class FakeTransport:
    """Mock transport for offline testing."""

    response_sequence: List = field(default_factory=list)
    call_count: int = 0

    def __call__(self, payload: dict) -> dict:
        """Return canned response."""
        if self.call_count >= len(self.response_sequence):
            raise RuntimeError("No more canned responses in FakeTransport")
        response = self.response_sequence[self.call_count]
        self.call_count += 1
        return response


class FakeOpenAIDriver(AgentDriver):
    """OpenAI-compatible backend using FakeTransport for offline testing."""

    def __init__(self, transport: FakeTransport):
        self.transport = transport

    def probe_capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            name="fake-openai",
            tool_use_accuracy=0.85,
            recommended_verification_tier=2,
        )

    def run_command(
        self, command: str, cwd: Optional[str] = None, shell: Optional[str] = None
    ) -> CommandResult:
        """Invoke the transport and return formatted result."""
        try:
            # Build a minimal OpenAI Chat Completions payload.
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": command}],
                "temperature": 0,
            }
            response_data = self.transport(payload)
            # Format as JSON string in stdout.
            response_json = json.dumps(response_data)
            return CommandResult(exit_code=0, stdout=response_json, stderr="")
        except Exception as e:
            return CommandResult(exit_code=1, stdout="", stderr=str(e))

    def worker_status(self, worker_id: str) -> WorkerStatus:
        return WorkerStatus(worker_id=worker_id)

    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(worker_id="fake")

    def resolve_model(self, role: str) -> str:
        return "gpt-4o-mini"

    def get_tokens_spent(self) -> Optional[int]:
        return None


class OpenAICompatibleDriver(AgentDriver):
    """OpenAI-compatible backend (live or custom base_url)."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 120.0,
        model: str = "gpt-4o-mini",
    ):
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.model = model
        self.tokens_spent = 0
        self.last_context_pack = None
        # Evidence: the model id the API reports as having SERVED each call
        # (response body "model" field). Recorded so every rung's scorecard can
        # prove which brain actually answered, not just which was requested.
        self.served_models: List[str] = []

    def probe_capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            name="openai-compatible",
            tool_use_accuracy=0.85,
            recommended_verification_tier=2,
        )

    def run_command(
        self, command: str, cwd: Optional[str] = None, shell: Optional[str] = None
    ) -> CommandResult:
        """Call OpenAI Chat Completions API for decision-making."""
        try:
            # Ensure env var is set BEFORE accessing it (runtime check).
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return CommandResult(
                    exit_code=1,
                    stdout="",
                    stderr="OPENAI_API_KEY environment variable not set",
                )

            # If this is a decision command, build a proper prompt.
            if command.startswith("decide:"):
                decision_type = command.split(":", 1)[1]
                # Use the last context pack if available.
                if self.last_context_pack:
                    pack = self.last_context_pack
                    user_prompt = f"""You are the orchestrator adjudication seat for aesop.

Decision type: {decision_type}

File brain (orchestrator's only input):
"""
                    # Include main content (NO 500-char clip; pack's own size bounds apply).
                    for source, text in pack.content.items():
                        user_prompt += f"\n[{source}]:\n{text}\n"

                    # Include evidence section if present (increment 2.5).
                    if pack.evidence:
                        user_prompt += "\n[evidence]:\n"
                        for evidence_name, evidence_text in pack.evidence.items():
                            user_prompt += f"  {evidence_name}:\n{evidence_text}\n"

                    user_prompt += """

---

Respond with valid JSON (no code blocks, no markdown). Must include:
- verdict (string): "real_defect", "false_positive", "enhancement_opportunity", or "undetermined"
- evidence (string): your reasoning explaining the classification
- confidence (float 0.0-1.0): your confidence in this classification

Example:
{"verdict": "real_defect", "evidence": "Explanation of why this is a real defect", "confidence": 0.95}

Classify this finding."""
                else:
                    user_prompt = command

            else:
                user_prompt = command

            # Build the payload with temperature 0 for consistency. Reasoning-family
            # models (gpt-5.x) reject non-default temperature; on that specific 400
            # we drop the key and remember (recorded in scorecard as a parity note).
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": user_prompt}],
            }
            if not getattr(self, "omit_temperature", False):
                payload["temperature"] = 0

            try:
                response_data = default_openai_transport(
                    payload, timeout_s=self.timeout_s, base_url=self.base_url
                )
            except Exception as te:
                if "temperature" in str(te) and "unsupported_value" in str(te).lower():
                    self.omit_temperature = True
                    payload.pop("temperature", None)
                    response_data = default_openai_transport(
                        payload, timeout_s=self.timeout_s, base_url=self.base_url
                    )
                else:
                    raise

            # Track tokens if available.
            if isinstance(response_data, dict) and "usage" in response_data:
                usage = response_data.get("usage", {})
                self.tokens_spent += usage.get("total_tokens", 0)

            # Record the served model id (evidence of which brain answered).
            if isinstance(response_data, dict) and response_data.get("model"):
                self.served_models.append(str(response_data["model"]))

            # Extract the completion text and try to parse as JSON decision.
            if isinstance(response_data, dict) and "choices" in response_data:
                choices = response_data.get("choices", [])
                if choices and "message" in choices[0]:
                    completion_text = choices[0]["message"].get("content", "")
                    # Try to extract JSON from the completion.
                    try:
                        import re
                        # Try to extract JSON from markdown code blocks first.
                        code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', completion_text, re.DOTALL)
                        if code_match:
                            decision_json = json.loads(code_match.group(1))
                            return CommandResult(exit_code=0, stdout=json.dumps(decision_json), stderr="")

                        # Try to extract raw JSON object.
                        json_match = re.search(r'\{.*\}', completion_text, re.DOTALL)
                        if json_match:
                            decision_json = json.loads(json_match.group())
                            return CommandResult(exit_code=0, stdout=json.dumps(decision_json), stderr="")
                    except (json.JSONDecodeError, ValueError):
                        pass
                    # If no JSON found, return the text as-is for error handling.
                    return CommandResult(exit_code=1, stdout=completion_text, stderr="Failed to parse JSON from response")

            # Fallback: return the raw response.
            response_json = json.dumps(response_data)
            return CommandResult(exit_code=0, stdout=response_json, stderr="")

        except Exception as e:
            return CommandResult(exit_code=1, stdout="", stderr=str(e))

    def worker_status(self, worker_id: str) -> WorkerStatus:
        return WorkerStatus(worker_id=worker_id)

    def dispatch_worker(self, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(worker_id="fake")

    def resolve_model(self, role: str) -> str:
        return self.model

    def get_tokens_spent(self) -> Optional[int]:
        return self.tokens_spent


# ============================================================================
# Corpus and Scorecard
# ============================================================================


@dataclass
class CorpusItem:
    """One adjudication item from the corpus."""

    id: str
    finding_text: str
    source_lens: str
    incumbent_verdict: str
    ground_truth: str
    gt_note: str
    evidence: list = None

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = []


@dataclass
class ScorecardItem:
    """Scorecard entry for one adjudication."""

    id: str
    challenger_classification: str
    challenger_actionable: bool
    evidence_count: int
    schema_valid: bool
    retries_used: int
    agreement_with_incumbent: bool
    correct_vs_ground_truth: bool
    challenger_confidence: float = 0.0
    challenger_evidence: List[Dict[str, str]] = field(default_factory=list)


def load_corpus(corpus_path: str) -> List[CorpusItem]:
    """Load corpus from jsonl file (now with optional evidence field)."""
    items = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                labels = obj.get("labels", {})
                item = CorpusItem(
                    id=obj["id"],
                    finding_text=obj["finding_text"],
                    source_lens=obj["source_lens"],
                    incumbent_verdict=labels.get("incumbent_verdict", "unknown"),
                    ground_truth=labels.get("ground_truth", "unknown"),
                    gt_note=labels.get("gt_note", ""),
                    evidence=obj.get("evidence", []),
                )
                items.append(item)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing corpus line {line_num}: {e}", file=sys.stderr)
                raise
    return items


def build_finding_context_pack(
    item: CorpusItem, repo_root: str, conductor_root: str, enriched: bool = False, evidence_mode: str = "full"
) -> ContextPack:
    """Build a context pack for adjudication (BLIND: no labels).

    Args:
        item: Corpus item with finding_text and source_lens.
        repo_root: Repo root path.
        conductor_root: Conductor root path.
        enriched: If True, include evidence from the corpus item (increment 2.5).
        evidence_mode: How much evidence to surface when enriched=True:
          - 'full': all 3 parts (mechanism + behavior + impact/conclusion)
          - 'mechanism': first 2 parts only (mechanism + behavior, no conclusions)
          - Mechanism mode prevents answer-leakage from [3] impact clauses.

    Returns:
        ContextPack with finding_text + source framing (no labels).
        If enriched, also includes evidence section (sliced per evidence_mode).
    """
    # Build sources dict: finding text + source lens.
    # This is the BLIND framing the challenger sees.
    sources = {
        "brief:finding": None,  # Will be constructed inline.
    }

    # Construct the brief as finding_text + source framing.
    finding_brief = f"""FINDING: {item.finding_text}

Source lens: {item.source_lens}

Please adjudicate this finding. Classify it as one of:
- real_defect: actionable code/process defect needing a fix
- false_positive: not actually a defect (e.g., misunderstood, refuted by evidence)
- enhancement_opportunity: nice-to-have, not blocking
- undetermined: insufficient information to classify

Provide evidence supporting your classification."""

    # Override the brief source with the constructed text.
    # We'll manually pass this to the OrchestratorDriver.
    pack = ContextPack(
        decision_type="adjudicate_finding",
        sources_requested=("finding",),
        content={"finding": finding_brief},
        total_size_bytes=len(finding_brief.encode("utf-8")),
    )
    pack.manifest.append(
        {
            "source": "finding",
            "included": True,
            "truncated": False,
            "truncation_reason": None,
            "size_bytes": len(finding_brief.encode("utf-8")),
        }
    )

    # Add evidence if enriched mode is enabled (increment 2.5).
    if enriched and item.evidence:
        # Slice evidence based on mode: mechanism mode drops the [3] conclusion clause
        # to prevent answer-leakage (confound fix).
        evidence_list = item.evidence
        if evidence_mode == "mechanism":
            # Mechanism mode: keep only first 2 items (mechanism + behavior)
            evidence_list = item.evidence[:2]
        elif evidence_mode != "full":
            raise ValueError(f"Unknown evidence_mode: {evidence_mode}")

        # Convert evidence list to a dict for build_context_pack
        evidence_dict = {}
        for idx, evidence_item in enumerate(evidence_list):
            evidence_dict[f"evidence_{idx}"] = evidence_item

        # Rebuild pack with evidence
        pack_with_evidence = build_context_pack(
            decision_type="adjudicate_finding",
            sources=sources,
            repo_root=repo_root,
            conductor_root=conductor_root,
            evidence=evidence_dict,
        )
        return pack_with_evidence

    return pack


def adjudicate_one_finding(
    driver: OrchestratorDriver,
    item: CorpusItem,
    repo_root: str,
    conductor_root: str,
    schema: Optional[Dict[str, Any]],
    enriched: bool = False,
    evidence_mode: str = "full",
) -> ScorecardItem:
    """Run one adjudication decision through the driver."""
    try:
        # Build context pack (BLIND; optionally enriched with evidence).
        pack = build_finding_context_pack(item, repo_root, conductor_root, enriched=enriched, evidence_mode=evidence_mode)

        # Verify labels never reach the pack (unit test for blind adjudication).
        pack_text = json.dumps(pack.content)
        for label_key in ["incumbent_verdict", "ground_truth", "gt_note"]:
            if label_key in pack_text:
                print(
                    f"ERROR: Label '{label_key}' found in context pack for {item.id}",
                    file=sys.stderr,
                )
                raise ValueError(f"Blind adjudication violated: {label_key} in pack")

        # Pass the context pack to the backend so it can use it in API calls.
        if hasattr(driver.backend, "last_context_pack"):
            driver.backend.last_context_pack = pack

        # Call the driver.
        decision = driver.decide("adjudicate_finding", pack, schema=schema)

        # Parse decision.
        verdict_obj = decision.get("verdict", {})
        if isinstance(verdict_obj, dict):
            classification = verdict_obj.get("classification", "undetermined")
            actionable = verdict_obj.get("actionable", False)
        else:
            classification = str(verdict_obj)
            actionable = False

        evidence = decision.get("evidence", [])
        evidence_count = len(evidence) if isinstance(evidence, list) else 0

        retries = decision.get("retry_count", 0)
        schema_valid = decision.get("schema_validated", False)
        confidence = decision.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0

        # If decision failed, log it for debugging
        if "DECISION_FAILED" in str(decision.get("verdict", "")):
            print(
                f"    [FAILED] {item.id}: {decision.get('evidence', 'no error message')}",
                file=sys.stderr,
            )

        # Map incumbent verdict to schema enum.
        incumbent_enum = item.incumbent_verdict.lower()
        challenger_enum = classification.lower()
        agreement = incumbent_enum == challenger_enum

        # Correct vs ground truth.
        ground_truth_enum = item.ground_truth.lower()
        correct = challenger_enum == ground_truth_enum

        return ScorecardItem(
            id=item.id,
            challenger_classification=classification,
            challenger_actionable=actionable,
            evidence_count=evidence_count,
            schema_valid=schema_valid,
            retries_used=retries,
            agreement_with_incumbent=agreement,
            correct_vs_ground_truth=correct,
            challenger_confidence=confidence,
            challenger_evidence=evidence if isinstance(evidence, list) else [],
        )

    except Exception as e:
        print(f"Error adjudicating {item.id}: {e}", file=sys.stderr)
        return ScorecardItem(
            id=item.id,
            challenger_classification="DECISION_FAILED",
            challenger_actionable=False,
            evidence_count=0,
            schema_valid=False,
            retries_used=0,
            agreement_with_incumbent=False,
            correct_vs_ground_truth=False,
        )


def compute_scorecard_stats(
    scorecard: List[ScorecardItem], corpus: List[CorpusItem]
) -> Dict[str, Any]:
    """Compute aggregate statistics."""
    if not scorecard:
        return {}

    # Agreement rates.
    total_agreement = sum(1 for s in scorecard if s.agreement_with_incumbent)
    overall_agreement_pct = (total_agreement / len(scorecard)) * 100 if scorecard else 0

    # Real defect subset (ground_truth == real_defect).
    real_defect_items = [
        (c, s)
        for c, s in zip(corpus, scorecard)
        if c.ground_truth.lower() == "real_defect"
    ]
    real_defect_agreement = sum(1 for _, s in real_defect_items if s.correct_vs_ground_truth)
    real_defect_pct = (
        (real_defect_agreement / len(real_defect_items)) * 100
        if real_defect_items
        else 0
    )

    # False positive subset (ground_truth == false_positive).
    false_positive_items = [
        (c, s)
        for c, s in zip(corpus, scorecard)
        if c.ground_truth.lower() == "false_positive"
    ]
    false_positive_agreement = sum(
        1 for _, s in false_positive_items if s.correct_vs_ground_truth
    )
    false_positive_pct = (
        (false_positive_agreement / len(false_positive_items)) * 100
        if false_positive_items
        else 0
    )

    # Rubber-stamp test: items 9 (whitelist-gate-weakening) and 14 (regression-ui-suite).
    rubber_stamp_items = [s for s in scorecard if s.id in ["whitelist-gate-weakening", "regression-ui-suite"]]
    rubber_stamp_refutations = sum(
        1 for s in rubber_stamp_items if s.challenger_classification == "false_positive"
    )

    # Schema validity rate.
    schema_valid_count = sum(1 for s in scorecard if s.schema_valid)
    schema_valid_pct = (schema_valid_count / len(scorecard)) * 100 if scorecard else 0

    # DECISION_FAILED count.
    decision_failed_count = sum(
        1 for s in scorecard if s.challenger_classification == "DECISION_FAILED"
    )

    return {
        "overall_agreement_pct": round(overall_agreement_pct, 1),
        "real_defect_agreement_pct": round(real_defect_pct, 1),
        "false_positive_agreement_pct": round(false_positive_pct, 1),
        "rubber_stamp_refutations_count": rubber_stamp_refutations,
        "schema_valid_pct": round(schema_valid_pct, 1),
        "decision_failed_count": decision_failed_count,
        "total_items": len(scorecard),
    }


def write_scorecard_json(
    scorecard: List[ScorecardItem],
    stats: Dict[str, Any],
    output_path: str,
) -> None:
    """Write full scorecard as JSON."""
    items = [
        {
            "id": s.id,
            "challenger_classification": s.challenger_classification,
            "challenger_actionable": s.challenger_actionable,
            "evidence_count": s.evidence_count,
            "schema_valid": s.schema_valid,
            "retries_used": s.retries_used,
            "agreement_with_incumbent": s.agreement_with_incumbent,
            "correct_vs_ground_truth": s.correct_vs_ground_truth,
            "challenger_confidence": s.challenger_confidence,
        }
        for s in scorecard
    ]

    data = {"statistics": stats, "items": items}

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)

    print(f"Wrote scorecard JSON: {output_path}")


def write_scorecard_md(
    scorecard: List[ScorecardItem],
    corpus: List[CorpusItem],
    stats: Dict[str, Any],
    output_path: str,
    model: str = "gpt-4o-mini",
) -> None:
    """Write human-readable scorecard as Markdown."""
    lines = [
        "# Shadow Adjudication Wave — Scorecard Report",
        "",
        "**Date**: 2026-07-23",
        f"**Challenger Model**: {model} (OpenAI-compatible)",
        "**Corpus Size**: 16 items",
        "",
        "## Aggregate Statistics",
        "",
        f"- **Overall Agreement (vs incumbent)**: {stats.get('overall_agreement_pct', 0):.1f}%",
        f"- **Real Defect Subset Agreement**: {stats.get('real_defect_agreement_pct', 0):.1f}%",
        f"- **False Positive Subset Agreement**: {stats.get('false_positive_agreement_pct', 0):.1f}%",
        f"- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): {stats.get('rubber_stamp_refutations_count', 0)}/2",
        f"- **Schema Validity Rate**: {stats.get('schema_valid_pct', 0):.1f}%",
        f"- **DECISION_FAILED Count**: {stats.get('decision_failed_count', 0)}",
        "",
        "## Success Bar Results",
        "",
    ]

    # Check success criteria.
    real_defect_pct = stats.get("real_defect_agreement_pct", 0)
    rubber_stamp = stats.get("rubber_stamp_refutations_count", 0)
    schema_pct = stats.get("schema_valid_pct", 0)

    lines.append(
        f"- >=80% agreement on gt=real_defect items: "
        f"**{'PASS' if real_defect_pct >= 80 else 'FAIL'}** ({real_defect_pct:.1f}%)"
    )
    lines.append(
        f"- >=1 of items {{9, 14}} classified false_positive: "
        f"**{'PASS' if rubber_stamp >= 1 else 'FAIL'}** ({rubber_stamp}/2)"
    )
    lines.append(
        f"- >=90% schema-valid without retry exhaustion: "
        f"**{'PASS' if schema_pct >= 90 else 'FAIL'}** ({schema_pct:.1f}%)"
    )

    lines.extend(
        [
            "",
            "## Item-by-Item Results",
            "",
            "| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |",
            "|---|---|---|---|---|---|",
        ]
    )

    for corp, score in zip(corpus, scorecard):
        correct = "✓" if score.correct_vs_ground_truth else "✗"
        schema_ok = "✓" if score.schema_valid else "✗"
        lines.append(
            f"| {score.id} | {score.challenger_classification} | {corp.ground_truth} | {correct} | {score.challenger_confidence:.2f} | {schema_ok} |"
        )

    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- **Corpus Size**: N=16 (single replay, not statistically comprehensive)",
            "- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)",
            "- **Single Run**: No repeated trials; variance not measured",
            "- **Real-World Drift**: Actual adjudication may differ on live production findings",
        ]
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote scorecard markdown: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Shadow adjudication wave: replay corpus through OrchestratorDriver"
    )
    parser.add_argument(
        "--corpus",
        required=True,
        help="Path to corpus jsonl file",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run offline with FakeTransport (for testing)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live with real OpenAI API (requires OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Challenger model id for the ladder (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--enriched",
        action="store_true",
        default=False,
        help="Use enriched context packs with evidence (increment 2.5; default: off for reproducibility)",
    )
    parser.add_argument(
        "--evidence-mode",
        choices=["full", "mechanism"],
        default="full",
        help="How much evidence to surface when --enriched is used: 'full' (all 3 parts, may leak answers), 'mechanism' (first 2 parts only, no conclusions)",
    )
    parser.add_argument(
        "--out-tag",
        default=None,
        help="Results filename tag (default: derived from --model); rung files never overwrite each other",
    )

    args = parser.parse_args()

    # Validate corpus path.
    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"Error: corpus file not found: {corpus_path}", file=sys.stderr)
        sys.exit(1)

    # Load corpus.
    try:
        corpus = load_corpus(str(corpus_path))
        print(f"Loaded {len(corpus)} corpus items")
    except Exception as e:
        print(f"Error loading corpus: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate item count.
    if len(corpus) != 16:
        print(f"Error: corpus must have exactly 16 items, got {len(corpus)}", file=sys.stderr)
        sys.exit(1)

    # Set up driver and backend.
    repo_root = REPO_ROOT
    conductor_root = Path.home() / "conductor3"

    # Load schema.
    schema_path = DRIVER_DIR / "decisions" / "adjudicate_finding.schema.json"
    schema = None
    if schema_path.exists():
        try:
            with open(schema_path, encoding="utf-8") as f:
                schema = json.load(f)
        except Exception as e:
            print(f"Warning: failed to load schema: {e}", file=sys.stderr)

    if args.offline:
        print("Running in OFFLINE mode (FakeTransport)")
        # For offline mode, use canned responses (real-world would use FakeTransport here).
        # For now, just create a fake driver that returns placeholder responses.
        transport = FakeTransport()
        backend = FakeOpenAIDriver(transport)
    elif args.live:
        print("Running in LIVE mode (OpenAI API)")
        # Check for API key at runtime.
        if not os.environ.get("OPENAI_API_KEY"):
            print(
                "Error: OPENAI_API_KEY environment variable not set",
                file=sys.stderr,
            )
            sys.exit(1)
        backend = OpenAICompatibleDriver(model=args.model)
    else:
        print("Error: specify --offline or --live", file=sys.stderr)
        sys.exit(1)

    # Create OrchestratorDriver.
    driver = OrchestratorDriver(backend, schema_dir=str(DRIVER_DIR), max_retries=2)

    # Run adjudications.
    scorecard = []
    api_call_count = 0
    max_calls = 40

    for item in corpus:
        if api_call_count >= max_calls:
            print(
                f"Reached max API calls ({max_calls}). Stopping adjudication.",
                file=sys.stderr,
            )
            break

        result = adjudicate_one_finding(
            driver, item, str(repo_root), str(conductor_root), schema, enriched=args.enriched, evidence_mode=args.evidence_mode
        )
        scorecard.append(result)
        api_call_count += 1

        print(f"  [{api_call_count:2d}] {item.id}: {result.challenger_classification}")

    # Compute stats.
    stats = compute_scorecard_stats(scorecard, corpus[: len(scorecard)])
    stats["challenger_model_requested"] = args.model
    stats["challenger_model"] = args.model
    # Served-model receipts: what the API says actually answered each call.
    served = sorted(set(getattr(backend, "served_models", [])))
    stats["served_models"] = served
    stats["temperature_omitted"] = bool(getattr(backend, "omit_temperature", False))
    print(f"Served models (API-reported): {served or 'NONE RECORDED (offline mode?)'}")
    if stats["temperature_omitted"]:
        print("PARITY NOTE: model rejected temperature=0; ran at API default (recorded in scorecard)")

    # Write outputs.
    results_dir = REPO_ROOT / "bench" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Per-rung output files: default tag from model id so ladder runs never clobber.
    # If enriched mode is on, add "-enriched" to tag.
    # Rung 1 (gpt-4o-mini) keeps its original untagged filenames for continuity.
    if args.out_tag:
        tag = args.out_tag
    else:
        base_tag = "" if args.model == "gpt-4o-mini" else "-" + args.model.replace("/", "_")
        enriched_suffix = "-enriched" if args.enriched else ""
        tag = base_tag + enriched_suffix

    json_path = results_dir / f"shadow-adjudication-2026-07-23{tag}.json"
    md_path = results_dir / f"shadow-adjudication-2026-07-23{tag}.md"

    write_scorecard_json(scorecard, stats, str(json_path))
    write_scorecard_md(scorecard, corpus[: len(scorecard)], stats, str(md_path), model=args.model)

    # Print summary.
    print("")
    print("=" * 60)
    print("SHADOW ADJUDICATION WAVE — SUMMARY")
    print("=" * 60)
    print(f"Overall Agreement: {stats.get('overall_agreement_pct', 0):.1f}%")
    print(
        f"Real Defect Accuracy: {stats.get('real_defect_agreement_pct', 0):.1f}%"
    )
    print(
        f"False Positive Accuracy: {stats.get('false_positive_agreement_pct', 0):.1f}%"
    )
    print(
        f"Rubber-Stamp Refutations: {stats.get('rubber_stamp_refutations_count', 0)}/2"
    )
    print(f"Schema Validity: {stats.get('schema_valid_pct', 0):.1f}%")
    print(f"DECISION_FAILED: {stats.get('decision_failed_count', 0)}")
    print("=" * 60)

    # Get tokens spent (if available).
    tokens = backend.get_tokens_spent()
    if tokens:
        print(f"Total tokens spent: {tokens}")

    print("")
    print(f"Results written to:")
    print(f"  {json_path}")
    print(f"  {md_path}")


if __name__ == "__main__":
    main()
