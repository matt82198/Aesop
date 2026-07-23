# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-23
**Challenger Model**: gpt-5.6-sol (OpenAI-compatible)
**Corpus Size**: 16 items

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 43.8%
- **Real Defect Subset Agreement**: 55.6%
- **False Positive Subset Agreement**: 40.0%
- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): 1/2
- **Schema Validity Rate**: 100.0%
- **DECISION_FAILED Count**: 0

## Success Bar Results

- >=80% agreement on gt=real_defect items: **FAIL** (55.6%)
- >=1 of items {9, 14} classified false_positive: **PASS** (1/2)
- >=90% schema-valid without retry exhaustion: **PASS** (100.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | undetermined | real_defect | ✗ | 0.98 | ✓ |
| dryrun-blocked | undetermined | real_defect | ✗ | 0.93 | ✓ |
| uninstall-exit0 | real_defect | real_defect | ✓ | 0.98 | ✓ |
| quote-validation | false_positive | real_defect | ✗ | 0.88 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.98 | ✓ |
| unc-paths | undetermined | real_defect | ✗ | 0.98 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.96 | ✓ |
| audit-log-observability | undetermined | enhancement_opportunity | ✗ | 0.92 | ✓ |
| whitelist-gate-weakening | real_defect | false_positive | ✗ | 0.86 | ✓ |
| ps1-syntax-gate | undetermined | enhancement_opportunity | ✗ | 0.99 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.98 | ✓ |
| fixreview-parents1 | undetermined | false_positive | ✗ | 0.98 | ✓ |
| fixreview-backtick-test | false_positive | false_positive | ✓ | 0.94 | ✓ |
| regression-ui-suite | false_positive | false_positive | ✓ | 0.83 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.90 | ✓ |
| vbs-syntax-validity | undetermined | false_positive | ✗ | 0.98 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings