# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-23
**Challenger Model**: gpt-5.6-sol (OpenAI-compatible)
**Corpus Size**: 16 items

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 62.5%
- **Real Defect Subset Agreement**: 88.9%
- **False Positive Subset Agreement**: 40.0%
- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): 0/2
- **Schema Validity Rate**: 100.0%
- **DECISION_FAILED Count**: 0

## Success Bar Results

- >=80% agreement on gt=real_defect items: **PASS** (88.9%)
- >=1 of items {9, 14} classified false_positive: **FAIL** (0/2)
- >=90% schema-valid without retry exhaustion: **PASS** (100.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | real_defect | real_defect | ✓ | 0.97 | ✓ |
| dryrun-blocked | real_defect | real_defect | ✓ | 0.93 | ✓ |
| uninstall-exit0 | real_defect | real_defect | ✓ | 0.93 | ✓ |
| quote-validation | real_defect | real_defect | ✓ | 0.91 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.98 | ✓ |
| unc-paths | undetermined | real_defect | ✗ | 0.90 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.97 | ✓ |
| audit-log-observability | undetermined | enhancement_opportunity | ✗ | 0.88 | ✓ |
| whitelist-gate-weakening | undetermined | false_positive | ✗ | 0.88 | ✓ |
| ps1-syntax-gate | real_defect | enhancement_opportunity | ✗ | 0.88 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.99 | ✓ |
| fixreview-parents1 | false_positive | false_positive | ✓ | 0.96 | ✓ |
| fixreview-backtick-test | undetermined | false_positive | ✗ | 0.97 | ✓ |
| regression-ui-suite | undetermined | false_positive | ✗ | 0.93 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.98 | ✓ |
| vbs-syntax-validity | false_positive | false_positive | ✓ | 0.99 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings