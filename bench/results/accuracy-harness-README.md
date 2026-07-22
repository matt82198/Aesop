# Accuracy Harness: Tool-Use Structured Output Measurement

**Status**: Wave 27, Lane D (WS2c) — Harness + offline tests + documentation (SHIPPED)

## Purpose

The codex driver's `tool_use_accuracy=0.92` attribute is asserted, never measured. This harness provides measurement infrastructure to validate that claim with real data. It measures how reliably a backend produces valid, schema-compliant JSON responses for file-replacement tasks — the core of "tool-use accuracy."

## What Gets Measured

Three independent metrics, each binary (pass/fail):

1. **valid_json_first_try** — Can the backend produce valid JSON on the first attempt without retry?
2. **schema_exact** — Does the JSON match the strict WORKER_PATCH_SCHEMA (full-file replacements)?
3. **ownership_respect** — Do all returned file paths belong to the owned_files set (no escapes)?

**Composite accuracy** = mean(valid_json, schema_exact, ownership_respect) in [0.0, 1.0]

Per-task scores are reported; overall accuracy is the mean across all N tasks.

## Test Dataset: 32 Structured Tasks

The harness includes 32 representative file-modification prompts covering:

| Category | Count | Represents |
|---|---|---|
| Single-file edits | 4 | append, replace, create, multiline operations |
| Multi-file edits | 3 | coordination across 2–4 files |
| Path handling | 3 | nested paths, special characters, unusual cases |
| Schema edge cases | 5 | empty fields, missing fields, extra fields, false flags |
| Malformed responses | 4 | truncated JSON, invalid escapes, missing required fields |
| Ownership violations | 3 | relative escapes (../), absolute paths, unowned files |
| Real-world patterns | 7 | version bumps, dependency updates, config, fixtures, migrations |
| Stress tests | 2 | many small files, complex nested JSON, shell scripts, SQL |

Each task has:
- **id**: unique stable identifier (t01–t32)
- **category**: descriptive task type
- **prompt**: the request sent to the backend
- **owned_files**: tuple of paths the backend is allowed to modify
- **expected_valid_json**: whether we expect this response to parse as JSON
- **expected_schema_match**: whether we expect it to match WORKER_PATCH_SCHEMA
- **expected_ownership_respect**: whether we expect all paths to be in owned_files

Tasks marked as "expected to fail" (e.g., truncated JSON, ownership violations) allow the harness to prove it correctly detects errors.

## Measurement Modes

### Offline Mode (Default, Zero Cost, No Network)

```bash
python bench/accuracy_harness.py --mode offline
```

Uses `FakeTransport` — a scripted transport callable that returns canned responses simulating various backend behaviors:
- **Good responses**: Valid JSON matching schema with correct owned files
- **Malformed responses**: Truncated, invalid escape, missing fields, extra fields
- **Ownership violations**: Paths with ../, absolute paths, unowned files

**Output**: `bench/results/accuracy-harness-results.json`

```
Overall Accuracy: 86.46%
────────────────────────────────────────────────────
id            category                    composite
────────────────────────────────────────────────────
t01           single_file_append          1.00 ✓
t14           malformed_truncated         0.00 ✗
t18           ownership_escape_relative   0.67
...
────────────────────────────────────────────────────
```

- **Offline tests in CI**: Fully passing, no API key, no network. Proves the scoring pipeline works.
- **Use case**: Quick local validation, continuous integration, rapid iteration.
- **Cost**: Zero. FakeTransport is pure Python.

### Live Mode (Against Real Backend)

```bash
export OPENAI_API_KEY=sk-...
python bench/accuracy_harness.py --mode live --model gpt-3.5-turbo
```

Runs all 32 tasks against the live OpenAI Chat Completions API (or any compatible backend):

1. Each task is sent via `default_openai_transport` (real HTTP POST)
2. Responses are scored by the same pipeline as offline mode
3. Results include token usage and latency per task
4. Output: `bench/results/accuracy-harness-results.json` with real data

**Output format (extended with live metrics)**:

```json
{
  "mode": "live",
  "model": "gpt-3.5-turbo",
  "timestamp": "2026-07-22T15:30:45Z",
  "overall_accuracy": 0.91,
  "task_count": 32,
  "tasks": [
    {
      "task_id": "t01",
      "category": "single_file_append",
      "valid_json_first_try": true,
      "schema_exact": true,
      "ownership_respect": true,
      "composite_accuracy": 1.0,
      "error": null,
      "raw_response": "(first 500 chars of response)"
    },
    ...
  ]
}
```

- **Use case**: Production-grade measurement. Determines whether the backend meets the accuracy requirement for automated dispatch.
- **Cost**: ~$5–10 depending on token usage and model.
- **Duration**: 30–60 seconds (one task per second to avoid rate limits).

## Running the Live Harness (User-Triggered)

### Prerequisites

1. **OpenAI API key**: Set `OPENAI_API_KEY` environment variable
   ```bash
   export OPENAI_API_KEY=sk-proj-...
   ```

2. **Python environment**: Same as development (pytest, requests, json)

3. **No special setup**: The transport uses stdlib `urllib.request`, no external dependencies beyond what's already in the codebase.

### Command

```bash
# Against gpt-3.5-turbo (default cheap model, ~0.92 claimed accuracy)
python bench/accuracy_harness.py --mode live

# Against gpt-4-turbo (stronger model for comparison)
python bench/accuracy_harness.py --mode live --model gpt-4-turbo

# Against a different OpenAI-compatible endpoint
python bench/accuracy_harness.py --mode live --model mistral-large
```

### Interpreting Results

**Overall accuracy >= 0.90**: The model is suitable for Tier-2 dispatch (with verification).
- Tier-2 means: validate all JSON, require adversarial review, allow bounded repair (2 attempts).
- The 0.92 claim for gpt-3.5-turbo should be validated here before production use.

**Overall accuracy < 0.90**: The model should be downgraded to Tier-3 or higher verification.
- Tier-3: more aggressive spot-checking, longer repair cap, stricter validation.
- Consider fallback to gpt-4-turbo or adding more verification passes.

### Monitoring and Baseline

After the first live run, save the results as a baseline:

```bash
cp bench/results/accuracy-harness-results.json bench/results/baseline-gpt-3.5-turbo.json
```

On subsequent runs (weekly/monthly), compare against the baseline to catch model drift:

```bash
python bench/accuracy_harness.py --mode live --model gpt-3.5-turbo
# Then manually compare accuracy to baseline-gpt-3.5-turbo.json
```

## Offline Test Suite (CI-Proven)

The offline harness is fully tested in `tests/test_accuracy_harness.py` (23 tests):

**Scoring logic tests**:
- Valid JSON + schema + ownership → 100% composite ✓
- Truncated JSON → 0% composite, error reported ✓
- Invalid escapes → detected and scored correctly ✓
- Missing required fields → schema_exact=false ✓
- Extra fields (additionalProperties=false) → schema_exact=false ✓
- Ownership violations (../, absolute, unowned) → ownership_respect=false ✓

**FakeTransport tests**:
- Good responses → valid schema-compliant JSON ✓
- Truncated → unparseable ✓
- Escape sequences → invalid ✓
- Ownership violations → detected per path ✓

**Task generation & benchmark**:
- 32 tasks generated, all unique IDs ✓
- Malformed/violation tasks correctly marked ✓
- Offline benchmark completes with consistent scores ✓

Run offline tests locally:

```bash
python -m pytest tests/test_accuracy_harness.py -v
```

Or in CI:

```bash
pytest tests/test_accuracy_harness.py --tb=short
```

## Design Notes

### Why Not Use the Existing Bench?

The existing `bench/` benchmark (12 curated tasks, mock runner) measures general knowledge/capability. This accuracy harness is orthogonal:
- Focuses on **tool-use accuracy**: Can the model produce valid structured JSON?
- **Codex-specific**: Geared toward OpenAI Chat Completions, not general capability.
- **Measurement-ready**: Offline tests prove the scoring works; live mode is user-triggered for real data.

### Why Three Metrics?

1. **valid_json_first_try**: Models often produce non-JSON text when confused. Measuring this separately catches "I apologize, I can't do that" responses.
2. **schema_exact**: Even valid JSON may violate the contract (missing fields, extra fields). The orchestrator needs strict schema compliance.
3. **ownership_respect**: A well-formed response that touches files outside the owned set is a critical security/isolation failure.

Taking the mean treats all three equally. Alternatives (weighted average, geometric mean) could be explored later.

### FakeTransport Pattern

The injectable transport seam is borrowed from CodexDriver itself. It enables:
- **Offline testing**: No API key, no network, reproducible responses.
- **Deterministic validation**: Same tasks → same responses every run.
- **CI integration**: No rate limiting, no cost, no flakiness.

FakeTransport is NOT a model replacement; it's a response simulator that proves the scoring pipeline works. Real model quality requires live measurement.

### Ownership Enforcement

The ownership_respect metric guards against path traversal:
- `../secret.py` ← Detected (relative escape)
- `/etc/passwd` ← Detected (absolute path)
- `unowned.py` (not in owned_files) ← Detected

This is redundant with CodexDriver's own ownership checks, but measuring it separately makes scoring transparent: "the model tried to escape, and the orchestrator caught it."

## Next Steps

### Phase 1 (This Wave)

- [x] Harness design (scoring logic, task dataset, offline tests)
- [x] FakeTransport with good/bad response patterns
- [x] 32 representative file-replacement tasks
- [x] Offline validation (100% CI-passing tests)
- [x] User-facing documentation (this file)

### Phase 2 (Wave 28+)

- [ ] **Run live benchmark** (user-triggered):
  ```bash
  export OPENAI_API_KEY=sk-...
  python bench/accuracy_harness.py --mode live
  ```
  Produces real accuracy for gpt-3.5-turbo and gpt-4-turbo.

- [ ] **Evaluate tier assignment**: If measured accuracy < 0.90, adjust verification tier in `verification_policy.py`.

- [ ] **Baseline monitoring**: Save live run results; periodically re-run to catch model drift.

- [ ] **Extend task dataset**: Sample from real aesop transcripts (using `bench/sample_transcripts.py`) to grow beyond curated tasks.

### Phase 3 (Wave 32+)

- [ ] **Compare models**: Run harness against Claude Sonnet, Opus; compare accuracy/token cost/latency.
- [ ] **A/B testing**: Use harness results to inform backend selection for production dispatch.
- [ ] **Automated tier assignment**: Wire harness results into verification_policy.py so tier scales with measured accuracy.

## Technical Internals

### Scoring Algorithm

```python
def score_response(task, response_text):
    # 1. valid_json_first_try
    try:
        parsed = json.loads(response_text)
        valid_json = True
    except:
        valid_json = False
    
    # 2. schema_exact (only if JSON valid)
    if valid_json:
        try:
            _validate_patch_schema(parsed)
            schema_exact = True
        except:
            schema_exact = False
    else:
        schema_exact = False
    
    # 3. ownership_respect (only if JSON + schema valid)
    if valid_json and schema_exact:
        ownership_respect = all(
            file_entry["path"] in task.owned_files
            for file_entry in parsed.get("files", [])
        )
    else:
        ownership_respect = False
    
    # Composite
    composite = mean([valid_json, schema_exact, ownership_respect])
    return TaskScore(..., composite_accuracy=composite)
```

### Task Format

Each task is an `AccuracyTask` dataclass:

```python
@dataclass
class AccuracyTask:
    id: str                           # t01, t02, ...
    category: str                     # single_file_append, malformed_truncated, ...
    prompt: str                       # "Append 'done' to main.py"
    owned_files: Tuple[str, ...]      # ("main.py",)
    expected_valid_json: bool = True  # Should this task produce valid JSON?
    expected_schema_match: bool = True
    expected_ownership_respect: bool = True
```

### Response Contract (WORKER_PATCH_SCHEMA)

All responses must match:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "files": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "path": {"type": "string"},
          "contents": {"type": "string"}
        },
        "required": ["path", "contents"]
      }
    },
    "summary": {"type": "string"},
    "done": {"type": "boolean"}
  },
  "required": ["files", "summary", "done"]
}
```

Violations:
- Missing `files`, `summary`, or `done` → schema_exact=false
- Extra fields (e.g., `metadata`) → schema_exact=false (additionalProperties=false)
- `files[i]` without `path` or `contents` → schema_exact=false
- `done` is not boolean → schema_exact=false

## File Manifest

```
bench/
├── accuracy_harness.py              [NEW] Main harness + 32 tasks + FakeTransport + offline/live modes
├── results/
│   └── accuracy-harness-README.md   [NEW] This file
│   └── accuracy-harness-results.json [GENERATED] Results from offline runs
└── README.md                         [EXISTING] General bench overview

tests/
└── test_accuracy_harness.py         [NEW] 23 unit tests, all CI-passing

driver/
├── codex_driver.py                  [UNCHANGED] References WORKER_PATCH_SCHEMA, _validate_patch_schema
├── openai_transport.py              [UNCHANGED] default_openai_transport
└── agent_driver.py                  [UNCHANGED] WorkerRequest, WorkerResult, DriverCapabilities
```

## Assumptions & Limitations

- **No retry loop in harness**: The harness scores first attempts. Real CodexDriver retries malformed JSON up to 2 times; this harness does not simulate retry.
- **FakeTransport is scripted, not random**: Responses are deterministic (same task ID → same response). Real model variation is captured only in live mode.
- **Ownership check is simplified**: The harness checks set membership. Real CodexDriver enforces path normalization, drive-relative paths on Windows, etc. The harness assumes paths are already normalized (matching task.owned_files).
- **No latency modeling**: FakeTransport responds instantly. Live mode captures real network latency.
- **Token cost is rough**: FakeTransport returns fixed token counts (50–60 tokens). Real costs vary per model and response length.
- **No adversarial prompts**: The 32 tasks are representative but not adversarially chosen. Production drift may exceed these results.

## References

- **CodexDriver**: `driver/codex_driver.py` — the Tier-2 OpenAI backend
- **WORKER_PATCH_SCHEMA**: `driver/codex_driver.py` line 77–97 — the strict JSON contract
- **Verification tiers**: `driver/verification_policy.py` — how accuracy feeds orchestrator tuning
- **AgentDriver contract**: `driver/agent_driver.py` — the backend abstraction
- **Existing benchmark**: `bench/README.md` — 12-task general capability benchmark (complementary, not this harness)

## Contact & Questions

This harness is part of aesop's Wave-27 delivery (WS2c, Lane D). Questions or findings:
- Review the PR + CI run
- File a tracker item for follow-up
- Reach out to the fleet-ops team

---

**Generated**: Wave 27, Lane D (WS2c)  
**Status**: Offline tests GREEN, live mode user-triggered  
**Next action**: Run live benchmark to measure gpt-3.5-turbo accuracy
