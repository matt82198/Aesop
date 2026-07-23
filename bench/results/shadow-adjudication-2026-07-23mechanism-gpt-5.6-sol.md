# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-23
**Challenger Model**: gpt-5.6-sol (OpenAI-compatible)
**Corpus Size**: 16 items

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 68.8%
- **Real Defect Subset Agreement**: 66.7%
- **False Positive Subset Agreement**: 60.0%
- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): 1/2
- **Schema Validity Rate**: 100.0%
- **DECISION_FAILED Count**: 0

## Success Bar Results

- >=80% agreement on gt=real_defect items: **FAIL** (66.7%)
- >=1 of items {9, 14} classified false_positive: **PASS** (1/2)
- >=90% schema-valid without retry exhaustion: **PASS** (100.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | undetermined | real_defect | ✗ | 0.97 | ✓ |
| dryrun-blocked | undetermined | real_defect | ✗ | 0.88 | ✓ |
| uninstall-exit0 | real_defect | real_defect | ✓ | 0.99 | ✓ |
| quote-validation | real_defect | real_defect | ✓ | 0.96 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.99 | ✓ |
| unc-paths | false_positive | real_defect | ✗ | 0.90 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.98 | ✓ |
| audit-log-observability | enhancement_opportunity | enhancement_opportunity | ✓ | 0.78 | ✓ |
| whitelist-gate-weakening | undetermined | false_positive | ✗ | 0.96 | ✓ |
| ps1-syntax-gate | enhancement_opportunity | enhancement_opportunity | ✓ | 0.87 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.99 | ✓ |
| fixreview-parents1 | false_positive | false_positive | ✓ | 0.97 | ✓ |
| fixreview-backtick-test | real_defect | false_positive | ✗ | 0.86 | ✓ |
| regression-ui-suite | false_positive | false_positive | ✓ | 0.92 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.99 | ✓ |
| vbs-syntax-validity | false_positive | false_positive | ✓ | 0.93 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings