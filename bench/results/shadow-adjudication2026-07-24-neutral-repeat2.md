# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-24
**Challenger Model**: gpt-4o-mini (OpenAI-compatible)
**Corpus Size**: 16 items
**Runs**: 2 (increment 2.6: verdict-neutral corpus)

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 0.0%
- **Real Defect Subset Agreement**: 0.0%
- **False Positive Subset Agreement**: 0.0%
- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): 0/2
- **Schema Validity Rate**: 0.0%
- **DECISION_FAILED Count**: 16

## Narrative-Refusal Stability (Items 9, 13)

**Item 9 (whitelist-gate-weakening, gt=false_positive)**:

| Verdict | Runs | Stability |
|---|---|---|
| DECISION_FAILED | 2/2 | 100% |

**Modal verdict**: DECISION_FAILED (2/2 runs)

**Item 13 (fixreview-backtick-test, gt=false_positive)**:

| Verdict | Runs | Stability |
|---|---|---|
| DECISION_FAILED | 2/2 | 100% |

**Modal verdict**: DECISION_FAILED (2/2 runs)

## Success Bar Results

- >=80% agreement on gt=real_defect items: **FAIL** (0.0%)
- >=1 of items {9, 14} classified false_positive: **FAIL** (0/2)
- >=90% schema-valid without retry exhaustion: **FAIL** (0.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| dryrun-blocked | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| uninstall-exit0 | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| quote-validation | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| apostrophe-path | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| unc-paths | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| hardcoded-username | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| audit-log-observability | DECISION_FAILED | enhancement_opportunity | ✗ | 0.00 | ✗ |
| whitelist-gate-weakening | DECISION_FAILED | false_positive | ✗ | 0.00 | ✗ |
| ps1-syntax-gate | DECISION_FAILED | enhancement_opportunity | ✗ | 0.00 | ✗ |
| test-hardcoded-path | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| fixreview-parents1 | DECISION_FAILED | false_positive | ✗ | 0.00 | ✗ |
| fixreview-backtick-test | DECISION_FAILED | false_positive | ✗ | 0.00 | ✗ |
| regression-ui-suite | DECISION_FAILED | false_positive | ✗ | 0.00 | ✗ |
| cimergewait-exit0 | DECISION_FAILED | real_defect | ✗ | 0.00 | ✗ |
| vbs-syntax-validity | DECISION_FAILED | false_positive | ✗ | 0.00 | ✗ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings