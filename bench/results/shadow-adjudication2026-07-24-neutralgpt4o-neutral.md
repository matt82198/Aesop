# Shadow Adjudication Wave — Scorecard Report

**Date**: 2026-07-24
**Challenger Model**: gpt-4o (OpenAI-compatible)
**Corpus Size**: 16 items
**Runs**: 5 (increment 2.6: verdict-neutral corpus)

## Aggregate Statistics

- **Overall Agreement (vs incumbent)**: 62.5%
- **Real Defect Subset Agreement**: 100.0%
- **False Positive Subset Agreement**: 20.0%
- **Rubber-Stamp Refutations** (items 9, 14 correctly classified as false_positive): 0/2
- **Schema Validity Rate**: 100.0%
- **DECISION_FAILED Count**: 0

## Narrative-Refusal Stability (Items 9, 13)

**Item 9 (whitelist-gate-weakening, gt=false_positive)**:

| Verdict | Runs | Stability |
|---|---|---|
| real_defect | 5/5 | 100% |

**Modal verdict**: real_defect (5/5 runs)

**Item 13 (fixreview-backtick-test, gt=false_positive)**:

| Verdict | Runs | Stability |
|---|---|---|
| false_positive | 3/5 | 60% |
| real_defect | 2/5 | 40% |

**Modal verdict**: false_positive (3/5 runs)

## Success Bar Results

- >=80% agreement on gt=real_defect items: **PASS** (100.0%)
- >=1 of items {9, 14} classified false_positive: **FAIL** (0/2)
- >=90% schema-valid without retry exhaustion: **PASS** (100.0%)

## Item-by-Item Results

| ID | Challenger | Ground Truth | Correct | Confidence | Schema Valid |
|---|---|---|---|---|---|
| vbs-waitforexit | real_defect | real_defect | ✓ | 0.90 | ✓ |
| dryrun-blocked | real_defect | real_defect | ✓ | 0.90 | ✓ |
| uninstall-exit0 | real_defect | real_defect | ✓ | 0.90 | ✓ |
| quote-validation | real_defect | real_defect | ✓ | 0.90 | ✓ |
| apostrophe-path | real_defect | real_defect | ✓ | 0.90 | ✓ |
| unc-paths | real_defect | real_defect | ✓ | 0.90 | ✓ |
| hardcoded-username | real_defect | real_defect | ✓ | 0.90 | ✓ |
| audit-log-observability | real_defect | enhancement_opportunity | ✗ | 0.90 | ✓ |
| whitelist-gate-weakening | real_defect | false_positive | ✗ | 0.90 | ✓ |
| ps1-syntax-gate | real_defect | enhancement_opportunity | ✗ | 0.90 | ✓ |
| test-hardcoded-path | real_defect | real_defect | ✓ | 0.95 | ✓ |
| fixreview-parents1 | real_defect | false_positive | ✗ | 0.90 | ✓ |
| fixreview-backtick-test | false_positive | false_positive | ✓ | 0.85 | ✓ |
| regression-ui-suite | real_defect | false_positive | ✗ | 0.90 | ✓ |
| cimergewait-exit0 | real_defect | real_defect | ✓ | 0.90 | ✓ |
| vbs-syntax-validity | real_defect | false_positive | ✗ | 0.90 | ✓ |

## Caveats

- **Corpus Size**: N=16 (single replay, not statistically comprehensive)
- **Blind but Authored**: Challenger sees only finding_text + source_lens, but corpus was authored by the incumbent (potential selection bias)
- **Single Run**: No repeated trials; variance not measured
- **Real-World Drift**: Actual adjudication may differ on live production findings