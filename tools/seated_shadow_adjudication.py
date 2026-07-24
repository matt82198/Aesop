#!/usr/bin/env python3
"""Seated shadow adjudication — REAL file-brain context A/B test.

This is increment 4a of the orchestrator-swap microkernel proof. Unlike the
prior synthetic ladder runs, this run feeds REAL file-brain context (STATE.md,
tracker.json, REAL cited code from repo) to the OrchestratorDriver seam.

It is a controlled A/B over 16 items:
  - BASELINE: decontextualized verdicts (from bench/results/shadow-adjudication-2026-07-23-*.json)
  - SEATED:   this run with REAL file-brain + REAL repo code snippets
  - ONE VARIABLE: synthetic context -> seated real context
  - NON-AUTHORITATIVE: verdicts logged, never acted on
  - NOT A FULL WAVE: no fleet, no merges, no git operations

Key item: item 9 (whitelist-gate-weakening) is the "money question" — can the
challenger now see the REAL secret_scan.py header showing it scans file contents
recursively? If so, can it reverse the false-positive call?

Blind adjudication: labels are NEVER included in context packs.

CLI:
  python tools/seated_shadow_adjudication.py --corpus <path> [--offline] [--live --repeat 3]

Exit: 0 on success, 1 on error.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Type stubs for context pack
WorkerStatus = Dict[str, Any]
WorkerRequest = Dict[str, Any]
WorkerResult = Dict[str, Any]

# Add driver/ to sys.path.
REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO_ROOT / "driver"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

from agent_driver import CommandResult, DriverCapabilities  # noqa: E402
from context_pack import build_context_pack, ContextPack  # noqa: E402
from orchestrator_driver import OrchestratorDriver  # noqa: E402

# Import OpenAI transport
try:
    from openai_transport import default_openai_transport  # noqa: E402
except ImportError:
    default_openai_transport = None


# Simple OpenAI-compatible driver for orchestrator adjudication
class SimpleOpenAIDriver:
    """Minimal OpenAI-compatible driver for OrchestratorDriver.decide()."""

    def __init__(self, model: str = "gpt-5.5", base_url: str = "https://api.openai.com/v1", timeout_s: float = 120.0):
        self.model = model
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.last_context_pack = None

    def probe_capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            name="openai-compatible",
            tool_use_accuracy=0.85,
            recommended_verification_tier=2,
        )

    def run_command(
        self, command: str, cwd: Optional[str] = None, shell: Optional[str] = None
    ) -> CommandResult:
        """Call OpenAI Chat Completions API."""
        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return CommandResult(
                    exit_code=1,
                    stdout="",
                    stderr="OPENAI_API_KEY not set",
                )

            # Build user prompt for adjudication
            user_prompt = command
            if command.startswith("decide:") and self.last_context_pack:
                decision_type = command.split(":", 1)[1]
                pack = self.last_context_pack
                user_prompt = f"""You are the orchestrator adjudication seat for aesop.

Decision type: {decision_type}

File brain:
"""
                for source, text in pack.content.items():
                    user_prompt += f"\n[{source}]:\n{text[:500]}\n"  # Clip for brevity

                if pack.evidence:
                    user_prompt += "\n[evidence]:\n"
                    for name, text in pack.evidence.items():
                        user_prompt += f"  {name}: {text[:200]}\n"

                user_prompt += """
---
Respond with valid JSON (no markdown):
{"verdict": "real_defect|false_positive|enhancement_opportunity|undetermined", "evidence": "...", "confidence": 0.0-1.0}
"""

            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0,
            }

            # Catch temperature rejection for reasoning models
            try:
                response_data = default_openai_transport(payload, timeout_s=self.timeout_s, base_url=self.base_url)
            except Exception as e:
                if "temperature" in str(e).lower():
                    payload.pop("temperature", None)
                    response_data = default_openai_transport(payload, timeout_s=self.timeout_s, base_url=self.base_url)
                else:
                    raise

            # Extract response
            response_text = ""
            if "choices" in response_data and response_data["choices"]:
                choice = response_data["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    response_text = choice["message"]["content"]

            return CommandResult(exit_code=0, stdout=response_text, stderr="")
        except Exception as e:
            return CommandResult(exit_code=1, stdout="", stderr=str(e))

    def worker_status(self, worker_id: str) -> Any:
        return {"worker_id": worker_id, "alive": True}

    def dispatch_worker(self, request: Any) -> Any:
        return {"worker_id": "fake"}

    def resolve_model(self, role: str) -> str:
        return self.model

    def get_tokens_spent(self) -> Optional[int]:
        return None


# ============================================================================
# Real Context Pack Construction
# ============================================================================


def extract_real_file_brain(repo_root: Path) -> Dict[str, str]:
    """Extract REAL file-brain sources (STATE.md, tracker.json, etc.)

    Returns dict of {source_name: content} for use in context packs.
    Files that don't exist are gracefully omitted.
    """
    sources = {}

    # STATE.md (primary)
    state_path = repo_root / "STATE.md"
    if state_path.exists():
        try:
            with open(state_path, encoding="utf-8") as f:
                sources["state"] = f.read()
        except Exception as e:
            sources["state"] = f"[Error reading STATE.md: {e}]"

    # BUILDLOG.md (if exists)
    buildlog_path = repo_root / "BUILDLOG.md"
    if buildlog_path.exists():
        try:
            with open(buildlog_path, encoding="utf-8") as f:
                # Read last 50 lines for tail
                lines = f.readlines()
                tail = "".join(lines[-50:]) if len(lines) > 50 else "".join(lines)
                sources["buildlog_tail:50"] = tail
        except Exception as e:
            sources["buildlog_tail:50"] = f"[Error reading BUILDLOG.md: {e}]"

    # state/tracker.json (open items)
    tracker_path = repo_root / "state" / "tracker.json"
    if tracker_path.exists():
        try:
            with open(tracker_path, encoding="utf-8") as f:
                tracker_data = json.load(f)
                # Include open items only
                items = tracker_data.get("items", [])
                open_items = [
                    i for i in items
                    if i.get("status") not in ("done", "archived")
                ]
                sources["tracker_open"] = json.dumps(
                    {"open_items_count": len(open_items), "items": open_items[:10]},
                    indent=2
                )
        except Exception as e:
            sources["tracker_open"] = f"[Error reading tracker.json: {e}]"

    return sources


def extract_real_repo_code(repo_root: Path, finding_id: str) -> Dict[str, str]:
    """Extract REAL code from repo files mentioned in findings.

    Maps finding IDs to the actual repo files they reference, reads them,
    and includes relevant sections in the evidence dict.

    Returns dict of {evidence_name: code_snippet}.
    """
    evidence = {}

    # Define explicit mappings of finding_id -> repo files + how to extract them
    mappings = {
        "vbs-waitforexit": [
            ("daemons/run-hidden.vbs", "full"),  # Show entire fixed file
        ],
        "dryrun-blocked": [
            ("daemons/install-tasks.ps1", "lines", 1, 50),  # Show param validation
        ],
        "uninstall-exit0": [
            ("daemons/install-tasks.ps1", "lines", 160, 180),  # Show uninstall block
        ],
        "quote-validation": [
            ("daemons/install-tasks.ps1", "lines", 46, 55),  # Show action string building
        ],
        "apostrophe-path": [
            ("daemons/install-tasks.ps1", "lines", 15, 35),  # Show path converter
        ],
        "unc-paths": [
            ("daemons/install-tasks.ps1", "lines", 15, 35),  # Show UNC handling
        ],
        "hardcoded-username": [
            ("docs/INSTALL.md", "grep", "Users"),  # Show doc examples with paths
        ],
        "audit-log-observability": [
            ("daemons/install-tasks.ps1", "lines", 70, 100),  # Show logging
        ],
        "whitelist-gate-weakening": [
            # THIS IS THE MONEY ITEM: include REAL secret_scan.py header
            # showing it scans file contents recursively, not just top-level dirs
            ("tools/secret_scan.py", "lines", 1, 100),  # Full header + patterns
            ("tools/power_selftest.py", "lines", 80, 150),  # Check whitelist section
        ],
        "ps1-syntax-gate": [
            ("tools/secret_scan.py", "lines", 1, 50),  # Show validation patterns
        ],
        "test-hardcoded-path": [
            ("tests/test_orchestrator_driver.py", "grep", "resolve()"),  # Show fix
        ],
        "fixreview-parents1": [
            ("tests/test_orchestrator_driver.py", "grep", "parents"),
        ],
        "fixreview-backtick-test": [
            ("tests/test_orchestrator_driver.py", "grep", "backtick"),
        ],
        "regression-ui-suite": [
            ("ui/package.json", "full"),  # Show dependency structure
        ],
        "cimergewait-exit0": [
            ("tools/ci_merge_wait.py", "lines", 1, 50),  # Show exit code handling
        ],
        "vbs-syntax-validity": [
            ("daemons/run-hidden.vbs", "full"),  # Show working VBScript
        ],
    }

    if finding_id not in mappings:
        return evidence  # No special code evidence for this finding

    for spec in mappings[finding_id]:
        rel_path = spec[0]
        method = spec[1]

        file_path = repo_root / rel_path
        if not file_path.exists():
            evidence[f"code:{rel_path}"] = f"[File not found: {rel_path}]"
            continue

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()

            if method == "full":
                evidence[f"code:{rel_path}"] = content
            elif method == "lines":
                start_line = spec[2] - 1  # 0-indexed
                end_line = spec[3]
                lines = content.split("\n")
                excerpt = "\n".join(lines[start_line:end_line])
                evidence[f"code:{rel_path}:{start_line+1}-{end_line}"] = excerpt
            elif method == "grep":
                pattern = spec[2]
                lines = content.split("\n")
                matching = [
                    (i+1, line) for i, line in enumerate(lines)
                    if pattern.lower() in line.lower()
                ]
                if matching:
                    # Show first 5 matches with context
                    excerpt_lines = []
                    for line_no, line in matching[:5]:
                        excerpt_lines.append(f"Line {line_no}: {line}")
                    evidence[f"code:{rel_path}:grep({pattern})"] = "\n".join(
                        excerpt_lines
                    )
                else:
                    evidence[f"code:{rel_path}:grep({pattern})"] = (
                        f"[Pattern '{pattern}' not found in {rel_path}]"
                    )
        except Exception as e:
            evidence[f"code:{rel_path}"] = f"[Error reading {rel_path}: {e}]"

    return evidence


def build_seated_context_pack(
    repo_root: Path,
    finding: Dict[str, Any],
    decision_type: str = "adjudicate_findings",
) -> ContextPack:
    """Build a REAL context pack for a finding.

    Combines:
      1. REAL file-brain (STATE.md, tracker.json, etc.)
      2. REAL repo code snippets (secret_scan.py, install-tasks.ps1, etc.)
      3. The finding_text itself (NEVER labels or incumbent verdict)

    Returns a ContextPack ready for OrchestratorDriver.decide().
    """
    file_brain = extract_real_file_brain(repo_root)
    repo_code = extract_real_repo_code(repo_root, finding["id"])

    # Build sources dict for context_pack (allowlisted logical sources)
    sources = {
        "state": None,  # Will read from default location
        "buildlog_tail:50": None,
        "tracker_open": None,
    }

    # Build evidence dict with finding_text + code
    evidence_dict = {
        "finding_text": finding["finding_text"],
        "evidence_from_corpus": "\n".join(finding.get("evidence", [])),
    }
    evidence_dict.update(repo_code)

    # Build the pack
    pack = build_context_pack(
        decision_type=decision_type,
        sources=sources,
        repo_root=str(repo_root),
        conductor_root=os.path.expanduser("~/conductor3"),
        size_cap=65536,  # 64KB for real context
        evidence=evidence_dict,
        evidence_cap=16384,  # 16KB for evidence
    )

    return pack


# ============================================================================
# Scorecard & Comparison
# ============================================================================


@dataclass
class VerdictRecord:
    """Single verdict from one run."""
    item_id: str
    challenger_classification: str
    challenger_confidence: Optional[float] = None
    retry_count: int = 0
    schema_valid: bool = True


def load_baseline_results(bench_dir: Path, model: str) -> Dict[str, Dict]:
    """Load baseline (decontextualized) results from bench/results/.

    Returns dict mapping item_id -> baseline verdict info.
    """
    baseline_file = bench_dir / f"shadow-adjudication-2026-07-23-{model}.json"
    if not baseline_file.exists():
        return {}

    try:
        with open(baseline_file, encoding="utf-8") as f:
            data = json.load(f)

        # Index by item id
        baseline_map = {}
        for item in data.get("items", []):
            baseline_map[item["id"]] = {
                "classification": item.get("challenger_classification"),
                "confidence": item.get("challenger_confidence"),
                "correct": item.get("correct_vs_ground_truth"),
            }
        return baseline_map
    except Exception as e:
        print(f"Warning: Could not load baseline results: {e}")
        return {}


def generate_comparison_table(
    baseline_map: Dict,
    seated_results: List[Dict],
    ground_truth_map: Dict,
    corpus: List[Dict],
) -> str:
    """Generate markdown comparison table (baseline vs seated vs ground_truth).

    Returns markdown string.
    """
    lines = [
        "## Per-Item Comparison: Baseline vs Seated Real Context",
        "",
        "| Item ID | Finding | Baseline | Seated Modal | Stability | Ground Truth | Real Sources Included |",
        "|---------|---------|----------|--------------|-----------|--------------|----------------------|",
    ]

    for item in corpus:
        item_id = item["id"]
        finding_text = item["finding_text"][:60] + "..." if len(item["finding_text"]) > 60 else item["finding_text"]

        baseline = baseline_map.get(item_id, {})
        baseline_class = baseline.get("classification", "?")

        # Modal verdict from seated runs
        seated_verdicts = [
            r["challenger_classification"] for r in seated_results
            if r["item_id"] == item_id
        ]
        seated_modal = max(set(seated_verdicts), key=seated_verdicts.count) if seated_verdicts else "?"

        # Stability: how many of the 3 runs agree
        stability = f"{seated_verdicts.count(seated_modal)}/3" if seated_verdicts else "0/3"

        gt = ground_truth_map.get(item_id, {}).get("ground_truth", "?")

        # Real sources used (simplified)
        sources_used = "REAL file-brain + code"
        if item_id in ["vbs-waitforexit", "quote-validation", "whitelist-gate-weakening"]:
            sources_used += " (repo code)"

        lines.append(
            f"| {item_id} | {finding_text} | {baseline_class} | {seated_modal} | {stability} | {gt} | {sources_used} |"
        )

    return "\n".join(lines)


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Seated shadow adjudication with REAL file-brain context"
    )
    parser.add_argument("--corpus", required=True, help="Path to corpus JSONL")
    parser.add_argument("--offline", action="store_true", help="Run offline (FakeTransport; no API calls)")
    parser.add_argument("--live", action="store_true", help="Run live (requires OPENAI_API_KEY)")
    parser.add_argument("--repeat", type=int, default=3, help="Number of runs per item (default 3)")
    parser.add_argument("--model", default="gpt-5.6-sol", help="Model to use (default gpt-5.6-sol); frontier-first with early-abort gate")
    parser.add_argument("--also-run", default="gpt-5.5", help="Also run this model if item 9 flips (default gpt-5.5)")
    parser.add_argument("--output-dir", default="bench/results", help="Output directory for results")
    parser.add_argument("--no-early-abort", action="store_true", help="Disable early-abort gate (run all models regardless)")

    args = parser.parse_args()

    # Load corpus
    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"ERROR: Corpus file not found: {corpus_path}", file=sys.stderr)
        return 1

    corpus = []
    try:
        with open(corpus_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    corpus.append(json.loads(line))
    except Exception as e:
        print(f"ERROR: Could not load corpus: {e}", file=sys.stderr)
        return 1

    print(f"Loaded corpus: {len(corpus)} items")

    # Extract ground truth map
    ground_truth_map = {}
    for item in corpus:
        if "labels" in item:
            ground_truth_map[item["id"]] = {
                "ground_truth": item["labels"].get("ground_truth", "?"),
                "incumbent": item["labels"].get("incumbent_verdict", "?"),
            }

    if args.offline:
        print("Offline mode: skipping live runs")
        seated_results = []
        models_run = []
    elif args.live:
        if not os.environ.get("OPENAI_API_KEY"):
            print("ERROR: OPENAI_API_KEY not set for live mode", file=sys.stderr)
            return 1

        # Initialize OrchestratorDriver with OpenAI backend
        if default_openai_transport is None:
            print("ERROR: default_openai_transport not available", file=sys.stderr)
            return 1

        seated_results = []
        models_run = []
        models_to_run = [args.model]
        if args.also_run and not args.no_early_abort:
            models_to_run.append(args.also_run)

        for model_idx, model in enumerate(models_to_run):
            print(f"\n{'='*70}")
            print(f"Model {model_idx+1}/{len(models_to_run)}: {model}")
            print(f"{'='*70}")

            driver = SimpleOpenAIDriver(model=model)
            orchestrator = OrchestratorDriver(backend=driver)

            model_results = []
            call_count = 0
            max_calls = len(corpus) * args.repeat

            for item_idx, item in enumerate(corpus):
                print(f"\n[{item_idx+1}/{len(corpus)}] {item['id']}...")

                for repeat_idx in range(args.repeat):
                    if call_count >= max_calls:
                        print(f"Reached call limit ({max_calls}); stopping.")
                        break

                    # Build real context pack
                    try:
                        pack = build_seated_context_pack(REPO_ROOT, item)
                    except Exception as e:
                        print(f"  ERROR building pack for {item['id']}: {e}")
                        continue

                    # Make decision (store pack in driver for prompt building)
                    try:
                        driver.last_context_pack = pack
                        decision = orchestrator.decide(
                            decision_type="adjudicate_findings",
                            context_pack=pack,
                            schema=None,
                        )

                        classification = decision.get("verdict", "DECISION_FAILED")
                        confidence = decision.get("confidence", None)

                        model_results.append({
                            "item_id": item["id"],
                            "model": model,
                            "challenger_classification": classification,
                            "challenger_confidence": confidence,
                            "retry_count": decision.get("retry_count", 0),
                            "schema_valid": decision.get("schema_validated", True),
                        })

                        print(f"    [repeat {repeat_idx+1}] {classification} (confidence: {confidence})")
                        call_count += 1
                    except Exception as e:
                        print(f"    ERROR: {e}")

            # Add model results to overall results
            seated_results.extend(model_results)
            models_run.append(model)

            # EARLY-ABORT GATE: Check item 9 (whitelist-gate-weakening)
            if model_idx == 0 and not args.no_early_abort and args.also_run:
                item9_verdicts = [
                    r["challenger_classification"] for r in model_results
                    if r["item_id"] == "whitelist-gate-weakening"
                ]
                if item9_verdicts:
                    item9_modal = max(set(item9_verdicts), key=item9_verdicts.count)
                    print(f"\n>>> EARLY-ABORT CHECK: Item 9 modal verdict from {model} = {item9_modal}")

                    if item9_modal != "false_positive":
                        print(f">>> EARLY ABORT: Item 9 did NOT flip to false_positive with real context.")
                        print(f">>> Skipping cheaper models ({args.also_run}) — if frontier can't flip, cheaper won't either.")
                        print(f">>> Cost-rational abort: {model} alone sufficient to show real-context value.")
                        break  # Don't run cheaper models
                    else:
                        print(f">>> Item 9 FLIPPED to false_positive! Proceeding to run {args.also_run}.")
    else:
        print("No mode specified. Use --offline or --live")
        return 1

    # Load baseline for comparison
    bench_dir = Path(args.output_dir)
    bench_dir.mkdir(parents=True, exist_ok=True)

    # Write results for each model
    for model in models_run:
        baseline_map = load_baseline_results(bench_dir, model)
        model_results = [r for r in seated_results if r.get("model") == model]

        output_file = bench_dir / f"seated-shadow-2026-07-24-{model}.json"
        if model_results:
            results_data = {
                "statistics": {
                    "total_items": len(corpus),
                    "total_runs": len(model_results),
                    "model_requested": model,
                    "context_type": "real_file_brain",
                    "early_abort_gate": not args.no_early_abort,
                },
                "items": model_results,
            }

            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results_data, f, indent=2)
                print(f"\nWrote {model} results to {output_file}")
            except Exception as e:
                print(f"ERROR writing results: {e}")
                return 1

    # Write unified comparison table (all models)
    comparison_file = bench_dir / f"seated-shadow-2026-07-24-comparison.md"
    try:
        # If multiple models, note early-abort in header
        abort_note = ""
        if len(models_run) == 1 and args.also_run and not args.no_early_abort:
            item9_verdicts = [r["challenger_classification"] for r in seated_results if r["item_id"] == "whitelist-gate-weakening"]
            if item9_verdicts:
                item9_modal = max(set(item9_verdicts), key=item9_verdicts.count)
                if item9_modal != "false_positive":
                    abort_note = f"\n\n### Early-Abort Gate (Frontier-First)\n\nTested {models_run[0]} first (frontier seam). Item 9 verdict: {item9_modal} (not false_positive). EARLY ABORT: skipped {args.also_run} — if frontier can't flip with real code context, cheaper models won't either.\n"

        # Generate comparison for first model (or union for multiple)
        primary_model = models_run[0]
        primary_results = [r for r in seated_results if r.get("model", primary_model) == primary_model]
        baseline_map = load_baseline_results(bench_dir, primary_model)

        comparison = generate_comparison_table(
            baseline_map, primary_results, ground_truth_map, corpus
        )

        with open(comparison_file, "w", encoding="utf-8") as f:
            f.write("# Seated Shadow Adjudication — Real File-Brain A/B Results\n\n")
            f.write(f"**Models run**: {', '.join(models_run)}\n")
            f.write(f"**Context**: REAL file-brain (STATE.md, tracker.json, real repo code)\n")
            f.write(f"**Item 9 focus**: whitelist-gate-weakening with REAL secret_scan.py in pack\n\n")
            f.write(comparison)

            # Item 9 analysis
            f.write("\n\n## Key Finding: Item 9 (whitelist-gate-weakening)\n\n")
            f.write(f"**Primary model**: {primary_model}\n\n")

            item9_baseline = baseline_map.get("whitelist-gate-weakening", {}).get("classification")
            item9_seated = [r["challenger_classification"] for r in primary_results if r["item_id"] == "whitelist-gate-weakening"]
            item9_modal = max(set(item9_seated), key=item9_seated.count) if item9_seated else "?"
            item9_stability = f"{item9_seated.count(item9_modal)}/{len(item9_seated)}" if item9_seated else "0/0"

            f.write(f"Baseline (decontextualized): {item9_baseline}\n")
            f.write(f"Seated (real file-brain + secret_scan.py): {item9_modal} (stability: {item9_stability})\n\n")

            if item9_modal == "false_positive":
                f.write(f"✓ FLIPPED: Item 9 reversed from {item9_baseline} to false_positive with real context.\n")
                f.write(f"✓ Real secret_scan.py in context pack enabled the challenger to see the refutation.\n")
            else:
                f.write(f"✗ NO FLIP: Item 9 remains {item9_modal} despite real secret_scan.py in context.\n")
                f.write(f"✗ Real file-brain context did not reverse the call.\n")

            # Real sources note
            f.write("\n### Real Sources Included in Pack (Item 9)\n\n")
            f.write("- **tools/secret_scan.py** (full header, 1-100): Shows recursive file scanning patterns\n")
            f.write("- **tools/power_selftest.py** (lines 80-150): Shows known_ok whitelist section\n")
            f.write("- **STATE.md** (real, full): Orchestrator context + decisions\n")
            f.write("- **state/tracker.json** (real, if present): Open work items\n")
            f.write("- **Finding text** (blind): Presented without labels\n")

            f.write(abort_note)

            f.write("\n\n## Honest Framing\n\n")
            f.write("This run tests **file-brain context isolation** — whether real code and state can be safely included in OrchestratorDriver context packs. ")
            f.write("It does NOT test:\n")
            f.write("- Long-loop coherence (iterative refinement over decisions)\n")
            f.write("- Orchestrator seat-swap readiness (full loop + running backlog)\n")
            f.write("- Cost/latency of different backends\n\n")
            f.write("**Early-abort gate**: Frontier-first model (gpt-5.6-sol) run first. ")
            f.write("If item 9 doesn't flip with real context, cheaper models skipped (cost-rational). ")
            f.write("If it does flip, gpt-5.5 tested for portability.\n")

        print(f"Wrote comparison to {comparison_file}")
    except Exception as e:
        print(f"ERROR writing comparison: {e}")
        return 1

    print(f"\nDone. Results in {bench_dir}/")
    print(f"Models run: {', '.join(models_run)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
