# Adversarial Review: PR #314 Mutation Testing Tool

**Status**: **FIX-FIRST** — Ship with fixes or defer. Do not merge in current state.

**Reviewer**: Adversarial Read-Only Auditor  
**Date**: 2026-07-22  
**Contract**: Mutation testing sandbox leak-proof, wave_loop works 2/3, validation 5/5 faults with 100% accuracy

---

## Executive Summary

The PR fixes critical sandbox issues (sibling imports now copied) but leaves one fundamental integration problem unfixed. The validation claims cannot be reproduced. The tool ships with known-broken module coverage that's documented as "under investigation (non-blocking)" — this is not honest for a correctness tool.

**Verdict**: The 2/3 working modules + 1 documented-broken state is acceptable ONLY if:
1. wave_loop issue is explicitly documented in CLI help + README
2. Validation is reproducible (missing fixtures must be added or claim removed)
3. Actual test results match reported numbers (wave_audit_tail discrepancy)

---

## Break-it Claim 1: LEAK-PROOF Sandbox Shadowing

### Claim
> sys.path precedence proof — does the sandbox correctly shadow mutated files when siblings are involved under every import order?

### Finding: ❌ **FAILS** for package imports

**Root Cause**: Sandbox copies sibling .py files but doesn't preserve **package structure**.

**Evidence**:
- `test_wave_loop.py` line 893: `from driver import verification_policy as vp_module`
- This expects a `driver/` package directory, not just `verification_policy.py` in tmpdir
- When mutation_test.py runs, it flattens all files into tmpdir (no package dirs)
- Result: `ModuleNotFoundError: No module named 'driver'`

**Actual Test Run** (wave_loop baseline in sandbox):
```
{
  "error": "baseline tests fail in sandbox — results invalid"
}
```

**Passing Case** (simple sibling imports):
- TestMutationTestWithSiblingImports tests pass ✓
- These only test direct module imports (`import fixture_sibling_config`)
- Do NOT test package imports (`from driver import X`)

### Impact
- **wave_loop.py + test_wave_loop.py**: Cannot be mutation tested (baseline fails)
- **ui/wave_audit_tail.py + test_ui_wave_audit_tail.py**: Works (only `import config`, `import cost`)
- **driver/codex_driver.py + test_codex_driver_e2e.py**: Works (only direct imports)

### Fix Required
Create proper package structure in tmpdir:
```python
# In mutation_test.py run() function, after copying files:
for sibling in tmpdir.glob("*.py"):
    parent_package = tmpdir / target_path.parent.name
    parent_package.mkdir(exist_ok=True)
    shutil.move(str(sibling), str(parent_package / sibling.name))
(tmpdir / "driver" / "__init__.py").touch()
(tmpdir / "ui" / "__init__.py").touch()
```

---

## Break-it Claim 2: wave_loop Isolation Issue Status

### Claim
> The PR says "sandbox isolation issue under investigation (CI parity)" — is this 2/3 fixed + 1 documented honest or premature shipping?

### Finding: ❌ **Premature to ship as-is**

**Evidence**:
- Validation report line 36-38:
  > "Status: Baseline test passes when run directly; sandbox isolation issue under investigation (CI parity)"
  > "Note: Tests (47 test cases) pass in normal pytest; workaround: use -m pytest directly"

- Direct pytest run: **PASS** (47/47 tests) ✓
- Sandbox baseline: **FAIL** (ModuleNotFoundError from package import)
- The "workaround" (use `-m pytest directly`) doesn't apply — the sandbox still fails

**Baseline Test Results**:
```bash
$ cd aesop && python -m pytest tests/test_wave_loop.py -v
# Result: 47 passed ✓

$ cd aesop && python tools/mutation_test.py --target driver/wave_loop.py --test tests/test_wave_loop.py --json
# Result: {"error": "baseline tests fail in sandbox — results invalid"} ✗
```

### Honesty Assessment
- **Claim**: 2/3 modules work, 1 has known CI parity issue (not blocking)
- **Reality**: 1/3 modules is completely untestable in sandbox (hard blocker)
- **Assessment**: Understated severity; "non-blocking" should be "blocking for wave_loop coverage"

### Fix Required
Either:
1. Fix the package import issue (Claim 1 fix applies here)
2. OR explicitly document: "wave_loop.py cannot be mutation tested — see LIMITATIONS.md"

---

## Break-it Claim 3: Validation Fixture Reproducibility

### Claim
> 5-fault validation: fixture/test files exist and CI can reproduce the "100% accuracy" claim

### Finding: ❌ **NOT REPRODUCIBLE**

**Missing Files**:
- `mutation_fault_fixture.py` — not in repo
- `test_mutation_fault_fixture.py` — not in repo
- No CI script that generates validation results

**Evidence**:
```bash
$ find . -name "*fault*" -type f
# (no output)

$ grep -r "mutation-validation" --include="*.py" --include="*.sh"
# (no output — no automation)
```

**Validation Report Claims** (bench/results/mutation-validation.md):
- Shows Python code for fixture + test
- Claims "100% accuracy: 5/5 faults" (2 killed, 3 survived as expected)
- Report signed "Validation Summary: Tool accuracy: 5/5 faults (100%)"

**Status**: One-time manual validation, NOT reproducible

### Credibility Impact
- Cannot re-run validation to verify mutation tool correctness
- Cannot prove kill-detection accuracy against known faults
- Cannot audit if fixtures were real modules (contamination risk) vs isolated fixtures

### Fix Required
**Restore reproducibility**:
```bash
# Add to repo:
- bench/fixtures/mutation_fault_fixture.py (exactly as shown in report)
- bench/fixtures/test_mutation_fault_fixture.py
- bench/validate-fixtures.sh (regenerates mutation-validation.md)

# Update CI:
- Add step: `bash bench/validate-fixtures.sh` (must pass before merge)
```

---

## Break-it Claim 4: Data Accuracy — wave_audit_tail Mismatch

### Claim
> Validation report shows kill rates for three real modules; do reported numbers match actual runs?

### Finding: ⚠️  **PARTIAL MISMATCH** (only wave_audit_tail)

**Comparison**:

| Module | Metric | Reported | Actual | Match |
|--------|--------|----------|--------|-------|
| wave_audit_tail | Killed | 8 (44.4%) | 7 | ❌ |
| wave_audit_tail | Survived | 10 (55.6%) | 11 | ❌ |
| wave_audit_tail | Total | 18 | 18 | ✓ |
| codex_driver | Killed | 17 (42.5%) | 17 | ✓ |
| codex_driver | Survived | 23 (57.5%) | 23 | ✓ |
| codex_driver | Total | 40 | 40 | ✓ |
| wave_loop | Status | baseline fail | baseline fail | ✓ |

**Actual Run Output**:
```bash
$ python tools/mutation_test.py --target ui/wave_audit_tail.py \
  --test tests/test_ui_wave_audit_tail.py --json
# {"killed": 7, "survived": 11, "mutations": [...]}
```

**Hypothesis for Mismatch**:
- Mutation recording order changed between report generation and current code
- One mutation's classification changed (survived vs killed)
- Possible cause: ast.NodeTransformer visitor order is non-deterministic or changed

### Fix Required
1. Re-run all three modules to generate fresh validation-results.md
2. Compare output to verify reproducibility
3. OR update report to match actual results with explanation

---

## Break-it Claim 5: Performance Cost — ACCEPTABLE

### Claim
> Copying siblings to tmpdir for large packages (ui/ has many files) — is runtime reasonable?

### Finding: ✓ **ACCEPTABLE**

**Measured**:
- ui/wave_audit_tail.py: 18 mutations, 9.11s total, **0.506s/mutation**
- ui/ contains 17 .py files
- Overhead per mutation: ~100ms file copy + ~400ms test execution

**Assessment**: Copying is negligible compared to pytest startup + test execution. No optimization needed.

---

## Summary Table

| Claim | Test | Finding | Severity | Fix Required |
|-------|------|---------|----------|--------------|
| 1. LEAK-PROOF | Package imports fail in sandbox | FAIL | **HIGH** | Preserve package structure in tmpdir |
| 2. wave_loop | Cannot be mutation tested | FAIL | **HIGH** | Fix Claim 1 or document limitation |
| 3. Fixture validation | Files missing, not reproducible | FAIL | **MEDIUM** | Add fixture files + CI validation step |
| 4. Data accuracy | wave_audit_tail results mismatch | FAIL | **MEDIUM** | Re-run and reconcile |
| 5. Performance | Copying cost per mutation | PASS | - | No action |

---

## Recommendation: FIX-FIRST

Do not merge PR #314 in its current state. Required before shipping:

1. **BLOCKING (HIGH)**: Fix sandbox package structure to support `from X import Y` imports
   - Affects: wave_loop (currently broken), future modules with package imports
   - Effort: ~20 lines of code in mutation_test.py

2. **BLOCKING (HIGH)**: Update validation report OR restore reproducible validation
   - Remove "100% accuracy" claim if fixtures can't be reproduced
   - OR add fixture files + CI step to regenerate validation report

3. **REQUIRED (MEDIUM)**: Reconcile wave_audit_tail data mismatch
   - Re-run and document why numbers changed OR identify regression

4. **REQUIRED (MEDIUM)**: Explicit documentation of limitations
   - Add LIMITATIONS.md or CLI help: "wave_loop.py is not yet supported"
   - Once Claim 1 is fixed, re-validate wave_loop and remove limitation

---

## Honest Shipping Posture

**Current**: "Tool validates 3 real modules with 100% fixture accuracy, 2/3 work in sandbox + 1 under investigation"  
**Honest**: "Tool validates 3 real modules, 2/3 work in sandbox, fixture validation not reproducible, package imports need fixing"

The tool IS correct on what it DOES test (codex_driver, wave_audit_tail pass). But it's incomplete (wave_loop fails) and unverified (fixtures gone). Honest shipping means fixing or documenting both.

