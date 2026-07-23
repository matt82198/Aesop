# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-23
**Challenger Model**: gpt-5.6-terra (OpenAI-compatible)
**Corpus Size**: 16 items

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 50.0%
- **Real Defect Subset Agreement**: 66.7%
- **False Positive Subset Agreement**: 40.0%
- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): 0/2
- **Schema Validity Rate**: 100.0%
- **DECISION_FAILED Count**: 0

## Success Bar Results

- >=80% agreement on gt=real_defect items: **FAIL** (66.7%)
- >=1 of items {9, 14} classified false_positive: **FAIL** (0/2)
- >=90% schema-valid without retry exhaustion: **PASS** (100.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | enhancement_opportunity | real_defect | ✗ | 0.86 | ✓ |
| dryrun-blocked | real_defect | real_defect | ✓ | 0.91 | ✓ |
| uninstall-exit0 | undetermined | real_defect | ✗ | 0.72 | ✓ |
| quote-validation | real_defect | real_defect | ✓ | 0.93 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.95 | ✓ |
| unc-paths | undetermined | real_defect | ✗ | 0.90 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.97 | ✓ |
| audit-log-observability | real_defect | enhancement_opportunity | ✗ | 0.82 | ✓ |
| whitelist-gate-weakening | undetermined | false_positive | ✗ | 0.72 | ✓ |
| ps1-syntax-gate | real_defect | enhancement_opportunity | ✗ | 0.84 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.98 | ✓ |
| fixreview-parents1 | false_positive | false_positive | ✓ | 0.93 | ✓ |
| fixreview-backtick-test | undetermined | false_positive | ✗ | 0.93 | ✓ |
| regression-ui-suite | undetermined | false_positive | ✗ | 0.90 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.98 | ✓ |
| vbs-syntax-validity | false_positive | false_positive | ✓ | 0.98 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings