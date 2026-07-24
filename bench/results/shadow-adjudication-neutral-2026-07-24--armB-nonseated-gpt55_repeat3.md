# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-24
**Challenger Model**: gpt-5.5 (OpenAI-compatible)
**Corpus Size**: 16 items
**Runs**: 3 (increment 2.6: verdict-neutral corpus)

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 68.8%
- **Real Defect Subset Agreement**: 88.9%
- **False Positive Subset Agreement**: 40.0%
- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): 0/2
- **Schema Validity Rate**: 100.0%
- **DECISION_FAILED Count**: 0

## Narrative-Refusal Stability (Items 9, 13)

**Item 9 (whitelist-gate-weakening, gt=false_positive)**:

| Verdict | Runs | Stability |
|---|---|---|
| undetermined | 3/3 | 100% |

**Modal verdict**: undetermined (3/3 runs)

**Item 13 (fixreview-backtick-test, gt=false_positive)**:

| Verdict | Runs | Stability |
|---|---|---|
| undetermined | 3/3 | 100% |

**Modal verdict**: undetermined (3/3 runs)

## Success Bar Results

- >=80% agreement on gt=real_defect items: **PASS** (88.9%)
- >=1 of items {9, 14} classified false_positive: **FAIL** (0/2)
- >=90% schema-valid without retry exhaustion: **PASS** (100.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | real_defect | real_defect | ✓ | 0.82 | ✓ |
| dryrun-blocked | real_defect | real_defect | ✓ | 0.84 | ✓ |
| uninstall-exit0 | real_defect | real_defect | ✓ | 0.78 | ✓ |
| quote-validation | real_defect | real_defect | ✓ | 0.78 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.82 | ✓ |
| unc-paths | undetermined | real_defect | ✗ | 0.78 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.82 | ✓ |
| audit-log-observability | enhancement_opportunity | enhancement_opportunity | ✓ | 0.74 | ✓ |
| whitelist-gate-weakening | undetermined | false_positive | ✗ | 0.82 | ✓ |
| ps1-syntax-gate | real_defect | enhancement_opportunity | ✗ | 0.78 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.95 | ✓ |
| fixreview-parents1 | false_positive | false_positive | ✓ | 0.72 | ✓ |
| fixreview-backtick-test | undetermined | false_positive | ✗ | 0.78 | ✓ |
| regression-ui-suite | undetermined | false_positive | ✗ | 0.72 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.86 | ✓ |
| vbs-syntax-validity | false_positive | false_positive | ✓ | 0.84 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings