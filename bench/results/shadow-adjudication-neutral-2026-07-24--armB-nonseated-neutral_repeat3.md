# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-24
**Challenger Model**: gpt-5.6-sol (OpenAI-compatible)
**Corpus Size**: 16 items
**Runs**: 3 (increment 2.6: verdict-neutral corpus)

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 50.0%
- **Real Defect Subset Agreement**: 66.7%
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

- >=80% agreement on gt=real_defect items: **FAIL** (66.7%)
- >=1 of items {9, 14} classified false_positive: **FAIL** (0/2)
- >=90% schema-valid without retry exhaustion: **PASS** (100.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | real_defect | real_defect | ✓ | 0.96 | ✓ |
| dryrun-blocked | real_defect | real_defect | ✓ | 0.94 | ✓ |
| uninstall-exit0 | undetermined | real_defect | ✗ | 0.82 | ✓ |
| quote-validation | undetermined | real_defect | ✗ | 0.62 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.93 | ✓ |
| unc-paths | undetermined | real_defect | ✗ | 0.58 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.96 | ✓ |
| audit-log-observability | undetermined | enhancement_opportunity | ✗ | 0.96 | ✓ |
| whitelist-gate-weakening | undetermined | false_positive | ✗ | 0.96 | ✓ |
| ps1-syntax-gate | real_defect | enhancement_opportunity | ✗ | 0.90 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.99 | ✓ |
| fixreview-parents1 | false_positive | false_positive | ✓ | 0.94 | ✓ |
| fixreview-backtick-test | undetermined | false_positive | ✗ | 0.98 | ✓ |
| regression-ui-suite | undetermined | false_positive | ✗ | 0.97 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.98 | ✓ |
| vbs-syntax-validity | false_positive | false_positive | ✓ | 0.98 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings