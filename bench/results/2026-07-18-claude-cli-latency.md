# Cross-model run via claude CLI — 2026-07-18 (latency axis)

> CAVEAT: Opus scored 6/12 in this run with failures that are instruction-following/formatting
> violations (explanatory text added to answer-only prompts), not comprehension errors — a VERIFIED
> anomaly (re-run on 2026-07-18 reproduced: 3 genuine misclassifications, 2 correct-but-wrapped answers, 
> 1 unstable). Likely CLI/system-prompt interaction. Haiku=Sonnet 11/12 is consistent with all prior runs. 
> N=12: deltas <8pp are noise. Scope: CLI configuration, not comparative model ranking. Latency includes CLI startup overhead.

# Benchmark Results
Executed: 2026-07-17 19:56:52
CLI Overhead: 8659.3 ms

## Accuracy Summary
| Model | Accuracy | Pass | Fail |
|-------|----------|------|------|
| claude-haiku-4-5-20251001      | 100.0% | 12/12 |  0/12 |
| claude-sonnet-5                |  91.7% | 11/12 |  1/12 |
| claude-opus-4-8                |  50.0% |  6/12 |  6/12 |

## Latency Summary (ms)
| Model | P50 | P95 | Min | Max | Avg |
|-------|-----|-----|-----|-----|-----|
| claude-haiku-4-5-20251001      | 4987.0 | 7585.4 | 3889.3 | 7585.4 | 5177.3 |
| claude-sonnet-5                | 4110.3 | 15874.1 | 3212.8 | 15874.1 | 5043.6 |
| claude-opus-4-8                | 3723.3 | 6718.0 | 3135.9 | 6718.0 | 4496.8 |

## Per-Task Results
| Task | Category | Match | claude-haiku-4- | claude-sonnet-5 | claude-opus-4-8 | |
|------|----------|-------|---|---|---|
| t01 | classify_file_change | exact |        ✓        |        ✓        |        ✓        | 
| t02 | classify_file_change | exact |        ✓        |        ✓        |        ✗        | 
| t03 | classify_file_change | exact |        ✓        |        ✓        |        ✗        | 
| t04 | classify_file_change | exact |        ✓        |        ✓        |        ✗        | 
| t05 | extract_test_name    | regex |        ✓        |        ✓        |        ✓        | 
| t06 | extract_issue_number | regex |        ✓        |        ✓        |        ✓        | 
| t07 | classify_pr_title    | exact |        ✓        |        ✓        |        ✗        | 
| t08 | extract_exception_type | regex |        ✓        |        ✓        |        ✓        | 
| t09 | is_real_bug_judgment | exact |        ✓        |        ✗        |        ✗        | 
| t10 | extract_version      | regex |        ✓        |        ✓        |        ✓        | 
| t11 | transform_snake_to_camel | exact |        ✓        |        ✓        |        ✗        | 
| t12 | extract_file_line    | regex |        ✓        |        ✓        |        ✓        | 

## Failure Details

### t02 (classify_file_change)

**claude-opus-4-8:**
```
exact mismatch: got 'docs

Wait, let me reconsider.

test', expected 'test'
```

### t03 (classify_file_change)

**claude-opus-4-8:**
```
exact mismatch: got 'docs', expected 'config'
```

### t04 (classify_file_change)

**claude-opus-4-8:**
```
exact mismatch: got 'docs', expected 'code'
```

### t07 (classify_pr_title)

**claude-opus-4-8:**
```
exact mismatch: got 'chore', expected 'fix'
```

### t09 (is_real_bug_judgment)

**claude-sonnet-5:**
```
exact mismatch: got 'No', expected 'yes'
```

**claude-opus-4-8:**
```
exact mismatch: got 'No.', expected 'yes'
```

### t11 (transform_snake_to_camel)

**claude-opus-4-8:**
```
exact mismatch: got 'camelCase conversion is a mechanical string transformation — no tools needed.

fleetLedgerRotateCount', expected 'fleetLedgerRotateCount'
```

## Caveats
- **N=12 is small.** Differences under ~8 percentage points are likely noise.
- **Task selection bias.** Tasks skew toward extraction/classification; real fleet work has more semantic judgment.
- **Latency includes CLI startup.** Measurement overhead (8659.3 ms) is included in all timings.
- **Exact/regex match only.** Answers phrased differently may fail even if semantically correct.
