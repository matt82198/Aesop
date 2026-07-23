# Orchestrator S2 Decision Catalog

The orchestrator's "seat 2" (S2) responsibility is to perform recurring judgment calls that keep a wave running safely and coherently. This directory documents the six core decision types with their input/output contracts as JSON Schema draft-07 files.

## Core Decision Types

### 1. `rank_backlog`

**Purpose**: Intake audit findings, feature ideation, fleet-ops recommendations, and existing backlog items; produce a prioritized, scoped backlog for the current wave.

**Trigger Point**: Phase 0 (wave setup). Runs once per wave after audit lenses complete.

**Input**: 
- Audit findings from multiple lenses (security, correctness, test-integrity, architecture, UI/UX, ideation, docs, fleet-ops)
- Existing backlog items (tracker.json)
- Fleet-ops monitor recommendations
- Wave constraints (cost ceiling, max items)

**Output**:
- Ranked list of items selected for this wave (locked scope)
- Deferred items and reasons
- Per-item priority, estimated cost, dependencies

**Schema**: [`rank_backlog.schema.json`](rank_backlog.schema.json)

**Example I/O** (SANITIZED):

*Input*:
```json
{
  "audit_findings": [
    {
      "lens": "correctness",
      "category": "defect",
      "description": "Worker dispatch fails when owned files include symlinks",
      "impact": "high"
    },
    {
      "lens": "ideation",
      "category": "enhancement",
      "description": "Add cost-attribution per audit lens (user insight: know what each scanner costs)",
      "impact": "medium"
    }
  ],
  "backlog_items": [
    {
      "id": "feat/x",
      "description": "Implement multi-model backend routing",
      "priority": "p1"
    }
  ],
  "wave_constraints": {
    "cost_ceiling_dollars": 50,
    "max_items": 8
  }
}
```

*Output*:
```json
{
  "verdict": {
    "scope_locked": true,
    "wave_items": [
      {
        "rank": 1,
        "item_id": "fix/symlink-dispatch",
        "priority": "p0",
        "reason": "Correctness defect blocking worker dispatch",
        "estimated_cost": 8.50,
        "dependencies": []
      },
      {
        "rank": 2,
        "item_id": "feat/x",
        "priority": "p1",
        "reason": "High-value feature enabling multi-model routing",
        "estimated_cost": 12.00,
        "dependencies": []
      },
      {
        "rank": 3,
        "item_id": "feat/cost-attribution",
        "priority": "p2",
        "reason": "Deferred: enhancement, lower urgency",
        "estimated_cost": 0
      }
    ]
  },
  "confidence": 0.92,
  "evidence": [
    {
      "file": "conductor3/AUDIT-PRIMER.md",
      "lines": "120-135",
      "description": "Correctness lens flagged symlink defect as P0"
    }
  ]
}
```

---

### 2. `adjudicate_finding`

**Purpose**: Given an audit finding (potential defect, false positive, or enhancement), render a verdict: is it real? actionable? what priority? Should it go in the backlog?

**Trigger Point**: Phase 0 (audit review). Runs per-finding when audit briefs arrive.

**Input**:
- Finding text, category, claimed severity
- Reproduction steps (if defect)
- Source audit lens and file/line
- Related findings (duplicates/blocked-by)
- Prior verdicts on similar findings (for consistency)

**Output**:
- Classification (real_defect, false_positive, minor_quality, etc.)
- Actionable? (yes/no)
- Recommended priority if actionable
- Severity adjustment (if different from claimed)
- Suggested fix approach

**Schema**: [`adjudicate_finding.schema.json`](adjudicate_finding.schema.json)

**Example I/O** (SANITIZED):

*Input*:
```json
{
  "finding": {
    "id": "sec-2026-07-23-001",
    "description": "Secret token 'DEMO_KEY_abc' appears in test fixture, not marked as runtime-concat",
    "category": "security",
    "severity_claimed": "p1",
    "reproduction_steps": "Run: grep -r 'DEMO_KEY' tests/ — visible in test_xyz.py line 42"
  },
  "finding_source": {
    "lens": "security",
    "file": "tests/test_xyz.py",
    "line": 42
  },
  "prior_verdicts": [
    {
      "wave": 25,
      "verdict": "real",
      "reasoning": "Dummy secret without concat marker blocks push gate"
    }
  ]
}
```

*Output*:
```json
{
  "verdict": {
    "classification": "real_defect",
    "actionable": true,
    "recommended_priority": "p1",
    "severity_adjusted": "p1",
    "suggested_fix_approach": "Mark the dummy secret with runtime-concat (concat at runtime to defeat push-gate scanning)"
  },
  "confidence": 0.98,
  "evidence": [
    {
      "type": "code_location",
      "file": "tests/test_xyz.py",
      "lines": "40-45",
      "excerpt": "DEMO_KEY = 'abc' # should be concat-assembled",
      "description": "Literal secret string blocks push gate; prior wave had same pattern"
    }
  ]
}
```

---

### 3. `review_diff`

**Purpose**: Given a code diff from a worker agent, determine: does it correctly implement the requested change? Are there defects, oversights, or style issues? Should it be merged or sent for revision?

**Trigger Point**: Phase 1 (build) and Phase 2 (repair). After each worker completes, before merge.

**Input**:
- Unified diff (files changed, additions/deletions, patch)
- Original dispatch prompt (intent)
- Domain contract/spec the change should fulfill
- Test results (pass/fail, exit code)
- Worker model and owned files

**Output**:
- Approval status (approved, approved_with_minor_nits, request_changes, undetermined)
- Implements intent? (yes/no)
- Issues found (defects, style, test gaps, ownership violations)
- Out-of-scope detections
- Requires revision? (yes/no)

**Schema**: [`review_diff.schema.json`](review_diff.schema.json)

**Example I/O** (SANITIZED):

*Input*:
```json
{
  "diff": {
    "branch": "feat/decision-catalog",
    "commit_sha": "a1b2c3d",
    "files_changed": [
      {
        "path": "driver/decisions/rank_backlog.schema.json",
        "status": "added",
        "additions": 150,
        "deletions": 0
      }
    ],
    "tests_passing": true,
    "test_exit_code": 0
  },
  "original_intent": {
    "prompt_excerpt": "Create JSON Schema for rank_backlog decision type",
    "contract_hint": "input must have audit_findings and backlog_items; output must require evidence field"
  }
}
```

*Output*:
```json
{
  "verdict": {
    "approval_status": "approved",
    "implements_intent": true,
    "issues_found": [],
    "test_coverage_adequate": true,
    "requires_revision": false
  },
  "confidence": 0.95,
  "evidence": [
    {
      "type": "test_output",
      "description": "Schema validation passes; example I/O pairs parse correctly against schema"
    }
  ]
}
```

---

### 4. `synthesize_briefs`

**Purpose**: Consume multiple audit briefs (from independent lenses) and produce a consolidated context pack: unified findings list, relationships, priority ordering, and clarifications for the PM/orchestrator.

**Trigger Point**: Phase 0 (wave setup). After all audit lenses complete, before PM planning.

**Input**:
- Multiple audit briefs (security, correctness, UX, ideation, docs, etc.)
- Each brief contains findings with IDs, categories, severity
- Prior synthesis (if re-synthesizing)
- Known duplicates list

**Output**:
- Consolidated findings (deduplicated, organized by priority)
- Duplicate map (old ID → consolidated ID)
- Intra-finding relationships (blocks, caused_by, suggests, contradicts)
- Summary by theme (high-level patterns)
- Changes from prior synthesis (if re-synthesized)

**Schema**: [`synthesize_briefs.schema.json`](synthesize_briefs.schema.json)

**Example I/O** (SANITIZED):

*Input*:
```json
{
  "briefs": [
    {
      "lens": "correctness",
      "findings": [
        {
          "id": "corr-001",
          "description": "Verification policy struct missing cost-per-tier data",
          "severity": "medium"
        }
      ]
    },
    {
      "lens": "docs",
      "findings": [
        {
          "id": "docs-042",
          "description": "README lacks example of orchestrator decision flow",
          "severity": "low"
        }
      ]
    }
  ]
}
```

*Output*:
```json
{
  "verdict": {
    "consolidated_findings": [
      {
        "id": "consolidated-001",
        "description": "Verification policy struct missing cost-per-tier data",
        "source_lenses": ["correctness"],
        "category": "defect",
        "priority": "p2",
        "suggested_backlog_item": true
      }
    ],
    "duplicate_map": {},
    "summary_by_theme": {
      "key_themes": [
        {
          "theme": "Policy/verification gaps",
          "finding_count": 1,
          "findings": ["consolidated-001"]
        }
      ]
    }
  },
  "confidence": 0.88,
  "evidence": [
    {
      "source_brief": "correctness",
      "finding_id": "corr-001",
      "description": "Verification policy struct missing cost-per-tier data"
    }
  ]
}
```

---

### 5. `decide_repair`

**Purpose**: A wave item failed its test. Analyze the failure and test output, then decide: is it worth a repair attempt? What strategy? Should we escalate or defer?

**Trigger Point**: Phase 1 (build) and Phase 2 (repair). When an item's test fails.

**Input**:
- Failed item (slug, branch, model, owned files)
- Test output (test command, exit code, stdout/stderr)
- Failure pattern detected (assertion_error, timeout, import_error, etc.)
- Repair context (which round, repair cap, prior attempts)
- Verification policy (repair_cap, spot_check_frac)

**Output**:
- Should attempt repair? (yes/no)
- Repair strategy (root_cause_analysis, incremental_fix, escalate_to_human, skip_item, etc.)
- Root cause hypothesis
- Is failure transient? (flaky test vs. genuine defect)
- Escalation reason (if not repairing)
- Suggested prompt addendum for repair agent

**Schema**: [`decide_repair.schema.json`](decide_repair.schema.json)

**Example I/O** (SANITIZED):

*Input*:
```json
{
  "failed_item": {
    "slug": "feat/xy-backend",
    "branch": "feat/xy-backend",
    "model_used": "claude-haiku-4",
    "owned_files": ["driver/backend_xy.py", "tests/test_backend_xy.py"]
  },
  "test_output": {
    "test_command": "python -m pytest tests/test_backend_xy.py -v",
    "exit_code": 1,
    "failure_pattern": "assertion_error",
    "stdout": "FAILED test_backend_xy.py::test_response_format - AssertionError: expected key 'status' in response"
  },
  "repair_context": {
    "round": 1,
    "repair_cap": 2,
    "prior_rounds": []
  }
}
```

*Output*:
```json
{
  "verdict": {
    "should_attempt_repair": true,
    "repair_strategy": "root_cause_analysis",
    "root_cause_hypothesis": "Response format missing 'status' key; likely worker misread contract",
    "failure_is_transient": false,
    "suggested_repair_prompt_addendum": "Test failed: expected response['status'], but response = {...}. The backend_xy contract requires all responses to include a 'status' field. Review the contract and fix."
  },
  "confidence": 0.87,
  "evidence": [
    {
      "type": "test_output",
      "excerpt": "expected key 'status' in response",
      "description": "Clear assertion error; testable with a quick fix"
    }
  ]
}
```

---

### 6. `final_catch`

**Purpose**: Pre-merge safeguard. Before shipping (merging to main), perform a last sanity check: does the item pass all gates? Are there any last-minute red flags? Should it be held or escalated?

**Trigger Point**: Phase 3 (wave close). Before merging to main, after all repairs complete.

**Input**:
- Item ready to merge (slug, branch, PR number, commit SHA, files changed)
- Verification results (test passed? secret-scan passed? CI green? branch protection?)
- Adversarial review results (if performed)
- Branch protection check (required checks passing, reviews, strict-up-to-date)
- Gate history (prior attempts)

**Output**:
- Safe to merge? (yes/no)
- Gates passed/failed
- Blocker defects (if any)
- Hold reason (if not safe)
- Escalation needed? (yes/no)
- Escalation reason (if yes)

**Schema**: [`final_catch.schema.json`](final_catch.schema.json)

**Example I/O** (SANITIZED):

*Input*:
```json
{
  "item": {
    "slug": "fix/worker-dispatch-symlink",
    "branch": "fix/worker-dispatch-symlink",
    "pr_number": 999,
    "commit_sha": "f1e2d3c",
    "files_changed": 3,
    "additions": 120,
    "deletions": 45
  },
  "verification_results": {
    "test_passed": true,
    "test_exit_code": 0,
    "secret_scan_passed": true,
    "ci_status": "success",
    "branch_protection_check": {
      "required_checks_passing": true,
      "strict_up_to_date": true
    },
    "adversarial_review": {
      "completed": true,
      "defects_found": 0
    }
  }
}
```

*Output*:
```json
{
  "verdict": {
    "safe_to_merge": true,
    "gates_passed": ["test_pass", "secret_scan", "ci_green", "branch_protection", "adversarial_review_clean"],
    "gates_failed": [],
    "blocker_defects": [],
    "escalation_needed": false
  },
  "confidence": 1.0,
  "evidence": [
    {
      "gate": "test_output",
      "status": "passed",
      "description": "All tests pass; no timeouts or flakes"
    }
  ]
}
```

---

## Schema Structure (Common to All)

Each schema file enforces a contract:

### Required Fields (all decision types)
- **`decision_type`** (const): e.g., "rank_backlog"
- **`input`** (object): context fields from control files
- **`verdict`** (object): the decision/judgment output
- **`confidence`** (number 0.0-1.0): how sure is this decision?
- **`evidence`** (array, REQUIRED): citations to source files/findings supporting this decision

### Input Fields (varies by type)
Each decision type documents which control files or findings it consumes (e.g., `rank_backlog` reads STATE.md, AUDIT-PRIMER.md, tracker.json; `adjudicate_finding` reads a finding text + source).

### Output/Verdict Fields (varies by type)
Each decision renders a different output structure. For instance:
- `rank_backlog`: ranked item list + deferred items
- `adjudicate_finding`: classification + priority + actionable?
- `review_diff`: approval status + issues found
- `synthesize_briefs`: consolidated findings + duplicate map
- `decide_repair`: repair strategy + root cause hypothesis
- `final_catch`: safe_to_merge + blocker defects

### Evidence Requirement
**All verdicts MUST include an `evidence` array with at least one citation.** Each citation should reference:
- **File**: control file path (e.g., STATE.md, AUDIT-PRIMER.md, findings.json) or source file
- **Lines**: line range or number if applicable
- **Excerpt**: quoted text supporting the verdict
- **Description**: how this evidence informs the decision

Verdicts without evidence citations do not count in the system; this enforces traceability and prevents hallucination.

---

## Sanitization Notes

Example I/O pairs in this README have been sanitized:
- No verbatim user prose or session transcripts
- No tokens, API keys, or credential-like strings
- No machine-identifying values beyond repo-relative paths
- Paraphrased examples distilled from real BUILDLOG entries and documented orchestrator behavior
- Runtime-concatenated dummy-secret-looking strings (to defeat the push gate and serve as examples)

---

## Tooling & Tests

See [`tests/test_decision_schemas.py`](../../tests/test_decision_schemas.py) for:
- Schema validation (all `.schema.json` files parse as valid JSON Schema draft-07)
- Presence check (README documents exactly the schema files present, drift gate)
- Example validation (if examples in this README are machine-readable fenced JSON, they validate against their schemas)

Run tests with:
```bash
cd /c/Users/matt8/aesop-wt-inc0
python -m unittest tests.test_decision_schemas -v
```

---

## Next Steps

**Increment 1** (OrchestratorDriver seam): Mirror AgentDriver to create OrchestratorDriver, with a `decide(decision_type, context_pack, schema)` method. Implement backends for Claude, OpenAI-compatible, and Codex.

**Increment 2** (Shadow mode): Run all S2 decisions on both Claude and a challenger backend, zero behavior change, measure agreement rate.

**Increment 3** (Live swap): Swap one decision class (e.g., `adjudicate_finding`) to the challenger, while Claude spot-checks a sample.

**Increment 4** (Full headless): Run an entire wave with all S2 decisions on a challenger backend.

**Increment 5** (Micro-kernel formalization): Formalize the complete S2 decision interface, syscall table, and capability probing in docs/MICROKERNEL.md.

---

## References

- **Plan**: [`conductor3/plans/orchestrator-swap-microkernel.md`](../../../conductor3/plans/orchestrator-swap-microkernel.md)
- **Driver architecture**: [`driver/README.md`](../README.md)
- **Wave loop**: [`driver/wave_loop.py`](../wave_loop.py)
- **Verification policy**: [`driver/verification_policy.py`](../verification_policy.py)
