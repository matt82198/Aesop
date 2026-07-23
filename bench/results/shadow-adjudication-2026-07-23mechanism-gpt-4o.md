# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-23
**Challenger Model**: gpt-4o (OpenAI-compatible)
**Corpus Size**: 16 items

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 50.0%
- **Real Defect Subset Agreement**: 66.7%
- **False Positive Subset Agreement**: 20.0%
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
| vbs-waitforexit | enhancement_opportunity | real_defect | ✗ | 0.85 | ✓ |
| dryrun-blocked | enhancement_opportunity | real_defect | ✗ | 0.85 | ✓ |
| uninstall-exit0 | real_defect | real_defect | ✓ | 0.90 | ✓ |
| quote-validation | real_defect | real_defect | ✓ | 0.90 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.90 | ✓ |
| unc-paths | enhancement_opportunity | real_defect | ✗ | 0.85 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.90 | ✓ |
| audit-log-observability | real_defect | enhancement_opportunity | ✗ | 0.90 | ✓ |
| whitelist-gate-weakening | enhancement_opportunity | false_positive | ✗ | 0.90 | ✓ |
| ps1-syntax-gate | enhancement_opportunity | enhancement_opportunity | ✓ | 0.90 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.90 | ✓ |
| fixreview-parents1 | undetermined | false_positive | ✗ | 0.50 | ✓ |
| fixreview-backtick-test | real_defect | false_positive | ✗ | 0.90 | ✓ |
| regression-ui-suite | false_positive | false_positive | ✓ | 0.90 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.90 | ✓ |
| vbs-syntax-validity | undetermined | false_positive | ✗ | 0.50 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings